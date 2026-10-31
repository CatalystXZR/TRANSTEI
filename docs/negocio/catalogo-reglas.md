# Catálogo de reglas de negocio — ERP Transportes TEI SpA

> **Pregunta que responde:** ¿cuál es la regla de negocio `R-0XX`, su fórmula y su estado de implementación?
> **Dueño:** `negocio-finanzas` · **Verificado:** 2026-10-30 (R-04; R-01…R-03 sin re-verificar en esta sesión) · **Método:** lectura de código + DDL de migraciones + decisiones del dueño
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

## Validaciones pendientes

Las preguntas que afectan a estas reglas (IVA/F29, nómina legal, clase de licencia
exigida por el seguro, tributación de la comisión) **no se responden acá**. El
registro único de decisiones del dueño (`D-NN`) y de preguntas a terceros (`P-NN`)
es [`preguntas.md`](preguntas.md). Este documento solo enuncia la regla y su estado
de implementación.
