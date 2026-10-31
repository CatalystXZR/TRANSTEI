# Informe — FASE 2, Ola B: APIs del núcleo para los 4 módulos sin equivalente

> **Dueño:** `backend` · **Fecha:** 2026-10-31 · **Riesgo:** ALTO (nómina,
> impuestos, configuración, tenant) · **Rama:** `main` (sin commit).
> **Alcance autorizado:** `backend/app/nucleo/**`, `backend/tests/**`,
> `docs/backend/**`. **No** se tocaron migraciones, `frontend/`, dependencias,
> secretos ni git.
> **Contrato:** [`docs/backend/contratos/ola-b-modulos-nucleo.md`](../contratos/ola-b-modulos-nucleo.md).

## Resultado

Se implementaron y probaron los endpoints del núcleo para mantenimiento (0024),
liquidaciones/anticipos/ajustes (0025), IVA débito y configuración por empresa
(0026), más el export CSV con permisos. Todos resuelven la empresa desde
`X-Empresa-ID` + membresía (`get_contexto_empresa`), declaran permiso explícito y
traducen errores de PostgreSQL a 409/422. La comisión usa
`nucleo.redondear_half_up()` (no `quantize`), la emisión es idempotente y la
imputación de anticipos está serializada por `SELECT … FOR UPDATE`.

`make unit`: **139 passed** (antes 135; +4 de esquema).
`make test`: **406 passed** (antes 388; +18: 4 de esquema y 14 nuevos).

## Evidencia

### Rutas registradas (real)

```text
$ cd backend && ../.venv/bin/python -c "from fastapi.testclient import TestClient; ..."
/api/v1/nucleo/mantenimiento/pautas                     ['get', 'post']
/api/v1/nucleo/mantenimiento/mantenimientos             ['get', 'post']
/api/v1/nucleo/mantenimiento/mantenimientos/{id}/anular ['post']
/api/v1/nucleo/mantenimiento/estado                     ['get']
/api/v1/nucleo/liquidaciones                            ['get', 'post']
/api/v1/nucleo/liquidaciones/{id}/emitir                ['post']
/api/v1/nucleo/liquidaciones/{id}/anular                ['post']
/api/v1/nucleo/anticipos                                ['get', 'post']
/api/v1/nucleo/ajustes                                  ['get', 'post']
/api/v1/nucleo/iva/resumen                              ['get']
/api/v1/nucleo/configuracion                            ['get']
/api/v1/nucleo/configuracion/{clave}                    ['get', 'put']
/api/v1/nucleo/export/liquidaciones                     ['get']
/api/v1/nucleo/export/viajes                            ['get']
/api/v1/nucleo/export/facturas                          ['get']
```

Los routers se agregan en `backend/app/nucleo/router.py:20-24` y se montan bajo
el router `/nucleo` existente en `backend/app/nucleo/api.py:25,47`; no se editó
`backend/app/api/router.py` ni ninguna ruta legacy.

### Pruebas ejecutadas

```text
$ make unit
139 passed, 2 warnings in 0.72s

$ make test
406 passed, 2 warnings in 7.92s

$ NUCLEO_TEST_DATABASE_URL=…tei_test NUCLEO_DATABASE_URL=…tei_app \
    ../.venv/bin/python -m pytest tests/test_nucleo_ola_b_modulos.py \
    tests/test_nucleo_schemas.py
25 passed, 1 warning in 0.84s
```

`backend/tests/test_nucleo_ola_b_modulos.py` cubre:

| Prueba | Qué garantiza |
|---|---|
| `test_mantenimiento_cn08_y_validaciones` (línea 276) | CN-08 (`ok/por_vencer/pendiente`), snapshot, `sin_registro`, `sin_odometro`, costo/km, xor, pauta duplicada |
| `test_mantenimiento_historico_no_se_borra…` (371) | DELETE bloqueado; anulación con motivo; el anulado no cuenta |
| `test_nomina_cn03…` (403) | CN-03 (530.000 sin anticipo / 380.000 con anticipo), emisión idempotente, inmutabilidad, anulación |
| `test_nomina_cn04_half_up_y_duplicado` (485) | CN-04: 125.001,13 (HALF_UP), no 125.001,12; duplicado 409 |
| `test_nomina_concurrencia_emision…` (526) | dos conexiones: una sola imputación y una sola emisión |
| `test_iva_solo_debito_ignora_anuladas` (584) | CN-07: débito 95.000; anuladas y mes siguiente fuera; sin crédito |
| `test_configuracion_vigencia_historial…` (618) | cierre + apertura, historial 2 filas, iva 0–100, PUT idempotente |
| `test_http_*` (665, 722, 764) | 201/200/403/422 con la matriz real de permisos |
| `test_export_neutraliza_formula_en_celda` (803) | `'=HYPERLINK…` en el CSV |

Las pruebas de integración corren con el rol real `tei_app` (sin `BYPASSRLS`) y
el listener `begin` de `app/core/database.py`, no con el rol privilegiado; las
fixtures se siembran con el rol de test, igual que el seed. Las HTTP sustituyen
`get_contexto_empresa` con `contexto_helpers.contexto_de_prueba`, pero **no**
desactivan `requiere_permiso` (el 403 se mide sobre la matriz real).

### Decisiones verificables en código

- Permisos nuevos en `backend/app/nucleo/permisos.py:48-53,96,117-121,136,148,167-168`.
- Esquemas en `backend/app/nucleo/schemas.py:1815-2056`.
- Mantenimiento: `servicio_mantenimiento.py:81` (listar), `:109` (pauta),
  `:259` (registro), `:300` (vista), `:351` (anular).
- Nómina: `servicio_nomina.py:222` (listar), `:260` (borrador), `:310` (emitir),
  `:426` (anular), `:509` (anticipo), `:582` (ajuste).
- IVA: `servicio_iva.py:53` (solo débito).
- Configuración: `servicio_configuracion.py:114,151` (catálogo + vigencia).
- Export: `servicio_export.py:33` (`_celda`), `:47` (CSV), `:71,107,161`.

## Verificado 🟢

- Rutas, permisos y contratos listados arriba; `extra="forbid"` en escrituras.
- CN-03, CN-04 (HALF_UP), CN-07 y CN-08 con salidas reales de pytest.
- Concurrencia real de emisión (dos conexiones) → una sola imputación.
- Emisión idempotente; anulación idempotente con el mismo motivo y 409 con otro.
- IVA solo débito; no se calcula crédito ni `a_pagar`.
- Configuración: cierre/apertura con el mismo instante, historial y rango 0–100.
- Export sin recálculo y con prefijo `'` para fórmulas.
- `make unit` y `make test` verdes; guard estático de "núcleo no lee `public`"
  sigue verde (se corrigieron docstrings que contenían `public.`).

## Inferido 🟡

- La comisión del núcleo replica R-01/R-05 (primera factura no anulada por
  `fecha_emision`, ventana `[inicio, fin)`, fallback a viaje `facturado/cobrado`).
  Se verificó con datos de prueba, no contra la cartera real del piloto.
- El umbral por defecto de la vista (5.000 km cuando la pauta no fija
  `alerta_km`) no se conectó a `configuracion_empresa.alerta_km_mantenimiento`:
  la deuda sigue declarada por `datos` (0024 §7.3). El endpoint lee la vista tal
  cual.

## No verificado 🔴

- **Datos reales del piloto**: no se ejecutó cutover ni se comparó la nómina
  nueva contra el legacy con producción. La paridad es funcional, no numérica
  sobre la cartera real.
- **Mutación automatizada**: las garantías de base (trigger de emisión, `CHECK`
  de costo, snapshot, `EXCLUDE` de configuración) ya están probadas por `datos`
  en `supabase/tests/0024–0026`; no se repitió el ejercicio de mutación en esta
  sesión.
- **Volumen/planes**: no hay `EXPLAIN (ANALYZE, BUFFERS)` con datos realistas.
- **Frontend**: ningún cliente consume todavía estos endpoints (Ola A retiró las
  pantallas legacy).

## Riesgos y preguntas abiertas (no inventadas)

| ID | Qué queda fuera | Destinatario |
|---|---|---|
| `P-09` | Crédito fiscal de IVA, `a_pagar`, remanente y cuadre F29 | Contador |
| `P-01`/`D-21` | Tasa vigente y autoridad de la tasa (config vs request) | Contador/dueño |
| `P-02` | AFP/salud/cesantía/impuesto/gratificación | Asesor laboral |
| `P-10`/`D-19` | Anticipos de meses cerrados, anticipo > haberes, `total_liquido < 0` | Asesor laboral/dueño |
| `P-12` | Anticipo imputado a una liquidación anulada | Negocio |
| `P-11` | Intervalos de mantención con fuente documental | Dueño/proveedor |
| `D-20` | Costo de mantención en el costo del viaje | Dueño |
| `RET-08` | ¿Mantención vencida bloquea el despacho? | Dueño |
| `P-13` | Migración de las 4 claves legacy a configuración por empresa | Dueño/arquitectura |
| — | `UNIQUE (empresa_id, chofer_id, mes)` de `0025` impide crear un documento nuevo tras anular (el trigger dice "cree un documento nuevo"). Requiere índice parcial por estado: decisión de `datos`, no se cambió | `datos` |
| — | Un anticipo creado para un mes ya liquidado queda `pendiente` y nunca se imputa (CN-05). Rechazo/arrastre depende de `D-19` | Negocio/asesor laboral |

Riesgo operativo declarado: mientras convivan las pantallas legacy, la nómina y
el mantenimiento pueden escribirse en `public` y en `nucleo` (doble escritura);
ninguna constraint lo impide hasta la Ola D.

## Compatibilidad

- No se modificó ninguna ruta legacy, tabla de `public` ni migración.
- Los endpoints nuevos usan el prefijo `/api/v1/nucleo`; no colisionan con
  `/api/v1/liquidaciones`, `/api/v1/mantenimiento`, etc.
- `nucleo.choferes.porcentaje_comision` se usa como fracción (0,10), igual que
  el default de `models.py:584-586` y `0017/0019`.

## Handoff

- **frontend**: consumir los contratos de §2–§6 del documento de contrato. No
  hay cliente previo; no se tocó `frontend/`.
- **qa**: reproducir CN-03/04/07/08 contra `tei_test` y añadir E2E cuando exista
  pantalla. Revisar el 403 de nómina para `tesorería`/`taller`.
- **auditor-seguridad**: revisar que `export/liquidaciones` exige
  `liquidaciones:leer` (SEC-008), que el tenant no sale del body y que el CSV
  neutraliza fórmulas. Confirmar el criterio de permisos de IVA (`iva:leer` para
  tesorería/auditor).
- **datos**: la deuda del umbral `alerta_km_mantenimiento` (vista con 5.000 fijo)
  y el `GRANT` de las 6 tablas nuevas al rol de test (hoy solo `tei_app`), que
  obligó a las pruebas a correr con `tei_app` + contexto RLS.

## Rollback

- Código: eliminar los 9 archivos nuevos de `backend/app/nucleo/` y las dos
  inclusiones de `api.py:25,47`; revertir el bloque agregado a `schemas.py` y
  `permisos.py`. No hay cambios de esquema ni de datos.
- Tests y docs: eliminar `test_nucleo_ola_b_modulos.py`, el bloque agregado a
  `test_nucleo_schemas.py` y los dos documentos de `docs/backend/`.
- Los endpoints no están conectados al frontend, por lo que retirarlos no rompe
  ninguna pantalla.
