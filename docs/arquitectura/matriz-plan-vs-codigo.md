# Matriz de reconciliación — `docs/_archivo/planes/PLAN_MAESTRO_ERP_V2.md` vs. repositorio

> **Pregunta que responde:** ¿qué afirmaba el plan maestro y qué existe realmente hoy?
> **Dueño:** `arquitectura` · **Verificado:** 2026-10-29 · **Método:** lectura estática **antes** de `0015`–`0019`
> **Caduca si:** se archiva o corrige (hoy está superado por las migraciones 0015–0019).
> **Re-verificar con:** `ls supabase/migrations | wc -l`


- **Autor:** agente `arquitectura`
- **Fecha:** 2026-10-29
- **Documento reconciliado:** `docs/_archivo/planes/PLAN_MAESTRO_ERP_V2.md` (v2.0, octubre 2026)
- **Alcance:** hallazgos §2.4 (20), riesgos §27 "esta semana" (5), contradicciones y
  capacidades ausentes.
- **Método:** lectura estática de SQL, código Python/TypeScript y búsquedas
  dirigidas. **No se ejecutó nada**: PostgreSQL en `127.0.0.1:54322` estaba
  apagado, backend `:8000` y frontend `:3000` cerrados, y este agente no tiene
  permiso de shell. Toda afirmación sobre comportamiento en ejecución es
  🔴 hasta que alguien la pruebe.

## 0. Cómo leer esta matriz

| Marca | Significado |
|---|---|
| 🟢 **Verificado** | Leído en el archivo citado, en esta sesión. |
| 🟡 **Inferido** | Deducción razonable; se indica qué la confirmaría. |
| 🔴 **No verificable** | Requiere base de datos, ejecución o información ausente. |

**Veredictos y su regla.** El plan pide "corregir" defectos. Un defecto está
`resuelto` solo si existe el mecanismo **y** no queda una ruta de escritura que lo
evite. Como `nucleo.cutover_control.legacy_escritura_congelada` nace en `false`
(`supabase/migrations/0014_cutover.sql:10,17-19`) y el middleware solo bloquea
escrituras legacy cuando ese flag está en `true`
(`backend/app/main.py:36-61`), **hoy ningún hallazgo está `resuelto` en el
sistema completo**: los que tienen mecanismo en `nucleo` quedan como
`solo en núcleo`, porque `public` sigue aceptando escrituras y no comparte el
libro de ocupación.

Ese es el hallazgo estructural que ordena todo el resto y el motivo del
`ADR-0001`.

---

## 1. Los 20 hallazgos del §2.4

Leyenda de columnas: **N** = ¿existe mecanismo en `nucleo`? · **L** = ¿existe en
`public` (legacy)? · **V** = veredicto.

| # | Hallazgo del plan | N — mecanismo en `nucleo` | L — estado en `public` | V | Riesgo residual |
|---|---|---|---|---|---|
| 1 | Solo se valida tracto, no rampla/chofer | 🟢 3 `EXCLUDE USING gist` (tracto, rampla, chofer) `supabase/migrations/0004_nucleo_operacional.sql:744-757`; reservas creadas por trigger desde el viaje `0004:1621-1650`; locks de asesoría en el servicio `backend/app/nucleo/servicio_disponibilidad.py:1397-1411` | 🟢 Solo tracto y por estado `backend/app/api/routes/viajes.py:99-115`; `_validar_recursos` no mira rampla/chofer `viajes.py:74-88` | solo en núcleo | **Alto**: una escritura legacy asigna la misma rampla/chofer sin tocar `nucleo.reservas_recurso` (`AGENTS.md` §3.8, RA-02) |
| 2 | Validación por estado, no por fechas | 🟢 `ventana tstzrange` con `ck_viaje_ventana` `0004:561,666-669`; cálculo en `fn_viaje_ventana` `0004:899-940`; `EXCLUDE` sobre la ventana `0004:746` | 🟢 `Viaje.estado.in_([programado, en_ruta])` `viajes.py:102-105`; fechas solo se comparan entre sí `viajes.py:91-96` | solo en núcleo | **Alto** en legacy: bloqueos falsos y solapes futuros persisten |
| 3 | No se validan documentos al asignar | 🟢 Trigger de BD `trg_viajes_10_validar` `0004:1834-1835` → `validar_documentos_recurso` por tracto/rampla/chofer `0004:1281-1292`; tipos exigidos por recurso `0004:1041-1074`; evaluación de vencimientos en servicio `backend/app/nucleo/servicio_disponibilidad.py:234-311` | 🟢 Solo `activo` booleano `viajes.py:74-88`; no consulta documentos | solo en núcleo | **Alto** en legacy (multa, seguro nulo). En núcleo la **clase** de licencia es advertencia, no bloqueo: comentario explícito `0004:1272-1274` → validar con el dueño/legal |
| 4 | `finalizado → en_ruta` permitido | 🟢 `transiciones_viaje` sin reapertura de `cerrado`/`facturado` `0004:779-808`; `fn_viaje_transicion` rechaza transición no listada `0004:1511-1547`; anulado no se reabre `0004:1493-1495`; finanzas congeladas `0004:1474-1491` | 🟢 `TRANSICIONES` permite `finalizado → en_ruta` y `facturado → finalizado` `viajes.py:36-41` | solo en núcleo | **Alto** en legacy. En núcleo **no existe reapertura controlada** (el plan pedía reapertura con motivo/aprobación): es una decisión de negocio pendiente, no un defecto técnico |
| 5 | Gastos se pueden crear/borrar en viaje facturado | 🟢 `crear_gasto` bloquea `anulado/facturado/cobrado` `backend/app/nucleo/servicio_gastos.py:255-259`; aprobación con segregación `servicio_gastos.py:151-165`; congelamiento de campos financieros en BD `0004:1474-1491` | 🟢 `crear_gasto` y `eliminar_gasto` sin mirar estado del viaje `backend/app/api/routes/gastos.py:55-102`; `on delete cascade` `supabase/migrations/0001_esquema_base.sql:116` | solo en núcleo | **Alto** en legacy: el margen histórico se puede alterar o borrar |
| 6 | Factura se puede borrar si está pendiente | 🟢 `nucleo.notas_credito_nucleo` `supabase/migrations/0013_facturacion.sql:112-134`; `crear_nota_credito` con tope de saldo `backend/app/nucleo/servicio_facturacion.py:653-664`; la API no expone `DELETE` ni `PUT` (`backend/app/nucleo/api_facturacion.py:48-124`) | 🟢 `@router.delete("/facturas/{id}")` con `session.delete` `backend/app/api/routes/facturas.py:241-262` | solo en núcleo | **Alto** en legacy: pérdida de trazabilidad tributaria |
| 7 | Folio único por cliente | 🟢 `unique (empresa_id, numero_factura)` `0013:30`; folio generado en BD `nucleo.siguiente_folio` `0004:498` usado en `servicio_facturacion.py:548-559` | 🟢 `unique (numero_sii, cliente_id)` `0001:142` | solo en núcleo | **Alto** en legacy: folios duplicados entre clientes |
| 8 | Pago total, sin parciales | 🟢 Tabla `nucleo.pagos_nucleo` `0013:78`; `registrar_pago` valida `monto <= saldo` `servicio_facturacion.py:620-651`; saldos con notas de crédito `servicio_facturacion.py:133-149` | 🟢 Solo `estado` `pendiente/pagada` en `facturas.py:201-232`; no hay tabla de pagos en `0001` | solo en núcleo | **Alto** en legacy: la realidad de pagos parciales no se puede representar |
| 9 | Comisión sobre flete no cobrado | — no hay módulo de liquidaciones en `nucleo`; solo costo estimado con `comision_estimada` `backend/app/nucleo/servicio_rentabilidad.py:346` (no es nómina) | 🟢 `_comision_chofer` usa estados `finalizado/facturado` `backend/app/api/routes/liquidaciones.py:45-59`; sin política devengado/cobrado configurable | **no resuelto** | **Alto**: es una decisión comercial/laboral del dueño, no un bug. No debe resolverse por inferencia |
| 10 | PDF de liquidación recalcula desde viajes | — no existe liquidación en `nucleo` | 🟢 `pdf_liquidacion` recalcula comisión al emitir `liquidaciones.py:465-502`; sin snapshot de líneas | **no resuelto** | **Medio-alto**: documento histórico inconsistente. Requiere decisión de qué se congela |
| 11 | KPI de mantenimiento ignora "sin registro" | — `nucleo` no tiene plan de mantenimiento por km; solo **bloqueos** de agenda tipo `mantenimiento` `supabase/migrations/0006_bloqueos.sql:9-14` | 🟢 La pantalla devuelve `estado: "sin_registro"` `backend/app/api/routes/mantenimiento.py:186-198`, pero el KPI hace `continue` cuando no hay registro `backend/app/services/kpi_engine.py:484-485` | **no resuelto** | **Medio**: unidades nuevas siguen sin alertar; la inconsistencia pantalla/KPI es explotable por confianza falsa |
| 12 | Dashboard no muestra mantenimiento | 🟢 `servicio_alertas` incluye categoría `mantencion` `backend/app/nucleo/servicio_alertas.py:165-198` y alimenta el tablero | 🟢 `/alertas` solo documentos y facturas `backend/app/api/routes/dashboard.py:100-178` | solo en núcleo | **Medio** en legacy: falla sorpresa |
| 13 | `margen_bruto` no descuenta comisión | 🟢 `margen = ingreso − costo_variable` con comisión incluida en el costo `servicio_rentabilidad.py:179-215,323-346` | 🟢 `margen = ingresos − gastos` `kpi_engine.py:440`; la comisión se calcula aparte `kpi_engine.py:369-381` y **no se resta** | solo en núcleo | **Alto** en legacy: margen sobreestimado en toda decisión basada en KPI |
| 14 | Gastos del mes vs ingresos devengados | — `nucleo` calcula por viaje; no hay P&L mensual devengado | 🟢 Ingresos desde viajes `finalizado/facturado` por `fecha_fin` `kpi_engine.py:312-320`; gastos por `GastoViaje.fecha` `kpi_engine.py:321-327` | **no resuelto** | **Medio**: mezcla de criterios. Requiere definición contable (validar con contador) |
| 15 | CSV sin sanitización | — `nucleo` no exporta CSV (búsqueda `csv|CSV` en `backend/app/nucleo` → 0 resultados) | 🟢 `csv.DictWriter` con `QUOTE_MINIMAL`, sin escapar `= + - @` `backend/app/api/routes/export.py:29-45` | **no resuelto** | **Medio**: inyección de fórmulas en Excel al abrir un export con nombres de cliente maliciosos |
| 16 | Sin paginación | 🟢 `limit/offset` en listados `backend/app/nucleo/api.py:108-109,132-133`, `api_facturacion.py:65-66`, `api_expediente.py:57-58`, `api_permisos.py:81-82`; tope `MAX_RECURSOS` `servicio_disponibilidad.py:638` | 🟢 Listados sin `limit/offset` `viajes.py:118-137`, `facturas.py:73-87` | solo en núcleo | **Medio** en legacy: lentitud y riesgo operativo con volumen |
| 17 | Sin auditoría | 🟢 `nucleo.auditoria` `0004:813-828`; inmutabilidad por trigger `0004:880-892`; triggers `fn_auditoria` en viajes, reservas, documentos, OC, facturación, gastos, POD, expediente (`0004:1761-1862`, `0005:42`, `0007:58-211`, `0009:45`, `0011:24,81`, `0013:49-158`) | — no existe tabla ni trigger de auditoría en `0001`–`0003` | solo en núcleo | **Alto** en legacy. Además la cobertura del núcleo es **parcial**: `nucleo.cutover_control`, `nucleo.transiciones_viaje` y `nucleo.folio_contador` no tienen trigger de auditoría |
| 18 | Sin multiempresa | 🟢 `empresa_id` en tablas de negocio y FKs compuestas `0004:720-728`; resolución de empresa por `X-Empresa-ID` + membresía `backend/app/nucleo/deps.py:40-82`; RLS habilitado `0004:1867-1881` | — `public` no tiene `empresa_id` en ninguna tabla (`0001` completo) | solo en núcleo | **Alto**: RLS habilitado **sin políticas** (`create policy` en `nucleo` → 0 resultados) no es aislamiento; el rol efectivo de `DATABASE_URL` no es verificable sin base 🔴 (RA-03) |
| 19 | Migraciones manuales y posible deriva SQLModel/SQL | 🟢 14 migraciones forward-only `supabase/migrations/0001..0014`; sin `create_all` (`backend/app/nucleo/models.py:4`); sin Alembic | 🟢 Mismo esquema, sin verificación de deriva | **no resuelto** | **Alto**: no hay CI (`.github/workflows` → 0 archivos), no hay chequeo de deriva modelo↔DDL, no hay entorno staging declarado en el repo |
| 20 | Sin cola/worker | — búsqueda `outbox|redis|celery|worker|cola_trabajo|job_queue` en `*.{py,ts,tsx,sql}` → **0 resultados** | — igual | **no resuelto** | **Bajo hoy, medio al escalar**: no hay proceso asíncrono; alertas y reportes son síncronos. No justifica introducir cola todavía (ver ADR-0001, alternativas descartadas) |

**Lectura de conjunto.** De 20 hallazgos: 13 tienen mecanismo en `nucleo`
(quedan `solo en núcleo`), 7 no tienen mecanismo en ninguno de los dos esquemas.
Ninguno está `resuelto` globalmente mientras el legacy pueda escribir.

---

## 2. Los 5 riesgos del §27 "esta semana"

| Riesgo (§27) | N — mecanismo en `nucleo` | L — estado en `public` | V | Riesgo residual |
|---|---|---|---|---|
| Doble asignación de rampla/chofer | 🟢 `ex_reserva_rampla` `0004:749-752`, `ex_reserva_chofer` `0004:754-757`; traducción de `23P01` a HTTP 409 `backend/app/nucleo/errores.py:140-147` | 🟢 Solo tracto `viajes.py:99-115` | solo en núcleo | **Alto**: la garantía es real en `nucleo` pero **no está probada con dos conexiones** (ver §5). En `public` el riesgo es total |
| Documentos vencidos al asignar | 🟢 Bloqueo duro en trigger `0004:1281-1292` + `0004:1041-1074` | 🟢 No se valida `viajes.py:74-88` | solo en núcleo | **Alto** en legacy. En núcleo la lista de documentos exigidos es configurable por empresa (`exigir_soap`, `exigir_seguro_carga`, `0004:123,1047-1059`): validar la configuración con el dueño |
| Mantenimiento sin alerta | 🟡 Alerta sobre **bloqueos agendados** en los próximos 7 días `servicio_alertas.py:165-198`; **no** hay pauta por km en `nucleo` (búsqueda `plan_mantenimiento` → 0) | 🟢 KPI ignora `sin_registro` `kpi_engine.py:484-485`; dashboard no muestra mantenimiento `dashboard.py:100-178` | **no resuelto** | **Medio**: el plan pedía "mantenimiento sin alerta" y hoy solo se resuelve la mitad (agenda sí, preventivo por km no) |
| Factura sin POD | 🟢 `_validar_viajes_facturables` exige POD `servicio_facturacion.py:494-501`; además exige viaje `cerrado` y OC `servicio_facturacion.py:485-493`; `nucleo.pod` con firma, fotos, lat/lon y no borrado `0009:8-50` | 🟢 `crear_factura` solo exige `viaje.estado == finalizado` `facturas.py:127`; no consulta POD | solo en núcleo | **Alto** en legacy: se factura sin prueba de entrega |
| Folio duplicado | 🟢 `unique (empresa_id, numero_factura)` `0013:30` | 🟢 `unique (numero_sii, cliente_id)` `0001:142` | solo en núcleo | **Alto** en legacy |

---

## 3. Contradicciones del plan

Todas son afirmaciones del plan refutadas (o desactualizadas) por el repositorio.
No se corrige el plan: se registra la diferencia.

| # | Afirmación del plan | Evidencia en el repo | Clasificación |
|---|---|---|---|
| C1 | §0.1: "Revisé … las 3 migraciones SQL, los 12 routers del backend … las 15 pantallas" | 14 migraciones (`supabase/migrations/0001..0014`); **26 routers** montados `backend/app/api/router.py:32-56`; **28** `page.tsx` (25 bajo `frontend/src/app/(app)/`, más `login`, raíz y `conductor`) | 🟢 refutado — el diagnóstico es anterior al núcleo v2 |
| C2 | §0.2 y §2.1: "No tiene auditoría, multiempresa, …" | `nucleo.auditoria` `0004:813`; `empresa_id` + RLS `0004:1867-1881`; resolución por membresía `deps.py:40-82` | 🟢 refutado **para `nucleo`**, cierto **para `public`**. El plan no distingue esquemas |
| C3 | §2.3: "No hay restricciones de exclusión en PostgreSQL para evitar doble asignación" | 3 `EXCLUDE USING gist` `0004:744-757` | 🟢 refutado para `nucleo` |
| C4 | §2.3: "No hay RLS efectiva … el backend usa `service_role`" | RLS habilitado en 15 tablas `0004:1867-1881`, **sin políticas**; el comentario del propio DDL dice que el backend entra con `service_role`/`postgres` `0004:1865` | 🟡 parcialmente confirmado: el mecanismo existe, la **efectividad como aislamiento no**. Falta verificar el rol real de conexión 🔴 |
| C5 | §2.3: "No hay tests E2E ni tests de integración en CI con PostgreSQL real" | `frontend/e2e/tei.spec.ts` con 9 escenarios `:14-90`; `backend/tests/test_nucleo_integracion.py:58` prueba doble asignación contra PostgreSQL real | 🟡 parcialmente refutado: los tests **existen**, pero (a) no hay CI (`.github/workflows` → 0) y (b) no se ejecutaron en esta sesión |
| C6 | §2.3: "El folio de factura es único por cliente" | `unique (empresa_id, numero_factura)` `0013:30` | 🟢 refutado para `nucleo`; cierto en `0001:142` |
| C7 | §22.1: "Estado actual: monolito simple, sin cola, sin eventos, sin multiempresa" | `nucleo` es multiempresa con auditoría; sigue sin cola y sin outbox | 🟡 parcialmente refutado |
| C8 | §6.5: estrategia de migración = "Agregar `empresa_id` … a las tablas actuales", "mantener compatibilidad … mediante vistas o columnas puente", "congelar el esquema viejo" | El repo **no** evolucionó `public`: creó un esquema paralelo `nucleo` con tablas nuevas (`0004`–`0014`) y un script de copia `scripts/cutover_legacy.py:82-403`. No hay vistas puente ni columnas puente | 🟢 **divergencia de estrategia**, no error. Es exactamente lo que resuelve el `ADR-0001` |
| C9 | §23.2 Fase 0 "3 semanas: multiempresa, auditoría, migraciones, seguridad, backups, observabilidad, roles v2" | Multiempresa, auditoría y roles v2 existen en `nucleo`; **observabilidad y staging no** (sin CI, sin Sentry/OTel, sin `.github`); backups vía `scripts/restore_drill.sh` (no ejecutado) | 🟡 parcialmente construida |
| C10 | §27: "Corregir los 5 riesgos más caros **esta semana**" | 4 de 5 ya tienen mecanismo en `nucleo`; ninguno está protegido en `public`; el riesgo de mantenimiento sigue abierto en ambos | 🟡 el plan asume un solo esquema |

---

## 4. Qué del plan NO está en el repo (verificado por ausencia)

Búsquedas ejecutadas con `grep` sobre el repositorio. Se cita el patrón y el
resultado. Un resultado vacío es evidencia de ausencia en el código, **no** de
que no se haya decidido construir.

| Capacidad del plan | Patrón buscado (ámbito) | Resultado | Clasificación |
|---|---|---|---|
| GPS, geocercas, telemetría, ETA | `gps\|GPS\|geocerca\|telemetria\|telemetría` en `*.{py,ts,tsx,sql}` | **0 coincidencias** | 🟢 ausente |
| DTE / SII | `DTE\|SII\|sii_\|boleta_electronica\|xml_dte` en `*.{py,ts,tsx,sql}` | 9 coincidencias, **todas declarando la ausencia**: `0013:4` ("Sin DTE real en el piloto"), `servicio_facturacion.py:3`, `nueva-factura-dialog.tsx:139`, `facturacion/page.tsx:140,204,303,370,375`, `cobranzas/page.tsx:141` | 🟢 ausente y **declarado** en UI |
| Cuentas por pagar, tesorería, caja 13 semanas, conciliación bancaria | `tesoreria\|tesorería\|flujo_caja\|flujo de caja\|conciliacion_bancaria\|factura_proveedor\|cuentas_por_pagar\|pago_proveedor` | 13 coincidencias, todas de **nombre de rol** o etiqueta UI (`models.py:84`, `permisos.py:99`, `permisos/page.tsx:25`, `seed_local.py:96,106`). Sin tablas ni endpoints | 🟢 ausente |
| Nómina legal (AFP, salud, cesantía, finiquito, gratificación, impuesto único) | `AFP\|afp\|cesantia\|cesantía\|finiquito\|gratificacion\|impuesto_unico\|nomina\|nómina` en `*.{py,ts,tsx,sql}` | **0 coincidencias** | 🟢 ausente |
| Jornada, horas de conducción, descansos, planes de mantenimiento por km, sucursales | `sucursal\|jornada\|horas_conduccion\|descanso_\|plan_mantenimiento` en `*.{py,sql}` | **0 coincidencias** | 🟢 ausente |
| Neumáticos, repuestos, inventario, órdenes de trabajo | `neumatico\|neumático\|repuesto\|inventario\|orden_trabajo\|proveedor` | 20 coincidencias, **todas** `proveedor` como **texto libre** en gastos (`0011:34`, `models.py:1062`, `schemas.py:1312`, `conductor/page.tsx:834`) y `centros_costo`; ninguna tabla de neumáticos/repuestos/inventario/OT | 🟢 ausente (solo un campo de texto) |
| OCR | `ocr\|OCR\|tesseract\|textract` | 1 coincidencia, **falso positivo**: `numero_oc=f"OCR-{token}"` en `backend/tests/test_nucleo_rentabilidad.py:107` | 🟢 ausente |
| Copiloto / IA | `copiloto\|openai\|llm\|embedding` | **0 coincidencias** | 🟢 ausente |
| Integraciones (WhatsApp, email, mapas, bancos) | `whatsapp\|WhatsApp\|twilio\|smtp\|sendgrid\|mapbox\|google_maps` | **0 coincidencias** | 🟢 ausente |
| Cola / worker / outbox / eventos | `outbox\|redis\|celery\|worker\|cola_trabajo\|job_queue` | **0 coincidencias** | 🟢 ausente |
| Export CSV desde el núcleo | `csv\|CSV` en `backend/app/nucleo` | **0 coincidencias** (el export CSV solo existe en legacy `export.py`) | 🟢 ausente en `nucleo` |
| Liquidaciones / comisiones en el núcleo | módulo `liquidaciones` en `backend/app/nucleo/**` | No existe archivo; solo `comision_estimada` para costo `servicio_rentabilidad.py:346` | 🟢 ausente |
| Mantenimiento preventivo en el núcleo | tablas `nucleo.*mantenimiento*` en migraciones | No existen; solo `tipo_reserva = 'mantenimiento'` en `0006_bloqueos.sql:9-14` | 🟢 ausente |

**Nota de honestidad:** la ausencia de GPS, DTE, AP, nómina, OCR, copiloto e
integraciones **coincide con lo que `docs/_archivo/planes/PLAN_90_DIAS.md:48-60` declara fuera
del piloto**. No es un incumplimiento del plan de 90 días; sí es una brecha
frente al plan maestro completo.

---

## 5. Lo que NO se pudo verificar (y qué lo confirmaría)

| # | Afirmación que queda 🔴 | Qué la confirmaría |
|---|---|---|
| V1 | Que las 14 migraciones aplican limpias y producen el esquema descrito | `supabase db reset` + `\d+ nucleo.*` en base local (requiere autorización y base arriba) |
| V2 | Que los `EXCLUDE` rechazan realmente dos transacciones simultáneas | Prueba con **dos conexiones** concurrentes que espere SQLSTATE `23P01`. El test existente `test_nucleo_integracion.py:262-274` es **secuencial** y verifica la pre-validación del servicio, no la restricción |
| V3 | Que `23P01` llega al cliente como 409 y no como 500 | Test HTTP con dos requests concurrentes contra el endpoint de asignación |
| V4 | El rol efectivo de conexión del backend y si está sujeto a RLS | Inspeccionar `current_user` y `pg_roles.rolbypassrls` **sin imprimir la cadena de conexión** |
| V5 | Que `make unit` sigue en verde | Ejecutarlo. Heredado del contrato del orquestador: 50 passed 🟡, no re-ejecutado aquí (sin shell) |
| V6 | Que la suite completa pasa | `make test` con Supabase local; hoy imposible (puerto cerrado) |
| V7 | Que los 9 escenarios E2E pasan | `make e2e` con frontend y datos |
| V8 | Que `scripts/cutover_legacy.py --dry-run` no falla | Ejecutarlo en dry-run (no escribe) |
| V9 | Que el flag de cutover se propaga en <5 s a todos los workers | El caché es por proceso (`servicio_cutover.py:17-41`); con un solo proceso es inmediato tras `invalidar_cache()`. Con varios, hay ventana de hasta 5 s **por proceso** |
| V10 | Estado exacto del árbol git (135 entradas, staging del núcleo) | `git status --short`. Heredado del contrato 🟡 |
| V11 | Que la pantalla de mantenimiento y el KPI muestran números distintos con datos reales | Consulta con datos del seed |

---

## 6. Conclusión operativa

1. **El plan no describe el repositorio de hoy.** Su §2 es un diagnóstico del
   legacy `public`; el núcleo v2 lo corrige en 13 de 20 puntos, pero el plan no
   lo sabe y sigue recomendando construir lo ya construido.
2. **El problema real no es "faltan correcciones": es que hay dos esquemas que
   aceptan escrituras y solo uno tiene garantías.** Mientras el flag de cutover
   esté en `false`, toda garantía del núcleo es evitable por la puerta legacy.
3. **7 de 20 hallazgos siguen sin mecanismo en ningún esquema**, y 4 de ellos
   (comisión devengada, snapshot de liquidación, criterio de devengo, mantenimiento
   preventivo) **no son decisiones técnicas**: son decisiones del dueño y del
   contador. No deben resolverse por inferencia.
4. El alcance del piloto no puede fijarse sin decidir primero **qué esquema es
   canónico por módulo**. Eso es el `ADR-0001` y la base de
   `02-alcance-piloto-90-dias.md`.
