# Fuentes de verdad — qué esquema manda por concepto

> **Pregunta que responde:** para cada concepto de negocio, ¿cuál es la fuente de verdad hoy, hay dos escrituras y existe reconciliación?
> **Dueño:** arquitectura · **Verificado:** 2026-10-29 · **Método:** lectura estática de DDL, routers legacy y servicios del núcleo; sin ejecución ni consultas.
> **Caduca si:** se agrega una pantalla que escribe un concepto, se ejecuta un cutover o se crea una sincronización.
> **Re-verificar con:** `grep -rn "api\\.\\(post\\|put\\|patch\\|del\\)" frontend/src/app` y `grep -rn "session.add\\|update(" backend/app/nucleo`

---

## 1. Regla de lectura

Una fila puede decir "dos escrituras" sin que exista doble escritura **en la misma operación**. El riesgo es que **dos pantallas distintas** escriben el mismo concepto en tablas distintas, con identificadores distintos y sin reconciliación. Eso es lo que se marca.

- 🟢 = leído en código/DDL con cita.
- 🟡 = inferido; se indica qué lo confirmaría.
- 🔴 = no determinable sin base/ejecución.

---

## 2. Matriz por concepto

| Concepto | Tabla(s) en `public` | Tabla(s) en `nucleo` | Fuente de verdad HOY | ¿Dos escrituras? | ¿Sincronización o detección de divergencia? | Riesgo |
|---|---|---|---|---|---|---|
| **Cliente** | `clientes` (`0001:47-58`) | `clientes` (`0004:158-186`) | Ninguna única. `/clientes` escribe `public`; `/maestros` y `/despacho` leen y escriben `nucleo`. | **Sí** 🟢 | No hay job, vista ni tabla de mapeo. El cutover copia una vez (`scripts/cutover_legacy.py:6-13`), no sincroniza. | **Alto**: mismo RUT con dos `id`; un viaje legacy no puede asociarse a un cliente del núcleo y viceversa. |
| **Chofer** | `choferes` (`0001:60-70`) | `choferes` (`0004:282-321`) | Ninguna única. Nómina legacy usa `public.choferes.porcentaje_produccion`; costo del núcleo usa `nucleo.choferes.porcentaje_comision`. | **Sí** 🟢 | Ninguna. `0017`/`0019` alinean el default del núcleo a 10 %, pero **no tocan `public`** (`0019:17-18,37-41`). | **Alto (dinero)**: dos porcentajes de comisión pueden pagar y costear distinto (SEC-003). |
| **Tracto** | `tractos` (`0001:72-84`) | `tractos` (`0004:191-230`) | Ninguna única. `/flota` escribe `public`; `/maestros` y despacho leen `nucleo`. | **Sí** 🟢 | Ninguna. El legacy no tiene tara/peso/capacidad; el cutover debe completarlos a mano. | **Alto**: un tracto legacy no es asignable en el núcleo hasta cargar datos que el legacy nunca pidió. |
| **Rampla** | `ramplas` (`0001:86-94`) | `ramplas` (`0004:235-277`) | Ninguna única. `/flota` escribe `public`; `/maestros` escribe `nucleo`. | **Sí** 🟢 | Ninguna; el legacy no tiene capacidad ni tipo completo (solo `plana/sider`, `0001:16`). | **Alto**: el núcleo exige capacidad y compatibilidad que el legacy no registra. |
| **Viaje** | `viajes` (`0001:97-112`) | `viajes` (`0004:542-698`) | Ninguna única. `/viajes` escribe `public`; `/despacho` y `/expediente` escriben `nucleo`. | **Sí** 🟢 | Copia one-way en el cutover; migra en `confirmado` y **sin recursos** (`scripts/cutover_legacy.py:6-13,378-401`), por lo que no copia la asignación ni crea reservas. Sin reconciliación posterior. | **Crítico**: dos ciclos de vida y dos libros de ocupación; un viaje legacy no reserva ni aparece en disponibilidad. |
| **Reserva / ocupación** | No existe | `reservas_recurso` (`0004:703-767`, `0006:9-18`) | `nucleo` es el único libro. | **No en reservas; sí en ocupación real** 🟢 | El legacy puede ocupar un recurso sin insertar reserva; no hay detección. | **Crítico (RA-02)**: doble asignación real; las 3 `EXCLUDE` solo protegen escrituras del núcleo. |
| **Factura** | `facturas` (`0001:127-143`) | `facturas_nucleo` (`0013:10-49`) | Ninguna única. `/facturacion` escribe `public`; `/cobranza` escribe `nucleo`. | **Sí** 🟢 | Ninguna. Folios con reglas distintas (`unique (numero_sii, cliente_id)` vs `unique (empresa_id, numero_factura)`). | **Crítico (tributario)**: dos numeraciones, dos estados y dos criterios de anulación; no hay DTE en ninguno. |
| **Pago** | Solo `facturas.estado` y `fecha_pago` (`0001:137-138`) | `pagos_nucleo` (`0013:78-98`) | Ninguna única. `/cobranzas` cambia estado en `public`; `/cobranza` registra pagos parciales en `nucleo`. | **Sí** 🟢 | Ninguna. | **Alto (dinero)**: un pago parcial del núcleo no se refleja en el legacy y viceversa; el saldo se calcula distinto. |
| **Gasto** | `gastos_viaje` (`0001:114-125`) | `viaje_gastos` (`0011:29-83`) | Ninguna única. `/viajes/[id]` escribe `public`; `/expediente/[id]` escribe `nucleo`. | **Sí** 🟢 | Ninguna. El legacy borra en duro (`gastos.py:92-102`); el núcleo aprueba/rechaza y conserva. | **Alto**: el margen histórico puede diferir o perderse; el legacy no exige aprobación. |
| **Usuario / identidad** | `usuarios` (`0001:36-45`) + `auth.users` | `usuarios_empresa` (`0004:139-153`) | `auth.users` es la identidad; **el rol sí está duplicado** (3 roles globales vs 8 por empresa). | **Sí (rol)** 🟢 | `public.handle_new_user` crea el espejo legacy (`0001:248-262`); no se crea membresía en `nucleo` automáticamente. | **Alto**: un usuario puede existir en un esquema y no en el otro; permisos distintos para la misma persona. |
| **Empresa / tenant** | No existe `empresa_id` en ninguna tabla | `empresas` (`0004:102-137`) | `nucleo` es la única fuente. | **No** 🟢 | No aplica. El legacy es global por diseño. | **Alto**: toda pantalla legacy opera sin filtro de empresa; no se puede presentar como aislada. |
| **Configuración** | `configuracion` (`0001:212-215`): IVA y alertas | `empresas` (`0004:116-125`) + `configuracion_costos` (`0012:8-25`) | Ninguna única: son **parámetros distintos** con nombres parecidos. | **Sí, con semántica distinta** 🟢 | Ninguna; el IVA solo existe en `public.configuracion` y no en el núcleo. | **Alto (tributario)**: el núcleo no tiene IVA configurable; el legacy no tiene costos por empresa. |
| **KPI** | `kpis` (`0003:5-20`) + `kpi_engine.py` | Alertas (`servicio_alertas.py`) y rentabilidad (`servicio_rentabilidad.py`) | Ninguna única: el legacy tiene motor de fórmulas; el núcleo, indicadores fijos. | **No compiten por la misma tabla, sí por el mismo nombre** 🟡 | Ninguna; no hay definición compartida de métrica. | **Alto**: dos "margen" distintos; el legacy no resta comisión (`kpi_engine.py:440`), el núcleo sí (`0011:115-127`). |
| **Orden de compra** | No existe | `ordenes_compra` + líneas (`0004:421-485`) | `nucleo` es la única fuente. | **No** 🟢 | No aplica. El legacy factura sin OC. | **Medio-alto**: el legacy puede facturar sin OC; el núcleo no. |
| **Tarifa** | No existe (solo `valor_flete_neto` libre en `viajes`) | `tarifas` (`0004:377-416`) | `nucleo` es la única fuente. | **No** 🟢 | No aplica. | **Medio**: el legacy no puede reproducir el precio del núcleo ni su vigencia. |
| **Documento habilitante** | Fechas sueltas: `tractos.vencimiento_revision_tecnica/seguro`, `choferes.vencimiento_licencia` (`0001:66,79-80`) | `documentos` versionados (`0004:326-372`) | Ninguna única. | **Sí** 🟢 | Ninguna; el legacy no bloquea por documento vencido al asignar. | **Alto**: el núcleo bloquea con documentos del núcleo; el legacy sigue despachando con fechas planas. |
| **Liquidación** | `liquidaciones`, `anticipos_chofer`, `ajustes_liquidacion` (`0001:151-186`) | No existe | `public` es la única fuente. | **No** 🟢 | No aplica. El núcleo solo estima la comisión como costo. | **Alto (laboral)**: no hay módulo equivalente; el PDF no es reproducible (SEC-002). |
| **Mantenimiento** | `pautas_mantenimiento`, `mantenimientos` (`0001:189-209`) | No existe (solo reserva tipo `mantenimiento`) | `public` es la única fuente. | **No** 🟢 | No aplica. | **Medio**: el núcleo no tiene preventivo por km; solo bloquea agenda. |

---

## 3. Diagnóstico de conjunto

1. **Solo 6 de 18 conceptos tienen una única fuente**: reserva, empresa, OC, tarifa, liquidación y mantenimiento. De esos, dos (liquidación y mantenimiento) viven **solo en el legacy**, que no es el destino.
2. **Ningún concepto tiene reconciliación automática.** No existe job, vista, tabla de mapeo ni consulta de divergencia. La única transferencia es el script de cutover, que es one-way y migra los viajes **sin asignación de recursos** (`scripts/cutover_legacy.py:6-13,378-401`): la asignación queda pendiente y debe hacerse en el núcleo con documentos reales.
3. **Los identificadores no son comparables.** No hay columna que enlace `public.clientes.id` con `nucleo.clientes.id`, ni `public.viajes.id` con `nucleo.viajes.id`. El cutover debe preservar o mapear; no está demostrado 🔴 (`select` de conteos antes/después).
4. **El legacy no participa del libro de ocupación.** Esta es la divergencia de mayor impacto operativo: todo lo demás puede corregirse con datos; una doble asignación puede costar un viaje, un seguro o una multa.
5. **La identidad es el bloqueo del cutover.** `public.usuarios` es la puerta de entrada de todo el backend legacy (`api/deps.py:9-28`) y `nucleo.usuarios_empresa` la del núcleo. Sin un mapeo `auth_id → membresía` no se puede retirar el legacy sin dejar usuarios fuera.

---

## 4. Regla operativa: un concepto, un esquema canónico

Antes de escribir una línea de código nueva:

1. **Declarar el dueño.** Todo concepto de la §2 debe tener un solo esquema canónico escrito en este documento y en el ADR correspondiente. Mientras no esté declarado, **no se agrega una tercera escritura**.
2. **Un solo escritor por operación.** La pantalla puede leer de ambos, pero la operación de negocio escribe en uno solo. Si necesita el otro, se resuelve por cutover, vista o evento explícito, no por doble `INSERT`.
3. **El corte se hace con el legacy congelado.** El flag `nucleo.cutover_control.legacy_escritura_congelada` debe estar en `true` (`0014:8-19`); hoy nace en `false` y `legacy_congelado()` falla en abierto (`servicio_cutover.py:38-39`), por lo que la garantía no está activa (RA-04).
4. **Toda divergencia se mide, no se supone.** Antes de declarar un concepto migrado: conteo por tabla, comparación de claves naturales (RUT, patente, número de factura) y consulta de huérfanos. Sin esa evidencia, el concepto sigue en "dos fuentes" 🔴.
5. **No se borra el legacy para "limpiar".** Se retira por módulo cuando exista paridad, datos migrados y reversibilidad (`docs/arquitectura/retiro-legacy.md`).

> **Criterio de éxito observable:** para cada concepto, una consulta de reconciliación devuelve 0 filas de diferencia y una sola pantalla puede escribir. Mientras eso no ocurra, la respuesta a "¿cuál manda?" es **"hoy, ninguna; depende de la pantalla"**.
