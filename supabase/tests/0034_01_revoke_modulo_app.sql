-- ============================================================================
-- Prueba 0034-1 — `tei_app` no puede ejecutar la función de módulos
-- ============================================================================
-- Invariante: INV-PRIV05 `tei_app` sin EXECUTE en
-- `nucleo.admin_set_modulo_empresa`; la activación es de plataforma (RA-16).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0034_01_revoke_modulo_app.sql
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
    raise exception 'FALLO 0034-1A: tei_app conserva EXECUTE en admin_set_modulo_empresa';
  end if;
  if not has_function_privilege(
       'postgres',
       'nucleo.admin_set_modulo_empresa(uuid, text, boolean)',
       'EXECUTE'
     ) then
    raise exception 'FALLO 0034-1A: postgres perdió EXECUTE en admin_set_modulo_empresa';
  end if;
end
$$;

set local role tei_app;

do $$
begin
  begin
    perform nucleo.admin_set_modulo_empresa(
      '11111111-1111-1111-1111-111111111111'::uuid,
      'agente-whatsapp',
      true
    );
    raise exception 'FALLO 0034-1B: tei_app pudo ejecutar admin_set_modulo_empresa';
  exception
    when insufficient_privilege then
      raise notice 'OK 0034-1B: EXECUTE de admin_set_modulo_empresa denegado a tei_app';
  end;
end
$$;

reset role;
rollback;
