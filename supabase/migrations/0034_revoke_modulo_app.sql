-- ============================================================================
-- TRANSTEI — Migración 0034: retirar EXECUTE de la función de módulos a tei_app
-- ============================================================================
-- Objetivo (revisión Ola 4, SEC-066 residual):
--   `nucleo.admin_set_modulo_empresa` es una operación de plataforma. El endpoint
--   HTTP del tenant se retiró en esta misma entrega, pero `tei_app` conservaba
--   `EXECUTE` (0029:270): un runtime comprometido o SQLi podía encender el flag
--   de `modulos_empresa` con el `ctx_empresa()` de su propia empresa.
--
-- Cambio:
--   revoke execute on function nucleo.admin_set_modulo_empresa(uuid, text, boolean)
--     from public, tei_app;
--   PostgreSQL concede EXECUTE a PUBLIC por defecto; revocar solo a `tei_app`
--   no alcanza. `postgres`/`supabase_admin` y el rol dueño conservan la ejecución;
--   la activación queda para el futuro rol de plataforma (RA-16).
--
-- Precondiciones: existen el rol tei_app y la función (0029 aplicada).
--
-- Impacto: solo privilegios; no toca datos. Ninguna ruta de `backend/app` llama
-- a esta función desde la retirada del endpoint (verificado 2026-11-09).
--
-- Rollback: `supabase/tests/0034_99_rollback.sql` restaura EXECUTE a tei_app
-- dentro de una transacción y hace ROLLBACK (simulación).
--
-- Prueba: `supabase/tests/0034_01_revoke_modulo_app.sql` (42501 real con
-- `set role tei_app`).
-- ============================================================================

begin;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'tei_app') then
    raise exception '0034: falta el rol tei_app (bootstrap de roles)';
  end if;
  if to_regprocedure('nucleo.admin_set_modulo_empresa(uuid, text, boolean)') is null then
    raise exception '0034: falta nucleo.admin_set_modulo_empresa (0029)';
  end if;
end
$$;

revoke execute on function nucleo.admin_set_modulo_empresa(uuid, text, boolean)
  from public, tei_app;

do $$
begin
  if has_function_privilege(
       'tei_app',
       'nucleo.admin_set_modulo_empresa(uuid, text, boolean)',
       'EXECUTE'
     ) then
    raise exception 'VERIFICACIÓN 0034: tei_app conserva EXECUTE en admin_set_modulo_empresa';
  end if;
end
$$;

commit;
