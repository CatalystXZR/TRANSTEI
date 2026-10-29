> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# Cerebro TEI — Plan Maestro de Desarrollo «Operación Resurrección»

**Propuesta del asesor logístico · Versión 2.0 · Octubre 2026**

> Documento de doble propósito: (a) hoja de ruta para el dueño de Transportes TEI SpA; (b) especificación ejecutable para el agente de código (OpenClaw) que tiene acceso al repositorio del ERP. Todas las cifras de este documento son **valores iniciales ilustrativos**: el sistema debe calibrarlas con los datos reales de TEI. Toda norma tributaria o legal citada debe ser **verificada con el contador y el abogado** antes de codificarse como regla fija; por eso todas viven en una tabla de parámetros editable, nunca en el código.

---

## 0. Cómo usar este documento

| Quién | Qué hace |
| --- | --- |
| **Dueño** | Lee las secciones 1, 2, 4 y 10. Ahí está el por qué y lo que verá cada mañana. |
| **Quien supervisa la IA** | Entrega a OpenClaw las secciones 1 a 8 como **contexto fijo** y luego pega **un solo Prompt de Fase** (sección 9) a la vez. Nunca dos fases juntas. |
| **OpenClaw** | Obedece el Prompt Maestro (sección 9.1). Antes de escribir una línea, lee el repo, confirma el stack y devuelve un plan. |

**Regla de oro del proyecto:** primero el tablero de instrumentos, después el piloto automático. Una empresa que no sabe cuánta plata tiene hoy no necesita una simulación estocástica; necesita un libro de caja conciliado. La matemática avanzada se construye **encima** de datos verificados, y cada modelo debe **ganarle a un método simple** en backtesting antes de mostrarse al dueño.

---

## 1. Tesis: por qué muere (y cómo revive) una empresa de transporte chilena

### 1.1 El diagnóstico de TEI en una línea

TEI no tiene un problema de camiones. Tiene un **problema de ciclo de caja y de ceguera operativa**. Trabajan con un tercio de la flota porque cada camión que sale a ruta **consume caja antes de generarla**, y esa caja no existe.

### 1.2 La ecuación central del negocio

```
Capital de trabajo por camión (WC_k) =
    Σ (cada desembolso del ciclo × días entre ese desembolso y el cobro efectivo) / 30
    + IVA débito pagado en F29 antes de cobrar

Crecimiento posible de la flota  ≤  Caja libre generada por mes / WC por camión nuevo
```

Ejemplo ilustrativo (a calibrar): 3 camiones facturan $21.000.000 netos al mes, es decir, $7.000.000 por camión. Si el plazo real de cobro pasa de 30 a 60 días, el negocio necesita **$21.000.000 adicionales de capital de trabajo** (21.000.000 / 30 × 30). Con 10 camiones, el hoyo sería de $70.000.000. **Los camiones están parados porque nadie puede financiar su ciclo.** Esa es la ecuación que gobierna todo lo demás.

### 1.3 El costo de un camión detenido

Un camión parado no es «cero»: sigue pagando leasing, seguro, permiso de circulación, revisión técnica, GPS y, a veces, un chofer. Ejemplo ilustrativo: cuota leasing $2.400.000 + seguro $250.000 + permisos, GPS y otros $150.000 = **$2.800.000 al mes ≈ $93.000 por día** de pérdida por cada camión inmóvil. Siete camiones parados con esa estructura serían ≈ $19.600.000 al mes sangrando. Por eso el criterio de decisión para un flete **no es el margen completo, es el margen de contribución** (lo que sobra después de los costos que solo existen si el camión sale), y la restricción que realmente manda es la **caja disponible para financiar el ciclo**.

### 1.4 Hipótesis a validar con datos sobre los 7 camiones detenidos

El sistema debe obligar a registrar la **causa raíz** de cada día de detención. Hipótesis a contrastar durante las primeras semanas:

| Código | Causa | Cómo se mide |
| --- | --- | --- |
| H1 | Sin caja para financiar el ciclo (diésel, viáticos, peajes) | Días parado con carga disponible rechazada por falta de caja |
| H2 | Mantención pendiente o repuesto sin pagar | Órdenes de trabajo abiertas por camión y su monto |
| H3 | Sin chofer disponible o confiable | Días sin chofer asignado |
| H4 | Sin carga rentable | Cotizaciones recibidas vs aceptadas vs piso de tarifa |
| H5 | Documentos vencidos (revisión técnica, permiso, seguro, licencia) | Calendario de vencimientos |

Sin esta tabla, cualquier plan de reactivación es una adivinanza.

### 1.5 Qué significa «revivir» en 90 días (metas medibles)

1. **Saber la verdad cada mañana:** caja real conciliada con el banco, a las 08:00, en una sola pantalla.
2. **Cero sorpresas de caja:** el sistema avisa con **≥ 3 semanas** de anticipación cuando la probabilidad de quedar bajo cero supera 10 %.
3. **Cero fletes aceptados sin costo conocido:** todo viaje tiene tarifa mínima calculada antes de decir que sí.
4. **Tarjeta bajo control:** la tarjeta de la empresa se modela como deuda con costo, con un tope de retiros del dueño.
5. **Reactivación secuencial financiable:** el sistema indica *qué camión* reactivar *cuándo*, y cuánta caja libre se necesita, de modo que cada camión nuevo financie al siguiente.

---

## 2. La realidad chilena: cómo se pierde y cómo se mueve la plata (no la teoría)

### 2.1 Estructura de costos de un tractocamión con rampla (rangos iniciales a calibrar)

| Rubro | % aprox. del costo total | Naturaleza | Comentario operativo |
| --- | --- | --- | --- |
| Combustible (diésel) | 35–45 % | Variable por km y por carga | El precio cambia semanalmente. Rendimiento depende de carga, pendiente y chofer. Es el principal foco de pérdida y de fuga. |
| Chofer (base, comisión, viáticos, cargas) | 12–20 % | Mixto | Habitualmente pagado como % del flete más viático. Los anticipos salen **antes** del viaje. |
| Leasing / depreciación / interés | 10–18 % | Fijo por día | Se paga parado o andando. |
| Neumáticos | 4–8 % | Variable por km | Más de 18 posiciones entre tracto y rampla. Caminos malos y mala presión destruyen vida útil. |
| Mantención y repuestos | 6–10 % | Variable por km | La mantención diferida es la mayor deuda oculta. |
| Peajes y TAG | 3–8 % | Variable por ruta | Postpago mensual: es crédito de corto plazo que se olvida. |
| Seguros, permiso, revisión técnica, GPS | 2–4 % | Fijo | Vencimientos puntuales y grandes. |
| Administración, contabilidad, otros | 3–6 % | Fijo |  |
| Multas, sobrepeso, mermas, deducibles | 0–3 % | Cola de riesgo | Evento raro, costo alto. |

### 2.2 Cómo fluye realmente la plata

**Salidas rápidas y ciertas (el camión las genera antes de cobrar):**

- Diésel: tarjeta de flota con facturación quincenal o mensual, o pago al contado o con tarjeta de crédito.
- Anticipo y viáticos del chofer, normalmente en efectivo antes de salir.
- Peajes y TAG: cargo mensual diferido.
- Mantención preventiva y correctiva: contado o crédito corto.
- Leasing, seguros, sueldos: fechas fijas, no negociables.
- **IVA débito del mes:** se declara y paga vía F29 el mes siguiente (día 12 o 20 según modalidad; confirmar con el contador), **aunque el cliente aún no haya pagado**.

**Entradas lentas e inciertas:**

- El plazo nominal (30 días) casi nunca es el plazo real. La ley de pago a 30 días (Ley 21.131) existe, pero en la práctica se negocian pactos y se ignoran plazos; **verificar con abogado** excepciones y vigencia.
- El reloj real de pago parte cuando el cliente **recibe conforme** (OC válida, guía firmada, HES en minería, estado de pago aprobado), no cuando TEI emite la factura.
- Los grandes clientes pagan en **corridas de pago con calendario fijo** (por ejemplo, lo recibido hasta el día 20 se paga el último viernes del mes siguiente). El pago es **discreto y agrupado en fechas**, no continuo.
- Pagan **varias facturas con una sola transferencia**, a veces sin glosa clara.
- La factura electrónica puede tener mérito ejecutivo (Ley 19.983) si se cumplen los pasos de recepción y acuse; **verificar plazos de reclamo con el abogado** y registrar la fecha exacta de recepción de cada factura en el sistema.

### 2.3 Las 14 trampas específicas del rubro (cada una tiene un módulo que la ataca)

1. **IVA adelantado:** se financia al fisco antes de cobrar. → Motor tributario (M4).
2. **Entregado y no facturado:** guías de despacho sin factura emitida. Es plata ganada que no corre ningún reloj de cobro. → Indicador de WIP y días de facturación.
3. **Facturas rechazadas** por OC mal citada, HES faltante o glosa incorrecta, que reinician el reloj. → Control de calidad documental previo a facturar.
4. **Sobrestadía no cobrada:** esperas de carga y descarga que consumen días-camión sin ingreso. → Costeo por día de ciclo.
5. **Retorno en vacío** que se absorbe en la tarifa sin medirse. → Margen por ciclo completo.
6. **Fletes spot que «calzan» y destruyen:** tarifa nominal alta, pago a 90 días, caminos malos. → Motor de decisión de fletes (M7).
7. **Contratos sin cláusula de reajuste por combustible:** el diésel sube y la tarifa no. → Tarifa piso dinámica.
8. **Tarjeta de la empresa como caja personal:** deuda revolving cara, mezclada con gastos del dueño. → Módulo de deuda (M9).
9. **Fuga y anomalías de combustible:** consumo no explicado por km, carga y ruta. → Control estadístico de rendimiento (M11).
10. **Mantención diferida** que termina en falla grave en ruta. → Costo por km con tendencia y alertas.
11. **Concentración en un cliente grande** que usa tu caja como financiamiento. → Límites de exposición (M8).
12. **Estacionalidad y calendario:** temporada agrícola, paradas de planta mineras, cierres contables de clientes en diciembre, feriados. → Calendario hábil chileno en todo modelo.
13. **Informalidad:** pagos en efectivo, anticipos sin respaldo, gastos sin documento. → Captura móvil y conciliación bancaria.
14. **Multas y sobrepeso** por mala planificación de carga. → Registro de eventos y su costo por chofer y ruta.

### 2.4 Lo que este plan **no** hace

- No promete «blindar» la caja. Promete **probabilidades calibradas, alertas oportunas y decisiones recomendadas**.
- No usa GARCH. Se justificó que es el objeto matemático equivocado para esta empresa (pocos datos, estacionalidad de calendario, no hay serie de alta frecuencia). Se reemplaza por control estadístico de proceso y simulación Monte Carlo (secciones 6.4 y 6.5).
- No exige sub-milisegundo. Exige **integridad, trazabilidad y que el dueño entienda cada número**.

---

## 3. Principios de diseño innegociables

1. **Registro antes que predicción.** Sin datos limpios, ningún modelo vale. La captura de datos es la fase más importante.
2. **Entrada mínima.** Registrar un gasto o un viaje debe tomar **menos de 30 segundos**, idealmente desde el celular del chofer con foto.
3. **Trazabilidad total.** Cada número del tablero permite un *drill-down* hasta el documento original (factura, cartola, boleta, guía).
4. **Dinero entero.** El CLP no tiene decimales: todo monto se guarda como `BIGINT` (pesos) o `Decimal`. Prohibido `float` para dinero. Los cálculos estadísticos pueden usar `float` pero se redondean **una sola vez** en el borde, con regla documentada.
5. **Distribuciones, no puntos; pero con baseline.** Todo modelo probabilístico se compara contra un método simple (mediana histórica). Si no gana en backtest, no se muestra.
6. **La factura impaga es un dato.** Los datos censurados se modelan; nunca se ignoran.
7. **Decisión sobre predicción.** Cada módulo termina en una **acción recomendada** en lenguaje del dueño.
8. **Vetos no compensatorios.** Un margen alto no compensa un cliente que no paga ni una caja que no alcanza.
9. **La restricción vinculante es la caja.** El sistema optimiza rentabilidad **sujeta a** factibilidad de caja.
10. **Degradación elegante.** Si faltan datos, usa el prior, marca **confianza baja** y dice qué dato falta.
11. **Auditable y reversible.** Todo cambio financiero deja registro con usuario, fecha y valor previo. Nada se borra; se anula.
12. **Zona horaria y calendario chilenos.** `America/Santiago`, feriados chilenos, días hábiles bancarios.

---

## 4. Los 24 indicadores indispensables

Cada uno responde una pregunta que el dueño hoy no puede contestar. Si el sistema no los calcula, no es un ERP de transporte; es una planilla con interfaz.

| # | Indicador | Fórmula | Por qué es indispensable | Decisión que dispara |
| --- | --- | --- | --- | --- |
| 1 | **Caja real conciliada** | Saldo cartola − cargos pendientes + abonos pendientes | Sin esto todo lo demás es ficción | Saber cuánto hay hoy |
| 2 | **Días de caja (runway)** | Caja disponible / egreso diario proyectado P50 | Dice cuántos días aguantas sin cobrar | Frenar gasto o factorizar |
| 3 | **Flujo a 13 semanas** | Saldo semanal proyectado, P10/P50/P90 | Es el estándar de tesorería | Planificar compras y fletes |
| 4 | **P(saldo < 0) por semana** | Fracción de simulaciones con saldo negativo | Anticipa el quiebre con semanas de aviso | Alertas amarilla/roja |
| 5 | **Buffer de caja requerido (CaR 95 %)** | Percentil 95 de la peor caída del saldo en el horizonte | Reemplaza al «colchón» sin fórmula | Cuánta liquidez reservar |
| 6 | **DSO real (countback)** y por cliente | Días de ventas que representa la cartera abierta | Mide el plazo **real**, no el nominal | Política de crédito |
| 7 | **Antigüedad relativa al patrón** | edad factura / mediana de pago del cliente | Una factura de 50 días es normal en un cliente y grave en otro | Cola de cobranza |
| 8 | **Cartera en riesgo** | Σ monto con edad > P90 del cliente | Detecta la deuda que deja de comportarse | Escalamiento |
| 9 | **WIP y rezago de facturación** | Σ guías entregadas sin factura; días entrega→emisión | Plata ganada que no cobra reloj | Facturar el mismo día |
| 10 | **Capital de trabajo requerido y CCC** | Ver 6.2 | Dice cuántos camiones puedes financiar | Techo de crecimiento |
| 11 | **Costo por km (CPK) y costo fijo por día** | Ver 6.1 | Es el costo real, por camión y por ruta | Tarifa piso |
| 12 | **Margen de contribución** por viaje, ciclo y día-camión | Ingreso neto − costos variables del viaje | Criterio correcto con flota parada | Aceptar o rechazar |
| 13 | **Eficiencia de capital** | Valor económico / (peso-días de capital comprometido) | Ordena fletes cuando la caja es el cuello de botella | Priorizar cargas |
| 14 | **Utilización y disponibilidad** | días en ruta / días calendario; días operativos / días calendario | Mide cuánto del activo trabaja | Reactivar o vender |
| 15 | **% km vacíos y días de retorno** | km sin carga / km totales | El retorno es parte del ciclo | Armar rutas redondas |
| 16 | **Utilización de equilibrio** | u\* = costo fijo diario / margen de contribución diario cuando opera | Cuántos días al mes debe trabajar un camión para no perder | Vender, arrendar o reactivar |
| 17 | **Rendimiento km/l y su desvío** | z = (km/l observado − esperado) / σ | Detecta fuga y mala conducción | Auditoría de carga de combustible |
| 18 | **Costo de neumático y mantención por km** | CLP / km con tendencia (CUSUM) | Anticipa fallas y costos ocultos | Mantención preventiva |
| 19 | **Concentración y exposición** | HHI = Σ s\_c²; exposición\_c = Σ saldo abierto + WIP | Evita depender de un solo pagador | Límite de crédito |
| 20 | **Interés quemado de deuda y DSCR** | Σ intereses del mes; (caja operativa) / (servicio de deuda) | Muestra cuánto cuesta vivir de la tarjeta | Plan de pago de deuda |
| 21 | **Retiros del dueño / ventas** | retiros del mes / ventas netas | Separa la plata de la empresa de la personal | Tope de retiros |
| 22 | **Brecha de tarifa vs piso** | tarifa efectiva − tarifa mínima económica | Detecta rutas y clientes que destruyen valor | Renegociar o dejar |
| 23 | **Pérdida esperada de cartera** | EL = Σ π\_c × saldo\_c | Provisión realista de incobrables | Provisionar y limitar |
| 24 | **Calibración del modelo y calidad de datos** | Cobertura real de intervalos; % de campos completos | Dice cuánta confianza darle al sistema | Mostrar semáforo de confianza |

---

## 5. Mapa de integración al ERP: qué se agrega, dónde y por qué

Se conserva la base del repositorio propuesta originalmente (FastAPI, SQLModel, PostgreSQL, APScheduler) y se **reemplaza** el motor GARCH. Estructura objetivo:

```text
cerebro_tei/
├── core/
│   ├── money.py              # tipo Money (CLP entero), redondeo único, utilidades
│   ├── calendar_cl.py        # feriados, días hábiles bancarios, America/Santiago
│   └── params.py             # tabla de parámetros versionada (tasas, % recuperación, etc.)
├── models/                   # SQLModel: ver sección 7
├── services/
│   ├── ledger_service.py         # libro de caja y categorías (incluye retiros del dueño)
│   ├── reconciliation_service.py # conciliación bancaria y asignación pago↔facturas
│   ├── costing_engine.py         # M1: CPK, costo fijo/día, margen de contribución
│   ├── working_capital.py        # M2: DSO, CCC, capital de trabajo, crecimiento posible
│   ├── ar_service.py             # M3: aging relativo, cola de cobranza, WIP
│   ├── tax_engine.py             # M4: IVA, F29, PPM, impuesto específico
│   ├── payment_model.py          # M5: modelo de pago censurado y jerárquico (reemplaza bayesian_engine)
│   ├── drift_monitor.py          # M6: EWMA/CUSUM de comportamiento de pago
│   ├── cash_simulator.py         # M6b: Monte Carlo de caja, CaR, buffer (reemplaza garch_engine)
│   ├── freight_decision.py       # M7: valor económico, tarifa mínima, contraoferta
│   ├── credit_policy.py          # M8: exposición y límite por cliente
│   ├── financing_advisor.py      # M9: factoring, anticipo, tarjeta/deuda
│   ├── fleet_analytics.py        # M10: utilización, mantención, neumáticos
│   ├── fuel_anomaly.py           # M11: rendimiento y detección de anomalías
│   ├── reactivation_planner.py   # M12: secuencia de reactivación de camiones
│   ├── load_assignment.py        # M13: asignación carga-camión con restricción de caja
│   └── backtesting.py            # M14: walk-forward, calibración, puerta de promoción
├── tasks/scheduler.py        # jobs diarios y semanales con puerta de validación
└── api/v1/ (finance.py, fleet.py, trips.py, ar.py, owner_dashboard.py)
```

| Módulo | Por qué es brutalmente útil para TEI |
| --- | --- |
| `ledger` + `reconciliation` | Resuelve «no sé cuánto tengo ni cuánto gano». Es la base de todo. |
| `costing_engine` | Resuelve «no sé cuánto cuesta realmente mover un camión». Convierte tarifas en decisiones. |
| `working_capital` | Explica por qué solo trabajan 1/3 de la flota y dice cuántos camiones puede financiar hoy. |
| `ar_service` | La cobranza es la mayor palanca de caja a costo cero. |
| `tax_engine` | Elimina la sorpresa del F29 que revienta la caja. |
| `payment_model` + `drift_monitor` | Predicen **cuándo** entra la plata y detectan cuándo un cliente cambia de conducta. |
| `cash_simulator` | Convierte todo en probabilidad de quiebre y en un buffer con fórmula. |
| `freight_decision` + `credit_policy` | Evita aceptar fletes ruinosos y concentración peligrosa; propone contraofertas en vez de solo bloquear. |
| `financing_advisor` | Dice cuándo factorizar sale más barato que quedarse sin caja. |
| `fleet_analytics` + `fuel_anomaly` | Atacan los dos costos más grandes y más fugables: combustible y mantención. |
| `reactivation_planner` | Es el plan de **revivir la flota**, camión por camión, sin quebrar la caja. |

---

## 6. Especificación matemática (M0 a M14)

**Convenciones globales (obligatorias para toda la implementación):**

- Montos en **CLP enteros, netos de IVA**, salvo que se indique lo contrario. Cada rubro se redondea a peso entero **una sola vez**, al final de su cálculo, con `ROUND_HALF_UP`.
- Tiempo en **días**; fechas en `America/Santiago`; todo pago bancario se desplaza al siguiente **día hábil** (`calendar_cl.py`).
- Intereses con **interés simple** `tasa_mensual × días / 30`, salvo que se indique lo contrario (parámetro `interest_convention`).
- Todo parámetro (tasas, %, umbrales) vive en `params` versionado, **nunca** hardcodeado.
- Todo cálculo con azar usa `numpy.random.Generator` con semilla explícita y registrada.
- Cada función pública recibe y devuelve tipos explícitos (`dataclass` o `pydantic`), sin `dict` anónimos.

### 6.0 M0 — Conciliación bancaria y asignación pago↔facturas (la base de toda la verdad)

**Por qué:** los clientes pagan varias facturas con una transferencia, a veces sin glosa. Sin esta asignación no hay historial de pagos, y sin historial no hay modelo.

**Algoritmo:**

1. Cada abono bancario `X` se asocia a un cliente por RUT en glosa o por cuenta de origen (el sistema aprende la relación cuenta→cliente y pide confirmación la primera vez).
2. Se buscan subconjuntos `S` de facturas abiertas del cliente tales que `Σ saldo_i = X` (tolerancia `τ` en CLP, por defecto 0; permitir retenciones o notas de crédito conocidas). Es un problema *subset-sum* entero: usar programación dinámica o *meet-in-the-middle* con **máximo 25 candidatas**, ordenadas de la más antigua a la más nueva.
3. Si hay **solución única**, se asigna automáticamente. Si hay varias, se proponen las 3 mejores (preferencia FIFO) y **un humano confirma**. Si no hay ninguna, el abono queda como `pago_sin_asignar`.
4. Los cargos se categorizan por reglas (comerciante→categoría) y cada corrección manual crea una regla nueva. **Existe una categoría obligatoria `retiro_dueño`.**

**Prueba dorada:** abono `7.350.000` con facturas abiertas `[3.000.000; 2.350.000; 2.000.000; 1.000.000]` debe asignar **exactamente** `{3.000.000, 2.350.000, 2.000.000}` (solución única). Un abono de `5.350.000` con las mismas facturas debe asignar `{3.000.000, 2.350.000}`.

### 6.1 M1 — Costeo real: costo por km, costo fijo diario y márgenes

**Por qué:** convierte una tarifa en una decisión. Sin esto, TEI acepta fletes sin saber si pierde.

```
Costo fijo diario del camión k:
  F_k = (Leasing_k + Seguro_k + Permiso_k/12 + RevisionTecnica_k/12 + GPS_k
         + Admin_asignada_k + SueldoBase_chofer_k) / 30

Precio neto del diésel por litro:
  p_neto = precio_bruto / (1 + IVA) − ρ_ie × impuesto_específico_por_litro
  (ρ_ie = % recuperable del impuesto específico: PARÁMETRO a verificar con contador)

Costo variable por km:
  c_v = p_neto / rend_kml + peaje_km + neumático_km + mantención_km + reserva_reparaciones_km
  neumático_km = Σ_posiciones (precio_p − valor_residual_p) / vida_km_p

Margen de contribución del viaje:
  CM_viaje = Ingreso_neto − km_total × c_v − comisión_chofer − viáticos − extras_directos
  (comisión_chofer = κ × Ingreso_neto; extras: carga/descarga, estacionamiento, cuadrillas)

Ciclo completo:
  T_ciclo = T_ida + T_carga + T_descarga + T_retorno + T_espera + T_mantención_prorrateada
  CM_día = CM_ciclo / T_ciclo
  EBITDA_día_camión = u × CM_día − F_k            (u = utilización)
  Utilización de equilibrio:  u* = F_k / CM_día

Tarifa piso operativa (sin costo financiero; el piso completo lo da M7):
  Ingreso_piso = (km_total×c_v + viáticos + extras + F_k × T_ciclo × cobertura_fijos) / (1 − κ)
```

**Regla de oro:** el retorno vacío **no se ignora**: el costo de los km vacíos va dentro de `km_total`, y el margen se mide **por día de ciclo completo**, no por tramo.

**Prueba dorada (ilustrativa):** `km_total = 1.000`, `rend = 2,2 km/l`, `p_neto = 1.000 CLP/l`, peajes `60.000`, neumático `45 CLP/km`, mantención `60 CLP/km`, reserva `25 CLP/km`, `Ingreso = 1.100.000`, `κ = 12 %`, viáticos `40.000`, extras `0`, `T_ciclo = 3 días`, `F_k = 93.000`.

- Combustible: `454.545` (redondeo al final del rubro). Suma de costos variables por km = `644.545`; comisión `132.000`.
- **`CM_viaje = 283.455`**; `CM_día = 94.485`; `EBITDA_día (u=1) = 1.485`; **`u* = 0,98428`** (tolerancia `1e-4`).
- Lectura que el sistema debe mostrar: *«Este viaje deja contribución positiva y conviene frente al camión parado, pero solo cubre el costo fijo si el camión trabaja el 98 % de los días. Tarifa frágil.»*

### 6.2 M2 — Capital de trabajo, ciclo de caja y crecimiento posible

**Por qué:** explica por qué trabaja 1/3 de la flota y cuántos camiones se pueden financiar.

```
V_d = ventas netas diarias (promedio móvil de 90 días)

DSO por método countback:
  recorrer hacia atrás los períodos de venta consumiéndolos hasta cubrir el saldo de
  cuentas por cobrar; el DSO es la suma de días consumidos (con fracción del último).

WC  = CxC + WIP − CxP_operacional + (IVA débito pagado antes de cobrar − IVA crédito pendiente)
CCC = DSO + Días_WIP − DPO

Camiones financiables hoy:
  N_max = floor( (Caja_libre_P10 − Buffer_CaR) / WC_por_camión )

Crecimiento sostenible mensual:
  g = Caja_operativa_libre_mensual / WC_total
```

**Pruebas doradas:**

- Ventas `21.000.000` en 30 días: pasar de DSO 30 a DSO 60 exige **`ΔWC = 21.000.000`**.
- Countback: `CxC = 31.500.000`; ventas de los últimos 30 días `21.000.000` y de los 30 anteriores `21.000.000`. Se consumen 21.000.000 (30 días) y quedan 10.500.000 sobre 21.000.000 × 30 = **15 días** → **`DSO = 45`**.

### 6.3 M3 — Cobranza, antigüedad relativa y rezago de facturación

```
Edad:                  a_i = hoy − t0_i  (t0 = recepción conforme; si no existe, issue_date + δ_c y marcar «reloj estimado»)
Antigüedad relativa:   r_i = a_i / Q50_c   (Q50_c = mediana del retraso del cliente según M5)
Semáforo de factura:   verde r<1 · amarillo 1≤r<1,5 · naranja 1,5≤r<2,5 · rojo r≥2,5 ó a_i > Q90_c
Prioridad de cobranza: score_i = A_i × min(r_i, 3) × (1 − P_i(pago en 7 d))
WIP = Σ guías entregadas sin factura;   rezago_facturación = días(entrega → emisión)
Plazo de reclamo (Ley 19.983): fecha_límite_reclamo = recepción + N días (N en params; verificar con abogado)
```

**Acciones automáticas:** (1) si falta un documento (OC, HES, guía firmada), la factura entra a la cola como **«documento pendiente»** *antes* que cualquier cobranza; (2) cola diaria ordenada por `score_i` con texto sugerido de gestión; (3) alerta de WIP si el rezago de facturación supera 2 días hábiles.

### 6.4 M4 — Motor tributario: IVA, F29, PPM e impuesto específico

**Por qué:** el F29 es la salida cierta que más revienta la caja de un transportista que cobra a 60–90 días.

```
IVA_d_m  = 19 % × Σ ventas afectas emitidas en el mes m
IVA_c_m  = 19 % × Σ compras afectas con derecho a crédito (diésel, repuestos, neumáticos, etc.)
A_pagar_m   = max(0, IVA_d_m − IVA_c_m − Remanente_{m−1})
Remanente_m = max(0, IVA_c_m + Remanente_{m−1} − IVA_d_m)
PPM_m    = tasa_ppm × ventas_netas_m                 (tasa en params)
Fecha de pago = día_F29 del mes m+1, ajustada a día hábil (día 12 o 20 según modalidad, en params)
Recuperación imp. específico:  R_m = ρ_ie × litros_elegibles_m × imp_esp_por_litro  (mecanismo y % en params)
Costo de financiar el IVA de la factura i:
  r_m/30 × IVA_d_i × max(0, fecha_cobro_i − fecha_F29_i)
```

**Pruebas doradas:** ventas afectas `21.000.000` → `IVA_d = 3.990.000`; compras afectas `12.000.000` → `IVA_c = 2.280.000`; remanente previo `0` → **`A_pagar = 1.710.000`**. Con remanente previo `500.000` → **`1.210.000`**. Con remanente previo `9.000.000` → `A_pagar = 0` y **`Remanente = 7.290.000`** (9.000.000 + 2.280.000 − 3.990.000).

### 6.5 M5 — Modelo de comportamiento de pago (reemplaza al motor bayesiano original)

**Es el corazón matemático del sistema.** Corrige los errores del diseño original: censura, riesgo de impago, reloj de partida, corridas de pago y parámetros ambiguos.

**Notación.** Factura `i` del cliente `c`; `t0_i` = recepción conforme; `T` = hoy; `a_i = T − t0_i`. La factura está **pagada** con retraso `d_i` o **abierta** (censurada a la derecha en `a_i`).

**Modelo «cura + corrida»:**

- Con probabilidad `π_c` la factura **no se paga dentro del horizonte `H = 365 d`** (disputa, nota de crédito, castigo).
- Con probabilidad `1 − π_c` hay un retraso de procesamiento latente `Δ_i ~ LogNormal(μ_c, σ_c)`.
- Si el cliente tiene **calendario de corridas** `R_c` (fechas de pago), el pago ocurre en la **primera corrida** `r` con `r ≥ t0_i + Δ_i`. Si no hay calendario, `D_i = Δ_i`.

```
Distribución del pago (condicionada a que se paga):
  Sin calendario:  F(x) = Φ( (ln x − μ_c) / σ_c )
  Con calendario:  F(x) = Φ( (ln ℓ(x) − μ_c) / σ_c )  si ℓ(x) > 0, si no 0
                   donde ℓ(x) = (última corrida con fecha ≤ t0 + x) − t0
  Masa en la corrida r_j:  P(r_j) = F_Δ(r_j − t0) − F_Δ(r_{j−1} − t0)

Supervivencia (no pagada a los x días):
  S(x) = π_c + (1 − π_c) × (1 − F(x))

Verosimilitud (peso de memoria w_i = 0,5^((T − fecha_evento_i)/h), semivida h = 180 d):
  LL = Σ_pagadas w_i · ln[(1 − π_c) · p_i(d_i)] + Σ_abiertas w_i · ln S(a_i)

A priori jerárquico (MAP):
  μ_c ~ N(μ_seg, τ_μ²)     ln σ_c ~ N(ln σ_seg, τ_σ²)     π_c ~ Beta(α₀, β₀)
  τ_μ = 0,25   τ_σ = 0,30   π₀ = 0,02   fuerza α₀ + β₀ = 30   (todo en params)
  Segmentos: minería, retail, forestal, agro, construcción, sin_segmento
```

**Ajuste y posterior:** minimizar `−LL_posterior` con `scipy.optimize.minimize(method='L-BFGS-B')` sobre `(μ_c, ln σ_c, logit π_c)`. La incertidumbre de parámetros se obtiene por **aproximación de Laplace** (inversa de la Hessiana); si no es definida positiva, usar *bootstrap* paramétrico de 500 réplicas. **Prohibido** ajustar solo con facturas pagadas.

**Predicción condicional (lo que realmente se muestra):**

```
P(pago en la semana w | abierta con edad a) = [ S(a + 7(w−1)) − S(a + 7w) ] / S(a)
P(no pagar en el horizonte)                  = S(a + H_sem) / S(a)
Ventana de cobro: cuantiles P10, P50, P90 de la fecha de pago condicional
  (se informa como «intervalo predictivo al 80 %»; el 95 % solo bajo petición)
Entrada esperada de caja de la semana w:  Σ_i  A_i × θ_c × P_i(w)    (θ_c = fracción pagada promedio, prior 1)
```

**Cold start (cliente nuevo, N = 0):** se usa el prior del segmento. Conversión del prior original (media 45 d, desv. 10 d) a parámetros log: `σ² = ln(1 + (10/45)²)`, `μ = ln 45 − σ²/2` → **`σ = 0,2195`, `μ = 3,7826`**. **Advertencia:** una desviación de 10 d es demasiado estrecha para Chile; el prior inicial debe ser más ancho (`σ_log` entre 0,35 y 0,50) hasta que existan datos propios, y se mide **desde recepción conforme**, no desde emisión.

**Baseline obligatorio:** `B1` = mediana de retraso del cliente (o del segmento si N < 3). Todo resultado del modelo se compara contra `B1` en M14.

**Pruebas doradas:**

1. *Recuperación de parámetros:* simular 400 facturas (semilla 42) con `μ = ln 45`, `σ = 0,30`, `π = 0,03`, observando en la fecha `T` (aprox. 15–20 % abiertas). El ajuste debe recuperar `|μ̂ − μ| < 0,06`, `|σ̂ − σ| < 0,06`, `|π̂ − π| < 0,025`.
2. *Sesgo del método ingenuo:* el ajuste solo con pagadas debe producir un retraso medio **menor** que el del modelo censurado (el test documenta el sesgo optimista).
3. *Conservación:* `Σ_w P(w) + P(cola) = 1` con tolerancia `1e-9`.
4. *Monotonía:* `S(x)` es no creciente y `S(x) ≥ π_c` para todo `x`.
5. *Corridas:* cliente que paga el último viernes de cada mes; toda la masa predicha cae en fechas de corrida.
6. *Conversión del prior:* `σ = 0,2195 ± 0,0005`, `μ = 3,7826 ± 1e-4`.

### 6.6 M6 — Monitor de deriva de pago (aquí vive el EWMA, con su rol correcto)

El EWMA con `α = 0,3` **no se usa para predecir**: con 10–20 facturas por cliente es ruido (memoria efectiva de \~3 observaciones). Se usa como **carta de control** para detectar que un cliente cambió de conducta.

```
z_i = (ln d_i − μ̂_c) / σ̂_c          (para facturas abiertas: z mínimo observado, usando ln a_i)
EWMA:  Z_t = λ z_t + (1 − λ) Z_{t−1},  Z_0 = 0,  λ = 0,2
  Límite de control: ± L × √( λ/(2−λ) × [1 − (1−λ)^{2t}] ),   L = 2,7
CUSUM unilateral:  C_t = max(0, C_{t−1} + z_t − k),  k = 0,5,  alarma si C_t ≥ h = 4,0
```

Se aplica por cliente y a la **cartera completa** (mediana mensual de `z`). La alarma de cartera es la señal temprana de «crisis sistémica» (cierres de mes, contracción) que el GARCH original pretendía capturar.

**Prueba dorada (CUSUM):** `z = [0,1; 0,2; −0,1; 1,5; 1,8; 2,2; 2,0]` con `k = 0,5`, `h = 4,0` → `C = [0; 0; 0; 1,0; 2,3; 4,0; 5,5]`; **la alarma salta en el índice 6** (tolerancia `1e-9`).

### 6.7 M6b — Simulador de caja Monte Carlo: Cash-at-Risk y Buffer con fórmula

**Por qué:** convierte todos los modelos en las dos respuestas que el dueño necesita: *¿cuándo me quedo sin plata?* y *¿cuánta liquidez debo tener reservada?* Reemplaza al GARCH y al «colchón sin fórmula».

**Configuración:** horizonte 13 semanas (91 días, pasos diarios, solo días hábiles bancarios para movimientos), `N = 10.000` simulaciones, semilla fija, 100 % vectorizado con NumPy, objetivo < 2 s en Mac M3.

**Entradas (ingresos):** cada factura abierta, más cada viaje ya entregado y por facturar, más viajes planificados; cada una con su distribución de M5 y una extracción de parámetros del posterior.

**Factor sistémico (los retrasos y los impagos se correlacionan en las crisis):**

```
Z_s ~ N(0,1)                                   (un shock por simulación)
μ_{c,s} = μ_c + β_c × σ_sys × Z_s              (β_c = carga sistémica, por defecto 0,5; σ_sys estimada
                                                 como desv. estándar de la mediana mensual de z, mínimo 0,05)
Impago correlacionado (cópula gaussiana de un factor):
  factura i impaga en s  ⇔  √ρ × Z_s + √(1−ρ) × ε_{i,s} > Φ⁻¹(1 − π_c),   ρ = 0,15
```

**Salidas (egresos):**

- **Ciertos y con fecha:** leasing, sueldos base, seguros, F29 calculado por M4 con la facturación **de cada escenario**.
- **Variables por viaje:** diésel, viáticos, peajes, con multiplicador `LogNormal(0, 0,08)` por viaje y un factor común de precio del combustible.
- **Reparaciones:** proceso de Poisson compuesto por camión: `λ_k` eventos por 10.000 km (inicial 0,8) y severidad `LogNormal` con mediana 350.000 CLP y `σ = 0,9` (todo a calibrar con historial).
- **Deuda:** cuotas mínimas de tarjeta y línea; el costo de la línea solo si se usa.

```
B_{s,t} = B_0 + Σ ingresos_{s,≤t} − Σ egresos_{s,≤t}       (saldo sin línea ni buffer)
M_s     = mín_{t ≤ H} B_{s,t}
CaR_95  = max(0, − Cuantil_{0,05}(M_s))
Buffer_requerido = CaR_95 + reserva_operativa            (reserva = 1 semana de costos fijos, en params)
Caja_libre = B_0 − Buffer_requerido
P_quiebre(w) = media( 1[ mín_{t ∈ semana w} B_{s,t} < 0 ] )
```

**Semáforo:** verde si `P_quiebre(13 sem) < 5 %`; amarillo 5–15 %; rojo si `> 15 %` **o** `P_quiebre(sem. 1–4) > 5 %`. Cada alerta indica semana crítica, monto en riesgo y las **tres palancas** más baratas (M9).

**What-if (API):** `POST /finance/simulate` acepta palancas (factorizar facturas X, diferir un pago, agregar o quitar un viaje, retirar un camión, retiro del dueño) y recalcula con la misma semilla para comparar.

**Pruebas doradas:**

1. *Degeneración:* con `σ → 0`, `π = 0`, `ρ = 0`, sin shocks ni multiplicadores, la simulación coincide con la proyección determinista **al peso** (diferencia ≤ 1 CLP) en todos los días.
2. *Caso analítico:* una factura de `10.000.000` que se paga con certeza el día 30; egresos ciertos de `8.000.000` el día 10; `B_0 = 3.000.000`. El saldo mínimo es `−5.000.000` el día 10 → **`CaR_95 = 5.000.000`**, `P_quiebre = 1` en la semana 2.
3. *Traslación:* aumentar `B_0` en `x` debe dar `CaR' = max(0, CaR − x)` exacto (tolerancia 1 CLP).
4. *Convergencia:* con dos semillas distintas, el `CaR_95` difiere menos de 2 %.
5. *Monotonía:* subir `σ_sys` o `ρ` nunca baja el `CaR_95`.

### 6.8 M7 — Decisión de fletes: valor económico, tarifa mínima y contraoferta

**Por qué:** reemplaza el *Freight Score* original (normalización indefinida, pesos sin método, compensación indebida, bloqueo que puede destruir valor). Un score sirve solo como **ranking visual**; la decisión sale de aquí.

```
Entradas por viaje: A (tarifa neta), desembolsos CV_j con fechas t_j, T_ciclo, km, cliente c,
                    t_cobro (P50 para el valor; P75 para decisión conservadora), π_c, rec (recuperación ante impago),
                    IVA_d = 19 %·A, IVA_c_viaje, fecha F29 (t_F29), costo marginal de capital r_m

Pérdida esperada:        PE = π_c × A × (1 − rec)
Costo financiero:        CF = r_m/30 × Σ_j CV_j × max(0, t_cobro − t_j)
Costo del IVA:           CI = r_m/30 × max(0, IVA_d − IVA_c_viaje) × max(0, t_cobro − t_F29)
Costo por espera no cobrada: CE = días_espera_no_cobrados × F_k

Valor = A − CV − PE − CF − CI − CE
Capital comprometido (peso-mes) = Σ_j CV_j × max(0, t_cobro − t_j)/30 + IVA_neto × max(0, t_cobro − t_F29)/30
Eficiencia = Valor / Capital comprometido           Valor_por_día_ciclo = Valor / T_ciclo
```

**Tarifa mínima (forma cerrada).** `Valor` es lineal en `A`: `Valor(A) = a·A − b`, con `a = 1 − π_c(1 − rec) − 0,19 × r_m × g/30`, `b = CV + CF + CE − r_m × g × IVA_c_viaje/30`, `g = max(0, t_cobro − t_F29)`.

```
Tarifa_mínima A* = (V_min + b) / a        con V_min = h × T_ciclo     (h = aporte mínimo por día de ciclo, en params)
```

**Orden de decisión (vetos primero, luego rentabilidad):**

1. **V1 — Contribución:** si `CM_viaje ≤ 0` → **ROJO** (destruye valor incluso con el camión parado).
2. **V2 — Exposición:** si `Exposición_c + A > Límite_c` (M8) → **ROJO**, salvo anticipo o pago contado que lo reduzca.
3. **V3 — Caja:** si agregar el viaje eleva `P_quiebre` sobre 10 % en la simulación → **ROJO «no financiable hoy»** y se ofrece la contraoferta (anticipo, factoring, o postergar).
4. **V4 — Conducta:** alarma roja de deriva (M6) del cliente → **AMARILLO** con exigencia de anticipo.
5. Si `0 < Valor_por_día_ciclo < h` → **AMARILLO + contraoferta**; si `≥ h` → **VERDE**.

**El sistema nunca solo bloquea:** genera una **contraoferta ordenada**: (i) tarifa `A*`; (ii) tarifa actual con anticipo `p %` al cargar (recalcula `CF`); (iii) pago contado o a 7 días; (iv) factorizar la factura (M9); (v) otra ruta de retorno para bajar `km_total`. Muestra el costo de cada una y la mínima combinación que lleva el viaje a verde.

**Cuando la caja es el cuello de botella** se ordenan los viajes por `Eficiencia`; cuando hay caja de sobra, por `Valor`.

**Pruebas doradas** (`r_m = 2,5 %` mensual, interés simple, sin IVA):

- **Flete A:** `A = 1.000.000`, `CV = 700.000` desembolsado el día 0, cobro día 90 → `CF = 52.500`, **`Valor = 247.500`**, capital `2.100.000` peso-mes, **`Eficiencia = 0,117857`**.
- **Flete B:** `A = 850.000`, mismo `CV`, cobro día 30 → `CF = 17.500`, **`Valor = 132.500`**, capital `700.000`, **`Eficiencia = 0,189286`**.
- Con caja disponible de `700.000` el sistema debe elegir **B**; con `≥ 2.800.000` debe poder tomar ambos si no se solapan; ordenado por `Valor` gana A y por `Eficiencia` gana B.
- Con `π = 2 %`, `rec = 0`, `V_min = 150.000`, `CV = 700.000`, cobro día 90: **`A* = ceil(902.500 / 0,98) = 920.919`**.
- `CM_viaje ≤ 0` debe devolver ROJO sin importar `Eficiencia`.

### 6.9 M8 — Exposición y límite de crédito por cliente

**Por qué:** el cliente grande usa tu caja como financiamiento gratuito. El límite se calcula, no se «siente».

```
Exposición_c = Σ saldo abierto_c + WIP_c + Σ viajes aprobados aún no facturados_c
K            = capacidad de financiamiento = Caja_libre + línea de sobregiro autorizada + factoring pactado disponible
φ            = CV / Ingreso  (proporción promedio de costo desembolsado sobre venta)

L_conc_c = ℓ_conc × K / φ                     (ℓ_conc = máx. fracción de K en un cliente; inicial 30 %)
L_loss_c = ℓ_loss × CM_mensual / max(π_c, π_min)   (ℓ_loss = pérdida tolerable como fracción del margen mensual; inicial 25 %)
Límite_c = min(L_conc_c, L_loss_c) × factor_deriva   (factor_deriva = 0,5 si alarma roja de M6; si no, 1)

Concentración de ventas:  HHI = Σ s_c²   (s_c = participación del cliente c en ventas 90 d);   alerta si HHI > 0,25 o top-1 > 40 %
Pérdida esperada de cartera:  EL = Σ π_c × saldo_c
```

**Prueba dorada:** `K = 30.000.000`, `ℓ_conc = 0,30`, `φ = 0,70` → `L_conc = 12.857.142` (piso). `CM_mensual = 6.000.000`, `ℓ_loss = 0,25`, `π_c = 0,03` → `L_loss = 50.000.000`. `Límite = 12.857.142`. Con exposición `11.000.000` y un viaje de `2.000.000`, el sistema debe marcar **excede el límite** (13.000.000 > 12.857.142).

### 6.10 M9 — Asesor de financiamiento: factoring, anticipo, tarjeta y retiros del dueño

**Factoring de una factura** (monto `A`, porcentaje anticipado `p`, comisión fija `c_f`, tasa mensual `r_f`, días restantes esperados hasta el cobro `d_rem` según M5):

```
Costo_factoring = A × ( c_f + p × r_f × d_rem/30 )          (+ IVA sobre comisión si corresponde; en params)
Neto recibido hoy = p × A − Costo_factoring
Costo efectivo mensual = Costo_factoring / ( p × A × d_rem/30 )
Costo efectivo anual   = (1 + costo_mensual)^12 − 1
```

**Regla de decisión:** factorizar una factura si (i) la simulación M6b proyecta `P_quiebre` sobre el umbral **y** el costo efectivo es menor que la alternativa (tarjeta, sobregiro), o (ii) el costo efectivo es menor que el **precio sombra de la caja** `λ` (M13): cada peso liberado financia fletes con mayor retorno. Para reunir un monto `X` de liquidez, se eligen primero las facturas con **menor costo por peso-día de anticipo** (las que se pagarán más tarde, donde la comisión fija pesa menos por mes).

**Tarjeta y deuda como deuda real:**

```
Saldo_{t+1}   = Saldo_t × (1 + i_m) + compras_t − pagos_t
Interés_mes   = Saldo_t × i_m               Costo anual efectivo = (1 + i_m)^12 − 1
Alerta de espiral:  Interés_mes > 15 % del CM mensual  ó  saldo creciente 3 meses seguidos con pago ≤ mínimo
Plan de pago (avalancha): pagar primero la deuda de mayor tasa con el flujo libre en P25 (conservador)
Tope de retiros del dueño: Retiro_máx_mes = max(0, α × (EBITDA_prom_3m − servicio_deuda))   solo con semáforo de caja verde
```

**Pruebas doradas:**

- Factoring: `A = 10.000.000`, `p = 0,9`, `c_f = 0,5 %`, `r_f = 1,8 %`/mes, `d_rem = 60` → `Costo = 374.000`; neto hoy `8.626.000`; **costo mensual efectivo `2,0778 %`**; anual **`≈ 27,99 %`** (tolerancia 0,1 pp).
- Tarjeta: saldo `8.000.000`, `i_m = 2,3 %` → **interés mensual `184.000`**; costo anual efectivo **`31,37 %`** (tolerancia 0,05 pp).

### 6.11 M10 — Flota: utilización, mantención, neumáticos, documentos

```
Utilización u = días en ruta / días calendario          Disponibilidad = días operativos / días calendario
Pérdida por causa = Σ días parado por código (H1..H5 de la sección 1.4) × F_k
Mantención: serie y_t = ln(costo_mantención / km) por camión; CUSUM de tendencia (k = 0,5σ, h = 4σ)
Preventiva por odómetro: alerta cuando km_restantes_al_servicio < 1.500; no asignar viaje cuyo km excede los restantes
Neumáticos (fase tardía): vida en km ~ Weibull(k, λ) con CENSURA (los montados son datos censurados);
  se predice P(falla antes de x km) y se programa recambio/recapado
Documentos (revisión técnica, permiso, seguro, licencia): alertas a 30, 15 y 7 días; vencido = camión no asignable
```

**Prueba dorada (Weibull):** con 200 neumáticos simulados (`k = 3`, `λ = 90.000 km`, 30 % censurados) el ajuste recupera `k` y `λ` con error relativo < 8 %.

### 6.12 M11 — Combustible: rendimiento esperado y detección de anomalías

**Por qué:** es el 35–45 % del costo y la principal vía de fuga.

```
litros_esperados = a_k × km + b_k × km × (carga_ton / capacidad_ton) + c_k × desnivel_acumulado_km
  (regresión robusta tipo Huber por camión, reentrenada semanalmente)
z_litros = (litros_cargados − litros_esperados) / σ_residual
Alerta si |z| > 3, o CUSUM(z) ≥ 4, o carga > capacidad_estanque × 1,02, o carga fuera de la ruta GPS
```

**Prueba dorada:** conjunto sintético con 8 % de robo en 15 % de los viajes: recall ≥ 0,8 con tasa de falsos positivos ≤ 0,05.

### 6.13 M12 — Plan de reactivación de camiones (revivir la flota)

El costo fijo `F_k` **ya se paga** parado: reactivar no lo crea, solo agrega contribución. Para cada camión parado `k` con costo de reactivación `R_k` (reparación, documentos), capital de trabajo `WC_k` (M2) y utilización alcanzable `u_k`:

```
Beneficio_incremental_día_k = u_k × CM_día_k
Requerimiento_caja_k       = R_k + WC_k
Payback_k (días)           = Requerimiento_caja_k / Beneficio_incremental_día_k
ROIC_mensual_k             = 30 × Beneficio_incremental_día_k / Requerimiento_caja_k
Factibilidad:  Caja_libre ≥ Requerimiento_caja_k   y   simulación M6b con el camión agregado: P_quiebre ≤ 10 %
Secuencia: ordenar por ROIC_mensual desc. Reactivar el siguiente solo cuando el anterior completó su primer ciclo de cobranza
           o la simulación confirma factibilidad. Tras cada reactivación: Caja_libre ← Caja_libre − Requerimiento + flujo reciclado.
Venta o arriendo: si EBITDA proyectado < 0 durante 3 meses y u* > u_alcanzable, evaluar vender, arrendar o subcontratar.
```

**Prueba dorada:** `R = 1.800.000`, `WC = 1.500.000`, `CM_día = 94.485`, `u = 0,6` → beneficio `56.691`/día; requerimiento `3.300.000`; **`Payback = 58,21 días`**; **`ROIC_mensual = 0,5154`**.

### 6.14 M13 — Asignación carga-camión con restricción de caja y precio sombra

Problema binario: `x_{j,k} = 1` si la carga `j` se asigna al camión `k`.

```
maximizar   Σ Valor_j × x_{j,k}
sujeto a:   cada carga a lo más a un camión; cada camión sin solapes de tiempo; compatibilidad (rampla, capacidad, permisos);
            horas de conducción; documentos vigentes;
            para cada semana w:  Σ Desembolso_{j,w} × x_{j,k} ≤ Caja_proyectada_P10_w − Buffer
```

Resolver con **OR-Tools CP-SAT** (versión fijada, límite 5 s) con *fallback* voraz por `Eficiencia`. El **precio sombra de la caja** `λ` sale del dual de la relajación lineal (`scipy.optimize.linprog`, HiGHS) y alimenta `r_m` en M7 y la regla de factoring de M9. **Prueba dorada:** en 50 instancias aleatorias con ≤ 8 cargas, la solución de CP-SAT coincide con la búsqueda exhaustiva.

### 6.15 M14 — Backtesting, calibración y puerta de promoción de modelos

```
Walk-forward semanal: para cada fecha T_k se ajusta el modelo SOLO con datos ≤ T_k y se pronostica el cobro de las 13 semanas siguientes.
Métricas: cobertura empírica del intervalo 80 %; pérdida pinball (q = 0,1; 0,5; 0,9); CRPS; WAPE del cobro semanal; Brier de P(pago ≤ 7 d); histograma PIT.
Baselines: B0 = fecha nominal · B1 = mediana del cliente · B2 = mediana del segmento
Promoción: el modelo candidato reemplaza al vigente SOLO SI
  (pinball_promedio_candidato ≤ 0,95 × pinball_mejor_baseline)  Y  (cobertura 80 % ∈ [75 %, 85 %])  Y  (≥ 8 semanas de backtest).
Si no gana, el sistema sigue mostrando «modelo simple» (B1) y lo dice en pantalla.
Modo sombra: 4 semanas calculando en paralelo antes de afectar el tablero. Registro de modelos: versión, hash de parámetros, ventana de datos, métricas, fecha, quién promovió.
```

**Prueba dorada:** con datos sintéticos generados por el propio modelo, la cobertura del intervalo 80 % debe quedar entre 76 % y 84 %; con datos de otra distribución (cola pesada) el sistema debe **detectar la descalibración** y no promover.

---

## 7. Modelo de datos (PostgreSQL + SQLModel)

**Reglas transversales:** todo monto `BIGINT` en CLP (nunca `float`); todo registro con `id`, `created_at`, `created_by`, `voided_at` (no se borra: se anula); toda modificación financiera escribe en `audit_log` (usuario, fecha, valor previo, valor nuevo); fechas con zona `America/Santiago`; extensión `btree_gist` habilitada.

```text
Maestros
  clients(id, rut, name, segment, credit_limit_override, is_active)
  client_terms(client_id, nominal_days, clock_start ENUM[recepcion_conforme, emision], requires_oc, requires_hes, portal, notes)
  payment_run_calendars(client_id, rule ENUM[fixed_dates, weekday_of_month, weekly], params JSON, valid_from, valid_to)
  vehicles(id, plate, type, capacity_ton, odometer_km, lease_monthly, insurance_monthly, permit_annual, rt_annual, gps_monthly, owned BOOL)
  vehicle_documents(vehicle_id, kind ENUM[revision_tecnica, permiso, seguro, soap], expires_on)
  drivers(id, rut, name, base_salary, commission_pct, license_expires_on, is_active)
  routes(id, origin, destination, km, elevation_gain_m, toll_clp, notes)
  vehicle_status_log(vehicle_id, status ENUM[operativo, parado], cause ENUM[sin_caja, mantencion, sin_chofer, sin_carga, documentos, accidente, otro], from_ts, to_ts, est_repair_cost)

Operación
  trips(id, client_id, vehicle_id, driver_id, route_id, status, planned_start, planned_end, actual_start, actual_end,
        km_loaded, km_empty, net_revenue, advance_paid, ...,
        EXCLUDE USING gist (vehicle_id WITH =, tstzrange(planned_start, planned_end) WITH &&) WHERE (status <> 'cancelado'),
        EXCLUDE USING gist (driver_id  WITH =, tstzrange(planned_start, planned_end) WITH &&) WHERE (status <> 'cancelado'))
  delivery_docs(id, trip_id, kind ENUM[guia, oc, hes, estado_pago], folio, received_ok_at, file_url)
  trip_costs(id, trip_id, kind ENUM[diesel, peaje, viatico, comision, carga_descarga, estacionamiento, multa, otro], amount, paid_on, doc_id)
  fuel_events(id, vehicle_id, trip_id, liters, price_per_l_gross, amount, odometer_km, station, gps_lat, gps_lon, ts)
  maintenance_orders(id, vehicle_id, kind ENUM[preventiva, correctiva], odometer_km, amount, supplier, status, due_odometer_km)
  tire_events(id, vehicle_id, position, action ENUM[monta, retira, recapa], odometer_km, cost, residual_value)

Finanzas
  invoices(id, client_id, folio, issue_date, received_ok_date NULL, clock_estimated BOOL, nominal_due_date, net_amount, iva_amount, status, trip_ids[])
  payments(id, client_id NULL, bank_tx_id, amount, paid_on, method, unassigned_amount)
  payment_allocations(payment_id, invoice_id, amount)          -- muchos a muchos
  bank_accounts(id, bank, number, kind ENUM[cuenta_corriente, tarjeta, linea_credito])
  bank_transactions(id, account_id, posted_on, amount, description, category, counterparty_rut, reconciled BOOL, rule_id)
  expenses(id, category, amount, date, doc_id, vehicle_id NULL, is_owner_draw BOOL)
  debt_instruments(id, kind, balance, monthly_rate, min_payment, due_day, credit_limit)
  tax_periods(period, iva_d, iva_c, remanente, ppm, f29_due_date, paid_on)

Analítica y gobierno
  params(key, value, valid_from, valid_to, source, verified_by)    -- tasas, %, umbrales, con vigencia
  client_model_params(client_id, model_version, mu, sigma, pi, theta, cov JSON, n_obs, n_open, fitted_at)
  model_registry(version, kind, params_hash, data_window, metrics JSON, status ENUM[sombra, vigente, retirado], promoted_by, promoted_at)
  forecast_runs(id, kind, seed, as_of, model_version, inputs_hash, output JSON)
  alerts(id, kind, severity, entity, message_owner, suggested_actions JSON, created_at, ack_by, ack_at)
  audit_log(id, table, row_id, action, user, ts, before JSON, after JSON)
```

**Idempotencia:** todo job analítico escribe con clave `(kind, as_of, model_version)` y *upsert*; correr dos veces no duplica ni cambia resultados (misma semilla, mismas entradas, mismo hash).

---

## 8. Hoja de ruta por fases (con criterios de aceptación)

Cada fase termina con: **código + pruebas doradas verdes + documentación + demostración al dueño**. No se inicia una fase sin cerrar la anterior.

| Fase | Semanas | Objetivo | Entregables principales | Criterio de aceptación (DoD) | Lo que ve el dueño |
| --- | --- | --- | --- | --- | --- |
| **0. Cimientos** | 1–2 | Base sólida y segura | Auditoría del repo; `Money`, `calendar_cl`, `params`; `audit_log`; autenticación y roles; respaldos automáticos; CI (pytest, mypy estricto, ruff) | CI verde; migraciones reversibles; restauración de respaldo probada; cobertura ≥ 85 % en `core/` | Nada aún: infraestructura |
| **1. La Verdad** | 2–5 | Saber cuánto hay y cuánto se gana | PWA del chofer (captura < 30 s: gasto, foto, viaje); importador de cartola y RCV del SII; conciliación M0; libro de caja; P&L por camión, viaje y cliente; costeo M1; tarjeta como deuda; categoría `retiro_dueño`; registro de causas de detención | Saldo del sistema = saldo de cartola al peso por 30 días; ≥ 90 % de movimientos categorizados; goldens M0 y M1 verdes | Caja real y utilidad real por camión por primera vez |
| **2. Cobranza y tesorería** | 5–7 | Cobrar mejor y ver 13 semanas | Facturas con recepción conforme; aging M3 y WIP; DSO y capital de trabajo M2; motor tributario M4; flujo de 13 semanas **determinista** (usa la mediana B1); **Pantalla Cero v1**; alertas por WhatsApp/correo | Goldens M2, M3, M4 verdes; flujo reproduce la caja real de las últimas 8 semanas con error medido y publicado | Cuánto le deben, a quién llamar hoy, cuándo llega el F29 |
| **3. Comportamiento de pago** | 7–10 | Predecir cuándo pagan, con honestidad | M5 (cura + corrida, jerárquico, censura); M6 (EWMA/CUSUM); arnés M14; modo sombra | Goldens M5 y M6; informe de backtest; el modelo solo se muestra si pasa la puerta de promoción | Ventana de cobro por factura y alertas de deriva |
| **4. Caja estocástica** | 10–12 | Probabilidad de quiebre y buffer | `cash_simulator` (M6b); CaR 95 %; semáforo; what-if | Goldens M6b; < 2 s en Mac M3; alertas con ≥ 3 semanas de anticipación en el backtest histórico | Semáforo de caja y «cuánto debo tener guardado» |
| **5. Decisión de fletes** | 12–15 | Nunca más un flete a ciegas | M7 (valor, tarifa mínima, contraoferta); M8 (límites); M9 (factoring, tarjeta, tope de retiros); cotizador | Goldens M7, M8, M9; cotizar un flete en < 60 s | Cotizador con semáforo y contraoferta |
| **6. Flota y reactivación** | 15–19 | Revivir camiones en secuencia | M10, M11, M12, M13; calendario de documentos; mantención por odómetro | Goldens M10–M13; plan de reactivación con requerimiento de caja por camión | Qué camión reactivar primero y cuándo |
| **7. Autopulido y blindaje** | 19–22 | Que se mantenga solo y no se degrade | `scheduler` con puerta de promoción; registro de modelos; endurecimiento de seguridad; prueba de restauración; manual y capacitación | Reentrenamiento semanal sin intervención; ningún modelo promovido sin ganar el backtest | Sistema que se calibra solo y avisa si pierde calidad |

**Metas de negocio a validar:** a 30 días, caja real conciliada y P&L por camión; a 60 días, cola de cobranza diaria y flujo a 13 semanas; a 90 días, cero fletes aceptados sin tarifa mínima, tarjeta con tope de retiros y primer camión reactivado con plan financiado.

**Dependencias críticas fuera del código:** (1) el dueño y la administración deciden quién registra qué y cuándo; (2) el contador valida parámetros tributarios; (3) el abogado valida plazos legales de cobro; (4) los clientes entregan calendarios de pago (se pregunta en cada negociación).

---

## 9. Paquete de prompts para OpenClaw (agente de código con acceso al repo)

### 9.0 Técnicas de prompting empleadas y por qué

| Técnica | Cómo se aplica | Qué alucinación o error previene |
| --- | --- | --- |
| **Rol + misión + definición de éxito** | El Prompt Maestro fija quién es el agente y qué significa «terminado». | Código «elegante» que no resuelve el dolor del cliente. |
| **Contexto delimitado con etiquetas** (`<contexto>`, `<especificacion>`…) | Cada bloque tiene una función clara y no se mezcla con otro. | Confundir instrucciones con datos o ejemplos. |
| **Glosario del dominio** | Define HES, RCV, F29, corrida de pago, WIP, etc. | Interpretar mal términos chilenos del rubro. |
| **Anclaje al repositorio (grounding)** | Obliga a leer el repo y confirmar stack y versiones antes de escribir. | Inventar archivos, librerías, esquemas o APIs inexistentes. |
| **Especificación por ejemplo (few-shot ejecutable)** | Las **pruebas doradas** con números exactos son los ejemplos. | Fórmulas «parecidas» pero incorrectas. |
| **TDD obligatorio** | Primero se escriben las pruebas desde las doradas; luego el código. | Código sin verificación; tests escritos para que pasen. |
| **Plan antes de código (razonamiento acotado)** | El agente entrega un plan y espera validación en fases riesgosas. | Rediseños improvisados y alcance descontrolado. |
| **Verificación en dos pasadas** | Lista de autocrítica contra la especificación, y segunda lectura de la diferencia (diff). | Errores de unidades, signos, redondeo, zona horaria. |
| **Prohibiciones explícitas (negative prompting)** | Lista de «nunca» (float para dinero, GARCH, parámetros hardcodeados…). | Atajos que degradan el sistema. |
| **Regla de parada y escalamiento** | Si falta un dato o hay ambigüedad: registrar supuesto y preguntar, no inventar. | Alucinación por relleno. |
| **Rebanadas verticales pequeñas** | Cada tarea es una rebanada completa (modelo + servicio + API + test). | Código a medias que nunca se integra. |
| **Salida estructurada** | Informe de entrega con formato fijo. | Entregas ambiguas imposibles de auditar. |
| **Determinismo** | Semillas fijas, entradas versionadas, redondeo único. | Resultados irreproducibles. |

### 9.1 Prompt Maestro (se carga una vez, como instrucción de sistema permanente)

```text
<rol>
Eres el Ingeniero Principal de Software y Matemática Aplicada del proyecto Cerebro TEI, el ERP
de Transportes TEI SpA (transporte de carga terrestre en Chile; flota de 10 camiones, 3 activos).
Tienes acceso de lectura y escritura al repositorio. Trabajas en español técnico claro.
</rol>

<mision>
Construir, por fases, un ERP que le diga al dueño la verdad financiera y operativa de su empresa
y le recomiende decisiones concretas (qué fletes aceptar, cuándo cobrar, cuánta caja reservar,
qué camión reactivar). "Terminado" significa: todas las pruebas doradas de la fase pasan,
el código cumple los estándares y el dueño puede usar la pantalla sin explicación.
</mision>

<fuente_de_verdad>
El documento "Cerebro TEI — Plan Maestro" (secciones 1 a 8) es la especificación. Las fórmulas
de la sección 6 se implementan EXACTAMENTE como están escritas. Las pruebas doradas son
contratos: si una prueba dorada no pasa, el error está en tu implementación o en tu
comprensión; JAMÁS modifiques el valor esperado para que pase. Si crees que la especificación
tiene un error, NO lo corrijas en silencio: documenta la discrepancia en docs/adr/ y pregunta.
</fuente_de_verdad>

<protocolo_de_trabajo>
Para CADA tarea sigue estos pasos, en orden:
1. EXPLORAR: lista el árbol del repo; lee pyproject/requirements y lockfile; identifica versiones
   instaladas de Python, FastAPI, SQLModel, SQLAlchemy, NumPy, SciPy, pandas, APScheduler, pytest.
   Revisa el código existente relacionado. No asumas nada que no hayas visto.
2. INFORMAR: escribe un resumen de lo que entendiste (máx. 15 líneas), lo que ya existe, lo que
   falta y tus supuestos. Si hay ambigüedad que cambie el resultado, pregunta ANTES de programar.
3. PLANIFICAR: lista de archivos a crear o modificar y orden de trabajo, en rebanadas verticales.
4. PRUEBAS PRIMERO: traduce cada prueba dorada del documento a un test automatizado que falle.
5. IMPLEMENTAR: lo mínimo para que pasen, con tipado estricto y funciones puras en el núcleo
   matemático (sin acceso a base de datos dentro de los motores matemáticos).
6. VERIFICAR: ejecuta pytest, mypy --strict y ruff. Pega el resultado real; nunca digas que pasó
   si no lo ejecutaste.
7. AUTOCRÍTICA: recorre la lista de verificación (abajo) y marca cada punto con evidencia.
8. ENTREGAR: usa el formato de entrega exacto (abajo).
</protocolo_de_trabajo>

<antialucinacion>
- Antes de usar cualquier función de una librería, verifica que existe en la versión instalada
  (python -c "import x; help(x.f)" o lee el código instalado). No inventes parámetros.
- No actualices ni agregues dependencias sin pedirlo explícitamente y justificarlo en un ADR.
- Si no sabes un dato del negocio (tasa, porcentaje, plazo legal, fecha), NO lo inventes: créalo
  como parámetro en la tabla params con el valor inicial indicado en el documento y la marca
  verified_by = NULL, y avísalo en el informe.
- Si un archivo o tabla que esperabas no existe, di que no existe; no lo simules.
- Distingue siempre HECHO (verificado en el repo o por test) de SUPUESTO (declarado).
</antialucinacion>

<prohibiciones>
NUNCA: usar float para dinero (usa int en CLP o Decimal); hardcodear tasas, porcentajes o umbrales;
implementar GARCH o cualquier modelo no especificado; ajustar modelos de pago solo con facturas
pagadas; usar datetime sin zona; borrar datos (se anula); hacer migraciones destructivas;
llamar a servicios externos de red sin que se pida; dejar print() o código muerto; cambiar
el valor esperado de una prueba dorada; fusionar dos fases en una sola entrega; aprobar
automáticamente un viaje o bloquearlo sin ofrecer contraoferta (regla de producto).
</prohibiciones>

<estandares>
Python 3.x del repo; tipado estricto (mypy --strict); funciones puras en el núcleo matemático;
semillas explícitas (numpy.random.Generator); redondeo único con ROUND_HALF_UP; fechas en
America/Santiago; días hábiles con calendar_cl; nombres en inglés para código y español para
mensajes al dueño; docstrings con la fórmula y la sección del documento; errores con tipos propios.
</estandares>

<lista_de_verificacion>
[ ] Cada fórmula coincide con la sección citada (signos, unidades, días vs meses).
[ ] Todas las pruebas doradas de la tarea existen y pasan; ninguna fue alterada.
[ ] Hay pruebas de propiedades (monotonía, conservación, límites) donde la sección las pide.
[ ] No hay float en dinero ni parámetros hardcodeados.
[ ] Los datos censurados (facturas abiertas) se usan donde corresponde.
[ ] Idempotencia: ejecutar dos veces da el mismo resultado.
[ ] Los mensajes al dueño son claros, en español, con monto y acción sugerida.
[ ] mypy --strict, ruff y pytest en verde, con salida real pegada.
[ ] Supuestos y parámetros sin verificar listados.
</lista_de_verificacion>

<formato_de_entrega>
1) Resumen en 5 líneas. 2) Archivos creados/modificados. 3) Resultado real de pytest/mypy/ruff.
4) Tabla: prueba dorada -> estado. 5) Supuestos y parámetros sin verificar. 6) Riesgos y
   discrepancias con la especificación. 7) Siguiente paso recomendado. Nada más.
</formato_de_entrega>
```

### 9.2 Plantilla de Prompt de Fase

```text
<fase>Número y nombre</fase>
<contexto>Qué existe ya en el repo (el agente lo confirma en el paso EXPLORAR).</contexto>
<objetivo>Resultado de negocio en una frase.</objetivo>
<especificacion>Secciones del Plan Maestro a implementar (con números).</especificacion>
<entregables>Archivos, endpoints, tablas, pantallas.</entregables>
<pruebas_de_aceptacion>Pruebas doradas con números + propiedades.</pruebas_de_aceptacion>
<restricciones>Prohibiciones específicas de la fase.</restricciones>
<fuera_de_alcance>Lo que NO se hace en esta entrega.</fuera_de_alcance>
```

### 9.3 Prompts de fase (se pegan de a uno, en orden)

**Fase 0 — Cimientos**

```text
<fase>0 — Cimientos</fase>
<objetivo>Dejar una base segura y verificable sobre la que se construya todo lo demás.</objetivo>
<especificacion>Secciones 3, 5 y 7. Principios de diseño; estructura de carpetas; reglas transversales de datos.</especificacion>
<entregables>
1. Auditoría del repo (docs/audit.md): qué hay, qué se reutiliza, qué se reemplaza (en especial: el
   motor GARCH y el Freight Score originales se reemplazan; NO los extiendas).
2. core/money.py (tipo Money en CLP entero, suma, resta, multiplicación por tasa con redondeo único ROUND_HALF_UP).
3. core/calendar_cl.py (feriados de Chile por año como datos, día hábil siguiente/anterior, cuenta de días hábiles).
4. core/params.py + tabla params con vigencia, fuente y verified_by.
5. audit_log automático para toda escritura financiera; autenticación y roles (dueño, administrador, chofer, solo lectura).
6. Respaldos automáticos de PostgreSQL con prueba de restauración documentada.
7. CI: pytest, mypy --strict, ruff; cobertura mínima 85 % en core/.
</entregables>
<pruebas_de_aceptacion>
- Money: 454545,4545 redondea a 454545; 0,5 redondea a 1 (ROUND_HALF_UP); sumar 3 Money es asociativo.
- calendar_cl: un pago que cae en sábado o feriado se mueve al siguiente día hábil.
- Una modificación a un monto deja una fila en audit_log con valor previo y nuevo.
- Una migración se aplica y se revierte sin pérdida de datos.
</pruebas_de_aceptacion>
<restricciones>No crear lógica de negocio ni modelos matemáticos en esta fase.</restricciones>
```

**Fase 1 — La Verdad**

```text
<fase>1 — La Verdad</fase>
<objetivo>Que el dueño sepa cuánta caja real tiene y cuánto gana por camión, viaje y cliente.</objetivo>
<contexto>La empresa hoy no lleva registro confiable. Un chofer debe poder registrar un gasto con foto en menos de 30 segundos desde el celular (PWA).</contexto>
<especificacion>Secciones 2.2, 6.0 (M0), 6.1 (M1), 7 (tablas de Maestros, Operación y Finanzas).</especificacion>
<entregables>
1. Modelos SQLModel de la sección 7 (con las restricciones EXCLUDE btree_gist sobre trips).
2. Importadores: cartola bancaria (CSV/Excel; detectar formato por cabecera, no por posición) y RCV de ventas/compras del SII.
3. reconciliation_service.py: asignación pago↔facturas (subset-sum acotado a 25 candidatas) con confirmación humana si hay ambigüedad.
4. ledger_service.py con categorías, incluida retiro_dueño; la tarjeta de crédito como debt_instruments.
5. costing_engine.py: M1 completo (F_k, c_v, CM_viaje, T_ciclo, CM_día, u*).
6. P&L por camión, por viaje y por cliente; registro de causas de detención (vehicle_status_log).
7. PWA del chofer: gasto con foto, inicio/fin de viaje, carga de combustible con litros y odómetro.
</entregables>
<pruebas_de_aceptacion>Todas las de 6.0 y 6.1 (CM_viaje = 283.455; CM_día = 94.485; u* = 0,98428; subset-sum 7.350.000).
Además: dos viajes del mismo camión con horarios solapados deben ser rechazados por la base de datos.</pruebas_de_aceptacion>
<restricciones>Ningún modelo probabilístico todavía. Cada gasto sin documento queda marcado como «sin respaldo».</restricciones>
```

**Fase 2 — Cobranza y tesorería**

```text
<fase>2 — Cobranza y tesorería determinista</fase>
<objetivo>Que el dueño vea a quién cobrar hoy, cuándo llega el F29 y el flujo de las próximas 13 semanas.</objetivo>
<especificacion>Secciones 6.2 (M2), 6.3 (M3), 6.4 (M4), 10 (Pantalla Cero).</especificacion>
<entregables>
working_capital.py, ar_service.py, tax_engine.py; flujo de 13 semanas determinista que usa como fecha de cobro la
mediana histórica del cliente (baseline B1) o el plazo nominal si no hay historia, con etiqueta de confianza baja;
endpoint GET /owner/zero con los 5 números de la sección 10; alertas por correo/WhatsApp (adaptador abstracto, sin enviar de verdad en tests).
</entregables>
<pruebas_de_aceptacion>Todas las de 6.2 (ΔWC = 21.000.000; DSO = 45) y 6.4 (1.710.000; 1.210.000; remanente 7.290.000).
Backtest simple: el flujo proyectado hace 8 semanas vs la caja real; reportar el error, sin ocultarlo.</pruebas_de_aceptacion>
<restricciones>No implementar aún el modelo estadístico de pago; usar solo el baseline B1.</restricciones>
```

**Fase 3 — Comportamiento de pago**

```text
<fase>3 — Modelo de comportamiento de pago</fase>
<objetivo>Predecir con honestidad cuándo entra el dinero, usando datos censurados y calendarios de pago.</objetivo>
<especificacion>Secciones 6.5 (M5), 6.6 (M6), 6.15 (M14).</especificacion>
<entregables>payment_model.py (cura + corrida, MAP jerárquico con scipy L-BFGS-B, Laplace/bootstrap), drift_monitor.py (EWMA y CUSUM),
backtesting.py (walk-forward, pinball, cobertura, puerta de promoción), model_registry en modo sombra.</entregables>
<pruebas_de_aceptacion>Las seis de 6.5, la de 6.6 y la de 6.15. En particular: recuperación de parámetros con semilla 42, sesgo del ajuste solo con pagadas,
conservación de probabilidad, y que el sistema NO promueva el modelo si no vence al baseline.</pruebas_de_aceptacion>
<restricciones>Prohibido ajustar solo con pagadas. No mostrar al dueño un modelo que no pasó la puerta; en ese caso mostrar «modelo simple».</restricciones>
```

**Fase 4 — Caja estocástica**

```text
<fase>4 — Simulador de caja Monte Carlo</fase>
<objetivo>Entregar probabilidad de quiebre por semana y el buffer de liquidez con fórmula.</objetivo>
<especificacion>Sección 6.7 (M6b).</especificacion>
<entregables>cash_simulator.py vectorizado, 10.000 simulaciones, factor sistémico y cópula, egresos ciertos e inciertos, CaR 95 %, semáforo,
endpoint POST /finance/simulate con palancas (what-if), persistencia en forecast_runs con semilla e inputs_hash.</entregables>
<pruebas_de_aceptacion>Las cinco de 6.7 (degeneración al peso; CaR = 5.000.000 en el caso analítico; traslación exacta; convergencia < 2 %; monotonía). Tiempo < 2 s en Mac M3.</pruebas_de_aceptacion>
<restricciones>Sin bucles de Python sobre simulaciones; vectorizar con NumPy. No usar GARCH.</restricciones>
```

**Fase 5 — Decisión de fletes**

```text
<fase>5 — Decisión de fletes, crédito y financiamiento</fase>
<objetivo>Que el dueño cotice un flete en menos de 60 segundos y reciba semáforo con contraoferta.</objetivo>
<especificacion>Secciones 6.8 (M7), 6.9 (M8), 6.10 (M9).</especificacion>
<entregables>freight_decision.py, credit_policy.py, financing_advisor.py; pantalla Cotizador; tarifa piso por ruta.</entregables>
<pruebas_de_aceptacion>Flete A: valor 247.500, eficiencia 0,117857. Flete B: 132.500, 0,189286. Tarifa mínima 920.919.
Límite de crédito 12.857.142. Factoring: costo 374.000, 2,0778 % mensual. Tarjeta: interés 184.000; 31,37 % anual. CM ≤ 0 devuelve ROJO.</pruebas_de_aceptacion>
<restricciones>Nunca solo bloquear: siempre ofrecer contraoferta. Vetos antes que rentabilidad (orden de 6.8).</restricciones>
```

**Fase 6 — Flota y reactivación**

```text
<fase>6 — Flota, combustible y reactivación</fase>
<objetivo>Atacar combustible y mantención, y producir el plan de reactivación de camiones.</objetivo>
<especificacion>Secciones 6.11 a 6.14 (M10 a M13).</especificacion>
<entregables>fleet_analytics.py, fuel_anomaly.py, reactivation_planner.py, load_assignment.py (OR-Tools con versión fijada y fallback voraz); calendario de documentos.</entregables>
<pruebas_de_aceptacion>Payback 58,21 días y ROIC 0,5154; Weibull con error < 8 %; detección de robo con recall ≥ 0,8; CP-SAT igual a fuerza bruta en 50 instancias.</pruebas_de_aceptacion>
<restricciones>Si OR-Tools no está instalado, pedir autorización antes de agregarlo.</restricciones>
```

**Fase 7 — Autopulido y blindaje**

```text
<fase>7 — Autopulido semanal y endurecimiento</fase>
<objetivo>Que los modelos se reentrenen solos sin degradarse y que el sistema sea seguro.</objetivo>
<especificacion>Secciones 6.15 (M14), 7 (model_registry), 11.</especificacion>
<entregables>tasks/scheduler.py con APScheduler: diario (importar, conciliar, aging, simular) y semanal (reentrenar en modo sombra, puerta de promoción, informe);
registro de modelos; revisión de seguridad (roles, secretos, respaldos cifrados); runbook y manual del dueño.</entregables>
<pruebas_de_aceptacion>Un modelo peor que el vigente NO se promueve; correr el job dos veces no duplica resultados; restaurar un respaldo reproduce el saldo al peso.</pruebas_de_aceptacion>
```

### 9.4 Protocolo de revisión humana entre fases

Antes de pegar el siguiente prompt de fase, quien supervisa verifica: (1) el informe de entrega usa el formato exacto; (2) **ninguna** prueba dorada fue modificada (`git diff` sobre los archivos de test); (3) la lista de parámetros sin verificar se envía al contador o abogado; (4) el dueño probó la pantalla con datos reales; (5) se hizo `git tag` de la fase. Si algo falla, se pega un **prompt de corrección**: *«La prueba X falla con este resultado real: \[pegar\]. Identifica la causa raíz antes de tocar código. No cambies el valor esperado.»*

---

## 10. Lo que ve el dueño: facilitarle la vida

La matemática no sirve si el dueño no la entiende en 30 segundos. Toda salida se escribe en lenguaje de negocio, con monto, probabilidad y acción.

### 10.1 Pantalla Cero (08:00 cada día, también por WhatsApp)

| # | Número | Ejemplo de mensaje |
| --- | --- | --- |
| 1 | **Caja real conciliada hoy** | «Tienes $4.280.000 en banco. Tarjeta usada: $3.100.000 (cuesta ≈ $71.000/mes en intereses).» |
| 2 | **Peor momento de las próximas 4 semanas (P10)** | «Con 90 % de certeza, tu caja no baja de $850.000 antes del viernes 13.» |
| 3 | **Probabilidad de quedar bajo cero en 13 semanas** | «Riesgo de quiebre de caja: 18 % (ROJO). Semana crítica: la 5, por el F29 de $1.710.000.» |
| 4 | **Lo que te deben y lo que realmente cobrarás esta semana** | «Te deben $31.500.000. Esta semana entran entre $2,1 M y $6,4 M (80 %).» |
| 5 | **Camiones parados y su costo** | «3 camiones parados cuestan $280.000 por día. El primero a reactivar es el N.º 4: necesita $3,3 M y se paga en 58 días.» |

Debajo: **las 3 acciones del día**, ordenadas por impacto (por ejemplo: «Llama a Cliente X: factura de $4,2 M con 2,6 veces su plazo habitual», «Factura hoy las 2 guías entregadas hace 4 días: $2,3 M», «Factoriza la factura 1043: costo 2,1 % mensual, evita el rojo de la semana 5»).

### 10.2 Rituales

- **Diario (5 min):** Pantalla Cero y cola de cobranza.
- **Lunes (20 min):** flujo de 13 semanas, semáforo de clientes, camiones y documentos por vencer.
- **Mensual (60 min):** P&L por camión, ruta y cliente; tarifa piso vs tarifa efectiva; revisión de la tarjeta y del tope de retiros; informe de calibración de modelos.

### 10.3 Cotizador (Fase 5)

El dueño ingresa cliente, ruta, tarifa y plazo. En menos de 60 segundos obtiene: semáforo, tarifa mínima, eficiencia de capital, exposición del cliente y la **contraoferta** con su costo. Si el cliente rechaza, el sistema registra el motivo para afinar el piso.

### 10.4 Chofer

PWA móvil de una mano: foto de la boleta, monto, tipo; botón de inicio y fin de viaje; carga de combustible con litros y odómetro. **Sin captura no hay rendición ni comisión liquidada**; es la palanca para que los datos existan.

---

## 11. Riesgos, gobierno y decisiones previas

| Riesgo | Probabilidad | Mitigación |
| --- | --- | --- |
| **Nadie registra los datos** (el riesgo número uno) | Alta | PWA de 30 segundos; comisión y viáticos liquidados solo con registro; Fase 1 antes que cualquier modelo |
| La IA «arregla» una prueba en vez del código | Media | Regla de oro en el Prompt Maestro; revisión de `git diff` sobre tests entre fases |
| Parámetros tributarios o legales erróneos | Media | Todo en `params` con `verified_by`; revisión de contador y abogado antes de usarlos en decisiones |
| Sobreajuste con pocas facturas | Alta | Prior jerárquico, baseline obligatorio y puerta de promoción; mostrar «confianza baja» |
| Falsa sensación de seguridad | Media | Mostrar siempre intervalos, probabilidad y calidad de datos; nunca «blindado» |
| Pérdida de datos o falla del equipo local | Media | Respaldo automático cifrado fuera del equipo; restauración probada trimestralmente |
| Acceso indebido a datos financieros | Media | Roles, autenticación, `audit_log` y secretos fuera del repositorio |
| El dueño mezcla otra vez la plata personal | Alta | Categoría `retiro_dueño`, tope mensual y alerta |

**Decisiones que el dueño debe tomar antes de la Fase 1:** (1) quién ingresa y concilia a diario; (2) fecha de corte desde la cual se reconstruye la historia (recomendado: últimos 24 meses vía RCV del SII); (3) listado de los 10 camiones con su causa de detención; (4) acceso a cartolas y tarjeta; (5) política de retiros mientras dure la recuperación.

**Primeros 10 días (sin código):** conseguir el RCV de 24 meses y las cartolas; levantar la lista de camiones con costos fijos reales; preguntar a cada cliente su fecha de corrida de pago y qué documentos exige; separar la tarjeta de los gastos personales; fijar el sueldo del dueño.

**Criterio final de éxito:** a 90 días, el dueño puede responder en menos de un minuto, con números verificables: *cuánta plata tiene, cuánta tendrá en 4 semanas con 90 % de certeza, quién le debe y cuándo pagará, cuánto gana realmente cada camión y qué camión debe reactivar primero.* Si no puede, el sistema no está terminado, aunque todas las pruebas pasen.
