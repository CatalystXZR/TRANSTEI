# Registro de invariantes — estado real por invariante

> **Pregunta que responde:** ¿qué invariante existe, qué lo impone y qué sigue sin garantía?
> **Dueño:** agente `datos` · **Verificado:** 2026-10-29 · **Método:** lectura de DDL
> **Caduca si:** se agrega o edita una migración, o se ejecutan pruebas contra una base real.
> **Re-verificar con:** `ls supabase/migrations/` + `grep -n "create trigger\|create or replace function"`.

> Este registro contiene **todos** los invariantes identificados, estén o no
> impuestos. Los que tienen mecanismo citan `archivo:línea`; los que no, declaran
> qué los cubre hoy (servicio, UI o nada). **Ningún mecanismo está verificado como
> aplicado**: ver §0.
>
> El diseño original de las fichas (§2–§7) se conserva; el **estado vigente** es
> el de la tabla de §1 y las correcciones de §10.

## 0. Convenciones

- **ID:** `INV-<categoría><NN>`
  `D` disponibilidad/ocupación · `C` comercial (OC/tarifas) · `DOC` documentos ·
  `G` gastos · `F` facturación/pagos · `L` legacy · `T` tenant/multiempresa ·
  `A` auditoría · `X` cutover.
- **Estado en base:**
  - `impuesto (DDL)` — el mecanismo existe en una migración del repo.
  - `parcial (DDL)` — el mecanismo cubre solo una parte del enunciado.
  - `solo servicio` — lo valida Python/el endpoint; la base no lo impide.
  - `solo UI` — solo lo impide la pantalla.
  - `ausente` — nada lo impone.
  **Ninguno de estos estados implica "aplicado".** La aplicación de las 19
  migraciones es 🔴: no hay acceso a la base en esta sesión y el repo no tiene un
  registro confiable (`catalogo-migraciones.md` §0). `impuesto (DDL)` se lee
  **"el mecanismo está escrito"**, no "está en vigor".
- **SQLSTATE esperado:** el que el mecanismo debe emitir para que
  `backend/app/nucleo/errores.py:135-186` lo traduzca sin 500.
  Recordatorio: el mapeo **real** hoy es `23P01/23505 → 409`, `23514 → 409`,
  `23503 → 422`, `23502 → 500 (sin rama)` (ver `garantias.md` §15.2).
- **Prueba:** toda prueba de concurrencia exige **dos conexiones reales**. Una
  prueba secuencial no prueba concurrencia (`AGENTS.md` §7). Toda prueba debe
  incluir **mutación**: retirar el mecanismo en una copia desechable y confirmar
  que la prueba falla.

## 1. Tabla resumen

| ID | Invariante (una frase) | Estado en base | Mecanismo (existente o escrito) | SQLSTATE | Dónde / nota |
|---|---|---|---|---|---|
| INV-D04 | Todo viaje con tracto, rampla y chofer, `estado <> 'anulado'`, tiene 3 reservas activas con la ventana del viaje | **impuesto (DDL)** | `fn_viaje_reservas()` reescrita + `trg_viajes_70_reservas` + backfill · `0015:183-245,318-471` | 23P01 (solape) / 23514 (backfill inconsistente) | Reemplaza el diseño de §2: la condición es "3 recursos", no una lista de estados. Recursos parciales no ocupan (`0015:30-35`) |
| INV-D05 | Una reserva de viaje no se desactiva mientras el viaje ocupe | **ausente** | — · `0015` **no** lo implementa | 23514 | `UPDATE activa=false` sigue siendo libre |
| INV-D06 | Sin reservas activas huérfanas con ventana pasada | **ausente** | — | n/a (alerta) | Propuesto como vista/job, no constraint |
| INV-D07 | Un bloqueo/mantención no se solapa con una reserva activa de viaje del mismo recurso | **impuesto (DDL)** | 3 `EXCLUDE` sobre `reservas_recurso` · `0004:744-757` | 23P01 | Mecanismo existe desde `0004`; **sin prueba** de dos conexiones |
| INV-DOC04 | Todo viaje con los tres recursos valida documentos de tracto, rampla y chofer | **impuesto (DDL)** | `fn_viaje_documentos()` + `trg_viajes_05_documentos` · `0015:247-315` | 23514 | Nuevo en `0015`; cierra el hueco de `confirmado` |
| INV-R02-01 | Solo la clase A5 es asignable; clase ausente ⇒ viola | **impuesto (DDL)** | `fn_viaje_licencia_a5()` + `trg_viajes_03_licencia_a5` · `0016:193-257` | 23514 | Nuevo en `0016`; no hay `CHECK` sobre `choferes.licencia_clase` |
| INV-R02-02 | La licencia del chofer vence en o después del fin efectivo del viaje (+ margen) | **impuesto (DDL)** | `validar_documentos_recurso` · `0004:1019-1104`, invocado por `fn_viaje_validar` y (desde `0015`) por `fn_viaje_documentos` | 23514 | Ya existía; `0015` amplía a qué viajes aplica |
| INV-R02-03 | Licencia a ≤14 días es **aviso**, no bloqueo | **solo servicio** | `politicas.py` (aviso) + default `dias_alerta_documentos = 14` · `0016:182-186` | — | Por diseño no es constraint; el default no reescribe filas |
| INV-C03 | `sobregiro_autorizado` solo puede aumentar si `sobregiro_estado='aprobado'` | **parcial (DDL)** | `ck_oc_sobregiro_estado`, `ck_oc_sobregiro_pendiente` · `0005:61-68`; el **monto habilitante** no está atado a la aprobación | 23514 | Sin trigger `fn_oc_sobregiro`; `0016` no lo implementa |
| INV-C04 | Una tarifa en uso no se borra | **ausente** | — · solo FK `restrict` si hay referencia viva · `0004:481-482` | 23514 | La referencia histórica en `tarifa_snapshot` no protege |
| INV-C05 | El crédito autorizado del cliente limita la exposición pendiente | **ausente** | columna `0004:171`, sin lector · `grep -rn "credito_autorizado" backend/app/nucleo/servicio_*.py` → 0 | 23514 | Bloqueado por decisión de negocio (§9) |
| INV-DOC03 | `exigir_oc`/`exige_oc` obligan a tener OC | **ausente** | columnas `0004:125,172`, sin lector; `0015`–`0019` no las tocan | 23514 | `grep -rn "exigir_oc\|exige_oc" backend/app/nucleo/**` → 0 |
| INV-G04 | Un gasto aprobado es inmutable en monto, tipo, proveedor y documento | **ausente** | — · `service_role` conserva `UPDATE` · `0011:179` | 23514 | — |
| INV-G05 | Un gasto no se duplica por doble envío | **ausente** | — · sin `UNIQUE` ni clave de idempotencia · `0011:29-71` | 23505 | La coincidencia de "idempotente" en `0015`/`0016` es del backfill, no de gastos |
| INV-G06 | Los gastos no se borran físicamente | **ausente** | — · sin `no_delete` | 23514 | — |
| INV-F01 | Pagos + NC aplicadas nunca superan el total de la factura | **solo servicio** | `servicio_facturacion.py:624-631`: `SELECT` + `if`, **sin lock** | 23514 | TOCTOU: dos pagos concurrentes pueden superar el saldo |
| INV-F02 | Registrar un pago es idempotente ante reintento | **ausente** | — · sin clave ni `UNIQUE` sobre `referencia` · `0013:78-98` | 23505 | — |
| INV-F03 | Una factura emitida no se edita ni se borra | **ausente** | — · `service_role` con `UPDATE` · `0013:264` | 23514 | — |
| INV-F04 | Los pagos y notas de crédito no se borran (se compensan) | **ausente** | — · `fn_pago_estado` recalcula incluso en `DELETE` · `0013:219-222` | 23514 | — |
| INV-F05 | El vínculo factura↔viaje no se rompe después de emitir | **ausente** | — · sin `no_delete` en `factura_viajes` · `0013:54-68` | 23514 | — |
| INV-F06 | Anular una factura exige motivo y deja rastro | **ausente** | — · `ck_factura_estado` solo valida el dominio · `0013:35` | 23514 | — |
| INV-F07 | Una NC no supera el saldo de la factura | **solo servicio** | `servicio_facturacion.py:656-663` | 23514 | — |
| INV-L01 | En `public.viajes`, un tracto/rampla/chofer no tiene dos viajes activos solapados | **ausente** | — · `0001:97-112`; el router solo mira tracto y dos estados · `viajes.py:99-115` | 23P01 | RA-02 abierto; `0015` no toca `public` |
| INV-L02 | El folio SII es único por empresa | **ausente** | existe `unique (numero_sii, cliente_id)` · `0001:142`, que garantiza **otra** cosa | 23505 | — |
| INV-L03 | En `public.facturas`, `total = monto_neto + iva` | **ausente** | — · tres columnas independientes con default 0 · `0001:132-134` | 23514 | — |
| INV-L04 | En `public.facturas`, una factura emitida no se borra | **ausente** | — · `DELETE` físico · `facturas.py:241-263` | 23514 | — |
| INV-L05 | En `public.liquidaciones`, `total_liquido` es coherente y no se recalcula tras emitir | **ausente** | — · columna plana · `0001:179`; cálculo en Python · `liquidaciones.py:295-299` | 23514 | — |
| INV-L06 | En `public.viajes`, `fecha_fin >= fecha_inicio` | **solo servicio** | router `viajes.py:91-96` | 23514 | — |
| INV-T01 | Ningún rol de aplicación lee o escribe filas de otra empresa | **ausente** | RLS habilitado, **cero políticas** en `nucleo` · `0004:1867-1881`; sin `FORCE RLS` | 42501 | RA-03; `0015`–`0019` no agregan políticas |
| INV-T02 | Una reserva no apunta a un viaje de otra empresa | **parcial (DDL)** | `fn_reserva_validar` · `0004:1669-1676`, **solo si `activa`**; FK simple `0004:727-728` | 23503 | Una reserva desactivada puede cruzar empresas |
| INV-T03 | Una membresía apunta a un usuario de Auth existente | **ausente** | `auth_id` sin FK · `0004:142` | 23503 | — |
| INV-T04 | `public` no acepta escrituras cuando el cutover está congelado | **ausente** | solo middleware HTTP · `main.py:36-56`; ningún trigger ni privilegio | 23514 | Scripts/`psql`/jobs no pasan por el middleware |
| INV-X01 | El estado de cutover es *fail-closed* | **ausente** | **fail-open**: `except Exception: congelado = False` · `servicio_cutover.py:38-39` | — (handoff) | Handoff a `backend` |
| INV-A01 | `nucleo.auditoria` no admite `TRUNCATE` | **parcial (DDL)** | trigger de fila · `0004:890-892`; `service_role` sin `TRUNCATE` · `0004:1887`; el **dueño sí puede** | 23514 | Falta trigger `BEFORE TRUNCATE` por sentencia |
| INV-A02 | Los cambios de cutover quedan auditados | **ausente** | `cutover_control` sin trigger `_audit` · `0014:8-15` | — | — |

**Total: 35 invariantes** (31 previos + 4 que ya estaban documentados en §10.2 y
se incorporan a la tabla: `INV-DOC04`, `INV-R02-01`, `INV-R02-02`, `INV-R02-03`).
Estado: **5 impuestos en DDL** (`INV-D04`, `INV-D07`, `INV-DOC04`, `INV-R02-01`,
`INV-R02-02`), **3 parciales en DDL** (`INV-C03`, `INV-T02`, `INV-A01`),
**4 solo servicio** (`INV-R02-03`, `INV-F01`, `INV-F07`, `INV-L06`), **0 solo UI**
y **23 ausentes**. Ninguno con prueba ejecutada (§8).

> Las fichas de §2–§7 conservan el diseño original y siguen siendo válidas como
> análisis del hueco, pero **no como estado**: donde digan "migración 0016/0017/…"
> el número corresponde al plan archivado, no al archivo real. El estado vigente es
> §1 y §10.

---

## 2. Detalle: disponibilidad y ocupación

### INV-D04 — Todo viaje con recursos ocupa el libro

> **Diseño superado.** Este enunciado (lista de estados + disyuntiva A/B) es el
> análisis previo a escribir el SQL. La regla vigente es la de §1 y §10.3: **tres
> recursos y `estado <> 'anulado'`**, sin lista de estados. Se conserva como
> historia del razonamiento, no como especificación.

**Enunciado.** Si `nucleo.viajes` tiene `tracto_id`, `rampla_id` o `chofer_id`
no nulos y su estado está en el conjunto operativo
(`asignado, en_carga, cargado, en_ruta, en_descarga, descargado, pod_pendiente,
cerrado, facturado, cobrado`), existe una fila activa correspondiente en
`nucleo.reservas_recurso` con la misma ventana.

**Por qué importa.** Disponibilidad. El `EXCLUDE` solo ve lo que está en el libro.
Hoy `fn_viaje_reservas` no inserta reservas para `confirmado`
(`0004:1632-1635`) y `ck_viaje_recursos_por_estado` **permite** recursos en
`confirmado` (`0004:671-674`). `scripts/cutover_legacy.py:361-388` inserta viajes
`confirmado` **con** los tres recursos: esos viajes ocupan un tracto real y son
invisibles para la mesa de despacho. Dos viajes pueden apuntar al mismo tracto en
la misma ventana y la base no dice nada.

**Mecanismo propuesto.** Dos alternativas, excluyentes:
- **(A) Reservar también en `confirmado`**: quitar `'confirmado'` de la lista de
  exclusión en `fn_viaje_reservas` y en `fn_viaje_validar` (para que la validación
  documental también aplique), o
- **(B) Prohibir recursos en `confirmado`**: endurecer
  `ck_viaje_recursos_por_estado` a `estado IN ('borrador','cotizado','confirmado','anulado') ⇒ los tres recursos NULL`.

Recomendación: **(A)**, porque el flujo real (`crear_viaje` → `confirmado` →
`confirmar_asignacion` → `asignado`, `servicio_disponibilidad.py:951` y
`1411-1572`) reserva en el paso 2 y el cutover ya deja recursos asignados en el
paso 1; (B) obligaría a limpiar los viajes migrados. **(A) exige decisión de
negocio**: reservar en `confirmado` bloquea el recurso antes de la confirmación
del cliente.

**SQLSTATE.** `23514` (trigger `raise ... using errcode`), igual que el resto de
`fn_viaje_*`.

**Prueba propuesta.**
1. Positiva: insertar viaje `confirmado` con los tres recursos ⇒ aparece 1 fila
   por recurso en `reservas_recurso` (`select count(*) … = 3`).
2. Violatoria (dos conexiones): A inserta viaje `confirmado` con tracto T en
   `[10:00,12:00)` sin commit; B intenta lo mismo con el mismo T ⇒ B **espera**
   (lock de fila del `EXCLUDE` no, pero sí conflicto al commitear) o falla con
   `23P01`; al commitear A, B recibe `23P01` y **no** queda segunda reserva.
3. Borde: `fin` del primero = `inicio` del segundo ⇒ permitido (rango semiabierto).
4. Mutación: retirar el `EXCLUDE` en la copia ⇒ la prueba 2 pasa a verde
   (duplicado) ⇒ la prueba sí probaba algo.

### INV-D05 — Una reserva de viaje no se desactiva mientras el viaje ocupe

**Enunciado.** Para `tipo_reserva='viaje'`, no se puede pasar `activa` de `true` a
`false` si el viaje sigue en estado operativo y esa reserva todavía coincide con
los recursos del viaje.

**Por qué importa.** `UPDATE nucleo.reservas_recurso SET activa=false` libera el
recurso para cualquier otro viaje **sin tocar el viaje**. Hoy solo el trigger
`fn_viaje_reservas` desactiva (`0004:1628-1630`), pero nada impide hacerlo a mano
(script, consola, futuro endpoint). Un `UPDATE` de una línea convierte un tracto
ocupado en "libre".

**Mecanismo.** Extender `fn_reserva_validar` (`0004:1653-1690`): en `UPDATE`, si
`old.activa AND NOT new.activa AND new.tipo_reserva='viaje'`, exigir que
(a) el viaje esté en estado no operativo, **o** (b) la reserva ya no coincida con
los recursos actuales del viaje (caso reasignación), **o** (c) exista
`current_setting('nucleo.reasignacion_autorizada')='on'` dentro de la misma
transacción que actualiza el viaje.

**SQLSTATE.** `23514`.

**Prueba.** Dos conexiones: A abre tx y actualiza el viaje a `asignado` (crea
reservas) sin commit; B hace `update reservas_recurso set activa=false where
viaje_id=A` ⇒ debe fallar `23514` (no debe poder "liberar" el recurso de un viaje
vivo). Mutación: retirar la rama ⇒ B devuelve `UPDATE 1` y el recurso queda libre.

### INV-D06 — Sin reservas activas huérfanas

**Enunciado.** No existe reserva activa cuyo `upper(ventana)` sea anterior a
`now() - intervalo de gracia` y que no corresponda a un viaje abierto.

**Por qué importa.** Higiene operativa: reservas viejas activas bloquean recursos
para siempre y hacen que el `EXCLUDE` rechace asignaciones legítimas; el síntoma
se diagnostica mal ("la base dice ocupado y nadie lo está").

**Mecanismo.** Job/trigger de cierre (desactivar con `cancelado_motivo='auto:
ventana vencida'`) + vista de control `nucleo.v_reservas_huerfanas`. **No** un
`EXCLUDE` (no es una regla de exclusión).

**SQLSTATE.** n/a (no rechaza; reporta). Se propone como **alerta**, no como
constraint: convertir esto en `CHECK` rompería viajes en curso con desvío.

**Prueba.** Insertar reserva con ventana pasada ⇒ la vista devuelve 1 fila; el job
la desactiva y deja `cancelado_*` poblado.

### INV-D07 — Bloqueo vs viaje (ya existe, falta prueba)

**Enunciado.** Un `bloqueo_manual`, `mantenimiento`, `descanso` o `vacaciones`
no puede solaparse con una reserva activa de viaje del mismo recurso.

**Estado.** **🟢 el mecanismo existe** (`ex_reserva_*`, `0004:744-757`, cubre toda
la tabla, no solo `tipo_reserva='viaje'`), pero **no hay ninguna prueba** y no se
verificó que `servicio_bloqueos.py:233-290` inserte en el mismo libro con la
ventana correcta. Se registra aquí solo para dejar constancia de la deuda de
prueba; ver §8.

**Prueba.** Dos conexiones: A crea viaje `asignado` en `[8:00,12:00)`; B intenta
bloqueo de mantención en `[11:00,13:00)` ⇒ `23P01` con constraint
`ex_reserva_tracto`. Mutación: retirar el `EXCLUDE` ⇒ B pasa.

---

## 3. Detalle: comercial

### INV-C03 — El sobregiro solo habilita consumo si fue aprobado

**Enunciado.** `ordenes_compra.sobregiro_autorizado` solo puede aumentar si
`sobregiro_estado='aprobado'` y `sobregiro_aprobado_por`/`_en` están poblados.

**Por qué importa.** Dinero. `monto_consumido <= monto_autorizado +
sobregiro_autorizado` (`0004:453`) es la única barrera de consumo, y
`sobregiro_autorizado` es una columna libre: subirla equivale a autorizar gasto
sin aprobación. El flujo de aprobación (`0005:47-75`) valida el **estado**, no el
**monto habilitante**.

**Mecanismo.** Trigger `fn_oc_sobregiro` (BEFORE UPDATE): si
`new.sobregiro_autorizado > old.sobregiro_autorizado` y no
(`new.sobregiro_estado='aprobado'` y `new.sobregiro_aprobado_por IS NOT NULL`),
rechazar. Alternativa más estricta: `sobregiro_autorizado` pasa a ser columna
derivada de `sobregiro_solicitado` cuando el estado es `aprobado`.

**SQLSTATE.** `23514`.

**Prueba.** `UPDATE ordenes_compra SET sobregiro_autorizado = 5000000` sin
aprobación ⇒ `23514`. Con `sobregiro_estado='aprobado'` y aprobador ⇒ pasa.
Mutación: retirar el trigger ⇒ el primer `UPDATE` devuelve `UPDATE 1`.

### INV-C04 — Una tarifa referenciada no se borra

**Enunciado.** No se puede `DELETE` una `nucleo.tarifas` que tenga líneas de OC o
viajes asociados.

**Por qué importa.** Trazabilidad de precio. Las FK `restrict`
(`0004:481-482`, `0004:650-651`) ya bloquean el borrado **si** hay referencia;
pero un viaje histórico que guardó `tarifa_snapshot` y perdió el `tarifa_id`
(permitido: `tarifa_id` es nullable, `0004:548`) deja la tarifa borrable y el
precio sin origen.

**Mecanismo.** Trigger `fn_tarifa_no_borrar` que rechace `DELETE` cuando
`existe viaje con tarifa_id` **o** `tarifa_snapshot->>'tarifa_id' = old.id::text`.
Es decir, cubre también la referencia histórica en JSONB.

**SQLSTATE.** `23514`.

**Prueba.** Borrar una tarifa usada por un viaje facturado ⇒ `23514`. Mutación:
retirar el trigger y además `UPDATE viajes SET tarifa_id=null` ⇒ el `DELETE` pasa
(evidencia de que la protección histórica hacía falta).

### INV-C05 — Crédito autorizado (requiere decisión de negocio)

**Enunciado.** La exposición pendiente de un cliente (facturas no pagadas menos
NC) no supera `clientes.credito_autorizado`, salvo `credito_autorizado = 0`
interpretado como "sin límite" **o** como "sin crédito" (decisión pendiente).

**Por qué importa.** Riesgo financiero. Hoy la columna existe (`0004:171`) y
**nadie la lee**: `grep -rn "credito_autorizado" backend/app/nucleo/servicio_*.py`
→ 0 resultados.

**Mecanismo propuesto.** Trigger en `nucleo.facturas_nucleo` (BEFORE INSERT y
UPDATE de `neto`/`estado`) que sume la exposición del cliente con `FOR UPDATE` de
la fila del cliente (punto de serialización). **Bloqueado**: falta que
`negocio-finanzas` defina el significado de `0` y si el límite aplica al emitir o
al despachar.

**SQLSTATE.** `23514`.

**Prueba.** Cliente con crédito 1.000.000 y factura vigente por 900.000; emitir
otra por 200.000 ⇒ `23514`. Dos conexiones: dos facturas de 600.000 simultáneas
⇒ solo una gana. Mutación: retirar el trigger ⇒ ambas pasan.

### INV-DOC03 — `exigir_oc` / `exige_oc` deben obligar

**Enunciado.** Si `nucleo.empresas.exigir_oc` o `nucleo.clientes.exige_oc` es
`true`, un viaje sin `orden_compra_id` no puede pasar a `facturado` (y, si la
decisión es de despacho, tampoco a `asignado`).

**Por qué importa.** Control interno. Ambas columnas existen (`0004:125`,
`0004:172`) y **no se usan en ninguna parte** del código (verificado con `grep`
sobre `servicio_*.py`, `politicas.py`, `api_*.py`). Un flag que no hace nada es
peor que no tenerlo: da falsa sensación de control.

**Mecanismo.** Extender `fn_viaje_facturacion` (`0009:65-136`): si
`v_empresa.exigir_oc or v_cliente.exige_oc` y `new.orden_compra_id IS NULL` ⇒
rechazar. Requiere leer el cliente, que la función ya no hace.

**SQLSTATE.** `23514`.

**Prueba.** Empresa con `exigir_oc=true`, viaje sin OC, `UPDATE estado='facturado'`
⇒ `23514`. Mutación: `exigir_oc=false` ⇒ pasa (confirma que el flag es la causa).

---

## 4. Detalle: gastos

### INV-G04 — Gasto aprobado inmutable

**Enunciado.** Con `estado='aprobado'`, no cambian `monto_total`, `iva`, `tipo`,
`proveedor`, `numero_documento`, `fecha`, `litros`, `precio_litro`, `viaje_id`.

**Por qué importa.** Dinero. El costo real se calcula desde gastos aprobados
(`0011:107-113`) y se persiste en el viaje (`0011:129-133`). Cambiar el monto de
un gasto aprobado altera el margen histórico sin dejar rastro (sí queda en
`nucleo.auditoria`, pero el dato cambia). `service_role` tiene `UPDATE` sobre la
tabla (`0011:179`).

**Mecanismo.** Trigger `fn_gasto_proteccion` (BEFORE UPDATE), mismo patrón que
`fn_viaje_proteccion` (`0004:1474-1491`), con escape por
`current_setting('nucleo.ajuste_autorizado')`.

**SQLSTATE.** `23514`.

**Prueba.** Aprobar gasto; luego `UPDATE viaje_gastos SET monto_total=999999` ⇒
`23514`. Mutación: retirar el trigger ⇒ `UPDATE 1` y `viajes.costo_variable_real`
cambia (la prueba demuestra el impacto económico).

### INV-G05 — Gasto no duplicable

**Enunciado.** Para una misma `(empresa_id, viaje_id, proveedor,
numero_documento)` no existe más de un gasto activo.

**Por qué importa.** Dinero directo: doble clic o reintento duplica el gasto y el
costo del viaje. No hay ninguna barrera (`0011:29-71`).

**Mecanismo.** `UNIQUE` parcial
`(empresa_id, viaje_id, upper(btrim(proveedor)), upper(btrim(numero_documento)))
WHERE activo AND numero_documento IS NOT NULL` **más** columna
`idempotency_key text` con `UNIQUE (empresa_id, idempotency_key)` para el caso sin
documento. Dos mecanismos porque el caso "sin boleta" no tiene clave natural.

**SQLSTATE.** `23505` (→ 409 con el mapeo actual de `errores.py:149-163`).

**Prueba.** Dos conexiones: A y B insertan el mismo `(proveedor, numero_documento)`
⇒ una gana, la otra recibe `23505` (no `23502`, no `500`). Mutación: retirar el
índice ⇒ 2 filas.

### INV-G06 — Gastos no se borran

**Enunciado.** `DELETE` sobre `nucleo.viaje_gastos` rechazado; se usa
`activo=false` con motivo.

**Por qué importa.** El costo del viaje se recalcula por trigger
(`0011:154-156`), así que borrar un gasto reescribe el margen sin dejar el monto
original en la fila. La auditoría sí guarda `datos_antes`, pero el registro de
negocio desaparece. En legacy el borrado es un endpoint (`api/routes/gastos.py:93-104`).

**Mecanismo.** `fn_gasto_no_borrar` + `REVOKE DELETE` a `service_role`.

**SQLSTATE.** `23514`.

**Prueba.** `DELETE FROM nucleo.viaje_gastos WHERE id=…` ⇒ `23514`. Con el rol de
aplicación ⇒ `42501`. Mutación: `DROP TRIGGER` + `GRANT DELETE` ⇒ borra.

---

## 5. Detalle: facturación, pagos y notas de crédito

### INV-F01 — Pagos + NC nunca superan el total

**Enunciado.** Para toda factura,
`sum(pagos.monto) + sum(NC aplicadas.monto) <= facturas_nucleo.total`.

**Por qué importa.** Dinero. Hoy la validación es
`servicio_facturacion.py:624-631`: `SELECT` de saldos → `if monto > saldo` →
`INSERT`. Sin lock y sin constraint, dos pagos concurrentes de 600.000 sobre una
factura de 1.000.000 con saldo 1.000.000 pueden **ambos** pasar (cada uno ve el
saldo completo) ⇒ se cobra 1.200.000. Es el TOCTOU clásico del manual.

**Mecanismo.** Trigger `fn_pago_validar` (BEFORE INSERT/UPDATE) que
(a) tome `SELECT ... FOR UPDATE` de `nucleo.facturas_nucleo` por `factura_id`
—el mismo punto de serialización que ya usa `fn_factura_estado`
(`0013:174`)—, y (b) revalide la suma incluyendo `NEW`. El `FOR UPDATE` es
obligatorio: sin él, dos triggers concurrentes leen el mismo saldo.

**SQLSTATE.** `23514` (regla de negocio; con el mapeo actual sale 409, que es el
HTTP correcto para "conflicto con el estado actual").

**Prueba (dos conexiones).** Factura total 1.000.000, sin pagos.
A: `BEGIN; INSERT pago 600.000;` (sin commit). B: `BEGIN; INSERT pago 600.000;`
⇒ B debe **bloquearse** en el `FOR UPDATE` de la factura; al commitear A, B debe
recibir `23514` y hacer rollback. Estado final: 1 pago, saldo 400.000.
Mutación: retirar el `FOR UPDATE` (dejar solo la suma) ⇒ con dos conexiones
aparecen 2 pagos (la prueba falla), demostrando que el lock era el mecanismo.

### INV-F02 — Pago idempotente

**Enunciado.** El mismo `Idempotency-Key` (o la misma `referencia` bancaria)
no produce dos pagos en la misma empresa.

**Por qué importa.** Un reintento de red o un doble clic duplica dinero cobrado y
descuadra la cobranza. `nucleo.pagos_nucleo` (`0013:78-98`) no tiene clave de
idempotencia ni `UNIQUE` sobre `referencia`.

**Mecanismo.** `idempotency_key text` + `UNIQUE (empresa_id, idempotency_key)
WHERE idempotency_key IS NOT NULL`; el endpoint devuelve la factura ya existente
en vez de error cuando la clave se repite (handoff a `backend`).

**SQLSTATE.** `23505` en la carrera; el servicio debe capturarlo y devolver
**200 con el pago existente**, no 409 (idempotencia ≠ conflicto). Esto es una
decisión de contrato para `backend`.

**Prueba.** Dos conexiones con la misma clave ⇒ 1 fila, y la segunda respuesta
apunta al mismo `pago_id`. Mutación: retirar el índice ⇒ 2 filas.

### INV-F03 — Factura emitida inmutable

**Enunciado.** Con `estado <> 'emitida'` (es decir, una vez que tiene pagos,
NC o está pagada/vencida/anulada) no cambian `neto`, `iva`, `cliente_id`,
`orden_compra_id`, `fecha_emision`, `moneda`; y nunca se permite `DELETE`.

**Por qué importa.** Documento tributario. `AGENTS.md` §3.16: un documento emitido
no se edita ni se borra, se corrige con documento compensatorio. Hoy
`nucleo.facturas_nucleo` no tiene ninguna protección (`0013:10-38`; `service_role`
con `UPDATE` en `0013:264`). En legacy es peor: `PUT` reescribe montos
(`facturas.py:174-198`) y `DELETE` borra la factura físicamente
(`facturas.py:241-263`).

**Mecanismo.** `fn_factura_proteccion` (BEFORE UPDATE/DELETE) análogo a
`fn_viaje_proteccion`: bloquea cambios de campos económicos cuando
`old.estado <> 'emitida'` o cuando ya existe pago/NC; bloquea `DELETE` siempre
(salvo `emitida` sin pagos y con autorización explícita). Requiere decidir si
"emitida sin pagos" es corregible: **decisión de negocio/tributaria** (§7).

**SQLSTATE.** `23514`.

**Prueba.** Factura pagada ⇒ `UPDATE neto` ⇒ `23514`; `DELETE` ⇒ `23514`.
Mutación: retirar el trigger ⇒ ambos pasan y el `total` generado cambia
(`0013:21`), demostrando que el documento emitido es mutable.

### INV-F04 — Pagos y NC no se borran

**Enunciado.** `DELETE` sobre `pagos_nucleo` y `notas_credito_nucleo` rechazado;
la corrección es una NC o un pago compensatorio.

**Por qué importa.** `fn_pago_estado` recalcula el estado incluso en `DELETE`
(`0013:219-222`): borrar un pago **degrada** la factura de `pagada` a `emitida`
sin dejar el hecho en el registro de negocio (sí en auditoría). Un cobro
desaparecido es un incidente financiero.

**Mecanismo.** `fn_pago_no_borrar` / `fn_nc_no_borrar` + `REVOKE DELETE`.

**SQLSTATE.** `23514`.

**Prueba.** Factura pagada; `DELETE FROM nucleo.pagos_nucleo` ⇒ `23514`; el
estado sigue `pagada`. Mutación: retirar el trigger ⇒ el pago desaparece y la
factura vuelve a `emitida`.

### INV-F05 — El vínculo factura↔viaje es inmutable tras emitir

**Enunciado.** No se `DELETE` ni se cambia `viaje_id` en `factura_viajes` de una
factura no anulada.

**Por qué importa.** Es el respaldo de "qué se facturó". `fn_factura_estado`
mueve viajes a `cobrado` leyendo esta tabla (`0013:202-210`); si se borra la fila,
el viaje queda `facturado` para siempre y la factura sin detalle.

**Mecanismo.** Trigger de protección + `REVOKE DELETE`.

**SQLSTATE.** `23514`.

**Prueba.** Borrar una fila de `factura_viajes` de una factura `pagada` ⇒ `23514`.
Mutación: retirar ⇒ borra y el viaje queda inconsistente.

### INV-F06 — Anulación de factura con motivo

**Enunciado.** El paso a `estado='anulada'` exige `motivo_anulacion`,
`anulado_por` y `anulado_en`, y es irreversible.

**Por qué importa.** Hoy `ck_factura_estado` solo valida el dominio del texto
(`0013:35`); no hay endpoint de anulación ni columnas de motivo. Cualquier
`UPDATE` puede dejar una factura `anulada` sin explicación, y `fn_factura_estado`
la ignora para siempre (`0013:178-180`).

**Mecanismo.** Columnas `motivo_anulacion`, `anulado_por`, `anulado_en` +
`CHECK (estado <> 'anulada' OR motivo_anulacion IS NOT NULL)` + trigger de
transición (patrón `fn_viaje_transicion`, `0004:1511-1547`).

**SQLSTATE.** `23514`.

**Prueba.** `UPDATE estado='anulada'` sin motivo ⇒ `23514`; con motivo ⇒ pasa; y
luego `UPDATE estado='emitida'` ⇒ `23514` (irreversible).

### INV-F07 — NC no supera el saldo

**Enunciado.** `sum(NC aplicadas) <= total - sum(pagos)`.

**Por qué importa.** Dinero. Hoy solo servicio (`servicio_facturacion.py:656-663`).
Una NC mayor que el saldo deja la factura con saldo negativo y `fn_factura_estado`
la marca `pagada` (`0013:190-191`) sin detectar el exceso.

**Mecanismo.** Mismo trigger que INV-F01 (`fn_nc_validar` con `FOR UPDATE` de la
factura).

**SQLSTATE.** `23514`.

**Prueba.** Dos conexiones emitiendo NC simultáneas ⇒ solo una gana.

---

## 6. Detalle: legacy `public`

> El legacy **no tiene `empresa_id`** (`0001` completo). Todo lo que sigue es
> single-tenant por construcción. Cualquier cambio en `public` requiere plan de
> convivencia y aprobación (`AGENTS.md` §8, §12; `database-safety` §4.3).

### INV-L01 — Sin doble asignación en `public.viajes`

**Enunciado.** Un mismo `tracto_id` (y `rampla_id`, `chofer_id`) no puede estar en
dos viajes con estado activo cuyas fechas se solapen.

**Por qué importa.** RA-02. Es la mitad legacy del problema de doble asignación:
`nucleo.reservas_recurso` protege el núcleo, `public.viajes` no tiene nada
(`0001:97-112`), y la validación es un `SELECT` sin lock que **solo mira el
tracto** (`viajes.py:99-115`) y solo los estados `programado`/`en_ruta`
(`viajes.py:104`) — ignora `finalizado` y no valida rampla ni chofer.

**Mecanismo.** `EXCLUDE USING gist (tracto_id WITH =, daterange(fecha_inicio,
coalesce(fecha_fin, fecha_inicio + 1), '[)') WITH &&) WHERE (estado IN
('programado','en_ruta'))` + análogos para rampla y chofer. Requiere `btree_gist`
(ya está, `0004:28`). **Problema de diseño del legacy:** usa `date`, no
`timestamptz`, así que la granularidad es el día y dos viajes el mismo día se
consideran solapados. Eso **cambia el comportamiento** del legacy y puede rechazar
operaciones hoy válidas ⇒ **exige aprobación y una consulta de detección**
ejecutada antes de aplicar; esa migración **no existe todavía**.

**SQLSTATE.** `23P01`.

**Prueba.** Dos conexiones: A inserta viaje `programado` tracto T 2026-11-01;
B inserta viaje `programado` tracto T 2026-11-01 ⇒ `23P01`. Mutación: retirar el
`EXCLUDE` ⇒ ambos pasan (reproduce RA-02).

### INV-L02 — Folio SII único por empresa

**Enunciado.** `numero_sii` es único en `public.facturas`.

**Por qué importa.** Tributario. Hoy `unique (numero_sii, cliente_id)`
(`0001:142`) permite emitir el folio 100 a dos clientes distintos. En un SII real
eso es un folio duplicado.

**Mecanismo.** Reemplazar por `UNIQUE (numero_sii)`. **Precondición obligatoria:**
detectar duplicados existentes (la consulta histórica L2 está en
`docs/_archivo/planes/plan-migraciones-0015.md`, **archivado: no citar como
estado**). Si hay filas, **reportar, no borrar** — decisión del contador.

**SQLSTATE.** `23505`.

**Prueba.** Insertar dos facturas con `numero_sii='100'` y clientes distintos ⇒
`23505`. Mutación: volver al índice viejo ⇒ pasa.

### INV-L03 — `total = monto_neto + iva` en legacy

**Enunciado.** En `public.facturas`, `total` es siempre `monto_neto + iva`.

**Por qué importa.** Dinero y tributario. Son tres columnas independientes con
default 0 (`0001:132-134`): se puede guardar `neto=100, iva=19, total=50`.

**Mecanismo.** `CHECK (total = monto_neto + iva)`. Alternativa (más invasiva):
`total generated always as (monto_neto + iva) stored` — rompe `INSERT` explícitos
del código actual (`facturas.py:169` hace commit del modelo con `total` calculado
en Python) ⇒ **preferir el `CHECK`** para no romper compatibilidad.

**SQLSTATE.** `23514`.

**Prueba.** `INSERT` con `total` inconsistente ⇒ `23514`. Precondición: contar
facturas que hoy lo violan.

### INV-L04 — Factura legacy no se borra

**Enunciado.** No se permite `DELETE` sobre `public.facturas` con `numero_sii`
no nulo.

**Por qué importa.** `DELETE /facturas/{id}` existe y borra físicamente
(`facturas.py:241-263`), incluyendo una factura emitida en estado `pendiente`.
`factura_viaje` tiene `on delete cascade` (`0001:146`), así que el borrado arrastra
el detalle.

**Mecanismo.** Trigger `public.fn_factura_no_borrar` + (si es viable) quitar el
endpoint (handoff a `backend`, no a `datos`).

**SQLSTATE.** `23514`.

**Prueba.** `DELETE` de una factura con `numero_sii` ⇒ `23514`. Mutación: retirar
el trigger ⇒ borra y desaparecen las filas de `factura_viaje`.

### INV-L05 — Liquidación legacy coherente e inmutable al emitir

**Enunciado.** `total_liquido = sueldo_base + comision + total_ajustes -
total_anticipos`; y con `estado='emitida'` los montos no cambian.

**Por qué importa.** Dinero laboral. `total_liquido` es una columna plana
(`0001:179`) calculada en Python (`liquidaciones.py:295-299`); `emitir` no valida
el estado previo (`liquidaciones.py:308-321`) y nada impide agregar anticipos o
ajustes después de emitir, dejando el PDF (`_generar_pdf`) distinto de la fila.

**Mecanismo.** `CHECK` de coherencia + trigger de inmutabilidad con
`estado='emitida'` + trigger que impida insertar `anticipos_chofer`/
`ajustes_liquidacion` en un mes ya emitido (o que obligue a reabrir con motivo).

**SQLSTATE.** `23514`.

**Prueba.** Emitir; luego `UPDATE total_liquido` ⇒ `23514`; insertar anticipo del
mismo mes ⇒ `23514`. Mutación: retirar ⇒ ambos pasan.

### INV-L06 — Fechas coherentes en legacy

**Enunciado.** `public.viajes.fecha_fin >= fecha_inicio`.

**Por qué importa.** Integridad básica; hoy solo se valida en el router
(`viajes.py:91-96`) y con `date` es fácil invertir el rango por error de tipeo.

**Mecanismo.** `CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)`.

**SQLSTATE.** `23514`.

**Prueba.** `UPDATE` con `fecha_fin < fecha_inicio` ⇒ `23514`. Precondición:
contar filas que ya lo violan.

---

## 7. Detalle: tenant (ver también `garantias.md` §14)

### INV-T01 — Aislamiento por empresa impuesto en la base

**Enunciado.** Con el rol de la aplicación, toda lectura y escritura sobre
`nucleo.*` queda restringida a la empresa del contexto de la transacción.

**Por qué importa.** RA-03. Es la garantía que el producto declara y hoy no tiene.
Cero políticas en `nucleo` (`grep -rn "create policy" supabase/migrations/` → solo
`0001:284` en `public.usuarios`), y el rol de conexión es el dueño
(`.env.example:15`) o `service_role`, ambos fuera de RLS.

**Mecanismo.** Políticas por tabla y operación + `FORCE ROW LEVEL SECURITY` + rol
`nucleo_app` sin `BYPASSRLS` + `SET LOCAL` del contexto. Detalle y trampas
(recursión de la política sobre `usuarios_empresa`, pooler en modo transacción) en
`garantias.md` §14.2.

**SQLSTATE.** `42501` (`insufficient_privilege`) — no es un conflicto de negocio;
el backend debe devolver **403/404 sin filtrar existencia**, no 500. Handoff.

**Prueba.** Rol `nucleo_app`, contexto empresa A: `SELECT * FROM
nucleo.viajes WHERE id = <viaje de B>` ⇒ 0 filas; `INSERT` con `empresa_id = B`
⇒ `42501` (o `WITH CHECK` violation). Mutación: `ALTER TABLE … NO FORCE ROW LEVEL
SECURITY` ⇒ las filas de B aparecen.

### INV-T02 — Reserva ligada a viaje de la misma empresa

**Enunciado.** `reservas_recurso.empresa_id` coincide con el `empresa_id` del
viaje referenciado.

**Por qué importa.** Es el único enlace sin FK compuesta (`0004:727-728`). Hoy lo
cubre `fn_reserva_validar` **solo cuando `activa`** (`0004:1669-1676`): una
reserva desactivada puede quedar apuntando a un viaje de otra empresa y la FK no
lo nota. Bajo RLS, esa fila sería visible para la empresa equivocada.

**Mecanismo.** FK compuesta `(empresa_id, viaje_id) → nucleo.viajes (empresa_id, id)`.
Requiere `UNIQUE (empresa_id, id)` en `viajes`, que ya existe (`0004:644`).

**SQLSTATE.** `23503`.

**Prueba.** Insertar reserva con `empresa_id=A, viaje_id` de B ⇒ `23503` (hoy:
pasa si `activa=false`). Mutación: volver a la FK simple ⇒ la fila entra.

### INV-T03 — Membresía apunta a un usuario real

**Enunciado.** `nucleo.usuarios_empresa.auth_id` existe en `auth.users`.

**Por qué importa.** Una membresía huérfana es una autorización zombi: si el UUID
se recicla o se escribe mal, alguien podría heredar permisos. En `public` sí hay
FK (`0001:38`); en `nucleo` no (`0004:142`).

**Mecanismo.** FK `auth_id → auth.users(id) ON DELETE CASCADE`. **Ojo:** los
tests y el seed deben crear usuarios de Auth; si hoy insertan UUIDs sintéticos, la
FK los rechazará ⇒ la precondición de la migración debe contarlos. **No borrar**:
reportar.

**SQLSTATE.** `23503`.

**Prueba.** Insertar membresía con UUID aleatorio ⇒ `23503`. Mutación: quitar la
FK ⇒ pasa.

### INV-T04 / INV-X01 — Congelamiento de cutover impuesto y fail-closed

**Enunciado.** (T04) Con `legacy_escritura_congelada = true`, ninguna escritura
en `public` se confirma. (X01) Si el estado no se puede leer, se asume congelado.

**Por qué importa.** El cutover es el momento en que se declara "una sola fuente
de verdad". Hoy el bloqueo es un middleware HTTP (`main.py:36-56`) con caché de
5 s (`servicio_cutover.py:17-26`) que **falla abierto** ante cualquier excepción
(`servicio_cutover.py:38-39`). Cualquier escritor que no pase por ese middleware
(script, psql, job, otro servicio) escribe en `public` sin obstáculo.

**Mecanismo.** (T04) Trigger `BEFORE INSERT/UPDATE/DELETE` en las tablas legacy
que consulte `nucleo.cutover_control` y rechace; con escape por
`current_setting('nucleo.cutover_override')`. (X01) es **handoff a `backend`**:
`except` ⇒ `True`.

**SQLSTATE.** `23514` (trigger) — el middleware ya devuelve 409 con código
`CUTOVER_LEGACY_CONGELADO` (`main.py:50-56`), así que el mapeo es coherente.

**Prueba.** Congelar; `INSERT` en `public.viajes` por `psql` (sin middleware) ⇒
`23514`. Mutación: retirar el trigger ⇒ inserta (demuestra que el middleware no
era la garantía).

### INV-A01 / INV-A02 — Auditoría no truncable y cutover auditado

**A01.** `TRUNCATE nucleo.auditoria` no dispara el trigger de fila
(`0004:890-892`). Mecanismo: trigger `BEFORE TRUNCATE ... FOR EACH STATEMENT`.
Prueba: `TRUNCATE` con el rol dueño ⇒ `23514`; mutación ⇒ la tabla queda vacía.
Hoy está 🟡 porque `service_role` no recibe `TRUNCATE` (`0004:1887` solo
`select, insert, update`), pero el dueño sí puede.

**A02.** `nucleo.cutover_control` no tiene trigger `_audit` (`0014:8-15`). Un
congelamiento o descongelamiento queda solo en sus columnas, que el mismo `UPDATE`
puede reescribir. Mecanismo: `trg_cutover_control_audit` con `fn_auditoria`.
Prueba: congelar y descongelar ⇒ 2 filas en `nucleo.auditoria` con
`tabla='nucleo.cutover_control'`.

---

## 8. Deuda de prueba de invariantes que **sí** tienen mecanismo

No son "sin mecanismo", pero sin prueba no son garantía (`AGENTS.md` §7). Se
registran para que `qa` los tome. **Ninguna de estas pruebas está ejecutada**: los
archivos existen, pero su `README.md` declara que no se corrieron y por lo tanto no
hay resultados que citar.

| Invariante ya impuesto | Mecanismo | Prueba: estado |
|---|---|---|
| INV-D04 (3 recursos ⇒ 3 reservas) | `0015:183-245` | Escrita: `0015_01_confirmado_ocupa.sql`, `0015_02_concurrencia_rampla.py` (2 conexiones). **No ejecutada** |
| INV-DOC04 (documentos por viaje) | `0015:247-315` | Escrita: `0015_03_confirmado_valida_documentos.sql`. **No ejecutada** |
| INV-R02-01 (A5) | `0016:193-257` | Escrita: `0016_01_licencia_clase_no_a5.sql`. **No ejecutada** |
| INV-R02-02 (licencia vigente) | `0004:1019-1104` | Escrita: `0016_03_licencia_vencida_bloquea.sql`. **No ejecutada** |
| INV-R02-03 (aviso ≤14 días) | servicio + default | Escrita: `0016_02_licencia_por_vencer_no_bloquea.sql`. **No ejecutada** |
| Solapamiento tracto/rampla/chofer en `nucleo` | `0004:744-757` | Parcial (solo rampla, `0015_02`). Falta tracto y chofer con **dos conexiones** |
| Transiciones de viaje | `0004:772-808`, `1511-1547` | Matriz completa origen→destino, incluida `anulado`→todo |
| Documento único vigente | `0004:362-370`, `1704-1741` | Dos inserciones concurrentes del mismo tipo |
| OC no sobreconsumida | `0004:1550-1597` | Dos viajes concurrentes contra el mismo saldo |
| Folio atómico | `0004:498-517` | 20 conexiones generando folio ⇒ 20 distintos, sin huecos |
| Sin POD no se factura | `0009:80-87` | `UPDATE estado='facturado'` sin POD ⇒ `23514` |
| Auditoría append-only | `0004:880-892` | `UPDATE`/`DELETE`/`TRUNCATE` |
| `ck_viaje_recursos_por_estado` | `0004:671-674` | `asignado` sin chofer ⇒ `23514` |

La mutación (retirar el mecanismo y confirmar que la prueba falla) está descrita en
`supabase/tests/mutacion.md` y **tampoco se ejecutó**.

---

## 9. Decisiones que **no** son de `datos` (bloquean invariantes)

| Invariante | Pregunta exacta | A quién |
|---|---|---|
| INV-C05 | ¿`credito_autorizado = 0` significa "sin límite" o "sin crédito"? ¿Se controla al emitir o al despachar? | `negocio-finanzas` + dueño |
| INV-D04 | **Resuelto el 2026-10-29:** la regla es "tiene los tres recursos ⇒ ocupa", sin lista de estados (`0015:26-43`). Queda como decisión de operación: dos borradores **parciales** pueden apuntar al mismo recurso en el papel | dueño / operación |
| INV-F03 | ¿Una factura `emitida` sin pagos puede corregirse por `UPDATE` o exige NC? | contador (`AGENTS.md` §3.15) |
| INV-L02 | Si hay folios SII duplicados en datos reales, ¿cómo se resuelven? | contador |
| INV-L01 | El legacy usa `date`: ¿el solapamiento se evalúa por día completo o por hora? | operación + `arquitectura` |
| INV-T04 | ¿El congelamiento de cutover debe bloquear también scripts y `psql`, o solo el backend? | `arquitectura` (ADR) |

---

## 10. Adenda 2026-10-29 — migraciones `0015`–`0019` escritas en disco

> **Autor:** agente `datos`. **Naturaleza:** adición, no reescritura. Esta sección
> corrige lo que dejó de ser cierto. **Nada de aquí es evidencia de aplicación**:
> el SQL existe en `supabase/migrations/0015_*.sql`…`0019_*.sql` y **no se sabe si
> está aplicado** (🔴). El estado en git es: `0001`–`0003` en `HEAD`, `0004`–`0014`
> *staged*, `0015`–`0019` sin seguimiento (`catalogo-migraciones.md` §2).

### 10.1 Por qué existe esta adenda

El encabezado anterior decía "Ninguno de los mecanismos propuestos está
implementado: son diseño para aprobación". Eso ya no es cierto para el
repositorio: hay cinco migraciones más y cuatro invariantes nuevos con SQL
escrito. Sigue siendo cierto para la base: **no hay evidencia de que se hayan
aplicado**. La tabla de §1 ya está actualizada; esta sección conserva el detalle y
el porqué de cada frontera.

### 10.2 Estado de lo escrito en `0015`–`0019`

> **Convención de IDs:** `INV-R02-NN` no sigue la taxonomía de §0 (una letra de
> categoría). Se usa a propósito: ata el invariante al ID de la regla de negocio
> `R-02` (`AGENTS.md` §11.2, flujo regla → invariante → mecanismo → prueba), para
> que no se pierda la trazabilidad. Si `negocio-finanzas` renombra R-02, estos IDs
> deben seguirlo.

| ID | Invariante | Estado en base | Mecanismo escrito (aplicación 🔴) | Migración |
|---|---|---|---|---|
| INV-D04 | Todo viaje con los tres recursos y `estado <> 'anulado'` tiene 3 reservas activas con la ventana del viaje | impuesto en DDL, **no aplicado** | `trg_viajes_70_reservas` (ya existía) → `fn_viaje_reservas()` reescrita + backfill · `0015:183-245,318-471` | `0015` |
| INV-DOC04 | Todo viaje con los tres recursos y `estado <> 'anulado'` valida documentos de tracto, rampla y chofer | impuesto en DDL, **no aplicado** | `trg_viajes_05_documentos` → `fn_viaje_documentos()` · `0015:247-315` | `0015` |
| INV-R02-01 | Solo la clase A5 es asignable (clase ausente ⇒ viola) | impuesto en DDL, **no aplicado** | `trg_viajes_03_licencia_a5` → `fn_viaje_licencia_a5()` · `0016:193-257` | `0016` |
| INV-R02-02 | La licencia del chofer debe estar vigente hasta el fin efectivo del viaje | impuesto en DDL desde `0004`; `0015` amplía a qué viajes aplica | `validar_documentos_recurso` · `0004:1019-1104` | `0004` + `0015` |
| INV-R02-03 | Licencia a ≤14 días: **aviso**, no bloqueo | solo servicio | ninguno (a propósito); default 14 en `empresas` · `0016:182-186` | `0016` |
| INV-D05 | Una reserva de viaje no se desactiva mientras el viaje ocupe | **ausente** | — | **no está en `0015`** |
| INV-D06 | Sin reservas activas huérfanas con ventana pasada | **ausente** | — | **no está en `0015`** |

**Ninguno de los invariantes comerciales, de gastos, facturación, legacy o tenant
tiene migración.** `0017`, `0018` y `0019` no imponen garantías: `0017` cambia un
default, `0018` carga `licencia_clase='A5'` y `0019` alinea `porcentaje_comision`
(`catalogo-migraciones.md` §1). Que existan esos números **no** significa que
INV-C03…C05, INV-G04…G06, INV-F01…F07, INV-L01…L06 o INV-T01…T04 estén cubiertos.

### 10.3 Correcciones a lo dicho antes

1. **INV-D04 cambió de enunciado.** §1 y §2 lo describen como "estado operativo"
   (lista de estados) y con la disyuntiva (A) reservar en `confirmado` o (B)
   prohibir recursos. El dueño decidió una tercera forma, más simple y más
   estricta: **la condición es "tiene los tres recursos", no una lista de
   estados**, con `anulado` como única excepción (libera). Recursos parciales no
   ocupan ni validan: frontera declarada, no omisión
   (`docs/datos/migraciones/0015-ocupacion-confirmado.md` §3.2).
2. **INV-DOC04 se incorporó a §1.** No estaba en la versión anterior porque el
   agujero documental es distinto del de ocupación: el mismo viaje `confirmado`
   con recursos no validaba documentos (`0004:1124-1126`). Mecanismo propio
   (`0015:247-315`).
3. **INV-D05 e INV-D06 no están cubiertos por `0015`.** La versión anterior de §1
   los asignaba a `0015`; `0015` tal como se escribió **no** los implementa y §1
   ya no los asigna a ninguna migración. Siguen abiertos y necesitan su propia
   migración. Se dejan visibles para que nadie los lea como cerrados.
4. **El número `0016` cambió de contenido.** Estaba reservado para "comercial"
   (INV-C03, INV-C04, INV-C05, INV-DOC03); `0016` es licencia A5. Esos
   invariantes **no** se pierden: siguen en §1 como `ausente`/`parcial` y sin
   migración asignada. La renumeración del plan histórico está en
   `docs/_archivo/planes/plan-migraciones-0015.md` §"Renumeración" — **archivado,
   no citar como estado**; la secuencia real es la de
   `catalogo-migraciones.md` §1.
5. **El SQLSTATE de INV-D04 en solape es `23P01`, no `23514`.** §2 proponía
   `23514` porque imaginaba un `raise` en el trigger. La realidad es mejor: el
   `EXCLUDE` de `0004:744-757` emite `23P01` con nombre de constraint
   (`ex_reserva_tracto|rampla|chofer`). `23514` queda para los rechazos
   explícitos (documentos, clase de licencia, backfill inconsistente).

### 10.4 Escritores cubiertos por los mecanismos nuevos

| Mecanismo | Cubre | **No** cubre |
|---|---|---|
| `fn_viaje_reservas` (`0015`) | Todo `INSERT`/`UPDATE` de `nucleo.viajes`: backend, scripts, seeds, `psql` | `public.viajes` (legacy): RA-02 sigue abierto; `DELETE` de viaje (lo cubre la FK `restrict`, `0004:727-728`, y `fn_viaje_proteccion`) |
| `fn_viaje_documentos` (`0015`) | Todo `INSERT`/`UPDATE` de `nucleo.viajes` con los tres recursos | Recursos parciales (decisión); viajes ya despachados que solo cambian de estado (excepción heredada de `0004:1128-1138`) |
| `fn_viaje_licencia_a5` (`0016`) | Asignación de un chofer: `INSERT` y `UPDATE` que cambia `chofer_id`, más todo `UPDATE` cuando el estado resultante es `asignado` | Cambios de estado sin cambio de chofer (`0016:212-215`); degradación de `choferes.licencia_clase` después de asignar; `public` |

### 10.5 Deuda de prueba actualizada

§8 ya refleja la realidad: hay pruebas **escritas** para INV-D04, INV-DOC04,
INV-R02-01/02/03 (`supabase/tests/README.md`), **sin ejecutar**. La deuda cambia
de "no hay prueba" a "hay prueba, falta correrla y mutarla" (🔴). Siguen sin
prueba: solapamiento de **tracto** y **chofer** con dos conexiones, transiciones
completas, folio atómico, OC concurrente, POD, auditoría append-only y **todos los
invariantes que siguen ausentes en §1**.
