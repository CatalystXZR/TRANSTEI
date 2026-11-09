# Métricas económicas del chat in-app — definición, fórmulas y límites

> **Pregunta que responde:** ¿qué significa exactamente cada número económico que el
> gerente o la secretaria pueden pedir por el chat, con qué campos de `nucleo` se
> calcula, qué excluye y qué no se puede afirmar?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-11-04 · **Método:** lectura de
> código y DDL. **Esta sesión no ejecutó consultas, pruebas ni migraciones.** Todo lo
> marcado 🟢 es lectura de código, no resultado de ejecución.
> **Caduca si:** cambia `servicio_facturacion.py`, `servicio_gastos.py`,
> `servicio_rentabilidad.py`, `servicio_iva.py`, las migraciones `0011`/`0013` o el
> registro de tools del chat.
> **Re-verificar con:** `rg -n "def aging|def costos|def rentabilidad_viaje|def resumen" backend/app/nucleo/servicio_*.py`
> y `rg -n "HERRAMIENTAS" backend/app/nucleo/agente/chat/herramientas.py`.

---

## 0. Resumen y estado real

Hoy **no existe ninguna tool económica** en el chat. El registro
(`backend/app/nucleo/agente/chat/herramientas.py:730-859`) contiene cinco tools del
gerente y cuatro de la secretaria; ninguna consulta facturación, cobranza, gastos,
margen ni IVA. Las allowlists están en `agente/chat/personas.py:104-132`.

| ID | Métrica | Quién la pide | Existe el cálculo? | Existe la tool? |
|---|---|---|---|---|
| **M-01** | Resumen económico del período | gerente | **Parcial**: las piezas están, el agregado no | 🔴 no |
| **M-02** | Margen por camión | gerente | **Parcial**: por viaje sí; por tracto y período no | 🔴 no |
| **M-03** | Total de fletes por cliente | secretaria | **No** (solo 10 viajes recientes) | 🔴 no |
| **M-04** | Facturas pendientes | secretaria | **No** como listado con saldo; `aging()` da el agregado | 🔴 no |
| **M-05** | Cartera y aging | gerente | **Sí**, `ServicioFacturacion.aging()` | 🔴 no |
| **M-06** | Gastos del período | gerente | **Parcial**: por viaje sí; por período y tipo no | 🔴 no |
| **M-07** | IVA débito del período | gerente | **Sí**, `ServicioIva.resumen()` (solo débito) | 🔴 no |

**Lo que este documento no es:** no es un balance contable, no es una declaración
tributaria y no autoriza a inventar tasas, plazos ni tratamientos. Las preguntas sin
respuesta del dueño o del contador están en §7 y en
[`preguntas.md`](preguntas.md).

---

## 1. Alcance y definiciones

### 1.1 Vocabulario (fijado para todo el documento)

| Término | Significado preciso | Fuente |
|---|---|---|
| **viaje** = **flete** | La unidad económica del negocio: un traslado con origen, destino, carga, tracto y chofer | `docs/negocio/contexto.md:28-46` |
| **camión** | El **tracto** (`nucleo.tractos`). La rampla no es unidad de margen | `backend/app/nucleo/models.py:470-512` |
| **neto** | Importe **sin IVA** | `nucleo.viajes.valor_flete_neto` / `viaje_gastos.monto_neto` |
| **facturado** | Documento emitido (`facturas_nucleo`), independiente de si se cobró | `supabase/migrations/0013_facturacion.sql:10-38` |
| **cobrado** | Pago recibido (`pagos_nucleo`), independiente de qué factura se emitió en el período | `0013:78-98` |
| **devengado operativo** | Viaje **cerrado** (`fin_real` no nulo): su costo ya es medible | `backend/app/nucleo/servicio_expediente.py:1268-1270` |
| **cartera / CxC** | Saldo pendiente de facturas no anuladas, a una fecha de corte | `servicio_facturacion.py:777-812` |

### 1.2 Las siete métricas

| ID | Definición en una frase | Qué **sí** es | Qué **no** es |
|---|---|---|---|
| **M-01** | Resumen operativo del período: facturado, IVA débito, cobrado, gastos aprobados, margen directo y cartera | Foto de la operación con cifras trazables a documentos | Balance contable, estado de resultados, flujo de caja |
| **M-02** | Ingreso menos costo directo de los viajes **cerrados** de un tracto en el período | Margen de contribución operativo por camión | Utilidad del camión (no incluye costo fijo, mantención, overhead ni costo financiero) |
| **M-03** | Cantidad de viajes de un cliente en el período, con su monto neto | Conteo operativo y monto de los viajes listados | Cantidad de facturas ni monto facturado (son M-01/M-04) |
| **M-04** | Facturas con saldo > 0 y estado distinto de `anulada` | Documentos por cobrar, con saldo y atraso | Facturas emitidas en el período (puede haber facturas antiguas abiertas) |
| **M-05** | Saldo total y vencido de la cartera, repartido en 5 tramos de atraso | Foto de CxC al día de hoy | Proyección de cobranza ni aging histórico |
| **M-06** | Gastos de viaje del período, separando aprobados, pendientes y rechazados | Costo aprobado (neto) y gasto en trámite | Costo total del viaje (M-02) ni CxP |
| **M-07** | IVA **débito** de las facturas no anuladas emitidas en el período | Dato almacenado y trazable a facturas | IVA a pagar, crédito fiscal ni F29 |

### 1.3 Fuera de alcance (declarado, no olvidado)

- **Caja y bancos:** no hay tabla de movimientos de caja. `caja_operativa` del tablero
  es `cobros − gastos` de 30 días (`servicio_alertas.py:365-392`), **no** un saldo
  bancario.
- **Cuentas por pagar, depreciación, intereses, impuestos y presupuesto:** no existen
  tablas (ver `docs/negocio/kpis.md:90-95`).
- **Costo financiero del capital de trabajo:** no modelado; es pregunta (`D-23`).
- **Nómina y comisión devengada:** la comisión entra al costo del viaje (R-11), pero la
  liquidación mensual no es una métrica de este chat.

---

## 2. Convenciones comunes (obligatorias para M-01…M-07)

### 2.1 Empresa

- `empresa_id` se toma del **contexto del servidor** (`ContextoEmpresa`), nunca del
  mensaje, del LLM ni del body. El patrón ya existe en las tools:
  `herramientas.py:141-159` verifica membresía activa en `nucleo.usuarios_empresa`.
- Toda consulta lleva `empresa_id = :e` en **cada** tabla. No se acepta un `empresa_id`
  como argumento de la tool (`personas.py:40-41`).
- El acceso al chat hoy es **solo `admin`**: `RolEmpresa.gerente` resta explícitamente
  `PERMISOS_AGENTE` (`permisos.py:69-73`). Que el rol `gerente` o `secretaría` de la
  empresa use estas tools es **AB-02**, no esta entrega.

### 2.2 Período

- Convención del repo: intervalo **semiabierto `[desde, hasta)`** (AGENTS.md §3.9).
- **Columnas `date`** (`fecha_emision`, `pagos.fecha`, `viaje_gastos.fecha`,
  `notas_credito_nucleo.fecha`): comparación directa
  `columna >= :desde AND columna < :hasta`.
- **Columnas `timestamptz`** (`viajes.inicio_planificado`, `viajes.fin_real`): se
  convierten a la zona de la **empresa** (`empresa.zona_horaria`), no a UTC:

  ```sql
  v.fin_real >= (:desde::timestamp AT TIME ZONE :tz)
  AND v.fin_real <  (:hasta::timestamp AT TIME ZONE :tz)
  ```

  El patrón `v.fin_real::date` o `AT TIME ZONE 'UTC'` desplaza los viajes nocturnos
  (ver CN-104). La zona ya se usa para `hoy` en `servicio_facturacion.py:103-104`.
- **Presets** que la tool resuelve y **devuelve en la respuesta** (para que el modelo no
  los adivine):
  - `mes_actual`: `[primer día del mes de hoy, primer día del mes siguiente)`;
  - `mes_anterior`: `[primer día del mes anterior, primer día del mes actual)`;
  - `ultimos_30_dias`: `[hoy − 29 días, hoy + 1 día)` = 30 días calendario incluido hoy;
  - `personalizado`: `desde` y `hasta` explícitos.
- Se rechaza `desde >= hasta` y un rango mayor a **366 días** (guarda de costo).
- **Decisión pendiente `D-22`:** si el dueño quiere mes calendario o móvil, y si el
  margen se atribuye por `fin_real` o por `inicio_planificado`.

### 2.3 Moneda y tipo

- CLP con 2 decimales (`numeric(14,2)`); **nunca `float`**.
- En Python, `Decimal`; en SQL, `numeric`. Las sumas se hacen en la base o en
  `Decimal`, jamás en `float` (`kpis.md:48-54` documenta que el motor legacy sí usa
  `float` y por eso no sirve para dinero).

### 2.4 Redondeo

| Qué | Modo | Momento |
|---|---|---|
| Importes (montos, saldos, márgenes) | `ROUND_HALF_UP` a 2 decimales | **Al presentar**; las sumas intermedias no se redondean |
| Comisión por viaje | `ROUND_HALF_UP` a 2 decimales | **Por viaje**, porque así lo hace `ServicioGastos.costos()` (`servicio_gastos.py:60-61,456-461`). Es la única excepción documentada y existe para que el chat y la ficha del viaje muestren el mismo número |
| Porcentajes | `ROUND_HALF_UP` a 2 decimales | Al presentar; si el denominador es 0 → `null`, no `0` |

**Deuda detectada:** `servicio_gastos.py:464-466` cuantiza `margen_pct` **sin**
`rounding=`, es decir con `ROUND_HALF_EVEN` del contexto `decimal`, mientras los montos
del mismo método usan `ROUND_HALF_UP`. Diferencia máxima: $0,01 por ciento (ver CN-103).
Para el chat se especifica `HALF_UP`; si se reutiliza el servicio tal cual, el número
puede diferir en 0,01 pp.

### 2.5 Nulos

| Campo | Puede ser nulo | Tratamiento |
|---|---|---|
| `viajes.monto_total_neto` | **No** (columna generada `valor_flete_neto + monto_recargos`, `0004:623`) | No requiere `coalesce`; se usa igual |
| `viajes.valor_flete_neto`, `monto_recargos` | No (`NOT NULL DEFAULT 0`) | — |
| `viajes.tracto_id` | Sí | Bucket **`sin_tracto`**; no se descarta el viaje en silencio |
| `viajes.chofer_id` | Sí | Comisión = **0** (explícito, no "desconocida") |
| `viajes.fin_real` | Sí | El viaje **no** entra al margen; se informa `viajes_abiertos` |
| `viajes.distancia_km` | Sí | No se usa en M-01/M-02; solo afecta costo/km, que no es métrica de este chat |
| `viaje_gastos.iva` | No (`NOT NULL DEFAULT 0`) | — |
| `viaje_gastos.monto_neto` | No (generada `monto_total − iva`, `0011:39`) | — |
| `facturas_nucleo.iva` | No (`NOT NULL DEFAULT 0`) | — |
| `notas_credito_nucleo.estado` | No (`aplicada`/`anulada`) | Solo `aplicada` resta del saldo |
| `pagos_nucleo.fecha` | No | — |

### 2.6 Vacío y truncamiento

- Un período sin datos devuelve **ceros**, `sin_datos: true` y una advertencia; nunca
  `null` en un monto.
- Los listados se truncan a `N` (M-04: 20 por defecto, máximo 50; M-02: 50 tractos),
  pero los **agregados se calculan sobre el total**. La respuesta incluye
  `total` y `truncado: true/false`.
- **No repetir el defecto de `aging()`:** `servicio_facturacion.py:778` llama
  `listar_facturas(limit=1000)`; con más de 1000 facturas el total se trunca en
  silencio. La tool de M-05 debe agregar en SQL, no reutilizar ese método.

### 2.7 Envelope de respuesta (propuesta para `backend`)

Toda tool económica devuelve el mismo sobre; el modelo no puede inventar el período ni
la moneda porque los recibe:

```json
{
  "periodo": {"desde": "2026-10-01", "hasta": "2026-11-01",
              "zona": "America/Santiago", "etiqueta": "octubre 2026"},
  "corte": "2026-10-31",
  "moneda": "CLP",
  "datos": { },
  "advertencias": ["Solo débito fiscal; no incluye crédito ni F29."],
  "estado_tool": "ok"
}
```

---

## 3. Fórmulas exactas

### M-01 — Resumen económico del período

**Fórmula:**

```text
facturado_neto    = Σ f.neto        para f.empresa_id = :e
                                     AND f.estado <> 'anulada'
                                     AND f.fecha_emision ∈ [desde, hasta)
iva_debito        = Σ f.iva         (mismo filtro)
facturado_total   = Σ f.total       (mismo filtro; total = neto + iva, generada)
notas_credito     = Σ n.monto       para n.estado = 'aplicada'
                                     AND n.fecha ∈ [desde, hasta)
cobrado           = Σ p.monto       para p.fecha ∈ [desde, hasta)
gastos_aprobados  = Σ g.monto_neto  para g.estado = 'aprobado' AND g.activo
                                     AND g.fecha ∈ [desde, hasta)
margen_operativo  = Σ (ingreso_viaje − costo_directo_viaje)
                     para viajes con fin_real ∈ [desde, hasta) y estado <> 'anulado'
cxc_total         = Σ saldo(f)      para saldo(f) > 0 AND f.estado <> 'anulada'   (corte = hoy)
cxc_vencido       = Σ saldo(f)      para saldo(f) > 0 AND f.estado <> 'anulada'
                                     AND dias_atraso(f) > 0
```

donde `ingreso_viaje`, `costo_directo_viaje`, `saldo(f)` y `dias_atraso(f)` se definen
en M-02 y M-04/M-05.

| Aspecto | Definición |
|---|---|
| **Tablas y campos** | `facturas_nucleo.neto/iva/total/fecha_emision/estado`; `pagos_nucleo.monto/fecha`; `notas_credito_nucleo.monto/fecha/estado`; `viaje_gastos.monto_neto/estado/activo/fecha`; `viajes.monto_total_neto/fin_real/estado` |
| **Empresa** | `empresa_id = :e` en cada tabla |
| **Período** | Facturado e IVA: `fecha_emision`. Cobrado: `pagos.fecha`. Gastos: `viaje_gastos.fecha`. Margen: `fin_real` en zona de la empresa. Cartera: **corte = hoy**, sin período |
| **Exclusiones** | Facturas `estado = 'anulada'`; gastos `estado <> 'aprobado'` o `activo = false`; viajes `estado = 'anulado'` o `fin_real IS NULL` |
| **Redondeo** | Sumas exactas; `ROUND_HALF_UP` 0,01 al presentar; porcentajes 2 dec |
| **Nulos** | `coalesce(sum(...), 0)`; `fin_real` nulo excluye y se informa `viajes_abiertos`; `tracto_id` nulo no afecta M-01 |

**Advertencia de conciliación (obligatoria en la respuesta):** `facturado_neto`,
`cobrado`, `gastos_aprobados` y `margen_operativo` salen de **cuatro poblaciones
distintas** (emisión, pago, fecha de gasto, cierre de viaje). **No** se cumple
`margen = facturado − gastos` y no debe presentarse como si lo fuera. Ver §3.8 y
CN-104.

**Implementación real:** no existe el agregado. Las piezas: `servicio_iva.py:53-81`
(facturado/IVA), `servicio_gastos.py:437-506` (costo por viaje),
`servicio_facturacion.py:777-812` (cartera). El cobrado solo aparece como
`caja_operativa` de 30 días (`servicio_alertas.py:365-392`), que **no** es esta métrica.

**Clasificación:** `ausente` (tool) · `parcial` (cálculo de origen).

**Caso numérico:** CN-101.

---

### M-02 — Margen por camión (tracto)

**Fórmula por viaje:**

```text
ingreso_viaje  = v.monto_total_neto                      -- numeric(14,2), NOT NULL, generada
comision_viaje = ROUND_HALF_UP(v.monto_total_neto × c.porcentaje_comision, 2)
                 si v.chofer_id IS NOT NULL
               = 0                                        si v.chofer_id IS NULL
gastos_viaje   = Σ g.monto_neto  para g.estado = 'aprobado' AND g.activo
costo_directo  = gastos_viaje + comision_viaje
margen_viaje   = ingreso_viaje − costo_directo
```

**Agregado por tracto:**

```text
ingreso_tracto = Σ ingreso_viaje
costo_tracto   = Σ costo_directo
margen_tracto  = ingreso_tracto − costo_tracto
margen_pct     = ROUND_HALF_UP(margen_tracto / ingreso_tracto × 100, 2)   si ingreso_tracto > 0
               = NULL                                                      si ingreso_tracto = 0
```

| Aspecto | Definición |
|---|---|
| **Tablas y campos** | `viajes.monto_total_neto/tracto_id/chofer_id/fin_real/estado`; `viaje_gastos.monto_neto/estado/activo`; `choferes.porcentaje_comision`; `tractos.patente` |
| **Empresa** | `empresa_id = :e` en `viajes`, `viaje_gastos` y `choferes` |
| **Período** | `fin_real ∈ [desde, hasta)` en zona de la empresa. **No** `inicio_planificado`: incluiría viajes no ejecutados con costo incompleto |
| **Exclusiones** | Viajes `estado = 'anulado'`; viajes `fin_real IS NULL` (se informan como `viajes_abiertos`); gastos no aprobados, rechazados o `activo = false`; comisión de viaje sin chofer = 0 |
| **Redondeo** | Comisión por viaje `HALF_UP` 0,01 (igual que `costos()`); margen y % redondeados solo al presentar |
| **Nulos** | `tracto_id` nulo → fila **`sin_tracto`** con sus totales; `chofer_id` nulo → comisión 0; `porcentaje_comision` nulo → 0 (default de modelo 0,10, `models.py:584-586`; default de base 0 en `0004:300-301`, corregido a 0,10 por `0017` **si está aplicada**) |

**Qué incluye y qué no:**

| Concepto | ¿Entra al costo? | Evidencia |
|---|---|---|
| Combustible, peajes, estadías, viáticos, lavado, pesaje, otros gastos aprobados | **Sí**, por `monto_neto` | `servicio_gastos.py:446-448,461` |
| Comisión del chofer | **Sí** | `servicio_gastos.py:456-461` |
| Gastos pendientes o rechazados | **No** | `servicio_gastos.py:446-447` |
| Mantención del tracto | **No** (solo KPI mensual legacy) | `D-20`; `catalogo-reglas.md` R-07 |
| Costo fijo mensual / overhead | **No** | `servicio_gastos.py:462` (`costo_total = costo_variable`) |
| Costo financiero del capital de trabajo | **No** | no modelado → `D-23` |

**No confundir con `ServicioRentabilidad.rentabilidad_viaje()`:** ese método devuelve
`margen` = ingreso − costo_variable (`servicio_rentabilidad.py:192`) y, aparte,
`costo_total` = costo_variable + **costo fijo asignado** (`:201`), más tarifa piso y
Freight Score. Son dos números distintos con el mismo nombre. Para el chat se usa el de
`ServicioGastos.costos()`, que es el que ve el operador en la ficha del viaje.

**Implementación real:** `servicio_gastos.py:437-506` (por viaje). El agregado por
tracto y período **no existe**. Existe además una copia persistida en PostgreSQL,
`nucleo.fn_viaje_costos` (`0011:91-135`, trigger `0011:137-156`), que escribe
`viajes.costo_variable_real` / `costo_total_real`; **ningún código de aplicación la
lee** (grep 2026-11-04: solo `models.py:807-812` y un test). Es una tercera versión
latente: puede quedar obsoleta si cambia el porcentaje del chofer o el flete sin que se
toque un gasto.

**Clasificación:** `parcial` (por viaje implementado; agregado y composición pendientes
`D-20`/`D-23`).

**Caso numérico:** CN-103.

---

### M-03 — Total de fletes por cliente

**Fórmula:**

```text
fletes_cliente = COUNT(v.id)
monto_neto     = Σ v.monto_total_neto
para v.empresa_id = :e
 AND v.cliente_id = :cliente
 AND v.estado NOT IN ('anulado', 'borrador', 'cotizado')
 AND v.inicio_planificado ∈ [desde, hasta)
```

| Aspecto | Definición |
|---|---|
| **Tablas y campos** | `viajes.cliente_id/estado/inicio_planificado/monto_total_neto`; `clientes.razon_social/rut` |
| **Empresa** | `empresa_id = :e`; el cliente se resuelve **dentro** de la empresa (nunca por ID de otra) |
| **Período** | `inicio_planificado` (siempre poblado), en zona de la empresa |
| **Exclusiones** | `anulado` (no es flete), `borrador` y `cotizado` (no son fletes comprometidos). **Decisión pendiente `D-24`** |
| **Redondeo** | Conteo entero; monto `HALF_UP` 0,01 al presentar |
| **Nulos** | `monto_total_neto` no nulo; cliente sin viajes → `fletes: 0`, `monto_neto: 0.00`, `sin_datos: true` |

**Respuesta mínima:** `cliente_id`, `cliente_nombre`, `fletes`, `monto_neto`,
`por_estado` (conteo por estado), `periodo`. Si el nombre es ambiguo (dos clientes con
razón social parecida), la tool devuelve los candidatos y **no** elige uno.

**No confundir:** "total de fletes" es **conteo de viajes**, no monto facturado. Si el
dueño pregunta "¿cuánto facturamos a SQM?", la métrica es M-01 filtrada por cliente
(`fecha_emision`), no M-03.

**Implementación real:** no existe. `secretaria_consultar_viajes`
(`herramientas.py:431-465`) devuelve los **10 más recientes** y el conteo por estado de
los últimos 30 días, sin cliente ni período. `listar_viajes`
(`servicio_expediente.py:366-404`) sí filtra por cliente y fechas, pero usa
`inicio_planificado <= hasta` (**inclusivo**, `:394-395`), lo que contradice
`[desde, hasta)`.

**Clasificación:** `ausente`.

**Caso numérico:** CN-104.

---

### M-04 — Facturas pendientes

**Fórmula:**

```text
saldo(f)       = f.total − Σ pagos(f) − Σ notas_aplicadas(f)
dias_atraso(f) = max(0, (hoy − f.fecha_vencimiento).días)
pendiente(f)   = saldo(f) > 0 AND f.estado <> 'anulada'

total_pendiente = Σ saldo(f) para pendiente(f)
total_vencido   = Σ saldo(f) para pendiente(f) AND dias_atraso(f) > 0
```

| Aspecto | Definición |
|---|---|
| **Tablas y campos** | `facturas_nucleo.total/fecha_vencimiento/estado/cliente_id`; `pagos_nucleo.monto`; `notas_credito_nucleo.monto/estado` |
| **Empresa** | `empresa_id = :e` en las tres tablas |
| **Período** | **Sin período por defecto**: es una foto a `hoy`. Filtros opcionales `cliente_id` y `solo_vencidas` |
| **Exclusiones** | `estado = 'anulada'`; `saldo <= 0` (pagada o sobrepagada) |
| **Redondeo** | `saldo` con `ROUND_HALF_UP` 0,01 (`servicio_facturacion.py:63-64,207`) |
| **Nulos** | Factura sin pagos ni notas → ambos sumandos 0 (`coalesce`) |

**Orden y límite:** `fecha_vencimiento ASC, numero_factura ASC`; lista de 20 (máx. 50),
con `total`, `total_vencido` y `truncado` calculados sobre el conjunto completo.

**Implementación real:** no existe el listado "pendientes". `listar_facturas`
(`servicio_facturacion.py:234-...`) filtra por estado pero **no por saldo**: el saldo se
calcula en Python (`:169-183,207`), así que filtrar después de un `LIMIT` puede perder
facturas abiertas. `aging()` (`:777-812`) da el agregado, no la lista.

**Clasificación:** `ausente`.

**Caso numérico:** CN-102.

---

### M-05 — Cartera y aging

**Fórmula:**

```text
cartera(f) = saldo(f)  para pendiente(f)          (definiciones de M-04)
total_cxc     = Σ cartera(f)
total_vencido = Σ cartera(f) donde dias_atraso(f) > 0
facturas_abiertas = COUNT(f) donde pendiente(f)
```

**Buckets (los cinco existentes, `servicio_facturacion.py:185-195`):**

| Bucket | Etiqueta | Regla exacta | Borde |
|---|---|---|---|
| `por_vencer` | Por vencer | `dias_atraso <= 0` | El día del vencimiento (`0`) **no** está vencido |
| `0_30` | 0–30 días | `1 <= dias_atraso <= 30` | `30` cae acá; `31` pasa al siguiente |
| `31_60` | 31–60 días | `31 <= dias_atraso <= 60` | — |
| `61_90` | 61–90 días | `61 <= dias_atraso <= 90` | — |
| `mas_90` | > 90 días | `dias_atraso >= 91` | — |

| Aspecto | Definición |
|---|---|
| **Tablas y campos** | Las de M-04 |
| **Empresa** | `empresa_id = :e` |
| **Período** | **Corte = hoy** en zona de la empresa (`servicio_facturacion.py:103-104`). No hay aging histórico |
| **Exclusiones** | `estado = 'anulada'`; `saldo <= 0` |
| **Redondeo** | `HALF_UP` 0,01 por factura y en los totales |
| **Nulos** | Sin facturas → totales 0, `facturas_abiertas: 0`, mensaje "Sin facturas abiertas" |

**Aging histórico:** no implementado. Un corte pasado exigiría filtrar también
`pagos.fecha <= corte`, `notas.fecha <= corte` y `facturas.fecha_emision <= corte`; hoy
`_saldos()` suma todos los pagos sin fecha (`servicio_facturacion.py:169-183`). Si el
gerente pide "la cartera al 30 de septiembre", la respuesta correcta es "no está
disponible" (o se implementa como consulta nueva).

**Implementación real:** `ServicioFacturacion.aging()` (`servicio_facturacion.py:777-812`),
expuesto en `GET /nucleo/cobranza/aging` (`api_facturacion.py:124-128`). **Defectos
conocidos:** trunca a 1000 facturas (`:778`) y hace N+1 consultas de saldo (una por
factura vía `_saldos`). La tool debe agregar en SQL.

**Clasificación:** `implementada` (servicio) · `ausente` (tool).

**Caso numérico:** CN-102.

---

### M-06 — Gastos del período

**Fórmula:**

```text
gastos_aprobados_neto = Σ g.monto_neto   para g.estado = 'aprobado' AND g.activo
                                          AND g.fecha ∈ [desde, hasta)
gastos_pendientes_bruto = Σ g.monto_total para g.estado = 'pendiente' AND g.activo
                                          AND g.fecha ∈ [desde, hasta)
gastos_rechazados      = COUNT(g), Σ g.monto_total  para g.estado = 'rechazado' AND g.activo
                                          AND g.fecha ∈ [desde, hasta)
desglose_por_tipo(t)   = Σ g.monto_neto  para g.tipo = t AND g.estado = 'aprobado' AND g.activo
```

| Aspecto | Definición |
|---|---|
| **Tablas y campos** | `viaje_gastos.tipo/monto_total/iva/monto_neto/estado/activo/fecha` |
| **Empresa** | `empresa_id = :e` |
| **Período** | `viaje_gastos.fecha` (fecha del gasto, no del viaje) |
| **Exclusiones** | `activo = false` (anulado lógico); los rechazados se informan pero **no** suman; los pendientes se informan pero **no** suman al costo |
| **Redondeo** | Aprobados por `monto_neto`; pendientes por `monto_total`; `HALF_UP` 0,01 al presentar |
| **Nulos** | `tipo` no nulo (`default 'otro'`); `litros`, `km_odometro` opcionales y no se usan acá |

**Inconsistencia a no propagar:** `ServicioGastos.costos()` suma los **aprobados** por
`monto_neto` y los **pendientes** por `monto_total` (`servicio_gastos.py:448-449`). Es
decir, el pendiente se muestra con IVA y el aprobado sin IVA. La tool debe etiquetar
explícitamente "pendiente (bruto, incluye IVA)" o informar ambos valores; no debe
sumarlos en una misma columna.

**Implementación real:** por viaje, `servicio_gastos.py:437-506`. Agregado por período y
tipo: **no existe**. `caja_operativa` suma gastos aprobados netos de 30 días
(`servicio_alertas.py:373-380`), pero no desglosa ni respeta un período arbitrario.

**Clasificación:** `parcial` (por viaje) · `ausente` (agregado).

**Caso numérico:** CN-101 (gastos) y CN-103 (rechazado/pendiente/inactivo).

---

### M-07 — IVA débito del período

**Fórmula:**

```text
facturas        = COUNT(f)
base_neta       = Σ f.neto
iva_debito      = Σ f.iva
para f.empresa_id = :e
 AND f.estado <> 'anulada'
 AND f.fecha_emision ∈ [desde, hasta)
tasa_vigente    = nucleo.config_vigente(:e, 'iva_porcentaje')   -- porcentaje, no fracción
```

| Aspecto | Definición |
|---|---|
| **Tablas y campos** | `facturas_nucleo.neto/iva/fecha_emision/estado`; `configuracion_empresa` vía `nucleo.config_vigente` |
| **Empresa** | `empresa_id = :e` |
| **Período** | `fecha_emision` |
| **Exclusiones** | `estado = 'anulada'` |
| **Redondeo** | Sumas exactas; `HALF_UP` 0,01 al presentar |
| **Nulos** | `iva` no nulo; si no hay tasa configurada, `tasa_vigente = null` y se advierte (la emisión de facturas falla cerrada, `servicio_facturacion.py:578-583`) |

**Lo que la métrica NO hace (y no debe insinuar):**

- **No calcula crédito fiscal.** `ServicioIva` lo excluye por diseño
  (`servicio_iva.py:9-14,31-35`).
- **No calcula `a_pagar` ni F29.** Es `P-13` y `P-01`.
- **No descuenta notas de crédito.** El tratamiento no está definido (`P-06`/`P-09`).
- **`base_neta` no es necesariamente la base imponible:** la consulta suma `neto` de
  **todas** las facturas no anuladas (`servicio_iva.py:61-68`). Hoy toda factura aplica
  la tasa de la empresa (`servicio_facturacion.py:602`), así que no hay exentas; si se
  agrega la afecta/exenta, `base_neta` incluiría exentas y dejaría de ser la base
  imponible. Es `P-13(b)`.

**Implementación real:** `servicio_iva.py:53-81`; `GET /nucleo/iva/resumen`
(`api_iva.py:46-53`). **Ojo con el borde:** el servicio usa `fecha_emision <= :hasta`
(`servicio_iva.py:68`), **inclusivo**; la convención del chat es `[desde, hasta)`.
Reutilizarlo sin ajustar incluye un día de más (CN-105).

**Clasificación:** `implementada` (servicio, solo débito) · `ausente` (tool).

**Caso numérico:** CN-105.

---

### 3.8 Por qué los números no cuadran entre sí (y está bien)

| Número | Población | Fecha que manda |
|---|---|---|
| Facturado | Facturas no anuladas | `fecha_emision` |
| Cobrado | Pagos recibidos (de cualquier factura) | `pagos.fecha` |
| Gastos | Gastos aprobados | `viaje_gastos.fecha` |
| Margen | Viajes cerrados y sus gastos/comisión | `fin_real` |
| Cartera | Saldo de facturas abiertas | corte = hoy |

**Regla de presentación:** el chat nunca debe escribir "resultado = facturado − gastos"
ni "margen del mes = facturado − gastos". Si el gerente lo pide, se explican las cuatro
poblaciones y se ofrece el margen operativo (M-02) como el número correcto para
"ganancia de los viajes".

---

## 4. Casos numéricos (calculados a mano, datos sintéticos)

Todos en **CLP**, aritmética decimal exacta, sin `float`. El IVA de los ejemplos es un
dato sintético almacenado en la factura; **no** es una afirmación sobre la tasa vigente
(`P-01`).

### CN-101 resumen económico de octubre — M-01

**Datos.** Empresa A; período `[2026-10-01, 2026-11-01)`; corte `2026-10-31`.

- Facturas no anuladas emitidas en octubre:
  - F-101, cliente SQM: neto **1.000.000,00**, IVA **190.000,00**, total **1.190.000,00**, vence 2026-10-20.
  - F-102, cliente Cervera: neto **500.000,00**, IVA **95.000,00**, total **595.000,00**, vence 2026-11-15.
- Pagos con fecha en octubre: P-101, sobre F-101, **700.000,00** (2026-10-05).
- Gastos aprobados y activos con fecha en octubre: G-101 combustible total 238.000,00 / IVA 38.000,00 → neto **200.000,00**; G-102 peaje total 119.000,00 / IVA 19.000,00 → neto **100.000,00**.
- Gasto pendiente: G-103 estadía total **59.500,00** (no suma).
- Viajes cerrados en octubre (no anulados), tracto T-101, chofer al 10 %:
  - V-101: `monto_total_neto` **1.000.000,00**; gastos aprobados **180.000,00**; comisión 1.000.000,00 × 0,10 = **100.000,00**.
  - V-102: `monto_total_neto` **500.000,00**; gastos aprobados **120.000,00**; comisión 500.000,00 × 0,10 = **50.000,00**.

**Cálculo paso a paso.**

1. `facturado_neto` = 1.000.000,00 + 500.000,00 = **1.500.000,00**
2. `iva_debito` = 190.000,00 + 95.000,00 = **285.000,00**
3. `facturado_total` = 1.190.000,00 + 595.000,00 = **1.785.000,00**
4. `cobrado` = **700.000,00**
5. `gastos_aprobados` = 200.000,00 + 100.000,00 = **300.000,00** (G-103 no suma)
6. Costo V-101 = 180.000,00 + 100.000,00 = 280.000,00 → margen 1.000.000,00 − 280.000,00 = **720.000,00**
7. Costo V-102 = 120.000,00 + 50.000,00 = 170.000,00 → margen 500.000,00 − 170.000,00 = **330.000,00**
8. `margen_operativo` = 720.000,00 + 330.000,00 = **1.050.000,00**; `margen_pct` = 1.050.000,00 / 1.500.000,00 × 100 = **70,00 %**
9. Cartera: saldo F-101 = 1.190.000,00 − 700.000,00 = 490.000,00 (11 días de atraso → `0_30`); saldo F-102 = 595.000,00 (por vencer).
10. `cxc_total` = 490.000,00 + 595.000,00 = **1.085.000,00**; `cxc_vencido` = **490.000,00**; `facturas_abiertas` = **2**.

**Resultado esperado:** facturado neto 1.500.000,00 · IVA débito 285.000,00 · cobrado 700.000,00 · gastos 300.000,00 · margen operativo 1.050.000,00 (70,00 %) · CxC 1.085.000,00 · vencido 490.000,00.

**Borde que ejercita:** caso normal; distingue facturado de cobrado y de margen; el gasto pendiente no contamina el costo.

**Fuente de la regla:** M-01, R-12.

---

### CN-102 pago parcial, nota de crédito y bordes de aging — M-04/M-05/R-10

**Datos.** F-103 emitida 2026-09-10, vence **2026-10-10**, neto 2.000.000,00, IVA 380.000,00, total **2.380.000,00**.

- Pago 2026-09-30: **500.000,00**.
- Pago 2026-10-05: **380.000,00**.
- Nota de crédito aplicada 2026-10-08: **200.000,00**.

**Cálculo paso a paso.**

1. `saldo` = 2.380.000,00 − (500.000,00 + 380.000,00) − 200.000,00 = 2.380.000,00 − 880.000,00 − 200.000,00 = **1.300.000,00**.
2. Al corte 2026-10-31: `dias_atraso` = 31 − 10 = **21** → bucket **`0_30`**; `pendiente` = sí (saldo > 0, estado `parcial`, no `anulada`).
3. `cxc_total` = **1.300.000,00**; `cxc_vencido` = **1.300.000,00**; `facturas_abiertas` = **1**.

**Bordes de bucket (mismo saldo, distintos cortes):**

| Corte | Días | Bucket |
|---|---|---|
| 2026-10-10 | 0 | `por_vencer` |
| 2026-10-11 | 1 | `0_30` |
| 2026-11-09 | 30 | `0_30` |
| 2026-11-10 | 31 | `31_60` |
| 2026-12-10 | 61 | `61_90` |
| 2027-01-09 | 91 | `mas_90` |

**Borde de tope (INV-F02/INV-F03):** antes de la NC, el saldo era 2.380.000,00 − 880.000,00 = **1.500.000,00**. Una NC de **1.500.000,01** se rechaza (`DatosInvalidos`, `servicio_facturacion.py:719-722`); una de **1.500.000,00** se acepta y deja saldo **0,00**. Un pago de **1.500.000,01** también se rechaza (`:686-689`).

**Resultado esperado:** saldo 1.300.000,00; bucket `0_30` al 2026-10-31; NC/pago por encima del saldo rechazados con 422/400 de dominio, nunca saldo negativo.

**Borde que ejercita:** pago parcial + NC + límites exactos de bucket + tope de saldo.

**Fuente de la regla:** R-10 (M-04, M-05).

---

### CN-103 margen por camión: rechazado, pendiente, inactivo, anulado y redondeo — M-02/R-11

**Datos.** Tracto T-102, octubre; chofer de V-103 al **12,5 %** (`0,1250`).

- **V-103:** `monto_total_neto` **1.000.009,00** (flete 900.009,00 + recargos 100.000,00).
  - Combustible aprobado: total 200.000,00 / IVA 38.000,00 → neto **162.000,00**.
  - Peaje aprobado: total 50.000,00 / IVA 9.500,00 → neto **40.500,00**.
  - Estadía **rechazada**: 80.000,00 → no suma.
  - Viático **pendiente**: 60.000,00 → no suma.
  - Lavado **aprobado pero `activo = false`**: neto 40.000,00 → no suma.
- **V-104:** `monto_total_neto` **500.000,00**; **sin chofer**; gastos aprobados netos **100.000,00**.
- **V-105 anulado:** `monto_total_neto` 900.000,00; gastos 300.000,00 → se excluye completo.

**Cálculo paso a paso.**

1. Comisión V-103 = 1.000.009,00 × 0,125 = **125.001,125** exacto → `HALF_UP` a 2 dec = **125.001,13**.
2. Gastos V-103 = 162.000,00 + 40.500,00 = **202.500,00**.
3. Costo V-103 = 202.500,00 + 125.001,13 = **327.501,13**.
4. Margen V-103 = 1.000.009,00 − 327.501,13 = **672.507,87**.
5. Comisión V-104 = **0,00** (sin chofer). Costo = **100.000,00**. Margen = **400.000,00**.
6. Tracto T-102: ingreso = 1.000.009,00 + 500.000,00 = **1.500.009,00**; costo = 327.501,13 + 100.000,00 = **427.501,13**; margen = **1.072.507,87**.
7. `margen_pct` = 1.072.507,87 / 1.500.009,00 × 100 = 71,500095… % → **71,50 %**.
8. V-105 no aporta ni ingreso ni costo.

**Redondeo por viaje vs por total:**

- Implementado (comisión cuantizada por viaje): margen = **1.072.507,87**.
- Exacto hasta el final: costo = 202.500,00 + 125.001,125 + 100.000,00 = 427.501,125; margen = 1.500.009,00 − 427.501,125 = 1.072.507,875 → redondeado una vez = **1.072.507,88**. **Δ $0,01.**

**Redondeo de porcentaje (mitad exacta):** con ingreso 1.000.000,00 y margen 100.050,00, la razón es 10,005 % → `HALF_UP` = **10,01 %**; `HALF_EVEN` (lo que hace hoy `servicio_gastos.py:464-466`) = **10,00 %**. **Δ 0,01 pp.**

**Resultado esperado:** margen T-102 = 1.072.507,87 (71,50 %); V-105 fuera; gasto rechazado, pendiente e inactivo fuera; comisión del viaje sin chofer = 0.

**Borde que ejercita:** gasto rechazado/pendiente/inactivo, viaje anulado, comisión con mitad exacta, redondeo por viaje vs por total y `HALF_UP` vs `HALF_EVEN`.

**Fuente de la regla:** R-11 (M-02).

---

### CN-104 mes cruzado y total de fletes por cliente — M-03/R-12

**Datos.** Cliente SQM; consulta "octubre 2026" = `[2026-10-01, 2026-11-01)`, zona
`America/Santiago`.

| Viaje | `inicio_planificado` | `fin_real` | Estado | `monto_total_neto` | Factura (emisión) |
|---|---|---|---|---|---|
| V-106 | 2026-09-28 08:00 | 2026-10-02 18:00 | cobrado | 400.000,00 | 2026-11-05 |
| V-107 | 2026-10-05 07:00 | 2026-10-06 16:00 | facturado | 500.000,00 | 2026-10-20 |
| V-108 | 2026-10-20 09:00 | **null** | en_ruta | 350.000,00 | — |
| V-109 | 2026-10-15 10:00 | — | **anulado** | 600.000,00 | — |
| V-110 | 2026-10-30 11:00 | — | **borrador** | 250.000,00 | — |
| V-111 | 2026-09-30 22:00 | 2026-10-01 03:00 | cerrado | 300.000,00 | — |
| V-112 | 2026-09-30 20:00 | **2026-09-30 22:30** | cerrado | 200.000,00 | — |

**Cálculo paso a paso.**

1. **M-03 por `inicio_planificado` en octubre**, excluyendo `anulado`, `borrador` y `cotizado`: V-107 y V-108 → **2 fletes**. Monto neto = 500.000,00 + 350.000,00 = **850.000,00**.
2. **Margen por `fin_real` en octubre (zona Chile)**, no anulados: V-106 (02-oct), V-107 (06-oct) y V-111 (01-oct) → **3 viajes**. V-108 sigue abierto; V-112 cae el **30 de septiembre** en Chile.
3. **Trampa de zona horaria:** si `fin_real` se interpretara en UTC, V-112 (2026-09-30 22:30 Chile) caería el **2026-10-01** y el conteo sería **4**, no 3.
4. **Facturado en octubre** (`fecha_emision`): solo la factura de V-107 → **1 factura**, neto **500.000,00**. La de V-106 se emitió en noviembre y la de V-111 no existe en el ejemplo.
5. **Cobrado en octubre:** supongamos un pago de **300.000,00** el 2026-10-03 aplicado a una factura de **agosto** → `cobrado` = **300.000,00**, distinto del facturado de octubre (500.000,00). No es un error: son poblaciones distintas.
6. Si se contara el `borrador` V-110: 3 fletes por inicio. Si se contara el anulado V-109: 4. Por eso la exclusión debe estar escrita, no supuesta.

**Resultado esperado:** 2 fletes / 850.000,00 por inicio; 3 viajes por cierre; 1 factura / 500.000,00 por emisión; 300.000,00 cobrado. **Cuatro números distintos para "octubre".**

**Borde que ejercita:** mes cruzado, viaje abierto, anulado, borrador y cambio de día por zona horaria.

**Fuente de la regla:** R-12 (M-03); `D-22`/`D-24` pendientes.

---

### CN-105 IVA débito del período — M-07/R-06 (antecedente)

**Datos.** Octubre 2026; tasa configurada **19 %** (valor de ejemplo, no afirmación
normativa).

- F-105: afecta, emitida 2026-10-03, neto **1.000.000,00**, IVA **190.000,00**, pagada.
- F-106: afecta, emitida 2026-10-31, neto **200.000,00**, IVA **38.000,00**, emitida.
- F-107: **anulada**, emitida 2026-10-15, neto 400.000,00, IVA 76.000,00.
- F-108: afecta, emitida **2026-11-01**, neto 300.000,00, IVA 57.000,00.

**Cálculo paso a paso.**

1. `[2026-10-01, 2026-11-01)`: entran F-105 y F-106; F-107 se excluye por `anulada`; F-108 queda fuera por fecha.
2. `facturas` = **2**.
3. `base_neta` = 1.000.000,00 + 200.000,00 = **1.200.000,00**.
4. `iva_debito` = 190.000,00 + 38.000,00 = **228.000,00**.
5. **Borde inclusivo:** si se usara `fecha_emision <= :hasta` (como
   `servicio_iva.py:68`), F-108 entraría → `iva_debito` = 228.000,00 + 57.000,00 =
   **285.000,00**. **Δ $57.000,00** por un solo día.

**Resultado esperado:** 2 facturas, base 1.200.000,00, débito **228.000,00**; con
`<=` inclusive, 285.000,00 (incorrecto para el chat).

**Lo que no se calcula:** crédito fiscal, `a_pagar`, F29, notas de crédito. Si el
gerente pregunta "¿cuánto IVA pago?", la respuesta es: "solo tengo el débito; el crédito
y el F29 no están implementados (`P-13`)".

**Borde que ejercita:** factura anulada, factura fuera del período por un día, borde
inclusivo/exclusivo.

**Fuente de la regla:** M-07 (R-12); antecedente R-06.

---

## 5. Matriz de evidencia (qué existe hoy y qué es nuevo)

### 5.1 Piezas reutilizables

| Pieza | `archivo:línea` | Qué hace | Estado | ¿Sirve para la tool? |
|---|---|---|---|---|
| Saldo de factura | `backend/app/nucleo/servicio_facturacion.py:169-183` | Suma pagos y NC `aplicada` | 🟢 | Sí, pero es N+1; agregar en SQL |
| Días de atraso | `servicio_facturacion.py:208-210` | `max(0, hoy − vencimiento)`, 0 si saldo ≤ 0 | 🟢 | Sí |
| Buckets | `servicio_facturacion.py:185-195` | 5 tramos | 🟢 | Sí, copiar los bordes |
| Cartera | `servicio_facturacion.py:777-812` | Total, vencido, 5 buckets | 🟢 | **No** tal cual: trunca a 1000 (`:778`) |
| Listado de facturas | `servicio_facturacion.py:234-...` (filtros `:244-254`) | Filtra por estado/cliente/vencida | 🟢 | Parcial: no filtra por saldo |
| Recalculo estado/saldo | `supabase/migrations/0013_facturacion.sql:163-212` | Trigger sobre pagos y NC | 🟢 | Sí (fuente de `estado`) |
| Costo por viaje | `servicio_gastos.py:437-506` | Aprobados + comisión | 🟢 | Sí, por viaje |
| Costo persistido | `0011_gastos.sql:91-135,137-156` | `fn_viaje_costos` → `viajes.costo_variable_real` | 🟢 escrito / 🔴 leído | **No** para el chat: puede estar obsoleto |
| Rentabilidad | `servicio_rentabilidad.py:323-427` | Margen contribución + fijo + score | 🟢 | No: otra definición de margen |
| IVA débito | `servicio_iva.py:53-81` | Σ `iva` no anuladas | 🟢 | Sí, corrigiendo el `<=` |
| Tasa IVA vigente | `servicio_iva.py:44-51`; `servicio_facturacion.py:566-584` | Config por empresa | 🟢 | Sí |
| Emisión de factura | `servicio_facturacion.py:586-676` | Neto, IVA, estado inicial | 🟢 | Contexto |
| Gate POD/OC | `0009_pod.sql:65-104`; `servicio_facturacion.py:521-547` | Sin POD/OC no se factura | 🟢 | Garantiza el respaldo de lo facturado |
| Listado de viajes | `servicio_expediente.py:366-404` | Filtra cliente y fechas | 🟢 | Parcial: `hasta` inclusivo (`:394-395`) |
| Conteo reciente | `herramientas.py:431-465` | 10 viajes + por estado | 🟢 | No: sin cliente ni período |
| Registro de tools | `herramientas.py:730-859`; `personas.py:104-132` | 9 tools, ninguna económica | 🟢 | Punto de extensión |
| Caja operativa | `servicio_alertas.py:365-392` | Cobros − gastos 30 días | 🟢 | **No** es caja ni es M-01 |

### 5.2 Qué es nuevo de esta entrega (cálculo en la tool del chat)

| Métrica | Nuevo |
|---|---|
| M-01 | Agregado de facturado neto/total por período; cobrado por `pagos.fecha`; gastos por `viaje_gastos.fecha`; margen por `fin_real`; composición en un solo sobre |
| M-02 | Agregación por `tracto_id` y período; bucket `sin_tracto`; comisión por viaje con `HALF_UP` |
| M-03 | Conteo y monto por cliente y período; exclusiones de estado; resolución de cliente por nombre/RUT |
| M-04 | Listado con saldo calculado en SQL, orden por vencimiento y agregados completos |
| M-05 | Tool sobre `aging()`, con agregación en SQL (sin truncar a 1000) |
| M-06 | Agregado por período y `tipo`; separación aprobado/pendiente/rechazado/inactivo |
| M-07 | Tool sobre `ServicioIva` con período semiabierto y advertencia de alcance |

### 5.3 Versiones duplicadas detectadas (no corregidas acá)

| Regla | Versión A | Versión B | Riesgo |
|---|---|---|---|
| Costo del viaje | `ServicioGastos.costos()` (`servicio_gastos.py:437-506`), recalcula al leer | `fn_viaje_costos` (`0011:91-135`), persiste `costo_variable_real` | B queda obsoleta si cambia el % del chofer o el flete sin tocar un gasto; nadie la lee |
| Margen | `costos()`: ingreso − variable (`:461-463`) | `rentabilidad_viaje()`: margen = ingreso − variable (`:192`) y `costo_total` = + fijo (`:201`) | Mismo nombre, dos números |
| Redondeo de % | `_d` HALF_UP para montos (`servicio_gastos.py:60-61`) | `quantize(0.01)` sin `rounding` = HALF_EVEN (`:464-466`) | Δ 0,01 pp |
| Período de viajes | `[desde, hasta)` (convención) | `listar_viajes` usa `<= hasta` (`servicio_expediente.py:394-395`) | Un día de más |
| IVA | `[desde, hasta)` (convención) | `servicio_iva.py:68` usa `<= hasta` | Un día de más |
| Estado `vencida` | Python usa `hoy` en zona empresa (`servicio_facturacion.py:103-104`) | `fn_factura_estado` usa `current_date` de la sesión (`0013:194`) | Cerca de medianoche, el estado puede decir `vencida` con 0 días de atraso |

---

## 6. Invariantes que estas métricas tocan

| ID | Invariante | Dónde se impone hoy | ¿Prueba? | Efecto en las métricas |
|---|---|---|---|---|
| **INV-F01** | Un viaje no se factura dos veces | **DB + servicio**: `unique (empresa_id, viaje_id)` en `factura_viajes` (`0013:63`); chequeo `servicio_facturacion.py:538-547` | Declarada `test_nucleo_facturacion.py` (no ejecutada acá) | Evita doble conteo en facturado y cartera |
| **INV-F02** | Un pago no supera el saldo | **Solo aplicación**: `servicio_facturacion.py:682-689`; no hay trigger ni `CHECK` que sume pagos | Declarada `test_nucleo_facturacion.py:230-360` | Si falla, la cartera puede quedar negativa |
| **INV-F03** | Una NC no genera saldo negativo | **Solo aplicación**: `servicio_facturacion.py:717-722` | Declarada (misma prueba) | Igual que F02 |
| **INV-G01** | Un gasto rechazado no suma al costo | **DB + servicio**: `fn_viaje_costos` filtra `estado='aprobado' AND activo` (`0011:107-113`); `costos()` filtra (`servicio_gastos.py:446-448`) | Declarada `test_nucleo_gastos.py:272-276` | Si falla, el margen se subestima |
| **INV-G02** | Un gasto aprobado no se aprueba dos veces | **Servicio** con `estado='pendiente'` + bloqueo optimista por `version` (`servicio_gastos.py:349-373`) | Declarada | Evita doble costo por reintento |
| **INV-M01** | El margen no mezcla costos de otro viaje ni de otra empresa | **DB + servicio**: `costos()` filtra `empresa_id` y `viaje_id` (`servicio_gastos.py:439-445`); `fn_viaje_costos` filtra `empresa_id` (`0011:110-111`) | Declarada `test_nucleo_gastos.py:227-229` | Es la base de M-02 |
| **INV-A01** | Una anulación conserva rastro | El viaje anulado permanece con `motivo_anulacion`, `anulado_por`, `anulado_en` (`models.py:822-825`); las métricas lo **excluyen por estado**, no lo borran | Declarada | Un anulado no suma ni ingreso ni costo |
| **INV-P01** | Sin POD no se factura (regla vigente) | **DB**: `fn_viaje_facturacion` (`0009_pod.sql:65-104`) y trigger de no borrado de POD (`0009:48-59`); servicio `servicio_facturacion.py:530-537` | Declarada `test_nucleo_facturacion.py` | Lo facturado tiene respaldo documental |

**Observación de riesgo:** INV-F02 e INV-F03 son **solo de aplicación**. Para las
métricas de cartera, un pago o NC insertado por SQL directo (o por un futuro endpoint
que no replique la validación) puede dejar saldo negativo y distorsionar M-04/M-05. La
recomendación a `datos` está en §9.

---

## 7. Preguntas abiertas (nuevas; registradas en `preguntas.md`)

| ID | Pregunta | Destinatario | Qué bloquea |
|---|---|---|---|
| **D-22** | ¿El "mes" de las métricas es **calendario** o **móvil**? ¿El margen se atribuye por `fin_real` (cierre) o por `inicio_planificado`? ¿El conteo de fletes usa la misma fecha que el margen? | Dueño | R-12; M-01, M-02, M-03; cierre mensual |
| **D-23** | ¿El "margen por camión" debe incluir **mantención** (`D-20`), **costo fijo/overhead** y **costo financiero**? Hoy solo incluye gastos aprobados + comisión | Dueño (+ contador para el costo financiero) | M-02; tarifa piso; comparación entre camiones |
| **D-24** | ¿Qué cuenta como "flete" en el total por cliente: todos los viajes no anulados, solo los ejecutados/cerrados, o también borradores y cotizaciones? | Dueño | M-03 |
| **D-25** | ¿El ingreso del margen incluye **recargos**? (`monto_total_neto` = `valor_flete_neto + monto_recargos`; son el mismo valor, la pregunta es si los recargos deben ser ingreso). ¿Se usa neto de IVA? | Dueño (base) + contador (IVA) | M-01, M-02; coherencia con R-01/`D-01` |
| **P-12** | ¿La cartera informada debe **netear notas de crédito y pagos parciales**? ¿Qué se hace con una NC que supera el saldo (hoy se rechaza)? | Contador | M-04, M-05; `P-06` |
| **P-13** | **(a)** ¿El IVA del chat se limita al **débito** o requiere **crédito** y **F29**? **(b)** ¿La "base neta" debe excluir operaciones exentas (hoy suma todas las no anuladas)? | Contador | M-07; `P-01`, `P-09` |

> `D-25` no duplica `D-01`: `D-01` fija la **base de la comisión**; `D-25` fija la base
> del **ingreso del margen**. Hoy el código usa `monto_total_neto` para el costo/margen
> (`servicio_gastos.py:455`) y `valor_flete_neto` para la nómina legacy
> (`liquidaciones.py:92-95`): son decisiones distintas.

---

## 8. Reglas nuevas del catálogo

| ID | Nombre | Clasificación | Caso |
|---|---|---|---|
| **R-10** | Saldo, factura pendiente y aging | `implementada` | CN-102 |
| **R-11** | Costo directo y margen de viaje (definición para el chat) | `parcial` | CN-103 |
| **R-12** | Período y exclusiones de las métricas del chat | `decisión pendiente` | CN-104 |

El detalle (enunciado, fuente, fórmula, implementación, invariantes y riesgos) está en
[`catalogo-reglas.md`](catalogo-reglas.md), sección R-10…R-12.

---

## 9. Handoff

### 9.1 `datos`

1. **No se requiere cambio de esquema** para M-01…M-07.
2. Índices candidatos (medir antes de crear): `viajes (empresa_id, fin_real)` parcial
   `WHERE estado <> 'anulado'`; `viaje_gastos (empresa_id, fecha, estado)` ya existe
   (`0011:74`); `facturas_nucleo (empresa_id, fecha_emision, estado)` no existe (solo
   `(empresa_id, estado, fecha_vencimiento)`, `0013:40-41`).
3. Evaluar **INV-F02/INV-F03 en base** (trigger que rechace pago/NC > saldo). Hoy son
   solo de aplicación; el chat de cartera depende de que el saldo no sea negativo.
4. `fn_viaje_costos` y `viajes.costo_variable_real` no tienen lector: decidir si se
   eliminan, se consumen o se documentan como caché con invalidación (hoy no la tienen).

### 9.2 `backend`

1. Crear las tools económicas en `agente/chat/herramientas.py` y agregarlas a las
   allowlists de `personas.py:104-132`; `agente="gerente"` para M-01/M-02/M-05/M-06/M-07
   y `agente="secretaria"` para M-03/M-04 (o compartidas, con decisión explícita).
2. Implementar los agregados en **SQL** (no reutilizar `aging()` ni `listar_facturas`
   con `LIMIT`): el saldo se filtra en la base.
3. Respetar `[desde, hasta)` y la zona de la empresa; **corregir** el `<=` de
   `servicio_iva.py:68` o no reutilizarlo.
4. Devolver el sobre de §2.7 con `periodo`, `corte`, `moneda` y `advertencias`.
5. No exponer `empresa_id` como argumento; reutilizar `_usuario_empresa_id`
   (`herramientas.py:141-159`).
6. Aplicar permisos: hoy `agente:chat` es solo `admin` (`permisos.py:69-73`). Si el
   dueño quiere que el rol `gerente` consulte, es **AB-02**, no un cambio silencioso.

### 9.3 `qa`

1. CN-101…CN-105 como casos de aceptación con datos sintéticos y `Decimal`.
2. Bordes: `dias_atraso` 0/1/30/31/60/61/90/91; NC/pago exactamente igual al saldo y un
   centavo por encima; gasto `activo=false`; viaje sin chofer; `tracto_id` nulo;
   `fin_real` nulo; factura anulada; factura emitida el último día del período.
3. Zona horaria: viaje con `fin_real` a las 22:30 hora Chile debe caer en el día
   chileno, no en UTC (CN-104).
4. Concurrencia/idempotencia: dos consultas simultáneas no deben duplicar ni bloquear;
   las tools son de lectura y no escriben.
5. Verificar que la respuesta incluye el período usado y que el modelo no lo inventa.

---

## 10. Lo que este documento no afirma

- No afirma que las tools existan: **no existen** (§0).
- No afirma que las pruebas se hayan ejecutado: **no se ejecutó ninguna** en esta sesión.
- No fija la tasa de IVA, el tratamiento de exentas, el crédito fiscal ni el F29: son
  `P-01`/`P-13`.
- No fija la base de la comisión (`D-01`), la composición del margen (`D-23`) ni el
  período (`D-22`).
- No convierte una práctica observada en obligación legal ni contable.
- No propone cambiar la fuente de verdad ni el esquema; solo especifica consultas.
