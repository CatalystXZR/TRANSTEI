# Catálogo de reglas de negocio — ERP Transportes TEI SpA

> **Pregunta que responde:** ¿cuál es la regla de negocio `R-0XX`, su fórmula y su estado de implementación?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-10-31 para **R-05…R-09** y **CN-03…CN-09** (FASE 2, retiro del legacy); R-01…R-04 conservan su verificación del 2026-10-29/30, no re-ejecutada · **Método:** lectura de código + DDL de migraciones + decisiones del dueño
> **Caduca si:** cambia una regla, su implementación o se cierra una `D-NN`.
> **Re-verificar con:** `grep -n "R-0" docs/negocio/catalogo-reglas.md | head`


Cada regla lleva un ID `R-0XX`, su fuente (quién la definió y cuándo), su estado de
implementación verificado en código, y los casos numéricos asociados.

Fuente de las reglas de este documento: **dueño del negocio, 2026-10-29**, más las
confirmaciones posteriores que cada regla indica (R-04: `D-16`, 2026-10-30). Las
reglas tributarias y laborales NO se definen aquí: se registran como pregunta al
contador o asesor laboral.

---

## R-01 — Comisión del conductor

**Enunciado (dueño, 2026-10-29):** la comisión del chofer es el **10 % de la
facturación total del mes**, y ese porcentaje lo puede cambiar el administrador.

**Interpretación registrada:** el porcentaje es configurable por chofer
(`porcentaje_comision` / `porcentaje_produccion`) y el valor por defecto debe ser
**10 %**. La base de cálculo es la facturación del mes, es decir, el flete **facturado**,
no el cobrado: el dueño descartó explícitamente distinguir devengado vs. cobrado.

**Estado en el código (verificado 2026-10-29, tras la decisión de atribución):**

| Aspecto | Implementación real | ¿Cumple? |
|---|---|---|
| Porcentaje configurable por chofer | `public.choferes.porcentaje_produccion` (`backend/app/models/__init__.py:102-105`); `nucleo.choferes.porcentaje_comision` (`backend/app/nucleo/models.py:583-586`) | 🟢 |
| Valor por defecto 10 % | `models/__init__.py:103-105`, `schemas/catalogos.py:34-36`, `nucleo/models.py:584-586`; `0017` fija el default en la base; `0019` alinea las filas del piloto | 🟢 |
| Base = flete **facturado** | `liquidaciones.py:51-96`: exige factura no anulada, o estado `facturado` como fallback declarado; suma `valor_flete_neto` (`:92-95`) | 🟢 |
| Mes = mes de **emisión de la factura** | Decisión del dueño del 2026-10-29, opción (a) de SEC-001: usa `facturas.fecha_emision` vía `factura_viaje` (`liquidaciones.py:66-83`) | 🟢 |
| Factura anulada no devenga | `cambiar_estado_factura` desvincula el viaje y lo devuelve a `finalizado` (`facturas.py:218-228`); la consulta excluye `EstadoFactura.anulada` (`liquidaciones.py:70`) | 🟢 |

**Brechas abiertas (no de esta regla, pero afectan el dinero):**

- **SEC-002:** el PDF de una liquidación emitida recalcula haberes pero imprime el
  total almacenado → el documento firmado no es reproducible.
- **SEC-003:** `nucleo.choferes.porcentaje_comision` (costo/margen) y
  `public.choferes.porcentaje_produccion` (nómina) son dos fuentes del mismo
  porcentaje; pueden discrepar. Requiere ADR.
- Un viaje marcado `facturado` **sin** factura asociada se atribuye por la fecha del
  viaje (fallback declarado) para no perder la comisión; es un dato inconsistente que
  conviene detectar, no una regla de negocio.
- **Base de cálculo no cerrada (`D-01`):** el enunciado dice "facturación total", pero
  la nómina suma solo `valor_flete_neto` (`liquidaciones.py:92-95`): **no** incluye
  `monto_recargos` ni IVA. El costo del núcleo usa `monto_total_neto` (con recargos) y
  el KPI usa el neto; son tres bases distintas (`implementacion.md` §2.1). Falta que
  el dueño defina la base.

**Caso numérico CN-01:** dos viajes facturados en el mes por $1.000.000 y $800.000,
chofer con 10 % → comisión = 0,10 × 1.800.000 = **$180.000**. Anticipo $100.000 y bono
$50.000 → líquido = 400.000 (base) + 180.000 + 50.000 − 100.000 = **$530.000**.

---

## R-02 — Licencia de conducir del chofer

**Enunciado (dueño, 2026-10-29):** la única clase de licencia válida es **A5**. Si
maneja camiones, tiene A5; no hay excepciones. Se debe llevar el control de la
documentación para que esté al día:

- **Vencida → bloqueo** de la asignación.
- **Por vencer (entre 14 días y 1 día) → advertencia.**
- Clase distinta de A5 → **bloqueo**.

**Estado en el código (verificado 2026-10-29):**

| Aspecto | Implementación real | ¿Cumple? |
|---|---|---|
| Documento de licencia vencido bloquea | `nucleo.validar_documentos_recurso` invocado por `fn_viaje_validar` (`supabase/migrations/0004_nucleo_operacional.sql:1281-1292`); la vigencia se exige hasta el fin del viaje + margen (`0004:1276-1279`) y el vencimiento lanza `23514` (`0004:1097-1101`) | 🟢 |
| Ventana de advertencia | Default **14** en Python (`backend/app/nucleo/models.py:222`) y en la base (`0016:182-183`). `0004:120-121` conserva el default 30 original, que 0016 reemplaza **si está aplicada** | 🟢 |
| Clase de licencia distinta de A5 bloquea | Trigger `trg_viajes_03_licencia_a5` / `fn_viaje_licencia_a5` (`0016:193-257`): clase distinta o ausente → `23514`. El servicio la marca bloqueante antes de escribir (`politicas.py:297-322`). El comentario `0004:1272-1274` es anterior y quedó obsoleto | 🟢 (con 0016 aplicada; ver nota) |

**Alcance de la verificación:** la regla es una **decisión del dueño**, no una
obligación legal verificada (`0016:34-38`). `0016` está en disco, pero **no en `HEAD`**:
`docs/estado.md:31` registra solo 3 migraciones en `HEAD`, y `backend/tests/test_reglas_negocio.py:33-35`
registra que se aplicó en PostgreSQL local. En un clon limpio, sin aplicar 0016, el
bloqueo de clase queda solo en el servicio (la asignación normal pasa por
`validar_asignacion`, `servicio_disponibilidad.py:1463-1474`), no en la base. El
encabezado de 0016 (líneas 151-155) dice que `models.py:221` tiene default 30; el código
actual declara 14 en la línea 222: es un comentario desactualizado, no la regla. El
default 14 aplica a **altas nuevas**; las empresas existentes conservan el valor que
tengan, porque 0016 no hace backfill (`0016:135-149`).

Si el seguro exige una clase específica por tipo de equipo, debe confirmarse con el
corredor de seguros (`P-03`); hoy se registra como política interna del negocio.

---

## R-03 — Mes de imputación del viaje (pendiente)

**Situación verificada:** al finalizar un viaje, el flujo de cambio de estado estampa
`fecha_fin = date.today()` (`backend/app/api/routes/viajes.py:245-246`). **No es cierto
que no exista ninguna vía para declararla:** el `PUT /viajes/{id}` acepta `fecha_fin`
(`backend/app/schemas/viajes.py:24-26`; `backend/app/api/routes/viajes.py:194,206-213`),
pero la pantalla solo la muestra (`frontend/src/app/(app)/viajes/[id]/page.tsx:257`). En
el núcleo, `cerrar_viaje` estampa `fin_real = fin_real or ahora_utc()`
(`backend/app/nucleo/servicio_expediente.py:1268-1270`) y `CerrarViaje` no acepta fecha
(`backend/app/nucleo/schemas.py:1162-1165`).

**Consecuencia:** la **comisión legacy ya no depende de `fecha_fin`** (R-01 la atribuye
por emisión de factura, `liquidaciones.py:66-83`); sí dependen el **margen/KPI**
(`kpi_engine.py:312-320,352-360`) y el **resumen del mes** (`dashboard.py:57-63`), que
se imputan al día en que alguien apretó el botón.

**Pregunta al dueño (`D-03`):** ¿se debe permitir registrar la fecha real de término del
viaje (por ejemplo, cuando se cierra al día siguiente o a fin de mes)? ¿Quién puede
corregirla y hasta cuándo?

---

## R-04 — ID comercial de flete por cliente

**Enunciado (dueño, 2026-10-29; confirmado 2026-10-30 en `D-16`):** todo flete
lleva un **ID comercial por cliente** con formato `<PREFIJO>-NNNNN` —prefijo
derivado del cliente y **5 dígitos** con relleno de ceros (`SQM-00001`,
`SQM-00002`, …)—, estable, asignado en **orden creciente**, **sin reutilización**,
que identifica el flete en las comunicaciones (hoja de ruta, desgloses) en lugar
del UUID/folio técnico. Identifica, **no autoriza**: todo acceso pasa por la ACL
del contacto (`0021:566-570`).

**Fórmula:** `siguiente = máximo(dígitos ya asignados para (empresa_id, cliente_id)) + 1`;
`código = UPPER(prefijo) || '-' || LPAD(siguiente, 5, '0')`.
Unidades: entero ≥ 1. Base: los dígitos son la parte numérica del código, no el
folio técnico. Redondeo: **no aplica** (enteros; el relleno con ceros no es
redondeo). Signo: no aplica. Momento: al **asignar** el ID al viaje (alta o
backfill), dentro de la misma transacción; el contador se incrementa **antes** de
devolver el código. Moneda: no aplica. Prefijo: 2–8 caracteres alfanuméricos
(`0021:614-617`), entregado por el llamador — la base **no** lo deriva del cliente.

**Implementación real (verificada 2026-10-30 en las migraciones en disco; aplicadas solo en `tei_test`):**

| Aspecto | Implementación real | ¿Cumple? |
|---|---|---|
| Columna y formato `PREFIJO-00001` | `nucleo.viajes.id_comercial_flete` + `CHECK` `^[A-Z0-9]{2,8}-[0-9]{5}$` (`0021:548-553`) | 🟢 en `tei_test` |
| Unicidad por (empresa, cliente, código) | índice único parcial `uq_viajes_id_comercial` (`0021:555-557`) | 🟢 |
| Contador atómico por (empresa, cliente) | tabla `nucleo.id_comercial_contador` (`0021:572-589`); `obtener_siguiente_id_comercial_flete` con `INSERT … ON CONFLICT DO UPDATE` (`0021:603-636`, upsert `:628-634`) | 🟢 |
| Creciente sin reutilización | el contador no retrocede: trigger `trg_contador_10_no_retrocede` (`0022:284-307`); `registrar_id_comercial_flete` lo alinea con `greatest` (`0021:640-670`, `:668`) | 🟢 |
| ID inmutable tras asignar (incluido el paso a `NULL`) | trigger `trg_viajes_10_id_comercial_inmutable` (`0022:315-341`); asignar desde `NULL` sigue permitido (backfill) | 🟢 |
| Tope 99.999 **fail-closed** | guarda `v_numero > 99999` → `23514`; la transacción revierte el incremento (`0022:401-444`, `:434-440`) | 🟢 |
| "Todo flete lleva ID" | **no impuesto**: columna **nullable**, sin trigger que exija el ID al crear, cerrar o facturar (`0021:548-549`) | 🔴 |
| Prefijo derivado del cliente | **no existe**: lo entrega el llamador (`0021:606,614-617`); sin tabla ni constraint de prefijo por cliente | 🔴 (`D-18`) |
| Consumo desde `backend/**` | **ninguno** según el encabezado de `0022:110-113` (grep 2026-10-30): sin escritores ni lectores de la columna | 🔴 |

**Estado de aplicación:** 🟡 `0021` y `0022` están **solo en `tei_test`**
(`docs/datos/catalogo-migraciones.md:59-60`; `docs/datos/agente-esquema.md:14-15`);
no se verificaron en la base de la app ni en otro entorno. Este catálogo **no es
prueba de implementación**: la prueba es el DDL y la base.

**Evidencia ejecutada (en `tei_test`, re-ejecutada por el orquestador):** `0021_02`
— 8 conexiones con barrera obtuvieron `SQM-00001..00008` sin duplicados ni saltos
(`docs/orquestacion/registro.md:932`); sondas D3/D2 con el rol real `tei_app`
(`:951-953`); `0021_04` — mutación M1–M9 y ROLLBACK (`:938-939,971-974`);
rollback/re-aplicación completa de `0021`+`0022` (`:966-974`). No se ejecutaron
pruebas en esta sesión: se citan las del registro.

**Clasificación:** **parcial** — numeración, unicidad, monotonía, inmutabilidad y
tope están impuestas en PostgreSQL y probadas en `tei_test`; faltan (a) aplicar las
migraciones fuera del clon, (b) imponer que todo flete tenga ID, (c) resolver
`D-18` (prefijo/resolución) y (d) el consumo desde `backend`.

**Invariantes asociados** (referencia `AW-14` de `docs/datos/agente-esquema.md:190`;
los IDs `INV-*` los administra `datos`):

- Unicidad del código dentro de `(empresa_id, cliente_id)` — `0021:555-557`.
- Secuencia creciente sin reutilización — contador monótono no decreciente (`0022:284-307`).
- ID inmutable una vez asignado — `0022:315-341`.
- Tope 99.999 fail-closed — `0022:434-440`.
- **No es invariante hoy:** unicidad del código dentro de `(empresa_id)` — `D-18`.

**Riesgos:**

- **Prefijo colisionante (`D-18`):** dos clientes pueden usar `SQM` y ambos emitir
  `SQM-00001`; la búsqueda por `(empresa, código)` puede devolver N fletes
  (`0021:559-564`; verificado en `docs/datos/agente-esquema.md:542,637`). Mientras
  `D-18` no se responda, la resolución debe llevar **`cliente_id`**.
- **Tope de 99.999 por cliente:** al agotarse, la emisión falla (`23514`) en vez de
  continuar con 6 dígitos; el rango es finito y no hay regla para ampliarlo.
- **Contador adelantable:** `tei_app` conserva `UPDATE` sobre el contador; puede
  subirlo (no bajarlo) y agotar el rango — falla cerrada, no reutiliza
  (`docs/datos/agente-esquema.md:675-677`).
- **Sin enforcement de "todo flete lleva ID"** y sin escritor en `backend/**`:
  hoy la regla se cumple solo si el llamador invoca las funciones.
- **Solo `tei_test`:** aplicar las migraciones en la base de la app es riesgo Alto y
  exige autorización y ventana; ambas están untracked.

**Caso numérico CN-02 — secuencia por (empresa, cliente) y tope fail-closed**

Datos: empresa A; cliente Soquimich con `SQM-00001`, `SQM-00002` y `SQM-00003` ya
asignados → contador `(A, Soquimich) = 3`.
Cálculo paso a paso: siguiente = 3 + 1 = 4 → `LPAD('4', 5, '0')` = `00004` →
**`SQM-00004`**. Otro flete de Soquimich el mismo día: 4 + 1 = 5 → **`SQM-00005`**
(la secuencia es por cliente, no por fecha). Cliente Cervera en A: contador
`(A, Cervera) = 0` → 0 + 1 = 1 → **`CER-00001`**. Otra empresa B con un cliente
homónimo usa su propio contador y arranca en `00001`: la secuencia es por
(empresa, cliente).
Borde fail-closed: contador `(A, Soquimich) = 99.998` → 99.999 → **`SQM-99999`**;
con el contador en 99.999, siguiente = 100.000 → **`23514`**, no se emite código y
el incremento se revierte (el contador sigue en 99.999; no se quema el número).
Borde de redondeo: no existe; son enteros y `LPAD` solo rellena ceros (`SQM-00004`,
nunca `SQM-4`).
Fuente de la regla: R-04. Pregunta abierta asociada: `D-18`.

---

## R-05 — Liquidación del chofer (legacy): composición del líquido

**Enunciado (observado en código, no decisión registrada):** el líquido de una
liquidación mensual es `sueldo_base + comisión (R-01) + bonos − descuentos −
anticipos del mes`, y una liquidación `emitida` no se recalcula por API.

**Fuente:** implementación legacy `backend/app/api/routes/liquidaciones.py:229-342`.
La **comisión** sí es decisión del dueño (R-01, 2026-10-29); la **composición del
líquido** y el tratamiento de anticipos/ajustes **no tienen fuente escrita** →
regla observada. Su validez laboral es `P-02`; el descuento de anticipos es `P-10`.

**Fórmula:**

```text
comisión      = ( Σ valor_flete_neto × porcentaje_produccion ).quantize(0.01)
total_ajustes = Σ bonos − Σ descuentos
total_liquido = sueldo_base + comisión + total_ajustes − Σ anticipos
```

- **Unidades/moneda:** CLP con 2 decimales (`numeric(14,2)`, `0001:155,167,175-179`);
  el legacy **no tiene campo moneda**: CLP implícito.
- **Base de la comisión:** viajes del chofer con factura **no anulada**; mes =
  [inicio, fin) de `facturas.fecha_emision` (`liquidaciones.py:66-84`). Suma **solo**
  `valor_flete_neto` (`:92-95`): sin recargos y sin IVA.
- **Signo:** bonos suman; descuentos y anticipos restan. `total_ajustes` puede ser
  negativo (no hay `CHECK`).
- **Redondeo:** la comisión usa `quantize(Decimal("0.01"))` **sin `rounding`
  explícito** (`:95`) → `ROUND_HALF_EVEN` del contexto `decimal` (no se cambia el
  contexto en `backend/app`). Las facturas usan `ROUND_HALF_UP` (`facturas.py:42-44`):
  **dos modos de redondeo para dinero en el mismo sistema** (CN-04).
- **Momento:** al `POST /liquidaciones/calcular`; el `sueldo_base` se **copia** del
  maestro en ese instante (`:332`). Si el maestro cambia después, el borrador guardado
  no cambia hasta el próximo cálculo.
- **Entradas mutables después del cálculo:** sí — `resumen_liquidaciones` (`:229-275`)
  y el PDF (`:502-541`) **recalculan en vivo**; una `emitida` bloquea el recálculo por
  API (`:326-330`) pero **no** por SQL ni por el resumen.

**Estados que la habilitan:** `liquidaciones.estado ∈ {borrador, emitida}`;
`emitida` → `POST /liquidaciones/calcular` responde 409.

**Implementación real:** `liquidaciones.py:51-96` (comisión), `:229-275` (resumen),
`:278-342` (cálculo), `:345-358` (emitir: **sin** usuario, fecha ni verificación de
estado previo), `:502-541` (PDF); tablas `0001:151-186`.

**Clasificación:** **implementada (legacy)** · **parcial** como regla de nómina: no
modela descuentos previsionales (`P-02`), no tiene auditoría, no hay inmutabilidad en
base y el documento emitido no es reproducible.

**Evidencia:** `backend/tests/test_flujos_criticos.py:168-229` declara comisión
180.000 y líquido 530.000; `test_reglas_negocio.py:507-543` declara 580.000.
**No ejecutadas en esta sesión** (sin shell ni base): cobertura *declarada*, no
resultado verde.

**Invariantes propuestos a `datos` (sin ID asignado):**

- Una liquidación `emitida` no cambia (hoy solo lo impide el servicio, `:326-330`).
- `total_liquido ≥ 0` (hoy `numeric` sin `CHECK`, `0001:179`).
- Un anticipo se descuenta **exactamente una vez** (hoy puede descontarse cero, CN-05).
- Borrar un anticipo/ajuste no borra evidencia (`DELETE` duro en `:146-156,206-216`,
  sin auditoría; permitido incluso con liquidación emitida).

**Riesgos:** pérdida de anticipos (CN-05), documento no reproducible (CN-09),
comisión con redondeo distinto al de la factura (CN-04), nómina legal incompleta
(`P-02`), sueldos/RUT expuestos por `/export/liquidaciones` (ver R-09).

**Casos numéricos:** CN-03, CN-04, CN-05.

---

## R-06 — IVA (legacy): tasa, base y resumen mensual

**Enunciado (observado en código):** la factura **afecta** agrega la tasa de
`configuracion.iva_porcentaje` sobre el neto de los viajes facturados; el resumen
mensual resta al débito el crédito **estimado** de los gastos marcados
`iva_recuperable`.

**Fuente:** implementación legacy `facturas.py:35-44,141-155`,
`finanzas.py:116-185` y una tercera copia en `services/kpi_engine.py:400-421`. El
valor **19** es un **seed de configuración** (`0001:290-293`), **no** una decisión
registrada ni una norma verificada → `P-01`. **No es una tasa hardcodeada**: se lee
de la tabla con default `"19"` (`finanzas.py:133`; `facturas.py:35-36`;
`kpi_engine.py:401`).

**Fórmula (una factura):**

```text
neto  = Σ valor_flete_neto   (solo viajes del mismo cliente, finalizados y no facturados antes)
iva   = 0                                        si tipo = exenta
      = (neto × tasa / 100).quantize(0.01, ROUND_HALF_UP)   si tipo = afecta
total = neto + iva
vencimiento = fecha_emision + cliente.dias_pago (default 30)
```

- **Unidades/moneda:** CLP, 2 decimales; `tasa` en puntos porcentuales (19 = 19 %).
- **Base:** neto **sin recargos** (el legacy no tiene recargos) y **sin IVA**.
- **Redondeo:** `ROUND_HALF_UP` explícito por factura (`facturas.py:42-44`), sobre el
  **total de la factura**, no por viaje.
- **Momento:** al emitir la factura; el IVA queda **almacenado**. Cambiar
  `iva_porcentaje` después **no** reajusta facturas históricas (solo se recalcula si
  se cambia `tipo`, `facturas.py:192-194`) → cumple el espíritu de snapshot de tarifa.

**Fórmula (resumen mensual, `GET /iva/resumen`):**

```text
débito  = Σ facturas.iva    (tipo = afecta, estado ≠ anulada, emisión ∈ [inicio, fin))
factor  = tasa / (100 + tasa)
crédito = Σ gastos.monto × factor    (iva_recuperable = true, fecha ∈ [inicio, fin))
a_pagar = max(débito − crédito, 0)
```

- **Supuesto no declarado:** `gastos_viaje.monto` se trata como **monto con IVA
  incluido** (`finanzas.py:151-153`); `gastos.py:60` no lo dice y la tabla no tiene
  columnas neto/IVA (`0001:114-125`). Si el operador tipeó el neto, el crédito queda
  16 % subestimado → `P-09`.
- **Redondeo:** el crédito se cuantiza **por línea** al mostrarse (`:171`) y **por
  total** al declararse (`:181`) → los ítems pueden sumar $0,01 más que el total
  (CN-06).
- **Remanente:** `max(…, 0)` descarta el crédito sobrante; **no se arrastra** al mes
  siguiente (`:182`) → `P-09`.
- **No incluye:** notas de crédito, F29, DTE, prorrateo de crédito, impuesto
  específico al combustible (`P-05`, `P-06`).

**Implementación real:** `facturas.py:35-44,141-155`; `finanzas.py:116-185`;
copia en `kpi_engine.py:400-421`. **Núcleo:** `tasa_iva` **por request** con default
`0.19` (`nucleo/schemas.py:1543`) → `iva = neto × tasa` (`servicio_facturacion.py:544`);
no existe resumen de IVA en el núcleo (grep `/iva` en `backend/app/nucleo` = 0).

**Clasificación:** **implementada (legacy)** · **no válida como declaración
tributaria** (`P-01`, `P-06`).

**Invariantes propuestos a `datos` (sin ID):** el IVA de una factura emitida no
cambia; `total = neto + iva` siempre; el resumen y el KPI dan la misma cifra.

**Riesgos:** dos fuentes de tasa (config vs request), tres copias del cálculo,
crédito sobre un supuesto no verificado, remanente perdido, cambio de tasa que altera
períodos pasados solo en el resumen (no en la factura).

**Casos numéricos:** CN-06, CN-07.

---

## R-07 — Mantenimiento por kilometraje (pauta + estado)

**Enunciado (observado en código):** cada tracto se controla contra una **pauta por
ítem** con `intervalo_km`; el estado del ítem se deriva del último registro (mayor km)
más el intervalo, comparado con `tractos.km_actual`.

**Fuente:** implementación legacy `backend/app/api/routes/mantenimiento.py:28-228`,
duplicada en `services/kpi_engine.py:465-491`; tablas y seeds `0001:188-209,296-302`.
Los intervalos sembrados (aceite 20.000; aire 40.000; engrase 5.000; frenos
60.000/120.000) son **valores por defecto declarados como "el cliente confirmará los
reales"** (`0001:295`): **no** son especificación del fabricante → `P-11`.

**Fórmula:**

```text
próximo_km  = último_km + intervalo_km          (último = registro con mayor km del par tracto×pauta)
restante_km = próximo_km − tracto.km_actual
estado      = "sin_registro"            si no hay registro
            = "pendiente"               si restante_km ≤ 0
            = "por_vencer"              si 0 < restante_km ≤ alerta_km_mantenimiento
            = "ok"                      en otro caso
```

- **Unidades:** km enteros; **sin redondeo**; **sin moneda** (el estado no es dinero).
- **`km_actual`:** se actualiza a `max(km registrado, km_actual)` al crear la
  mantención (`:133-135`); nunca decrece por API.
- **Parámetros:** `alerta_km_mantenimiento` default **5000** (`:163`; `0001:292`).
- **Costo:** `costo` es CLP informativo; **no entra al costo del viaje ni al
  costo/km** (solo al KPI `costo_mantenimiento_mes`, `kpi_engine.py:392-398`) → `D-20`.

**Estados que la habilitan:** solo exige tracto existente y pauta `activo`
(`:116-121`). **No bloquea el despacho**: ni `routes/viajes.py` ni
`nucleo/politicas.py` consultan pautas o mantenciones (grep = 0); el núcleo solo
bloquea si alguien crea una `reserva_recurso` con tipo `mantenimiento` (`0004:68`;
`servicio_alertas.py:172`), y **nada la crea desde una mantención**.

**Implementación real:** `mantenimiento.py:28-87` (pautas), `:93-152` (registro),
`:158-228` (estado); segunda copia `kpi_engine.py:465-491`.

**Clasificación:** **implementada (legacy)** · **parcial**: sin bloqueo operativo,
sin respaldo por API (`respaldo_url` existe en el modelo `models/__init__.py:265` y
**nunca se escribe**), `costo` sin cota inferior (`:111`; `0001:205` sin `CHECK`).

**Invariantes propuestos a `datos` (sin ID):** `costo ≥ 0`; el intervalo aplicado a
un registro histórico no cambia si se edita la pauta (hoy **sí** cambia:
`PUT /pautas/{id}` reescribe `intervalo_km`, `:57-73`, y todos los "próximos" se
recalculan); una mantención no se borra sin rastro (`:142-152`).

**Riesgos:** costo negativo, mantención sin comprobante, regla duplicada (servicio y
KPI pueden discrepar si una cambia), odómetro manual, tracto con mantención vencida
despachable.

**Caso numérico:** CN-08.

---

## R-08 — Configuración operativa global (legacy)

**Enunciado (observado en código):** existen cuatro claves globales
(`iva_porcentaje`, `alerta_km_mantenimiento`, `dias_alerta_vencimientos`,
`dias_alerta_cobranza`); solo `admin` las escribe y el servidor **no valida** el valor.

**Fuente:** `backend/app/api/routes/configuracion.py:14-40`; semilla `0001:290-293`.

**Fórmula:** no aplica (parámetros). Efectos: R-06 (tasa), R-07 (alerta km),
`kpi_engine.py:427` (vencimientos) y `finanzas.py:71` (cobranza).

- **Validación:** solo lista blanca de claves (`:30`); el valor es un `str` libre
  (`:26,35-37`). La UI restringe numéricamente (`frontend/src/app/(app)/configuracion/page.tsx:46-51`),
  la API **no**.
- **Fallback:** si la clave no es numérica, `get_config_decimal` cae en silencio al
  default (`settings_db.py:14-25`), pero las claves enteras usan `int(...)` directo
  (`mantenimiento.py:163`; `kpi_engine.py:468`) → un valor no numérico produce **500**.
- **Sin historial:** no hay quién/cuándo/valor anterior ni auditoría; la tabla **no
  tiene `empresa_id`** (`0001:212-215`): es global para todas las empresas.
- **Clave sin semilla:** `dias_alerta_cobranza` no está en `0001:290-293`; el código
  usa default **5** (`finanzas.py:71`) pero la pantalla la muestra **vacía** hasta que
  alguien la guarde.

**Implementación real:** `configuracion.py:14-40`. **Núcleo:** no hay tabla
equivalente; `nucleo.configuracion_costos` (por empresa, `models.py:1100-1119`) cubre
solo costos y `empresa.dias_alerta_documentos` (`models.py:222`) cubre vencimientos.

**Clasificación:** **implementada (legacy)** · **parcial** (sin validación de
servidor, sin historial, sin multiempresa, una clave sin seed).

**Riesgos:** una tasa inválida cae al 19 % sin avisar; un entero inválido rompe
`/mantenimiento/estado` y el KPI; no se puede saber qué valor regía al emitir un
documento (la factura guarda su IVA, el resumen no).

**Pregunta asociada:** `D-21`.

---

## R-09 — Export/import CSV (legacy)

**Enunciado (observado en código):** se exportan viajes, facturas y liquidaciones a
CSV (`;`, BOM UTF-8, coma decimal) y se importan clientes y choferes desde CSV.

**Fuente:** `backend/app/api/routes/export.py:30-275`.

**Fórmula:** no aplica, salvo que **el export de liquidaciones recalcula** con la
misma función de R-05 (`:115,124-165`) en vez de leer el documento emitido → un CSV
puede diferir de la liquidación firmada (CN-09). El `total_liquido` del CSV se calcula
de nuevo en `:165`, sin pasar por `liquidaciones.total_liquido`.

**Validaciones reales (import):**

| Regla | Implementación | Brecha |
|---|---|---|
| Filas con `razon_social`+`rut` / `nombre`+`rut` | `:212-214`, `:250-252` | — |
| RUT ya existente → se omite | `:215-218`, `:253-256` | duplicado **dentro del archivo** → `23505` en el `commit` → 500 |
| `dias_pago` entero | `:223` `int(...)` | no numérico → **500** (no 422) |
| `sueldo_base`/`porcentaje_produccion` decimal, coma→punto | `:258-261` | `sueldo_base` **negativo aceptado** (sin `ge`, `models/__init__.py:101`) |
| `porcentaje > 1 → /100` | `:260-261` | heurística: `1` se interpreta como **100 %**; `0,10` y `10` → 0,10 |
| Tamaño del archivo | `leer_archivo_acotado`, `nucleo/storage.py:21` (10 MB) | — |
| RUT con dígito verificador | **no existe** | `P` de calidad de dato (no legal) |
| Empresa / auditoría | **no existe** (legacy single-tenant) | al portar: `empresa_id` obligatorio |

**Autorización:** el export usa `get_current_user` (`:26`), no el rol restringido de
`liquidaciones.py:33`; por tanto **cualquier usuario autenticado** (incluido
`operacion`) puede descargar sueldos, comisión y RUT desde `/export/liquidaciones` →
hallazgo para `auditor-seguridad` (SEC-008 quedó corregido solo en el módulo, no acá).

**Clasificación:** **implementada (legacy)** · **parcial** (sin validación de
entrada, sin empresa, sin auditoría, con fuga de nómina).

**Riesgos:** nómina exportable por rol indebido; CSV no reproducible contra el
documento emitido; inyección de fórmulas de Excel (los campos de texto se escriben
crudos, `:30-47`, y `nombre`/`razon_social` vienen de un CSV subido); import que deja
la sesión a medias (un `commit` para todo el archivo, `:229,274`).

**Caso numérico:** CN-09.

---

## Casos numéricos CN-03 … CN-09 (FASE 2 — módulos legacy)

Todos en **CLP**, con aritmética decimal exacta. Se calcularon a mano; **ninguno se
ejecutó** contra el sistema en esta sesión (sin base ni shell).

### CN-03 liquidación normal — R-05
Datos: sueldo base **400.000**; dos viajes del chofer facturados en 2026-10 por
**1.000.000** y **800.000** (factura emitida 2026-10-15); anticipo **100.000** con
`mes_liquidacion=2026-10`; bono **50.000**; sin descuentos; porcentaje **0,10**.
Cálculo paso a paso: base = 1.000.000 + 800.000 = 1.800.000 → comisión =
1.800.000 × 0,10 = 180.000,00 → `quantize(0.01)` = 180.000,00; `total_ajustes` =
50.000 − 0 = 50.000; líquido = 400.000 + 180.000 + 50.000 − 100.000 = **530.000,00**.
Resultado esperado: `comision = 180000.00`, `total_liquido = 530000.00`.
Borde que ejercita: caso normal de paridad con `test_flujos_criticos.py:228-229`.
Fuente de la regla: R-05 (comisión: R-01).

### CN-04 redondeo de la comisión — R-05
Datos: porcentaje **0,1250** (12,5 %, 4 decimales permitidos por
`models/__init__.py:103-105`); viajes facturados del mes que suman **1.000.009,00**
(500.000,50 + 500.008,50).
Cálculo paso a paso: 1.000.009 × 0,125 = **125.001,125** exacto. `quantize(0.01)`
**sin** `rounding` → `ROUND_HALF_EVEN`: el tercer decimal es 5 y el segundo es 2
(par) → **125.001,12**. Con `ROUND_HALF_UP` (el que usa la factura,
`facturas.py:42-44`) daría 125.001,13.
Resultado esperado: `comision = 125001.12`; diferencia de **$0,01** contra el criterio
de las facturas.
Borde que ejercita: mitad exacta + dos modos de redondeo en el mismo sistema
(por línea, sin cuantizar el total de haberes).
Fuente de la regla: R-05.

### CN-05 anticipo imputado a un mes ya emitido — R-05
Datos: liquidación **2026-09 emitida** por 530.000 (CN-03). El **2026-10-05** se
registra un anticipo de **150.000** con `mes_liquidacion="2026-09"` (se acepta: solo
se valida el formato `YYYY-MM`, `liquidaciones.py:39-41,132`).
Cálculo paso a paso: (1) `POST /liquidaciones/calcular?mes=2026-09` → **409**
(`:326-330`), no se descuenta; (2) `?mes=2026-10` suma solo anticipos con
`mes_liquidacion="2026-10"` (`:233-238`) = 0, tampoco se descuenta; (3)
`GET /liquidaciones/resumen?mes=2026-09` recalcula y muestra anticipos 150.000 y total
**380.000**, mientras el documento emitido dice **530.000**.
Resultado esperado: el anticipo **no se recupera nunca** y el resumen contradice al
documento; diferencia visible **150.000**. Pregunta abierta: `D-19`.
Borde que ejercita: mes cruzado + estado `emitida` + borrado lógico inexistente.
Fuente de la regla: R-05.

### CN-06 IVA — crédito por línea vs por total, con base bruta — R-06
Datos: tasa **19**; tres gastos del mes con `iva_recuperable=true` por **10.000**,
**20.000** y **30.000**; una factura afecta del mes con neto **1.000.000** e IVA
almacenado **190.000**.
Cálculo paso a paso: factor = 19/119 = 0,1596638655…
- 10.000 × 19/119 = 190.000/119 = 1.596,638655… → **1.596,64**
- 20.000 × 19/119 = 380.000/119 = 3.193,277310… → **3.193,28**
- 30.000 × 19/119 = 570.000/119 = 4.789,915966… → **4.789,92**
- suma de las líneas mostradas = **9.579,84**
- crédito del resumen = (60.000 × 19/119) = 1.140.000/119 = 9.579,831932… → **9.579,83**
- `a_pagar` = 190.000,00 − 9.579,83 = **180.420,17**
Resultado esperado: `credito = 9579.83`, `a_pagar = 180420.17`; los ítems del detalle
suman 9.579,84 (**Δ $0,01** por redondear por línea y no por total).
Contraste del supuesto: si `monto` fuera **neto** en vez de bruto, el crédito sería
60.000 × 0,19 = **11.400,00** (Δ 1.820,17): por eso la semántica de `monto` es
`P-09` y no se puede asumir.
Borde que ejercita: redondeo por línea vs total + base de cálculo no declarada.
Fuente de la regla: R-06.

### CN-07 IVA — exenta, anulada y remanente — R-06
Datos: (a) factura afecta neto **500.000** (IVA 95.000); factura **exenta** neto
**300.000**; factura afecta **anulada** con IVA **76.000**. (b) un gasto recuperable
de **119.000**. (c) otro mes con débito **50.000** y crédito **80.000**.
Cálculo paso a paso:
- (a) débito = 95.000 (la exenta no tiene IVA y además se filtra por
  `tipo == afecta`, `finanzas.py:137`; la anulada se excluye, `:138`) = **95.000,00**
- (b) crédito = 119.000 × 19/119 = 1.000 × 19 = **19.000,00**; `a_pagar` =
  95.000 − 19.000 = **76.000,00**
- (c) 50.000 − 80.000 = −30.000 → `max(−30.000, 0)` = **0,00**; el remanente de
  **30.000** no se registra ni se arrastra (`finanzas.py:182`)
Resultado esperado: 76.000,00 en (b); 0,00 en (c) con **pérdida de 30.000**.
Borde que ejercita: afecta/exenta, anulación y remanente negativo (`P-09`).
Fuente de la regla: R-06.

### CN-08 estado de mantenimiento por km — R-07
Datos: tracto con `km_actual = 10.000`; pauta "Cambio de aceite" con
`intervalo_km = 20.000`; registro de mantención a **10.000 km**; alerta **5.000 km**.
Cálculo paso a paso: próximo = 10.000 + 20.000 = 30.000; restante = 30.000 − 10.000 =
20.000 → 20.000 > 5.000 → **ok**.
- `km_actual = 26.000` → restante 4.000 → 0 < 4.000 ≤ 5.000 → **por_vencer**
- `km_actual = 30.000` → restante 0 → ≤ 0 → **pendiente**
- `km_actual = 31.000` → restante −1.000 → **pendiente**
- pauta sin registro → `proximo_km = null`, **sin_registro**
Segundo registro a **9.000 km** (posterior en fecha): el "último" sigue siendo el de
10.000 porque se elige el de **mayor km** (`:170-179`) → próximo 30.000; el registro de
9.000 no altera el estado.
Contra-caso: si se edita la pauta a `intervalo_km = 25.000` (`PUT /pautas/{id}`,
`:57-73`), el mismo registro pasa a próximo 35.000 y restante 25.000 → **ok**: el
histórico se reinterpreta.
Resultado esperado: ok / por_vencer / pendiente / pendiente / sin_registro; y el
histórico cambia al editar la pauta.
Borde que ejercita: umbral exacto (`restante == 0`), odómetro que solo sube y
mutación retroactiva de la pauta.
Fuente de la regla: R-07.

### CN-09 export/PDF no reproducible contra el documento emitido — R-09
Datos: liquidación **2026-10 emitida** con CN-03 (comisión 180.000; líquido 530.000).
Después de emitir, se factura en el mismo mes un viaje del mismo chofer por
**200.000** (estaba `finalizado`).
Cálculo paso a paso:
- `GET /export/liquidaciones?mes=2026-10` recalcula la comisión (`export.py:115,124`):
  base = 1.800.000 + 200.000 = 2.000.000 → comisión = 200.000; `total_liquido` del CSV
  (`:165`) = 400.000 + 200.000 + 50.000 − 100.000 = **550.000,00**
- documento emitido: comisión **180.000**, líquido **530.000**
- `GET /liquidaciones/{id}/pdf` recalcula los haberes (`liquidaciones.py:515`) pero
  imprime el total almacenado (`:466`): el PDF muestra comisión 200.000, bonos 50.000,
  anticipos 100.000 y un "TOTAL LÍQUIDO" de **530.000** que no cuadra con la suma de
  sus propias líneas (400.000 + 200.000 + 50.000 − 100.000 = **550.000**)
Resultado esperado: CSV 550.000; PDF con líneas que suman 550.000 y total impreso
530.000; diferencia **20.000**.
Borde que ejercita: cambio posterior al cierre + documento emitido (misma familia que
SEC-002, ahora medible).
Fuente de la regla: R-09 (y R-05).

## Validaciones pendientes

Las preguntas que afectan a estas reglas (IVA/F29 y crédito fiscal, nómina legal,
descuento de anticipos, intervalos de mantención, clase de licencia exigida por el
seguro, tributación de la comisión) **no se responden acá**. El registro único de
decisiones del dueño (`D-NN`) y de preguntas a terceros (`P-NN`) es
[`preguntas.md`](preguntas.md). Este documento solo enuncia la regla y su estado
de implementación. Las reglas `R-05…R-09` se extrajeron de la implementación legacy el
**2026-10-31**; su análisis de portabilidad/retiro está en
[`retiro-legacy-modulos.md`](retiro-legacy-modulos.md).
