# Registro de invariantes — estado real por invariante

> **Pregunta que responde:** ¿qué invariante existe, qué lo impone y qué sigue sin garantía?
> **Dueño:** agente `datos` · **Verificado:** 2026-10-29 (cuerpo) · 2026-10-30 (adenda §11, catálogo de `tei_test`) · 2026-11-01 (adenda §13, retiro de `public`) · **Método:** lectura de DDL + `psql` (solo `0020`/`0021`)
> **Caduca si:** se agrega o edita una migración, o se ejecutan pruebas contra una base real.
> **Re-verificar con:** `ls supabase/migrations/` + `grep -n "create trigger\|create or replace function"`.

> **Adenda 2026-10-30.** El módulo agente WhatsApp (`0021`) se registra en §11 con
> IDs `INV-AW01`…`INV-AW16` (alias `AW-01`…`AW-16`, los que cita la migración
> aplicada). Para esas 16 filas **sí** hay aplicación verificada, y `0021` está
> aplicada y probada en el clon desechable `tei_test`; el resto del registro sigue
> con la advertencia de §0 ("`impuesto (DDL)`" = escrito, no en vigor). El contrato
> completo (mecanismo, SQLSTATE, escritores, defectos) está en
> `docs/datos/agente-esquema.md`.

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
| INV-T01 | Ningún rol de aplicación lee o escribe filas de otra empresa | **diseñado y probado en `tei_test`; no aplicado en la app** | `0020`: rol `tei_app` (NOBYPASSRLS) + 35 políticas + `FORCE` + `app.empresa_id` por transacción (31 tablas) · probado en el clon 2026-10-30 | 42501 | `docs/datos/rls-multiempresa.md` §7; `supabase/tests/0020_*`; RA-03 abierto hasta cambiar el rol del backend |
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

> **Actualización 2026-10-30.** El mecanismo está escrito y probado: migración
> `0020_rls_multiempresa.sql`, rol **`tei_app`** (el nombre `nucleo_app` de este
> párrafo era un borrador), GUC **`app.empresa_id`**. Aplicado y verificado con
> dos conexiones **solo en el clon `tei_test`**; en la base de la app sigue
> ausente y es inerte mientras el backend conecte como `postgres`. Diseño,
> decisión y evidencia: `docs/datos/rls-multiempresa.md`. El texto de abajo se
> conserva como registro de lo que faltaba.

**SQLSTATE.** `42501` (`insufficient_privilege`) — no es un conflicto de negocio;
el backend debe devolver **403/404 sin filtrar existencia**, no 500. Handoff.

**Prueba.** Rol `tei_app`, contexto empresa A: `SELECT * FROM
nucleo.viajes WHERE id = <viaje de B>` ⇒ 0 filas; `INSERT` con `empresa_id = B`
⇒ `42501` (o `WITH CHECK` violation). Mutación (probada el 2026-10-30):
`ALTER ROLE tei_app BYPASSRLS` ⇒ aparecen los viajes de B; `ALTER POLICY …
USING (true)` ⇒ aparecen los clientes de B. **`NO FORCE` no sirve como mutación**:
para un rol que no es dueño, FORCE es irrelevante (verificado en
`docs/datos/rls-multiempresa.md` §7.5).

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

---

## 11. Adenda 2026-10-30 — módulo agente WhatsApp (`0021`)

> **Autor:** agente `datos`. **Naturaleza:** sección nueva; no reescribe §0–§10.
> **Aplicación:** `0021_agente_whatsapp.sql` está aplicada **solo** en el clon
> desechable `tei_test` (verificado por catálogo el 2026-10-30). En la base de la
> app no está verificada (🔴). Por eso, en esta sección `impuesto (DDL)` significa
> además **"aplicado y leído del catálogo de `tei_test`"**, no solo "escrito".
> **Contrato completo** (precondiciones, inventario, decisiones, defectos,
> verificación post): `docs/datos/agente-esquema.md`.

### 11.1 Reconciliación de IDs

La migración aplicada cita `AW-01`…`AW-16` (`0021:87-88`) y **no se puede
editar**. Para no duplicar invariantes con dos IDs:

- **Canónico:** `INV-AW01`…`INV-AW16` (categoría `AW`; precedente: `INV-DOC04`,
  `INV-R02-NN`). Es la forma que se cita en `docs/datos/**`.
- **Alias estable:** `AW-NN`, uno a uno con el canónico. Se mantiene en el `.sql`
  aplicado y en los comentarios de `supabase/tests/0021_*`; no se renombra nada
  en la base.
- **Sin colisión:** no existía ningún `INV-AW*` antes de esta sección
  (`git grep -o 'INV-AW[0-9]*' HEAD -- docs/` → 0; y hoy solo aparece en
  `agente-esquema.md` e `invariantes.md`).
- **Citación:** `INV-AWNN` en documentos; `AW-NN` es aceptable en código/pruebas y
  significa lo mismo.

### 11.2 Registro

| ID | Alias | Invariante (una frase) | Estado en base | Mecanismo | SQLSTATE | Prueba |
|---|---|---|---|---|---|---|
| INV-AW01 | AW-01 | Un `wa_message_id` entra una sola vez en toda la base; todo entrante lo trae | impuesto (DDL) + aplicado | `uq_mensaje_wa_message_id` parcial · `0021:346-347`; `ck_mensaje_entrante_idempotente` · `:338-340` | 23505 / 23514 | `0021_01` C7A/C7C/C7E ✅; concurrencia (2 conexiones) **en curso `0021_02`** |
| INV-AW02 | AW-02 | Un número activo resuelve a un solo contacto en todo el sistema; desactivar libera | impuesto (DDL) + aplicado | `uq_contactos_telefono_activo (telefono) where activo` · `:222-223` | 23505 | `0021_01` C3A–C3F ✅ (incluye cross-tenant C3F, reactivación C3E) |
| INV-AW03 | AW-03 | Contacto coherente: E.164, nombre, una entidad por rol, OTP verificado con fecha | impuesto (DDL) + aplicado | CHECKs `:208-215` | 23514 | `0021_01` C1, C2A–C2D, C3A, C4 ✅ |
| INV-AW04 | AW-04 | Un mensaje solo pertenece a una conversación de su contacto y su empresa | impuesto (DDL) + aplicado | `fn_mensaje_validar` `:361-379` + trigger `:762-763`; FK compuesta `:334-335` | 23514 / 23503 | `0021_01` C8A ✅ (23514); otra empresa ⇒ 23503 (sonda propia). `UPDATE` de `contacto_id`: **sin cobertura** |
| INV-AW05 | AW-05 | A lo sumo una conversación activa por contacto; cerrada exige `cerrada_en` | impuesto (DDL) + aplicado | `uq_conversacion_activa` `:298-299`; `ck_conversacion_cierre` `:292` | 23505 / 23514 | `0021_01` C6A–C6E ✅; concurrencia **en curso `0021_02`** |
| INV-AW06 | AW-06 | Una fila ACL por (contacto, componente, variable-NULL); nada en blanco | impuesto (DDL) + aplicado | `uq_permisos_contacto_valor` `:262-263`; CHECKs `:258-259` | 23505 / 23514 | `0021_01` C5A–C5F ✅ |
| INV-AW07 | AW-07 | Sin fila en `permisos_contacto` no hay acceso (deny-by-default) | **solo servicio** (la base no puede imponer una ausencia) | ninguno; lo resuelve el gate O2.2 · `0021:267-270` | n/a (403/404) | **sin cobertura de base**; prueba prevista **O2.2** |
| INV-AW08 | AW-08 | Ninguna fila del módulo referencia una entidad de otra empresa | impuesto (DDL) + aplicado | FK compuestas `(empresa_id,id)` `:202-207,256-257,290-291,334-337,415-420,512-519,582-585,693-698` + `uq_usuarios_empresa_empresa` `:170-171` | 23503 | parcial ✅ C5D/C5F/C11B + sonda de mensajes; solicitudes/hoja_ruta/auditoría **en curso `0021_02`/`0021_04`** |
| INV-AW09 | AW-09 | Toda solicitud tiene exactamente un solicitante humano (contacto xor usuario) | impuesto (DDL) + aplicado | `ck_solicitud_solicitante` `:421-423` | 23514 | `0021_01` C9C/C9D ✅ |
| INV-AW10 | AW-10 | Estado terminal documentado y definitivo: no se reabre ni reclasifica | impuesto (DDL) + aplicado | CHECKs `:424-432` + `fn_solicitud_transicion` `:458-483` + trigger `:771-772` | 23514 | `0021_01` C9E–C9H, C9J ✅; dos aprobadores **en curso `0021_02`** |
| INV-AW11 | AW-11 | Rechazar solo registra la decisión: no muta el destino | **parcial** (la base exige motivo+fecha; el "no mutar" es del servicio O2.5) | `ck_solicitud_rechazada` `:427-429` | 23514 | **sin cobertura** (ningún caso de `0021_01` rechaza). Previsto `0021_02` + O2.5 |
| INV-AW12 | AW-12 | La misma `clave_idempotencia` no crea dos solicitudes en una empresa | impuesto (DDL) + aplicado | `uq_solicitud_idempotencia` `:437-438` | 23505 | `0021_01` C9B ✅; doble clic concurrente **en curso `0021_02`** |
| INV-AW13 | AW-13 | Hoja de ruta con estado coherente y a lo sumo una carga confirmada por solicitud | impuesto (DDL) + aplicado | CHECKs `:520-522`; `uq_hoja_ruta_carga_por_solicitud` `:528-529`; máquina de estados + `payload` inmutable `0022:349-392` | 23514 / 23505 | `0021_01` C10A–C10D ✅; sondas `0022` ✅ (C10E quedó obsoleta, `agente-esquema.md` §8.1) |
| INV-AW14 | AW-14 | Código comercial `PREFIJO-00000`, único por (empresa, cliente), generado sin carrera | impuesto (DDL) + aplicado | CHECK `:551-553`; `uq_viajes_id_comercial` `:555-557`; funciones `:603-636` y `:640-670`; inmutabilidad `0022:315-341`; contador monótono `0022:284-307`; tope de 5 dígitos `0022:401-444` | 23514 / 23505 | `0021_01` C11A–C11G ✅; `0021_02` C1/C1b ✅ (8 conexiones); sondas `0022` ✅. **D4 sigue abierto** (prefijo por cliente) |
| INV-AW15 | AW-15 | Auditoría de consultas append-only, incluso para el dueño; `tei_app` sin UPDATE/DELETE | impuesto (DDL) + aplicado | triggers `:729-735`; `revoke`/`grant` `:863-864` | 23514 / 42501 | `0021_01` C12A–C12D ✅; `DELETE` como `tei_app` ⇒ 42501 (sonda propia) |
| INV-AW16 | AW-16 | Cada fila del módulo es invisible e inescribible fuera de `app.empresa_id`; sin contexto, cero filas | impuesto (DDL) + aplicado | políticas `:799-825`; `ENABLE`+`FORCE` `:833-850`; GRANTs `:855-868`; `nucleo.ctx_empresa()` (`0020`) | 42501 / 0 filas | parcial ✅ sondas propias (sin contexto 0 filas y `INSERT` 42501; cross-tenant 42501); matriz con rol real **en curso `0021_03`** |

### 11.3 Deuda de prueba del bloque

`0021_01_smoke.sql` corre **secuencial y con rol `BYPASSRLS`**: prueba
constraints, triggers y funciones, **no** concurrencia ni RLS. Estado real:

| Prueba | Estado 2026-10-30 |
|---|---|
| `0021_01_smoke.sql` | **escrita y ejecutada** (14/14 OK, corrida propia); `BEGIN/ROLLBACK` por caso, sin residuo |
| `0021_02` (concurrencia, 2 conexiones) | **no existe todavía** (prevista, `qa` O1.2) |
| `0021_03` (RLS con rol `tei_app`) | **no existe todavía** (prevista, `qa` O1.2) |
| `0021_04` (mutación) | **no existe todavía** (prevista, `qa` O1.2) |
| `0021_99_rollback.sql` | **no existía** aunque la migración lo cita (`0021:79`) ⇒ defecto D1 |

> **Adenda 2026-10-30 (O1.3; no reescribe la foto anterior).** Las tres suites
> ya existen y corrieron verdes (`0021_02` con 8+2+2 conexiones reales,
> `0021_03` con `tei_app`, `0021_04` M1–M9), y `0021_99`/`0022_99` existen
> (**untracked**) y se ejecutaron en el ciclo rollback → re-aplicación
> (`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md:94-403`).

Las filas de la tabla conservan la foto previa a O1.3; las suites ejecutadas se
citan con su salida real en el informe enlazado.

### 11.4 Escritores cubiertos

| Mecanismo | Cubre | **No** cubre |
|---|---|---|
| Constraints/triggers de `0021` | Todo escritor sobre las 8 tablas y sobre `viajes.id_comercial_flete`: backend futuro, scripts, seeds, `psql`, `tei_app` cuando se cablee | `public` (legacy no escribe `nucleo`); DDL (un superusuario puede deshabilitar un trigger) |
| AW-16 (RLS) | Solo el rol `tei_app` (NOBYPASSRLS) | `postgres` y `supabase_admin` (BYPASSRLS/dueños). 🟡 **No verificado** qué rol usa hoy la app: el backend prefiere `NUCLEO_DATABASE_URL` (`tei_app`) y cae a `DATABASE_URL` con el marcador `RLS inerte` (`backend/app/core/database.py:24-32,110-135`) — RA-03 |
| AW-07 / AW-11 | Nada en la base: dependen del gate (O2.2) y del servicio de rechazo (O2.5) | Cualquier escritor directo por `psql`/script que no pase por el backend |

### 11.5 Defectos del bloque: estado (D2/D3/D5/D9 cerrados por `0022`)

`0021` está aplicada y sus defectos **no se editan**: se corrigen con una
migración nueva. `0022` (2026-10-30, aplicada solo en `tei_test`) cierra **D2,
D3, D5 y D9**; D4, D6 y D8 siguen abiertos. D1 quedó resuelto en el árbol de
trabajo (scripts `0021_99`/`0022_99`, untracked, ejecutados) y D7 quedó
**probado en clon (2026-10-30)**; D10 se registra como riesgo de proceso local.
Detalle, mecanismo y evidencia medida en `docs/datos/agente-esquema.md` §8,
§8.1 y §8.2.

| ID | Defecto | Invariante afectado | Estado |
|---|---|---|---|
| D1 | `supabase/tests/0021_99_rollback.sql` no existía aunque la migración lo cita (`0021:79`) | rollback de todo el bloque | 🟢 script creado y ejecutado en O1.3 (2026-10-30); **untracked**, falta versionarlo. `0022_99` ídem |
| D2 | `viajes.id_comercial_flete` se puede **reasignar** contra el `COMMENT` (`0021:566-570`) | INV-AW14 | 🟢 cerrado por `0022:315-341` |
| D3 | El contador puede **retroceder** por `UPDATE` directo (`tei_app` tiene `UPDATE`) | INV-AW14 (parcial: la `UNIQUE` evita el duplicado asignado) | 🟢 cerrado por `0022:284-307` |
| D4 | La resolución `(empresa, código)` **no es única**: dos clientes pueden compartir prefijo | INV-AW14 / tool de lectura §16.2 | 🔴 abierto: decisión de negocio (D-16 no la fijó) |
| D5 | `hoja_ruta` **no tiene máquina de estados** (`rechazado → cargado` y `cargado → propuesto` aceptados) | INV-AW13 | 🟢 cerrado por `0022:349-392` |
| D6 | "Rechazo solo-logra" no es garantía de base | INV-AW11 | 🔴 abierto (backend O2.5) |
| D7 | `0021` se editó tras una primera aplicación en `tei_test` (`0021:844-845`): aceptable en clon, **prohibido** en cualquier otra base | proceso forward-only | 🟡 probado en clon (2026-10-30: rollback + re-aplicación + 4 suites verdes); regla vigente: no editar una migración aplicada |
| D8 | `wa_message_id` único global permite "reservar" un id ajeno (DoS entre tenants, baja probabilidad) | INV-AW01 | 🟡 aceptado y documentado; sin cambio de índice |
| D9 | Tope duro de 99.999 códigos por (empresa, cliente); al llegar a 100.000 `lpad` trunca y **reutiliza** `SQM-10000` | INV-AW14 | 🟢 cerrado por `0022:401-444` |

---

## 12. Adenda 2026-10-31 — Ola B del retiro legacy (`0024`–`0026`)

> **Autor:** agente `datos`. **Naturaleza:** sección nueva; no reescribe §0–§11.
> **Aplicación:** `0024`, `0025` y `0026` están **aplicadas y probadas** en la
> base local (`postgres`) y en el clon desechable `tei_test` (2026-10-31). Por
> eso aquí `impuesto (DDL)` significa además **"leído del catálogo"**, no solo
> "escrito en un archivo".
> **Diseño completo** (inventario, precondiciones, impacto, rollback, salidas):
> `docs/datos/retiro-legacy-modelo.md`.
> **Regla de negocio de origen:** `docs/negocio/retiro-legacy-modulos.md` §3, §5
> y §6 (módulos sin equivalente en el núcleo).

### 12.1 Registro

| ID | Invariante (una frase) | Estado en base | Mecanismo | SQLSTATE | Prueba |
|---|---|---|---|---|---|
| INV-MANT01 | El costo de una mantención no es negativo | impuesto (DDL) | `ck_mantenimiento_costo` · `0024` | 23514 | `0024_01` 1F ✅ |
| INV-MANT02 | `km >= 0` y `proximo = ultimo_km + intervalo_km` con el intervalo vigente **al registrar** | impuesto (DDL) | `ck_mantenimiento_km` + `intervalo_km_snapshot` + `v_mantenimiento_estado` · `0024` | 23514 | `0024_01` 1B/1C ✅ |
| INV-MANT03 | Editar o desactivar una pauta no reescribe el histórico | impuesto (DDL) | `fn_mantenimiento_validar` congela el snapshot · `0024` | 23514 | `0024_01` 1G ✅ (CN-08 borde) |
| INV-MANT04 | Un registro apunta a un recurso y una pauta de su misma empresa y del tipo correcto | impuesto (DDL) | 3 FKs compuestas + `fn_mantenimiento_validar` · `0024` | 23503 / 23514 | `0024_01` 1D/1F ✅ |
| INV-MANT05 | El semáforo tiene una sola definición y no se almacena | impuesto (DDL) | `v_mantenimiento_estado` con `security_invoker` · `0024` | — | `0024_01` 1C ✅ |
| INV-MANT06 | Toda fila de mantenimiento es invisible/inescribible fuera de `app.empresa_id` | impuesto (DDL) | política `tenant_empresa` + `FORCE` + GRANT · `0024` | 42501 / 0 filas | `0026_02` A/B/C ✅ (rol `tei_app`) |
| INV-LIQ01 | `total_liquido = sueldo_base + comisión + bonos − descuentos − anticipos` | impuesto (DDL) | columna `generated always as … stored` · `0025` | 428C9 al escribirla | `0025_01` 1B ✅ (CN-03) |
| INV-LIQ02 | Una liquidación emitida no cambia montos, chofer ni mes, y no se borra | impuesto (DDL) | `fn_liquidacion_estado` + `fn_nomina_no_borrar` · `0025` | 23514 | `0025_01` 1D + `0025_02` C2 (2 conexiones) ✅ |
| INV-LIQ03 | Un anticipo/ajuste se imputa a lo sumo una vez y al mes declarado | impuesto (DDL) | `fn_imputacion_validar` + `liquidacion_id` inmutable + FK compuesta · `0025` | 23514 | `0025_01` 1E + `0025_02` C1 ✅ |
| INV-LIQ04 | Anticipos y ajustes no se borran: se anulan con motivo | impuesto (DDL) | `fn_nomina_no_borrar` + `CHECK` de anulación con sello · `0025` | 23514 | `0025_01` 1F/1G ✅ |
| INV-LIQ05 | Un solo criterio de redondeo monetario (HALF_UP) | impuesto (DDL) | `nucleo.redondear_half_up()` (`round(numeric,int)`) · `0025` | 22023 (rango) | `0025_01` 1C ✅ (CN-04) |
| INV-LIQ06 | La nómina es invisible/inescribible fuera de la empresa | impuesto (DDL) | política + `FORCE` + GRANT · `0025` | 42501 / 0 filas | `0026_02` A/B/C ✅ |
| INV-CFG01 | A lo sumo una fila vigente por (empresa, clave) | impuesto (DDL) | `uq_config_empresa_clave_vigente` + `ex_config_vigencia` · `0026` | 23505 / 23P01 | `0026_01` 1C ✅ |
| INV-CFG02 | Las vigencias de una clave no se solapan ni retroceden | impuesto (DDL) | `ex_config_vigencia` + `ck_config_vigencia` · `0026` | 23P01 / 23514 | `0026_01` 1G ✅ |
| INV-CFG03 | El valor de una fila cerrada no se edita y el historial no se borra | impuesto (DDL) | `fn_config_empresa_inmutable` + `fn_config_empresa_no_borrar` · `0026` | 23514 | `0026_01` 1D/1F ✅ |
| INV-CFG04 | `iva_porcentaje` es numérico y está en `[0, 100]` | impuesto (DDL) | `ck_config_iva_porcentaje` · `0026` | 23514 | `0026_01` 1H ✅ |
| INV-CFG05 | La configuración (y su lectura canónica) respeta el tenant | impuesto (DDL) | política + `FORCE` + `config_vigente` security invoker · `0026` | 42501 / 0 filas | `0026_02` B ✅ (`config_vigente` ajena ⇒ NULL) |

### 12.2 Escritores cubiertos y límites

| Mecanismo | Cubre | **No** cubre |
|---|---|---|
| Constraints/triggers de `0024`–`0026` | backend futuro, scripts, seeds, `psql`, `tei_app` cableado | `public` (el legacy no escribe `nucleo`); un superusuario que deshabilite un trigger |
| INV-MANT06 / INV-LIQ06 / INV-CFG05 (RLS) | solo el rol `tei_app` (NOBYPASSRLS), probado | `postgres`/`supabase_admin` (BYPASSRLS/dueños); el rol efectivo del backend sigue sin verificarse (RA-03) |
| INV-LIQ01–03 | toda escritura sobre las tablas de nómina | que `bonos/descuentos/anticipos` de la cabecera sumen lo mismo que las filas hijas: es snapshot de emisión y depende de `D-19`/`P-10` (§7.2 del diseño) |
| INV-MANT05 | cualquier lector del semáforo | el umbral por empresa (`alerta_km_mantenimiento`) llega cuando el backend lea `configuracion_empresa`; hoy la vista usa 5.000 km |

### 12.3 Deuda de prueba del bloque

| Prueba | Estado 2026-10-31 |
|---|---|
| `0024_01_mantenimiento.sql` | **ejecutada**, 16 `OK` + `ROLLBACK` (0 filas) |
| `0025_01_liquidaciones.sql` | **ejecutada**, 18 `OK` + `ROLLBACK` |
| `0026_01_configuracion.sql` | **ejecutada**, 15 `OK` + `ROLLBACK` |
| `0026_02_rls_tei_app.sql` | **ejecutada** como `tei_app` sin BYPASSRLS, 11 `OK` |
| `0025_02_concurrencia_anticipo.py` | **ejecutada**, C1 (2 conexiones, 1 imputación) y C2 (emisión vs edición) |
| `002[456]_99_rollback.sql` | **ejecutados**: rollback → 40 tablas/45 políticas → re-aplicación → 46/51 |
| Mutación | **manual y ejecutada**: retirar 4 mecanismos hace fallar la suite correspondiente; restaurados |
| `make unit` / `make test` | **135** y **388** pruebas en verde tras aplicar |

---

## 13. Adenda 2026-11-01 — retiro de `public` (`0028`, Ola E / ADR-0002 E.5)

Aplicado en local el 2026-11-01 (`supabase migration up --local` y, de nuevo, por
`make db-reset`). Contrato completo y conteos en `docs/datos/retiro-public.md`.

| ID | Invariante | Estado en base | Mecanismo | SQLSTATE | Prueba |
|---|---|---|---|---|---|
| INV-LEG01 | `public` no contiene tablas, funciones ni tipos propios del ERP | **impuesto (DDL, aplicado)** | 17 `DROP TABLE … CASCADE`, 8 `DROP TYPE`, 2 `DROP FUNCTION` + verificación V1–V3 dentro de la transacción · `0028` | n/a (estado, no error de escritura) | `0028_01` A ✅ + mutación `0028_02` ✅ |
| INV-LEG02 | Un alta en Supabase Auth no escribe el perfil en ningún esquema legacy | **impuesto (DDL)** | `DROP TRIGGER on_auth_user_created ON auth.users` + `DROP FUNCTION public.handle_new_user()` · `0028` | n/a | `0028_01` B ✅; identidad desde JWT en `test_f2_ola_e1_identidad.py` ✅ |
| INV-LEG03 | El rol de la aplicación no puede usar el esquema `public` | **impuesto (DDL)** | `REVOKE USAGE ON SCHEMA public FROM public` + `GRANT` explícito a los roles de Supabase (no a `tei_app`) · `0028` | `42501` | `0028_01` D ✅ (probado con `tei_app`, no con `postgres`) |
| INV-LEG04 | Las garantías del núcleo apoyadas en `btree_gist` sobreviven al retiro | **impuesto (DDL)** | extensión conservada en `public` + los 4 `EXCLUDE` verificados en V6 · `0028` | `23P01` (sigue) | `0028_01` C/E ✅ (`tei_app` inserta en `configuracion_empresa` con `EXCLUDE` gist) |

**Escritores cubiertos:** `tei_app` (denegado por `42501`), backend, seeds y
scripts (no hay objeto al que apuntar: `42P01`). **No cubre** a `postgres` /
`supabase_admin`: son dueños y pueden volver a crear objetos en `public`; el
invariante "`public` vacío" no es una restricción de PostgreSQL, se detecta con
`0028_01` (y la mutación demuestra que lo detecta).

**Nota de solapamiento:** los invariantes `INV-L01`…`INV-L06` (§6) describían
reglas del legacy `public`. **Quedan sin objeto**: no existen las tablas que las
imponían. No se borran del registro (historia), pero su estado real pasa a
"n/a — tabla retirada".
