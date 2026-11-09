-- ============================================================================
-- Rollback de 0031 — retira la memoria del chat in-app
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0031_agente_chat_inapp.sql:
--   drop trigger  trg_agente_chat_conv_* / trg_agente_chat_msg_* (si existen)
--   drop table    nucleo.agente_chat_mensajes
--   drop table    nucleo.agente_chat_conversaciones
-- Con las tablas caen PK, UNIQUE (empresa_id, id), FKs compuestas, CHECKs,
-- índices parciales, triggers, políticas, RLS y GRANTs.
--
-- NO toca:
--   · nucleo.empresas ni nucleo.usuarios_empresa (solo se les quitan FKs que
--     apuntaban a ellas),
--   · nucleo.conversaciones / nucleo.conversacion_mensajes (WhatsApp, 0021),
--   · nucleo.solicitudes ni ninguna otra tabla de negocio,
--   · las funciones compartidas fn_touch/fn_version (0004),
--   · nucleo.auditoria (append-only por diseño: sus filas NO se borran).
--
-- PÉRDIDA PREVISTA: el historial de chat in-app escrito. Al aplicar 0031 no
-- hay ninguna fila; si ya hay conversaciones reales, expórtelas y exija
-- autorización del dueño antes de revertir.
--
-- Es idempotente: si los objetos no existen, avisa y termina sin error.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0031_99_rollback.sql
--   (mismo comando con -d postgres para la base de la app, solo con autorización)
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_filas bigint := 0;
  v_n     integer;
  v_trg   text;
begin
  -- Triggers primero (idempotente; si la tabla no existe, no hay trigger).
  if to_regclass('nucleo.agente_chat_conversaciones') is not null then
    foreach v_trg in array array[
      'trg_agente_chat_conv_touch', 'trg_agente_chat_conv_version'
    ] loop
      execute format('drop trigger if exists %I on nucleo.agente_chat_conversaciones', v_trg);
    end loop;
  end if;
  if to_regclass('nucleo.agente_chat_mensajes') is not null then
    foreach v_trg in array array[
      'trg_agente_chat_msg_touch', 'trg_agente_chat_msg_version'
    ] loop
      execute format('drop trigger if exists %I on nucleo.agente_chat_mensajes', v_trg);
    end loop;
  end if;

  -- Mensajes primero: la FK RESTRICT apunta a conversaciones.
  if to_regclass('nucleo.agente_chat_mensajes') is not null then
    execute 'select count(*) from nucleo.agente_chat_mensajes' into v_filas;
    execute 'drop table nucleo.agente_chat_mensajes';
    raise notice '0031-99: agente_chat_mensajes eliminada; % fila(s) perdidas', v_filas;
  else
    raise notice '0031-99: nucleo.agente_chat_mensajes no existe';
  end if;

  if to_regclass('nucleo.agente_chat_conversaciones') is not null then
    execute 'select count(*) from nucleo.agente_chat_conversaciones' into v_filas;
    execute 'drop table nucleo.agente_chat_conversaciones';
    raise notice '0031-99: agente_chat_conversaciones eliminada; % fila(s) perdidas', v_filas;
  else
    raise notice '0031-99: nucleo.agente_chat_conversaciones no existe';
  end if;

  -- ---- Verificación: 0 objetos de 0031 -----------------------------------
  if to_regclass('nucleo.agente_chat_conversaciones') is not null
     or to_regclass('nucleo.agente_chat_mensajes') is not null then
    raise exception '0031-99 FALLO: quedan tablas de 0031';
  end if;

  select count(*) into v_n
    from pg_trigger
   where tgname in ('trg_agente_chat_conv_touch', 'trg_agente_chat_conv_version',
                    'trg_agente_chat_msg_touch', 'trg_agente_chat_msg_version')
     and not tgisinternal;
  if v_n <> 0 then
    raise exception '0031-99 FALLO: quedan % triggers de 0031', v_n;
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('agente_chat_conversaciones', 'agente_chat_mensajes');
  if v_n <> 0 then
    raise exception '0031-99 FALLO: quedan % políticas de 0031', v_n;
  end if;

  select count(*) into v_n
    from pg_indexes
   where schemaname = 'nucleo'
     and indexname in ('uq_agente_chat_conv_activa', 'uq_agente_chat_msg_idempotencia',
                       'idx_agente_chat_conv_usuario', 'idx_agente_chat_msg_conversacion');
  if v_n <> 0 then
    raise exception '0031-99 FALLO: quedan % índices de 0031', v_n;
  end if;

  -- Las tablas que NO se tocan siguen existiendo.
  if to_regclass('nucleo.empresas') is null
     or to_regclass('nucleo.usuarios_empresa') is null
     or to_regclass('nucleo.conversaciones') is null
     or to_regclass('nucleo.conversacion_mensajes') is null
     or to_regclass('nucleo.solicitudes') is null then
    raise exception '0031-99 FALLO: se perdió una tabla que no debía tocarse';
  end if;

  raise notice '0031-99: OK; 0 objetos de 0031; empresas/usuarios/WhatsApp/solicitudes intactos';
end
$$;

commit;

\echo '0031-99: OK (rollback aplicado; re-aplicar 0031 para volver al estado anterior)'
