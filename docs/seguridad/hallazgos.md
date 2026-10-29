# Auditoría de seguridad e integridad — R-01 (comisión) / R-02 (licencia A5) / 0015 (ocupación)

- **Rol:** `auditor-seguridad` (revisión independiente, sin acceso a la conclusión del autor).
- **Fecha:** 2026-10-29.
- **Naturaleza:** auditoría **estática**. No se ejecutó código ni SQL (ver §0.2).
- **Veredicto original:** **bloquear el cierre de R-01** (SEC-001, SEC-002 tocan dinero de trabajadores);
  **aprobar con cambios** el bloqueo A5 (SEC-005, SEC-006 son huecos de integridad, no bypass trivial).

---

## Estado al 2026-10-29 (posterior a esta auditoría)

> Esta sección la mantiene el `orquestador`. El cuerpo del informe **no se reescribe**:
> es evidencia de lo que se observó. Acá se registra qué cambió después.

| ID | Veredicto original | Estado hoy | Evidencia |
|---|---|---|---|
| SEC-001 | alta · comisión perdida por período | 🟢 **corregido** | `liquidaciones.py:51-96` imputa por `Factura.fecha_emision` |
| SEC-002 | alta · PDF recalcula en vivo | 🔴 **abierto** | `liquidaciones.py:515-533` sigue recalculando al generar el PDF |
| SEC-008 | media · PII a cualquier autenticado | 🟢 **corregido** | `liquidaciones.py:30` `require_roles(admin, contabilidad)` |

**El bloqueo de R-01 sigue vigente, pero sólo por SEC-002.**

Los demás hallazgos (SEC-003 a SEC-007, SEC-009 a SEC-015) conservan el estado del
informe original: no fueron re-verificados en esta sesión 🔴.

Actualizado: 2026-10-29. Re-verificar con `grep -n "_comision_chofer" backend/app/api/routes/liquidaciones.py`.

---

## 0. Alcance y método

### 0.1 Alcance revisado (exacto)

| Archivo | Tipo | Leído |
|---|---|---|
| `backend/app/api/routes/liquidaciones.py` | modificado | completo (506 líneas) |
| `backend/app/models/__init__.py` | modificado | secciones 1–129 + grep dirigido |
| `backend/app/schemas/catalogos.py` | modificado | completo (79) |
| `backend/app/nucleo/models.py` | modificado | secciones 212–236, 575–599 |
| `backend/app/nucleo/politicas.py` | modificado | completo (447) |
| `scripts/seed_local.py` | modificado | secciones 118–199, 310–347, 440–499, 555–649 |
| `Makefile` | modificado | completo (82) |
| `supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql` | nuevo | completo (479) |
| `supabase/migrations/0016_licencia_a5_bloqueante.sql` | nuevo | completo (275) |
| `supabase/migrations/0017_default_comision_chofer.sql` | nuevo | completo (51) |
| `backend/tests/test_reglas_negocio.py` | nuevo | completo (864) |
| `backend/tests/test_nucleo_politicas.py` | modificado | completo (354) |
| `frontend/e2e/tei.spec.ts` | modificado | completo (103) |

Contexto leído solo para entender hallazgos (fuera de alcance, no auditado):
`0001_esquema_base.sql`, `0004_nucleo_operacional.sql`, `api/deps.py`,
`api/router.py`, `api/routes/facturas.py`, `api/routes/viajes.py`,
`api/routes/export.py`, `core/config.py`, `tests/conftest.py`,
`scripts/cutover_legacy.py`, `supabase/tests/0016_0{1,2}*.sql`.

### 0.2 Limitación de método — leer antes que nada 🔴

**El permiso de `shell` fue rechazado en esta sesión.** No pude:

- ejecutar `git diff -- <archivo>` → **no sé qué líneas son nuevas y cuáles preexistentes**;
- ejecutar `psql` contra `127.0.0.1:54322` → **no hay reproducción en base**;
- ejecutar `pytest` / `make test` → **no hay salida real de pruebas**.

Por lo tanto: todos los hallazgos se sostienen sobre **lectura de código con cita
`archivo:línea`**, y los efectos en PostgreSQL se deducen del DDL (nivel 🟢 según
`AGENTS.md` §2 = "leído en código/DB con cita"), **no** de ejecución. Ningún
hallazgo se apoya en una respuesta HTTP ni en un error de PostgreSQL observado.
Donde la diferencia entre "código dice" y "ejecución confirma" importa, se indica
en la columna de confianza.

Los hallazgos se evalúan sobre el **estado actual** de los archivos en alcance, no
sobre el delta. Esto importa para SEC-008, SEC-011 y SEC-013: son defectos reales
del archivo en alcance, pero **no puedo afirmar que este cambio los introdujera**.

---

## 1. Resumen ejecutivo

Las tres migraciones hacen lo que declaran a nivel de mecanismo: 0015 mueve la
condición de "lista de estados" a "tiene los tres recursos" y es atómica; 0016
bloquea la clase distinta de A5 en `INSERT` y en todo cambio de `chofer_id`; 0017
alinea el default del núcleo con el modelo. La cadena de triggers es segura por
atomicidad de sentencia: un trigger posterior que falle revierte también la
reserva insertada por `70_reservas`, así que no encontré estados inconsistentes
por orden de disparo.

Lo que no cierra es **el dinero de la comisión**: la base del período es la fecha
del viaje y no la de facturación, y una liquidación emitida no se recalcula, de modo
que un viaje facturado con retraso **no se paga nunca** (SEC-001). Además el PDF de
una liquidación emitida se **recalcula en vivo**, así que el documento cambia
después de emitirse y sus líneas dejan de sumar el total almacenado (SEC-002).
Ambos son silenciosos: no hay error, no hay alerta, no hay rastro.

En el plano de integridad, R-02 se puede esquivar degradando la clase del chofer
después de asignar (SEC-005, declarado por el autor pero igualmente incumple la
regla del dueño) y la validación documental de 0015 **no se cumple en `UPDATE`** para
estados distintos de `asignado`, en contradicción con su propia invariante
INV-DOC04 (SEC-006). Y `cutover_legacy.py` queda inoperante (SEC-009), declarado a
propósito pero sin corrección entregada.

Conteo: **2 altas, 8 medias, 3 bajas, 2 informativas**. No encontré inyección,
bypass de autenticación ni lectura cruzada entre empresas dentro de estos archivos.

---

## 2. Tabla de hallazgos

| ID | Severidad | Área | Evidencia | Escenario de abuso o fallo | Remediación propuesta |
|---|---|---|---|---|---|
| SEC-001 | **alta** | Dinero / comisión | `liquidaciones.py:49-56` + `liquidaciones.py:291-295` + `viajes.py:245-246` | Viaje finalizado 28-oct se factura 10-nov. Liquidación de octubre ya emitida → 409 al recalcular; noviembre no lo incluye (`fecha_fin` en octubre). Comisión perdida | Atribuir por fecha de emisión de factura, o bloquear `emitir` con viajes del mes sin facturar, o ajuste compensatorio (negocio-finanzas + backend) |
| SEC-002 | **alta** | Dinero / trazabilidad | `liquidaciones.py:467-500` y `403-411` y `431` | Emitida la liquidación, se agrega un bono o cambia `porcentaje_produccion`; el PDF muestra haberes nuevos y total viejo. El documento firmado no es reproducible | Snapshot inmutable al emitir (comisión, bonos, descuentos, detalle de viajes); el PDF lee solo la liquidación (backend/datos) |
| SEC-003 | media | Dinero / fuente de verdad | `nucleo/models.py:584` vs `models/__init__.py:103`; `liquidaciones.py:58` vs `servicio_gastos.py:460` | Se fija 12 % en maestros del núcleo: la nómina paga 10 % (legacy) y el costo usa 12 %. Nadie lo detecta | Declarar canónica una de las dos y sincronizar (trigger o migración del pago); ADR (arquitectura/datos) |
| SEC-004 | media | Dinero / default 10 % | `export.py:256,267` + `0001_esquema_base.sql:65` | Importar choferes por CSV sin la columna `porcentaje_produccion` → todos quedan en 0 % y devengan 0 de comisión | Fallback 0.10 en el importador y `set default 0.10` en `public.choferes` (backend/datos) |
| SEC-005 | media | Integridad R-02 | `0016:212-216`; gap declarado en `0016:56-62` | Chofer A5 asignado a viaje `confirmado`/`en_ruta`; se edita `choferes.licencia_clase='A3'`; el viaje sigue y todo `UPDATE` que no sea a `asignado` pasa sin validar | Trigger en `nucleo.choferes` que rechace degradar la clase con viajes vigentes, o validar clase en transiciones operativas (datos) |
| SEC-006 | media | Integridad documental | `0015:21-24` (INV-DOC04) vs `0015:270-277` (excepción) | Viaje `borrador` con 3 recursos y docs válidos; los docs vencen; `UPDATE estado='confirmado'` no revalida y el viaje ocupa 3 reservas con expediente inválido | Limitar la excepción a estados ya despachados (`en_carga`…`pod_pendiente`) o revalidar en toda transición desde `borrador`/`cotizado`/`confirmado` (datos) |
| SEC-007 | media | Dinero / idempotencia | `liquidaciones.py:82-108,142-168`; `0001:151-160` (sin `unique`) | Doble clic en `POST /anticipos` de 100.000 → dos filas → 200.000 descontados de la liquidación | `Idempotency-Key` o `unique (chofer_id, fecha, monto, mes_liquidacion)` + 409 (backend/datos) |
| SEC-008 | media | Autorización / PII | `liquidaciones.py:27` + `187-240` + `467-506`; `deps.py:9-28` | Cualquier usuario autenticado activo (rol `operacion`) lee sueldos, comisiones y RUT de todos los choferes vía `GET /liquidaciones/resumen` | `require_roles(admin, contabilidad)` también en lectura (backend) |
| SEC-009 | media | Regresión operativa | `0015:130-143`; `cutover_legacy.py:361-388` + `166-264` | `make cutover` inserta viajes `confirmado` con 3 recursos y documentos insuficientes → 23514 → rollback del cutover completo | Completar la carga documental del cutover o migrar sin recursos y asignar después (scripts/backend) |
| SEC-010 | media | Pruebas / entorno | `test_reglas_negocio.py:104-110` vs `conftest.py:63` y `Makefile:65` | Sin `DATABASE_URL` el módulo se salta en silencio; si apunta a staging/producción, los tests conectan a un entorno no local | Usar `NUCLEO_TEST_DATABASE_URL` con skip explícito; nunca `DATABASE_URL` (qa) |
| SEC-011 | baja | Pruebas E2E | `tei.spec.ts:48-54` y `96-100` | Sin enlace "Abrir", la prueba de expediente pasa solo con el heading; el estado de cutover acepta ambos valores | Exigir ≥1 enlace (el seed los garantiza) y aseverar el estado esperado del entorno (qa) |
| SEC-012 | baja | Migración 0015 | `0015:363-391` vs `0004:744-757` | Un viaje con 3 recursos que se solapa con una mantención/descanso hace abortar el backfill con 23P01 crudo, no con el mensaje operativo | Añadir a P1.2 la comparación contra reservas activas de cualquier `tipo_reserva` (datos) |
| SEC-013 | baja | Dinero / concurrencia | `liquidaciones.py:284-290` + `0001:185` (`unique (chofer_id, mes)`) | Dos `POST /liquidaciones/calcular` concurrentes → `IntegrityError` sin manejar → 500 en endpoint de dinero | Capturar 23505 → 409 o `upsert` (backend) |
| SEC-014 | informativa | Secretos | `Makefile:6,26,65-69`; `tei.spec.ts:3` | Credenciales de seed en el repo y en `make help` | Aceptable solo para local; nunca reutilizar en staging/producción |
| SEC-015 | informativa | Cobertura | `Makefile` sin target; `supabase/tests/*.sql` se corren a mano | Las garantías de 0015/0016 pueden romperse sin que `make test` lo detecte | Target `make sql-tests` o integrarlas en CI (qa/datos) |

---

## 3. Detalle de hallazgos

### SEC-001 [alta] La comisión se pierde cuando la facturación cae en un mes ya cerrado
- **Estado:** confirmado por lectura de código (no ejecutado) · **Confianza:** alta
- **Evidencia:** `backend/app/api/routes/liquidaciones.py:49-56` filtra
  `Viaje.estado == EstadoViaje.facturado` y el período por
  `coalesce(fecha_fin, fecha_inicio)`. `liquidaciones.py:291-295` rechaza recalcular
  una liquidación `emitida` con 409. `api/routes/viajes.py:245-246` fija
  `fecha_fin = date.today()` al pasar a `finalizado`; `api/routes/facturas.py:166`
  al facturar **solo** cambia `estado` a `facturado`.
- **Escenario:** viaje finalizado el 2026-10-28 (`fecha_fin = 2026-10-28`). La
  liquidación de octubre se emite el 2026-11-05 sin ese viaje (aún `finalizado`).
  El viaje se factura el 2026-11-10 → `estado='facturado'`, `fecha_fin` sigue en
  octubre. `POST /liquidaciones/calcular?mes=2026-10` → **409** ("ya fue emitida").
  `mes=2026-11` no lo incluye porque el filtro mira `fecha_fin`. **La comisión no
  se paga nunca y nadie recibe un error.**
- **Agravante:** `viajes.py:208` permite `PUT fecha_fin=null` en un viaje
  `facturado`; entonces el filtro cae a `fecha_inicio` y el viaje puede **cambiar
  de mes** después del cierre.
- **Impacto:** pérdida de dinero del trabajador, sistemática en todo cierre de mes
  con facturación tardía. Alcance: todos los choferes, todos los meses.
- **Capas que fallan:** servicio (atribución del período) + regla de negocio no
  definida (¿mes del viaje o mes de la factura?).
- **Remediación:** una de tres, decidida por `negocio-finanzas`:
  (a) atribuir por fecha de emisión de la factura (`facturas.fecha`/`created_at`);
  (b) bloquear `emitir_liquidacion` si existen viajes del mes en `finalizado`
  (cierre con pendientes explícito); (c) permitir un ajuste compensatorio en el mes
  siguiente con trazabilidad. Luego `backend` implementa.
- **Prueba de verificación:** test que finaliza un viaje en el mes M, emite la
  liquidación de M, factura el viaje en M+1 y verifica que la comisión aparece en
  alguna liquidación pagada (o que la emisión de M falla con un mensaje claro).
- **Esfuerzo:** M · **Depende de:** decisión de negocio (R-01 no define el período).

### SEC-002 [alta] El PDF de una liquidación emitida se recalcula en vivo y deja de cuadrar
- **Estado:** confirmado por lectura de código · **Confianza:** alta
- **Evidencia:** `liquidaciones.py:467-500` (`pdf_liquidacion`) vuelve a llamar
  `_comision_chofer` y a sumar `AjusteLiquidacion` **en el momento de generar el
  PDF**. `liquidaciones.py:403-411` usa esos valores vivos para "Comisión por
  producción" y "Bonos"/"Descuentos"; `liquidaciones.py:409` usa
  `liquidacion.total_anticipos` (almacenado) y `liquidaciones.py:431` imprime
  `liquidacion.total_liquido` (almacenado).
- **Escenario:** se emite la liquidación de octubre (total 580.000). Se agrega un
  bono de 50.000 (`POST /ajustes`) o se cambia `porcentaje_produccion` del chofer.
  Se descarga el PDF de la liquidación **emitida**: la línea "Comisión/Bonos"
  cambia pero el recuadro "TOTAL LÍQUIDO A PAGAR" sigue en 580.000. El documento
  impreso no cuadra consigo mismo y ya no es reproducible.
- **Impacto:** documento laboral emitido, mutable y sin rastro. Contradice
  `AGENTS.md` §16 ("un documento emitido no se edita") por analogía. Alcance: todos
  los choferes liquidados.
- **Capas que fallan:** servicio (no hay snapshot) + ausencia de inmutabilidad en
  `liquidaciones`.
- **Remediación:** al `emitir`, congelar `comision`, `total_ajustes`,
  `total_anticipos`, `total_liquido` **y** el detalle de viajes considerados
  (`liquidacion_viajes` o JSON); el PDF debe leer exclusivamente de la liquidación.
  Agente: `backend` (+`datos` si se requiere tabla de detalle).
- **Prueba de verificación:** emitir, agregar un bono, generar el PDF y comprobar
  que las líneas suman el total y que coincide con lo emitido.
- **Esfuerzo:** M · **Depende de:** SEC-001 (ambos definen qué se congela).

### SEC-003 [media] Dos fuentes de verdad para el porcentaje de comisión
- **Estado:** confirmado · **Confianza:** alta
- **Evidencia:** `backend/app/nucleo/models.py:584` (`porcentaje_comision`,
  default 0.10 desde 0017) se usa en
  `backend/app/nucleo/servicio_gastos.py:460` para costo/rentabilidad.
  `backend/app/models/__init__.py:103` (`porcentaje_produccion`, default 0.10) se
  usa en `liquidaciones.py:58` para **pagar**. No hay FK, trigger ni job que los
  sincronice (grep de ambas cadenas: solo esas apariciones).
- **Escenario:** el administrador fija 12 % en la pantalla de maestros del núcleo
  (campo `porcentaje_comision`). La nómina sigue pagando 10 %
  (`porcentaje_produccion` del legacy) mientras la rentabilidad costea 12 %.
- **Impacto:** discrepancia entre lo pagado y lo costeado, sin señal. Alcance: por
  chofer, acumulativo.
- **Remediación:** ADR que declare cuál es canónica; mientras convivan, sincronizar
  por trigger o unificar el cálculo. Agente: `arquitectura` → `datos`.
- **Prueba de verificación:** cambiar el porcentaje en un esquema y verificar que
  el pago y el costo usan el mismo valor (o que el sistema rechaza el cambio).
- **Esfuerzo:** L · **Depende de:** decisión de arquitectura.

### SEC-004 [media] El default de 10 % se elude en la importación CSV y en INSERT directo
- **Estado:** confirmado · **Confianza:** alta
- **Evidencia:** `backend/app/api/routes/export.py:256`
  (`f.get("porcentaje_produccion") or "0"`) y `:267` (lo pasa **explícito** al
  modelo, anulando el default 0.10). `0001_esquema_base.sql:65`
  (`porcentaje_produccion numeric(5,4) not null default 0`): la base del legacy
  sigue naciendo en 0. `0017` solo toca `nucleo.choferes`.
- **Escenario:** se importa la nómina de choferes por CSV sin la columna de
  porcentaje → todos quedan en 0 % y devengan 0 de comisión. Es exactamente el
  "error de dinero silencioso" que `0017:10-12` dice corregir.
- **Impacto:** subpago total de comisiones en altas masivas. Alcance: todos los
  choferes importados.
- **Remediación:** fallback `Decimal("0.10")` en el importador y
  `alter table public.choferes alter column porcentaje_produccion set default 0.10`
  (migración nueva, con la misma lógica de "no backfill" de 0017). Agente:
  `backend` + `datos`.
- **Prueba de verificación:** importar un CSV sin la columna y comprobar que el
  chofer creado tiene 0.10.
- **Esfuerzo:** S · **Depende de:** —

### SEC-005 [media] R-02 se esquiva degradando la clase del chofer después de asignar
- **Estado:** confirmado (gap declarado por el autor en `0016:56-62`) · **Confianza:** alta
- **Evidencia:** `0016:212-216`:
  `if new.estado <> 'asignado' and new.chofer_id = old.chofer_id then return new`.
  No existe trigger sobre `nucleo.choferes.licencia_clase`.
- **Escenario:** viaje en `confirmado` o `en_ruta` con chofer A5. Se edita el
  maestro `nucleo.choferes.licencia_clase = 'A3'` (pantalla de maestros). El viaje
  continúa; cualquier `UPDATE` posterior que no sea a `asignado` (cambiar
  observaciones, peso, origen, pasar a `en_carga`) no valida la clase.
- **Impacto:** un viaje vigente opera con un conductor que la regla del dueño
  prohíbe. Alcance: un viaje por evento; requiere acceso de escritura a maestros.
- **Capas que fallan:** DB (el trigger mira el viaje, no el maestro).
- **Remediación:** trigger `BEFORE UPDATE` en `nucleo.choferes` que rechace pasar
  de A5 a otra clase (o a NULL) cuando existan viajes vigentes con ese chofer, o
  revalidar la clase en la transición a estados operativos. Agente: `datos`.
- **Prueba de verificación:** asignar A5, degradar a A3, intentar mover el viaje a
  `en_carga` → debe fallar con 23514.
- **Esfuerzo:** S · **Depende de:** —

### SEC-006 [media] INV-DOC04 no se cumple en UPDATE: la validación documental se salta fuera de `asignado`
- **Estado:** confirmado · **Confianza:** alta
- **Evidencia:** `0015:21-24` declara la invariante "documentos vigentes … **sin
  importar el estado del viaje**". `0015:270-277` la exceptúa: si es `UPDATE`, el
  estado no es `asignado` y los recursos no cambian, `return new` sin validar.
- **Escenario:** viaje `borrador` con tracto+rampla+chofer y documentos válidos
  (el `INSERT` sí validó). Luego la licencia del chofer vence (o se desactiva el
  documento). `UPDATE nucleo.viajes SET estado='confirmado'` → no valida
  (`05_documentos` se salta por la excepción y `10_validar` retorna para
  `confirmado`, `0004:1124-1126`). El viaje queda `confirmado`, **ocupa las 3
  reservas** y bloquea el tracto con expediente inválido.
- **Impacto:** recursos comprometidos por un viaje no despachable; contradice la
  invariante que la propia migración declara. Alcance: un viaje; se detecta recién
  al pasar a `asignado`.
- **Remediación:** acotar la excepción a estados ya despachados
  (`en_carga`…`pod_pendiente`) o revalidar en toda transición **desde**
  `borrador`/`cotizado`/`confirmado`. Agente: `datos`.
- **Prueba de verificación:** insertar borrador con 3 recursos y docs válidos,
  vencer la licencia, `UPDATE estado='confirmado'` → debe fallar con 23514.
- **Esfuerzo:** S · **Depende de:** —

### SEC-007 [media] Anticipos y ajustes sin idempotencia: el doble clic descuenta dos veces
- **Estado:** confirmado · **Confianza:** alta
- **Evidencia:** `liquidaciones.py:82-108` (`POST /anticipos`) y `142-168`
  (`POST /ajustes`) no reciben clave de idempotencia ni consultan duplicados;
  `0001_esquema_base.sql:151-160` define `anticipos_chofer` sin `unique` (solo el
  índice `idx_anticipos_chofer_mes`, línea 228).
- **Escenario:** doble clic (o reintento de red) en un anticipo de 100.000 → dos
  filas → `resumen_liquidaciones` (`liquidaciones.py:198-203`) suma 200.000 y los
  descuenta del líquido a pagar.
- **Impacto:** descuento indebido al trabajador; se corrige solo borrando una fila
  a mano (`DELETE`, sin auditoría). Alcance: por operación.
- **Remediación:** `Idempotency-Key` en el endpoint, o
  `unique (chofer_id, mes_liquidacion, fecha, monto)` con 409. Agente: `backend`
  (+`datos`).
- **Prueba de verificación:** dos `POST` idénticos → uno crea, el otro responde 409
  y la suma no cambia.
- **Esfuerzo:** S · **Depende de:** —

### SEC-008 [media] Remuneraciones y RUT expuestos a cualquier usuario autenticado
- **Estado:** confirmado · **Confianza:** alta
- **Evidencia:** `liquidaciones.py:27` `lectura = Depends(get_current_user)` (sin
  rol); `liquidaciones.py:187-240` devuelve `sueldo_base`, `comision`,
  `anticipos`, `bonos`, `descuentos`, `total` y `rut` de **todos** los choferes
  activos; `liquidaciones.py:467-506` entrega el PDF con RUT.
  `deps.py:9-28` solo exige usuario existente y `activo`.
- **Escenario:** una cuenta con rol `operacion` (o cualquier cuenta activa) llama
  `GET /api/v1/liquidaciones/resumen?mes=2026-10` y obtiene la nómina completa de
  la empresa.
- **Impacto:** divulgación de datos personales y salariales. Alcance: toda la
  empresa.
- **Nota de honestidad:** no puedo afirmar que este cambio lo introdujera; el
  archivo está en alcance y el control es real y verificable.
- **Remediación:** `escritura`-equivalente en lectura:
  `Depends(require_roles(admin, contabilidad))` en los endpoints de liquidaciones y
  anticipos. Agente: `backend`.
- **Prueba de verificación:** request con rol `operacion` → 403.
- **Esfuerzo:** S · **Depende de:** —

### SEC-009 [media] `cutover_legacy.py` deja de funcionar (regresión declarada, sin corrección)
- **Estado:** confirmado por lectura de código (no ejecutado) · **Confianza:** alta
- **Evidencia:** `0015:130-143` declara el script INCOMPATIBLE.
  `scripts/cutover_legacy.py:361-388` inserta viajes en `'confirmado'` con tracto,
  rampla y chofer. El script carga documentos **parciales**:
  `licencia_conducir` (`:166`), `revision_tecnica`+`seguro_obligatorio` de tracto
  (`:206-219`), `revision_tecnica` de rampla (`:255-264`). `nucleo.validar_documentos_recurso`
  (`0004:1041-1074`) exige además `examen_medico` (chofer), `permiso_circulacion`
  (tracto y rampla), y `soap`/`seguro_carga` cuando `exigir_soap`/
  `exigir_seguro_carga` están en true (default, `0004:223-225`).
- **Escenario:** `make cutover` → el primer viaje migrado con 3 recursos dispara
  `trg_viajes_05_documentos` → 23514 → rollback de toda la transacción del cutover.
- **Inexactitud documental:** el encabezado de 0015 (`:131-133`) afirma que el
  script "NO crea documentos en `nucleo.documentos`"; el script **sí** crea algunos
  (insuficientes). Quien siga el handoff `(a) cargar primero nucleo.documentos`
  puede creer que no hay ninguno.
- **Impacto:** procedimiento de cutover inoperante hasta corregir el script. Falla
  cerrado y ruidoso (no corrompe datos). Alcance: operación de cutover.
- **Remediación:** completar la carga documental del cutover con los tipos exigidos
  o migrar viajes sin recursos (`borrador`) y asignarlos después; corregir la
  afirmación del encabezado. Agente: `backend`/`scripts` (handoff ya declarado).
- **Prueba de verificación:** `make cutover-dry` seguido de un `cutover` en base
  desechable → sin 23514.
- **Esfuerzo:** M · **Depende de:** —

### SEC-010 [media] Los tests de R-01/R-02 usan la URL de la aplicación, no la de test
- **Estado:** confirmado · **Confianza:** alta
- **Evidencia:** `backend/tests/test_reglas_negocio.py:104-110` lee
  `settings.DATABASE_URL`. Los otros 12 módulos de integración leen
  `os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL`
  (p. ej. `test_nucleo_bloqueos.py:38`, `test_nucleo_gastos.py:44`).
  `Makefile:65` exporta **solo** `NUCLEO_TEST_DATABASE_URL`.
- **Escenario A (cobertura falsa):** si `.env` no define `DATABASE_URL`, el módulo
  completo hace `pytest.skip` y `make test` lo reporta como omitido, no como fallo,
  mientras el docstring (`test_reglas_negocio.py:4-5,17`) afirma "11 passed".
- **Escenario B (entorno indebido):** si `DATABASE_URL` apunta a staging o
  producción, las pruebas **conectan** a ese entorno. La transacción externa se
  revierte (`join_transaction_mode="create_savepoint"`), pero se viola
  `AGENTS.md` §3 ("solo local/staging con datos del seed") y la convención del repo.
- **Remediación:** usar `NUCLEO_TEST_DATABASE_URL` con `skip` explícito; rechazar
  `DATABASE_URL`. Agente: `qa`.
- **Prueba de verificación:** ejecutar con solo `NUCLEO_TEST_DATABASE_URL` definida
  y comprobar que los 11 tests corren (no se saltan).
- **Esfuerzo:** S · **Depende de:** —

### SEC-011 [baja] E2E con aserciones incapaces de fallar
- **Estado:** confirmado · **Confianza:** alta
- **Evidencia:** `frontend/e2e/tei.spec.ts:48-54`: `if (await abrir.count()) { … }`
  — si no hay enlace "Abrir", se omiten la URL del detalle, "Resumen" y el QR.
  `tei.spec.ts:96-100`: `getByText(/^(Congelada|Abierta)$/)` acepta ambos estados.
- **Escenario:** una regresión que deje la lista de expedientes vacía (o que rompa
  el QR) no hace fallar la suite; el test pasa solo con el heading.
- **Impacto:** regresión no detectada. No es vulnerabilidad.
- **Remediación:** el seed garantiza viajes (`seed_local.py:605-635`), así que
  `expect(await abrir.count()).toBeGreaterThan(0)` es seguro; para cutover,
  aseverar el estado esperado del entorno de prueba. Agente: `qa`.
- **Esfuerzo:** S · **Depende de:** —

### SEC-012 [baja] El backfill de 0015 puede abortar con 23P01 crudo frente a mantención/descanso
- **Estado:** potencial (deducido del DDL, no reproducido) · **Confianza:** media
- **Evidencia:** la detección previa `0015:363-391` solo compara pares **viaje ×
  viaje**. El `INSERT` de `0015:394-443` sí queda sujeto a
  `ex_reserva_tracto`/`ex_reserva_rampla`/`ex_reserva_chofer`
  (`0004:744-757`), que excluyen contra **cualquier** reserva activa, incluida
  `mantenimiento`/`descanso` (el propio seed crea ambas, `seed_local.py:563-598`).
- **Escenario:** un viaje con 3 recursos cuya ventana se solapa con una mantención
  programada del mismo tracto (estado legal antes de 0015, porque `confirmado` no
  ocupaba) → el backfill lanza 23P01 sin el mensaje operativo de P1.2.
- **Impacto:** la migración falla sin guía; no pierde datos. Falta confirmar con
  una ejecución real (no disponible, §0.2).
- **Remediación:** ampliar P1.2 a reservas activas de cualquier `tipo_reserva`.
  Agente: `datos`.
- **Esfuerzo:** S · **Depende de:** —

### SEC-013 [baja] Carrera en `calcular_liquidacion` devuelve 500 en vez de 409
- **Estado:** confirmado · **Confianza:** alta
- **Evidencia:** `liquidaciones.py:284-290` hace `SELECT` y luego `INSERT`;
  `0001_esquema_base.sql:185` define `unique (chofer_id, mes)`. No hay manejo de
  `IntegrityError`.
- **Escenario:** dos `POST /liquidaciones/calcular` simultáneos → uno inserta, el
  otro viola la única → 500. No duplica dinero (la única lo impide), pero rompe
  `AGENTS.md` §8 (`23505` → 409).
- **Remediación:** capturar 23505 → 409, o `INSERT … ON CONFLICT (chofer_id, mes)
  DO UPDATE`. Agente: `backend`.
- **Esfuerzo:** S · **Depende de:** —

### SEC-014 [informativa] Credenciales de seed en el repositorio
- **Evidencia:** `Makefile:6` (URL local con credenciales por defecto de Supabase),
  `Makefile:26` (login de seed impreso en `make help`), `Makefile:65-69`
  (credenciales de test exportadas), `frontend/e2e/tei.spec.ts:3`.
- **Evaluación:** aceptable para un entorno local documentado; el `Makefile`
  incluso **mejora** la situación previa al redirigir la salida de `supabase start`
  a un log (`Makefile:32-36`) en lugar de filtrar claves en stdout. Riesgo real solo
  si estas credenciales se reutilizan fuera de local. No se reproduce el valor aquí.

### SEC-015 [informativa] Las pruebas SQL de 0015/0016 no están automatizadas
- **Evidencia:** el `Makefile` no tiene target que ejecute `supabase/tests/*.sql`;
  `0016_01…sql:17-18` documenta ejecución manual con `psql -f`.
- **Impacto:** las garantías de base de 0015/0016 pueden romperse sin que
  `make test` lo note. Los scripts existen y son de buena calidad (ver §4).

---

## 4. Lo que probé y **no** rompí

Cada punto indica el ataque intentado y por qué el control lo cubre.

### 4.1 Licencia A5 (0016)
| Ataque intentado | Resultado | Evidencia |
|---|---|---|
| `INSERT` con `estado='borrador'` + chofer A3 | **bloqueado**: `tg_op='INSERT'` no tiene excepción | `0016:212` (la excepción exige `tg_op='UPDATE'`) |
| `INSERT` con `estado='confirmado'` + chofer A3 | **bloqueado** (mismo motivo) | `0016:200-216` |
| `INSERT` con `chofer_id=NULL`, luego `UPDATE chofer_id=A3` | **bloqueado**: cambia `chofer_id`, la excepción no aplica | `0016:213` |
| `UPDATE` de `chofer_id` en un `borrador` | **bloqueado** (verificado además por `0016_01` caso C) | `supabase/tests/0016_01…sql:115-124` |
| `ON CONFLICT DO UPDATE` para "colar" un chofer A3 | **bloqueado en el camino de inserción**; en el camino `DO UPDATE` hereda el mismo gap de SEC-005, no uno nuevo | `0016:212-216` |
| `COPY FROM` con chofer A3 | **bloqueado**: `COPY` dispara triggers `BEFORE INSERT` | comportamiento documentado de PostgreSQL |
| Anular y recrear el viaje | **bloqueado**: recrear es `INSERT` | `0016:200-216` |
| Clase `'a5'`/`' A5 '` (minúsculas/espacios) | **aceptado a propósito**: normaliza con `upper(btrim(...))` | `0016:218`, coherente con `politicas.py:300` |
| Chofer de otra empresa | **no explotable**: el `SELECT` filtra `empresa_id` y la FK compuesta lo impide | `0016:225-226`, `0004:656-657` |
| Viaje `anulado` con chofer no-A5 | **permitido a propósito** (terminal, libera recursos) | `0016:205-207` |

No encontré un bypass **trivial** de la clase A5 en el camino de asignación. El
único hueco es SEC-005 (degradar el maestro), que requiere escritura en
`nucleo.choferes`.

### 4.2 Orden de triggers y consistencia
- Orden real en `nucleo.viajes` (nombre ASCII, PostgreSQL dispara `BEFORE` en ese
  orden): `00_ventana` → `03_licencia_a5` → `05_documentos` → `10_validar` →
  `15_facturacion` → `20_proteccion` → `30_transicion` → `40_touch` → `50_version`;
  `AFTER`: `60_audit` → `70_reservas` → `75_expediente` → `80_oc`.
  Verificado por los `create trigger` de `0004:1832-1850`, `0008:42`,
  `0015:313`, `0016:255`.
- **Un trigger posterior que falla no deja inconsistencia**: `70_reservas` inserta
  en `reservas_recurso`, y si `75_expediente` u `80_oc` (que puede lanzar 23514 en
  `fn_oc_recalcular`, `0004:1580-1584`) fallan, la **sentencia completa** se
  revierte, incluida la reserva. No hay ventana de estado inconsistente.
- **Si `05_documentos` falla después de que `03_licencia_a5` pasó**, la sentencia se
  revierte: no queda viaje escrito. Correcto.
- El mensaje de error es el correcto por el orden elegido (clase antes que fecha),
  como declara `0016:250-253`. 🟢 (inferido del orden de nombres; no ejecutado).

### 4.3 Ocupación (0015)
| Ataque / borde | Resultado | Evidencia |
|---|---|---|
| `borrador` con los 3 recursos ocupa el libro | **sí, por diseño** (regla del dueño) | `0015:194-197` |
| `borrador`/`cotizado` con recursos **parciales** ocupa de más | **no**: `v_ocupa` exige los 3 no nulos | `0015:194-197` |
| Reasignar tracto/rampla/chofer deja reservas huérfanas activas | **no**: desactiva y reinserta en la misma transacción | `0015:219-233` |
| Cambiar la ventana deja reservas con ventana vieja | **no**: la comparación incluye `r.ventana = new.ventana` | `0015:207` |
| Duplicar reservas activas del mismo tipo | **no**: `uq_reserva_viaje_recurso_activa` | `0004:759-761` |
| `anulado` sigue ocupando | **no**: libera y permite desactivar (`fn_reserva_no_borrar` solo prohíbe `DELETE`) | `0015:194,219-221`, `0004:1692-1700` |
| `fin_planificado`/`buffer_minutos` nulos → validación documental en `NULL` → fail-open | **no**: ambos son `not null` | `0004:554-560` |
| Backfill crea duplicados al re-ejecutar | **no**: `NOT EXISTS` por (viaje, `recurso_tipo`) + índice único parcial | `0015:405-407,422-424,439-441`, `0004:759` |
| Backfill adopta viajes `anulado` | **no**: excluye `estado <> 'anulado'` | `0015:402` |
| Backfill deja el libro incompleto en silencio | **no**: autochequeo con `raise exception` 23514 | `0015:450-470` |
| Solapamiento viaje×viaje pasa desapercibido | **no**: aborta con mensaje operativo | `0015:365-391` |
| Solapamiento viaje×mantención | **falla con 23P01** (SEC-012) | `0004:744-757` |

### 4.4 Dinero
| Caso | Resultado | Evidencia |
|---|---|---|
| Viaje `finalizado` (no facturado) devenga comisión | **no** | `liquidaciones.py:52` |
| Viaje facturado de otro mes entra al mes corriente | **no** (el filtro de rango funciona) | `liquidaciones.py:53-54` |
| Factura anulada sigue generando comisión | **no** en el camino normal: `facturas.py:218-228` revierte el viaje a `finalizado` y borra `FacturaViaje` | `api/routes/facturas.py:218-228` |
| Mes sin viajes | **no falla**: `sum(..., Decimal("0"))` y `Decimal(coalesce(...,0))` | `liquidaciones.py:59,199-217,257-282` |
| Redondeo inestable | **no**: `quantize(Decimal("0.01"))` es determinista (HALF_EVEN) sobre `Decimal` | `liquidaciones.py:60` |
| `float` en dinero | **no** en estos archivos: todo es `Decimal`/`numeric` | `liquidaciones.py:6,45-61` |
| Recalcular una liquidación emitida | **bloqueado** con 409 | `liquidaciones.py:291-295` |
| Doble emisión | **inocuo**: solo reescribe `estado` | `liquidaciones.py:319` |
| Monto negativo en ajuste | **rechazado** con 400 | `liquidaciones.py:156-157` |
| Anticipo ≤ 0 | **rechazado** con 400 | `liquidaciones.py:95-96` |
| `fecha_fin` nula en `_comision_chofer` y en el PDF | **no revienta**: `fecha_inicio` es `not null` en el legacy | `0001:99`, `liquidaciones.py:53,445` |

Los defectos de dinero que **sí** quedan son SEC-001 (pérdida por período),
SEC-002 (documento mutable), SEC-003 (doble fuente), SEC-004 (default eludible),
SEC-007 (sin idempotencia) y SEC-013 (500 en carrera). **No encontré doble conteo
de comisión**: la base se recalcula desde cero y la única `(chofer_id, mes)` impide
duplicar la liquidación.

### 4.5 Regresión y entorno
| Comprobación | Resultado | Evidencia |
|---|---|---|
| Los triggers de 0015/0016 afectan al legacy `public.viajes` | **no**: ambos son `on nucleo.viajes` | `0015:313-315`, `0016:255-257` |
| El seed sigue siendo re-ejecutable | **sí**: `on conflict` en todas las inserciones relevantes | `seed_local.py:168,181,191,327,341,468,571,589,620,646` |
| El seed sobrevive a R-02 (choferes A5) | **sí**: los 3 choferes son `A5` | `seed_local.py:314-318` |
| El seed sobrevive a 0015 (viajes `cerrado` con 3 recursos y documentos válidos a +365 d) | **sí, en el papel**: `vence = hoy + 365` cubre el fin del viaje | `seed_local.py:119,632-633` |
| El seed alinea `dias_alerta_documentos` con 0016 | **sí**: inserta 14 explícito | `seed_local.py:167` |
| El seed alinea la comisión con 0017 | **sí**: `public.choferes` con 0.10 explícito y `nucleo.choferes` sin el campo (usa el default de base) | `seed_local.py:340` |
| `Makefile` expone más credenciales que antes | **no**: redirige `supabase start` a un log en lugar de stdout | `Makefile:32-36` |
| `make unit` cubre lo nuevo | **parcial**: no incluye `test_reglas_negocio.py` (es `integracion`), lo cual es correcto | `Makefile:54-60` |

### 4.6 Pruebas existentes
- `test_nucleo_politicas.py`: **no encontré aserciones debilitadas**. Las de
  licencia son ahora más estrictas (`bloqueante is True`, `test:163,174`), la de
  capacidad sigue exigiendo `== []` (`test:124`), y la nueva
  `test_licencia_a5_es_valida_aunque_el_tracto_configure_otra_clase` (`test:136-152`)
  no relaja nada: solo afirma que el array deprecado no genera hallazgos de licencia.
- `test_reglas_negocio.py`: las aserciones son exactas y numéricas
  (`180000`, `580000`, `100000`, `90000`), con mensajes de fallo útiles. La
  parametrización `["A3", None]` cubre ambos casos de R-02a. El aislamiento por
  savepoint revertido es correcto. **El defecto es la URL (SEC-010), no las
  aserciones.**
- `supabase/tests/0016_01…sql`: los tres casos (A3, NULL, `UPDATE`) verifican
  `sqlstate` **y** el texto del mensaje; no hay `EXCEPTION WHEN OTHERS` que pueda
  enmascarar un fallo distinto.

---

## 5. No verificado 🔴

| Qué | Por qué | Qué lo confirmaría |
|---|---|---|
| `git diff` de los 13 archivos | `shell` denegado en esta sesión | `git diff -- <archivo>` en una sesión con permiso |
| Ejecución real de `pytest` / `make test` | idem | salida real de los 11 tests de `test_reglas_negocio.py` |
| Aplicación real de 0015/0016/0017 y sus precondiciones P1.1–P1.4, P2.1–P2.4, P17.1 | idem | `psql` con las consultas del encabezado |
| SEC-012 (23P01 del backfill) | requiere datos y ejecución | `BEGIN; <backfill>; ROLLBACK` sobre un viaje que se solape con una mantención |
| Concurrencia real de SEC-007/SEC-013 | requiere dos conexiones | dos `psql` simultáneos |
| `make seed` end-to-end tras 0015/0016 | requiere base y escritura | `make db-reset && make seed` en base desechable |
| `make cutover-dry` / `cutover` (SEC-009) | requiere base y autorización | ejecución en base local desechable |
| E2E (SEC-011) | requiere frontend y base arriba | `make e2e` |
| Rol efectivo de `DATABASE_URL` frente a RLS (RA-03) | fuera de alcance de este cambio | `select current_user` con la cadena de la app |
| Que los tests SQL de 0015/0016 pasen hoy | requieren `psql` | `psql -f supabase/tests/00*.sql` |

**Ningún hallazgo de este informe fue reproducido en ejecución.** Los de severidad
alta (SEC-001, SEC-002) son deducciones directas de tres líneas de código cada una
y se pueden confirmar leyendo `liquidaciones.py` sin base de datos.

---

## 6. Observaciones (decisiones de negocio discutibles, **no** vulnerabilidades)

1. **Recursos parciales no ocupan** (`0015:30-35`). Es una decisión explícita: dos
   borradores pueden "reservar" el mismo tracto en el papel. No lo reporto como
   defecto porque el autor lo declara y el dueño habló de "todo viaje **con**
   tracto, rampla y chofer". Consecuencia real: el libro no es la verdad para
   asignaciones a medio armar.
2. **La ventana de aviso de 14 días no se aplica a las empresas existentes**
   (`0016:135-155`): solo cambia el `DEFAULT`. Las empresas con 30 siguen en 30
   hasta un `UPDATE` autorizado. Es correcto según `AGENTS.md` §8, pero el efecto
   observable es que "R-02 pide 14" no es cierto para los datos actuales.
3. **`tractos.licencias_permitidas` queda deprecado pero visible y editable**
   (`0016:39-49`). La UI sigue ofreciendo un campo que ya no autoriza nada. Es
   deuda de frontend, no un fallo de seguridad.
4. **`legacy` no tiene noción de clase de licencia** (`0001:60-70`). R-02 y 0015
   solo gobiernan `nucleo`; un viaje creado en `public.viajes` no pasa por A5 ni
   por el libro de ocupación. Es el `RA-02` conocido, no un defecto nuevo.
5. **`emitir_liquidacion` no exige que la liquidación haya sido calculada**
   (`liquidaciones.py:310-323`): si existiera una fila en cero, se emitiría en
   cero. Hoy no hay camino para crear esa fila, así que es potencial, no
   confirmado.
6. **`DELETE` físico de anticipos y ajustes** (`liquidaciones.py:111-121,171-181`)
   sin auditoría ni verificación de que la liquidación esté emitida. El legacy no
   tiene tabla de auditoría; queda como deuda (RA-07).

---

## 7. Prioridad recomendada

**Quick wins (S, severidad alta/media) — hacer primero:**
1. **SEC-008** (403 en lectura de liquidaciones) — una línea por endpoint, cierra
   exposición de sueldos y RUT. Agente: `backend`.
2. **SEC-007** (idempotencia de anticipos/ajustes) — `Idempotency-Key` + 409.
   Agente: `backend`.
3. **SEC-004** (fallback 0.10 en el importador) — una línea. Agente: `backend`.
4. **SEC-010** (URL de test) — dos líneas. Agente: `qa`.
5. **SEC-013** (23505 → 409). Agente: `backend`.

**Requieren decisión antes de tocar código:**
6. **SEC-001** — `negocio-finanzas` debe definir el período de la comisión (mes del
   viaje vs. mes de la factura). Sin esa decisión, cualquier arreglo es una
   invención de regla (`AGENTS.md` §15).
7. **SEC-003** — `arquitectura` debe declarar canónica una de las dos columnas.

**Después de 6 y 7:**
8. **SEC-002** — snapshot de la liquidación al emitir (depende de qué se congela,
   que depende de SEC-001).
9. **SEC-005** y **SEC-006** — endurecer triggers en `nucleo.choferes` y en la
   excepción de `05_documentos`. Agente: `datos`.
10. **SEC-009** — corregir `cutover_legacy.py` antes de cualquier ventana de
    cutover. Agente: `backend`/`scripts`.

**Higiene:**
11. SEC-011, SEC-012, SEC-015 (bajas/informativas).

**Dependencias:** SEC-002 → SEC-001 → decisión de negocio. SEC-005/SEC-006 no
dependen de nada y pueden ir en paralelo con `datos`.

---

## 8. Autoverificación

1. ¿Cada hallazgo confirmado tiene evidencia reproducible? — Sí: cita
   `archivo:línea`; ninguno depende de una ejecución que no pude hacer.
2. ¿Distinguí confirmado de potencial? — Sí: SEC-012 es `potencial` (deducido del
   DDL); el resto es `confirmado` por lectura.
3. ¿Describí el control real en lugar de "no hay control"? — Sí: §4 documenta qué
   protege cada trigger, incluidos los casos que **sí** funcionan.
4. ¿Probé variantes (verbo, rol, endpoint legacy vs núcleo)? — Sí: §4.1 (INSERT,
   UPDATE, ON CONFLICT, COPY, anular/recrear), §4.5 (legacy vs núcleo).
5. ¿Excluí secretos? — Sí: referencio `Makefile:6,26,65-69` y
   `tei.spec.ts:3` sin valores.
6. ¿Evité presentar una buena práctica ausente como vulnerabilidad? — Sí: §6
   separa las decisiones discutibles; SEC-011/014/015 son baja/informativa.
7. ¿Listé lo que no pude verificar? — Sí: §5, incluida la limitación de método en
   §0.2.
8. ¿Cada remediación tiene prueba de verificación y agente? — Sí, en el detalle de
   cada hallazgo.

**Limitación que condiciona todo el informe:** sin `git diff` no puedo atribuir
SEC-008, SEC-011 y SEC-013 a este cambio. Son defectos verificables del estado
actual de archivos en alcance, y deben evaluarse como tales.
