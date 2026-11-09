-- ============================================================================
-- Rollback de 0034 — SIMULACIÓN no destructiva: restaura EXECUTE a tei_app
-- ============================================================================
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0034_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
begin
  if has_function_privilege(
       'tei_app',
       'nucleo.admin_set_modulo_empresa(uuid, text, boolean)',
       'EXECUTE'
     ) then
    raise exception '0034-99: el estado de partida ya tiene EXECUTE; nada que simular';
  end if;
end
$$;

grant execute on function nucleo.admin_set_modulo_empresa(uuid, text, boolean)
  to public;

do $$
begin
  if not has_function_privilege(
       'tei_app',
       'nucleo.admin_set_modulo_empresa(uuid, text, boolean)',
       'EXECUTE'
     ) then
    raise exception '0034-99: el rollback no restauró EXECUTE';
  end if;
end
$$;

rollback;
