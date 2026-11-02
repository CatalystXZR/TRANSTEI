-- ============================================================================
-- Prueba 0028-1 — retiro físico de `public`: que el legacy no vuelva
-- ============================================================================
-- Verifica el estado que impone `0028_retiro_public.sql` (Ola E, ADR-0002 §6.7
-- E.5). Falla si el mecanismo deja de existir (prueba de mutación:
-- `0028_02_mutacion.sh`).
--
--   A  `public` sin relaciones, funciones ni tipos propios (solo extensión).
--   B  `auth.users` sin `on_auth_user_created`; sin `public.handle_new_user`.
--   C  El núcleo sigue en pie: `btree_gist` instalada y sus 4 `EXCLUDE`.
--   D  Rol real `tei_app`: sin `USAGE` en `public` (42501, no 42P01) y con
--      `USAGE` en `nucleo`.
--   E  `tei_app` sigue escribiendo en `nucleo` sobre una tabla con `EXCLUDE`
--      gist (prueba de que los objetos de `btree_gist` en `public` se usan por
--      OID y no por nombre: revocar el `USAGE` no rompió el índice).
--   F  El esquema `public` se conserva (PostgREST/Supabase lo esperan) y el
--      bucket `respaldos` sigue existiendo.
--
-- Transacción con ROLLBACK: no deja filas.
--
-- Uso (sin psql en el host, se usa el del contenedor):
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
--     -v ON_ERROR_STOP=1 < supabase/tests/0028_01_retiro_public.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

\echo '0028-1A: public sin objetos propios (solo la extensión btree_gist)'
do $$
declare
  v_n bigint;
begin
  select count(*) into v_n
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    left join pg_depend d on d.objid = c.oid and d.deptype = 'e'
   where n.nspname = 'public'
     and d.objid is null
     and c.relkind in ('r', 'v', 'm', 'p', 'f', 'S');
  if v_n <> 0 then
    raise exception 'FALLO 0028-1A: % relación(es) propias en public', v_n;
  end if;

  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_depend d on d.objid = p.oid and d.deptype = 'e'
   where n.nspname = 'public' and d.objid is null;
  if v_n <> 0 then
    raise exception 'FALLO 0028-1A: % función(es) propias en public', v_n;
  end if;

  select count(*) into v_n
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    left join pg_depend d on d.objid = t.oid and d.deptype = 'e'
   where n.nspname = 'public' and t.typtype in ('e', 'd') and d.objid is null;
  if v_n <> 0 then
    raise exception 'FALLO 0028-1A: % tipo(s) propios en public', v_n;
  end if;

  -- Ninguna de las 17 tablas del legacy sobrevive, ni la tabla de identidad.
  if to_regclass('public.usuarios') is not null then
    raise exception 'FALLO 0028-1A: sigue existiendo public.usuarios';
  end if;
  if to_regclass('public.viajes') is not null then
    raise exception 'FALLO 0028-1A: sigue existiendo public.viajes';
  end if;
  if to_regclass('public._migraciones') is not null then
    raise exception 'FALLO 0028-1A: sigue existiendo public._migraciones';
  end if;

  raise notice 'OK 0028-1A public sin relaciones, funciones ni tipos propios';
end $$;

\echo '0028-1B: la identidad no escribe más en public'
do $$
declare
  v_n integer;
begin
  if to_regprocedure('public.handle_new_user()') is not null then
    raise exception 'FALLO 0028-1B: sigue existiendo public.handle_new_user()';
  end if;
  if to_regclass('auth.users') is not null then
    select count(*) into v_n
      from pg_trigger
     where tgrelid = 'auth.users'::regclass
       and tgname = 'on_auth_user_created';
    if v_n <> 0 then
      raise exception 'FALLO 0028-1B: el trigger on_auth_user_created sigue activo';
    end if;
  end if;
  raise notice 'OK 0028-1B sin handle_new_user ni trigger en auth.users';
end $$;

\echo '0028-1C: el núcleo conserva sus garantías gist'
do $$
declare
  v_n integer;
begin
  if not exists (select 1 from pg_extension where extname = 'btree_gist') then
    raise exception 'FALLO 0028-1C: falta la extensión btree_gist';
  end if;
  select count(*) into v_n
    from pg_constraint
   where contype = 'x' and connamespace = 'nucleo'::regnamespace;
  if v_n <> 4 then
    raise exception 'FALLO 0028-1C: % de 4 EXCLUDE en nucleo', v_n;
  end if;
  -- Los 3 EXCLUDE del libro de ocupación siguen nombrados igual (INV-001).
  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.reservas_recurso'::regclass
     and conname in ('ex_reserva_tracto', 'ex_reserva_rampla', 'ex_reserva_chofer');
  if v_n <> 3 then
    raise exception 'FALLO 0028-1C: % de 3 EXCLUDE de reservas_recurso', v_n;
  end if;
  raise notice 'OK 0028-1C btree_gist + 4 EXCLUDE (3 de reservas_recurso) intactos';
end $$;

\echo '0028-1D: rol real tei_app sin USAGE en public'
do $$
declare
  v_uso_public boolean;
  v_uso_nucleo boolean;
begin
  select has_schema_privilege('tei_app', 'public', 'USAGE'),
         has_schema_privilege('tei_app', 'nucleo', 'USAGE')
    into v_uso_public, v_uso_nucleo;
  if v_uso_public then
    raise exception 'FALLO 0028-1D: tei_app conserva USAGE en public';
  end if;
  if not v_uso_nucleo then
    raise exception 'FALLO 0028-1D: tei_app perdió USAGE en nucleo';
  end if;

  -- Con el rol de la app, tocar `public` da 42501 (defecto seguro), no 42P01.
  set local role tei_app;
  begin
    perform 1 from public.viajes limit 1;
    raise exception 'FALLO 0028-1D: tei_app pudo consultar public.viajes';
  exception when insufficient_privilege then
    raise notice 'OK 0028-1D tei_app => public.viajes da 42501';
  end;
  reset role;
end $$;

\echo '0028-1E: tei_app sigue escribiendo en nucleo con EXCLUDE gist'
do $$
declare
  v_tei constant uuid := '11111111-1111-1111-1111-111111111111';
  v_n   integer;
begin
  set local role tei_app;
  perform set_config('app.empresa_id', v_tei::text, true);

  -- `configuracion_empresa` tiene EXCLUDE USING gist (gbtreekey32, gbtreekey_var).
  insert into nucleo.configuracion_empresa (empresa_id, clave, valor)
  values (v_tei, 'clave_prueba_0028', to_jsonb('ok'::text));

  select count(*) into v_n
    from nucleo.configuracion_empresa where clave = 'clave_prueba_0028';
  if v_n <> 1 then
    raise exception 'FALLO 0028-1E: tei_app no ve su propia fila (% filas)', v_n;
  end if;
  reset role;
  raise notice 'OK 0028-1E tei_app insertó en nucleo.configuracion_empresa (EXCLUDE gist)';
end $$;

\echo '0028-1F: el esquema public se conserva y el bucket de respaldos sigue'
do $$
declare
  v_n integer;
begin
  select count(*) into v_n from pg_namespace where nspname = 'public';
  if v_n <> 1 then
    raise exception 'FALLO 0028-1F: no existe el esquema public';
  end if;
  if to_regclass('storage.buckets') is not null then
    select count(*) into v_n from storage.buckets where id = 'respaldos';
    if v_n <> 1 then
      raise exception 'FALLO 0028-1F: falta el bucket respaldos';
    end if;
  end if;
  raise notice 'OK 0028-1F esquema public conservado; bucket respaldos intacto';
end $$;

rollback;

\echo '0028-1: OK (rollback; 0 filas residuales)'
