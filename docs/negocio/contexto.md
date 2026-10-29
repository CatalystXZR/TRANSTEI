# Contexto de negocio — ERP Transportes TEI SpA

> **Pregunta que responde:** ¿qué negocio modela el ERP y qué se puede afirmar sin inventar?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-10-29 · **Método:** lectura de código y DDL
> **Caduca si:** cambia el modelo de viajes, tarifas, OC, facturación o liquidación.
> **Re-verificar con:** `rg "class (Viaje|Tarifa|OrdenCompra|FacturaNucleo|Liquidacion)" backend/app/nucleo/models.py backend/app/models/__init__.py`

## 0. Límite de esta reconstrucción

`docs/_archivo/` **no contiene un documento de contexto del dueño**: las notas
originales fueron retiradas del repo por contener datos sensibles. Este documento **no
reconstruye historia, socios, deudas, clientes ni tarifas reales**; describe solo lo
que el modelo de datos afirma.

| Tema | Nivel | Por qué |
|---|---|---|
| El negocio es transporte de carga terrestre vendido por viaje | 🟢 | El agregado central es `nucleo.viajes`, con origen, destino, carga, equipo y flete (`backend/app/nucleo/models.py:699-809`) |
| Fundación, socios, estrategia, deuda, cartera real | 🔴 | Sin fuente en el repo |
| Tarifas, metas y volúmenes reales | 🔴 | El código define modalidades y campos; los valores son datos de la empresa |
| Obligaciones tributarias, laborales o de seguro | 🔴 | No se deducen del código; ver `preguntas.md` |

El sistema se configura con país `CL`, moneda `CLP` y zona `America/Santiago`
(`backend/app/nucleo/models.py:216-218`). Es configuración del software, **no** una
afirmación sobre el régimen legal aplicable.

## 1. La unidad económica: el viaje

Un viaje vende un servicio de transporte entre origen y destino, con ventana
planificada, vehículo, conductor y carga. El núcleo registra:

| Dimensión | Campos | Evidencia |
|---|---|---|
| Tiempo | `inicio_planificado`, `fin_planificado`, `inicio_real`, `fin_real`, `buffer_minutos` | `backend/app/nucleo/models.py:715-720` |
| Carga | tipo, pesos, tara, volumen, bultos, dimensiones, peligrosa, refrigerada, sobredimensionada | `backend/app/nucleo/models.py:728-757` |
| Ruta | origen/destino, `distancia_km`, `km_vacios` | `backend/app/nucleo/models.py:760-776` |
| Dinero | `valor_flete_neto`, `monto_recargos`, `monto_total_neto` calculado, moneda | `backend/app/nucleo/models.py:787-797` |
| Condiciones | `condiciones_pago_dias`, `tarifa_snapshot`, `oc_numero_snapshot` | `backend/app/nucleo/models.py:798-803` |

El ingreso del viaje es **neto**: `valor_flete_neto + monto_recargos`
(`backend/app/nucleo/models.py:789-796`). El IVA vive en la factura, no en el viaje
(`supabase/migrations/0013_facturacion.sql:19-21`). El legacy `public.viajes` es más
simple: cuatro estados, un flete neto, sin recargos, tarifa ni snapshot
(`backend/app/models/__init__.py:140-156`).

## 2. Recursos productivos

El servicio se ejecuta con **tracto + rampla + chofer**. Una asignación completa ocupa
el libro de ocupación y dispara la validación documental; una parcial (borrador) no
ocupa (`supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql:18-35`).

| Recurso | Modelo | Evidencia |
|---|---|---|
| Tracto | patente, km, vencimientos, capacidad | `supabase/migrations/0004_nucleo_operacional.sql:191-234` |
| Rampla | 8 tipos: plana, sider, refrigerada, portacontenedor, cisterna, cama baja, granelera, otra | `backend/app/nucleo/models.py:101-109` |
| Chofer | licencia, exámenes, autorización de carga peligrosa, sueldo, comisión | `backend/app/nucleo/models.py:561-598` |

Toda asignación completa queda en `nucleo.reservas_recurso`, que no admite solapamientos
para tracto, rampla ni chofer (tres `EXCLUDE`,
`supabase/migrations/0004_nucleo_operacional.sql:746-756`). Dos borradores **parciales**
sí pueden solaparse en el papel, porque no reservan (0015:30-35). La mantención se
planifica por pauta e intervalo de km (`backend/app/models/__init__.py:244-266`); su
costo se registra, pero no se prorratea automáticamente a cada viaje.

## 3. Personas y roles

El núcleo define ocho roles: `admin`, `gerente`, `despacho`, `contador`, `tesoreria`,
`taller`, `conductor` y `auditor` (`backend/app/nucleo/models.py:79-87`). Los permisos
se resuelven en el backend; la UI solo los refleja.

El conductor tiene dos conceptos económicos separados:

- **Sueldo base** y **comisión** por producción (`backend/app/nucleo/models.py:582-586`;
  `backend/app/models/__init__.py:101-105`).
- **Anticipos** y **ajustes** (bonos/descuentos) por mes (`backend/app/models/__init__.py:202-223`).

La liquidación suma haberes y resta descuentos/anticipos
(`backend/app/api/routes/liquidaciones.py:438-446`). Las reglas previsionales,
tributarias y de gratificación **no están modeladas**: `P-02`.

## 4. Ciclo operativo

El núcleo modela 14 estados con transiciones explícitas
(`supabase/migrations/0004_nucleo_operacional.sql:779-808`):

```
borrador → cotizado → confirmado → asignado → en_carga → cargado → en_ruta
→ en_descarga → descargado → pod_pendiente → cerrado → facturado → cobrado
```

`anulado` es terminal y libera recursos
(`supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql:29`). `facturado` y
`cobrado` no se eligen a mano: los dispara la facturación y el pago
(`supabase/migrations/0013_facturacion.sql:202-210`). El legacy usa solo `programado →
en_ruta → finalizado → facturado` (`supabase/migrations/0001_esquema_base.sql:12`).

## 5. Ciclo documental

Antes de despachar, el núcleo exige documentos vigentes por recurso
(`supabase/migrations/0004_nucleo_operacional.sql:1041-1074`):

| Recurso | Documentos |
|---|---|
| Tracto | revisión técnica, permiso de circulación, seguro obligatorio; SOAP y permisos especiales según configuración/carga |
| Rampla | revisión técnica y adicionales según tipo de carga |
| Chofer | licencia de conducir, examen médico; curso de carga peligrosa si aplica |

Un documento faltante o vencido antes del fin efectivo del viaje produce `23514`
(`0004:1091-1101`). La clase A5 es regla del dueño; su origen (legal, seguro o interno)
es `P-03` (ver `R-02`).

Además, el núcleo registra paradas, checklist, eventos, incidentes y documentos
(`supabase/migrations/0007_expediente.sql:17-181`), y un POD con firma, fotos,
receptor y geolocalización (`supabase/migrations/0009_pod.sql:8-45`). Sin POD no se
puede facturar (`supabase/migrations/0009_pod.sql:80-87`).

## 6. Ciclo económico

**6.1 Precio.** La tarifa del núcleo se define por cliente y modalidad: viaje, km,
tonelada, tonelada-km, hora o contenedor (`backend/app/nucleo/models.py:150-158,301-327`).
El flete se calcula en backend con `Decimal` y se compara contra el mínimo de cobro
(`backend/app/nucleo/tarifas.py:27-86`); los recargos se suman aparte
(`backend/app/nucleo/servicio_disponibilidad.py:914`). El viaje guarda snapshot de la
tarifa usada (`supabase/migrations/0004_nucleo_operacional.sql:966-993`), de modo que
un cambio posterior no reescribe el histórico.

**6.2 Orden de compra.** La OC tiene monto autorizado, sobregiro y consumo
(`backend/app/nucleo/models.py:361-404`). El consumo se **recalcula** sumando los viajes
no borrador/cotizado/anulados, no se incrementa a ciegas
(`supabase/migrations/0004_nucleo_operacional.sql:1574-1595`). La OC es requisito para
facturar, no para despachar (`backend/app/nucleo/politicas.py:390-400`;
`supabase/migrations/0009_pod.sql:89-93`). Si debe cambiar, es `D-05`.

**6.3 Factura.** Agrupa viajes cerrados, con OC y POD; `total = neto + iva` se calcula
en la base (`supabase/migrations/0013_facturacion.sql:10-38`). El folio es **simulado**:
no hay DTE real (`0013:4`; `backend/app/nucleo/servicio_facturacion.py:548-556`). La
tasa de IVA llega como parámetro del request, default `0.19`
(`backend/app/nucleo/schemas.py:1543`; `backend/app/nucleo/servicio_facturacion.py:544`).
Su validez tributaria y la del folio son `P-01`/`P-06`.

**6.4 Cobro.** Los pagos pueden ser parciales; pagos y notas de crédito recalculan
saldo y estado (`supabase/migrations/0013_facturacion.sql:163-211`). Al quedar pagada,
los viajes pasan a `cobrado` (`0013:202-210`). El aging se calcula por **saldo** y fecha
de vencimiento (`backend/app/nucleo/servicio_facturacion.py:714-729`). Facturar no es
cobrar: son tablas y estados distintos (`0013:10-98`).

**6.5 Costo y margen.** El costo del viaje suma gastos aprobados más comisión estimada
(`backend/app/nucleo/servicio_gastos.py:446-465`). El margen es ingreso menos costo
variable (`servicio_gastos.py:461-466`); la rentabilidad agrega costo fijo asignado,
tarifa piso y Freight Score (`backend/app/nucleo/servicio_rentabilidad.py:192-221`).
Hay al menos tres implementaciones de margen; ver `implementacion.md` §2.

**6.6 Nómina.** La liquidación mensual compone sueldo base, comisión, bonos, anticipos y
descuentos. La comisión legacy se atribuye por la **fecha de emisión de la factura**, no
por la del viaje (`backend/app/api/routes/liquidaciones.py:51-96`). La base exacta (neto
o total con IVA/recargos) es `D-01`.

## 7. Dos esquemas, un mismo negocio

- `public` es el legacy: `0001`–`0003`, sin `empresa_id`, viaje simplificado
  (`supabase/migrations/0001_esquema_base.sql:36-212`).
- `nucleo` es el destino: empresas, roles, disponibilidad, expediente, OC, tarifas,
  facturación y auditoría (`supabase/migrations/0004_nucleo_operacional.sql:102-850`).

No se debe introducir una tercera fuente de verdad. Qué esquema manda por concepto se
decide en `docs/arquitectura/fuentes-de-verdad.md`; las migraciones aplicadas, en
`docs/estado.md`.

## 8. Preguntas de contexto abiertas

El registro único está en [`preguntas.md`](preguntas.md). Condicionan este contexto:
`D-01` base de la comisión · `D-02` origen de A5 · `D-03` fecha real de término ·
`D-04` Freight Score como bloqueo · `D-05` OC en despacho vs facturación ·
`D-06` metas y dueños de KPI · `P-01` IVA/F29 · `P-02` nómina · `P-03` seguro ·
`P-04` tributación de la comisión.

Lo que el código no puede responder (historia, deuda, caja, cartera, contratos,
metas reales y régimen legal) queda 🔴 y solo lo responde el dueño o un asesor.
