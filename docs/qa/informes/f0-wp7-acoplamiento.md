# F0 WP-7 — Acoplamiento y modularidad (¿soporta conectores y un escritor por tabla?)

> Depositado por el orquestador (2026-10-29): el agente `arquitectura` no tiene permiso de escritura en `docs/qa/informes/`; el contenido es íntegro de su respuesta. F0 es solo lectura.

- Fecha: 2026-10-29 · Rol: arquitectura · Misión solo lectura (read/grep/glob; sin shell)
- Base de evidencia: WP-1 (inventario) y WP-2 (F-01…F-10) de la sesión anterior; niveles 🟢/🟡/🔴 obligatorios.

## 1. Matriz de escritores por tabla

Metodología: grep de `session.add/update/execute/insert` por módulo + lectura de los puntos de escritura. Los "escritores" incluyen: servicios (app), rutas legacy (app), scripts operativos (`scripts/`), triggers/funciones de BD y seed.

### 1.1 `public` (legacy, 16 tablas)

| Tabla | Escritores (archivo:línea) | N.º | Cumple 1-escritor |
|---|---|---|---|
| `public.clientes` | `api/routes/catalogos.py:45-87` (POST/PUT/DELETE) · `api/routes/export.py:217-227` (import CSV) · `scripts/seed_local.py:235` | 3 | ❌ (2 rutas legacy escriben el mismo recurso) |
| `public.choferes` | `catalogos.py:111-153` · `export.py` (import choferes, 231-271) · `seed_local.py:322` | 3 | ❌ |
| `public.tractos` | `catalogos.py:177-224` · `seed_local.py:270` | 2 | ✅ (seed es dato inicial) |
| `public.ramplas` | `catalogos.py:246-288` · `seed_local.py:305` | 2 | ✅ |
| `public.viajes` | `api/routes/viajes.py:152-268` (único escritor en app) | 1 | ✅ |
| `public.gastos_viaje` | `api/routes/gastos.py:55-102` | 1 | ✅ |
| `public.facturas` | `api/routes/facturas.py:101-263` | 1 | ✅ |
| `public.factura_viaje` | `facturas.py` (creación asocia viajes, 101-169) | 1 | ✅ |
| `public.anticipos_chofer` | `liquidaciones.py:117-156` | 1 | ✅ |
| `public.ajustes_liquidacion` | `liquidaciones.py:177-216` | 1 | ✅ |
| `public.liquidaciones` | `liquidaciones.py:278-356` | 1 | ✅ |
| `public.pautas_mantenimiento` | `mantenimiento.py:40-87` | 1 | ✅ |
| `public.mantenimientos` | `mantenimiento.py:105-152` | 1 | ✅ |
| `public.configuracion` | `configuracion.py:23-39` | 1 | ✅ |
| `public.kpis` | `kpis.py:141-204` | 1 | ✅ |
| `public.usuarios` | trigger `public.handle_new_user` (`supabase/migrations/0001_esquema_base.sql:248-262`) · `seed_local.py:198` | 2 | ✅ (trigger = mecanismo único de app) |

### 1.2 `nucleo` (30 tablas)

| Tabla | Escritores (archivo:línea) | N.º | Nota |
|---|---|---|---|
| `empresas` | `seed_local.py:159` (sin endpoints de administración) | 1 | — |
| `usuarios_empresa` | `seed_local.py:179,189` | 1 | permiso `usuarios:administrar` existe (`permisos.py`) sin router visto 🟡 |
| `clientes` | `servicio_maestros.py:199` · `scripts/cutover_legacy.py:124` · `seed_local.py:222` | 3 | ❌ |
| `choferes` | `servicio_maestros.py:333` · `cutover_legacy.py:158` · `seed_local.py:322` | 3 | ❌ |
| `tractos` | `servicio_maestros.py:243` · `cutover_legacy.py:200` · `seed_local.py:253` | 3 | ❌ |
| `ramplas` | `servicio_maestros.py:285` · `cutover_legacy.py:259` · `seed_local.py:291` | 3 | ❌ |
| `documentos` | `servicio_maestros.py:463` · `cutover_legacy.py:176,223,268` | 2 | cutover fabrica documentos desde vencimientos legacy |
| `tarifas` | `servicio_comercial.py:447` (+updates) · `cutover_legacy.py:324` (tarifas sintéticas `MIG-*`) | 2 | ❌ |
| `centros_costo` | `servicio_comercial.py:232` | 1 | ✅ |
| `ordenes_compra` | `servicio_comercial.py:795,889,929,1095,1129,1160` · `cutover_legacy.py:361` | 2 | ❌ (OC sintéticas de cutover) |
| `ordenes_compra_lineas` | `servicio_comercial.py:799,976` | 1 | ✅ |
| **`viajes`** | **`servicio_disponibilidad.py:972` (INSERT), `:1487` (UPDATE)** · **`servicio_conductor.py:210`** · **`servicio_expediente.py:1262`** · **`servicio_facturacion.py:587`** · **`servicio_rentabilidad.py:401`** · `cutover_legacy.py:378` · `seed_local.py:461,611,699` | **7** | ❌❌ punto de mayor acoplamiento (ver §1.3) |
| `viaje_paradas` | `servicio_expediente.py:826,921` (+delete) | 1 | ✅ |
| `viaje_checklist` | `servicio_expediente.py:1002` | 1 | ✅ |
| **`viaje_eventos`** | `servicio_conductor.py:222-239` · `servicio_expediente.py:351` · `servicio_facturacion.py:599-608` · `servicio_pod.py:367-372` | 4 | ❌ 4 servicios escriben el log de eventos |
| `viaje_incidentes` | `servicio_expediente.py:1129` (+add) | 1 | ✅ |
| `viaje_documentos` | `servicio_expediente` (POST `api_expediente.py:240`) 🟡 (add exacto no localizado en grep) | 1 | ✅ |
| `pod` | `servicio_pod.py:254` (add), `:356` (update con version) | 1 | ✅ |
| `precios_diesel` | `servicio_gastos.py:210` | 1 | ✅ |
| `viaje_gastos` | `servicio_gastos.py:294,337,357,401` · `seed_local.py:653` | 2 | ✅ (seed) |
| `configuracion_costos` | `servicio_rentabilidad.py:137` · `seed_local.py:516` | 2 | ✅ (seed) |
| `facturas_nucleo` | `servicio_facturacion.py:570` · `seed_local.py:671` | 2 | ✅ (seed) |
| `factura_viajes` (nucleo) | `servicio_facturacion.py:578` · `seed_local.py:690` | 2 | ✅ (seed) |
| `pagos_nucleo` | `servicio_facturacion.py:643` | 1 | ✅ |
| `notas_credito_nucleo` | `servicio_facturacion.py:683` | 1 | ✅ |
| `promesas_pago_nucleo` | `servicio_facturacion.py:708` | 1 | ✅ |
| `reservas_recurso` | `servicio_bloqueos.py:244-252` (INSERT raw) y `:373-385` (UPDATE) · **trigger** `nucleo.fn_viaje_reservas` (`0015_viaje_con_recursos_ocupa_y_valida.sql:183-240`) | 2 | Libro de ocupación compartido por diseño: servicio (bloqueos) + trigger (viajes). Ningún otro servicio lo escribe directamente 🟢 |
| `folio_contador` | función DB `nucleo.siguiente_folio()` llamada por `servicio_facturacion.py:548-556` | 1 | ✅ |
| `auditoria` | trigger `nucleo.fn_auditoria` (`0007_expediente.sql:58,97,134,176,211`) | 1 | ✅ append-only por trigger |
| `cutover_control` | `servicio_cutover.py:105-138` · `cutover_legacy.py:410` (+insert inicial en 0014) | 2 | ✅ (mismo propósito) |
| `transiciones_viaje` | catálogo estático seed `0004_nucleo_operacional.sql:779` | — | No transaccional |

### 1.3 Violaciones del principio "un escritor por tabla"

1. **`nucleo.viajes` (7 escritores)** — 5 servicios de app + 2 scripts. Los 5 servicios usan optimistic lock `version` + `rowcount==1` (`servicio_disponibilidad.py:1486-1509`, `servicio_conductor.py:209-221`, `servicio_facturacion.py:586-598`); **excepción: `servicio_rentabilidad.py:400-416` actualiza sin `version`** (pisa `freight_score_*`; impacto menor, riesgo de carrera benigno). `cutover_legacy.py:378` inserta sin locks (operativo, con freeze). Evidencia 🟢.
2. **`nucleo.viaje_eventos` (4 escritores)** — append-only sin conflictos; acoplamiento de *registro*, no de estado. 🟢
3. **`public.clientes`/`public.choferes` (2 rutas legacy)** — `catalogos.py` y `export.py` (import CSV) escriben lo mismo sin coordinación; ambas sin manejo de `IntegrityError` (F-03). 🟢
4. **Maestros nucleo (3 escritores)** — `servicio_maestros` + `cutover_legacy.py` + `seed_local.py`. El script de cutover bypasea servicio, permisos, RLS y triggers de validación (conexión `psycopg` directa, `cutover_legacy.py:102-140`); escribe tarifas/OC sintéticas (`MIG-*`) que quedan como deuda de datos. 🟢
5. **`nucleo.reservas_recurso` (2 mecanismos)** — `servicio_bloqueos` con INSERT SQL crudo (`:244-252`) y el trigger `fn_viaje_reservas` (0015:219-224). Es el libro de ocupación **compartido** (correcto por diseño), pero conviven dos mecanismos con SQL duplicado. 🟢

## 2. Entrelazamiento de dependencias

### 2.1 Servicio→servicio (núcleo)

grep `^from app\.(nucleo|api|services|models|core)` en `backend/app/nucleo`:

| Servicio | Salientes hacia otros servicios | Entrantes desde servicios |
|---|---|---|
| `servicio_alertas` | **2**: `servicio_comercial.py:39`, `servicio_facturacion.py:40` (los instancia para leer datos) | 0 |
| Los otros 13 servicios + `kpi_engine` | **0** | — |

Único caso de servicio→servicio: alertas reutiliza los servicios de comercial y facturación como capa de lectura en lugar de consultar modelos propios. El resto se comunica **solo vía modelos + constraints + triggers** (p. ej. facturación cambia `nucleo.viajes.estado` con version; el trigger de reservas reacciona al cambio de viaje). 🟢

### 2.2 Rutas→servicios y servicios→rutas

- Cada router nucleo importa exactamente su servicio (1:1): `api_maestros.py:35`, `api_comercial.py` (get_servicio_*), etc. Excepciones: `api.py:39` (servicio_disponibilidad) y `servicio_alertas` vía `api_alertas.py`.
- `main.py:9` importa `servicio_cutover.legacy_congelado` para el middleware (dependencia app→servicio a nivel módulo).
- **Inversión (servicio→ruta): 0 coincidencias** (`from app.api` en nucleo = 0) 🟢.

### 2.3 Cruzadas legacy↔nucleo

- **legacy→nucleo**: solo montaje `api/router.py:17-29` y `main.py:8-9` (errores + cutover). Ninguna ruta legacy usa lógica nucleo. 🟢
- **nucleo→legacy**: 0 imports (`from app.api`/`from app.services` en nucleo = 0). 🟢
- **Acoplamiento real entre esquemas**: (a) scripts (`cutover_legacy.py` lee `public.*` y escribe `nucleo.*`; `seed_local.py` escribe ambos, p. ej. `:235` vs `:222`), (b) `servicio_cutover.estado()` lee `public.viajes` (`servicio_cutover.py:67`) para contar viajes abiertos legacy, (c) una sola conexión DB para ambos schemas. 🟢

### 2.4 Métrica resumen

| Tipo de dependencia | Resultado |
|---|---|
| Servicio→servicio | 1 par (alertas→comercial, alertas→facturacion); 13/14 servicios con 0 salientes 🟢 |
| Servicio→ruta (inversión) | 0 🟢 |
| Rutas→servicios | 1:1 por módulo 🟢 |
| legacy→nucleo | 2 archivos de composición (`router.py`, `main.py`) 🟢 |
| nucleo→legacy | 0 🟢 |
| Escrituras a tablas ajenas | `servicio_rentabilidad`→`viajes` (score), `servicio_facturacion`→`viajes` (estado), `servicio_conductor`→`viajes`, `servicio_expediente`→`viajes` — todas documentadas arriba, con version excepto rentabilidad 🟢 |

## 3. Hooks / interfaces / puntos de extensión

grep `Protocol|abstractmethod|ABC|webhook|callback|dispatch|subscribe|listener|signal|EventEmitter|BaseService` en `backend/app` → **0 coincidencias** 🟢.

- Los servicios se construyen inline en los routers: `ServicioMaestros(session, contexto)` (`api_maestros.py:61,69`), sin fábrica, interfaz ni contenedor. El único punto de inyección es `Depends()` de FastAPI.
- **No existe** ningún mecanismo de eventos/suscripciones a nivel de aplicación para conectar un emisor DTE/SII, un PSP de pagos o un ERP externo. Hoy, integrar un conector exige **modificar el cuerpo de `servicio_facturacion`** (emisión, pagos, notas) o del servicio correspondiente.
- Los únicos "hooks" reales son de **base de datos**: triggers `fn_viaje_reservas` (0015), `fn_viaje_documentos` (0015:247-315), `fn_auditoria` (0007), y el contexto vía `set_config('nucleo.auth_id'/'request_id')` (p. ej. `servicio_comercial.py:107-113`). La BD es el punto de extensión existente y probado.
- Consecuencia: cada integración futura = cirugía en el servicio + nueva migración; no hay "slot" donde enchufar un conector sin tocar el núcleo. Esto NO es un defecto hoy (nada lo exige aún), pero define el coste de la próxima integración (ver §5).

## 4. Rescatabilidad por módulo

Criterios usados: capas (F-10), transacciones/idempotencia (F-02, F-03), float (F-04), excepciones (F-08), versionado/locks (WP-7 §1.3).

### Legacy

| Módulo | Clasificación | Justificación (evidencia) |
|---|---|---|
| `catalogos` (public) | **NO RESCATABLE** | CRUD trivial duplicado por `nucleo.maestros` (`api_maestros.py:57-194`); commits directos sin manejo (F-03, F-10); único valor exclusivo: import CSV (`export.py:194-271`) |
| `viajes` (public) | **NO RESCATABLE** | Sin servicio, sin locks ni versiones; rentabilidad vía `kpi_engine` con float (F-04, `viajes.py:293-337`); el núcleo ya reemplaza con EXCLUDE + advisory locks (`servicio_disponibilidad.py:1397-1409`) |
| `facturacion` (public) | **NO RESCATABLE** | `numero_sii` manual sin idempotencia de folio (F-02), sin pagos/notas; el núcleo tiene folio por función (`servicio_facturacion.py:548-556`) y ciclo completo |
| `liquidaciones` | **RESCATABLE CON CIRUGÍA** | La regla de comisión (`liquidaciones.py:93-95`, Decimal, R-01/R-02) es la única lógica legacy sin equivalente nucleo; contorno (rutas, commits, PDF) a rehacer |
| `mantenimiento` | **RESCATABLE CON CIRUGÍA** | CRUD + estado simple; sin equivalente nucleo; lógica mínima, contorno a rehacer |
| `kpi_engine` | **RESCATABLE CON CIRUGÍA** | Motor de fórmulas (catalogo/validar/evaluar) reutilizable; capa de métricas con `float()` (F-04, `kpi_engine.py:442-458,503-520`) a rehacer en Decimal; probablemente obsoleto vs `servicio_rentabilidad` |
| `dashboard` (public) | **NO RESCATABLE** | Solo lectura sobre `public.*` que diverge de nucleo (F-02); reemplazado por `/nucleo/alertas/tablero` |

### Núcleo

| Módulo | Clasificación | Justificación (evidencia) |
|---|---|---|
| disponibilidad/reservas | **RESCATABLE** | Transaccional, advisory locks ordenados (`:1397-1409`), optimistic lock (`:1486-1509`), EXCLUDE en DB, `politicas.py`, `tarifas.py`; es el corazón del sistema |
| comercial (tarifas/OC/centros) | **RESCATABLE** | Validaciones de monto/sobregiro (`politicas.py:433-434`), historial de tarifas, traducción de errores (F-03 cumple) |
| facturación/cobranza nucleo | **RESCATABLE CON CIRUGÍA** | Folio por función, transiciones con version; defectos puntuales: `crear_promesa` sin try/except (F-03, `servicio_facturacion.py:708-709`); sin slot para conector DTE (§3) |
| expediente/POD | **RESCATABLE** | Eventos/checklist/incidentes/POD con version y compensación de storage (`servicio_pod.py:348-384`) |
| gastos | **RESCATABLE** | Decimal, aprobación con permisos, traducción; nota F-09 (permiso cruzado diésel, `api_gastos.py:71`) |
| rentabilidad | **RESCATABLE CON CIRUGÍA** | Decimal correcto; update de score sin `version` (`servicio_rentabilidad.py:400-416`) y swallow de fallo (F-08) |
| alertas | **RESCATABLE CON CIRUGÍA** | Único servicio con acoplamiento servicio→servicio (`servicio_alertas.py:39-40`); conviene desacoplar a consultas propias |
| permisos/auditoría | **RESCATABLE** | Catálogo de permisos (`permisos.py`) + trigger append-only (0007); sin deuda relevante |
| cutover | **RESCATABLE CON CIRUGÍA** | F-01: fail-open (`servicio_cutover.py:38-39`) y caché TTL 5 s (`:17,24-26`) a corregir |
| maestros | **RESCATABLE** | Documentos con storage + compensación (`servicio_maestros.py:442-474,500-506`), unicidad por empresa |
| conductor | **RESCATABLE** | Transiciones con version + eventos (`servicio_conductor.py:209-240`) |
| bloqueos | **RESCATABLE** | INSERT raw + traducción correcta; duplicación de SQL con el trigger de reservas (§1.3.5) |

## 5. Estimación de reescritura (entrada para el orquestador — NO es decisión)

Escenario peor (integración de conectores + retiro del legacy duplicado + corrección de defectos de WP-2):

- **Legacy**: la lógica única que vale la pena trasladar es ≤20% del código legacy (comisión de liquidaciones, fórmulas de kpi_engine, import CSV); el resto es reemplazo limpio por el núcleo (no se "rescata", se retira). 12 archivos de rutas quedarían obsoletos al completar el núcleo.
- **Núcleo**: reescritura cercana a **0 %** en disponibilidad/comercial/gastos/expediente/maestros/conductor (solo cirugías puntuales: F-01, F-03 promesa, version en score). Ajustes mayores acotados: alertas (desacople), cutover (fail-open). Estimado: **≤10–15 % del código del núcleo** requiere cirugía no trivial.
- **Conectores nuevos** (DTE/SII, pagos externos, otro ERP): son **código nuevo**, no reescritura; pero al no existir hooks (§3) el coste es tocar el cuerpo de `servicio_facturacion` (+ posible servicio nuevo) y agregar migración. Rango global estimado del backend: **15–25 % reescritura/cirugía mayor** en el peor escenario; el resto es rescatable tal cual o retirado sin rescate.

## 6. No verificado / limitaciones

- Sin shell: conteos de DB no re-ejecutados (heredados del orquestador). Todo lo citado con archivo:línea es lectura de código en disco 🟢.
- `viaje_documentos` (nucleo): escritor = servicio_expediente por el endpoint (`api_expediente.py:240`); el `add()` exacto no se localizó en el grep (🟡).
- Rol efectivo de `DATABASE_URL` (scripts bypasean RLS/permisos por diseño): no leído (secretos; ubicación `backend/.env`).
- `seed_local.py` y `cutover_legacy.py` son operativos/autorizados; su condición de "escritores paralelos" es deuda de datos, no bug.

## 7. Hallazgo inesperado (para escalar)

`scripts/cutover_legacy.py` es un escritor directo de **9 tablas nucleo** (`clientes:124`, `choferes:158`, `documentos:176,223,268`, `tractos:200`, `ramplas:259`, `tarifas:324`, `ordenes_compra:361`, `viajes:378`, `cutover_control:410`) por SQL `psycopg` que **bypasea servicios, permisos, triggers de validación documental (0015) y auditoría**, y crea tarifas/OC sintéticas `MIG-*` con valores fabricados (monto_autorizado `max(total*1.2, 1.000.000)`, `cutover_legacy.py:373`; capacidades fijas 30.000 kg `:203,261`). Documentado en su docstring (`:6-13`), pero conviene que el orquestador confirme si este bypass está aprobado para producción.
