-- ============================================================================
-- Prueba 0031-2 — RLS del chat in-app con el ROL REAL de la app (`tei_app`)
-- ============================================================================
-- Se ejecuta como `supabase_admin` y cambia a `tei_app` con `SET LOCAL ROLE`
-- dentro de la transacción. Comprueba:
--   A) rol efectivo: tei_app, NOBYPASSRLS.
--   B) sin contexto (`app.empresa_id` vacío): 0 filas y escritura => 42501.
--   C) con contexto TEI: ve solo TEI; INSERT propio OK; insertar con empresa
--      ajena => 42501; UPDATE de otra empresa => 0 filas; DELETE => 42501
--      (privilegio revocado, no RLS).
--   D) con contexto TES: no ve TEI.
--
-- Todo termina en ROLLBACK: 0 filas residuales.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0031_02_rls_tei_app.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_tei     constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes     constant uuid := '22222222-2222-2222-2222-222222222222';
  v_usr_tei uuid;
  v_usr_tes uuid;
  v_conv_tei uuid;
  v_conv_tes uuid;
  v_msg_tei uuid;
  v_msg_tes uuid;
  v_n       integer;
  v_by      boolean;
begin
  -- ---- 0. Fixtures como rol de plataforma (BYPASSRLS) ---------------------
  select id into v_usr_tei from nucleo.usuarios_empresa
   where empresa_id = v_tei order by id limit 1;
  select id into v_usr_tes from nucleo.usuarios_empresa
   where empresa_id = v_tes order by id limit 1;
  if v_usr_tei is null or v_usr_tes is null then
    raise exception 'ENTORNO 0031-2: faltan usuarios_empresa de TEI/TES en el seed';
  end if;

  insert into nucleo.agente_chat_conversaciones
    (empresa_id, usuario_empresa_id, agente)
  values (v_tei, v_usr_tei, 'gerente')
  returning id into v_conv_tei;

  insert into nucleo.agente_chat_conversaciones
    (empresa_id, usuario_empresa_id, agente)
  values (v_tes, v_usr_tes, 'gerente')
  returning id into v_conv_tes;

  insert into nucleo.agente_chat_mensajes
    (empresa_id, conversacion_id, rol, contenido)
  values (v_tei, v_conv_tei, 'user', 'hola TEI')
  returning id into v_msg_tei;

  insert into nucleo.agente_chat_mensajes
    (empresa_id, conversacion_id, rol, contenido)
  values (v_tes, v_conv_tes, 'user', 'hola TES')
  returning id into v_msg_tes;

  -- ---- 1. Cambio al rol real ---------------------------------------------
  set local role tei_app;

  select rolbypassrls into v_by from pg_roles where rolname = current_user;
  if current_user <> 'tei_app' or coalesce(v_by, true) then
    raise exception 'FALLO 0031-2A rol: current_user=% bypass=%', current_user, v_by;
  end if;
  raise notice 'OK 0031-2A rol: current_user=% bypass=% (session_user conserva admin)', current_user, v_by;

  -- ---- 2. Sin contexto: 0 filas y escritura rechazada --------------------
  perform set_config('app.empresa_id', '', true);

  select count(*) into v_n from nucleo.agente_chat_conversaciones;
  if v_n <> 0 then
    raise exception 'FALLO 0031-2B: % conversaciones visibles sin contexto', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_chat_mensajes;
  if v_n <> 0 then
    raise exception 'FALLO 0031-2B: % mensajes visibles sin contexto', v_n;
  end if;

  begin
    insert into nucleo.agente_chat_conversaciones
      (empresa_id, usuario_empresa_id, agente)
    values (v_tei, v_usr_tei, 'secretaria');
    raise exception 'FALLO 0031-2B: INSERT de conversación sin contexto aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0031-2B INSERT de conversación sin contexto => 42501';
  end;

  begin
    insert into nucleo.agente_chat_mensajes
      (empresa_id, conversacion_id, rol, contenido)
    values (v_tei, v_conv_tei, 'user', 'sin contexto');
    raise exception 'FALLO 0031-2B: INSERT de mensaje sin contexto aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0031-2B INSERT de mensaje sin contexto => 42501';
  end;

  -- ---- 3. Contexto TEI ----------------------------------------------------
  perform set_config('app.empresa_id', v_tei::text, true);

  select count(*) into v_n from nucleo.agente_chat_conversaciones;
  if v_n <> 1 then
    raise exception 'FALLO 0031-2C: TEI ve % conversaciones (esperado 1)', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_chat_mensajes;
  if v_n <> 1 then
    raise exception 'FALLO 0031-2C: TEI ve % mensajes (esperado 1)', v_n;
  end if;

  insert into nucleo.agente_chat_conversaciones
    (empresa_id, usuario_empresa_id, agente)
  values (v_tei, v_usr_tei, 'secretaria');
  insert into nucleo.agente_chat_mensajes
    (empresa_id, conversacion_id, rol, contenido)
  values (v_tei, v_conv_tei, 'assistant', 'respuesta TEI');

  select count(*) into v_n from nucleo.agente_chat_conversaciones;
  if v_n <> 2 then
    raise exception 'FALLO 0031-2C: TEI ve % conversaciones tras insertar (esperado 2)', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_chat_mensajes;
  if v_n <> 2 then
    raise exception 'FALLO 0031-2C: TEI ve % mensajes tras insertar (esperado 2)', v_n;
  end if;
  raise notice 'OK 0031-2C TEI: filas propias visibles y escribibles';

  -- Escribir con empresa_id ajeno: lo bloquea el WITH CHECK, no el servicio.
  begin
    insert into nucleo.agente_chat_conversaciones
      (empresa_id, usuario_empresa_id, agente)
    values (v_tes, v_usr_tes, 'secretaria');
    raise exception 'FALLO 0031-2C: INSERT de conversación con empresa TES aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0031-2C INSERT de conversación con empresa de TES => 42501';
  end;

  begin
    insert into nucleo.agente_chat_mensajes
      (empresa_id, conversacion_id, rol, contenido)
    values (v_tes, v_conv_tes, 'user', 'cruzado');
    raise exception 'FALLO 0031-2C: INSERT de mensaje con empresa TES aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0031-2C INSERT de mensaje con empresa de TES => 42501';
  end;

  -- UPDATE de una fila ajena: 0 filas, ni error ni fuga.
  update nucleo.agente_chat_conversaciones set resumen = 'fuga' where empresa_id = v_tes;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0031-2C: UPDATE tocó % conversaciones de otra empresa', v_n;
  end if;
  update nucleo.agente_chat_mensajes set contenido = 'fuga' where empresa_id = v_tes;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0031-2C: UPDATE tocó % mensajes de otra empresa', v_n;
  end if;
  raise notice 'OK 0031-2C UPDATE de otra empresa: 0 filas';

  -- ---- 4. DELETE denegado por privilegio (no por RLS) --------------------
  begin
    delete from nucleo.agente_chat_conversaciones where id = v_conv_tei;
    raise exception 'FALLO 0031-2D: tei_app pudo borrar una conversación propia';
  exception when insufficient_privilege then
    raise notice 'OK 0031-2D DELETE de conversación => 42501';
  end;

  begin
    delete from nucleo.agente_chat_mensajes where id = v_msg_tei;
    raise exception 'FALLO 0031-2D: tei_app pudo borrar un mensaje propio';
  exception when insufficient_privilege then
    raise notice 'OK 0031-2D DELETE de mensaje => 42501';
  end;

  -- ---- 5. Contexto TES: no ve TEI ----------------------------------------
  perform set_config('app.empresa_id', v_tes::text, true);

  select count(*) into v_n from nucleo.agente_chat_conversaciones where empresa_id = v_tei;
  if v_n <> 0 then
    raise exception 'FALLO 0031-2E: TES ve % conversaciones de TEI', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_chat_mensajes where empresa_id = v_tei;
  if v_n <> 0 then
    raise exception 'FALLO 0031-2E: TES ve % mensajes de TEI', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_chat_conversaciones;
  if v_n <> 1 then
    raise exception 'FALLO 0031-2E: TES ve % conversaciones propias (esperado 1)', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_chat_mensajes;
  if v_n <> 1 then
    raise exception 'FALLO 0031-2E: TES ve % mensajes propios (esperado 1)', v_n;
  end if;
  raise notice 'OK 0031-2E contexto TES: 0 filas de TEI, solo las propias';

  reset role;

  raise notice 'OK 0031-2: aislamiento por empresa verificado con tei_app';
end
$$;

rollback;

\echo '0031-2: OK (rollback; 0 filas residuales)'
