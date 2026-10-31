-- ============================================================================
-- Prueba 0020-4 — COMPATIBILIDAD con el rol actual de la app (`postgres`)
-- ============================================================================
-- La migración 0020 crea políticas y activa FORCE. Antes de cambiar el rol de
-- conexión del backend (handoff), la app SIGUE entrando como `postgres`. Esta
-- prueba demuestra que, en ese estado:
--
--   A) `postgres` (BYPASSRLS) sigue viendo TODAS las filas, con o sin
--      `app.empresa_id` fijado ⇒ fijar el GUC antes de cambiar el rol es
--      inocuo y el despliegue se puede hacer en dos pasos.
--   B) `postgres` puede escribir sin contexto (la app actual no se rompe) y el
--      trigger de auditoría sigue registrando.
--   C) FORCE no neutraliza a `postgres`: BYPASSRLS gana sobre FORCE.
--
-- Contraparte: 0020-01/02/03 prueban el mismo esquema con `tei_app`, donde el
-- aislamiento SÍ aplica. Si esta prueba y aquellas no discrepan, el rol es la
-- variable que decide.
--
-- Todo va en una transacción con ROLLBACK: no deja datos.
--
-- Uso:
--   psql "$ADMIN_URL" -v ON_ERROR_STOP=1 \
--        -f supabase/tests/0020_04_compatibilidad_postgres.sql
-- (rol con BYPASSRLS; en local: postgres o supabase_admin)
-- ============================================================================

\set ON_ERROR_STOP on

\echo '0020-4: rol privilegiado efectivo'
do $$
declare
  v_bypass boolean;
begin
  select rolbypassrls into v_bypass from pg_roles where rolname = current_user;
  if not coalesce(v_bypass, false) then
    raise exception 'FALLO 0020-4: esta prueba necesita un rol con BYPASSRLS (hoy: %)', current_user;
  end if;
  raise notice 'OK 0020-4 rol: current_user=% bypass=%', current_user, v_bypass;
end $$;

begin;

do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_total bigint;
  v_sin_ctx bigint;
  v_con_ctx bigint;
  v_id uuid := gen_random_uuid();
  v_rut text := 'TEST-' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 8);
  v_n bigint;
begin
  -- A) sin contexto y con contexto: el rol privilegiado ve lo mismo (todo).
  perform set_config('app.empresa_id', '', true);
  select count(*) into v_sin_ctx from nucleo.viajes;
  perform set_config('app.empresa_id', v_a::text, true);
  select count(*) into v_con_ctx from nucleo.viajes;
  select count(*) filter (where true) into v_total from nucleo.viajes;

  if v_sin_ctx <> v_total or v_con_ctx <> v_total then
    raise exception 'FALLO 0020-4A: el rol privilegiado quedó filtrado (total=%, sin ctx=%, con ctx=%)',
      v_total, v_sin_ctx, v_con_ctx;
  end if;
  if v_total = 0 then
    raise exception 'FALLO 0020-4A: no hay viajes para medir';
  end if;
  raise notice 'OK 0020-4A postgres ve % viajes con y sin app.empresa_id (BYPASSRLS gana sobre FORCE)', v_total;

  -- B) escribe sin contexto; la app actual no se rompe.
  perform set_config('app.empresa_id', '', true);
  insert into nucleo.clientes (id, empresa_id, razon_social, rut)
  values (v_id, v_a, 'Cliente compatibilidad 0020', v_rut);
  select count(*) into v_n from nucleo.clientes where id = v_id;
  if v_n <> 1 then
    raise exception 'FALLO 0020-4B: el rol privilegiado no puede insertar sin contexto';
  end if;
  select count(*) into v_n from nucleo.auditoria where registro_id = v_id;
  if v_n <> 1 then
    raise exception 'FALLO 0020-4B: el trigger de auditoría no registró el INSERT del rol privilegiado (%)', v_n;
  end if;
  raise notice 'OK 0020-4B postgres inserta sin contexto y el trigger de auditoría registra';

  -- C) una fila de OTRA empresa también es visible para el rol privilegiado.
  select count(*) into v_n from nucleo.viajes where empresa_id <> v_a;
  if v_n = 0 then
    raise exception 'FALLO 0020-4C: no hay filas de otra empresa para comparar';
  end if;
  raise notice 'OK 0020-4C postgres ve % viajes de otras empresas (así se comporta la app HOY)', v_n;
end $$;

rollback;

\echo '0020_04_compatibilidad_postgres: OK'
