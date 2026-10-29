# Núcleo operacional v2 — diseño, riesgos y operación

> **Pregunta que responde:** ¿cómo funciona el schema `nucleo` y su motor de disponibilidad?
> **Dueño:** `arquitectura` · **Verificado:** 2026-10-29 · **Método:** lectura de DDL `0004`–`0019` y servicios
> **Caduca si:** cambia una migración del núcleo o `servicio_disponibilidad.py`.
> **Re-verificar con:** `grep -c "exclude using gist" supabase/migrations/0004_nucleo_operacional.sql`


**Versión:** 1.0  
**Fecha:** Octubre 2026  
**Alcance:** Fase 1 del Plan Maestro (piloto 90 días): empresa, flota, choferes, OC, tarifas, viaje, disponibilidad, cumplimiento documental y auditoría.

---

## 1. Decisión de arquitectura: schema `nucleo`, no un big bang

El MVP actual vive en `public` (`clientes`, `tractos`, `viajes`, …). El nuevo núcleo vive en el schema PostgreSQL **`nucleo`**. Esto permite:

- No romper las 15 pantallas ni los 12 routers existentes mientras se desarrolla el piloto.
- Tener una fuente de verdad limpia para la Fase 1: multiempresa real, `timestamptz`, OC, tarifas, documentos versionados y libro de reservas.
- Migrar por estrangulamiento (*strangler*): primero maestros, luego viajes abiertos, luego se apaga la escritura legacy y se conmuta la mesa de despacho.

**Regla de cutover:** durante la ventana de migración, la disponibilidad se calcula **solo** en `nucleo`. Nunca se permiten asignaciones simultáneas en `public.viajes` y `nucleo.viajes`; sería la peor forma de crear una doble asignación.

La migración DDL es `supabase/migrations/0004_nucleo_operacional.sql`. Los modelos Python están en `backend/app/nucleo/models.py`. El servicio está en `backend/app/nucleo/servicio_disponibilidad.py` y la API en `backend/app/nucleo/api.py`.

---

## 2. Los tres mayores puntos de fallo del motor de disponibilidad

### Riesgo 1 — La restricción de exclusión cubre viajes, pero no la realidad operativa

Una restricción directa sobre `viajes` tiene dos agujeros:

1. **Solo ve viajes.** Una mantención, un descanso obligatorio, un bloqueo por siniestro o una unidad en taller no están en `viajes`. El camión puede estar “libre” para el motor y estar físicamente en el taller.
2. **Los NULL no colisionan.** En PostgreSQL, `EXCLUDE USING gist (tracto_id WITH =, ...)` no considera conflicto cuando `tracto_id` es NULL. Un viaje a medio asignar, un recurso opcional o una fila mal construida puede pasar silenciosamente.

**Mitigación implementada:** un libro único de ocupación, `nucleo.reservas_recurso`, con exactamente un recurso tipado por fila y tres restricciones parciales:

```sql
alter table nucleo.reservas_recurso
  add constraint ex_reserva_tracto
  exclude using gist (tracto_id with =, ventana with &&)
  where (recurso_tipo = 'tracto' and activa);

alter table nucleo.reservas_recurso
  add constraint ex_reserva_rampla
  exclude using gist (rampla_id with =, ventana with &&)
  where (recurso_tipo = 'rampla' and activa);

alter table nucleo.reservas_recurso
  add constraint ex_reserva_chofer
  exclude using gist (chofer_id with =, ventana with &&)
  where (recurso_tipo = 'chofer' and activa);
```

- `tracto`, `rampla` y `chofer` compiten en igualdad de condiciones contra mantenciones, descansos, vacaciones y bloqueos manuales.
- La fila tiene `CHECK` de un solo recurso; no hay NULL ambiguo en la dimensión de igualdad.
- Los viajes se sincronizan automáticamente al libro mediante `fn_viaje_reservas` (AFTER INSERT/UPDATE). Cambiar tracto, rampla, chofer, ventana, ETA o anular el viaje mueve las reservas en la misma transacción.
- Las reservas históricas no se borran: se desactivan (`activa=false`). La auditoría conserva qué ocupó qué y cuándo.

**Costo:** una tabla más y un trigger. **Beneficio:** una sola definición de “ocupado” para toda la empresa, no tres validaciones incompletas.

---

### Riesgo 2 — TOCTOU: dos despachadores ven “libre” al mismo tiempo

El patrón “consultar disponibilidad → validar → insertar” es una condición de carrera clásica. Dos requests concurrentes pueden leer el mismo hueco y ambos creer que ganaron. Un `if` en Python no es una garantía transaccional.

**Mitigación implementada en tres capas:**

1. **Bloqueo del viaje:** `SELECT ... FOR UPDATE` sobre `nucleo.viajes` antes de validar y escribir.
2. **Locks de asesoría por recurso**, ordenados lexicográficamente para evitar deadlocks:
   ```sql
   select pg_advisory_xact_lock(hashtextextended('nucleo:tracto:<uuid>', 0));
   ```
   Se toman los tres (tracto, rampla, chofer) en orden determinista.
3. **La base como árbitro final:** aunque el servicio se equivoque, la restricción `EXCLUDE` rechaza el segundo `INSERT` con SQLSTATE `23P01`. El servicio traduce ese error a `409 CONFLICTO_DISPONIBILIDAD`, no a un 500.

Además, el `UPDATE` del viaje lleva `WHERE version = :version`; si otro usuario lo modificó, se devuelve `409 CONFLICTO_CONCURRENCIA` en lugar de pisar el cambio.

**Regla de ingeniería:** la previsualización (`POST /validar-asignacion`) es para explicar y decidir; **la confirmación (`POST /viajes/{id}/asignar`) es la que garantiza**. Nunca se confirma una asignación solo con el resultado de la previsualización.

---

### Riesgo 3 — Semántica temporal: DST, rangos inclusivos y ETA móvil

Chile cambia de hora dos veces al año. Un ERP de flota que trabaje con `date` o con `datetime` naive puede:

- Crear un viaje que “termina” una hora antes o después de lo real en el cambio de hora.
- Marcar conflicto en el borde (`13:00`) cuando un viaje termina exactamente a las 13:00 y otro empieza a las 13:00.
- Olvidar que el buffer operacional (90 minutos por defecto) también ocupa al recurso.
- Permitir que una ETA retrasada invada el siguiente viaje porque la reserva no se movió.

**Mitigaciones implementadas:**

- Todo se almacena en `timestamptz` (UTC). La zona `America/Santiago` se usa solo para numeración, vencimientos y presentación.
- Los rangos son **semiabiertos** `[inicio, fin)` en `tstzrange`. Un viaje que termina a las 13:00 no bloquea uno que empieza a las 13:00; uno que termina a las 13:00:01 sí.
- El buffer operacional se incluye **dentro** de la reserva: `[inicio, fin + buffer)`. No se suma dos veces en el cálculo de “libre desde”.
- `fin_estimado` y `fin_real` forman parte de la ventana. Si la ETA se mueve, el trigger recalcula la reserva y la restricción de exclusión vuelve a validar contra el siguiente viaje.
- La API rechaza datetimes naive con 422. No hay “hora local implícita”.
- Hay tests específicos para el salto DST de Chile (`2026-09-06`) y para los bordes semiabiertos.

**Decisión operativa:** la validación documental dura se exige al **asignar/despachar**, no en cada cambio de estado. Si un documento vence mientras el camión ya está en ruta, el sistema no bloquea `en_ruta → en_descarga`; bloquearlo dejaría la carga varada. El vencimiento se alerta y se resuelve al cerrar/renovar.

---

## 3. Modelo de datos

| Tabla | Rol | Notas |
|---|---|---|
| `nucleo.empresas` | Tenant | Buffer, zona horaria, moneda, políticas documentales |
| `nucleo.usuarios_empresa` | Membresía | `auth_id` de Supabase + rol; no se confía en `empresa_id` del body |
| `nucleo.clientes` | Comercial | `exige_oc`, crédito, días de pago |
| `nucleo.tractos` | Flota | Capacidad, peso bruto/tara, licencias permitidas, documentos |
| `nucleo.ramplas` | Flota | Tipo, capacidad, volumen, temperaturas |
| `nucleo.choferes` | Personas | Licencia, autorización de carga peligrosa |
| `nucleo.documentos` | Cumplimiento | Versionado, `vence_en`, hash, un vigente por tipo/recurso |
| `nucleo.tarifas` | Comercial | Modalidad, vigencia, moneda, recargos, snapshot |
| `nucleo.ordenes_compra` | Comercial | Saldo autorizado, sobregiro aprobado, consumo |
| `nucleo.ordenes_compra_lineas` | Comercial | Detalle de la OC |
| `nucleo.viajes` | Átomo | Carga, ventana, recursos, snapshot financiero, estados |
| `nucleo.reservas_recurso` | Disponibilidad | Libro único de ocupación con `EXCLUDE` |
| `nucleo.transiciones_viaje` | Workflow | Máquina de estados explícita |
| `nucleo.folio_contador` | Numeración | `VJ-2026-000001`, concurrencia segura |
| `nucleo.auditoria` | Auditoría | Append-only, inmutable, antes/después |

**Multiempresa:** todas las tablas transaccionales llevan `empresa_id`, y las FKs son compuestas `(empresa_id, id)` contra los maestros. Esto impide asignar un tracto de otra empresa incluso si se adivina el UUID. El servicio filtra siempre por `contexto.empresa_id`; el `empresa_id` del body no existe.

**Dinero:** `numeric(14,2)` para totales, `numeric(16,4)` para precios unitarios. Nunca `float`.

**Fechas:** `timestamptz` para eventos; `date` para vencimientos y vigencias.

---

## 4. “Libre desde”: definición y algoritmo

El plan maestro define:

```
libre_desde = max(
  fin_estimado_viaje_actual,
  fin_mantenimiento,
  fin_descanso,
  fecha_habilitación_documentos
) + buffer_operacional
```

Implementación operativa:

1. Se leen todas las reservas activas del recurso con `upper(ventana) > desde`.
2. Se ordenan por inicio y se avanza por la **cadena contigua** de ocupación.
3. Si el recurso está libre en `desde`, `libre_desde = desde` (no se inventa una espera).
4. Si está ocupado, `libre_desde` es el fin de la cadena contigua. Un hueco, por pequeño que sea, corta la cadena; el llamador decide si la ventana solicitada cabe.
5. El buffer ya está dentro de cada reserva de viaje; no se suma de nuevo.
6. Si un documento obligatorio está vencido o no alcanza a cubrir el fin del viaje + margen, `libre_desde = null` y el recurso es **no asignable**. No se devuelve una fecha ficticia de “renovación”.
7. El traslado en vacío se agrega aparte: `inicio_operativo_posible = libre_desde + minutos_traslado`. Si el inicio propuesto es anterior, se bloquea con `TRASLADO_INSUFICIENTE`.

La función pura está en `backend/app/nucleo/tiempo.py` (`calcular_libre_desde`), probada sin base de datos.

---

## 5. API

Prefijo: `/api/v1/nucleo`. Header obligatorio: `X-Empresa-ID`. Autenticación: JWT de Supabase. Roles de lectura: admin, gerente, despacho, contador, tesorería, taller, auditor. Escritura: admin, gerente, despacho.

| Método | Ruta | Uso |
|---|---|---|
| GET | `/mis-empresas` | Empresas activas del usuario autenticado (sin `X-Empresa-ID`) |
| GET | `/empresa` | Empresa activa y configuración |
| GET | `/viajes` | Viajes confirmados/asignados para la mesa de despacho |
| GET | `/disponibilidad/recursos` | Lista de tractos/ramplas/choferes con `libre_desde`, documentos y conflictos para una ventana |
| GET | `/disponibilidad/recursos/{tipo}/{id}/libre-desde` | Detalle de un recurso y próximas reservas |
| POST | `/disponibilidad/validar-asignacion` | Previsualización: ¿es apto? ¿por qué no? |
| POST | `/viajes/{id}/asignar` | Confirmación atómica; devuelve reservas, versión y auditoría |

La pantalla **Mesa de despacho** (`/despacho`) consume estos endpoints: muestra
viajes por asignar, disponibilidad por recurso, valida antes de confirmar y
exige motivo cuando se reasigna un viaje ya asignado.

Ejemplo de validación:

```json
{
  "viaje_id": "…",
  "tracto_id": "…",
  "rampla_id": "…",
  "chofer_id": "…",
  "inicio_planificado": "2026-11-01T08:00:00-03:00",
  "fin_planificado": "2026-11-01T12:00:00-03:00",
  "minutos_traslado": 30,
  "buffer_minutos": 90
}
```

La respuesta incluye `apto`, `incidencias`, `conflictos`, `documentos`, `libre_desde`, `inicio_operativo_posible`, `flete_total`, `oc_numero` y `tarifa_codigo`. Los errores de dominio tienen forma estable:

```json
{
  "codigo": "CONFLICTO_DISPONIBILIDAD",
  "mensaje": "No apto: 0 bloqueo(s) y 3 conflicto(s).",
  "contexto": {"viaje_id": "…"},
  "errores": [{"codigo": "CONFLICTO_RESERVA", "mensaje": "…"}]
}
```

Códigos HTTP: 401/403 auth/empresa/rol; 404 recurso; 409 conflicto/estado/transición/concurrencia; 422 datos/regla de capacidad/OC; 500 error inesperado.

---

## 6. Reglas duras y casos borde financieros

### Cumplimiento documental

- Tracto: revisión técnica, permiso de circulación, seguro obligatorio y SOAP (exigido por defecto).
- Rampla: revisión técnica, permiso de circulación, seguro de carga (exigido por defecto), certificado de gases si es refrigerada.
- Chofer: licencia de conducir, examen médico, curso de carga peligrosa si aplica.
- La ausencia se trata igual que el vencimiento: **bloquea**.
- El documento debe estar vigente hasta `fin del viaje + buffer + días de margen` de la empresa. Un documento que vence durante el viaje no sirve para despachar.
- Nuevo documento del mismo tipo desactiva la versión anterior; el índice único parcial impide dos vigentes.

**Documentos adicionales a confirmar con prevención de riesgos/legal:** tacógrafo, limitador de velocidad, extintores, botiquín, triángulos, sujeción de carga y permisos especiales. El modelo ya tiene el tipo `otro` y la tabla de documentos permite cargarlos con vencimiento; se activan como bloqueo duro cuando TEI entregue la lista definitiva y su periodicidad. No se hardcodean obligaciones legales sin esa validación.

### Capacidad y compatibilidad

- Peso bruto de carga contra capacidad del tracto y de la rampla.
- Volumen contra capacidad de la rampla.
- Refrigerada exige rampla refrigerada y temperaturas dentro de rango.
- Contenedor exige portacontenedores.
- Sobredimensionada exige plana o cama baja.
- Carga peligrosa exige número UN, permiso y chofer autorizado.
- La clase de licencia se compara contra `licencias_permitidas` del tracto como **control interno/documental**: una diferencia genera advertencia, no bloqueo. La vigencia del documento de licencia sí es un bloqueo duro. No se hardcodea normativa legal.

### Buffer operacional

El valor por defecto es **90 minutos**: cubre descarga, firma de POD, combustible, revisión básica y traslado corto en rutas de carga pesada. Se puede sobrescribir por viaje: 60 min para rutas locales rápidas, 120 min para puertos, faenas o clientes con esperas. Es una reserva de capacidad, no un tiempo muerto.

### OC y tarifa

- Sin tarifa vigente, del mismo cliente y misma moneda: no se despacha.
- **La OC es requisito de facturación, no de despacho.** Un viaje sin OC puede operar, pero el trigger `fn_viaje_facturacion` impide pasarlo a `facturado` hasta cargar una OC válida. El servicio lo muestra como advertencia `OC_PENDIENTE_FACTURACION`.
- Si el viaje tiene una OC vinculada, se valida que sea del mismo cliente, misma moneda, vigente al inicio y al fin, y con saldo. Una OC inválida vinculada se rechaza para no arrastrar un documento que no servirá para facturar.
- El consumo de OC se recalcula de forma idempotente sumando los viajes no borrador/cotizado/anulado.
- **Caso borde crítico:** al asignar un viaje que ya estaba `confirmado`, su monto ya estaba incluido en `monto_consumido`. El trigger resta el monto anterior antes de comparar; de lo contrario, un viaje de $60.000 contra una OC de $100.000 se rechazaría por “$120.000 consumidos”. Este caso está cubierto por `fn_viaje_validar` y por una prueba de integración.
- El snapshot de tarifa y el número de OC se congelan al asignar. Los campos financieros se congelan al entrar a `en_carga`; un ajuste posterior requiere un mecanismo auditado (`nucleo.ajuste_autorizado`).

### Inmutabilidad y reasignación

- Si un viaje ya está `asignado` y cambian tracto, rampla, chofer, ventana o buffer, se exige `motivo_reasignacion`. Las reservas anteriores se desactivan, no se borran, y quedan en el historial auditable.
- No se borra un viaje asignado/en ejecución/cerrado. Se anula con motivo.
- No se borran documentos; se versionan.
- No se borran reservas; se desactivan.
- `auditoria` es append-only por trigger.
- `numero_viaje`, `empresa_id` y los campos financieros tienen protección explícita.

---

## 7. Pruebas ejecutadas

- **Unitarias (sin base):** 41 tests de tiempo/DST, políticas de capacidad/licencia/OC/tarifa, contratos Pydantic y metadatos SQLModel.
- **SQL real (PostgreSQL 18/PGlite):** migración completa, 3 restricciones `EXCLUDE`, doble asignación, borde exacto de buffer, mantención que solapa, versión de documentos, borrado prohibido, OC sobreconsumida, transición ilegal, anulación y reutilización de ventana, documento vencido, auditoría.
- **Servicio real (psycopg + SQLModel):** asignación, 3 reservas, buffer, conflicto, reasignación, OC límite sin doble conteo, documento vencido, auditoría.
- **HTTP real (FastAPI TestClient):** 200 en validar/asignar, 422 en datetime naive y reasignación sin motivo, 409 en solapamiento.

La prueba de integración versionada está en `backend/tests/test_nucleo_integracion.py` y se ejecuta solo si existe `NUCLEO_TEST_DATABASE_URL`.

---

## 8. Cómo aplicar y operar

### Base de datos

```bash
# Con Supabase CLI (recomendado)
supabase db push

# O aplicando la migración en un PostgreSQL local
psql "$DATABASE_URL" -f supabase/migrations/0004_nucleo_operacional.sql
```

La migración requiere PostgreSQL 15+ y las extensiones `btree_gist` y `pgcrypto`.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/test_nucleo_tiempo.py tests/test_nucleo_politicas.py \
       tests/test_nucleo_schemas.py tests/test_nucleo_modelos.py -q
```

Para integración:

```bash
export NUCLEO_TEST_DATABASE_URL="postgresql+psycopg://user:pass@host:5432/db"
pytest tests/test_nucleo_integracion.py -q
```

### Membresía inicial

El usuario autenticado debe tener una fila en `nucleo.usuarios_empresa`:

```sql
insert into nucleo.usuarios_empresa (empresa_id, auth_id, rol)
values ('<uuid-empresa>', '<auth_id-supabase>', 'admin');
```

---

## 9. Migración desde el MVP y siguientes pasos

### Cutover recomendado

1. Crear empresa TEI y membresías.
2. Migrar clientes, tractos, ramplas y choferes; normalizar RUT/patente.
3. Cargar documentos críticos con `vence_en`; los que falten bloquean asignaciones (es intencional).
4. Migrar tarifas y OC abiertas.
5. Migrar viajes abiertos a `nucleo.viajes`, con recursos y ventana; generar `numero_viaje` con `siguiente_folio`.
6. Apagar escritura de asignaciones en `public.viajes`; conmutar la mesa de despacho a `/api/v1/nucleo`.
7. Mantener `public` como histórico de solo lectura hasta el cierre del piloto.

### Limitaciones conocidas

- El listado de disponibilidad calcula en memoria y tiene un tope de 500 recursos por consulta. Para una flota mayor, mover los filtros de documentos/reservas a SQL o materializar una vista.
- No existen aún endpoints para crear mantenciones/descansos; el libro de reservas ya los soporta y el motor los respeta.
- El “libre desde” de un recurso sin viaje propuesto usa el día actual + margen documental; la validación exacta se hace contra el viaje concreto.

### Fuera de este entregable (fase siguiente)

- Endpoints CRUD de maestros y documentos (el servicio de disponibilidad ya los consume).
- Registro de mantenciones/descansos como órdenes con aprobación; hoy se modelan como reservas con ventana.
- Horas de conducción y descanso legal (requiere validación laboral).
- DTE/SII, pagos, tesorería y contabilidad.
- Portal del cliente y PWA del conductor.
- Job diario que marque OC vencidas y alertas de documentos.

---

## 10. Resumen ejecutivo

El motor no depende de que el frontend “se porte bien”. La base de datos impide la doble asignación de tracto, rampla y chofer contra **cualquier** fuente de ocupación; el servicio explica por qué no se puede asignar y calcula cuándo sí; la confirmación es atómica y auditada. Los tres riesgos estructurales —cobertura incompleta, concurrencia y semántica temporal— están atacados en la capa donde no se pueden saltar: PostgreSQL.
