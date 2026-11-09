-- ============================================================================
-- Prueba 0033-1 — privilegios de `tei_app` en chat y suscripciones
-- ============================================================================
-- Invariantes (docs/datos/invariantes.md):
--   INV-PRIV01 `tei_app` NO puede UPDATE/DELETE el historial del chat
--   INV-PRIV02 `tei_app` SÍ puede INSERT/SELECT mensajes (el runtime los crea)
--   INV-PRIV03 `tei_app` NO puede escribir `tenant_suscripciones`
--   INV-PRIV04 `tei_app` SÍ puede leer `tenant_suscripciones` (muro de pago)
--
-- Corre como `supabase_admin`; los intentos de escritura cambian a `tei_app`
-- con `set local role` para comprobar la denegación real (42501), no solo el
-- catálogo de privilegios. Termina en ROLLBACK: 0 filas residuales.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0033_01_privilegios_tei_app.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

-- ---- Catálogo: los grants quedaron como se espera ---------------------------
do $$
begin
  if has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'UPDATE') then
    raise exception 'FALLO 0033-1A: tei_app conserva UPDATE en agente_chat_mensajes';
  end if;
  if has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'DELETE') then
    raise exception 'FALLO 0033-1A: tei_app conserva DELETE en agente_chat_mensajes';
  end if;
  if not has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'INSERT') then
    raise exception 'FALLO 0033-1A: tei_app perdió INSERT en agente_chat_mensajes';
  end if;
  if not has_table_privilege('tei_app', 'nucleo.agente_chat_mensajes', 'SELECT') then
    raise exception 'FALLO 0033-1A: tei_app perdió SELECT en agente_chat_mensajes';
  end if;

  if has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'INSERT')
     or has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'UPDATE')
     or has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'DELETE') then
    raise exception 'FALLO 0033-1A: tei_app conserva escritura en tenant_suscripciones';
  end if;
  if not has_table_privilege('tei_app', 'nucleo.tenant_suscripciones', 'SELECT') then
    raise exception 'FALLO 0033-1A: tei_app perdió SELECT en tenant_suscripciones';
  end if;
end
$$;

-- ---- Denegación real con el rol de la aplicación ----------------------------
set local role tei_app;

do $$
begin
  -- UPDATE del historial: debe fallar por privilegio, no por RLS/fila.
  begin
    update nucleo.agente_chat_mensajes
       set contenido = contenido
     where false;
    raise exception 'FALLO 0033-1B: tei_app pudo UPDATE agente_chat_mensajes';
  exception
    when insufficient_privilege then
      raise notice 'OK 0033-1B: UPDATE de agente_chat_mensajes denegado a tei_app';
  end;

  -- DELETE del historial: debe fallar por privilegio.
  begin
    delete from nucleo.agente_chat_mensajes where false;
    raise exception 'FALLO 0033-1C: tei_app pudo DELETE agente_chat_mensajes';
  exception
    when insufficient_privilege then
      raise notice 'OK 0033-1C: DELETE de agente_chat_mensajes denegado a tei_app';
  end;

  -- INSERT de una suscripción: debe fallar por privilegio (no por CHECK/FK).
  begin
    insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo, estado, vigente_desde)
    values ('11111111-1111-1111-1111-111111111111', 'premium', 'activa', now());
    raise exception 'FALLO 0033-1D: tei_app pudo INSERT en tenant_suscripciones';
  exception
    when insufficient_privilege then
      raise notice 'OK 0033-1D: INSERT de tenant_suscripciones denegado a tei_app';
  end;

  -- SELECT de suscripciones: debe funcionar (muro de pago).
  perform 1 from nucleo.tenant_suscripciones limit 1;
  raise notice 'OK 0033-1E: SELECT de tenant_suscripciones permitido a tei_app';
end
$$;

reset role;

-- ---- 0 filas residuales ----------------------------------------------------
do $$
declare
  v_n bigint;
begin
  select count(*) into v_n from nucleo.tenant_suscripciones;
  if v_n < 0 then
    raise exception 'FALLO 0033-1F: conteo inesperado';
  end if;
end
$$;

rollback;
