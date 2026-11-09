-- ============================================================================
-- Prueba 0031-1 — chat in-app: unicidad activa, FKs por empresa, roles LLM e
--                 idempotencia del turno
-- ============================================================================
-- Invariantes (docs/datos/invariantes.md §15):
--   INV-CHAT01 una conversación activa por (empresa, usuario, agente)
--   INV-CHAT02 `activa` y `cerrada_en` son coherentes
--   INV-CHAT03 el usuario de la conversación es de la misma empresa (FK compuesta)
--   INV-CHAT04 el mensaje pertenece a una conversación de la misma empresa
--   INV-CHAT05 un turno `tool` declara `tool_call_id`
--   INV-CHAT06 un turno deja contenido o `tool_calls` (tool/system exentos)
--   INV-CHAT07 una `clave_idempotencia` no se repite dentro de la empresa
--   INV-CHAT08 con el rol tei_app, dos empresas no se ven
--   INV-CHAT09 tei_app no puede borrar conversaciones ni mensajes
--
-- Corre como `supabase_admin` (BYPASSRLS) para probar constraints/triggers.
-- El aislamiento exhaustivo con el rol real está en 0031_02_rls_tei_app.sql;
-- aquí hay un bloque acotado con `set local role tei_app`.
--
-- TODO termina en ROLLBACK: 0 filas residuales.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0031_01_chat.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_tei      constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes      constant uuid := '22222222-2222-2222-2222-222222222222';
  v_usr_tei  uuid;
  v_usr_tes  uuid;
  v_conv_tei uuid;
  v_conv_sec uuid;
  v_conv_new uuid;
  v_conv_tes uuid;
  v_msg      uuid;
  v_id       uuid;
  v_n        integer;
  v_ver      integer;
  v_ts       timestamptz;
begin
  -- ---- 0. Mecanismo en la base --------------------------------------------
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('agente_chat_conversaciones', 'agente_chat_mensajes')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 2 then
    raise exception 'FALLO 0031-1A: RLS+FORCE en % de 2 tablas', v_n;
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('agente_chat_conversaciones', 'agente_chat_mensajes')
     and policyname = 'tenant_empresa'
     and coalesce(qual, '') like '%ctx_empresa%'
     and coalesce(with_check, '') like '%ctx_empresa%';
  if v_n <> 2 then
    raise exception 'FALLO 0031-1A: % de 2 políticas tenant_empresa con ctx_empresa', v_n;
  end if;

  if to_regclass('nucleo.uq_agente_chat_conv_activa') is null
     or to_regclass('nucleo.uq_agente_chat_msg_idempotencia') is null then
    raise exception 'FALLO 0031-1A: faltan los UNIQUE parciales de 0031';
  end if;

  select count(*) into v_n
    from pg_trigger
   where not tgisinternal
     and tgname in ('trg_agente_chat_conv_touch', 'trg_agente_chat_conv_version',
                    'trg_agente_chat_msg_touch', 'trg_agente_chat_msg_version');
  if v_n <> 4 then
    raise exception 'FALLO 0031-1A: % de 4 triggers de 0031', v_n;
  end if;

  -- No debe existir trigger de auditoría en estas tablas (decisión explícita).
  select count(*) into v_n
    from pg_trigger
   where not tgisinternal
     and tgrelid in ('nucleo.agente_chat_conversaciones'::regclass,
                     'nucleo.agente_chat_mensajes'::regclass)
     and tgname like '%audit%';
  if v_n <> 0 then
    raise exception 'FALLO 0031-1A: hay % trigger(s) de auditoría (no corresponden)', v_n;
  end if;

  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.agente_chat_conversaciones'::regclass
     and contype = 'f' and confrelid = 'nucleo.usuarios_empresa'::regclass;
  if v_n <> 1 then
    raise exception 'FALLO 0031-1A: falta la FK compuesta a usuarios_empresa';
  end if;

  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.agente_chat_mensajes'::regclass
     and contype = 'f' and confrelid = 'nucleo.agente_chat_conversaciones'::regclass;
  if v_n <> 1 then
    raise exception 'FALLO 0031-1A: falta la FK compuesta a agente_chat_conversaciones';
  end if;
  raise notice 'OK 0031-1A mecanismo: RLS+FORCE, 2 políticas, UNIQUE parciales, 4 triggers, 2 FKs compuestas';

  -- ---- 1. Fixtures: un miembro del núcleo por empresa ---------------------
  select id into v_usr_tei from nucleo.usuarios_empresa
   where empresa_id = v_tei order by id limit 1;
  select id into v_usr_tes from nucleo.usuarios_empresa
   where empresa_id = v_tes order by id limit 1;
  if v_usr_tei is null or v_usr_tes is null then
    raise exception 'ENTORNO 0031-1: faltan usuarios_empresa de TEI/TES en el seed';
  end if;

  -- ---- 2. Conversación válida (gerente) -----------------------------------
  insert into nucleo.agente_chat_conversaciones
    (empresa_id, usuario_empresa_id, agente)
  values (v_tei, v_usr_tei, 'gerente')
  returning id into v_conv_tei;

  insert into nucleo.agente_chat_conversaciones
    (empresa_id, usuario_empresa_id, agente)
  values (v_tei, v_usr_tei, 'secretaria')
  returning id into v_conv_sec;
  raise notice 'OK 0031-1B conversaciones válidas: gerente y secretaria';

  -- ---- 3. INV-CHAT01: segunda activa del mismo usuario+agente -------------
  begin
    insert into nucleo.agente_chat_conversaciones
      (empresa_id, usuario_empresa_id, agente)
    values (v_tei, v_usr_tei, 'gerente');
    raise exception 'FALLO 0031-1C: se aceptaron dos conversaciones activas del mismo agente';
  exception when unique_violation then
    raise notice 'OK 0031-1C segunda activa (empresa, usuario, agente) => 23505';
  end;

  -- ---- 4. INV-CHAT02: activa=false exige cerrada_en ----------------------
  begin
    insert into nucleo.agente_chat_conversaciones
      (empresa_id, usuario_empresa_id, agente, activa)
    values (v_tei, v_usr_tei, 'gerente', false);
    raise exception 'FALLO 0031-1D: se aceptó activa=false sin cerrada_en';
  exception when check_violation then
    raise notice 'OK 0031-1D activa=false sin cerrada_en => 23514';
  end;

  insert into nucleo.agente_chat_conversaciones
    (empresa_id, usuario_empresa_id, agente, activa, cerrada_en)
  values (v_tei, v_usr_tei, 'gerente', false, now());

  -- Borde: al cerrar la activa, el índice parcial libera el par y se puede
  -- abrir una sesión nueva del mismo agente.
  update nucleo.agente_chat_conversaciones
     set activa = false, cerrada_en = now()
   where id = v_conv_tei;

  insert into nucleo.agente_chat_conversaciones
    (empresa_id, usuario_empresa_id, agente)
  values (v_tei, v_usr_tei, 'gerente')
  returning id, abierta_en into v_conv_new, v_ts;
  raise notice 'OK 0031-1D borde: sesión nueva tras cerrar la anterior permitida';

  -- ---- 5. INV-CHAT03: usuario de otra empresa ----------------------------
  begin
    insert into nucleo.agente_chat_conversaciones
      (empresa_id, usuario_empresa_id, agente)
    values (v_tei, v_usr_tes, 'gerente');
    raise exception 'FALLO 0031-1E: se aceptó un usuario de TES en una conversación TEI';
  exception when foreign_key_violation then
    raise notice 'OK 0031-1E usuario de otra empresa => 23503';
  end;

  -- ---- 6. Conversación y mensajes de TES (para idempotencia por empresa) --
  insert into nucleo.agente_chat_conversaciones
    (empresa_id, usuario_empresa_id, agente)
  values (v_tes, v_usr_tes, 'gerente')
  returning id into v_conv_tes;

  -- ---- 7. INV-CHAT05/06: roles LLM y forma del turno ---------------------
  insert into nucleo.agente_chat_mensajes
    (empresa_id, conversacion_id, rol, contenido, clave_idempotencia)
  values (v_tei, v_conv_new, 'user', '¿Cuánto facturamos esta semana?', 'cli-001')
  returning id into v_msg;

  begin
    insert into nucleo.agente_chat_mensajes
      (empresa_id, conversacion_id, rol, contenido)
    values (v_tei, v_conv_new, 'tool', null);
    raise exception 'FALLO 0031-1F: se aceptó un turno tool sin tool_call_id';
  exception when check_violation then
    raise notice 'OK 0031-1F turno tool sin tool_call_id => 23514';
  end;

  begin
    insert into nucleo.agente_chat_mensajes
      (empresa_id, conversacion_id, rol)
    values (v_tei, v_conv_new, 'assistant');
    raise exception 'FALLO 0031-1F: se aceptó un turno assistant sin contenido ni tool_calls';
  exception when check_violation then
    raise notice 'OK 0031-1F assistant sin contenido ni tool_calls => 23514';
  end;

  insert into nucleo.agente_chat_mensajes
    (empresa_id, conversacion_id, rol, tool_call_id, nombre_herramienta)
  values (v_tei, v_conv_new, 'tool', 'call_abc123', 'facturacion_semana');

  insert into nucleo.agente_chat_mensajes
    (empresa_id, conversacion_id, rol)
  values (v_tei, v_conv_new, 'system');
  raise notice 'OK 0031-1F tool con tool_call_id y system sin contenido aceptados';

  -- ---- 8. INV-CHAT04: mensaje con conversación de otra empresa ------------
  begin
    insert into nucleo.agente_chat_mensajes
      (empresa_id, conversacion_id, rol, contenido)
    values (v_tei, v_conv_tes, 'user', 'cruzado');
    raise exception 'FALLO 0031-1G: se aceptó un mensaje TEI en una conversación TES';
  exception when foreign_key_violation then
    raise notice 'OK 0031-1G mensaje con conversación de otra empresa => 23503';
  end;

  -- ---- 9. INV-CHAT07: idempotencia por empresa ---------------------------
  begin
    insert into nucleo.agente_chat_mensajes
      (empresa_id, conversacion_id, rol, contenido, clave_idempotencia)
    values (v_tei, v_conv_new, 'user', 'reintento', 'cli-001');
    raise exception 'FALLO 0031-1H: se duplicó la clave_idempotencia en la misma empresa';
  exception when unique_violation then
    raise notice 'OK 0031-1H clave_idempotencia repetida en la empresa => 23505';
  end;

  insert into nucleo.agente_chat_mensajes
    (empresa_id, conversacion_id, rol, contenido, clave_idempotencia)
  values (v_tes, v_conv_tes, 'user', 'misma clave, otra empresa', 'cli-001');
  raise notice 'OK 0031-1H la misma clave en otra empresa convive (alcance por empresa)';

  -- ---- 10. touch/version en mensajes -------------------------------------
  update nucleo.agente_chat_mensajes
     set metadata = jsonb_build_object('tokens', 42)
   where id = v_msg
  returning version into v_ver;
  if v_ver <> 2 then
    raise exception 'FALLO 0031-1I: version esperada 2 en el mensaje, quedó %', v_ver;
  end if;
  raise notice 'OK 0031-1I touch+version en mensajes: version = 2';

  -- ---- 11. INV-CHAT08 acotado: con tei_app, dos empresas no se ven --------
  set local role tei_app;

  perform set_config('app.empresa_id', v_tei::text, true);
  select count(*) into v_n from nucleo.agente_chat_conversaciones where empresa_id = v_tes;
  if v_n <> 0 then
    raise exception 'FALLO 0031-1J: TEI ve % conversaciones de TES', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_chat_mensajes where empresa_id = v_tes;
  if v_n <> 0 then
    raise exception 'FALLO 0031-1J: TEI ve % mensajes de TES', v_n;
  end if;

  perform set_config('app.empresa_id', v_tes::text, true);
  select count(*) into v_n from nucleo.agente_chat_conversaciones where empresa_id = v_tei;
  if v_n <> 0 then
    raise exception 'FALLO 0031-1J: TES ve % conversaciones de TEI', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_chat_mensajes where empresa_id = v_tei;
  if v_n <> 0 then
    raise exception 'FALLO 0031-1J: TES ve % mensajes de TEI', v_n;
  end if;

  -- ---- 12. INV-CHAT09: DELETE denegado por privilegio --------------------
  begin
    delete from nucleo.agente_chat_conversaciones where id = v_conv_tes;
    raise exception 'FALLO 0031-1K: tei_app pudo borrar una conversación';
  exception when insufficient_privilege then
    raise notice 'OK 0031-1K DELETE de conversación con tei_app => 42501';
  end;

  begin
    delete from nucleo.agente_chat_mensajes where id = v_msg;
    raise exception 'FALLO 0031-1K: tei_app pudo borrar un mensaje';
  exception when insufficient_privilege then
    raise notice 'OK 0031-1K DELETE de mensaje con tei_app => 42501';
  end;

  reset role;

  raise notice 'OK 0031-1J dos empresas no se ven (set local role tei_app)';
  raise notice 'OK 0031-1: unicidad activa, cierre, FKs por empresa, roles LLM, idempotencia y tenant';
end
$$;

rollback;

\echo '0031-1: OK (rollback; 0 filas residuales)'
