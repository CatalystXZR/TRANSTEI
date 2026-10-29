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
