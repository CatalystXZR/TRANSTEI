# Migración 0015 — Todo viaje con los tres recursos ocupa el libro y valida documentos

> **Pregunta que responde:** ¿qué garantiza la migración 0015 y cómo se revierte?
> **Dueño:** `datos` · **Verificado:** 2026-10-29 · **Método:** lectura de DDL
> **Estado:** SQL escrito en `supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql`; **aplicación en base 🔴 no verificada**.
> **Re-verificar con:** `grep -n "create trigger" supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql`


> **Autor:** agente `datos` · **Fecha:** 2026-10-29 · **Riesgo:** Alto
> (disponibilidad / asignación de recursos)
> **Estado:** SQL escrito en `supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql`;
> **no aplicado, no ejecutado**. Nada de este documento es evidencia hasta que el
> orquestador aplique y corra las pruebas (🔴).
> **Aprobación requerida para:** aplicar la migración y ejecutar el backfill
> (`AGENTS.md` §10).

---

## 1. Propósito

Cerrar un agujero confirmado por lectura de código:

| Hecho | Evidencia |
|---|---|
| `fn_viaje_reservas` excluía `borrador, cotizado, confirmado, anulado` | `0004:1632-1635` |
| `fn_viaje_validar` devolvía temprano para `confirmado` | `0004:1124-1126` |
| `ck_viaje_recursos_por_estado` **permite** recursos en `confirmado` | `0004:671-674` |
| `cutover_legacy.py` inserta `confirmado` con los tres recursos | `scripts/cutover_legacy.py:361-388` |
| `crear_viaje` del backend nunca asigna recursos (`extra="forbid"` y sin campos de recurso) | `backend/app/nucleo/schemas.py:204-297`, `servicio_disponibilidad.py:869-980` |

Resultado: un viaje `confirmado` con tracto, rampla y chofer existía, era
despachable y **no** aparecía en `nucleo.reservas_recurso` ni validaba documentos.
La mesa de despacho veía el recurso libre.

## 2. Invariantes que impone

| ID | Enunciado | Mecanismo | Dónde | SQLSTATE |
|---|---|---|---|---|
| INV-D04 | Si `nucleo.viajes` tiene `tracto_id`, `rampla_id` y `chofer_id` no nulos y `estado <> 'anulado'`, existen **tres** reservas activas en `nucleo.reservas_recurso` con la **misma** `ventana` del viaje | `trg_viajes_70_reservas` → `nucleo.fn_viaje_reservas()` (reescrita) + `EXCLUDE` de `0004:744-757` | Núcleo | `23P01` en solape; `23514` en backfill inconsistente |
| INV-DOC04 | Con los tres recursos y `estado <> 'anulado'`, los documentos exigibles de tracto, rampla y chofer están vigentes hasta el fin efectivo del viaje (+ margen de la empresa), **sin importar el estado** | `trg_viajes_05_documentos` → `nucleo.fn_viaje_documentos()` (nueva) → `nucleo.validar_documentos_recurso` (`0004:1019-1104`) | Núcleo | `23514` |

Escritores cubiertos: backend del núcleo (INSERT/UPDATE de `nucleo.viajes`),
`psql`/scripts que escriban en `nucleo.viajes` (incluido `cutover_legacy.py`), y
seeds. **No cubre** `public.viajes` (legacy), que no escribe en el libro: RA-02
sigue abierto y esta migración no lo cierra.

## 3. Fronteras y decisiones de diseño

### 3.1 La condición es "tiene los tres recursos", no una lista de estados

Pedido del dueño: *todo viaje con los tres recursos ocupa y valida, sea cual sea
su estado*. Se implementa literal, con **una** excepción: `anulado` es terminal y
libera los recursos (`0004:1536-1543` lo trata como cierre con motivo).

### 3.2 Recursos parciales no ocupan ni validan (frontera declarada)

Un viaje con solo tracto (o tracto+rampla) **no** reserva. Razones:

1. Una asignación operativa es completa; reservar por un borrador a medio armar
   bloquea flota por un viaje que puede no existir.
2. `backend/tests/test_nucleo_bloqueos.py` y el flujo de bloqueos crean reservas
   manuales; exigir reserva por recursos parciales rompería escenarios legítimos
   sin ganar garantía.
3. Consecuencia aceptada: dos borradores pueden "apuntar" al mismo tracto en el
   papel hasta que la asignación se complete. Cuando se completa, el `EXCLUDE`
   arbitra y el segundo recibe `23P01`.

Esta frontera es la que permite que los flujos de `borrador`/`cotizado` sigan
funcionando (ver §3.3).

### 3.3 ¿Rompe transiciones legítimas de `borrador`/`cotizado`?

| Flujo | Antes | Con 0015 | Veredicto |
|---|---|---|---|
| `borrador` sin recursos → `confirmado` sin recursos → asignar | sin reservas | sin reservas (asignación completa ocurre en el paso 2) | **Sin cambio** |
| `borrador`/`cotizado` **con** los tres recursos (armado completo antes de confirmar) | sin reservas, sin validación documental | reserva + valida documentos al completar el tercer recurso | **Cambio intencional**: es la regla aprobada. Si el expediente está incompleto, el UPDATE falla con `23514` y el operador ve por qué |
| `confirmado` sin recursos → `asignado` con recursos | reserva + valida (0004) | igual | Sin cambio |
| `anulado` desde cualquier estado | libera | libera | Sin cambio |
| Borrar un `borrador` con los tres recursos | `DELETE` permitido | `DELETE` permitido por `fn_viaje_proteccion` pero **bloqueado por `fk_reserva_viaje` (ON DELETE RESTRICT)** | **Regresión funcional acotada** (ver §3.4) |

### 3.4 `DELETE` de un borrador con recursos

Al crear reservas para `borrador` con los tres recursos, el `DELETE` de ese viaje
falla con `23503` (FK `fk_reserva_viaje`, `0004:726-728`). No hay endpoint de
borrado de viajes en `backend/app/nucleo/api_*.py` (solo transiciones a `anulado`),
así que **hoy no hay impacto de API**. Si se agrega uno, debe desactivar las
reservas antes de borrar o usar `anulado`. Registrado como riesgo R1.

### 3.5 Se conserva la excepción operativa de 0004 (no se endurece)

`0004:1128-1138` no revalida documentos a un viaje ya despachado que solo cambia
de estado, para no detener unidades en ruta porque un papel venció después del
despacho. `fn_viaje_documentos` **replica** esa condición (`UPDATE`, estado ≠
`asignado`, recursos sin cambio ⇒ no valida). Cambiarla es una decisión de
negocio, no de `datos`.

### 3.6 No se toca `ck_viaje_recursos_por_estado` ni `fn_viaje_validar`

La validación completa de despacho (capacidad, tarifa, OC, ventana) sigue atada a
`asignado` (`0004:1106-1384`). Consecuencia: en `confirmado` con recursos, la
validación documental puede ejecutarse dos veces (una en `05_documentos`, otra en
`10_validar` cuando el viaje llega a `asignado`). Es read-only e idempotente;
se acepta para no duplicar la lógica de validación.

## 4. Precondiciones (ejecutar antes de aplicar)

Ninguna se ejecutó (🔴: no hay base levantada en esta sesión). Se entregan listas.

### P1.1 — Viajes en alcance sin sus 3 reservas activas (el agujero)

```sql
select v.id, v.empresa_id, v.numero_viaje, v.estado, v.inicio_planificado
  from nucleo.viajes v
 where v.estado <> 'anulado'
   and v.tracto_id is not null and v.rampla_id is not null
   and v.chofer_id is not null
   and 3 > (select count(*) from nucleo.reservas_recurso r
             where r.viaje_id = v.id and r.activa);
```

**Esperado:** > 0 si el cutover o pruebas manuales corrieron (esos viajes los
adopta el backfill). **Acción:** ninguna manual; el backfill los incorpora.

### P1.2 — Pares de viajes en alcance solapados sobre el mismo recurso

```sql
select a.numero_viaje as viaje_a, b.numero_viaje as viaje_b,
       a.estado as estado_a, b.estado as estado_b, a.ventana
  from nucleo.viajes a
  join nucleo.viajes b
    on a.id < b.id
   and a.empresa_id = b.empresa_id
   and a.ventana && b.ventana
 where a.estado <> 'anulado' and b.estado <> 'anulado'
   and a.tracto_id is not null and a.rampla_id is not null and a.chofer_id is not null
   and b.tracto_id is not null and b.rampla_id is not null and b.chofer_id is not null
   and (a.tracto_id = b.tracto_id or a.rampla_id = b.rampla_id
        or a.chofer_id = b.chofer_id)
   and ( 3 > (select count(*) from nucleo.reservas_recurso r
               where r.viaje_id = a.id and r.activa)
      or 3 > (select count(*) from nucleo.reservas_recurso r
               where r.viaje_id = b.id and r.activa) );
```

**Debe devolver 0 filas.** Si devuelve filas, el `DO` del backfill **aborta con
`23514`** y nombra un par de ejemplo. **No se borra ni se reasigna nada:** son dos
viajes reales compitiendo; lo resuelve operación (anular o reasignar) y se vuelve
a aplicar.

### P1.3 — Reservas activas de viaje con ventana distinta a la del viaje

```sql
select r.id, r.viaje_id, r.recurso_tipo, r.ventana, v.ventana as ventana_viaje
  from nucleo.reservas_recurso r
  join nucleo.viajes v on v.id = r.viaje_id
 where r.activa and r.tipo_reserva = 'viaje'
   and r.ventana <> v.ventana;
```

**Debe devolver 0 filas.** Si hay deriva, el backfill no puede dejar el libro
coherente y aborta con `23514` (el autochequeo final cuenta viajes con reservas
cuya ventana no coincide).

### P1.4 — Tamaño real (dimensiona locks; medir, no suponer)

```sql
select relname,
       n_live_tup,
       pg_size_pretty(pg_total_relation_size(relid)) as total
  from pg_stat_user_tables
 where schemaname = 'nucleo'
   and relname in ('viajes', 'reservas_recurso');
```

**Acción:** si `reservas_recurso` es grande (> ~1 M filas), planifique ventana: el
backfill inserta contra tres índices GIST y puede esperar reservas concurrentes
del mismo recurso.

## 5. DDL

Todo en una transacción implícita del archivo (`psql` sin `--single-transaction`
ejecuta sentencia por sentencia; el backfill está en un único `DO`, que es
atómico). No hay `CREATE INDEX CONCURRENTLY`: no se crean índices nuevos.

1. `create or replace function nucleo.fn_viaje_reservas()` — reescritura de
   `0004:1621-1650`.
   - Condición nueva: `estado <> 'anulado' and los tres recursos no nulos`.
   - **Camino rápido**: si ya hay 3 reservas activas con la misma `ventana` y los
     recursos del viaje, retorna sin tocar el libro. Evita desactivar/reinsertar
     en cada `UPDATE` irrelevante (con `confirmado` ahora en alcance, sin este
     camino cada cambio de campo generaría 6 operaciones y riesgo de `23P01`
     espurio).
   - Reasignación/anulación/cambio de ventana: `UPDATE ... activa = false` y
     reinserción **en la misma transacción** (atómico).
2. `create or replace function nucleo.fn_viaje_documentos()` — nueva.
   - Salta si `anulado`, si faltan recursos, o si es `UPDATE` con estado ≠
     `asignado` y recursos sin cambio (excepción operativa heredada).
   - Calcula `fin_efectivo = coalesce(fin_real, fin_estimado, fin_planificado) +
     buffer_minutos` (idéntico a `fn_viaje_ventana`, `0004:926-936`) y
     `hasta = (fin_efectivo at time zone zona)::date + dias_margen_documentos`.
   - Llama `nucleo.validar_documentos_recurso` para tracto, rampla y chofer.
3. `drop trigger if exists` + `create trigger trg_viajes_05_documentos
   before insert or update on nucleo.viajes for each row`.
   - Orden alfabético resultante: `00_ventana` → `03_licencia_a5` (0016) →
     `05_documentos` → `10_validar` → `15_facturacion` → `20_proteccion` → …
4. Backfill (§6) + `analyze nucleo.reservas_recurso`.

Re-ejecutable: `CREATE OR REPLACE`, `DROP TRIGGER IF EXISTS`, backfill con
`NOT EXISTS` por `(viaje, recurso_tipo)`.

## 6. Backfill

**Universo:** viajes con los tres recursos y `estado <> 'anulado'`.
**Operación:** tres `INSERT ... SELECT` (tracto, rampla, chofer), cada uno con
`NOT EXISTS` sobre una reserva **activa del mismo tipo** para ese viaje.

| Requisito (`AGENTS.md` §8) | Cómo se cumple |
|---|---|
| Idempotente | `NOT EXISTS` por `(viaje_id, recurso_tipo)`; re-ejecutar no duplica |
| Reanudable | Si el `DO` falla, no deja filas (el bloque es una transacción); si se aplicó y se repite, no hace nada |
| Conteos antes/después | `raise notice` con `viajes con 3 recursos`, `por adoptar`, `reservas insertadas`, `reservas activas de viaje: antes -> después` |
| Checksum | §6.2 |
| No borra | Solo `INSERT`; ninguna sentencia `DELETE`/`UPDATE` de datos existentes |
| Aborta ante conflicto | P1.2 embebida: si hay pares solapados, `raise ... using errcode = '23514'` |
| Autochequeo | Al final cuenta viajes que siguen sin 3 reservas en la ventana del viaje; si > 0, aborta con `23514` |

### 6.1 ¿Por qué no por lotes?

El patrón "por lotes" protege contra transacciones largas. Aquí el volumen es
**desconocido hasta correr P1.4**, y la operación es un `INSERT ... SELECT`
set-based: una sola pasada, sin cursor, con el mismo costo total que N lotes pero
sin estados intermedios incoherentes. La decisión:

- Si P1.4 muestra un universo pequeño (< ~50 000 viajes), se ejecuta tal cual.
- Si es mayor, **no edite esta migración**: agregue `LIMIT`/`ORDER BY` por lotes
  en una migración 0017 o en un script autorizado, y deje 0015 para el DDL. El
  autochequeo convierte un backfill incompleto en un fallo explícito, no en un
  éxito silencioso.

### 6.2 Checksum de control

Antes y después, guarde el resultado:

```sql
select count(*) as reservas_viaje_activas,
       md5(string_agg(r.id::text, ',' order by r.id::text)) as checksum
  from nucleo.reservas_recurso r
 where r.activa and r.tipo_reserva = 'viaje';
```

El `checksum` **debe cambiar** si hubo adopciones y **debe ser igual** en una
segunda ejecución (idempotencia).

## 7. Impacto y locks

| Sentencia | Lock | Duración esperada | Efecto en operación |
|---|---|---|---|
| `CREATE OR REPLACE FUNCTION` (×2) | catálogo | ms | Ninguno; las sesiones nuevas usan la versión nueva |
| `CREATE TRIGGER` | `ShareRowExclusiveLock` sobre `nucleo.viajes` | ms | Bloquea escrituras de viajes mientras crea el trigger |
| Backfill `INSERT` | `RowExclusiveLock` en `reservas_recurso` + GIST | proporcional a filas | Puede **esperar** por reservas concurrentes del mismo recurso (el `EXCLUDE` bloquea la fila en conflicto) |
| `ANALYZE` | `ShareUpdateExclusiveLock` | segundos | No bloquea lecturas ni escrituras |

- `public` (legacy): **no se toca**, sin impacto.
- No hay `ACCESS EXCLUSIVE` sobre `nucleo.viajes` salvo el instante del
  `CREATE TRIGGER`.
- Sin reescritura de tablas, sin `DROP`, sin pérdida de datos.

## 8. Compatibilidad

| Consumidor | Efecto | Evidencia |
|---|---|---|
| `crear_viaje` (núcleo) | Sin cambio: nunca envía recursos (`extra="forbid"`, sin campos) | `schemas.py:204-297`, `servicio_disponibilidad.py:951` |
| `confirmar_asignacion` / `asignar` | Sin cambio funcional; ya creaba reservas y validaba documentos | `servicio_disponibilidad.py:1411-1572` |
| `anular` | Sin cambio: libera recursos | `fn_viaje_transicion` (`0004:1511-1547`) |
| Frontend despacho | Sin cambio de contrato; puede recibir `23514` en el paso "asignar" con mensaje de documento | `frontend/src/lib/nucleo.ts` (handoff) |
| `scripts/seed_local.py` | Sin cambio si no crea viajes con recursos; si lo hace, ahora exige documentos | `scripts/seed_local.py` |
| `scripts/cutover_legacy.py` | **INCOMPATIBLE a propósito** (§8.1) | `cutover_legacy.py:361-388` |
| `public` legacy | Sin cambio | — |

### 8.1 `cutover_legacy.py` — incompatibilidad declarada

El script inserta viajes `confirmado` **con** los tres recursos y **no** crea
`nucleo.documentos`. Con 0015 el `INSERT` falla con `23514` ("Documento
`licencia_conducir` faltante …") y la transacción del cutover se revierte completa.

Se marca **INCOMPATIBLE** deliberadamente:

- Migrar viajes con recursos y sin expediente equivale a despachar sin control.
- **No** se agrega un GUC de escape: sería un mecanismo fail-open, el mismo
  defecto que RA-04 (`legacy_congelado()`).

Camino correcto (handoff a quien mantiene `scripts/`, **no** a esta migración):

- **(a)** cargar primero `nucleo.documentos` de tracto/rampla/chofer y luego los
  viajes, o
- **(b)** migrar los viajes en `borrador`/`cotizado` **sin** recursos y completar
  la asignación después de cargar documentos.

Además, P1.2 (solapamientos del legacy) debe estar en 0 antes de aplicar.

## 9. Rollback (exacto, conserva datos)

```sql
-- 1. Retirar la puerta documental
drop trigger if exists trg_viajes_05_documentos on nucleo.viajes;
drop function if exists nucleo.fn_viaje_documentos();

-- 2. Restaurar fn_viaje_reservas con el cuerpo textual de 0004:1621-1650
create or replace function nucleo.fn_viaje_reservas()
returns trigger
language plpgsql
as $$
declare
  v_auth text := coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema');
begin
  update nucleo.reservas_recurso
     set activa = false
   where viaje_id = new.id and activa;

  if new.estado not in ('borrador', 'cotizado', 'confirmado', 'anulado')
     and new.tracto_id is not null
     and new.rampla_id is not null
     and new.chofer_id is not null then
    insert into nucleo.reservas_recurso (
      empresa_id, recurso_tipo, tracto_id, rampla_id, chofer_id, ventana,
      tipo_reserva, viaje_id, motivo, activa, creado_por
    ) values
      (new.empresa_id, 'tracto', new.tracto_id, null, null, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth),
      (new.empresa_id, 'rampla', null, new.rampla_id, null, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth),
      (new.empresa_id, 'chofer', null, null, new.chofer_id, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth);
  end if;

  return new;
end;
$$;

-- 3. Las reservas del backfill NO se borran: se desactivan (trazabilidad).
--    fn_reserva_no_borrar impide DELETE; el trigger de auditoría conserva el rastro.
update nucleo.reservas_recurso
   set activa = false,
       cancelado_motivo = 'rollback 0015',
       cancelado_por = 'migracion_0015',
       cancelado_en = now()
 where activa and creado_por = 'migracion_0015';

-- 4. Verificar
select count(*) from nucleo.reservas_recurso
 where activa and creado_por = 'migracion_0015';   -- -> 0
```

- **Conserva datos:** no hay `DELETE`; las reservas quedan inactivas con motivo.
- **Permite volver a operar:** el sistema regresa al comportamiento de 0004.
- **Es un incidente, no rutina:** el rollback reabre el agujero (viajes
  `confirmado` con recursos invisibles para el libro). Debe registrarse como tal.
- Las reservas creadas **por el flujo normal** (estado operativo) no se tocan:
  el filtro es `creado_por = 'migracion_0015'`.

## 10. Verificación posterior

```sql
-- V1: ningún viaje en alcance queda fuera del libro (esperado: 0)
select count(*) from nucleo.viajes v
 where v.estado <> 'anulado'
   and v.tracto_id is not null and v.rampla_id is not null and v.chofer_id is not null
   and 3 > (select count(*) from nucleo.reservas_recurso r
             where r.viaje_id = v.id and r.activa and r.ventana = v.ventana);

-- V2: triggers en su lugar y en el orden esperado
select tgname from pg_trigger
 where tgrelid = 'nucleo.viajes'::regclass and not tgisinternal
 order by tgname;

-- V3: las pruebas de garantía (ver §11)
```

V2 debe listar `trg_viajes_05_documentos` entre `03_licencia_a5` y `10_validar`.

## 11. Pruebas

| Archivo | Qué demuestra | Estado |
|---|---|---|
| `supabase/tests/fixtures_0015_0016.sql` | Empresa `TST15` aislada, flota, 7 choferes, 26 documentos | 🔴 no ejecutado |
| `supabase/tests/0015_01_confirmado_ocupa.sql` | `confirmado` + 3 recursos ⇒ 3 reservas con la ventana del viaje; `anulado` ⇒ 0 activas / 3 históricas; parciales ⇒ 0 | 🔴 |
| `supabase/tests/0015_02_concurrencia_rampla.py` | **Dos conexiones**: B se bloquea y al commit de A recibe `23P01` (`ex_reserva_rampla`); queda 1 reserva | 🔴 |
| `supabase/tests/0015_03_confirmado_valida_documentos.sql` | `confirmado` + 3 recursos + chofer sin documentos ⇒ `23514` "faltante"; parciales no validan | 🔴 |
| `supabase/tests/mutacion.md` (M1, M2) | Retirar el trigger o restaurar `fn_viaje_reservas` de 0004 hace **fallar** las pruebas | 🔴 |
| `supabase/tests/99_limpieza_viajes_prueba.sql` | Retira el viaje commiteado por la prueba de concurrencia | 🔴 |

Faltantes declarados: no hay prueba de concurrencia para **tracto** ni **chofer**
(mismo patrón, una `EXCLUDE` por tipo); no hay prueba del backfill sobre volumen
real (se valida con V1 en la base que corresponda).

## 12. Riesgos y no verificado

| ID | Riesgo | Nivel | Mitigación / dueño |
|---|---|---|---|
| R1 | Un `borrador` con los tres recursos ya no se puede `DELETE` (`fk_reserva_viaje` RESTRICT). Hoy no hay endpoint de borrado | Bajo | Documentado; si aparece el endpoint, desactivar reservas primero (`backend`) |
| R2 | Cambiar `fin_real`/`fin_estimado` de un viaje en ruta recalcula `ventana` y reinserta reservas: puede chocar con el viaje siguiente (`23P01`) | Medio, **heredado de 0004** | No lo introduce 0015 (0004 ya reinsería en estados operativos). Si molesta, la decisión es de negocio: ¿extender la ventana o no? |
| R3 | `cutover_legacy.py` deja de funcionar | Alto operativo | §8.1; el script debe adaptarse **antes** de un cutover |
| R4 | El legacy sigue sin escribir en el libro (RA-02) | Alto | Fuera de alcance; requiere ADR de convivencia (`arquitectura`) |
| R5 | Backfill en una base grande sin ventana | Medio | P1.4 + §6.1 |
| R6 | La excepción operativa (recursos sin cambio ⇒ no revalidar) permite que un documento vencido pase desapercibido en un viaje ya despachado | Medio, decisión de negocio | Documentado en §3.5; cambiarlo exige autorización |
| — | **Nada ejecutado**: sin base local levantada, ni precondiciones ni pruebas ni mutación | 🔴 | Orquestador/`qa` |
