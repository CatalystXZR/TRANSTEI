# Matriz de trazabilidad — invariante → mecanismo → prueba

> **Pregunta que responde:** ¿qué garantía tiene prueba, cuál no, y dónde se impone?
> **Dueño:** `qa` · **Verificado:** 2026-10-29 · **Método:** lectura de DDL, servicios y `backend/tests/*.py` (sin ejecutar integración)
> **Caduca si:** cambia una migración, se agrega/borra una prueba o se cierra un hallazgo.
> **Re-verificar con:** `ls backend/tests`, `grep -n "def test_" backend/tests/*.py`, `make test`.

---

## 0. Cómo leer esta matriz

| Columna | Significado |
|---|---|
| **ID** | `INV-*` de `docs/datos/invariantes.md`; `R-*` de `docs/negocio/catalogo-reglas.md`; `SEC-*` de `docs/seguridad/hallazgos.md`; `N.N` = fila de `docs/datos/garantias.md`; `RA-*` de `docs/estado.md` §5 |
| **Dónde se impone** | PostgreSQL (constraint/trigger/función) o Python. `sin mecanismo` = no existe en DB; puede haber validación de servicio (se cita) |
| **Prueba** | `archivo:línea` de la prueba que **puede fallar** si se viola la garantía |
| **¿Existe?** | `sí` / `no` / `escrita, no ejecutada` |
| **Cobertura** | `completa` = la prueba afirma la condición exacta; `parcial` = prueba una versión más débil (secuencial donde se exige concurrencia, servicio donde se exige DB); `sin cobertura` = no hay prueba; `escrita, no ejecutada` = existe pero nadie la corrió |

**Límite declarado:** cobertura ≠ resultado. En esta sesión solo se ejecutó
`make unit` (ver `docs/qa/linea-base.md`). Ninguna fila marcada `completa` fue
re-ejecutada aquí; el informe `docs/qa/informes/2026-10-29-r01-r02-suite-verde.md`
registra la última corrida de integración (🟡, no repetida).

**Ninguna prueba de `backend/tests/` usa dos conexiones simultáneas.** Búsqueda:
`grep -rnE "Thread|threading|asyncio|gather" backend/tests/*.py` → 0 resultados.
Toda garantía de concurrencia es, como mínimo, `parcial`.

---

## 1. Reglas de negocio (`R-`)

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| R-01 comisión = 10 % del flete **facturado** del mes | Servicio `liquidaciones.py:51-101` | `test_reglas_negocio.py:509`, `:548`; `test_flujos_criticos.py:167` | sí | completa |
| R-01 mes = fecha de emisión de la factura (ex-SEC-001) | Servicio `liquidaciones.py:66-82` | `test_reglas_negocio.py:658` | sí | completa |
| R-01 factura anulada no devenga | Servicio `liquidaciones.py:51-96` | `test_reglas_negocio.py:700` | sí | completa |
| R-01 porcentaje por defecto 10 % | `models/__init__.py:103`; `0017`; `0019` | `test_reglas_negocio.py:776` | sí | completa |
| R-01 CN-01: 1.800.000 → comisión 180.000, líquido 530.000 | Servicio `liquidaciones.py:336` | `test_flujos_criticos.py:167` (HTTP) | sí | completa |
| R-02 clase ≠ A5 bloquea (servicio) | `politicas.py:300-322` | `test_nucleo_politicas.py:155`, `:166`; `test_reglas_negocio.py:817` | sí | completa |
| R-02 clase ≠ A5 bloquea (base) | `0016_licencia_a5_bloqueante.sql` (trigger `fn_viaje_licencia_a5`) | `supabase/tests/0016_01_licencia_clase_no_a5.sql` | escrita, no ejecutada | escrita, no ejecutada |
| R-02 vencida bloquea / por vencer avisa (14 días) | `0004:1019-1104`; `politicas.py`; `empresas.dias_alerta_documentos` | `test_reglas_negocio.py:876`, `:918`, `:967`, `:994` | sí | completa |
| R-03 fecha real de término del viaje | **sin mecanismo**: `viajes.py:246` fija `date.today()` | — | no | sin cobertura |

> Las filas de `test_reglas_negocio.py` se omiten si falta `DATABASE_URL`
> (`test_reglas_negocio.py:114-120`, SEC-010). `make test` exporta
> `NUCLEO_TEST_DATABASE_URL`, **no** `DATABASE_URL`: la cobertura es real solo si
> ese módulo efectivamente corre.

## 2. Disponibilidad y ocupación

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| 1.1–1.3 solape tracto/rampla/chofer (núcleo) | `EXCLUDE` `0004:744-757` + `fn_viaje_reservas` `0004:1621-1650` | `test_nucleo_integracion.py:58` (2.ª asignación, secuencial) | sí | parcial |
| INV-D04 `confirmado` con 3 recursos ocupa el libro | `0015` (escrita; aplicación **no verificada**) | `supabase/tests/0015_01_confirmado_ocupa.sql`; `0015_02_concurrencia_rampla.py` | escrita, no ejecutada | escrita, no ejecutada |
| INV-D05 reserva de viaje no se desactiva mientras ocupa | **sin mecanismo** (`0004:1653-1690` no lo impide) | — | no | sin cobertura |
| INV-D06 reservas activas huérfanas | **sin mecanismo** (solo alerta propuesta) | — | no | sin cobertura |
| INV-D07 bloqueo/mantención vs viaje | `EXCLUDE` `0004:744-757`; `servicio_bloqueos.py:233-290` | `test_nucleo_bloqueos.py:61` (incluye `:172`) | sí | parcial (secuencial) |
| INV-DOC04 documentos vigentes en `confirmado` | `0015` (escrita; no aplicada) | `supabase/tests/0015_03_confirmado_valida_documentos.sql` | escrita, no ejecutada | escrita, no ejecutada |
| INV-DOC03 `exigir_oc`/`exige_oc` obligan | **sin mecanismo** (columnas muertas) | `test_nucleo_politicas.py:241` (solo prueba que **no** bloquea despacho) | sí | parcial |

## 3. Comercial (OC, tarifas, crédito)

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| INV-C03 sobregiro solo habilita si está aprobado | `0005:61-68` (CHECK de estado) + servicio | `test_nucleo_comercial.py:81` (`:249` 403 aprobador) | sí | parcial (no prueba `UPDATE` directo al monto) |
| INV-C04 tarifa en uso no se borra | **sin mecanismo** (FK `restrict` `0004:481-482` solo si hay referencia) | `test_nucleo_comercial.py:229` (desactivar, no borrar) | sí | parcial |
| INV-C05 crédito autorizado limita la exposición | **sin mecanismo**; nadie lee la columna | — | no | sin cobertura |
| 4.1 OC no se sobreconsume | `fn_oc_recalcular` con `FOR UPDATE` `0004:1550-1597` | `test_nucleo_comercial.py:81` (`:233`) | sí | parcial (secuencial) |
| 4.2 consumo no se duplica al reasignar | `0004:1361-1370` + recálculo por suma | — | no | sin cobertura |

## 4. Gastos

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| INV-G04 gasto aprobado inmutable | **sin mecanismo** (`service_role` con `UPDATE` `0011:179`) | — | no | sin cobertura |
| INV-G05 gasto no duplicable (doble envío) | **sin mecanismo** (sin `UNIQUE` ni clave de idempotencia) | — | no | sin cobertura |
| INV-G06 gastos no se borran | **sin mecanismo** (sin trigger `no_delete`) | — | no | sin cobertura |
| Segregación: quien registra no aprueba | Servicio `servicio_gastos.py:349-352` | `test_nucleo_gastos.py:142` (`:231`, `:245`) | sí | completa (servicio) |
| 6.7 costo real recalculado en DB | `fn_viaje_costos` `0011:91-135` | `test_nucleo_gastos.py:142` (`:260`) | sí | completa |

## 5. Facturación, pagos y notas de crédito

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| INV-F01 pagos + NC ≤ total | Servicio `servicio_facturacion.py:624-631` (sin lock ni constraint) | `test_nucleo_facturacion.py:151` (`:249`) | sí | parcial (secuencial; TOCTOU abierto) |
| INV-F02 pago idempotente ante reintento | **sin mecanismo** (sin `idempotency_key`) | — | no | sin cobertura |
| INV-F03 factura emitida inmutable | **sin mecanismo** (`service_role` con `UPDATE` `0013:264`) | — | no | sin cobertura |
| INV-F04 pagos y NC no se borran | **sin mecanismo** (`fn_pago_estado` recalcula en `DELETE` `0013:219-222`) | — | no | sin cobertura |
| INV-F05 vínculo factura↔viaje inmutable | **sin mecanismo** | — | no | sin cobertura |
| INV-F06 anulación con motivo y rastro | **sin mecanismo** (sin columnas `anulado_*`) | — | no | sin cobertura |
| INV-F07 NC no supera el saldo | Servicio `servicio_facturacion.py:656-663` (sin lock) | — (solo NC válida en `test_nucleo_facturacion.py:253`) | no | sin cobertura |
| 8.9 estado de factura derivado de pagos/NC | `fn_factura_estado` `FOR UPDATE` `0013:163-212` | `test_nucleo_facturacion.py:151` (`:245`, `:270`) | sí | completa (secuencial) |
| 9.1 folio atómico, sin duplicados | `siguiente_folio` `0004:498-517` | `test_nucleo_integracion.py:194`; `test_nucleo_facturacion.py:216` | sí | parcial (no concurrencia) |
| 5.3 sin POD no se factura | `fn_viaje_facturacion` `0009:65-87` | `test_nucleo_pod.py:254` | sí | completa |

## 6. Legacy `public`

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| INV-L01 / **RA-02** doble asignación legacy | **sin mecanismo**: `SELECT` sin lock en `viajes.py:99-115` (solo tracto) | `test_flujos_criticos.py:106` | sí | parcial (secuencial; ignora rampla, chofer y concurrencia) |
| INV-L02 folio SII único por empresa | `unique (numero_sii, cliente_id)` `0001:142` (permite repetir entre clientes) | — | no | sin cobertura |
| INV-L03 `total = neto + iva` | **sin CHECK** (`0001:132-134`) | `test_flujos_criticos.py:134` | sí | parcial (aritmética HTTP, no DB) |
| INV-L04 factura legacy no se borra | **sin mecanismo** (`DELETE` en `facturas.py:241-263`) | — | no | sin cobertura |
| INV-L05 liquidación coherente e inmutable al emitir | Cálculo Python `liquidaciones.py:336`; sin trigger | `test_flujos_criticos.py:167` | sí | parcial (coherencia; no inmutabilidad → SEC-002) |
| INV-L06 `fecha_fin >= fecha_inicio` | Solo servicio `viajes.py:91-96`; sin CHECK | `test_flujos_criticos.py:106` | sí | parcial (servicio, no DB) |

## 7. Tenant, auditoría y cutover

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| INV-T01 aislamiento multiempresa (RA-03) | **sin mecanismo**: 0 políticas RLS en `nucleo`; rol efectivo no verificado | `test_nucleo_permisos.py:32` prueba la matriz de roles, **no** el aislamiento | no | sin cobertura |
| INV-T02 reserva ligada a viaje de la misma empresa | Trigger solo si `activa` `0004:1669-1676`; FK simple `0004:727-728` | — | no | sin cobertura |
| INV-T03 membresía apunta a `auth.users` | **sin FK** `0004:142` | — | no | sin cobertura |
| INV-T04 / INV-X01 / **RA-04** cutover fail-closed | Middleware `main.py:36-56`; **fail-open** `servicio_cutover.py:38-39`; sin trigger en `public` | `test_nucleo_cutover.py:26` (solo roundtrip del flag) | sí | parcial |
| INV-A01 `auditoria` no admite `TRUNCATE` | **sin mecanismo** (trigger `FOR EACH ROW` `0004:880-892`) | — | no | sin cobertura |
| INV-A02 cambios de cutover auditados | **sin trigger** `_audit` en `cutover_control` `0014:8-15` | — | no | sin cobertura |
| 10.1 log append-only (`UPDATE`/`DELETE`) | `fn_auditoria_inmutable` `0004:880-892` | `test_nucleo_expediente.py:260` (solo `viaje_eventos`); `test_nucleo_permisos.py:71` (lectura) | sí | parcial |
| 11.3 permisos por rol en servidor | `permisos.py:150-160` | `test_nucleo_permisos.py:32` | sí | completa (unitaria) |
| 11.2 empresa desde `X-Empresa-ID`, nunca del body | `deps.py:44-82` | `test_flujos_criticos.py:84`, `:90` | sí | parcial (sin prueba IDOR/otra empresa) |

## 8. Hallazgos de seguridad → garantía afectada

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| SEC-001 comisión perdida por facturación tardía | Servicio `liquidaciones.py:51-96` (atribución por emisión) | `test_reglas_negocio.py:658` | sí | completa |
| SEC-002 PDF de liquidación emitida recalcula en vivo | `liquidaciones.py:515` recalcula; `:466` imprime el total almacenado | — | no | sin cobertura |
| SEC-003 doble fuente del % de comisión | `nucleo/models.py:583` vs `models/__init__.py:102` | — | no | sin cobertura |
| SEC-004 default 10 % eludible en importación CSV | `export.py:256,267` | — | no | sin cobertura |
| SEC-005 degradar clase A5 después de asignar | **sin mecanismo** (no hay trigger en `choferes`) | — | no | sin cobertura |
| SEC-006 INV-DOC04 no se cumple en `UPDATE` | Excepción de `0015:270-277` | — | no | sin cobertura |
| SEC-007 anticipos/ajustes sin idempotencia | **sin mecanismo** (`liquidaciones.py:118-145`, `:178-205`) | — | no | sin cobertura |
| SEC-008 lectura de sueldos/RUT restringida a admin/contabilidad | `liquidaciones.py:34` (`require_roles`); antes bastaba autenticarse | — | no | sin cobertura (mecanismo corregido, falta prueba 403) |
| SEC-009 `cutover_legacy.py` inoperante con 0015 | **Desactualizado**: el comentario de `0015:130-143` describe una versión anterior; el script actual migra sin recursos (`cutover_legacy.py:6-13,378-401`) | — | no | mecanismo corregido; falta prueba `--dry-run` (D-05) |
| SEC-010 tests R-01/R-02 usan `DATABASE_URL` | `test_reglas_negocio.py:114-120` | — (es el defecto de la prueba) | no | sin cobertura |
| SEC-011 E2E con aserciones que no pueden fallar | `tei.spec.ts:48-54`, `:96-100` | `frontend/e2e/tei.spec.ts` (9 escenarios) | sí | parcial |
| SEC-013 carrera en `calcular_liquidacion` → 500 | **sin manejo de 23505** `liquidaciones.py:279-290` | — | no | sin cobertura |

## 9. E2E del piloto

| ID | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| P0-01…P0-13 (`docs/qa/uat-piloto.md`) | Flujo visible completo | `frontend/e2e/tei.spec.ts:14,23,34,42,57,67,75,84,90` | escrita, no ejecutada | escrita, no ejecutada (0 ejecutados) |

---

## 10. Resumen

| Cobertura | Filas |
|---|---|
| completa | 13 |
| parcial | 16 |
| escrita, no ejecutada | 4 |
| **sin cobertura** | **31** |
| **Total** | **64** |

Comprobación reproducible (cuenta la última celda de cada fila; ignora cabeceras):

```bash
awk -F'|' '/^\|/ { c=$(NF-1); gsub(/^ +| +$/,"",c);
  if (c ~ /^completa/) C++; else if (c ~ /^parcial/) P++;
  else if (c ~ /^escrita/) E++; else if (c ~ /^sin cobertura/) S++ }
  END { printf "completa=%d parcial=%d escrita=%d sin=%d total=%d\n",
        C, P, E, S, C+P+E+S }' docs/qa/matriz-trazabilidad.md
```

---

## 11. Garantías sin cobertura (la deuda real)

**Sin ninguna prueba (31):**

- **Reglas:** R-03.
- **Dinero:** INV-F02, INV-F03, INV-F04, INV-F05, INV-F06, INV-F07, INV-G04,
  INV-G05, INV-G06, SEC-002, SEC-003, SEC-004, SEC-007, SEC-013.
- **Disponibilidad:** INV-D05, INV-D06 (además, ninguna prueba con dos conexiones
  simultáneas en `backend/tests/`).
- **Comercial:** INV-C05, 4.2.
- **Tenant y auditoría:** INV-T01, INV-T02, INV-T03, INV-A01, INV-A02.
- **Legacy:** INV-L02, INV-L04.
- **Integridad R-02/documental:** SEC-005, SEC-006.
- **Controles de prueba:** SEC-008, SEC-009, SEC-010.

**Escritas y nunca ejecutadas (4):** R-02 base (`supabase/tests/0016_01…sql`),
INV-D04 (`0015_01` + `0015_02`), INV-DOC04 (`0015_03`), E2E del piloto.

**Parciales que no deben contarse como verdes (16):** 1.1–1.3, INV-D07,
INV-DOC03, INV-C03, INV-C04, 4.1, INV-F01, 9.1, INV-L01/RA-02, INV-L03,
INV-L05, INV-L06, INV-T04/RA-04, 10.1, 11.2, SEC-011. Motivos recurrentes:
(a) prueba secuencial donde se exige concurrencia; (b) validación de servicio
donde el invariante exige DB; (c) aserción que admite más de un resultado.

**Nota sobre las cifras:** `docs/datos/invariantes.md:63` declara 31 invariantes
sin mecanismo en DB. Esta matriz cubre las filas `INV-` de ese catálogo (con
`INV-X01` fusionado en la fila de `INV-T04`) más `INV-DOC04` de la adenda §10, y
añade reglas, garantías y hallazgos. Un invariante con mecanismo no implica
prueba: `INV-D07` lo tiene y sigue parcial.

---

## 12. Qué haría falta para mover cada fila (orden de valor)

1. **Concurrencia real (2 conexiones):** pagos (`INV-F01`), OC (`4.1`), reservas
   (`1.1–1.3`, `INV-D04`), folio (`9.1`). Es la deuda transversal.
2. **Inmutabilidad y borrado:** `INV-F03`–`F06`, `INV-G04`–`G06`, `INV-L04`,
   `INV-A01`. Requieren migración nueva: el plan de `docs/datos/invariantes.md`
   las numeraba `0018`/`0019`/`0021`, pero esos números ya se usaron para A5 y
   comisión (`0018`, `0019`); la numeración debe reasignarse. Sin mecanismo, la
   prueba roja es el entregable.
3. **Idempotencia:** `INV-F02`, `INV-G05`, `SEC-007`. Probar el doble envío con la
   misma clave y contar 1 fila.
4. **Tenant:** `INV-T01`–`T03`. Exige rol real sin `BYPASSRLS` y dos empresas.
   Con el rol actual la prueba **no vale** (`docs/datos/garantias.md` §14.2).
5. **Cutover:** `RA-04`/`INV-T04`/`X01` y `SEC-009`. Probar el `except` y una
   escritura por `psql` con el flag congelado.
6. **SEC-002:** emitir, agregar un bono, regenerar el PDF y comparar líneas vs
   total almacenado. Hoy el defecto está confirmado por lectura
   (`liquidaciones.py:515` vs `:466`).

---

## 13. Módulo agente WhatsApp — O1.2 (0021) y O1.3 (0021+0022, rollback)

> **Verificado:** 2026-10-30 en `tei_test` (PostgreSQL 17.11). O1.2: `0021`
> aplicada. O1.3: `0022` aplicada y ciclo completo de rollback (`0022_99` →
> `0021_99`) y re-aplicación (`0021` → `0022`). Informes:
> `docs/qa/informes/2026-10-31-o1.2-invariantes-agente.md` y
> `docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md`.
> **Roles:** `0021_01`/concurrencia con `postgres` (BYPASSRLS), RLS con `tei_app`,
> mutación y rollback con `supabase_admin`.

| Invariante | Dónde se impone | Prueba (`archivo:línea`) | ¿Existe? | Cobertura |
|---|---|---|---|---|
| R-04 contador atómico por (empresa, cliente), sin duplicados ni saltos | `INSERT ... ON CONFLICT DO UPDATE` `supabase/migrations/0021:628-632` | `supabase/tests/0021_02_concurrencia_id_comercial.py:115` (C1, 8 conexiones + barrera) | sí | completa (mutada: función no atómica ⇒ falla) |
| R-04 un `ROLLBACK` no consume número | transacción del contador | `0021_02_concurrencia_id_comercial.py:240` (C1b) | sí | completa |
| R-04 árbitro final `(empresa, cliente, código)` | `uq_viajes_id_comercial` `0021:555-557` | `supabase/tests/0021_04_mutacion.sql:222` (M4); base `0021_01_smoke.sql:675` (C11G) | sí | completa (mutada) |
| R-04 formato `PREFIJO-00001` | `ck_viaje_id_comercial_flete` `0021:551-553` | `0021_01_smoke.sql:665` (C11E) | sí | completa (smoke) |
| **D3** contador comercial monótono no decreciente | `trg_contador_10_no_retrocede` + `fn_contador_no_retrocede` `supabase/migrations/0022:284-307` | `0021_04_mutacion.sql:305` (M6); `0021_01_smoke.sql:648` (C11D, `greatest`) | sí | completa (mutada: sin trigger 500→0 se acepta) |
| **D2** ID comercial inmutable una vez asignado (incluido el paso a NULL); asignar desde NULL sigue permitido | `trg_viajes_10_id_comercial_inmutable` + `fn_viaje_id_comercial_inmutable` `0022:315-341` | `0021_01_smoke.sql:684` (C11H desasignar ⇒ 23514) y `:690` (C11H2 NULL ⇒ valor permitido); `0021_04_mutacion.sql:341` (M7) | sí | completa (mutada: sin trigger QAM-00001→QAM-00002 se acepta) |
| **D9** tope de 5 dígitos fail-closed (99999) | `nucleo.obtener_siguiente_id_comercial_flete` `0022:401-444` | `0021_04_mutacion.sql:449` (M9); rollback `0022_99_rollback.sql:60-91` restaura el comportamiento previo (`SQM-10000`, verificado) | sí | completa (mutada: sin tope emite `SQM-10000` y deja 100000) |
| **D5** máquina de estados de `hoja_ruta` (propuesto→solicitud_creada→cargado/rechazado; terminales) + `payload` inmutable | `trg_hoja_ruta_10_transicion` + `fn_hoja_ruta_transicion` `0022:349-392` | `0021_01_smoke.sql:544-596` (C10A-F; C10E recorre la ruta legal); `0021_04_mutacion.sql:389` (M8) | sí | completa (mutada: sin trigger se aceptan transición ilegal y cambio de payload) |
| D-10 decisión definitiva de la solicitud | `trg_solicitudes_10_transicion` `0021:458-483` | `0021_02_concurrencia_id_comercial.py:325` (C2a/C2b, 2 conexiones); `0021_04_mutacion.sql:125` (M2); `0021_01_smoke.sql:489` (C9G/H) | sí | completa (mutada) |
| D-10 idempotencia de creación (`clave_idempotencia`) | `uq_solicitud_idempotencia` `0021:437-438` | `0021_01_smoke.sql:443` (C9B) | sí | completa (smoke) |
| Webhook idempotente por `wa_message_id` | `uq_mensaje_wa_message_id` `0021:346-347` | `0021_02_concurrencia_id_comercial.py:424` (C3, 2 conexiones); `0021_04_mutacion.sql:80` (M1) | sí | completa (mutada) |
| Mensaje pertenece a la conversación de su contacto | `fn_mensaje_validar` `0021:361-379` | `0021_01_smoke.sql:408` (C8) | sí | completa (smoke) |
| Auditoría de consultas append-only | triggers `0021:729-735` + REVOKE UPDATE/DELETE `0021:863-864` | `0021_03_rls_tei_app.sql:421` (rol real, 42501); `0021_04_mutacion.sql:171` (M3); `0021_01_smoke.sql:722` (postgres, 23514) | sí | completa (mutada) |
| RLS multiempresa de las 8 tablas (fail-closed, WITH CHECK, FORCE) | políticas + FORCE `0021:799-850` | `0021_03_rls_tei_app.sql:217` (A/B/C/E) y `0021_04_mutacion.sql:264` (M5) | sí | completa con `tei_app` (una sesión; 2 conexiones del patrón: `0020_02`) |
| ACL deny-by-default por ausencia de fila | **sin mecanismo de base**: gate del backend O2.2 | — | no | sin cobertura (no es DB) |
| Cierre de conversación por inactividad (15 min) | **sin mecanismo de base**: orquestador O3.5 | — | no | sin cobertura |
| OTP: emisión/expiración/revocación | base solo formato/estado `0021:215`; política D-12 en backend | `0021_01_smoke.sql:194` (solo el CHECK) | parcial | parcial (falta backend O2.3) |
| Teléfono activo único global (anti-ambigüedad de identidad) | `uq_contactos_telefono_activo` `0021:222-223` | `0021_01_smoke.sql:176` (C3F) | sí | completa |
| Una conversación activa por contacto | `uq_conversacion_activa` `0021:298-299` | `0021_01_smoke.sql:285-313` (C6A-C6E) | sí | completa (smoke) |
| Hoja de ruta: CHECKs de estado/carga y una carga por solicitud | `ck_hr_*` `0021:520-522`; `uq_hoja_ruta_carga_por_solicitud` `0021:528-529` | `0021_01_smoke.sql:544-596` (C10A-F) | sí | completa (smoke; la transición la cubre D5) |
| Contador nunca retrocede en `registrar_id_comercial_flete` | `greatest(...)` `0021:640-669` | `0021_01_smoke.sql:648` (C11D) | sí | completa (smoke) |
| RLS de `nucleo.viajes.id_comercial_flete` | hereda la política de `viajes` (0020) | — | no específica | parcial (tabla cubierta por `0020_01`) |
| **D7** rollback de 0021/0022 ejecutable y re-aplicación limpia | scripts `supabase/tests/0022_99_rollback.sql` y `0021_99_rollback.sql` (orden 0022→0021) | ejecutados 2026-10-30: 0 triggers/funciones de 0022, 0 objetos del módulo, 35 políticas, re-aplicación `0021`+`0022` limpia y 4 suites verdes | sí | completa en `tei_test`; **no probado con datos reales** (ver informe O1.3 §6) |

**Hallazgo O1.3 (reproducibilidad, no invariante):** tras re-aplicar `0021` como
`supabase_admin` (rol necesario para el índice sobre `usuarios_empresa`), el rol
`postgres` solo conserva `SELECT` (vía `pg_read_all_data`); las suites
`0021_01`/`0021_02`, documentadas para `postgres`, fallan con `42501`. El clon
previo tenía GRANTs de escritura para `postgres` que no están en `0021`.
En `tei_test` se restauraron con `GRANT ALL` sobre las 8 tablas + secuencia.
Decisión pendiente de `datos`/`orquestador`: incluirlos en `0021` o cambiar el
rol de las suites. Ver informe O1.3 §7.

**Residuo:** 0 filas en las 8 tablas del módulo tras las 4 suites; `nucleo.viajes`
conserva 220 filas. Solo creció `nucleo.auditoria` (append-only, 8519 filas al
cierre) por las transacciones commiteadas de concurrencia y M9.
