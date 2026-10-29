> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# CATÁLOGO DE KPIs Y FREIGHT SCORE
## Transportes TEI SpA — definiciones, fórmulas, metas y uso

**Versión:** 2.0  
**Fecha:** Octubre 2026  
**Uso:** dueño, gerencia, operaciones, contabilidad y BI

> **Regla de oro:** un KPI sin dueño, meta, frecuencia y acción es un adorno.  
> **Regla de datos:** si el dato no está registrado, el KPI no existe.  
> **Regla de negocio:** el margen de contribución sirve para decidir un viaje; el margen neto sirve para evaluar la empresa.

---

## 1. Definiciones base

### 1.1 Los tres ingresos

| Concepto | Definición | Fecha de reconocimiento | Uso |
|---|---|---|---|
| **Ingreso devengado** | Flete neto de viajes finalizados o facturados, más recargos | Fecha de fin del viaje | Margen operacional |
| **Facturación** | Total de facturas no anuladas emitidas | Fecha de emisión | Flujo tributario y cobranza |
| **Cobranza** | Dinero efectivamente recibido | Fecha de pago | Caja |

No mezclar los tres. Un mes puede tener facturación alta, cobranza baja y caja negativa.

### 1.2 Márgenes

| Margen | Fórmula | Qué incluye | Para qué |
|---|---|---|---|
| **Margen de contribución** | Ingreso devengado − costos variables directos | Combustible, peajes, viáticos, comisión, mantenimiento variable, neumáticos variables, factoring | Decidir si un viaje conviene |
| **Margen bruto** | Ingreso devengado − costo directo total | Incluye costos directos fijos imputados (chofer base, mantenimiento, seguro, depreciación) | Evaluar rentabilidad operativa |
| **EBITDA** | Margen bruto − gastos fijos operativos − administración | Excluye depreciación, intereses e impuestos | Evaluar operación |
| **Utilidad neta** | EBITDA − depreciación − intereses − impuestos | Todo | Evaluar empresa |

### 1.3 Costos

| Concepto | Definición |
|---|---|
| **Costo variable** | Cambia con el km, el viaje o la carga |
| **Costo fijo** | Existe aunque no haya viajes (seguro, permisos, sueldos base, arriendo) |
| **Costo directo** | Se puede imputar a un viaje/unidad |
| **Costo indirecto** | Se prorratea (administración, taller, supervisión) |
| **Costo estándar** | Presupuesto técnico por km/ruta |
| **Costo real** | Lo efectivamente pagado |
| **Desviación** | Real − estándar |

### 1.4 Unidades

- **Km:** kilómetros recorridos.
- **Km productivos:** con carga.
- **Km vacíos:** sin carga (deadhead + retorno).
- **Tonelada-km:** toneladas transportadas × km.
- **Litros:** combustible.
- **Horas:** conducción, espera, taller, disponibilidad.
- **CLP:** pesos chilenos, sin decimales en reportes ejecutivos.
- **DIO:** días de inventario = (inventario promedio / costo de ventas) × días.
- **DSO:** días de cobro = (cuentas por cobrar / facturación) × días.
- **DPO:** días de pago = (cuentas por pagar / compras) × días.
- **CCC:** ciclo de conversión de caja = DSO + DIO − DPO.

---

## 2. KPIs del dueño (tablero diario)

| # | KPI | Fórmula | Frecuencia | Meta | Dueño | Acción si falla |
|---|---|---|---|---|---|---|
| 1 | **Caja disponible** | Saldo bancario + caja chica − sobregiros | Diaria | ≥ 1 mes de costos fijos | Tesorería | Activar cobranza/factoring |
| 2 | **Caja proyectada 13 semanas** | Caja inicial + cobros − pagos | Semanal | Nunca < mínimo | Tesorería | Ajustar pagos/cobros |
| 3 | **Margen del mes** | (Ingreso devengado − costo total) / ingreso | Mensual | ≥ objetivo (ej. 15%) | Dueño | Revisar precio/costo |
| 4 | **Margen por tracto disponible** | Margen neto / tractos disponibles | Mensual | ≥ meta | Dueño | Revisar flota/clientes |
| 5 | **CxC vencidas** | Σ facturas pendientes con vencimiento < hoy | Diaria | < 10% de CxC | Cobranza | Llamar/cobrar |
| 6 | **DSO** | (CxC / facturación) × días | Mensual | ≤ 35 días | Cobranza | Dunning/factoring |
| 7 | **Camiones disponibles** | Tractos asignables / tractos activos | Diaria | ≥ 20% | Operaciones | Reasignar/mantener |
| 8 | **Utilización** | Km productivos / km disponibles | Semanal | ≥ 75% | Operaciones | Buscar carga |
| 9 | **Viajes con margen bajo** | Viajes con contribución < piso / total | Semanal | ≤ 5% | Comercial | Renegociar |
| 10 | **Alertas críticas abiertas** | Alertas críticas sin resolver | Diaria | 0 | Dueño | Resolver |

---

## 3. KPIs comerciales

| # | KPI | Fórmula | Frecuencia | Meta | Dueño | Acción |
|---|---|---|---|---|---|---|
| 11 | **Ingreso devengado** | Σ fletes netos + recargos de viajes finalizados/facturados | Mensual | Presupuesto | Comercial | Plan comercial |
| 12 | **Facturación** | Σ facturas no anuladas emitidas | Mensual | Presupuesto | Contabilidad | Emitir pendientes |
| 13 | **Cobranza** | Σ pagos recibidos | Mensual | Facturación × % | Tesorería | Cobrar |
| 14 | **Ticket promedio** | Ingreso devengado / viajes | Mensual | Creciente | Comercial | Mix de carga |
| 15 | **Tarifa media $/km** | Ingreso devengado / km facturados | Mensual | ≥ costo/km + margen | Comercial | Ajustar tarifas |
| 16 | **Tarifa media $/ton** | Ingreso devengado / toneladas | Mensual | Benchmark | Comercial | Negociar |
| 17 | **Win rate** | Cotizaciones ganadas / cotizaciones enviadas | Mensual | ≥ 30% | Comercial | Revisar precio/velocidad |
| 18 | **Ciclo de cotización** | Días entre solicitud y respuesta | Semanal | ≤ 1 día | Comercial | Estandarizar |
| 19 | **Concentración top 5** | Ingreso top 5 clientes / ingreso total | Mensual | ≤ 50% | Dueño | Diversificar |
| 20 | **Retención de clientes** | Clientes activos que repiten / clientes activos | Trimestral | ≥ 80% | Comercial | Plan de cuenta |
| 21 | **Margen por cliente** | (Ingreso − costo) / ingreso por cliente | Mensual | ≥ objetivo | Comercial | Renegociar/descartar |
| 22 | **DSO por cliente** | (CxC cliente / facturación cliente) × días | Mensual | ≤ 35 | Cobranza | Política de crédito |
| 23 | **Reclamos por cliente** | Reclamos / viajes | Mensual | ≤ 1% | Operaciones | Causa raíz |
| 24 | **Descuento promedio** | (Tarifa lista − tarifa facturada) / tarifa lista | Mensual | ≤ 5% | Comercial | Control de fuga |
| 25 | **Cumplimiento de OC** | Viajes con OC / viajes que requieren OC | Semanal | 100% | Despacho | Bloquear sin OC |

---

## 4. KPIs operacionales

| # | KPI | Fórmula | Frecuencia | Meta | Dueño | Acción |
|---|---|---|---|---|---|---|
| 26 | **Utilización de flota** | Horas productivas / horas disponibles | Semanal | ≥ 75% | Operaciones | Buscar carga |
| 27 | **Km vacíos** | Km sin carga / km totales | Semanal | ≤ 15% | Operaciones | Backhaul |
| 28 | **Viajes por tracto/mes** | Viajes / tractos activos | Mensual | Según ruta | Operaciones | Mix/rutas |
| 29 | **On-time pickup** | Recogidas a tiempo / total | Semanal | ≥ 95% | Despacho | Planificar |
| 30 | **On-time delivery** | Entregas a tiempo / total | Semanal | ≥ 95% | Operaciones | ETA/alertas |
| 31 | **OTIF** | Entregas a tiempo y completas / total | Semanal | ≥ 92% | Operaciones | Causa raíz |
| 32 | **Estadía promedio** | Horas de espera / viajes | Semanal | ≤ 3 h | Operaciones | Cobrar detención |
| 33 | **Ciclo del viaje** | Horas entre carga y descarga | Semanal | Según ruta | Operaciones | Rediseñar |
| 34 | **Disponibilidad mecánica** | Horas disponibles / horas totales | Semanal | ≥ 90% | Taller | Preventivo |
| 35 | **Cumplimiento preventivo** | Preventivos a tiempo / programados | Mensual | ≥ 95% | Taller | Planificar |
| 36 | **Incidentes/100.000 km** | Incidentes × 100.000 / km | Mensual | Tendencia a 0 | Seguridad | Capacitación |
| 37 | **Documentos al día** | Documentos vigentes / total | Semanal | 100% | Cumplimiento | Alertas |
| 38 | **Viajes con documentación completa** | Viajes con checklist completo / total | Semanal | 100% | Despacho | Checklist |
| 39 | **Viajes con POD** | Viajes con POD / viajes entregados | Semanal | 100% | Despacho | Bloquear factura |
| 40 | **Viajes sin facturar** | Viajes entregados sin factura / total | Semanal | 0 | Contabilidad | Facturar |
| 41 | **Días entrega-factura** | Días promedio entre POD y factura | Mensual | ≤ 3 | Contabilidad | Automatizar |
| 42 | **Tiempo de despacho** | Minutos entre viaje confirmado y asignado | Semanal | ≤ 30 min | Despacho | Mesa de despacho |

---

## 5. KPIs de combustible y mantenimiento

| # | KPI | Fórmula | Frecuencia | Meta | Dueño | Acción |
|---|---|---|---|---|---|---|
| 43 | **Rendimiento** | Km / litros | Semanal | Según unidad/ruta | Operaciones | Revisar conductor/ruta |
| 44 | **L/100 km** | Litros / km × 100 | Semanal | Benchmark | Operaciones | Eficiencia |
| 45 | **Costo combustible/km** | $ combustible / km | Mensual | Presupuesto | Operaciones | Precio/consumo |
| 46 | **Desviación de consumo** | (Real − estándar) / estándar | Semanal | ≤ 3% | Operaciones | Investigar |
| 47 | **Transacciones anómalas** | Anomalías / transacciones | Semanal | ≤ 1% | Auditoría | Investigar |
| 48 | **Costo mantenimiento/km** | $ mantenimiento / km | Mensual | Benchmark | Taller | Preventivo |
| 49 | **Costo neumáticos/km** | $ neumáticos / km | Mensual | Benchmark | Taller | Rotación/presión |
| 50 | **MTBF** | Km / fallas | Mensual | Creciente | Taller | Causa raíz |
| 51 | **MTTR** | Horas de reparación / fallas | Mensual | Decreciente | Taller | Repuestos/proceso |
| 52 | **% órdenes con repuestos** | Órdenes con repuesto / órdenes | Mensual | ≥ 80% | Taller | Inventario |
| 53 | **Costo total/km** | Costo total flota / km | Mensual | Benchmark | Dueño | Plan de flota |

---

## 6. KPIs financieros

| # | KPI | Fórmula | Frecuencia | Meta | Dueño | Acción |
|---|---|---|---|---|---|---|
| 54 | **Margen de contribución** | Ingreso − costos variables | Mensual | ≥ objetivo | Dueño | Precio/costo |
| 55 | **Margen bruto** | Ingreso − costo directo total | Mensual | ≥ objetivo | Dueño | Eficiencia |
| 56 | **EBITDA** | Margen bruto − gastos fijos | Mensual | Presupuesto | Dueño | Costos |
| 57 | **Utilidad neta** | EBITDA − depreciación − intereses − impuestos | Mensual | Presupuesto | Dueño | Gestión |
| 58 | **Punto de equilibrio** | Costos fijos / (1 − costo variable / ingreso) | Mensual | ≤ ingreso esperado | Dueño | Costos/volumen |
| 59 | **Costo por viaje** | Costo directo + fijos asignados | Por viaje | ≤ tarifa − margen | Operaciones | Costeo |
| 60 | **Costo por km** | Costo total / km | Mensual | Benchmark | Operaciones | Eficiencia |
| 61 | **Costo por tonelada-km** | Costo total / tonelada-km | Mensual | Benchmark | Operaciones | Mix |
| 62 | **DSO** | (CxC / facturación) × días | Mensual | ≤ 35 | Cobranza | Cobrar |
| 63 | **DPO** | (CxP / compras) × días | Mensual | Negociado | Tesorería | Pagar |
| 64 | **CCC** | DSO + DIO − DPO | Mensual | ≤ 30 | Tesorería | Capital de trabajo |
| 65 | **Cash runway** | Caja / burn mensual | Mensual | ≥ 3 meses | Tesorería | Caja |
| 66 | **Aging CxC** | 0–30 / 31–60 / 61–90 / >90 | Semanal | >90 < 10% | Cobranza | Dunning |
| 67 | **% cobrado a tiempo** | Facturas pagadas ≤ vencimiento / total | Mensual | ≥ 85% | Cobranza | Crédito |
| 68 | **Presupuesto vs real** | Real / presupuesto − 1 | Mensual | ±5% | Dueño | Plan |
| 69 | **Costo financiero** | Intereses + factoring + comisiones | Mensual | ≤ 2% ingreso | Tesorería | Negociar |
| 70 | **IVA a pagar** | Débito − crédito | Mensual | Según ley | Contador | F29 |
| 71 | **Conciliación bancaria** | Movimientos conciliados / total | Semanal | 100% | Tesorería | Conciliar |
| 72 | **Días de cierre** | Días hábiles para cerrar el mes | Mensual | ≤ 5 | Contador | Checklist |

---

## 7. KPIs de personas y seguridad

| # | KPI | Fórmula | Frecuencia | Meta | Dueño | Acción |
|---|---|---|---|---|---|---|
| 73 | **Rotación de conductores** | Salidas / dotación promedio | Trimestral | ≤ 15% | RRHH | Clima/retención |
| 74 | **Ausentismo** | Días ausentes / días programados | Mensual | ≤ 4% | RRHH | Salud/clima |
| 75 | **Horas fuera de norma** | Horas > límite / horas totales | Semanal | 0 | Operaciones | Rotación/descanso |
| 76 | **Licencias vencidas** | Licencias vencidas / total | Semanal | 0 | Cumplimiento | Bloquear |
| 77 | **Exámenes médicos vencidos** | Vencidos / total | Mensual | 0 | RRHH | Renovar |
| 78 | **Accidentes por millón km** | Accidentes × 1.000.000 / km | Mensual | Tendencia a 0 | Seguridad | Capacitación |
| 79 | **Costo de siniestros** | Σ costos de siniestros | Mensual | Presupuesto | Seguridad | Prevención |
| 80 | **Cumplimiento de capacitación** | Capacitados / programados | Trimestral | ≥ 90% | RRHH | Plan |
| 81 | **Consumo por conductor** | Desviación vs estándar | Mensual | ≤ 3% | Operaciones | Coaching |
| 82 | **Satisfacción del conductor** | Encuesta 1–5 | Trimestral | ≥ 4 | RRHH | Plan |

---

## 8. KPIs de datos y sistema

| # | KPI | Fórmula | Frecuencia | Meta | Dueño | Acción |
|---|---|---|---|---|---|---|
| 83 | **Completitud de viajes** | Viajes con datos obligatorios / total | Semanal | ≥ 98% | Datos | Validaciones |
| 84 | **Completitud de gastos** | Gastos con respaldo / total | Semanal | ≥ 95% | Contabilidad | OCR/control |
| 85 | **Documentos digitalizados** | Documentos en sistema / total | Mensual | ≥ 95% | Cumplimiento | Escaneo |
| 86 | **Alertas resueltas a tiempo** | Resueltas ≤ SLA / total | Semanal | ≥ 90% | Operaciones | Workflow |
| 87 | **Usuarios activos** | Usuarios que ingresan / usuarios activos | Semanal | ≥ 90% | Dueño | Adopción |
| 88 | **Tiempo de respuesta API** | P95 ms | Diario | ≤ 500 ms | TI | Performance |
| 89 | **Disponibilidad del sistema** | Uptime | Mensual | ≥ 99,5% | TI | Infra |
| 90 | **Backup verificado** | Restauraciones exitosas / pruebas | Mensual | 100% | TI | DR |

---

## 9. Freight Score (Índice de Calidad del Flete)

### 9.1 Qué responde

No “¿cuánto facturé?”, sino **“¿este flete me conviene?”**.

Un flete puede tener buen precio y ser malo porque:
- El cliente paga a 90 días.
- La carga pesa poco y ocupa mucho.
- El retorno va vacío.
- La ruta tiene esperas eternas.
- El riesgo de daño es alto.
- El equipo queda mal posicionado.

### 9.2 Fórmula

```
Freight Score = 100 × (
    0,30 × score_margen_pct
  + 0,20 × score_margen_km
  + 0,15 × score_pago
  + 0,15 × score_utilizacion
  + 0,10 × score_retorno
  + 0,10 × score_riesgo
)
```

Cada componente va entre 0 y 1.

### 9.3 Componentes

#### A. Margen de contribución % (30%)

```
margen_pct = (flete_neto + recargos − costos_variables) / (flete_neto + recargos)
score_margen_pct = min(1, margen_pct / margen_objetivo)
```

Ejemplo: margen 30%, objetivo 25% → 1,0. Margen 15% → 0,6.

#### B. Margen de contribución por km (20%)

```
margen_km = margen_contribucion / km_totales
score_margen_km = min(1, margen_km / benchmark_margen_km)
```

El benchmark se calcula con la mediana de los últimos 90 días para la misma ruta/tipo de equipo.

#### C. Comportamiento de pago del cliente (15%)

| Días reales de pago | Score |
|---|---:|
| ≤ 30 | 1,00 |
| 31–45 | 0,70 |
| 46–60 | 0,40 |
| 61–90 | 0,20 |
| > 90 o mora recurrente | 0,00 |

#### D. Utilización de capacidad (15%)

```
score_utilizacion = min(1, toneladas_transportadas / capacidad_util)
```

Si la carga es volumétrica, usar m³. Si es mixta, usar el menor de los dos.

#### E. Retorno/backhaul (10%)

| Situación | Score |
|---|---:|
| Retorno cargado completo | 1,00 |
| Retorno parcial | 0,60 |
| Retorno vacío, pero hay carga cercana | 0,30 |
| Retorno vacío sin alternativa | 0,00 |

#### F. Riesgo operativo (10%)

```
score_riesgo = 1 − puntos_riesgo / 10
```

Puntos por:
- Carga peligrosa: +3.
- Sobredimensión: +2.
- Refrigerada: +1.
- Ruta de riesgo/nocturna: +1.
- Cliente con reclamos frecuentes: +1.
- Espera estimada > 4 h: +1.
- Descarga sin cita: +1.

### 9.4 Semáforo

| Score | Color | Decisión |
|---|---|---|
| 80–100 | Verde | Aceptar |
| 60–79 | Amarillo | Negociar o aceptar con condiciones |
| 0–59 | Rojo | Rechazar o aprobar solo el dueño |

### 9.5 Ejemplo completo

Viaje Santiago–Concepción, 500 km, 25 t, capacidad 28 t, flete $1.200.000, costo variable $450.000, margen de contribución $750.000 (62,5%), margen/km $1.500, benchmark $1.200, cliente paga a 45 días, retorno cargado, riesgo bajo.

| Componente | Cálculo | Score | Peso | Aporte |
|---|---|---:|---:|---:|
| Margen % | 62,5% / 50% objetivo → 1,0 | 1,00 | 30% | 30,0 |
| Margen/km | 1.500 / 1.200 → 1,0 | 1,00 | 20% | 20,0 |
| Pago | 45 días | 0,70 | 15% | 10,5 |
| Utilización | 25 / 28 | 0,89 | 15% | 13,4 |
| Retorno | Cargado | 1,00 | 10% | 10,0 |
| Riesgo | Bajo | 0,90 | 10% | 9,0 |
| **Total** | | | | **92,9** |

**Resultado:** verde. Aceptar.

### 9.6 Ejemplo de flete malo

Mismo viaje, flete $800.000, costo variable $450.000, margen $350.000 (43,75%), margen/km $700, cliente paga a 75 días, retorno vacío, riesgo medio.

| Componente | Cálculo | Score | Peso | Aporte |
|---|---|---:|---:|---:|
| Margen % | 43,75% / 50% → 0,875 | 0,875 | 30% | 26,3 |
| Margen/km | 700 / 1.200 → 0,583 | 0,583 | 20% | 11,7 |
| Pago | 75 días | 0,20 | 15% | 3,0 |
| Utilización | 25 / 28 | 0,89 | 15% | 13,4 |
| Retorno | Vacío | 0,00 | 10% | 0,0 |
| Riesgo | Medio | 0,70 | 10% | 7,0 |
| **Total** | | | | **61,4** |

**Resultado:** amarillo. Negociar o buscar retorno. Si el flete baja a $700.000, el score cae a rojo.

### 9.7 Reglas de decisión

- **Verde:** aceptar si hay capacidad y no desplaza un flete mejor.
- **Amarillo:** negociar precio, recargo, condiciones de pago o retorno. Aprobación de gerencia.
- **Rojo:** rechazar. Excepción: dueño, con justificación escrita (cliente estratégico, continuidad, retorno que evita km vacíos).
- **Nunca** aceptar un viaje con margen de contribución negativo, salvo decisión estratégica documentada.

---

## 10. Tarifa piso y punto de equilibrio

### 10.1 Tarifa piso estratégica

```
tarifa_piso = costo_total / (1 − margen_objetivo)
```

Ejemplo: costo total $615.000, margen objetivo 25% → $820.000.

### 10.2 Tarifa piso táctica

```
tarifa_piso_tactica = costos_variables + contribución_minima
```

Sirve para retornos y capacidad ociosa. No debe canibalizar tarifas ni clientes.

### 10.3 Punto de equilibrio mensual

```
viajes_equilibrio = costos_fijos_mes / contribución_promedio_por_viaje
```

Si los costos fijos son $30.000.000 y la contribución promedio es $500.000, se necesitan 60 viajes/mes.

### 10.4 Impacto del diésel

```
litros = km / rendimiento_km_l
costo_combustible = litros × precio_litro
recargo = (precio_actual − precio_base) × litros
```

Ejemplo: 500 km, 2,5 km/l → 200 L. Si el diésel sube $150/L, el recargo es $30.000. Para mantener el margen, la tarifa debe subir en ese monto (o más, si el contrato usa índice).

---

## 11. Cómo construir el catálogo en el ERP

### 11.1 Diccionario de KPI

Cada KPI debe tener:

- Código único.
- Nombre.
- Descripción.
- Fórmula.
- Fuente de datos.
- Unidad.
- Formato (CLP, %, número, días).
- Frecuencia.
- Período.
- Meta.
- Umbrales (verde/amarillo/rojo).
- Dueño.
- Acción.
- Dimensiones (empresa, sucursal, cliente, ruta, tracto, rampla, chofer, tipo de carga).
- Historial/snapshot.

### 11.2 Modelo de datos sugerido

```sql
kpi_definicion (
  id, empresa_id, codigo, nombre, descripcion, formula,
  unidad, formato, frecuencia, meta, umbrales_json,
  dueno_id, accion, activo, version
)

kpi_valor (
  id, empresa_id, kpi_id, periodo, dimension_tipo, dimension_id,
  valor, meta, color, calculado_en, fuente_hash
)

kpi_snapshot (
  id, empresa_id, fecha, kpi_id, valor, metadata_json
)
```

### 11.3 Reglas de cálculo

- Siempre calcular en backend, nunca en el navegador.
- Usar período cerrado para históricos.
- Guardar snapshot para auditoría.
- Versionar fórmulas.
- Explicar el cálculo en la UI (“ver detalle”).
- No permitir fórmulas que consulten datos de otra empresa.
- Cachear y materializar KPIs pesados.

### 11.4 Anti-patrones

- KPI sin meta.
- KPI que mezcla devengado y cobrado.
- KPI que cambia de fórmula sin versionar.
- KPI que solo mira el mes actual.
- KPI que no se puede desagregar.
- KPI que depende de datos manuales sin control.
- KPI que nadie usa para decidir.

---

## 12. Revisión mensual del negocio (MBR)

### 12.1 Estructura de 1 página

1. **Resultado:** ingreso, margen, EBITDA, caja.
2. **Vs presupuesto:** desviaciones.
3. **Vs mes anterior/año:** tendencia.
4. **Por cliente/ruta/tracto:** top y bottom.
5. **Costos:** combustible, mantenimiento, nómina, administración.
6. **Operación:** utilización, OTIF, km vacíos, estadías.
7. **Cobranza:** DSO, aging, top deudores.
8. **Riesgos:** documentos, accidentes, horas, concentración.
9. **Decisiones:** 3 acciones con dueño y fecha.
10. **Proyección:** caja 13 semanas y forecast del mes.

### 12.2 Preguntas que debe responder

- ¿Ganamos más o menos que el mes pasado? ¿Por qué?
- ¿Qué cliente/ruta nos hizo ganar o perder?
- ¿Qué costo se desvió?
- ¿Qué flete debemos renegociar?
- ¿Qué camión está dando menos margen?
- ¿Qué cobranza está en riesgo?
- ¿Qué decisión tomamos este mes?

---

## 13. Metas iniciales sugeridas

Ajustar con el dueño después de 3 meses de línea base.

| KPI | Meta inicial |
|---|---:|
| Margen de contribución | ≥ 30% |
| Margen EBITDA | ≥ 12% |
| Utilización de flota | ≥ 75% |
| Km vacíos | ≤ 15% |
| OTIF | ≥ 92% |
| DSO | ≤ 35 días |
| CxC > 90 días | ≤ 10% |
| Cumplimiento preventivo | ≥ 95% |
| Documentos al día | 100% |
| Viajes con POD | 100% |
| Días entrega-factura | ≤ 3 |
| Cierre mensual | ≤ 5 días |
| Desviación de combustible | ≤ 3% |
| Accidentes/1.000.000 km | ≤ 1 |
| Adopción diaria | ≥ 90% |

---

## 14. Resumen

- El KPI rey es **margen neto por tracto disponible**.
- El KPI de decisión de viaje es **margen de contribución + Freight Score**.
- El KPI de supervivencia es **caja proyectada**.
- El KPI de cobranza es **DSO + aging**.
- El KPI de operación es **utilización + OTIF + km vacíos**.
- El KPI de mantenimiento es **costo/km + cumplimiento preventivo**.
- El KPI de personas es **horas fuera de norma + siniestralidad**.
- El KPI de datos es **completitud + adopción**.

Si el sistema entrega estos números con confianza, el dueño puede dejar de llevar la empresa en la cabeza y empezar a dirigirla con datos.
