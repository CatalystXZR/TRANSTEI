# KPIs y Freight Score — qué se calcula de verdad

> **Pregunta que responde:** ¿qué indicadores existen, con qué fórmula y con qué datos?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-10-29 · **Método:** lectura de código + conteo del catálogo histórico
> **Caduca si:** cambia `kpi_engine.py`, el catálogo de 90 KPIs o el servicio de rentabilidad.
> **Re-verificar con:** `grep -c '^| [0-9]\+ |' docs/_archivo/mvp/CATALOGO_KPIS_Y_FREIGHT_SCORE.md` y `sed -n '38,64p' backend/app/services/kpi_engine.py`

## 1. El motor real de KPIs

### 1.1 Qué es y qué no es

`backend/app/services/kpi_engine.py` evalúa fórmulas de texto definidas por el
usuario sobre un **catálogo cerrado** de métricas. No traduce a SQL ni ejecuta código
arbitrario: parsea con `ast` y recorre solo nodos permitidos
(`kpi_engine.py:1-7,11,116,129-239`). Cualquier expresión fuera de la lista blanca
termina en error (`kpi_engine.py:239`).

| Pieza | Implementación | Evidencia |
|---|---|---|
| Entrada | fórmula de texto + diccionario de valores | `kpi_engine.py:109-120` |
| Parseo | `ast.parse(texto, mode="eval")` | `kpi_engine.py:116` |
| Nodos | constantes, nombres, binarios, unarios, comparaciones, lógicos y llamadas | `kpi_engine.py:129-239` |
| Funciones | `SI`/`IF`, `REDONDEAR`/`ROUND`, `MIN`, `MAX`, `ABS`/`ABSOLUTO` | `kpi_engine.py:66-74,203-237` |
| Alias | `Y`→`and`, `O`→`or`; `=`→`==` sin tocar `<=`, `>=`, `!=` | `kpi_engine.py:90-96` |
| Nombres | métricas en minúsculas; `NOMBRE` y `nombre` son la misma clave | `kpi_engine.py:137-141` |
| Cortocircuito | `SI` evalúa **solo** la rama elegida, evita división por cero | `kpi_engine.py:211-217` |
| Colores | primera regla que se cumple; si ninguna, gris | `kpi_engine.py:270-283` |
| Validación | métricas usadas contra el catálogo del ámbito | `kpi_engine.py:537-545` |

### 1.2 Las 22 métricas (17 globales + 5 de viaje)

Globales (`kpi_engine.py:38-56`): `ingresos_mes`, `gastos_mes`, `margen_bruto`,
`margen_pct`, `cuentas_por_cobrar`, `cuentas_atrasadas`, `iva_a_pagar`,
`facturacion_mes`, `viajes_mes`, `viajes_activos`, `flete_promedio`,
`costo_mantenimiento_mes`, `mantenimientos_pendientes`, `vencimientos_30d`,
`comision_total_mes`, `costo_choferes_mes`, `choferes_activos`.

De viaje (`kpi_engine.py:58-64`): `flete_viaje`, `gastos_viaje`, `comision_viaje`,
`margen_viaje`, `margen_viaje_pct`.

El período por defecto es el mes en curso; `periodo=YYYY-MM` lo acota a
`[inicio, mes siguiente)` (`kpi_engine.py:289-300`). Los ingresos se atribuyen por
`coalesce(fecha_fin, fecha_inicio)` del viaje (`kpi_engine.py:312-320`); la
facturación, por `fecha_emision` (`kpi_engine.py:343-351`).

### 1.3 Advertencia: calcula en `float`

`evaluar_formula()` devuelve `float` (`kpi_engine.py:109-126`); `_a_numero()` convierte
incluso `Decimal` a `float` (`kpi_engine.py:99-106`), y el resultado final se publica
como `float` (`kpi_engine.py:441-459` y `518-523`). **No es apto para contabilidad
exacta**: sirve para tableros y semáforos. Para dinero, la fuente son los servicios
con `Decimal` (`servicio_gastos.py`, `servicio_rentabilidad.py`, `liquidaciones.py`).

### 1.4 Endpoints y persistencia

Las rutas legacy viven en `backend/app/api/routes/kpis.py:38-193`
(`/kpis/catalogo`, `/kpis/valores`, `/kpis/preview`, CRUD de `/kpis`). La definición
persistida `kpis` guarda nombre, ámbito, fórmula, formato, período, colores, uso y
orden (`backend/app/models/__init__.py:276-292`). **No guarda meta ni dueño**, y no
hay tabla de snapshots históricos: el valor se recalcula al consultar.

## 2. Matriz de implementación de los 90 KPIs

El catálogo histórico tiene **90 KPIs** (conteo reproducible con el comando de la
cabecera: 10 dueño, 15 comerciales, 17 operacionales, 11 combustible/mantención, 19
financieros, 10 personas/seguridad y 8 datos/sistema;
`docs/_archivo/mvp/CATALOGO_KPIS_Y_FREIGHT_SCORE.md:67-202`). De esos, **7 tienen hoy
una métrica del motor que aproxima su fórmula**, ninguno la cumple por completo.

| # | KPI del catálogo | Métrica del motor | Qué falta para cumplir la fórmula |
|---|---|---|---|
| 3 | Margen del mes | `margen_pct` | Usa ingreso sin recargos y solo gastos de viaje; no incluye costo fijo ni comisión |
| 5 | CxC vencidas | `cuentas_atrasadas` | Da el monto vencido, no el `% de CxC` ni los tramos de aging |
| 11 | Ingreso devengado | `ingresos_mes` | Solo `valor_flete_neto` (sin recargos) y por fecha de fin, no por devengo formal |
| 12 | Facturación | `facturacion_mes` | Suma `Factura.total` (con IVA); no distingue neto/bruto ni notas de crédito |
| 14 | Ticket promedio | `flete_promedio` | Ingreso sin recargos dividido por viajes finalizados/facturados |
| 55 | Margen bruto | `margen_bruto` | Resta gastos del viaje, no costo directo total ni comisión |
| 70 | IVA a pagar | `iva_a_pagar` | Estimación interna: débito de facturas y crédito calculado desde gastos; no es F29 |

**Dato existe, KPI no implementado (nivel 🟡):** disponibilidad de camiones (#7, hay
`reservas_recurso`), cumplimiento de OC (#25, hay OC y `viaje.orden_compra_id`),
documentos al día y licencias vencidas (#37/#76, hay `documentos` con `vence_en`),
viajes con POD (#39, hay `pod`), viajes sin facturar (#40, ya se cuenta como alerta),
rendimiento y costo de combustible (#43/#45, hay litros y odómetro en gastos),
costo por viaje (#59, lo calcula `servicio_gastos`), completitud de gastos (#84, hay
`respaldo_url`).

**Sin fuente de datos (nivel 🔴):** caja y banco (#1, #2, #65, #71), cotizaciones y
win rate (#17, #18), neumáticos (#49), cuentas por pagar y CCC/DPO (#63, #64),
depreciación/intereses/impuestos y presupuesto (#56, #57, #58, #68, #69), horas,
ausentismo, rotación, capacitación y clima (#73-#75, #78-#82), MTBF/MTTR y
disponibilidad mecánica (#50, #51). No existen tablas de banco, cotización,
neumático, CxP, presupuesto ni RRHH en `supabase/migrations/`.

## 3. KPIs implementados que NO están en el catálogo

| Métrica | Qué mide | Evidencia |
|---|---|---|
| `gastos_mes` | Gastos de viaje del período | `kpi_engine.py:321-327` |
| `viajes_activos` | Viajes programados o en ruta *ahora* | `kpi_engine.py:361-367` |
| `cuentas_por_cobrar` | Saldo de todas las facturas pendientes | `kpi_engine.py:328-334` |
| `comision_total_mes` | Comisión devengada por viajes del mes | `kpi_engine.py:369-381` |
| `costo_choferes_mes` | Sueldos base activos + comisión del mes | `kpi_engine.py:383-390,457` |
| `choferes_activos` | Dotación activa | `kpi_engine.py:383-385` |
| `margen_viaje_pct` | Margen del viaje sobre el flete | `kpi_engine.py:516-523` |

`margen_viaje_pct` es el caso más delicado: usa la comisión del chofer y los gastos
del viaje, pero **no** el costo fijo asignado; no es el margen del Freight Score.

## 4. Freight Score

### 4.1 Qué está construido

Está implementado en `backend/app/nucleo/servicio_rentabilidad.py`, con `Decimal` y
redondeo `ROUND_HALF_UP` (`:9-10,65-66`). Pesos exactos del catálogo
**30/20/15/15/10/10** (`:43-50`):

| Componente | Peso | Cálculo | Evidencia |
|---|---:|---|---|
| `margen_pct` | 0,30 | `clamp(margen_pct / margen_objetivo)` | `:193-195,210-212` |
| `margen_km` | 0,20 | `clamp(margen_km / benchmark_margen_km)` | `:196-200,213-217` |
| `pago` | 0,15 | tramos ≤30 / 31-45 / 46-60 / 61-90 / >90 | `:69-78,218` |
| `utilizacion` | 0,15 | `clamp(peso / capacidad)` | `:219,307-311` |
| `retorno` | 0,10 | cargado 1,00 / parcial 0,60 / vacío cercano 0,30 / sin alternativa 0 | `:52-58,220` |
| `riesgo` | 0,10 | `clamp(1 − puntos/10)` | `:221` |

El total se compone por aporte y se redondea a 2 decimales (`:236-252`); el semáforo
es verde ≥80, amarillo ≥60, rojo <60 (`:253`). Se persiste en
`viaje.freight_score_estimado` y `freight_score_detalle` (`:398-416`).

- **Endpoint:** `POST /nucleo/rentabilidad/simulador` y
  `GET /nucleo/expediente/viajes/{id}/rentabilidad`
  (`backend/app/nucleo/api_rentabilidad.py:53-69`).
- **Pantalla:** `/rentabilidad` (`frontend/src/app/(app)/rentabilidad/page.tsx:55-75`).
- **Prueba:** `backend/tests/test_nucleo_rentabilidad.py:144` (6 componentes en
  `:253`). **Ojo:** se omite si falta `NUCLEO_TEST_DATABASE_URL`
  (`test_nucleo_rentabilidad.py:46`), así que en un entorno sin base no prueba nada.

### 4.2 Qué del catálogo NO está

| Pieza del catálogo | Estado | Evidencia |
|---|---|---|
| Benchmark = mediana de 90 días por ruta/tipo de equipo | 🔴 No se calcula: es un valor fijo configurado por empresa (default 1.200) | `backend/app/nucleo/models.py:1112-1114`; `servicio_rentabilidad.py:213-217` |
| Utilización volumétrica (m³) y mezcla peso/volumen | 🔴 Solo peso / capacidad; no usa `volumen_m3` | `servicio_rentabilidad.py:307-311,360-362` |
| Riesgo de 7 factores | 🟡 Solo 3: carga peligrosa (+3), sobredimensión (+2), refrigerada (+1) | `servicio_rentabilidad.py:380-386` |
| Recargo por diésel (catálogo §10.4) | 🔴 `precio_diesel` y `rendimiento_km_l` se guardan, pero no se usan en ningún cálculo | `models.py:1121-1122`; sin uso en `servicio_rentabilidad.py` |
| Punto de equilibrio mensual (§10.3) | 🔴 No implementado | No hay función equivalente |
| Retorno "no aplica" | 🟡 Agrega 0,30, valor que el catálogo no define | `servicio_rentabilidad.py:57` |

La tarifa piso sí está: estratégica = `costo_total / (1 − margen_objetivo)`
(`:203-207`) y táctica = `costo_variable + contribución_mínima` (`:208`), alineadas
con el catálogo §10.1-10.2.

## 5. Dos tableros que no son el mismo

| Tablero | Fuente | Qué muestra |
|---|---|---|
| `/dashboard` (legacy) | `public` + `kpi_engine` | Resumen del mes, CxC, gastos, viajes activos y tarjetas KPI (`frontend/src/app/(app)/dashboard/page.tsx:52-54`; `backend/app/api/routes/dashboard.py:42-97`) |
| `/tablero` (núcleo) | `nucleo` | Alertas por categoría: documentos, mantención, POD, facturación, OC, CxC, margen, incidentes, caja (`frontend/src/app/(app)/tablero/page.tsx:33-44`; `backend/app/nucleo/api_alertas.py:24-28`) |

Ambos aparecen en el menú (`frontend/src/lib/navigation.ts:48-49`). **No conciliar uno
contra el otro:** leen esquemas distintos, con estados de viaje distintos (el legacy
cuenta `programado`/`en_ruta`, `dashboard.py:84-86`; el núcleo tiene 14 estados,
`models.py:125-139`). Un mismo rótulo puede dar cifras diferentes sin que ninguna
esté "mal": miden universos distintos.

## 6. Advertencias para `datos` / `backend` / `qa`

1. `kpi_engine` es `float`: no usar sus valores para liquidar, facturar ni conciliar.
2. No hay snapshot histórico de KPI ni versionado de fórmulas: un cambio de fórmula
   reescribe el pasado al recalcular.
3. No hay meta ni dueño en la tabla `kpis`: las metas del catálogo son propuestas
   (`CATALOGO...:474-476`), no configuración vigente. Ver `D-06`.
4. El catálogo de 90 KPIs es una **visión objetivo**, no un inventario implementado.
