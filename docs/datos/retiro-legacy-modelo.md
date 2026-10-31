# Modelo de datos de la Ola B del retiro legacy — mantenimiento, nómina y configuración

> **Pregunta que responde:** ¿qué tablas, constraints, políticas y triggers se
> crearon en `nucleo` para los 3 módulos legacy sin equivalente, con qué
> garantías, y cómo se verificó?
> **Dueño:** agente `datos` · **Fecha:** 2026-10-31 · **Riesgo:** ALTO (dinero,
> datos laborales, tenant)
> **Método:** diseño a partir de `docs/negocio/retiro-legacy-modulos.md`
> (§3, §5, §6), del DDL legacy (`0001_esquema_base.sql:151-215`) y del patrón de
> `nucleo` (`0004`, `0020`, `0021`, `0023`). **Aplicado y probado en la base
> local** (`postgres`, datos ficticios) y en el clon `tei_test` con
> `docker exec … psql -U supabase_admin`. Salidas reales en §5.
> **Caduca si:** se agrega/edita una migración `0024`–`0026`, se cambia el rol
> de conexión del backend o se responde una `D-19`/`P-01`/`P-09`/`P-10`/`P-11`.
> **Re-verificar con:**
> `docker exec supabase_db_TRANSTEI psql -U supabase_admin -d postgres -Atc "select tablename from pg_tables where schemaname='nucleo' order by 1"`
> y las suites de §5.

---

## 0. Resumen

| Migración | Módulo | Objetos | Filas al aplicar |
|---|---|---|---|
| `0024_mantenimiento_nucleo.sql` | Mantenimiento (pautas + registros + semáforo) | 2 tablas, 1 vista, 3 funciones, 9 triggers, 2 políticas | 0 |
| `0025_liquidaciones_nucleo.sql` | Liquidaciones, anticipos y ajustes | 3 tablas, 4 funciones, 15 triggers, 3 políticas | 0 |
| `0026_configuracion_empresa.sql` | Configuración por empresa con vigencia | 1 tabla, 3 funciones, 5 triggers, 1 política | 1 por empresa (`iva_porcentaje = 19`) |

**Totales en la base local (`postgres`):** 40 → **46 tablas** en `nucleo`,
45 → **51 políticas**, **29 triggers** nuevos, **6 tablas** con `ENABLE`+`FORCE`
y política `tenant_empresa`, GRANT `select,insert,update` a `tei_app` (sin
`delete`) en las 6 y `select` en la vista.

**Lo que estas migraciones no hacen:** no migran filas del legacy (Ola D), no
tocan `public`, no encienden nada en el backend y **no modelan** el crédito
fiscal de IVA ni la composición legal de la remuneración (§7).

---

## 1. Inventario

### 1.1 `nucleo.pautas_mantenimiento` (`0024`)

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `uuid` PK | `gen_random_uuid()` |
| `empresa_id` | `uuid not null` | FK a `nucleo.empresas` |
| `recurso_tipo` | `nucleo.tipo_recurso` | `CHECK in ('tracto','rampla')` |
| `item` | `text not null` | `CHECK btrim <> ''` |
| `intervalo_km` | `integer not null` | `> 0` (paridad legacy) |
| `intervalo_meses` | `integer` | `> 0` si existe |
| `alerta_km` | `integer` | `>= 0`; `NULL` = umbral de la empresa / 5.000 |
| `orden`, `activo`, auditoría estándar | | `activo` = baja lógica |

`UNIQUE (empresa_id, id)` (habilita FKs compuestas) y **UNIQUE parcial**
`(empresa_id, recurso_tipo, lower(item)) WHERE activo` (`uq_pautas_empresa_tipo_item_activa`):
editar un ítem se hace desactivando y creando otro, sin reescribir el pasado.

### 1.2 `nucleo.mantenimientos` (`0024`)

`tracto_id` xor `rampla_id` (`ck_mantenimiento_un_recurso`), `pauta_id`,
`fecha date`, `km numeric(12,1) >= 0`, `costo numeric(14,2) >= 0`,
`estado ∈ {realizado, anulado}` + `motivo_anulacion`/`anulada_en`/`anulada_por`,
`observaciones`, `respaldo_url` (relativa, sin `..`, sin esquema, ≤ 512) y el
**snapshot** `intervalo_km_snapshot` / `intervalo_meses_snapshot` /
`alerta_km_snapshot`.

Fks compuestas `(empresa_id, pauta_id)`, `(empresa_id, tracto_id)`,
`(empresa_id, rampla_id)` ⇒ un registro no puede apuntar a un recurso de otra
empresa ni del tipo equivocado (el tipo lo valida además
`fn_mantenimiento_validar`).

Triggers: `validar` (snapshot inmutable, tipo coherente, terminalidad),
`no_borrar`, `odometro` (AFTER INSERT sube `tractos.km_actual` al km registrado,
nunca lo baja), `touch`, `version`, `audit`.

### 1.3 `nucleo.v_mantenimiento_estado` (`0024`)

Vista `security_invoker` (sin eso se saltaría el RLS de las tablas base) que
cruza recursos activos × pautas activas × último registro **realizado** y
calcula `proximo_km = ultimo_km + intervalo_km`, `proxima_fecha`, `restante_km` y
`estado ∈ {sin_registro, sin_odometro, pendiente, por_vencer, ok}`.
**El semáforo no se almacena**: guardarlo lo volvería obsoleto al moverse el
odómetro (defecto CN-08 borde).

### 1.4 `nucleo.liquidaciones` (`0025`)

`chofer_id`, `mes text` (`^[0-9]{4}-(0[1-9]|1[0-2])$`), `sueldo_base`,
`comision`, `bonos`, `descuentos`, `anticipos` (`numeric(14,2)`, `>= 0`) y
**`total_liquido` generado** `= sueldo_base + comision + bonos - descuentos -
anticipos` (misma técnica que `nucleo.facturas_nucleo.total`).
`UNIQUE (empresa_id, chofer_id, mes)` y `UNIQUE (empresa_id, id)`.
`estado ∈ {borrador, emitida, anulada}` con sellos `emitida_en/por`,
`anulada_en/por` y `motivo_anulacion`.

### 1.5 `nucleo.anticipos_chofer` y `nucleo.ajustes_liquidacion` (`0025`)

Anticipos: `monto > 0`, `mes_imputacion` `YYYY-MM`, `estado ∈ {pendiente,
descontado, anulado}`, `liquidacion_id` (FK compuesta a la liquidación).
Ajustes: `tipo ∈ {bono, descuento}`, `concepto` no vacío, `monto >= 0` (paridad
con `0001:168`), `estado ∈ {vigente, anulado}`, `liquidacion_id` opcional.
Ambos: `no_borrar` + anulación con motivo y sello.

### 1.6 `nucleo.configuracion_empresa` (`0026`)

`(empresa_id, clave, valor jsonb, vigente_desde, vigente_hasta)`, con
`UNIQUE parcial (empresa_id, clave) WHERE vigente_hasta IS NULL` y **EXCLUDE
gist** `(empresa_id =, clave =, tstzrange(vigente_desde, vigente_hasta, '[)') &&)`
para que las vigencias no se solapen. `iva_porcentaje` se acota a `[0,100]` con
un `CHECK` que primero valida la forma numérica (para no filtrar un `22P02`).
`nucleo.config_vigente(uuid, text)` es la lectura canónica (security invoker).
Seed de paridad: `iva_porcentaje = 19` por empresa.

---

## 2. Invariantes

| ID | Invariante | Mecanismo | Dónde | SQLSTATE | Prueba |
|---|---|---|---|---|---|
| INV-MANT01 | El costo de una mantención no es negativo | `ck_mantenimiento_costo` | `0024` | 23514 | `0024_01` 1F |
| INV-MANT02 | `km >= 0` y `proximo = ultimo + intervalo` con el intervalo vigente al registrar | `ck_mantenimiento_km` + snapshot + vista | `0024` | 23514 | `0024_01` 1B/1C |
| INV-MANT03 | Editar la pauta no reescribe el histórico | snapshot congelado por `fn_mantenimiento_validar` | `0024` | 23514 | `0024_01` 1G |
| INV-MANT04 | El registro y la pauta son de la misma empresa y del mismo tipo de recurso | FKs compuestas + `fn_mantenimiento_validar` | `0024` | 23503 / 23514 | `0024_01` 1D/1F |
| INV-MANT05 | Un solo cálculo del semáforo y no se almacena | vista `v_mantenimiento_estado` | `0024` | — | `0024_01` 1C |
| INV-MANT06 | Cada fila es invisible/inescribible fuera de `app.empresa_id` | política `tenant_empresa` + `FORCE` + GRANT | `0024` | 42501 / 0 filas | `0026_02` A/B/C |
| INV-LIQ01 | `total_liquido = base + comisión + bonos − descuentos − anticipos` | columna generada | `0025` | 428C9 al escribirla | `0025_01` 1B |
| INV-LIQ02 | Una liquidación emitida no cambia montos/chofer/mes ni se borra | `fn_liquidacion_estado` + `fn_nomina_no_borrar` | `0025` | 23514 | `0025_01` 1D, `0025_02` C2 |
| INV-LIQ03 | Un anticipo/ajuste se imputa a lo sumo una vez y al mes declarado | `fn_imputacion_validar` + `liquidacion_id` único por fila | `0025` | 23514 | `0025_01` 1E, `0025_02` C1 |
| INV-LIQ04 | Anticipos y ajustes no se borran: se anulan con motivo | `fn_nomina_no_borrar` + `CHECK` de anulación | `0025` | 23514 | `0025_01` 1F/1G |
| INV-LIQ05 | Un solo criterio de redondeo monetario (HALF_UP) | `nucleo.redondear_half_up()` | `0025` | 22023 (rango) | `0025_01` 1C (CN-04) |
| INV-LIQ06 | Aislamiento por empresa de la nómina | política + `FORCE` + GRANT | `0025` | 42501 / 0 filas | `0026_02` A/B/C |
| INV-CFG01 | A lo sumo una fila vigente por (empresa, clave) | UNIQUE parcial + EXCLUDE | `0026` | 23505 / 23P01 | `0026_01` 1C |
| INV-CFG02 | Las vigencias no se solapan ni retroceden | EXCLUDE gist + `ck_config_vigencia` | `0026` | 23P01 / 23514 | `0026_01` 1G |
| INV-CFG03 | El valor de una fila cerrada no se edita ni se borra | `fn_config_empresa_inmutable` + `no_borrar` | `0026` | 23514 | `0026_01` 1D/1F |
| INV-CFG04 | `iva_porcentaje` es numérico y está en `[0,100]` | `ck_config_iva_porcentaje` | `0026` | 23514 | `0026_01` 1H |
| INV-CFG05 | Aislamiento por empresa de la configuración (incluida la lectura) | política + `FORCE` + `config_vigente` invoker | `0026` | 42501 / 0 filas | `0026_02` B |

**Escritores cubiertos:** todos los que escriban en las 6 tablas (backend
futuro, scripts, seeds, `psql`, `tei_app`). **No cubiertos:** `public` (el legacy
no escribe `nucleo`); un superusuario que deshabilite un trigger; el snapshot de
la cabecera frente a la suma de las filas hijas (§7.3).

---

## 3. Precondiciones ejecutadas

Se corrieron **dentro** de la transacción de cada migración (abortan con `23514`
si fallan; no reparan nada). Valores medidos el 2026-10-31:

| Migración | Precondición | Medición |
|---|---|---|
| `0024` | P1 tablas no existen | 0 |
| `0024` | P2 `ctx_empresa`, rol `tei_app`, USAGE, `empresas` | 1/1/true/1 |
| `0024` | P3 `UNIQUE (empresa_id, id)` en `tractos` y `ramplas` | 1/1 |
| `0024` | P4 pautas y registros = 0 (verificado tras el DDL) | 0/0 |
| `0025` | P1 tablas no existen | 0 |
| `0025` | P2 igual que 0024 | 1/1/true |
| `0025` | P3 `UNIQUE (empresa_id, id)` en `choferes` | 1 |
| `0025` | P4 las 3 tablas = 0 filas | 0/0/0 |
| `0026` | P1 tabla no existe | 0 |
| `0026` | P2 `ctx_empresa`, rol, USAGE, `btree_gist` | 1/1/true/1 |
| `0026` | P3 `iva_porcentaje` vigente = nº de empresas (tras el seed) | 2/2 (`postgres`), 130/130 (`tei_test`) |

No hubo datos que violaran nada: las tablas nacen vacías y la única escritura es
el seed de `iva_porcentaje`.

---

## 4. Impacto, locks y rollback

### 4.1 Impacto

- **Datos:** sin backfill, sin `UPDATE`/`DELETE` sobre tablas existentes. En
  `postgres` no se escribió ninguna fila de negocio; el seed de `0026` insertó 2
  filas (1 por empresa) y sus 2 filas de `nucleo.auditoria`.
- **Locks:** `CREATE TABLE`/`CREATE VIEW`/`CREATE INDEX` sobre objetos nuevos
  (ACCESS EXCLUSIVE sobre la tabla que se crea, por milisegundos). Ningún
  `CREATE INDEX CONCURRENTLY` (tablas vacías y dentro de transacción).
- **Legacy:** ninguna sentencia referencia `public`. `public.configuracion`
  sigue siendo la fuente de `/configuracion` hasta que el backend lea `nucleo`
  (G0.3). No se apaga nada.
- **Backend actual:** no cambia. Nadie lee las tablas nuevas; `postgres` tiene
  `BYPASSRLS` y el módulo no está cableado.

### 4.2 Rollback (probado en ambas bases)

Scripts `supabase/tests/002[456]_99_rollback.sql`. Orden: `0026` → `0025` →
`0024` (no hay dependencias cruzadas; el orden es el inverso al de aplicación).

| Script | Qué hace | Pérdida |
|---|---|---|
| `0026_99` | `drop table nucleo.configuracion_empresa` + `drop function config_vigente`, `fn_config_empresa_inmutable`, `fn_config_empresa_no_borrar` | la configuración por empresa y su historial (el seed) |
| `0025_99` | `drop table` ajustes → anticipos → liquidaciones + 4 funciones | liquidaciones/anticipos/ajustes creados desde la app |
| `0024_99` | `drop view` + `drop table` mantenimientos → pautas + 3 funciones | pautas y registros de mantención |

Cada script imprime el conteo antes de borrar, no usa `CASCADE` (una dependencia
no prevista aborta) y verifica que el legacy siga existiendo. **No revierte**
`tractos.km_actual` que el trigger de odómetro hubiera subido: es un hecho, no un
estado de la migración.

Ciclo ejecutado (2026-10-31, `postgres` y `tei_test`): rollback de las 3 →
`tablas_nucleo = 40`, `politicas_nucleo = 45`, 0 objetos/funciones de la Ola B →
re-aplicación → `tablas_nucleo = 46`, `politicas = 51`, 6 tablas con
RLS+FORCE, `nomina_filas = 0` en `tei_test`.

---

## 5. Verificación (salidas reales)

### 5.1 Catálogo

```text
$ docker exec supabase_db_TRANSTEI psql -U supabase_admin -d postgres -Atc \
  "select 'tablas', count(*) from pg_tables where schemaname='nucleo' ..."
tablas|46
politicas|51
rls_force_6|6
iva_vigente|2

$ ... aclexplode sobre las tablas nuevas, grantee = tei_app
ajustes_liquidacion|INSERT,SELECT,UPDATE
anticipos_chofer|INSERT,SELECT,UPDATE
configuracion_empresa|INSERT,SELECT,UPDATE
liquidaciones|INSERT,SELECT,UPDATE
mantenimientos|INSERT,SELECT,UPDATE
pautas_mantenimiento|INSERT,SELECT,UPDATE
v_mantenimiento_estado|SELECT

$ ... triggers no internos en las 6 tablas
29
```

`select count(*) from pg_policies` (esquema `nucleo`): **51** (45 antes de la Ola B
+ 6 nuevas).

### 5.2 Suites de garantía

```text
$ docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
    -v ON_ERROR_STOP=1 < supabase/tests/0024_01_mantenimiento.sql
NOTICE:  OK 0024-1A mecanismo: 2 tablas RLS+FORCE, 2 políticas, vista presente
NOTICE:  OK 0024-1B positivo: registro creado con snapshot 20000 km
NOTICE:  OK 0024-1C bordes: restante 20000/0/5000/5001 => ok/pendiente/por_vencer/ok
NOTICE:  OK 0024-1D sin_registro + pauta/recurso incoherente => 23514
NOTICE:  OK 0024-1E positivo: rampla con pauta de rampla y costo 0
NOTICE:  OK 0024-1F costo < 0 => 23514
NOTICE:  OK 0024-1F km < 0 => 23514
NOTICE:  OK 0024-1F tracto+rampla => 23514
NOTICE:  OK 0024-1F tracto de otra empresa => 23503
NOTICE:  OK 0024-1G snapshot inmutable => 23514
NOTICE:  OK 0024-1G editar la pauta no reescribe el histórico
NOTICE:  OK 0024-1H ítem activo duplicado => 23505
NOTICE:  OK 0024-1I DELETE del histórico => 23514
NOTICE:  OK 0024-1I anular sin motivo => 23514
NOTICE:  OK 0024-1I anular con motivo deja el registro (no lo borra)
NOTICE:  OK 0024-1I el registro anulado no cuenta en el semáforo
ROLLBACK
0024-1: OK (rollback; 0 filas residuales)
```

```text
$ ... < supabase/tests/0025_01_liquidaciones.sql
NOTICE:  OK 0025-1B (CN-03): 400.000 + 180.000 + 50.000 - 100.000 = 530000.00
NOTICE:  OK 0025-1B total_liquido es `generated always` => 428C9
NOTICE:  OK 0025-1C (CN-04): HALF_UP 125001.125 => 125001.13 (HALF_EVEN/quantize habría dado 125001.12)
NOTICE:  OK 0025-1D emitida: cambio de comisión => 23514
NOTICE:  OK 0025-1D emitida -> borrador => 23514
NOTICE:  OK 0025-1D DELETE de liquidación => 23514
NOTICE:  OK 0025-1E positivo: anticipo imputado a la liquidación del mismo mes
NOTICE:  OK 0025-1E reimputar un anticipo => 23514
NOTICE:  OK 0025-1E limpiar la imputación => 23514
NOTICE:  OK 0025-1E (CN-05) mes de imputación incoherente => 23514
NOTICE:  OK 0025-1F DELETE de anticipo => 23514
NOTICE:  OK 0025-1F anular anticipo sin motivo => 23514
NOTICE:  OK 0025-1G DELETE de ajuste => 23514
NOTICE:  OK 0025-1G ajuste anulado con motivo (no borrado)
NOTICE:  OK 0025-1H (empresa, chofer, mes) duplicado => 23505
NOTICE:  OK 0025-1H chofer de otra empresa => 23503
NOTICE:  OK 0025-1I emitida -> anulada con motivo y sello
0025-1: OK (rollback; 0 filas residuales)
```

```text
$ ... < supabase/tests/0026_01_configuracion.sql
NOTICE:  OK 0026-1A mecanismo: RLS+FORCE, EXCLUDE de vigencia, UNIQUE parcial
NOTICE:  OK 0026-1B seed: iva_porcentaje = 19 por empresa (paridad 0001:291)
NOTICE:  OK 0026-1C segunda fila vigente => 23505/23P01
NOTICE:  OK 0026-1D UPDATE del valor vigente => 23514
NOTICE:  OK 0026-1E cambio de valor: cierre + fila nueva; vigente = 21
NOTICE:  OK 0026-1F UPDATE de fila cerrada => 23514
NOTICE:  OK 0026-1F reabrir vigencia cerrada => 23514
NOTICE:  OK 0026-1F DELETE del historial => 23514
NOTICE:  OK 0026-1G vigencia solapada => 23P01
NOTICE:  OK 0026-1G vigencia que retrocede => 23514
NOTICE:  OK 0026-1H aislado: iva = 101 => 23514
NOTICE:  OK 0026-1H aislado: iva = -1 => 23514
NOTICE:  OK 0026-1H aislado: iva no numérico => 23514
NOTICE:  OK 0026-1H borde 100 aceptado y vigente
0026-1: OK (rollback; vigencia sembrada intacta)
```

### 5.3 RLS con el rol real (`tei_app`, sin `BYPASSRLS`)

```text
$ docker exec -e PGPASSWORD=*** -i supabase_db_TRANSTEI \
    psql -h 127.0.0.1 -U tei_app -d postgres -v ON_ERROR_STOP=1 \
    < supabase/tests/0026_02_rls_tei_app.sql
NOTICE:  OK 0026-2 rol: current_user=tei_app bypass=f
NOTICE:  OK 0026-2E mecanismo: 6 tablas RLS+FORCE y 6 políticas
NOTICE:  OK 0026-2A INSERT sin contexto => 42501
NOTICE:  OK 0026-2A sin contexto: 6 tablas con 0 filas
NOTICE:  OK 0026-2B contexto TEI: filas propias visibles; config_vigente(TES) = NULL
NOTICE:  OK 0026-2B INSERT con empresa_id de TES => 42501
NOTICE:  OK 0026-2B INSERT de nómina ajena => 42501
NOTICE:  OK 0026-2B INSERT de config ajena => 42501
NOTICE:  OK 0026-2B UPDATE de otra empresa: 0 filas
NOTICE:  OK 0026-2C contexto TES: 0 filas de TEI; solo su propia config
NOTICE:  OK 0026-2D DELETE en las 6 tablas => 42501 (privilegio revocado)
ROLLBACK
0026-2: OK (rollback; 0 filas residuales)
```

### 5.4 Concurrencia real (dos conexiones) — `0025_02_concurrencia_anticipo.py`

```text
$ NUCLEO_DATABASE_URL='postgresql://tei_app:…@127.0.0.1:54322/tei_test' \
    .venv/bin/python supabase/tests/0025_02_concurrencia_anticipo.py
0025-2: fixtures listas (liquidación a2e35196-…, anticipo 05004009-…)
0025-2 C1 C1-0: filas=1 error=None
0025-2 C1 C1-1: filas=0 error=None
OK 0025-2 C1: dos conexiones, una sola imputación (row_count total = 1)
0025-2 C2 emitir: error=None sqlstate=None
0025-2 C2 editar: error=liquidación: emitida es inmutable en montos, chofer y mes (INV-LIQ02) sqlstate=23514
OK 0025-2 C2: emisión ganó; la edición posterior => 23514
AVISO 0025-2: sin privilegio TRUNCATE (el dueño es supabase_admin). …
0025_02: OK
```

Limpieza ejecutada después (la imprime el script):
`docker exec supabase_db_TRANSTEI psql -U supabase_admin -d tei_test -c "truncate …"`.

### 5.5 Mutación (la prueba falla si se retira el mecanismo)

| Mutación (en copia local) | Resultado |
|---|---|
| `drop trigger trg_liquidaciones_estado` (0025) | `ERROR: new row … violates check constraint "ck_liquidacion_emision"` → suite aborta |
| `alter table … drop constraint ck_mantenimiento_costo` (0024) | `ERROR: FALLO 0024-1F: se aceptó costo negativo` |
| `drop index uq_config_empresa_clave_vigente` + `drop constraint ex_config_vigencia` (0026) | `ERROR: FALLO 0026-1A: falta el EXCLUDE de vigencia` |
| `drop trigger trg_config_empresa_inmutable` (0026) | `ERROR: FALLO 0026-1D: se editó el valor de la fila vigente` |

Los 4 mecanismos se restauraron y las suites volvieron a verde.

### 5.6 No rompe las suites

```text
$ make unit
135 passed, 2 warnings in 0.73s

$ make test
388 passed, 2 warnings in 7.34s
```

---

## 6. Compatibilidad con `public`

- Ninguna sentencia de `0024`–`0026` referencia `public`; el legacy sigue
  operando igual y `nucleo` no depende de él.
- No hay dos fuentes de verdad nuevas para un mismo dato: las tablas legacy
  siguen siendo la fuente hasta la Ola D (ADR-0002). Mientras convivan, **la
  nómina y el mantenimiento pueden escribirse en ambos lados**: eso es un riesgo
  declarado (§7.2), no una garantía de esta entrega.
- El único dato compartido es `tractos.km_actual` (el legacy también lo
  actualiza desde el servicio). El trigger solo lo **sube** (`max`), así que no
  compite con el escritor legacy: ambos convergen al mayor km.

---

## 7. Preguntas abiertas y lo que **no** se impuso

### 7.1 Tributario/laboral (no se inventa)

| ID | Qué falta | A quién |
|---|---|---|
| `P-01` | Tasa IVA vigente, operaciones exentas, prorrateo y F29 | Contador |
| `P-09` | ¿El gasto es bruto o neto? ¿crédito con la tasa del día o del período? ¿arrastre de remanente? | Contador |
| `P-02` | AFP, salud, cesantía, impuesto único, gratificación y topes | Asesor laboral |
| `P-10` | ¿El anticipo es descuento lícito? ¿límite? ¿mes cerrado? ¿anticipo > haberes? | Asesor laboral |
| `D-19` | Anticipo de un mes ya emitido o mayor que los haberes: ¿arrastre, finiquito o rechazo? | Dueño |
| `D-20` | ¿El costo de mantención entra al costo del viaje / costo por km? | Dueño |
| `D-21` | Autoridad de la tasa IVA: configuración por empresa vs request de facturación | Dueño + contador |
| `P-11` | Intervalos de mantención por ítem, con fuente documental | Dueño + proveedor/mecánico |

**No modelado a propósito:** el crédito fiscal de IVA (`Σ monto × tasa/(100+tasa)`),
el `a_pagar`, el arrastre de remanente y cualquier cálculo de AFP/salud/impuesto.
Esas fórmulas dependen de `P-09`/`P-02`; `0026` solo guarda el parámetro de tasa
con vigencia. **Tampoco** se modeló el IVA débito: sale de
`nucleo.facturas_nucleo.iva`, que ya existe.

**Preguntas nuevas para `negocio-finanzas` (no se edita su archivo desde acá):**

- `P-12` (propuesta) — ¿Un anticipo imputado a una liquidación **anulada**
  vuelve a `pendiente`, se re-imputa al mes siguiente o se pierde? Hoy la base lo
  deja en `descontado` apuntando a un documento anulado, sin reimputar.
- `P-13` (propuesta) — ¿La configuración por empresa reemplaza a la global en
  `/configuracion` en una sola ventana, y con qué claves migradas (las 4 del
  legacy)? `0026` solo siembra `iva_porcentaje`.
- `RET-08` (abierta) — ¿Una mantención vencida debe **bloquear** la asignación
  del tracto? Hoy no bloquea (paridad) y `datos` no lo impuso.

### 7.2 Riesgos declarados

1. **Doble escritura durante la convivencia:** mientras las pantallas legacy
   sigan vivas, la nómina y el mantenimiento pueden registrarse en `public` y en
   `nucleo`. Ninguna constraint impide eso: es un riesgo de proceso hasta la Ola
   D (migración de datos) y el retiro de la pantalla.
2. **RLS inerte si el backend conecta como `postgres`:** el aislamiento está
   probado con `tei_app`, pero el wiring del rol es de `backend` (RA-03). Igual
   que `0020`–`0023`, la garantía no se activa sola.
3. **`estado` del registro de mantención:** el dominio `realizado | anulado` es
   una decisión de modelo (el legacy no lo tenía). Si el negocio necesita
   programar mantenciones futuras, eso va en `reservas_recurso`
   (tipo `mantenimiento`), no en esta tabla. Handoff a `backend`/`negocio`.
4. **Cabecera vs filas hijas:** `liquidaciones.bonos/descuentos/anticipos` son
   un **snapshot** de emisión; la base no exige que sumen lo mismo que las filas
   de `ajustes_liquidacion`/`anticipos_chofer`. Imponerlo obligaría a decidir
   `D-19`/`P-10` (qué pasa con un ajuste posterior a la emisión). Queda como
   regla de servicio y deuda de invariante.
5. **Seed de IVA:** `iva_porcentaje = 19` se sembró para 2 empresas en
   `postgres` y 130 en `tei_test`. Es paridad con `0001:291`, no una afirmación
   legal (`P-01`). Cambiarlo es "cerrar vigencia + insertar", y no reajusta
   facturas históricas.
6. **`vigente_desde`/`vigente_hasta` en la misma transacción:** el cierre y la
   apertura deben usar el **mismo** instante (`now()` en ambos, o una variable).
   Mezclar `now()` con `clock_timestamp()` produce un solape y el `EXCLUDE`
   rechaza (23P01). Está documentado en el `COMMENT` y probado en `0026-01`.

### 7.3 Deuda

- Prueba de mutación automatizada (hoy es un procedimiento manual, §5.5).
- La vista usa 5.000 km como umbral por defecto cuando la pauta no fija
  `alerta_km`: cuando el backend lea `configuracion_empresa`, el umbral debe
  venir de ahí (`alerta_km_mantenimiento`). No se puede resolver en `0024`
  porque `0026` se aplica después.
- `0024` no siembra las 6 pautas del legacy (`0001:296-302`) porque sus
  intervalos no tienen fuente documental (`P-11`). El seed es una decisión de
  negocio, no de `datos`.
- Índices: se crearon los que responden a las consultas obvias (por recurso,
  por pauta, por mes). No hay `EXPLAIN (ANALYZE, BUFFERS)` con volumen realista
  porque las tablas están vacías: 🔴 no medido.
