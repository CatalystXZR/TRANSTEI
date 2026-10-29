# Implementación de reglas — mapa regla → código

> **Pregunta que responde:** ¿dónde se calcula cada regla y cuántas versiones existen?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-10-29 · **Método:** lectura de código y DDL
> **Caduca si:** cambia un servicio de dinero, una migración o el router.
> **Re-verificar con:** `rg -n "def _comision_chofer|def metricas_viaje|def calcular_flete|iva_porcentaje|dias_alerta" backend/app`

**Ninguna prueba se ejecutó en esta sesión** (sin shell ni base): la columna "prueba"
indica la cobertura *declarada* en el repo, no un resultado verde. Para la evidencia
de ejecución, ver `docs/qa/linea-base.md`.

## 1. Mapa principal

| Regla | Dónde se calcula | `archivo:línea` | ¿Una sola versión? | Prueba que la cubre |
|---|---|---|---|---|
| **R-01** comisión del chofer | Nómina legacy: primera factura no anulada del viaje, mes por `fecha_emision` | `backend/app/api/routes/liquidaciones.py:51-96` | **No**: 3 cálculos (§2.1) | `backend/tests/test_reglas_negocio.py:509-800`; `test_flujos_criticos.py:167` |
| **R-02** bloqueo A5 | Trigger de base + hallazgo bloqueante del servicio | `supabase/migrations/0016_licencia_a5_bloqueante.sql:193-257`; `backend/app/nucleo/politicas.py:297-322`; default 14 en `backend/app/nucleo/models.py:222` | **Sí en DB** (servicio duplica el mensaje); el comentario viejo de `0004:1272-1274` dice lo contrario | `supabase/tests/0016_01/02/03*.sql`; `test_reglas_negocio.py:16-35` |
| **R-03** fecha de término | Legacy estampa `date.today()` al finalizar; el PUT acepta `fecha_fin`; el núcleo estampa `ahora_utc()` al cerrar | `backend/app/api/routes/viajes.py:245-246,194,206-213`; `backend/app/nucleo/servicio_expediente.py:1268-1270` | **No**: dos modelos y dos relojes (§2.5) | **Sin cobertura** |
| Margen de viaje (sin `R-`) | Tres cálculos distintos: KPI, costos del núcleo y rentabilidad | `kpi_engine.py:491-524`; `servicio_gastos.py:446-494`; `servicio_rentabilidad.py:192-221` | **No** (§2.2) | `backend/tests/test_nucleo_rentabilidad.py:144` |
| Tarifa (sin `R-`) | `calcular_flete` en backend; snapshot en el trigger del viaje | `backend/app/nucleo/tarifas.py:27-86`; `servicio_disponibilidad.py:902-914`; `0004:966-993,1294-1324` | **Sí en núcleo**; el legacy no tiene tarifa, solo flete manual (`backend/app/models/__init__.py:149`) | `backend/tests/test_nucleo_tarifas.py:9-78` |
| IVA (sin `R-`) | Legacy: tasa desde `configuracion.iva_porcentaje` (default 19). Núcleo: `tasa_iva` del request (default 0,19) | `backend/app/api/routes/facturas.py:35-43`; `finanzas.py:133-153`; `kpi_engine.py:401-421`; `backend/app/nucleo/schemas.py:1543`; `servicio_facturacion.py:544` | **No**: dos fuentes (§2.3) | `backend/tests/test_flujos_criticos.py:134-154` |
| Alertas de vencimiento (sin `R-`) | Legacy: `dias_alerta_vencimientos` (30). Núcleo: `empresa.dias_alerta_documentos` (14) | `backend/app/api/routes/dashboard.py:100-140`; `kpi_engine.py:426-438`; `backend/app/nucleo/servicio_alertas.py:124-135`; `servicio_disponibilidad.py:245` | **No**: dos claves y dos defaults (§2.4) | `backend/tests/test_nucleo_alertas.py` |
| Requisito de OC (sin `R-`) | Servicio + trigger de facturación; no bloquea despacho | `backend/app/nucleo/politicas.py:374-443`; `backend/app/nucleo/servicio_facturacion.py:490-515`; `supabase/migrations/0009_pod.sql:89-93` | **Sí**: el trigger manda; el servicio anticipa el error | `test_nucleo_comercial.py:203-232`; `test_nucleo_facturacion.py:227` |
| Gate de POD (sin `R-`) | Trigger de facturación + servicio | `supabase/migrations/0009_pod.sql:80-87`; `backend/app/nucleo/servicio_facturacion.py:494-501` | **Sí** en DB; servicio duplica | `test_nucleo_pod.py:250`; `test_nucleo_facturacion.py:176` |
| Consumo de OC (sin `R-`) | Recálculo por suma de viajes, no incremento | `supabase/migrations/0004_nucleo_operacional.sql:1574-1595,1599-1617` | **Sí** | `test_nucleo_comercial.py:203-232` |
| Freight Score (sin `R-`) | Servicio de rentabilidad | `backend/app/nucleo/servicio_rentabilidad.py:43-50,210-253` | **Sí** | `test_nucleo_rentabilidad.py:144` |

## 2. Reglas con más de una implementación

### 2.1 Comisión del chofer (R-01) — tres cálculos y dos campos

| Uso | Fórmula real | Base | Evidencia |
|---|---|---|---|
| Nómina legacy | `sum(valor_flete_neto) × porcentaje_produccion` | Viajes con factura no anulada, mes por emisión | `liquidaciones.py:66-96` |
| KPI legacy | `valor_flete_neto × porcentaje_produccion` | Viajes finalizados/facturados del mes por `fecha_fin` | `kpi_engine.py:369-381` |
| Costo/margen núcleo | `monto_total_neto × porcentaje_comision` | Viaje individual, incluye recargos | `servicio_gastos.py:455-461` |

Consecuencias verificables:

1. **Dos campos para el mismo porcentaje:** `public.choferes.porcentaje_produccion`
   (`backend/app/models/__init__.py:102-105`) y
   `nucleo.choferes.porcentaje_comision` (`backend/app/nucleo/models.py:583-586`).
   Pueden discrepar; es SEC-003, pendiente de ADR.
2. **Tres bases distintas:** neto sin recargos (nómina), neto del viaje (KPI), total
   neto con recargos (costo). El dueño dijo "facturación total del mes"
   (`catalogo-reglas.md`, R-01); la base exacta es `D-01`.
3. **Dos meses distintos:** la nómina atribuye por emisión de factura
   (`liquidaciones.py:51-75`); el KPI, por fecha de fin del viaje
   (`kpi_engine.py:312-320`). Un viaje de octubre facturado en noviembre cambia de mes
   según qué número se mire.
4. **La comisión del KPI no excluye facturas anuladas** porque no consulta facturas:
   cuenta viajes en estado `facturado`. Si una factura se anula y el viaje vuelve a
   `finalizado` (`facturas.py:218-228`), el KPI deja de contarlo; si el viaje queda
   `facturado` sin factura, lo cuenta igual.

### 2.2 Margen de viaje — tres definiciones

- **KPI legacy:** `flete − gastos − comisión`, en `float`
  (`kpi_engine.py:516-523`), sin costo fijo.
- **Costos del núcleo:** `ingreso_total − (gastos_aprobados + comisión)`, en `Decimal`
  (`servicio_gastos.py:455-466`); usa `monto_total_neto` (con recargos).
- **Rentabilidad:** margen de contribución + costo fijo asignado (mensual / viajes
  estimados), tarifa piso y score (`servicio_rentabilidad.py:192-221`).

El legacy expone `/viajes/{id}/rentabilidad` con la fórmula KPI configurable
(`backend/app/api/routes/viajes.py:289-295`), mientras el núcleo expone
`/nucleo/expediente/viajes/{id}/rentabilidad` con el servicio nuevo
(`api_rentabilidad.py:62-69`). **No son intercambiables**: uno es un porcentaje de
KPI, el otro un margen con costo fijo y score.

### 2.3 IVA — dos fuentes de la tasa

- Legacy: `get_config_decimal(session, "iva_porcentaje", "19")` en tres lugares
  (`facturas.py:35-43`, `finanzas.py:133-153`, `kpi_engine.py:401-421`).
- Núcleo: `FacturaCreate.tasa_iva` con default `0.19`
  (`backend/app/nucleo/schemas.py:1543`), usado tal cual en
  `servicio_facturacion.py:544`.

Si una empresa cambia `iva_porcentaje`, el núcleo **no** lo lee. Y como la tasa llega
del request, el cliente puede enviar otra. La validez de la tasa es `P-01`.

### 2.4 Alertas de vencimiento — dos claves, dos defaults

- Legacy: `configuracion.dias_alerta_vencimientos`, default **30**
  (`dashboard.py:106`, `kpi_engine.py:427`).
- Núcleo: `empresa.dias_alerta_documentos`, default **14**
  (`models.py:222`; `servicio_alertas.py:125`; `servicio_disponibilidad.py:245`).

El mismo documento puede aparecer "por vencer" en `/dashboard` y no en `/tablero`, o
al revés, según la clave que lea cada pantalla.

### 2.5 Fecha de término (R-03) — dos relojes

- Legacy: al pasar a `finalizado`, si no hay fecha, se estampa `date.today()`
  (`viajes.py:245-246`). El `PUT /viajes/{id}` **sí** acepta `fecha_fin`
  (`schemas/viajes.py:24-26`; `viajes.py:194,206-213`), pero la pantalla solo la
  muestra (`frontend/src/app/(app)/viajes/[id]/page.tsx:257`), no la edita.
- Núcleo: `cerrar_viaje` estampa `fin_real = fin_real or ahora_utc()`
  (`servicio_expediente.py:1268-1270`); `CerrarViaje` no acepta fecha
  (`schemas.py:1162-1165`).

La API legacy permite corregir la fecha después; el flujo del núcleo, no. Que eso sea
suficiente es `D-03`.

## 3. Dónde NO hay garantía estructural

Las reglas de arriba están en migraciones de `supabase/migrations/`, pero **`HEAD` solo
contiene `0001`–`0003`** (`docs/estado.md:31`). En un clon limpio del repositorio:

| Garantía | Vive en | ¿Está en `HEAD`? |
|---|---|---|
| Bloqueo A5 | `0016:193-257` | 🔴 No |
| Gate POD + OC para facturar | `0009:80-99` | 🔴 No |
| Transiciones de viaje y documentos | `0004:779-808,1019-1104` | 🔴 No |
| Recálculo de saldo/pagos | `0013:163-211` | 🔴 No |
| Consumo de OC idempotente | `0004:1574-1617` | 🔴 No |

Consecuencia: **la regla está implementada en disco y, si las migraciones se aplicaron,
en la base local; no es reproducible desde `HEAD`**. Eso no la convierte en "decisión
pendiente", pero impide declarar la garantía como parte del producto versionado.

## 4. Handoff

- `datos`: llevar a `HEAD` las migraciones que imponen R-02, POD, OC y saldo; declarar
  en `docs/datos/invariantes.md` dónde se impone cada una y si `0016` está aplicada.
- `backend`: unificar la comisión (un campo, una base, un mes) y el IVA (una fuente);
  decidir si el KPI legacy se retira o se alinea con R-01.
- `qa`: convertir `D-01`, `D-03` y `D-05` en pruebas cuando el dueño responda; hoy
  R-03 no tiene cobertura y las pruebas de R-01/R-02 no se ejecutaron en esta sesión.
