# Mutación — demostrar que las pruebas prueban algo

> **Autor:** agente `datos` · **Fecha:** 2026-10-29 · **Estado:** procedimiento
> escrito, **no ejecutado** (🔴: este agente no ejecuta SQL por contrato). Lo corre
> el orquestador o `qa` en la base local desechable.
>
> Una prueba verde no vale si sigue verde cuando se retira el mecanismo
> (`AGENTS.md` §7, `02-invariantes.md` §0). Para cada garantía de 0015/0016 se
> indica: cómo se retira, qué debe fallar y cómo se restaura.
>
> **Toda la mutación se hace en la base local `127.0.0.1:54322`, desechable.**
> Nunca en staging ni producción. Al terminar cada bloque, restaurar **antes** de
> pasar al siguiente: dos mecanismos retirados a la vez producen fallos ambiguos.

## 0. Preparación

```bash
export DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:54322/postgres'
# (no se imprime la cadena; use la suya si difiere)

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/fixtures_0015_0016.sql

# Línea base: todo verde ANTES de mutar.
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0015_01_confirmado_ocupa.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0015_03_confirmado_valida_documentos.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_01_licencia_clase_no_a5.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_02_licencia_por_vencer_no_bloquea.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_03_licencia_vencida_bloquea.sql
python supabase/tests/0015_02_concurrencia_rampla.py
psql "$DATABASE_URL" -c "set nucleo.test_cleanup='si'" \
     -f supabase/tests/99_limpieza_viajes_prueba.sql
```

Si la línea base no está verde, **deténgase**: mutar sobre una prueba que ya falla
no demuestra nada.

Registro sugerido por mutación:

```
| Mutación | Prueba | Esperado sin mecanismo | Resultado real | Restaurado |
```

---

## M1 — Retirar la puerta documental de 0015 (`trg_viajes_05_documentos`)

**Qué garantía prueba:** INV-DOC04 — un viaje con los tres recursos valida
documentos sin importar el estado.

**Mutación**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
drop trigger if exists trg_viajes_05_documentos on nucleo.viajes;
SQL
```

**Debe fallar** (prueba roja = la prueba sí probaba el trigger)

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f supabase/tests/0015_03_confirmado_valida_documentos.sql
# Esperado: ERROR ... FALLO 0015-3A: un viaje confirmado con chofer sin documentos fue ACEPTADO
```

Efecto colateral esperado: `0016_03` también deja de rechazar la licencia vencida
(el bloqueo documental de 0004 solo corría en estados operativos antes de 0015):

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f supabase/tests/0016_03_licencia_vencida_bloquea.sql
# Esperado: ERROR ... FALLO 0016-3: se aceptó un viaje con licencia VENCIDA
```

**Control (debe seguir verde):** `0016_02_licencia_por_vencer_no_bloquea.sql` no
depende de este trigger sino de la comparación contra el fin del viaje; si también
falla, algo más se rompió.

**Restaurar**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql
# 0015 es re-ejecutable: CREATE OR REPLACE + DROP TRIGGER IF EXISTS + backfill
# idempotente (NOT EXISTS por viaje/recurso_tipo).
```

**Verificar restauración**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"select tgname from pg_trigger
  where tgrelid = 'nucleo.viajes'::regclass and not tgisinternal
    and tgname = 'trg_viajes_05_documentos';"
# -> 1 fila
```

---

## M2 — Retirar la ocupación de 0015 (volver `fn_viaje_reservas` a 0004)

**Qué garantía prueba:** INV-D04 — un viaje `confirmado` con los tres recursos
ocupa el libro.

**Mutación** (cuerpo textual de `0004:1621-1650`, que excluía por lista de estados)

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
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
SQL
```

**Debe fallar**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f supabase/tests/0015_01_confirmado_ocupa.sql
# Esperado: ERROR ... FALLO 0015-1A: se esperaban 3 reservas activas para el viaje confirmado, hay 0
```

Y la prueba de concurrencia deja de tener algo que bloquear (la sesión A no crea
reservas, la B no se bloquea):

```bash
python supabase/tests/0015_02_concurrencia_rampla.py
# Esperado: FALLO 0015-2: la sesión A debía crear 3 reservas, creó 0
```

**Restaurar**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f supabase/migrations/0015_viaje_con_recursos_ocupa_y_valida.sql
```

**Verificar restauración**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"select prosrc like '%v_ocupa%' as es_0015 from pg_proc
  where proname = 'fn_viaje_reservas' and pronamespace = 'nucleo'::regnamespace;"
# -> t
```

---

## M3 — Retirar el bloqueo de clase A5 de 0016 (`trg_viajes_03_licencia_a5`)

**Qué garantía prueba:** INV-R02-01 — solo A5 es asignable.

**Mutación**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
drop trigger if exists trg_viajes_03_licencia_a5 on nucleo.viajes;
SQL
```

**Debe fallar**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f supabase/tests/0016_01_licencia_clase_no_a5.sql
# Esperado: ERROR ... FALLO 0016-1A: se aceptó un viaje con chofer clase A3
# (los documentos del chofer A3 están vigentes, así que sin el trigger nada lo frena)
```

**Control (debe seguir verde):** `0016_02` (chofer A5) y `0016_03` (chofer A5 con
licencia vencida) no dependen de este trigger; si fallan, el fallo es de otra causa.

**Restaurar**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
     -f supabase/migrations/0016_licencia_a5_bloqueante.sql
```

**Verificar restauración**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"select tgname from pg_trigger
  where tgrelid = 'nucleo.viajes'::regclass and not tgisinternal
    and tgname = 'trg_viajes_03_licencia_a5';"
# -> 1 fila
```

---

## M4 — Retirar el árbitro de concurrencia (`ex_reserva_rampla`)

**Qué garantía prueba:** el `EXCLUDE` de 0004 (no de 0015) es lo que convierte la
condición de carrera en un rechazo `23P01`. Esta mutación demuestra que
`0015_02` prueba concurrencia **y** que la base —no el servicio— es el árbitro.

**Mutación**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
alter table nucleo.reservas_recurso drop constraint ex_reserva_rampla;
SQL
```

**Debe fallar**

```bash
python supabase/tests/0015_02_concurrencia_rampla.py
# Esperado: FALLO 0015-2: la sesión B NO quedó bloqueada; terminó antes del commit de A
#   (o, si el timing cambia, "la sesión B fue ACEPTADA: dos viajes ocupan la misma rampla")
```

En ambos casos el mensaje es el fallo de la prueba; lo relevante es que **deja de
ser verde**.

**Restaurar**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
alter table nucleo.reservas_recurso
  add constraint ex_reserva_rampla
  exclude using gist (rampla_id with =, ventana with &&)
  where (recurso_tipo = 'rampla' and activa);
SQL
```

Si la restauración falla por filas ya duplicadas (la mutación dejó dos reservas
solapadas), **no borre**: primero liste el conflicto y resuélvalo a mano en la base
desechable:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"select a.id, b.id, a.rampla_id, a.ventana, b.ventana
   from nucleo.reservas_recurso a
   join nucleo.reservas_recurso b
     on a.id < b.id and a.rampla_id = b.rampla_id and a.ventana && b.ventana
  where a.activa and b.activa and a.recurso_tipo = 'rampla' and b.recurso_tipo = 'rampla';"
# En base desechable: desactivar la reserva del viaje perdedor y luego crear la constraint.
```

**Verificar restauración**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"select conname from pg_constraint
  where conrelid = 'nucleo.reservas_recurso'::regclass and conname = 'ex_reserva_rampla';"
# -> 1 fila
```

---

## M5 — Retirar el default 14 de `dias_alerta_documentos` (0016)

**Qué garantía prueba:** sólo el cambio de default. **No hay prueba automatizada**
de esto: es configuración, no integridad. Se verifica con una consulta, no con un
test. Se documenta aquí para que no se confunda "default" con "constraint".

**Mutación**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"alter table nucleo.empresas alter column dias_alerta_documentos set default 30;"
```

**Debe cambiar**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"select column_default from information_schema.columns
  where table_schema = 'nucleo' and table_name = 'empresas'
    and column_name = 'dias_alerta_documentos';"
# Esperado con 0016: 14   ·   mutado: 30
```

**Restaurar**

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"alter table nucleo.empresas alter column dias_alerta_documentos set default 14;"
```

**Nota:** ninguna fila existente cambia en ninguna de las dos direcciones. Si
quiere comprobar el "sin reescritura silenciosa":

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
"select codigo, dias_alerta_documentos from nucleo.empresas order by codigo;"
# TST15 conserva 14 (lo fija la fixture), el resto conserva lo que tenía.
```

---

## 1. Mutación no aplicable (y por qué)

| Garantía | Por qué no se muta | Qué la respalda |
|---|---|---|
| Ventana de aviso de 14 días (INV-R02-03) | No es un mecanismo de base: es notificación de servicio. Retirarla no cambia ningún SQL | `backend/app/nucleo/servicio_alertas.py`, `servicio_disponibilidad.py` (handoff) |
| `anulado` libera recursos | Es una rama del mismo trigger de M2; retirarla exige reescribir la función, no retirar un objeto | `fn_viaje_reservas` (0015) |
| Backfill de 0015 | Su "mutación" es no ejecutarlo; la verificación V1 del encabezado de 0015 lo detecta (count > 0) | `docs/datos/migraciones/0015-ocupacion-confirmado.md` §Verificación |
| Degradación de un chofer asignado de A5 a otra clase | **No está garantizada** (gap residual declarado en 0016). No hay mecanismo que mutar; hay un riesgo registrado | `docs/datos/migraciones/0016-licencia-a5.md` §Riesgos |

---

## 2. Cierre

Al terminar, la base local debe quedar **sin mutaciones** y con la línea base verde:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/fixtures_0015_0016.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0015_01_confirmado_ocupa.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0015_03_confirmado_valida_documentos.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_01_licencia_clase_no_a5.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_02_licencia_por_vencer_no_bloquea.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_03_licencia_vencida_bloquea.sql
python supabase/tests/0015_02_concurrencia_rampla.py
psql "$DATABASE_URL" -c "set nucleo.test_cleanup='si'" \
     -f supabase/tests/99_limpieza_viajes_prueba.sql
```

Si alguna restauración se hizo con `DISABLE TRIGGER USER` (§Alternativa de
`99_limpieza_viajes_prueba.sql`), confirme que los triggers quedaron habilitados
antes de declarar la base utilizable.
