-- ============================================================================
-- TRANSTEI — Migración 0033: privilegios de `tei_app` en chat y suscripciones
-- ============================================================================
-- Objetivo (revisión independiente 2026-11-09):
--   SEC-056  `tei_app` conserva UPDATE sobre el historial del chat; el historial
--            debe ser append-only para el rol de la aplicación.
--   SEC-068  `tei_app` conserva INSERT/UPDATE sobre `tenant_suscripciones`, la
--            tabla que autoriza el muro de pago. La app solo la lee.
--
-- Cambios (idempotentes, solo privilegios; no toca datos ni DDL de tablas):
--   · revoke update, delete on nucleo.agente_chat_mensajes from tei_app
--   · revoke insert, update, delete on nucleo.tenant_suscripciones from tei_app
--   · se conserva INSERT/SELECT en mensajes y SELECT en suscripciones
--   · `postgres` (plataforma) conserva todos los privilegios
--
-- Precondiciones (abortan si no se cumplen):
--   · existen el rol `tei_app` y las tablas `nucleo.agente_chat_mensajes` /
--     `nucleo.tenant_suscripciones` (migraciones 0030/0031 aplicadas).
--
-- Impacto y locks: solo `REVOKE`; toma locks de catálogo breves. No reescribe
-- filas. El runtime del chat solo INSERTA mensajes y LEE suscripciones; ninguna
-- ruta de la aplicación hace UPDATE/DELETE sobre estas tablas (verificado con
-- `grep` en backend/app el 2026-11-09).
--
-- Rollback: `0033_99_rollback.sql` restaura exactamente los GRANT previos:
--   grant select, insert, update on nucleo.agente_chat_mensajes to tei_app;
--   grant select, insert, update on nucleo.tenant_suscripciones to tei_app;
-- (DELETE no estaba concedido a `tei_app` en 0030/0031.)
--
-- Compatibilidad: `nucleo` y el frontend no cambian. Las pruebas HTTP del chat
-- siguen pasando porque insertan mensajes y leen suscripciones.
--
-- Pruebas: `supabase/tests/0033_01_privilegios_tei_app.sql` (denegación real con
-- `set role tei_app`) y `supabase/tests/0033_99_rollback.sql`.
-- ============================================================================

begin;

-- ---- Precondiciones ---------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'tei_app') then
    raise exception '0033: falta el rol tei_app (bootstrap de roles)';
  end if;
  if to_regclass('nucleo.agente_chat_mensajes') is null then
    raise exception '0033: falta nucleo.agente_chat_mensajes (0031)';
  end if;
  if to_regclass('nucleo.tenant_suscripciones') is null then
    raise exception '0033: falta nucleo.tenant_suscripciones (0030)';
  end if;
end
$$;

-- ---- SEC-056: historial del chat append-only para tei_app --------------------
revoke update, delete on table nucleo.agente_chat_mensajes from tei_app;
grant select, insert on table nucleo.agente_chat_mensajes to tei_app;

-- ---- SEC-068: la suscripción la escribe la plataforma, no la app -------------
revoke insert, update, delete on table nucleo.tenant_suscripciones from tei_app;
grant select on table nucleo.tenant_suscripciones to tei_app;

-- ---- Verificación -----------------------------------------------------------
do $$
begin
  if has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'UPDATE')
     or has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'DELETE') then
    raise exception 'VERIFICACIÓN 0033: tei_app conserva UPDATE/DELETE en agente_chat_mensajes';
  end if;
  if not has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'SELECT') then
    raise exception 'VERIFICACIÓN 0033: tei_app perdió INSERT/SELECT en agente_chat_mensajes';
  end if;

  if has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'INSERT')
     or has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'UPDATE')
     or has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'DELETE') then
    raise exception 'VERIFICACIÓN 0033: tei_app conserva escritura en tenant_suscripciones';
  end if;
  if not has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'SELECT') then
    raise exception 'VERIFICACIÓN 0033: tei_app perdió SELECT en tenant_suscripciones';
  end if;
end
$$;

commit;
