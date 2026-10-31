-- ============================================================================
-- Rollback de 0020 — quita el aislamiento RLS sin tocar datos
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0020_rls_multiempresa.sql: políticas, FORCE,
-- GRANTs y funciones de contexto. NO borra tablas, filas ni índices, y no toca
-- ninguna migración anterior.
--
-- El rol `tei_app` es de CLÚSTER: por defecto este script lo deja sin privilegios
-- (suficiente para desactivar el aislamiento) y lo conserva, porque otra base
-- puede estar usándolo. Para borrarlo, pasar la variable:
--
--   psql "$URL" -v drop_role=1 -v ON_ERROR_STOP=1 -f supabase/tests/0020_99_rollback.sql
--
-- Si el backend ya conecta como `tei_app`, este rollback lo deja sin acceso:
-- hay que volver `DATABASE_URL` a `postgres` en el mismo despliegue.
--
-- Requiere un rol con privilegios de dueño del esquema (postgres/supabase_admin).
-- ============================================================================

\set ON_ERROR_STOP on

begin;

-- 1) quitar FORCE
do $$
declare
  r record;
begin
  for r in
    select c.relname
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'nucleo' and c.relkind = 'r'
     order by c.relname
  loop
    execute format('alter table nucleo.%I no force row level security', r.relname);
  end loop;
end
$$;

-- 2) borrar TODAS las políticas del esquema (antes de 0020 no había ninguna)
do $$
declare
  r record;
  n int := 0;
begin
  for r in select tablename, policyname from pg_policies where schemaname = 'nucleo' loop
    execute format('drop policy %I on nucleo.%I', r.policyname, r.tablename);
    n := n + 1;
  end loop;
  raise notice 'rollback 0020: % políticas eliminadas', n;
end
$$;

-- 3) revocar privilegios del rol de aplicación (si existe)
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'tei_app') then
    execute 'revoke all on all tables in schema nucleo from tei_app';
    execute 'revoke all on all sequences in schema nucleo from tei_app';
    execute 'revoke all on all functions in schema nucleo from tei_app';
    execute 'revoke usage on schema nucleo from tei_app';
  end if;
end
$$;

-- 4) funciones de contexto (dependen solo de 0020)
drop function if exists nucleo.empresas_del_usuario();
drop function if exists nucleo.ctx_auth_id();
drop function if exists nucleo.ctx_empresa();

commit;

-- 5) rol (opcional; roles son de clúster)
\if :{?drop_role}
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'tei_app') then
    execute 'drop owned by tei_app';
    execute 'drop role tei_app';
    raise notice 'rollback 0020: rol tei_app eliminado';
  end if;
end
$$;
\endif

\echo '0020_99_rollback: OK (datos intactos)'
