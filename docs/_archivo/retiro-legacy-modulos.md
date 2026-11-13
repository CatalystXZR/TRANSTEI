# Retiro del legacy — módulos sin equivalente en el núcleo

> **Pregunta que responde:** ¿qué hacen **hoy** los módulos legacy que **no** tienen
> equivalente en `nucleo`, qué se debe **portar con paridad** y qué se debe **retirar**?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-10-31 · **Método:** lectura de
> código legacy y del núcleo (`backend/app/api/routes/*`, `backend/app/nucleo/*`,
> `backend/app/models/__init__.py`, `supabase/migrations/0001_esquema_base.sql`,
> `backend/tests/*`) + DDL de migraciones.
> **Caduca si:** cambia un router, un servicio de dinero, una migración o se responde
> una `D-NN`/`P-NN` de §9.
> **Re-verificar con:**
> `rg -n "def _comision_chofer|def iva_resumen|def estado_mantenimiento|def actualizar_configuracion|def importar_choferes" backend/app`
>
> **Ninguna prueba se ejecutó en esta sesión** (sin shell ni base de datos). Las
> pruebas que se citan son **cobertura declarada**, no resultados verdes. Toda cifra
> es aritmética hecha a mano sobre el código; el nivel de certeza se marca con
> 🟢 (leído en código) / 🟡 (inferido) / 🔴 (no determinable).

Este documento **no define reglas nuevas**. Extrae las que ya están en código, las
numera en [`catalogo-reglas.md`](catalogo-reglas.md) (`R-05…R-09`, `CN-03…CN-09`) y
recomienda portar o retirar. Lo tributario y lo laboral **no se responden acá**: se
registran como preguntas con destinatario (`P-09…P-11`) o decisión del dueño
(`D-19…D-21`).

---

## 1. Resumen ejecutivo

| # | Módulo legacy | Existe en `nucleo` | Qué es hoy | Recomendación |
|---|---|---|---|---|
| 1 | Liquidaciones / anticipos / ajustes / PDF | **No** (solo `nucleo.choferes.porcentaje_comision`) | Nómina mensual con comisión R-01, bonos, descuentos, anticipos y PDF de remuneraciones | **Portar con paridad**, corrigiendo 6 defectos (§3.5) |
| 2 | IVA (`/iva/resumen`) | **No** (el núcleo solo almacena `iva` por factura) | Estimación débito − crédito con tasa de `configuracion` | **Retirar el cálculo de crédito** y reimplementar un resumen único en el núcleo; el débito es reutilizable |
| 3 | Mantenimiento (pautas + estado por km) | **No** (el núcleo solo tiene reservas tipo `mantenimiento`) | Pauta por ítem con intervalo km y semáforo por odómetro | **Portar con paridad** (es la única fuente de este control) |
| 4 | Configuración global (4 claves) | **Parcial** (`nucleo.configuracion_costos`, `empresa.dias_alerta_documentos`) | Tabla clave/valor global, editable por admin, sin validación ni historial | **Retirar con reemplazo**: config por empresa en el núcleo; no apagar antes |
| 5 | Export/Import CSV | **No** (0 usos de `csv` en `nucleo`) | Export de viajes/facturas/liquidaciones; import de clientes/choferes | **Retirar el import**; **portar el export** como reporte de solo lectura con permisos |

Consecuencia para la FASE 2: **1 y 3 son portables con paridad funcional**
(corrigiendo los defectos de §3.5) y el **export** es portable como reporte de solo
lectura; **2, 4 y el import no deben portarse tal cual**, porque su comportamiento
actual incluye supuestos no declarados (base del crédito IVA), configuración global sin
vigencia y validaciones que hoy producen 500 o datos inválidos.

---

## 2. Método, alcance y límites

- Se leyó el código legacy **completo** de los cinco módulos y se contrastó con
  `backend/app/nucleo/` para confirmar la ausencia de equivalente.
- Se usó `grep`/lectura de archivos. **No** se ejecutó `make test`, ni consultas SQL, ni
  el servidor: no hay evidencia de ejecución en esta sesión 🔴.
- Los casos numéricos (`CN-03…CN-09`) están calculados a mano; su aritmética completa
  vive en `catalogo-reglas.md` (fuente canónica) y acá se resume el resultado.
- No se tocó código, migraciones ni datos. Solo `docs/negocio/**`.

---

## 3. Módulo 1 — Liquidaciones, anticipos y ajustes

### 3.1 Qué hace hoy (reglas implementadas)

| Regla | Implementación | Estado |
|---|---|---|
| Comisión = % de la producción **facturada** del mes, mes por **emisión** de factura | `backend/app/api/routes/liquidaciones.py:51-96` (candidatos `:61-63`; primera factura no anulada `:66-75`; ventana `[inicio, fin)` `:82-84`; fallback viaje `facturado` sin factura `:87-91`; `suma × porcentaje` y `quantize` `:92-95`) | 🟢 implementada (R-01/R-05) |
| Porcentaje configurable por chofer, default 10 % | `backend/app/models/__init__.py:103-105` (`le=1`, fracción 0,10) | 🟢 |
| Anticipo: monto > 0, mes `YYYY-MM` validado por regex, imputado por `mes_liquidacion` | `liquidaciones.py:117-143`; `0001:151-159` | 🟢 |
| Ajustes: `tipo ∈ {bono, descuento}`, `monto ≥ 0`, `concepto` libre | `liquidaciones.py:177-203`; `0001:161-169` | 🟢 |
| Líquido = sueldo base + comisión + bonos − descuentos − anticipos | `liquidaciones.py:253` (resumen) y `:332-336` (cálculo) | 🟢 implementada (R-05) |
| `total_ajustes` = bonos − descuentos (puede ser negativo) | `liquidaciones.py:335`; columna sin `CHECK` (`0001:178`) | 🟢 |
| Liquidación `emitida` no se recalcula (409) | `liquidaciones.py:326-330` | 🟢 |
| Emitir = cambiar estado, sin usuario, fecha ni folio | `liquidaciones.py:345-358` | 🟢 |
| Resumen mensual recalcula todo en vivo (incluidas emitidas) | `liquidaciones.py:229-275` | 🟢 |
| PDF: recalcula haberes, imprime total almacenado; RUT de la empresa es un **placeholder** | `liquidaciones.py:438-446,466`; `:411` (`RUT: 00.000.000-0`) | 🟢 |
| Borrado duro de anticipos y ajustes, sin auditoría | `liquidaciones.py:146-156,206-216` | 🟢 |

**Qué NO hace hoy** (para no prometer paridad sobre algo inexistente):

- No modela AFP, salud, cesantía, impuesto único, gratificación ni topes legales
  (`models/__init__.py:226-241`): el PDF se titula "LIQUIDACIÓN DE REMUNERACIONES"
  (`:415`) pero no es un documento legal completo → `P-02`.
- No hay historial de versiones del borrador ni snapshot del porcentaje usado.
- No hay `empresa_id` en las tablas de nómina (`0001:151-186`); el esquema legacy
  completo tampoco lo tiene: es monoempresa.
- No hay bloqueo de base para editar una liquidación emitida (solo el servicio).
- El PDF no se persiste (`pdf_url` nunca se escribe) y no tiene folio ni hash.

### 3.2 Casos numéricos (resumen; aritmética completa en `catalogo-reglas.md`)

| CN | Escenario | Resultado esperado |
|---|---|---|
| CN-03 | 400.000 base + 10 % de 1.800.000 + 50.000 − 100.000 | comisión **180.000**; líquido **530.000** |
| CN-04 | 12,5 % sobre 1.000.009 → 125.001,125 con `quantize` sin `rounding` | **125.001,12** (HALF_EVEN) vs 125.001,13 (HALF_UP de las facturas) |
| CN-05 | anticipo 150.000 imputado a un mes ya emitido | **no se descuenta nunca**; el resumen muestra 380.000 y el documento 530.000 |
| CN-09 | factura de 200.000 posterior a la emisión | CSV **550.000** vs documento **530.000**; PDF con líneas que suman 550.000 y total 530.000 |

### 3.3 Lo que no está definido (no se puede asumir)

| ID | Qué falta | A quién |
|---|---|---|
| `D-01` (abierta) | Base de la comisión: flete neto, neto + recargos o total con IVA. La nómina suma **solo** `valor_flete_neto` (`:92-95`) | Dueño |
| `D-19` (nueva) | ¿Qué pasa con un anticipo imputado a un mes ya emitido, o con un anticipo mayor que los haberes? ¿Se arrastra al mes siguiente, se descuenta del finiquito, se rechaza al registrar? | Dueño |
| `P-02` (abierta) | Cálculo legal de AFP/salud/cesantía/impuesto único/gratificación y topes | Asesor laboral |
| `P-10` (nueva) | ¿El anticipo es un descuento lícito y con qué límite? ¿Se descuenta íntegro en el mes imputado? ¿Cómo se documenta? | Asesor laboral |
| `P-04` (abierta) | Tributación de la comisión (¿remuneración? ¿base de cotizaciones?) | Contador |

**No asumible:** ni la composición del líquido ni el descuento de anticipos son
"reglas del dueño" verificadas: son **comportamiento observado**. Portarlas como si
fueran ley laboral sería inventar una obligación.

### 3.4 Recomendación: **portar con paridad** (no rediseñar)

Motivo: es dinero de personas, se paga todos los meses, y **no existe nada equivalente
en el núcleo** (`nucleo.choferes.porcentaje_comision` es un campo, no un módulo). Si se
retira sin reemplazo, la empresa pierde la nómina.

Paridad mínima aceptable (mismos resultados que hoy):

1. Comisión = `(Σ valor_flete_neto de viajes con factura no anulada, mes por
   `fecha_emision`) × porcentaje`, redondeo **documentado y único**.
2. `total_liquido = sueldo_base (snapshot) + comisión + bonos − descuentos − anticipos`.
3. Anticipos y ajustes imputados por mes `YYYY-MM`; una liquidación emitida no se
   recalcula.
4. PDF con el detalle de viajes del período.

### 3.5 Defectos que **no** deben portarse (corregir en el núcleo)

1. **Anticipo huérfano** (CN-05): un anticipo imputado a un mes emitido no se descuenta
   nunca. Requiere `D-19` y una regla de arrastre o rechazo en el alta.
2. **Documento no reproducible** (CN-09): recalcular haberes e imprimir el total
   almacenado produce un PDF que no cuadra consigo mismo. El núcleo debe emitir un
   snapshot inmutable (o recalcular **todo** y versionar).
3. **Redondeo inconsistente** (CN-04): `quantize` sin `rounding`
   (`liquidaciones.py:95`) usa HALF_EVEN, mientras las facturas usan HALF_UP
   (`facturas.py:42-44`). Un solo criterio, explícito.
4. **Borrado sin rastro** de anticipos/ajustes (`:146-156,206-216`): al portar, anular
   con motivo y auditoría, no `DELETE`.
5. **RUT de la empresa placeholder** en el PDF (`:411`): un documento de remuneraciones
   con identidad falsa no es aceptable en producción.
6. **`total_liquido` negativo permitido** (`0001:179` sin `CHECK`): decidir si se
   bloquea o se trata como deuda del trabajador (`D-19`).

---

## 4. Módulo 2 — IVA

### 4.1 Qué hace hoy

| Aspecto | Implementación | Estado |
|---|---|---|
| Tasa: **no hardcodeada**, leída de `configuracion.iva_porcentaje` con default `"19"` | `facturas.py:35-36`; `finanzas.py:133`; `kpi_engine.py:401`; seed `0001:291` | 🟢 (valor 19 = seed, no norma → `P-01`) |
| IVA de la factura: `neto × tasa/100`, `ROUND_HALF_UP` a 2 decimales; exenta = 0 | `facturas.py:39-44,143` | 🟢 |
| Base = suma de `valor_flete_neto` de los viajes incluidos | `facturas.py:141` | 🟢 |
| `total = neto + iva` (sin `CHECK` en base) | `facturas.py:155`; `0001:134` | 🟢 |
| Vencimiento = emisión + `cliente.dias_pago` (default 30) | `facturas.py:145-147` | 🟢 |
| IVA almacenado: cambiar la tasa **no** reajusta facturas históricas (salvo cambio de `tipo`) | `facturas.py:192-194` | 🟢 (snapshot de hecho) |
| Resumen: débito = Σ `factura.iva` (afecta, no anulada, por emisión) | `finanzas.py:135-143` | 🟢 |
| Resumen: crédito = `Σ gasto.monto × tasa/(100+tasa)` | `finanzas.py:151-153` | 🟢 con supuesto no declarado |
| `a_pagar = max(débito − crédito, 0)` → **remanente no arrastrado** | `finanzas.py:182` | 🟢 |
| Redondeo del crédito: **por línea** en el detalle y **por total** en el resumen | `finanzas.py:171` vs `:181` | 🟢 (Δ en CN-06) |
| Tercera copia del mismo cálculo en el KPI | `kpi_engine.py:400-421` | 🟢 (versión duplicada) |
| Núcleo: `tasa_iva` **por request**, default 0,19; `iva = neto × tasa` | `nucleo/schemas.py:1543`; `servicio_facturacion.py:544`; `nucleo/models.py:1160` | 🟢 |
| Núcleo: **no existe** resumen de IVA | grep `/iva` en `backend/app/nucleo` = 0 endpoints | 🟢 |
| Núcleo: **sí** existen notas de crédito (el legacy no las modela) | `nucleo/api_facturacion.py:106` | 🟢 |

### 4.2 Casos numéricos

| CN | Escenario | Resultado esperado |
|---|---|---|
| CN-06 | débito 190.000; gastos 10.000/20.000/30.000 | crédito **9.579,83**; ítems suman 9.579,84; `a_pagar` **180.420,17** |
| CN-07 | afecta 500.000 + exenta 300.000 + anulada 76.000; gasto 119.000 | débito 95.000; `a_pagar` **76.000**; remanente 30.000 → **0** |

### 4.3 Lo que no está definido

| ID | Qué falta | A quién |
|---|---|---|
| `P-01` (abierta) | ¿La tasa vigente es 19 %? ¿Qué operaciones son exentas? ¿Cómo se prorratea y declara el F29? | Contador |
| `P-09` (nueva) | **(a)** ¿El `monto` del gasto es bruto (con IVA) o neto? El código asume **bruto** (`finanzas.py:152`). **(b)** ¿El crédito se calcula con la tasa del día del gasto o con la del período? **(c)** ¿El remanente de crédito se arrastra al mes siguiente? **(d)** ¿El resumen debe cuadrar con el F29? | Contador |
| `P-05` (abierta) | Impuesto específico al combustible e IVA recuperable de combustible | Contador |
| `P-06` (abierta) | DTE real, folios y notas de crédito | Contador |
| `D-21` (nueva) | ¿Quién es la autoridad de la tasa: la configuración de la empresa (legacy) o el request de facturación (núcleo)? ¿Se versiona por fecha de vigencia? | Dueño + contador |

**No asumible:** el 19 % **no** se puede tratar como constante legal. Es un seed
(`0001:291`) que nadie validó (`P-01`), y el núcleo acepta la tasa que envíe el
cliente (`schemas.py:1543`) sin contrastarla con la configuración. Tampoco se puede
afirmar que el crédito esté bien calculado: depende de una semántica de `monto` que el
código no documenta.

### 4.4 Recomendación: **retirar el cálculo de crédito; reimplementar el resumen**

- **Retirar** `credito = Σ monto × tasa/(100+tasa)` y `a_pagar` del legacy: es una
  estimación sobre un supuesto no verificado (`P-09`), no un dato tributario, y si el
  operador tipeó el neto el crédito queda **16 % subestimado** (CN-06).
- **Portar** el débito (`Σ factura.iva` de afectas no anuladas por emisión): es
  trazable a documentos y no depende de supuestos.
- **Reimplementar en el núcleo** un único resumen con: tasa versionada, base explícita
  (bruto/neto) en el gasto, redondeo por total declarado, arrastre de remanente si el
  contador lo confirma, y **débito neto de notas de crédito** (el núcleo ya las tiene,
  `nucleo/api_facturacion.py:106`; el legacy no las modela). Mientras eso no exista, el
  resumen legacy **no debe presentarse como declaración** (`kpis.md:78` ya lo advierte).
- **No** portar la tercera copia de `kpi_engine.py`: un solo servicio.

---

## 5. Módulo 3 — Mantenimiento

### 5.1 Qué hace hoy

| Regla | Implementación | Estado |
|---|---|---|
| Pauta por ítem con `intervalo_km > 0`, `orden`, baja lógica | `mantenimiento.py:28-87`; `0001:188-196`; seed `0001:296-302` | 🟢 |
| Registro de mantención exige tracto y pauta activa | `mantenimiento.py:116-121` | 🟢 |
| `km_actual` del tracto = `max(km registrado, km_actual)` | `mantenimiento.py:133-135` | 🟢 |
| Estado: último = registro de **mayor km** por (tracto, pauta); próximo = último + intervalo; restante = próximo − odómetro | `mantenimiento.py:170-207` | 🟢 |
| Umbrales: `restante ≤ 0` → `pendiente`; `≤ alerta_km` → `por_vencer`; si no `ok`; sin registro → `sin_registro` | `mantenimiento.py:202-207,186-198` | 🟢 |
| Alerta configurable, default 5000 km | `mantenimiento.py:163`; `0001:292` | 🟢 |
| Copia de la regla de estado en el KPI (solo cuenta `pendiente`) | `kpi_engine.py:465-491` | 🟢 (versión duplicada) |
| Costo de mantención solo alimenta el KPI mensual | `kpi_engine.py:392-398` | 🟢 |
| **No** bloquea el despacho | `routes/viajes.py` y `nucleo/politicas.py`: 0 referencias a pautas/mantenciones | 🟢 |
| Núcleo: solo reserva de recurso tipo `mantenimiento`; no hay pauta ni historial | `0004:68`; `servicio_alertas.py:172`; `nucleo/models.py:187` | 🟢 |

**Qué NO hace hoy:** no asocia la mantención a un viaje, no calcula costo/km, no
guarda respaldo por API (`respaldo_url` existe en `models/__init__.py:265` y nunca se
escribe), no valida `costo ≥ 0` (`:111`; `0001:205` sin `CHECK`) y no bloquea el
tracto.

### 5.2 Casos numéricos

| CN | Escenario | Resultado esperado |
|---|---|---|
| CN-08 | pauta 20.000; registro 10.000; odómetro 10.000 / 26.000 / 30.000 / 31.000 | `ok` / `por_vencer` / `pendiente` / `pendiente`; sin registro → `sin_registro` |
| CN-08 (borde) | editar el intervalo a 25.000 | el mismo registro pasa a `ok`: **el histórico se reinterpreta** |

### 5.3 Lo que no está definido

| ID | Qué falta | A quién |
|---|---|---|
| `P-11` (nueva) | ¿Los intervalos por ítem son los del **fabricante** del equipo o una política interna? El seed dice "el cliente confirmará los reales" (`0001:295`). Necesita fuente documental (manual/pauta del proveedor) | Dueño + proveedor/mecánico |
| `D-20` (nueva) | ¿El costo de mantención debe entrar al costo del viaje / costo por km (y con qué prorrateo), o queda solo como gasto de flota? Hoy solo alimenta un KPI | Dueño |
| — | ¿Una mantención vencida debe **bloquear** la asignación del tracto? Hoy no lo hace en ningún lado | Dueño (operación) |

**No asumible:** los intervalos sembrados (aceite 20.000, aire 40.000, engrase 5.000,
frenos 60.000/120.000) **no** son especificación técnica verificada; usarlos como
verdad podría omitir una mantención que el fabricante exige antes.

### 5.4 Recomendación: **portar con paridad**

Motivo: es el único control de mantención preventiva del sistema y el núcleo **no**
tiene pauta, historial ni estado por km. Retirarlo deja la flota sin control.

Paridad mínima: pauta (ítem, intervalo, orden, activo), registro (tracto, pauta,
fecha, km, costo, notas), y los cuatro estados con el mismo umbral.

Correcciones obligatorias al portar:

1. `costo ≥ 0` en servicio **y** en base.
2. Snapshot del intervalo en el registro (o versionar la pauta): hoy editar la pauta
   reescribe el pasado (CN-08 borde).
3. Empresa en todas las filas y bloqueo por `empresa_id` (FK compuesta).
4. Respaldo (boleta/factura) con la misma ruta acotada que gastos
   (`nucleo/storage.py:21`).
5. Una sola implementación del cálculo de estado (servicio), consumida por la UI y el
   KPI.

---

## 6. Módulo 4 — Configuración

### 6.1 Qué hace hoy

| Regla | Implementación | Estado |
|---|---|---|
| Cuatro claves permitidas: `iva_porcentaje`, `alerta_km_mantenimiento`, `dias_alerta_vencimientos`, `dias_alerta_cobranza` | `configuracion.py:30` | 🟢 |
| Solo `admin` escribe; cualquier autenticado lee | `configuracion.py:10-11` | 🟢 |
| Valor `str` libre, **sin validación de servidor**; la UI valida rango | `configuracion.py:26,33-39`; `frontend/src/app/(app)/configuracion/page.tsx:13-18,46-51` | 🟢 |
| Fallback silencioso al default si el decimal no parsea | `settings_db.py:14-25` | 🟢 |
| Claves enteras usan `int()` sin fallback → valor no numérico = **500** | `mantenimiento.py:163`; `kpi_engine.py:468` | 🟢 |
| Sin historial, sin auditoría, sin `empresa_id` (global) | `0001:212-215` | 🟢 |
| `dias_alerta_cobranza` **no está sembrada**: UI vacía, código usa 5 | `0001:290-293`; `finanzas.py:71` | 🟢 |
| Núcleo: no hay tabla equivalente; solo `configuracion_costos` por empresa y `empresa.dias_alerta_documentos` | `nucleo/models.py:1100-1119,222` | 🟢 |

### 6.2 Casos numéricos

No hay cálculo monetario propio (R-08 no lleva CN). El efecto se mide en R-06/R-07:
cambiar `iva_porcentaje` a 21 altera **facturas nuevas** y **todo el resumen de
cualquier período** (el crédito se recalcula con la tasa actual), pero **no** las
facturas ya emitidas. Cambiar `alerta_km_mantenimiento` a 8.000 reclasifica todos los
ítems entre `ok` y `por_vencer` sin tocar ningún registro.

### 6.3 Lo que no está definido

| ID | Qué falta | A quién |
|---|---|---|
| `D-21` (nueva) | Gobierno de la tasa IVA: una sola fuente, por empresa y con vigencia; hoy el legacy la lee de la tabla y el núcleo del request | Dueño + contador |
| — | ¿La configuración debe ser **por empresa** o global? El legacy es global y el núcleo asume empresa | Dueño/arquitectura |
| — | ¿Quién puede cambiar `dias_alerta_cobranza` y con qué efecto en la cobranza ya reportada? | Dueño |

### 6.4 Recomendación: **retirar con reemplazo** (no antes)

Motivo: la tabla global no tiene validación, historial ni multiempresa, y el núcleo ya
reemplazó dos de sus funciones (costos y alerta de documentos) con parámetros por
empresa. Mantenerla como fuente de la tasa IVA es justamente lo que produce las dos
tasas (§4.1).

Plan: mover las cuatro claves a configuración por empresa en el núcleo, con validación
en servidor, historial (`quién/cuándo/valor anterior`) y auditoría; retirar la tabla
legacy cuando no queden lectores. **No retirar antes**: hoy `/configuracion` es la
única forma de ajustar la alerta de mantenimiento y la tasa.

---

## 7. Módulo 5 — Export / Import CSV

### 7.1 Qué hace hoy

| Aspecto | Implementación | Estado |
|---|---|---|
| Export viajes / facturas / liquidaciones en CSV `;` + BOM + coma decimal | `export.py:30-47,50-169` | 🟢 |
| Export de liquidaciones **recalcula** la comisión en vez de leer el documento | `export.py:115,124-165` | 🟢 (CN-09) |
| Export autorizado a **cualquier** usuario autenticado (incluye sueldos/RUT) | `export.py:26` (vs `liquidaciones.py:33`) | 🟢 (hallazgo de seguridad) |
| Import clientes: exige razón social + RUT; omite RUT existente | `export.py:195-230` | 🟢 |
| Import choferes: `sueldo_base` y `porcentaje_produccion` con coma→punto; `>1 → /100` | `export.py:233-275` | 🟢 |
| Lectura acotada a 10 MB | `nucleo/storage.py:21` | 🟢 |
| `dias_pago=int(...)` sin manejo de error → 500 | `export.py:223` | 🟢 |
| Sin validación de RUT/DV, sin empresa, sin auditoría, sin dedupe intra-archivo | `export.py:195-275` | 🟢 |
| Núcleo: **no** hay export/import CSV | grep `csv` en `backend/app/nucleo` = 0 | 🟢 |

### 7.2 Casos numéricos

| CN | Escenario | Resultado esperado |
|---|---|---|
| CN-09 | factura de 200.000 después de emitir la liquidación | CSV **550.000** vs documento **530.000** (Δ 20.000) |

Riesgo numérico del import: `porcentaje = "1"` se interpreta como **100 %** (no se
divide, `:260-261`); `sueldo_base` negativo se acepta (`models/__init__.py:101` sin
`ge`). Ambos cambian la nómina sin aviso.

### 7.3 Lo que no está definido

| ID | Qué falta | A quién |
|---|---|---|
| — | ¿El import de catálogos sigue siendo necesario en el piloto, o alcanza con alta manual? | Dueño/operación |
| — | ¿Se exige dígito verificador de RUT y normalización (puntos/guiones) al importar? (calidad de dato, no ley) | Dueño |
| — | ¿Debe existir un export de nómina para contabilidad, y con qué rol? | Dueño + contador |

### 7.4 Recomendación: **retirar el import**, **portar el export**

- **Retirar el import CSV**: aporta poco (dos catálogos) frente a un riesgo alto
  (datos inválidos aceptados, 500 por una fila mala, sin auditoría ni empresa). Si el
  piloto lo necesita, reemplazarlo por un import **validado** (RUT+DV, fila a fila con
  reporte, transacción por fila, `empresa_id`, auditoría).
- **Portar el export** como **reporte de solo lectura** del núcleo, con permisos por
  rol (nómina solo `admin`/`contabilidad`), sin recalcular: exportar exactamente lo
  almacenado. Alternativa superior: no portar CSV y usar el reporte del núcleo cuando
  exista.
- **No** portar el export de liquidaciones que recalcula (CN-09) ni el acceso sin rol
  (`export.py:26`).

---

## 8. Invariantes que la FASE 2 debe preservar (propuestos a `datos`)

`datos` es el dueño de los IDs `INV-*`; acá se describen sin numerar.

| # | Invariante | Dónde se impone hoy | Qué falta |
|---|---|---|---|
| 1 | Una liquidación `emitida` no cambia | Solo servicio (`liquidaciones.py:326-330`) | Trigger/estado inmutable + versión |
| 2 | Un anticipo se descuenta exactamente una vez | **No se impone** (CN-05) | Regla de arrastre/rechazo (`D-19`) |
| 3 | `total_liquido ≥ 0` | **No** (`0001:179`) | `CHECK` o regla de deuda |
| 4 | El documento emitido es reproducible (PDF/CSV = almacenado) | **No** (`:466` vs `:515`; `export.py:124`) | Snapshot inmutable |
| 5 | `factura.total = neto + iva` | Solo servicio (`facturas.py:155`); sin `CHECK` (`0001:134`) | `CHECK` |
| 6 | El IVA de una factura emitida no cambia | De hecho (se almacena; solo cambia si se cambia `tipo`) | Bloqueo explícito tras emisión |
| 7 | Resumen de IVA = KPI de IVA | **No**: dos copias (`finanzas.py:135-153`; `kpi_engine.py:402-421`) | Un solo servicio |
| 8 | `costo` de mantención ≥ 0 | **No** (`0001:205`) | `CHECK` |
| 9 | Editar una pauta no reescribe el histórico | **No** (`:57-73`; CN-08) | Snapshot del intervalo |
| 10 | Nómina exportable solo por rol autorizado | **No** (`export.py:26`) | Permiso en el endpoint |

---

## 9. Preguntas: destinatario y qué bloques desbloquean

### 9.1 Al contador

1. **`P-01`** — ¿La tasa de IVA vigente es 19 %? ¿Qué operaciones son exentas? ¿Cómo se
   prorratea el crédito y se declara el F29?
2. **`P-09`** — ¿El monto de un gasto se registra **con IVA incluido** o neto? ¿Con qué
   tasa se calcula su crédito (la del día del gasto o la del período)? ¿El remanente de
   crédito se arrastra? ¿El resumen debe cuadrar con el F29?
3. **`P-04`** — ¿La comisión del chofer es remuneración? ¿Cómo se tributa y retiene?
4. **`P-05`** — Impuesto específico al combustible e IVA recuperable.
5. **`P-06`** — DTE real, folios y notas de crédito.

### 9.2 Al asesor laboral

1. **`P-02`** — AFP, salud, cesantía, impuesto único, gratificación, topes y descuentos
   legales: qué falta para que la "liquidación de remuneraciones" sea válida.
2. **`P-10`** — Anticipos: ¿descuento lícito? ¿límite? ¿se descuenta íntegro en el mes
   imputado? ¿qué pasa con un anticipo de un mes ya liquidado o mayor que los haberes?

### 9.3 Al dueño

1. **`D-01`** — Base de la comisión (flete neto / neto + recargos / total con IVA).
2. **`D-19`** — Anticipos de meses cerrados y anticipos mayores que los haberes.
3. **`D-20`** — ¿El costo de mantención entra al costo del viaje / costo por km?
4. **`D-21`** — Gobierno de la tasa IVA (fuente única, vigencia, quién la cambia).
5. ¿Una mantención vencida debe **bloquear** la asignación del tracto?

### 9.4 Al proveedor / mecánico

1. **`P-11`** — Intervalos de mantención por ítem y por tipo de equipo, con fuente
   documental (manual del fabricante o pauta del taller).

### 9.5 Lo que este documento **no** afirma

- No afirma que el 19 % sea la tasa legal vigente ni que el crédito esté bien
  calculado.
- No afirma que la composición del líquido (sueldo + comisión + bonos − descuentos −
  anticipos) sea suficiente para una liquidación legal.
- No afirma que los intervalos de mantención sembrados sean los del fabricante.
- No convierte una práctica observada en obligación.

---

## 10. Handoff

### 10.1 `arquitectura`

- ADR de nómina: decidir si el módulo de liquidaciones vive en el núcleo y con qué
  granularidad de snapshot (porcentaje, sueldo, base, documento).
- ADR de IVA: una sola fuente de tasa, con vigencia; definir si el resumen tributario
  pertenece al ERP o a un sistema contable externo.

### 10.2 `datos`

- Tablas de nómina con `empresa_id` y FK compuestas; `CHECK` de no negatividad donde
  corresponda.
- Inmutabilidad de liquidación emitida (trigger) y de factura emitida.
- Snapshot del intervalo de pauta en `mantenimiento` (o versionado de la pauta).
- Configuración por empresa con historial; retirar la tabla global cuando no haya
  lectores.
- `CHECK` de `costo ≥ 0` en mantenimiento y de `total = neto + iva` en facturas.

### 10.3 `backend`

- Portar `R-05` y `R-07` a servicios del núcleo con **un solo** redondeo explícito
  (HALF_UP) y **un solo** cálculo de comisión/estado.
- No portar el crédito IVA por factor (`finanzas.py:152`) hasta que `P-09` esté
  respondida; portar el débito almacenado.
- Endpoint de export con permisos por rol y sin recálculo; retirar `import` o
  reescribirlo validado.
- Errores de dato → 422 (no 500) en toda importación.
- Idempotencia en emisión de liquidación y en import.

### 10.4 `qa`

Casos listos para convertir en pruebas: `CN-03` (paridad), `CN-04` (redondeo HALF_EVEN
vs HALF_UP), `CN-05` (anticipo de mes emitido: hoy **falla la expectativa de negocio**),
`CN-06` (Δ $0,01 por línea vs total), `CN-07` (exenta/anulada/remanente), `CN-08`
(umbral `restante == 0` y mutación de pauta), `CN-09` (export/PDF vs documento emitido).
Además: export de nómina con rol `operacion` (debe dar 403 al portar; hoy **200**).

### 10.5 `auditor-seguridad`

- `GET /export/liquidaciones` expone sueldo, comisión y RUT a cualquier usuario
  autenticado (`export.py:26`): SEC-008 quedó corregido solo en
  `liquidaciones.py:33-34`.
- Import CSV sin validación de origen ni auditoría; riesgo de CSV/formula injection al
  reexportar.
