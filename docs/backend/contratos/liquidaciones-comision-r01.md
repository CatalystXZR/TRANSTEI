# Comisión del conductor — R-01 (contrato verificado)

> **Pregunta que responde:** ¿cómo se calcula y se imputa la comisión del chofer?
> **Dueño:** `backend` · **Verificado:** 2026-10-29 · **Método:** lectura de código + migraciones
> **Caduca si:** cambia `_comision_chofer`, el default de comisión o la regla R-01.
> **Re-verificar con:** `sed -n '51,96p' backend/app/api/routes/liquidaciones.py`

Regla fuente: `docs/negocio/catalogo-reglas.md` R-01 (dueño, 2026-10-29).
Implementación: `backend/app/api/routes/liquidaciones.py:51-96` (`_comision_chofer`).

---

## Fórmula

```
comision      = quantize( Σ valor_flete_neto(viajes imputados al mes) × porcentaje , 0.01 )
total_liquido = sueldo_base + comision + bonos - descuentos - anticipos
```

`Decimal` en todo el cálculo; `quantize(..., 0.01)` al final (`liquidaciones.py:94-95`).

---

## Base de cálculo y mes de imputación

🟢 **La comisión se imputa por la FECHA DE EMISIÓN de la factura**, no por la fecha del
viaje (`liquidaciones.py:53-56`). Corrige SEC-001: un viaje finalizado en octubre y
facturado en noviembre devenga en **noviembre**.

Algoritmo real (`liquidaciones.py:61-91`):

1. Se toman todos los viajes del chofer.
2. Se busca, por viaje, la **primera emisión de factura no anulada**
   (`min(Factura.fecha_emision)`, `Factura.estado != anulada`).
3. Si existe factura: el viaje se imputa al mes `[inicio, fin)` que contiene esa fecha.
4. Si **no** existe factura pero el viaje está `facturado` (dato inconsistente):
   se imputa por `fecha_fin or fecha_inicio` para no perder la comisión.

Consecuencias:

- Solo viajes con factura no anulada devengan comisión.
- Un viaje `finalizado` sin factura **no** devenga.
- `public.estado_viaje` no tiene estados posteriores a `facturado`
  (`supabase/migrations/0001_esquema_base.sql:12`); `cobrado`/`cerrado`/`anulado`
  son de `nucleo.estado_viaje` y no aplican a esta ruta legacy.
- Cobrado vs. facturado: el pago se registra en `facturas.estado`, no en el viaje.

---

## Porcentaje

| Dónde | Valor |
|---|---|
| `public.choferes.porcentaje_produccion` | configurable por chofer |
| Default del modelo | **0.10** (`backend/app/models/__init__.py:103-105`) |
| Default del schema de alta | **0.10** (`backend/app/schemas/catalogos.py:34-36`) |
| Default del núcleo | **0.10** (`backend/app/nucleo/models.py:584-586`) |
| Default en la base | **0.10** (`0017_default_comision_chofer.sql:47-48`) |
| Datos del piloto | **10 %** (`0019_comision_piloto_10.sql`) |

Las brechas de "default = 0" del contrato anterior están **cerradas** por 0017 y 0019.

---

## Contrato HTTP

- `GET /api/v1/liquidaciones/resumen?mes=YYYY-MM`
- `POST /api/v1/liquidaciones/calcular?chofer_id=...&mes=YYYY-MM`
- `GET /api/v1/liquidaciones/{id}/pdf`
- Campos: `comision`, `total`, `total_liquido`, etc.

**Autorización** (SEC-008 corregido): lectura y escritura restringidas a
`admin` y `contabilidad` (`liquidaciones.py:30-31`).

---

## Brechas abiertas

| Brecha | Ubicación | Dueño | Impacto |
|---|---|---|---|
| El KPI de comisión suma `finalizado + facturado` y usa `fecha_fin`, contra R-01 | `backend/app/services/kpi_engine.py:368-381` | `negocio-finanzas` / `backend` | El tablero **sobreestima** la comisión del mes |
| El PDF recalcula comisión, bonos y descuentos en vivo (SEC-002) | `liquidaciones.py:515-533` | `backend` / `datos` | Un documento firmado no es reproducible |
| `fecha_fin` se estampa con `date.today()` al finalizar (R-03) | `backend/app/api/routes/viajes.py:245-246` | dueño | El mes del viaje puede no ser el real |
| Doble fuente del porcentaje (`public.choferes` vs `nucleo.choferes`) | SEC-003 | `datos` | Divergencia entre capas |

---

## Historial

| Fecha | Cambio |
|---|---|
| 2026-10-29 | SEC-001 corregido: imputación por fecha de emisión |
| 2026-10-29 | SEC-008 corregido: lectura restringida a admin/contabilidad |
| 2026-10-29 | Defaults de comisión alineados a 10 % (0017, 0019) |
