# Preguntas pendientes — decisiones y validaciones externas

> **Pregunta que responde:** ¿qué no está decidido o validado, y quién debe responderlo?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-10-29 · **Método:** lectura de código + reglas del catálogo
> **Caduca si:** el dueño, el contador, el asesor laboral o el corredor responden.
> **Re-verificar con:** `rg -n "D-0|P-0" docs/negocio/preguntas.md` y contrastar con `catalogo-reglas.md`

**Ninguna pregunta de este documento está respondida.** No se deduce una respuesta del
código: el código muestra lo que hoy hace, no lo que el negocio decidió ni lo que la
ley permite. `D-` es decisión del dueño; `P-` es validación de un tercero.

---

## 1. Decisiones del dueño

| ID | Pregunta | Evidencia de lo que hoy hace el código | Dueño | Bloquea a | Estado |
|---|---|---|---|---|---|
| **D-01** (R-01) | ¿La comisión del 10 % se calcula sobre el **flete neto**, sobre el **neto + recargos** o sobre el **total con IVA**? ¿Los recargos del viaje entran en la base? | La nómina suma solo `valor_flete_neto` (`backend/app/api/routes/liquidaciones.py:92-95`); el costo del núcleo usa `monto_total_neto` con recargos (`servicio_gastos.py:455-461`); el KPI usa `valor_flete_neto` (`kpi_engine.py:381`). El enunciado dice "facturación total" (`catalogo-reglas.md`, R-01) | Dueño del negocio (el tratamiento tributario es `P-04`) | Cierre de nómina, R-01, margen | Abierta |
| **D-02** (R-02) | ¿La exigencia de licencia **A5** es una obligación legal, una condición del seguro o una política interna? ¿Se aplica a todo tipo de equipo? | `0016:34-38` la declara regla global del dueño; `0004:1272-1274` dice que la clase es control interno, no validación legal; el servicio la vuelve bloqueante (`politicas.py:297-322`) | Dueño del negocio (el seguro es `P-03`) | R-02, asignación de choferes | Abierta |
| **D-03** (R-03) | ¿Se debe poder declarar la **fecha real de término** de un viaje, incluso si se cierra al día siguiente o a fin de mes? ¿Quién puede corregirla y hasta cuándo? | Al finalizar se estampa `date.today()` (`viajes.py:245-246`); el `PUT` acepta `fecha_fin` (`viajes.py:206-213`) pero la UI no la edita (`frontend/src/app/(app)/viajes/[id]/page.tsx:257`); el núcleo estampa `ahora_utc()` (`servicio_expediente.py:1270`) | Dueño del negocio | Cierre mensual, márgenes y KPI | Abierta |
| **D-04** (Freight Score) | ¿El Freight Score **bloquea** la asignación de un viaje o solo informa? Si bloquea, ¿desde qué umbral y quién puede aprobar la excepción? | Se calcula y persiste (`servicio_rentabilidad.py:398-416`), explica "rechazar o aprobar solo el dueño" (`:262-269`) y alerta bajo 60 (`servicio_alertas.py:343-354`), pero el despacho no lo consulta como condición | Dueño del negocio | Diseño de despacho, `P0` de aceptación | Abierta |
| **D-05** (OC) | ¿La OC del cliente bloquea el **despacho** o solo la **facturación**? ¿Es igual para todos los clientes o se configura por cliente? | El código la trata como requisito de facturación, no de despacho (`politicas.py:390-400`; `0009:89-93`), mientras el catálogo de KPIs propone "Bloquear sin OC" (`CATALOGO...:102`) | Dueño del negocio | Despacho, facturación, KPI #25 | Abierta |
| **D-06** (KPIs) | ¿Qué **metas**, **umbrales** y **dueños** rigen para cada KPI? ¿Se guardan en la plataforma o quedan como referencia? | La tabla `kpis` no tiene meta ni dueño (`backend/app/models/__init__.py:276-292`); las metas del catálogo son propuestas y se ajustan tras 3 meses (`CATALOGO...:474-476`) | Dueño del negocio | Tablero, alertas, evaluación de desempeño | Abierta |
| **D-07** (POD) | Si un viaje no puede obtener POD, ¿existe una **excepción** para facturar? ¿Quién la autoriza, con qué motivo y cómo se audita? | El trigger rechaza todo viaje sin POD (`0009:80-87`); el servicio también (`servicio_facturacion.py:494-501`); no hay tabla ni campo de excepción | Dueño del negocio | Facturación de excepciones | Abierta |

## 2. Validaciones de terceros

| ID | Pregunta | Evidencia de lo que hoy hace el código | Dueño | Bloquea a | Estado |
|---|---|---|---|---|---|
| **P-01** (IVA/F29) | ¿La tasa de IVA vigente es 19 %? ¿Qué operaciones son exentas? ¿Cómo se prorratea el crédito y cómo se declara el F29? | Legacy usa `iva_porcentaje` con default 19 (`facturas.py:35-43`; `finanzas.py:133-153`); el núcleo recibe `tasa_iva` con default 0,19 (`schemas.py:1543`). No hay F29 ni DTE | Contador | Facturación, KPI #70, cierre tributario | Abierta |
| **P-02** (Nómina) | ¿Cómo se calculan AFP, salud, cesantía, impuesto único y gratificación? ¿Qué descuentos y topes aplican? | La liquidación solo modela sueldo base, comisión, bonos, anticipos y descuentos (`models/__init__.py:226-241`; `liquidaciones.py:438-446`). No hay campos previsionales | Asesor laboral | Liquidación legal, pago de sueldos | Abierta |
| **P-03** (Seguro) | ¿Qué clase de licencia exige el seguro para cada tipo de equipo? ¿A5 es condición de cobertura? | La regla A5 se implementa como política global (`0016:34-38`); el array por tracto quedó deprecado (`0016:262-266`). No hay documento de póliza en el repo | Corredor de seguros | R-02, D-02, cobertura de siniestros | Abierta |
| **P-04** (Comisión) | ¿La comisión del chofer es remuneración? ¿Cómo se tributa, se documenta y se retiene? ¿Forma parte de la base de cotizaciones? | La comisión es un haber de la liquidación (`liquidaciones.py:438-446`) y un costo del viaje (`servicio_gastos.py:456-461`); no hay tratamiento tributario modelado | Contador | Nómina, costo, D-01 | Abierta |
| **P-05** (Combustible) | ¿Cómo se trata el **impuesto específico** al combustible y el IVA crédito de los gastos de combustible? ¿Se recupera total o parcialmente? | El gasto tiene `iva_recuperable` (`models/__init__.py:166`); el crédito se estima como `monto × tasa/(100+tasa)` (`finanzas.py:151-153`). No hay impuesto específico | Contador | Costo/km, IVA, margen | Abierta |
| **P-06** (DTE) | ¿Se emitirá DTE real? ¿Qué folios, tipos de documento y notas de crédito/débito se usarán? ¿Quién es el proveedor autorizado? | El folio es simulado (`0013:4`; `servicio_facturacion.py:548-556`); el legacy usa `numero_sii` de texto libre (`models/__init__.py:178`). No hay integración DTE/SII | Contador | Facturación real, anulación, cobranza | Abierta |

---

## 3. Qué haría falta para cerrar cada una

1. **Respuesta escrita y fechada** del dueño o del tercero, con la fuente que la
   sustenta (norma, póliza, contrato o decisión).
2. Actualizar la regla `R-0XX` en `catalogo-reglas.md` y, si cambia el
   comportamiento, abrir el handoff a `datos`/`backend`/`qa`.
3. Si la respuesta es "no se decide todavía", la regla sigue **ausente** o
   **pendiente**; no se implementa un supuesto.

## 4. Lo que este registro no hace

- No interpreta la ley ni la póliza.
- No convierte una práctica observada en obligación.
- No elige la base de la comisión, la meta del KPI ni el umbral del Freight Score.
- No responde por el dueño ni por el contador: solo deja la pregunta con destinatario
  y evidencia.
