# Matriz de garantías de integridad — `nucleo` vs legacy `public`

> **Pregunta que responde:** ¿qué garantiza PostgreSQL hoy y qué solo el servicio o la UI?
> **Dueño:** agente `datos` · **Verificado:** 2026-10-29 · **Método:** lectura de DDL
> **Caduca si:** se agrega o edita una migración, o se ejecutan pruebas contra una base real.
> **Re-verificar con:** `ls supabase/migrations/` + lectura de las migraciones citadas.

> **Alcance:** **19 migraciones** (`supabase/migrations/0001`–`0019`), modelos SQLModel
> (`backend/app/nucleo/models.py`, `backend/app/models/__init__.py`), servicios y
> rutas (`backend/app/nucleo/**`, `backend/app/api/routes/**`), scripts
> (`scripts/cutover_legacy.py`, `scripts/seed_local.py`).
> **Fuera de alcance:** ejecución contra base de datos.
> **Cambio respecto de la versión anterior (alcance `0014`):** se extendió a
> `0015`–`0019`; se corrigieron las filas 1.4, 1.6, 1.7, 3.3 y 12.4, que `0015`
> modifica; se agregó §13 con las garantías nuevas; y se renumeraron las secciones
> 13–15 a 14–16. El resto se conserva tal como se verificó.
> **Nota de numeración:** si un documento cita `garantias.md` §13.2 (RLS), hoy es
> §14.2; §14.2 (SQLSTATE) es hoy §15.2. Pendiente de corregir en
> `docs/qa/matriz-trazabilidad.md:213`.

## 0. Método y límites (leer antes de citar esta matriz)

1. **No hubo conexión a base de datos.** No se intentó levantar Supabase (por
   contrato). Todo lo que dice "existe" significa **"existe el DDL en una
   migración"**, no "está en vigor en una base".
2. **Lo único 🟢 de este documento es "el DDL existe y lo leí"**. Que el objeto
   esté aplicado, que el rol de la aplicación lo respete y que el invariante se
   sostenga con datos reales es 🔴 hasta que haya base y prueba.
3. **Nada de concurrencia está probado.** Sin dos conexiones reales, ninguna fila
   de esta matriz puede declararse "concurrencia verificada" (`AGENTS.md` §7).
4. Los "ausente" se justifican con el patrón de búsqueda usado, indicado en la
   nota al pie de cada dominio.
5. **Corrección al contexto heredado:** el brief del orquestador ubica los
   `EXCLUDE USING gist` por tracto/rampla/chofer "en `nucleo.viajes`
   (`0004_nucleo_operacional.sql:746,751,756`)". Es **incorrecto**:
   `nucleo.viajes` **no tiene ningún `EXCLUDE`** (solo un índice GIST sobre
   `ventana`, `0004:698`). Las tres restricciones de exclusión están en
   `nucleo.reservas_recurso` (`0004:744-757`) y solo protegen lo que **se escribe
   en el libro de reservas**. La distinción no es cosmética: es la causa de
   INV-D04 (ver §1 fila 1.4 y `invariantes.md`).
6. **Las migraciones `0015`–`0019` existen en disco, no se sabe si están
   aplicadas.** `0004`–`0014` están *staged* y `0015`–`0019` sin seguimiento en
   git (`docs/datos/catalogo-migraciones.md` §2). Ninguna fila de este documento
   puede declararse "en vigor": **la aplicación es 🔴 en las 19 migraciones**.
   Donde una garantía depende de `0015`–`0019`, la columna lo dice; la ausencia
   de esa nota significa que el mecanismo está en `0001`–`0014`.

### Leyenda

| Marca | Significado |
|---|---|
| 🟢 | Impuesto en PostgreSQL (constraint/trigger/función), con `archivo:línea` leído. **No** implica probado ni aplicado. |
| 🟡 | Solo en servicio/API (Python) o en UI. La base no lo impide. |
| 🔴 | Ausente: no hay mecanismo en DB ni validación de servicio que lo cubra. |
| ⚪ | No verificable sin base (dato, rol efectivo, comportamiento con volumen). |

---

## 1. Viajes y asignación de recursos

| # | Garantía esperada | `nucleo` (mecanismo · ubicación) | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 1.1 | Un tracto no tiene dos ocupaciones activas solapadas en `[inicio, fin)` | `EXCLUDE USING gist (tracto_id WITH =, ventana WITH &&) WHERE (recurso_tipo='tracto' AND activa)` · `0004:744-747`; materializado por `fn_viaje_reservas` · `0004:1621-1650` | Ninguno: `viajes` sin `EXCLUDE` ni `CHECK` de fechas · `0001:97-112` | Servicio legacy: `SELECT` + `if` sobre `estado in (programado, en_ruta)` · `api/routes/viajes.py:99-115` | núcleo 🟢 / legacy 🔴 |
| 1.2 | Ídem rampla | `ex_reserva_rampla` · `0004:749-752` | Ninguno | No se valida **nada** de rampla: `_validar_tracto_disponible` solo consulta `tracto_id` · `viajes.py:99-115` | núcleo 🟢 / legacy 🔴 |
| 1.3 | Ídem chofer | `ex_reserva_chofer` · `0004:754-757` | Ninguno | Ídem: chofer nunca se consulta para disponibilidad · `viajes.py:99-115` | núcleo 🟢 / legacy 🔴 |
| 1.4 | **Todo viaje que ocupa recursos tiene reserva activa en el libro** | `0015` reescribe `fn_viaje_reservas`: ocupa si tiene **los tres** recursos y `estado <> 'anulado'`, cualquiera sea el estado · `0015:183-245`; el trigger `trg_viajes_70_reservas` ya existía · `0004:1848` | n/a | `cutover_legacy.py:361-388` inserta viajes `confirmado` con recursos y **ahora falla con `23514`** (documentos) en vez de quedar fuera del libro: `0015:133-142` | 🟢 DDL (`0015`) · **🔴 sin aplicar ni probar**; recursos parciales **no** ocupan (frontera declarada, `0015:30-35`) |
| 1.5 | Una reserva de viaje no puede desactivarse mientras el viaje siga ocupando el recurso | `fn_reserva_validar` no lo impide · `0004:1653-1690`; solo bloquea `DELETE` · `0004:1692-1700,1859-1860`; `UPDATE ... activa=false` es libre | n/a | Solo el trigger de viaje desactiva reservas · `0004:1628-1630` (no exclusivo) | 🔴 |
| 1.6 | Recursos obligatorios desde `asignado` | `ck_viaje_recursos_por_estado` · `0004:671-674` | `chofer_id/tracto_id/rampla_id NOT NULL` siempre · `0001:106-108` | — | 🟢 (permite `confirmado` con o sin recursos; desde `0015`, con los tres ocupa el libro y sin ellos no bloquea: la frontera es "3 recursos", no el estado) |
| 1.7 | Al asignar: documentos vigentes, capacidad, compatibilidad de carga, tarifa y OC | `fn_viaje_validar` · `0004:1106-1384` + `validar_documentos_recurso` · `0004:1019-1104` (solo estados operativos, `0004:1124-1126`); desde `0015`, la puerta documental corre **para todo viaje con los tres recursos**, incluso `borrador`/`confirmado` · `0015:247-310` | Nada: `_validar_recursos` solo verifica existencia/`activo` · `viajes.py:74-88` | Triggers `trg_viajes_05_documentos` (`0015:312-315`) y `trg_viajes_10_validar` · `0004:1834-1835` | 🟢 DDL / legacy 🔴 |
| 1.8 | La validación dura no se salta al cambiar de estado | Bypass explícito y documentado para cambios de estado sin cambio de recursos · `0004:1128-1138` | n/a | — | 🟢 (decisión consciente; ver riesgo R-02 en §5) |
| 1.9 | Transiciones de estado legales | Tabla `transiciones_viaje` · `0004:772-808` + `fn_viaje_transicion` · `0004:1511-1547` | `TRANSICIONES` en Python · `viajes.py:36-41` + `cambiar_estado` · `viajes.py:236-240` | Trigger `trg_viajes_30_transicion` · `0004:1840-1841` | núcleo 🟢 / legacy 🟡 |
| 1.10 | Viaje anulado no se reabre; `numero_viaje` y `empresa_id` inmutables | `fn_viaje_proteccion` · `0004:1466-1472,1493-1495` | Ninguno | — | 🟢 |
| 1.11 | Campos financieros congelados tras iniciar ejecución | `fn_viaje_proteccion` · `0004:1474-1491`, escape por `current_setting('nucleo.ajuste_autorizado')='on'` · `0004:1485` | Ninguno (`actualizar_factura` reescribe montos si `pendiente` · `facturas.py:189-196`) | Trigger `trg_viajes_20_proteccion` · `0004:1838-1839` | 🟢 con salvedad (el escape es un `set_config` de sesión, no un permiso auditado) |
| 1.12 | No se borra un viaje ya operado | `fn_viaje_proteccion` · `0004:1457-1463` (solo `borrador`/`cotizado`) | `DELETE` permitido si `programado` · `viajes.py:253-268` | Trigger BEFORE DELETE · `0004:1838-1839` | núcleo 🟢 / legacy 🔴 |
| 1.13 | `ventana` coherente con inicio/fin/buffer | `fn_viaje_ventana` · `0004:899-936` + `ck_viaje_ventana` · `0004:666-670` | n/a | Trigger `trg_viajes_00_ventana` · `0004:1832-1833` | 🟢 |

*Búsqueda usada para los "ausente":* `grep -rn "exclude using gist" supabase/migrations/`
→ 3 coincidencias, todas en `0004` líneas 746/751/756 y todas sobre
`nucleo.reservas_recurso`; `0015`–`0019` **no agregan ningún `EXCLUDE`**
(`grep -ln "exclude using gist" supabase/migrations/001[5-9]_*.sql` → vacío);
`grep -n "unique\|check\|Index" backend/app/models/__init__.py`
→ `Viaje` (`139-155`) no declara ninguna restricción.

---

## 2. Disponibilidad y libro de reservas (bloqueos, mantención, descanso)

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 2.1 | Libro único de ocupación: viaje, mantención, descanso, vacaciones, siniestro y bloqueo compiten por el mismo recurso | `reservas_recurso` + 3 `EXCLUDE` · `0004:703-757`; `tipo_reserva` enum · `0004:67-69` | No existe el concepto | `servicio_bloqueos.py:233-290` inserta en el mismo libro | 🟢 |
| 2.2 | Una reserva declara exactamente un recurso (sin `NULL` ambiguo) | `ck_reserva_un_recurso` · `0004:729-733` | n/a | — | 🟢 (cierra el hueco clásico de `EXCLUDE` con columnas `NULL`) |
| 2.3 | Ventana finita y no vacía | `ck_reserva_ventana` · `0004:734-738` + `fn_reserva_validar` · `0004:1658-1661` | n/a | — | 🟢 |
| 2.4 | Toda reserva no-viaje tiene motivo | `ck_reserva_motivo` · `0004:740` | n/a | — | 🟢 |
| 2.5 | Cancelación trazable, sin borrado | `cancelado_motivo/por/en` · `0006:9-12` + `fn_reserva_no_borrar` · `0004:1692-1700` | n/a | `servicio_bloqueos.py:365-390` | 🟢 (la desactivación sigue siendo libre: ver 1.5) |
| 2.6 | Una reserva de viaje coincide con los recursos del viaje | `fn_reserva_validar` · `0004:1663-1680` (solo si `activa`) | n/a | — | 🟢 |
| 2.7 | Consulta de disponibilidad sin TOCTOU | `pg_advisory_xact_lock(hashtextextended(clave))` en orden determinista · `servicio_disponibilidad.py:1397-1409`; `EXCLUDE` como árbitro final | `SELECT` sin lock · `viajes.py:99-115` | `confirmar_asignacion` · `servicio_disponibilidad.py:1411-1572` | núcleo 🟢 / legacy 🔴 |

---

## 3. Documentos y vencimientos

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 3.1 | Un solo documento vigente por (recurso, tipo) | `uq_doc_{tracto,rampla,chofer}_vigente` parciales · `0004:362-370` + `fn_documento_vigente_unico` · `0004:1704-1741` | No existe tabla de documentos | Trigger `trg_documentos_vigente` · `0004:1802-1803` | 🟢 (la unicidad parcial es la defensa ante inserciones concurrentes) |
| 3.2 | Los documentos no se borran, se versionan | `fn_documento_no_borrar` · `0004:1743-1751` + `trg_documentos_no_delete` · `0004:1804-1805` | n/a | — | 🟢 |
| 3.3 | Un documento vencido o faltante bloquea la asignación | `validar_documentos_recurso` · `0004:1019-1104` invocado desde `fn_viaje_validar` · `0004:1281-1292` y, desde `0015`, desde `fn_viaje_documentos` para **todo viaje con los tres recursos** · `0015:247-310` | Ninguno: `vencimiento_*` son columnas `date` sueltas · `0001:66,79,90` | Trigger `trg_viajes_05_documentos` · `0015:312-315` | núcleo 🟢 DDL / legacy 🔴 |
| 3.4 | Documento con un solo recurso y fechas coherentes | `ck_doc_un_solo_recurso` · `0004:354-358`, `ck_doc_fechas` · `0004:359` | n/a | — | 🟢 |
| 3.5 | Requisitos documentales configurables por empresa | `exigir_soap`, `exigir_seguro_carga`, `exigir_curso_carga_peligrosa` · `0004:122-124` usados en `0004:1047-1074` | n/a | — | 🟢 |
| 3.6 | `exigir_oc` (empresa) y `exige_oc` (cliente) obligan a pedir OC | Columnas existen · `0004:125`, `0004:172` | n/a | **Nadie las lee**: `grep -rn "exigir_oc\|exige_oc" backend/app/nucleo/servicio_*.py backend/app/nucleo/politicas.py backend/app/nucleo/api_*.py` → 0 resultados | 🔴 (configuración muerta) |
| 3.7 | Integridad del archivo del documento (hash) | `hash_sha256 char(64)` · `0004:339` sin `CHECK` de formato ni obligatoriedad | n/a | — | 🟡 |

---

## 4. OC y tarifas

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 4.1 | La OC no se sobreconsume | `ck_oc_consumo` · `0004:453` + `fn_oc_recalcular` con `SELECT ... FOR UPDATE` de la OC · `0004:1550-1597` (revalidación `1580-1584`) + `fn_viaje_oc` AFTER · `0004:1599-1618` | No existe OC | Trigger `trg_viajes_80_oc` · `0004:1850-1851` | 🟢 (el `FOR UPDATE` de la fila OC serializa escritores concurrentes) |
| 4.2 | El consumo no se cuenta dos veces al reasignar | `0004:1361-1370` (resta el monto previo) + recálculo por suma · `0004:1574-1578` | n/a | — | 🟢 (idempotente por construcción: suma, no incremento) |
| 4.3 | Una OC no puede pertenecer a otro cliente/empresa | FK compuesta `fk_oc_cliente` · `0004:449-450` + `0004:1337-1340` | FK simple · `0001:130` | — | 🟢 |
| 4.4 | Vigencia de OC y tarifa válidas al asignar y al facturar | `0004:1315-1320`, `0004:1345-1358`, `0009:122-126` | Ninguno | — | 🟢 |
| 4.5 | Snapshot de tarifa inmutable tras el despacho | `fn_viaje_ventana` · `0004:966-993` + congelamiento · `0004:1478-1481` | Ninguno | — | 🟢 |
| 4.6 | El sobregiro de OC requiere solicitud y aprobación | `ck_oc_sobregiro_estado`, `ck_oc_sobregiro_pendiente` · `0005:61-68` | n/a | — | 🟡 `sobregiro_autorizado` (el monto que habilita el consumo, `0004:431`) puede subirse sin pasar por el flujo: no hay trigger que lo ate a `sobregiro_estado='aprobado'` |
| 4.7 | Las tarifas no se borran (se desactivan) | `activo boolean` · `0004:401`, sin trigger `no_delete` | n/a | — | 🔴 `DELETE` físico permitido si no hay líneas de OC que la referencien (`fk_ocl_tarifa` es `restrict`, `0004:481-482`) |
| 4.8 | El crédito autorizado del cliente limita el riesgo | `credito_autorizado` · `0004:171` | n/a | **Nadie la lee**: `grep -rn "credito_autorizado" backend/app/nucleo/servicio_*.py` → 0 resultados | 🔴 (columna decorativa) |

---

## 5. POD

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 5.1 | Un POD por viaje | `unique (viaje_id)` · `0009:29` | No existe POD en legacy | — | 🟢 |
| 5.2 | El POD no se borra | `fn_pod_no_borrar` · `0009:48-59` + `revoke delete` · `0009:147` | n/a | — | 🟢 |
| 5.3 | Sin POD no se factura | `fn_viaje_facturacion` · `0009:80-87` (reemplaza la de `0004`) | No hay gate | `trg_viajes_15_facturacion` · `0004:1836-1837` | 🟢 |
| 5.4 | Firma y receptor obligatorios; `fotos` es arreglo | `ck_pod_firma`, `ck_pod_receptor`, `ck_pod_fotos` · `0009:32-35` | n/a | — | 🟢 |
| 5.5 | El POD solo se registra en estados válidos | Ninguno | n/a | `servicio_pod.py:182-186` (`ESTADOS_POD`) | 🟡 |
| 5.6 | Integridad del archivo de firma | `firma_hash char(64)` nullable, sin `CHECK` · `0009:19` | n/a | Validación de MIME/tamaño solo en servicio · `servicio_pod.py:91-98` | 🟡 |

---

## 6. Gastos y combustible

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 6.1 | Monto positivo y `iva <= monto_total`; neto derivado | `0004`→`0011:37-39,66` (`monto_neto generated`) | `monto >= 0` · `0001:118`; sin `iva`, sin neto | — | núcleo 🟢 / legacy 🟡 |
| 6.2 | Aprobación con usuario y fecha | `ck_gasto_aprobacion` · `0011:68-70`; rechazo con motivo · `0011:67` | No existe flujo de aprobación | `servicio_gastos.py:346-388` | 🟢 |
| 6.3 | La aprobación no se duplica ni se revierte en silencio | Ninguno en DB | — | `servicio_gastos.py:349-352` + `WHERE version = :version` (`371-377`) | 🟡 |
| 6.4 | Un gasto aprobado es inmutable (monto/proveedor) | Ninguno: sin trigger de protección; `service_role` tiene `UPDATE` · `0011:179` | Ninguno | — | 🔴 |
| 6.5 | No se duplica un gasto por doble envío | Sin `UNIQUE (empresa_id, viaje_id, numero_documento)` ni clave de idempotencia · `0011:29-71` | Sin restricción · `0001:114-125` | — | 🔴 |
| 6.6 | Los gastos no se borran | Sin `no_delete`; `service_role` conserva `DELETE` | `DELETE /gastos/{id}` físico · `api/routes/gastos.py:93-104` | — | 🔴 |
| 6.7 | Costo real = gastos aprobados + comisión, recalculado en DB | `fn_viaje_costos` · `0011:91-135` + `trg_gastos_costos` · `0011:154-156` | Cálculo en Python por request · `kpi_engine.metricas_viaje` (vía `viajes.py:293`) | — | núcleo 🟢 / legacy 🟡 |
| 6.8 | Precio diésel único por empresa y día | `unique (empresa_id, fecha)` · `0011:20` | n/a | — | 🟢 |

---

## 7. Rentabilidad

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 7.1 | `costo_variable_real` persistido y no negativo | `0011:86-89` + trigger | n/a | — | 🟢 |
| 7.2 | Parámetros de costo únicos por empresa y en rango | `unique` + `CHECK` · `0012:10-18` | n/a | — | 🟢 |
| 7.3 | Margen / Freight Score correctos | Sin mecanismo (no se persiste el margen) | `formula` de KPI en texto evaluada por `kpi_engine` · `0003:10`, `viajes.py:295` | Backend · `0012:5` lo declara explícitamente | 🟡 (no es un invariante de DB; su corrección exige pruebas numéricas de `negocio-finanzas`) |

---

## 8. Facturación, pagos y notas de crédito

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 8.1 | Folio único por empresa | `unique (empresa_id, numero_factura)` · `0013:30` + `siguiente_folio` atómico · `0004:498-517` | `unique (numero_sii, cliente_id)` · `0001:142` | — | núcleo 🟢 / legacy 🟡 (el folio SII es de la empresa, no del cliente: dos clientes pueden repetir folio) |
| 8.2 | `total = neto + iva` | `total generated always as (neto + iva) stored` · `0013:21` | Tres columnas independientes sin `CHECK` · `0001:132-134` | — | núcleo 🟢 / legacy 🔴 |
| 8.3 | Un viaje no se factura dos veces | `unique (empresa_id, viaje_id)` · `0013:63` | `PK (factura_id, viaje_id)` permite el mismo viaje en 2 facturas · `0001:148` | — | núcleo 🟢 / legacy 🔴 |
| 8.4 | Una factura emitida es inmutable y no se borra | **Ninguno**: sin trigger de protección; `service_role` tiene `UPDATE` · `0013:264` | `PUT` reescribe montos mientras `pendiente` · `facturas.py:174-198`; `DELETE` físico · `facturas.py:241-263` | — | 🔴 |
| 8.5 | Un pago no supera el saldo | Ninguno en DB | Ninguno | `servicio_facturacion.py:624-631` (`SELECT` de saldos + `if`, sin lock) | 🔴 (TOCTOU puro: dos pagos concurrentes pueden superar el saldo) |
| 8.6 | Registrar un pago es idempotente | Sin clave de idempotencia ni `UNIQUE` sobre `referencia` · `0013:78-98` | n/a | — | 🔴 (doble clic = doble pago) |
| 8.7 | Los pagos no se borran | Sin `no_delete`; `fn_pago_estado` recalcula el estado incluso en `DELETE` · `0013:219-222` | n/a | — | 🔴 |
| 8.8 | Una NC no supera el total de la factura | Ninguno | n/a | `servicio_facturacion.py:656-663` | 🟡 |
| 8.9 | El estado de la factura se deriva de pagos y NC | `fn_factura_estado` con `FOR UPDATE` · `0013:163-212` | Transiciones en Python · `facturas.py:212-233` | Triggers `trg_pagos_estado`, `trg_nc_estado` · `0013:245-250` | 🟢 (derivación) / 🟡 (el `estado` puede fijarse a mano: `ck_factura_estado` solo valida el dominio · `0013:35`) |
| 8.10 | Anular una factura exige motivo y auditoría | Sin endpoint, sin `CHECK` de motivo, sin `anulado_*` · `0013:10-38` | Sin motivo; revierte viajes a `finalizado` y **borra** `factura_viaje` · `facturas.py:218-228` | — | 🔴 |
| 8.11 | El vínculo factura↔viaje no se rompe después de emitir | Sin `no_delete` en `factura_viajes` · `0013:54-68` | `session.delete(fila)` al anular · `facturas.py:228` | — | 🔴 |
| 8.12 | Las facturas de otra empresa son invisibles | FK compuestas · `0013:31-34` | Sin `empresa_id` · `0001:127-143` | — | 🟢 estructural / ⚪ aislamiento (§14) |

---

## 9. Folios

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 9.1 | Generación de folio atómica, sin duplicados | `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` · `0004:509-513` | No hay generador: `numero_sii` lo escribe el usuario · `0001:129` | `fn_viaje_ventana` · `0004:943`; `servicio_facturacion.py:548-556`; `668` (NC) | 🟢 |
| 9.2 | El contador no retrocede al insertar folios históricos | `greatest(...)` · `0004:535` | n/a | `0004:944-952` | 🟢 |
| 9.3 | Folio de viaje único por empresa | `unique (empresa_id, numero_viaje)` · `0004:645` | n/a | — | 🟢 |
| 9.4 | Folio no se reutiliza tras anular | El contador no retrocede · `0004:498-517` | El usuario puede repetir `numero_sii` para otro cliente · `0001:142` | — | núcleo 🟢 / legacy 🟡 |

---

## 10. Auditoría

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 10.1 | El log es append-only (sin `UPDATE`/`DELETE`) | `fn_auditoria_inmutable` · `0004:880-892` + `revoke update, delete` · `0004:1890-1891` | No existe | Trigger BEFORE UPDATE/DELETE · `0004:890-892` | 🟢 |
| 10.2 | `TRUNCATE` también está bloqueado | **No**: el trigger es `FOR EACH ROW`, `TRUNCATE` no dispara triggers de fila · `0004:890-892` | — | — | 🟡 (mitigado porque `service_role` no recibe `TRUNCATE`; el dueño sí puede) |
| 10.3 | Cobertura de auditoría por tabla | Triggers `_audit` en: empresas, usuarios_empresa, clientes, tractos, ramplas, choferes, documentos, tarifas, OC, OC líneas, viajes, reservas, centros de costo, paradas, checklist, eventos, incidentes, docs de viaje, POD, precios diésel, gastos, config costos, facturas, factura_viajes, pagos, NC, promesas (`0004:1760-1862`, `0005:41`, `0007:57-210`, `0009:44`, `0011:23-80`, `0012:31`, `0013:48-157`) | **Ninguna** | — | 🟢 / legacy 🔴 |
| 10.4 | Tablas del núcleo **sin** auditoría | `folio_contador` (`0004:490-496`), `transiciones_viaje` (`0004:772-777`), `cutover_control` (`0014:8-15`), `auditoria` (intencional) | — | — | 🔴 (un congelamiento de cutover no deja rastro en el log) |
| 10.5 | El usuario real queda en el log | `coalesce(current_setting('nucleo.auth_id', true), 'sistema')` · `0004:872`; `set_config` por transacción · `servicio_disponibilidad.py:1386-1395` | n/a | — | 🟢 con salvedad: si el servicio olvida `set_config`, el log dice `'sistema'` sin fallar |

*Búsqueda usada:* `grep -rn "no_delete\|no_borrar" supabase/migrations/` → solo
`documentos`, `reservas_recurso`, `pod`. `grep -n "_audit" 0004/0013` para cobertura.

---

## 11. Permisos y membresía

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 11.1 | Una membresía por (empresa, usuario) | `unique (empresa_id, auth_id)` · `0004:150` | `usuarios.auth_id unique` · `0001:38`; `rol_usuario` global (sin empresa) | — | 🟢 |
| 11.2 | La empresa se resuelve en el servidor, nunca del body | n/a (decisión de servicio) | n/a | `X-Empresa-ID` + consulta de membresía · `deps.py:44-82`; esquemas de entrada no exponen `empresa_id` (solo salidas, `schemas.py:145,166,1763`) | 🟡 (servicio) |
| 11.3 | Los permisos por rol se imponen en el servidor | Ninguno en DB | `require_roles` · `api/deps.py` (usado en `viajes.py:33-34`) | `permisos.py:52-…` (`ROLES_PERMISOS`) + `requiere_permiso` | 🟡 |
| 11.4 | Una membresía apunta a un usuario de Auth existente | **No**: `auth_id uuid` sin FK · `0004:142` | `references auth.users(id)` · `0001:38` | — | 🔴 (núcleo) |
| 11.5 | Nadie se autoasigna `admin` | Ninguno en DB | Ninguno | `api_permisos.py` (servicio) | 🟡 |

---

## 12. Cutover legacy ↔ núcleo

| # | Garantía esperada | `nucleo` | legacy `public` | Validado hoy en | Veredicto |
|---|---|---|---|---|---|
| 12.1 | Con el cutover congelado, **nadie** escribe en `public` | Solo un flag: `cutover_control` · `0014:8-15`. **No hay trigger, regla ni privilegio en `public` que lo imponga** | Nada | Middleware HTTP · `main.py:36-56`; script `cutover_legacy.py:390-401` | 🔴 como garantía de DB (es una garantía de aplicación, y solo para el backend) |
| 12.2 | El chequeo del flag falla cerrado | **Falla abierto**: `except Exception: congelado = False` · `servicio_cutover.py:38-39` | — | — | 🔴 |
| 12.3 | El flag se aplica de inmediato | Caché de 5 s · `servicio_cutover.py:17-18,25-26` | — | `invalidar_cache()` solo en el proceso que escribe · `servicio_cutover.py:44-46` | 🟡 (hasta 5 s de escritura legacy tras congelar; en multi-worker, más) |
| 12.4 | La migración de cutover deja los viajes asignados | **No**: migra `confirmado` con `tracto_id`, `rampla_id` y `chofer_id` en `NULL` (`cutover_legacy.py:6-13,378-401`), así que **no crea reservas** y el viaje queda sin recursos hasta que despacho los asigne. Es intencional (el legacy no tiene los documentos que exige `0015`), no un fallo | — | Reasignación manual post-cutover | 🔴 como garantía: el script no asigna; el `23514` de `0015` ya **no** se dispara porque no inserta recursos (D-05) |
| 12.5 | El cutover es reversible | `descongelar` · `servicio_cutover.py:123-140`; los viajes migrados quedan en `nucleo` (no se borran) | — | — | 🟡 (reversible como flag; la duplicación de viajes migrados no se deshace) |

---

## 13. Garantías introducidas por `0015`–`0019`

> **Estado:** el DDL **existe en disco**, pero **no se sabe si está aplicado**
> (`catalogo-migraciones.md` §0-§2: `0015`–`0019` sin seguimiento en git). Todo 🟢
> de esta sección significa "el mecanismo está escrito y lo leí", no "está en
> vigor". Ninguna de estas garantías tiene prueba **ejecutada**: los archivos de
> `supabase/tests/` están escritos y su propio `README.md:1-6` declara que no se
> corrieron.

| # | Garantía esperada | Mecanismo · `archivo:línea` | Qué **no** cubre | Prueba que la respalda |
|---|---|---|---|---|
| 13.1 | **Todo viaje con tracto, rampla y chofer ocupa el libro de ocupación**, cualquiera sea su estado; `anulado` libera | `fn_viaje_reservas()` reescrita · `0015:183-245`; dispara por `trg_viajes_70_reservas` (`0004:1848`); backfill de viajes existentes · `0015:318-471` | Recursos **parciales** (decisión explícita: no ocupan, `0015:30-35`); `public.viajes` (RA-02); reserva desactivable a mano (INV-D05, sigue 🔴) | `supabase/tests/0015_01_confirmado_ocupa.sql` + `0015_02_concurrencia_rampla.py` (2 conexiones) — **escritas, no ejecutadas** |
| 13.2 | **Todo viaje con los tres recursos valida documentos** de tracto, rampla y chofer, sea cual sea su estado | `fn_viaje_documentos()` · `0015:247-310`; trigger `trg_viajes_05_documentos` · `0015:312-315`; reusa `validar_documentos_recurso` · `0004:1019-1104` | Recursos parciales; viaje ya despachado que solo cambia de estado (excepción heredada de `0004:1128-1138`); `public` | `supabase/tests/0015_03_confirmado_valida_documentos.sql` — escrita, no ejecutada |
| 13.3 | **Solo la clase A5 es asignable**; clase ausente también bloquea | `fn_viaje_licencia_a5()` · `0016:193-251`; trigger `trg_viajes_03_licencia_a5` (previo a documentos en el orden alfabético) · `0016:254-257`; `23514` | Degradación posterior: cambiar `choferes.licencia_clase` a A3 **no** invalida viajes ya asignados; no hay `CHECK` sobre el dominio de la columna (`0004:296`); `public` | `supabase/tests/0016_01_licencia_clase_no_a5.sql` — escrita, no ejecutada |
| 13.4 | **La licencia debe estar vigente hasta el fin efectivo del viaje** (bloqueante, ya existente en `0004`) | `validar_documentos_recurso` · `0004:1019-1104`, invocado por `fn_viaje_validar` (`0004:1281-1292`) y desde `0015` para todo viaje con 3 recursos | Documentos que vencen **durante** el viaje tras el despacho (excepción operativa); `public` | `supabase/tests/0016_03_licencia_vencida_bloquea.sql` — escrita, no ejecutada |
| 13.5 | **Licencia a ≤14 días es aviso, no bloqueo** | `empresas.dias_alerta_documentos` default 30→**14** · `0016:182-186`; el aviso vive en el servicio (`politicas.py`), no en la base | No impone nada: es notificación por diseño. No reescribe filas existentes (las creadas antes conservan 30) | `supabase/tests/0016_02_licencia_por_vencer_no_bloquea.sql` — escrita, no ejecutada |
| 13.6 | **Un chofer nuevo sin porcentaje explícito devenga 10 %** y los choferes TEI en 0 quedan alineados | default `0.10` · `0017:47-49`; `UPDATE` acotado a TEI activos · `0019:44-66` | Filas de otras empresas; choferes inactivos o de baja; `public.choferes.porcentaje_produccion` (SEC-003); no hay **constraint** que obligue a usar el 10 % en el cálculo | **Sin cobertura**: no hay prueba de 0017/0019 en `supabase/tests/`; el informe `qa/2026-10-29-r01-r02` solo lo menciona como ejercicio indirecto |

Notas que cambian la lectura de filas anteriores:

1. **`0015` no reemplaza a `fn_viaje_validar`.** Este sigue validando capacidad,
   tarifa, OC y documentos para los estados operativos (`0004:1124-1126`);
   `0015` agrega una puerta **anterior** (trigger `05` < `10`) que cubre los
   estados que `fn_viaje_validar` salta. En estados operativos los documentos se
   validan dos veces: es redundante, no contradictorio.
2. **`0015` no agrega `EXCLUDE`.** Las tres restricciones de solape siguen siendo
   las de `0004:744-757` sobre `reservas_recurso`. Lo que cambia es **qué llega al
   libro**, no cómo se detecta el solape.
3. **`0016` no toca la validación documental de `0004`.** Solo agrega la clase y
   el default de aviso. El margen de bloqueo sigue siendo
   `empresas.dias_margen_documentos` (`0004:118`), que **no** es la columna que
   `0016` cambia (`dias_alerta_documentos`, `0004:120`). Confundirlas cambia la
   regla.
4. **`0018` no es una garantía.** Es una carga de datos con procedencia declarada
   por el dueño y **no contrastada con la licencia física** (`0018:16-19`); si una
   licencia real dice otra clase, el dato queda mal y la base no lo detecta.

### 13.1 `nucleo` vs legacy `public`: qué cambió con `0015`–`0019`

| Tema | `nucleo` (DDL) | legacy `public` | Cambio respecto de la versión de alcance `0014` |
|---|---|---|---|
| Solape de tracto/rampla/chofer | 3 `EXCLUDE` en `reservas_recurso` · `0004:744-757`; desde `0015`, **todo** viaje con 3 recursos entra al libro | **Nada**: `viajes` sin `EXCLUDE`; valida con `SELECT` en Python · `0001:97-112`, `viajes.py:99-115` | **RA-02 sigue abierto.** `0015` mejora el núcleo, no la convivencia: el legacy no escribe en `reservas_recurso` |
| Documentos al asignar | `fn_viaje_documentos` (0015) + `fn_viaje_validar` (0004) | Columnas `date` sueltas, sin gate · `0001:66,79,90` | Antes el hueco era `confirmado`; cerrado en DDL por `0015` |
| Licencia del chofer | `fn_viaje_licencia_a5` (0016) | Sin concepto de clase de licencia | Nuevo bloqueo en núcleo; legacy sin cambio |
| Comisión | default 10 % (0017) + filas TEI (0019) | `porcentaje_produccion` en `public.choferes`, fuente de la nómina legacy; SEC-003 abierto | Dos fuentes de comisión conviven: el núcleo y la nómina legacy pueden divergir |
| Aislamiento por empresa | RLS habilitado, **cero políticas**; `0015`–`0019` **no agregan ninguna** (`grep -n "create policy" supabase/migrations/*.sql` → solo `0001:284`) | Sin `empresa_id` | Sin cambio: RA-03 sigue abierto |
| Dinero (pagos, facturas, gastos) | Sin protectores: `0015`–`0019` no tocan `fn_gasto_*`, `fn_pago_*`, `fn_factura_*` (verificado por `grep`) | Sin cambios | Sin cambio: las garantías 6.x y 8.x siguen como estaban |

---

## 14. Sección multiempresa — qué falta para que `nucleo` sea aislamiento real (RA-03)

### 14.1 Lo que existe hoy (verificado en DDL)

| Elemento | Evidencia | Qué implica realmente |
|---|---|---|
| `empresa_id` en todas las tablas de dominio | `0004:160,193,237,284,328,379,423,544,705`, `0007`, `0009`, `0011`, `0013` | El dato está modelado por tenant |
| FKs compuestas `(empresa_id, id)` en la mayoría de relaciones | `0004:348-353,409-410,449-450,479-483,646-657,721-726`, `0007:41-42,82-83,113-114,158-159,199-200`, `0009:30-31`, `0011:59-60`, `0013:31-34,64-67` | Un UUID adivinado de otra empresa **sí** es rechazado por FK en esas relaciones |
| Excepción: `reservas_recurso → viajes` | `fk_reserva_viaje` es solo sobre `viaje_id` · `0004:727-728` | Único enlace sin FK compuesta; lo cubre el trigger `fn_reserva_validar` (`0004:1669-1676`) **solo si `activa`** |
| RLS **habilitado** en 19 tablas | `0004:1867-1881`, `0005:94`, `0007:257-261`, `0009:141`, `0011:172-173`, `0012:34`, `0013:255-259`, `0014:21` | Habilitar sin políticas = **denegar todo** a roles no privilegiados… y nada a los privilegiados |
| Políticas RLS | **Una sola en todo el repo**: `public.usuarios` · `0001:284-285`. En `nucleo`: **cero** | No hay aislamiento declarado |
| `FORCE ROW LEVEL SECURITY` | `grep -rn "force row level security" supabase/migrations/` → 0 | El dueño de las tablas (y `service_role` por `BYPASSRLS`) se salta RLS |
| Grants | `grant select, insert, update on all tables in schema nucleo to service_role` · `0004:1886-1888` y por tabla en cada migración | `service_role` puede leer y escribir **todas** las empresas; `auditoria` y `viaje_eventos` solo `select, insert` (`0004:1890-1891`, `0007:268-269`) |
| Exposición PostgREST | `supabase/config.toml:8`: `schemas = ["public", "graphql_public"]` | En **local**, `nucleo` no está expuesto por Data API (la anon key no lo alcanza). En el proyecto cloud **no verificado** ⚪ |
| Rol del backend | `backend/.env.example:15` plantilla `postgresql+psycopg://postgres.<ref>:…` | El rol **dueño** del esquema ⇒ RLS no aplica. Valor real en `.env` **no leído** (prohibido). ⚪ |

### 14.2 Qué falta (en orden de dependencia)

1. **Políticas explícitas** `USING` + `WITH CHECK` por tabla y por operación
   (`SELECT/INSERT/UPDATE/DELETE`), con defecto seguro: sin contexto ⇒ 0 filas.
   Ojo con la recursión: una política sobre `nucleo.usuarios_empresa` que consulte
   `usuarios_empresa` se llama a sí misma. El patrón correcto es una función
   `STABLE SECURITY DEFINER` (p. ej. `nucleo.empresas_del_usuario()`) que devuelva
   los `empresa_id` del `auth.uid()` actual, y políticas que la usen.
2. **Contexto por transacción**: hoy el backend solo fija `nucleo.auth_id`
   (`servicio_disponibilidad.py:1386-1395`) y **nunca** fija un `empresa_id`.
   Para RLS hace falta `SET LOCAL nucleo.empresa_id` (o `request.jwt.claims`) en
   cada request, incluida la lectura. Con pooler en modo transacción esto debe
   **demostrarse**, no suponerse.
3. **Un rol de aplicación distinto del dueño**, sin `BYPASSRLS`, con `GRANT`
   mínimo (nada de `ALL TABLES`). Sin este paso, las políticas son decorativas:
   el rol actual las ignora.
4. **`FORCE ROW LEVEL SECURITY`** en las tablas de dominio, para que ni el dueño
   las evada (o, alternativamente, un dueño distinto del rol de la aplicación).
5. **Cerrar los huecos estructurales**: FK compuesta en `reservas_recurso`
   (`0004:727`), FK de `usuarios_empresa.auth_id → auth.users(id)`
   (`0004:142`), y `empresa_id` en `public` (no existe: `0001` completo).
6. **Pruebas con el rol real**: dos empresas, dos usuarios, y un intento de leer/
   escribir el `empresa_id` de la otra. Con `service_role` o `postgres` la prueba
   **no vale** (`AGENTS.md` §8, `database-safety` §5).

### 14.3 Lo que NO se puede afirmar hoy (RA-03 se mantiene abierto)

- ❌ "`nucleo` está aislado por empresa". **No**: cero políticas en `nucleo`.
- ❌ "RLS protege aunque el backend falle". **No**: el rol de conexión es
  probablemente el dueño (`postgres.<ref>`) o `service_role` (BYPASSRLS).
  Confirmarlo exige `SELECT current_user, usesuper, …` contra la base ⚪.
- ❌ "El legacy es single-tenant y por eso no importa". El legacy **no tiene**
  `empresa_id` (`0001` completo): si mañana entra una segunda empresa por el
  legacy, no hay dónde ponerla ni cómo filtrarla.
- ❌ "La anon key no puede tocar nada". `public` sí está expuesto por PostgREST
  (`config.toml:8`). Las tablas de `public` tienen RLS sin políticas (deny), pero
  **`public._migraciones` se crea sin RLS** (`0002:6-9`): queda fuera de esa
  defensa. Clasificar con `auditor-seguridad` (RA-12), no aquí.
- ⚪ No se verificó el rol efectivo, ni el comportamiento con el pooler, ni la
  configuración del proyecto cloud.

---

## 15. Hallazgos estructurales que no son de un dominio en particular

### 15.1 Deriva modelo SQLModel ↔ DDL (reportar, no "arreglar")

| Objeto | Modelo declara | DDL real | Consecuencia si alguien usa `create_all()` |
|---|---|---|---|
| `nucleo.reservas_recurso` | Sin `EXCLUDE`, sin `ck_reserva_un_recurso`, sin `uq_reserva_viaje_recurso_activa` · `models.py:1280-1323` | 3 `EXCLUDE` + 4 `CHECK` + índice único parcial · `0004:729-761` | Se pierde **toda** la garantía de disponibilidad |
| `nucleo.clientes` | `UniqueConstraint("empresa_id","rut")` · `models.py:260` | Índice único funcional `upper(regexp_replace(rut,'[^0-9K]','','g'))` · `0004:184-185` | `12.345.678-9` y `123456789` pasarían como RUT distintos |
| `nucleo.empresas` | Sin `unique(codigo)`; `CHECK` llamado `ck_empresa_buffer` · `models.py:200-202` | `codigo text not null unique` · `0004:104`; el `CHECK` de buffer es inline y queda con nombre autogenerado · `0004:116-117` | Códigos de empresa duplicados |
| `nucleo.auditoria` | `id BigInteger autoincrement` · `models.py:1346-1349` | `generated always as identity` · `0004:814` | Semántica distinta de secuencia |
| `public.facturas` | Sin `unique` · `models/__init__.py:173-189` | `unique (numero_sii, cliente_id)` · `0001:142` | Duplicados de folio SII |
| `public.viajes` | Sin `CHECK` de fechas · `models/__init__.py:139-155` | `fecha_fin` sin `CHECK (>= fecha_inicio)` · `0001:99-100` | Fechas invertidas |

`create_all()` está prohibido como sustituto de migraciones (`AGENTS.md` §8); esta
tabla existe para que nadie lo intente "porque el modelo ya lo declara".

### 15.2 Mapeo SQLSTATE → HTTP del backend (handoff)

Verificado en `backend/app/nucleo/errores.py`:

| SQLSTATE | Mapeo real | Mapeo esperado por `AGENTS.md` §8 | Estado |
|---|---|---|---|
| `23P01` (exclusion) | `ConflictoDisponibilidad` → **409** · `errores.py:140-147` | 409 | ✅ |
| `23505` (unique) | `RegistroDuplicado` → **409** · `errores.py:149-163` | 409 | ✅ |
| `23514` (check) | `ReglaNegocioViolada` → **409** · `errores.py:165-169` | 422 | ⚠️ discrepancia de contrato |
| `23503` (FK) | `DatosInvalidos` → **422** · `errores.py:177-181` | — | ✅ razonable |
| `23502` (not null) | **Sin rama** ⇒ cae al default `ErrorPersistencia` → **500** · `errores.py:183-186` | 422 | ❌ |
| `40001`/`40P01` | `ConflictoConcurrencia` → 409 · `errores.py:171-175` | 409 | ✅ |

Esto es handoff para `backend`, no un cambio de `datos`.

---

## 16. Resumen cuantitativo (para no perderse)

83 filas de garantía (§1–§12), contadas con `awk`/`python` sobre la última
columna de cada fila (no a ojo) y **recontadas el 2026-10-29** tras las
correcciones de 1.4, 1.7, 3.3 y 12.4 (los veredictos cambiaron, no el número de
filas):

| Veredicto de la fila | Filas |
|---|---|
| 🟢 solo (mecanismo en DB, sin hueco declarado en esa fila) | 35 |
| 🟡 solo (vive en servicio/UI, o decisión de negocio pendiente) | 13 |
| 🔴 solo (ausente en `nucleo` y en legacy) | 19 |
| 🟢 + 🔴 (núcleo garantizado, legacy roto) | 10 |
| 🟢 + 🟡 (núcleo garantizado, legacy parcial) | 6 |
| **Total** | **83** |

De las 51 filas que mencionan 🟢, **16 declaran un hueco en el otro esquema**
(10 con legacy 🔴, 6 con legacy 🟡): el núcleo está blindado, la convivencia no.

§13 agrega **6 filas** de garantía con mecanismo escrito en `0015`–`0019`: 4 son
🟢 de DDL **sin aplicar ni probar** (13.1–13.4) y 2 son defaults sin `constraint`
(13.5–13.6). No se suman al total anterior porque su estado no es comparable
(mecanismo escrito, aplicación 🔴).

⚪ transversal (no verificable sin base): rol efectivo de conexión, si las
migraciones están aplicadas, concurrencia real y volumen de las tablas.

**Los 5 huecos de mayor riesgo económico/operativo** (detalle en
`invariantes.md` y `catalogo-migraciones.md`):

1. **INV-F01 / INV-F02** — pagos sin tope de saldo en DB ni idempotencia ante
   reintento (dinero directo: dos clics o un retry duplican el cobro).
2. **INV-F03 / INV-F04** — factura emitida editable y borrable; pagos y notas de
   crédito borrables (documento tributario y su respaldo).
3. **INV-D04** — cerrado **en DDL** por `0015`, pero sin aplicar ni probar; y el
   legacy sigue fuera del libro (RA-02).
4. **INV-G04 / INV-G05** — gasto aprobado editable y gasto duplicable.
5. **INV-T01** — multiempresa sin políticas ni rol sujeto a RLS (RA-03).
