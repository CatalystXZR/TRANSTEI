-- ============================================================================
-- Rollback de 0033 — SIMULACIÓN no destructiva: restaura los GRANT previos
-- ============================================================================
-- Revierte exactamente lo que cambia 0033_privilegios_tei_app.sql:
--   grant update, delete on nucleo.agente_chat_mensajes to tei_app;
--   grant insert, update on nucleo.tenant_suscripciones to tei_app;
-- (0030/0031 no concedían DELETE a `tei_app`; el rollback lo restaura por
-- simetría solo dentro de la transacción y hace ROLLBACK, sin dejar efecto).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0033_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

-- Estado endurecido (lo que aplica 0033).
do $$
begin
  if has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'UPDATE') then
    raise exception '0033-99: el estado de partida ya tiene UPDATE; nada que simular';
  end if;
end
$$;

-- Simulación del rollback: devuelve los grants originales.
grant update on table nucleo.agente_chat_mensajes to tei_app;
grant insert, update on table nucleo.tenant_suscripciones to tei_app;

do $$
begin
  if not has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'UPDATE') then
    raise exception '0033-99: el rollback no restauró UPDATE en agente_chat_mensajes';
  end if;
  if not has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'INSERT') then
    raise exception '0033-99: el rollback no restauró INSERT en tenant_suscripciones';
  end if;
end
$$;

-- No se conserva el rollback: la migración sigue aplicada.
rollback;
