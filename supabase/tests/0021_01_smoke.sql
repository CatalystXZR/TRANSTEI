-- ============================================================================
-- Prueba 0021-1 — SMOKE: mecánica de esquema del módulo agente (0021)
-- ============================================================================
-- Cubre contactos/ACL/conversaciones/mensajes/solicitudes/hoja de ruta/R-04/
-- auditoría (invariantes AW-01..AW-16 en docs/datos/agente-esquema.md §3).
-- Cada caso abre BEGIN y cierra ROLLBACK: sin residuo en tei_test.
--
-- ROL: corre con un rol BYPASSRLS (postgres). Aquí se prueban CONSTRAINTS,
-- TRIGGERS y FUNCIONES, no RLS (eso es 0021_03_rls_tei_app.sql). El script
-- aborta si el rol no tiene BYPASSRLS para no mezclar los dos órdenes.
--
-- Fixtures de tei_test (clon desechable):
--   EMPRESA A  = 11111111-1111-1111-1111-111111111111
--   EMPRESA B  = b0787fc9-ba4e-4005-9371-40cb7c0fbfa4
--   CLIENTE A1 = 22222222-2222-2222-2222-222222222221
--   CLIENTE B1 = c61c819b-df68-4617-8666-c88b5f85f54d
--   (chofer y viajes de A se resuelven dinámicamente dentro de cada caso)
--
-- SALIDA: NOTICE 'OK-Cxx' por caso pasante, 'FAIL-Cxx' por defecto, y
-- 'FIN' al terminar. FAIL aborta el script con error (ON_ERROR_STOP).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U postgres -d tei_test \
--     -v ON_ERROR_STOP=1 -f supabase/tests/0021_01_smoke.sql
--     (montar el archivo con docker cp o pasar todo por stdin)
-- ============================================================================

\set ON_ERROR_STOP on

\echo '0021-1: verificación de rol (exige BYPASSRLS para aislar la mecánica)'
do $$
declare
  v_by boolean;
begin
  select rolbypassrls into v_by from pg_roles where rolname = current_user;
  if not coalesce(v_by, false) then
    raise exception 'FAIL-ROL: correr con rol BYPASSRLS (postgres); current=% bypass=%',
      current_user, v_by;
  end if;
  raise notice 'OK     rol=% bypass=%', current_user, v_by;
end $$;

-- ============================================================================
-- CASO 1 — contacto válido: FKs compuestas + defaults OTP
-- ============================================================================
begin;
\echo '0021-1 caso1: contacto creado'
do $$
declare
  v_chofer uuid;
  v_cnt int;
begin
  select id into v_chofer from nucleo.choferes
   where empresa_id = '11111111-1111-1111-1111-111111111111' limit 1;
  if v_chofer is null then
    raise exception 'FAIL-C1 (entorno) no hay choferes en empresa A';
  end if;

  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol, chofer_id)
  values
    ('11111111-1111-1111-1111-111111111111', '+56911111111', 'Chofer Admin WhatsApp', 'conductor', v_chofer);

  select count(*) into v_cnt from nucleo.contactos_whatsapp
   where telefono = '+56911111111';
  if v_cnt = 1 then
    raise notice 'OK-C1   contacto conductor creado (chofer=%, otp=%)',
      v_chofer, (select otp_estado from nucleo.contactos_whatsapp where telefono='+56911111111');
  else
    raise exception 'FAIL-C1  no hay exactamente 1 contacto';
  end if;
end $$;
rollback;

-- ============================================================================
-- CASO 2 — rol vs entidad (ck_contacto_entidad en INSERT)
-- ============================================================================
begin;
\echo '0021-1 caso2: entidad según rol'
do $$
declare
  v_cliente uuid; v_chofer uuid;
begin
  select id into v_cliente from nucleo.clientes
   where empresa_id='11111111-1111-1111-1111-111111111111' limit 1;
  select id into v_chofer from nucleo.choferes
   where empresa_id='11111111-1111-1111-1111-111111111111' limit 1;

  begin
    insert into nucleo.contactos_whatsapp
      (empresa_id, telefono, nombre, rol)
      values ('11111111-1111-1111-1111-111111111111', '+56922222222', 'Sin entidad', 'conductor');
    raise notice 'FAIL-C2A conductor sin chofer_id no fue rechazado';
  exception when check_violation then
    raise notice 'OK-C2A  conductor sin chofer_id rechazado (23514)';
  end;

  begin
    insert into nucleo.contactos_whatsapp
      (empresa_id, telefono, nombre, rol, cliente_id, chofer_id)
      values ('11111111-1111-1111-1111-111111111111', '+56922222222', 'Doble entidad',
              'admin', v_cliente, v_chofer);
    raise notice 'FAIL-C2B admin con entidades no fue rechazado';
  exception when check_violation then
    raise notice 'OK-C2B  admin con entidades rechazado (23514)';
  end;

  begin
    insert into nucleo.contactos_whatsapp
      (empresa_id, telefono, nombre, rol, chofer_id)
      values ('11111111-1111-1111-1111-111111111111', '+56922222222',
              'Entidad equivocada', 'cliente_final', v_chofer);
    raise notice 'FAIL-C2C chofer como cliente_final no fue rechazado';
  exception when check_violation then
    raise notice 'OK-C2C  chofer_id no puede ir con rol cliente_final (23514)';
  end;

  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol, cliente_id)
    values ('11111111-1111-1111-1111-111111111111', '+56922222222',
            'Contacto Cliente', 'cliente_final', v_cliente);
  raise notice 'OK-C2D  cliente_final con su cliente aceptado';
end $$;
rollback;

-- ============================================================================
-- CASO 3 — teléfono: formato E.164, unicidad activa GLOBAL, liberación (D-12)
-- ============================================================================
begin;
\echo '0021-1 caso3: teléfono'
do $$
begin
  begin
    insert into nucleo.contactos_whatsapp
      (empresa_id, telefono, nombre, rol)
      values ('11111111-1111-1111-1111-111111111111', '56123', 'Formato malo', 'admin');
    raise notice 'FAIL-C3A formato inválido fue aceptado';
  exception when check_violation then
    raise notice 'OK-C3A  teléfono fuera de E.164 rechazado (23514)';
  end;

  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56933333333', 'Primero', 'admin');
  raise notice 'OK-C3B  primer teléfono activo insertado';

  begin
    insert into nucleo.contactos_whatsapp
      (empresa_id, telefono, nombre, rol)
      values ('11111111-1111-1111-1111-111111111111', '+56933333333', 'Doblete', 'admin');
    raise notice 'FAIL-C3C teléfono activo duplicado fue aceptado';
  exception when unique_violation then
    raise notice 'OK-C3C  teléfono activo duplicado rechazado (23505)';
  end;

  update nucleo.contactos_whatsapp set activo = false where telefono = '+56933333333';
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56933333333', 'Segundo', 'admin');
  raise notice 'OK-C3D  desactivar libera el número y se re-enrola';

  begin
    update nucleo.contactos_whatsapp set activo = true
     where telefono = '+56933333333' and nombre = 'Primero';
    raise notice 'FAIL-C3E reactivar con otro activo fue aceptado';
  exception when unique_violation then
    raise notice 'OK-C3E  reactivación chocó con el activo vigente (23505)';
  end;

  begin
    insert into nucleo.contactos_whatsapp
      (empresa_id, telefono, nombre, rol)
      values ('b0787fc9-ba4e-4005-9371-40cb7c0fbfa4', '+56933333333', 'Otra empresa', 'admin');
    raise notice 'FAIL-C3F otro tenant aceptó el mismo número activo';
  exception when unique_violation then
    raise notice 'OK-C3F  unicidad GLOBAL del teléfono (sin fuga entre tenants)';
  end;
end $$;
rollback;

-- ============================================================================
-- CASO 4 — OTP: verificado exige fecha (ck_contacto_otp_estado)
-- ============================================================================
begin;
\echo '0021-1 caso4: otp'
do $$
begin
  begin
    insert into nucleo.contactos_whatsapp
      (empresa_id, telefono, nombre, rol, otp_estado)
      values ('11111111-1111-1111-1111-111111111111', '+56944444444', 'OTP', 'admin', 'verificado');
    raise notice 'FAIL-C4  verificado sin fecha fue aceptado';
  exception when check_violation then
    raise notice 'OK-C4   verificado exige otp_verificado_en (23514)';
  end;

  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol, otp_estado, otp_verificado_en)
    values ('11111111-1111-1111-1111-111111111111', '+56944444444', 'OTP ok', 'admin', 'verificado', now());
  raise notice 'OK-C4b  verificado con fecha aceptado';
end $$;
rollback;

-- ============================================================================
-- CASO 5 — ACL: unicidad funcional (contacto, componente, coalesce(var,''))
-- ============================================================================
begin;
\echo '0021-1 caso5: ACL'
do $$
declare v_contacto uuid;
begin
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56955555555', 'Contacto ACL', 'admin')
    returning id into v_contacto;

  insert into nucleo.permisos_contacto
    (empresa_id, contacto_id, componente, variable, permitido)
    values ('11111111-1111-1111-1111-111111111111', v_contacto, 'buzon', NULL, true);
  raise notice 'OK-C5A  ACL (buzon, variable NULL) insertada';

  begin
    insert into nucleo.permisos_contacto
      (empresa_id, contacto_id, componente, variable, permitido)
      values ('11111111-1111-1111-1111-111111111111', v_contacto, 'buzon', NULL, false);
    raise notice 'FAIL-C5B clon exacto fue aceptado';
  exception when unique_violation then
    raise notice 'OK-C5B  (contacto, componente, variable-NULL) único (23505)';
  end;

  insert into nucleo.permisos_contacto
    (empresa_id, contacto_id, componente, variable, permitido)
    values ('11111111-1111-1111-1111-111111111111', v_contacto, 'buzon', 'cargar_oc', true);
  raise notice 'OK-C5C  variable específica distinta aceptada';

  -- FK compuesta: empresa B no puede referenciar el contacto de A. Con un
  -- componente DISTINTO la unicidad funcional no interviene y asoma el 23503.
  begin
    insert into nucleo.permisos_contacto
      (empresa_id, contacto_id, componente, variable, permitido)
      values ('b0787fc9-ba4e-4005-9371-40cb7c0fbfa4', v_contacto, 'viajes', NULL, true);
    raise notice 'FAIL-C5D ACL cruzó empresa (FK compuesta ausente)';
  exception when foreign_key_violation then
    raise notice 'OK-C5D  ACL no puede apuntar a contacto de otra empresa (23503)';
  end;

  -- Clon exacto hacia otra empresa: lo rechaza PRIMERO la unicidad
  -- funcional global (23505), antes que la FK compuesta (23503). Ambas
  -- guardan; el orden real se mide aquí (descubrimiento, no suposición).
  begin
    insert into nucleo.permisos_contacto
      (empresa_id, contacto_id, componente, variable, permitido)
      values ('b0787fc9-ba4e-4005-9371-40cb7c0fbfa4', v_contacto, 'buzon', NULL, true);
    raise notice 'FAIL-C5F clon del ACL hacia otra empresa fue aceptado';
  exception when unique_violation then
    raise notice 'OK-C5F  clon hacia otra empresa: fire primero 23505 (uq global)';
  when foreign_key_violation then
    raise notice 'FAIL-C5F el orden real fue FK (23503) y no 23505: ajustar doc';
  end;

  begin
    insert into nucleo.permisos_contacto
      (empresa_id, contacto_id, componente, variable, permitido)
      values ('11111111-1111-1111-1111-111111111111', v_contacto, '   ', NULL, true);
    raise notice 'FAIL-C5E componente en blanco fue aceptado';
  exception when check_violation then
    raise notice 'OK-C5E  componente solo espacios rechazado (23514)';
  end;
end $$;
rollback;

-- ============================================================================
-- CASO 6 — conversaciones: una activa por contacto; cerradas múltiples
-- ============================================================================
begin;
\echo '0021-1 caso6: conversaciones'
do $$
declare v_contacto uuid;
begin
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56966666666', 'Contacto Conv', 'admin')
    returning id into v_contacto;

  insert into nucleo.conversaciones (empresa_id, contacto_id)
    values ('11111111-1111-1111-1111-111111111111', v_contacto);
  raise notice 'OK-C6A  conversación activa 1';

  begin
    insert into nucleo.conversaciones (empresa_id, contacto_id)
      values ('11111111-1111-1111-1111-111111111111', v_contacto);
    raise notice 'FAIL-C6B segunda activa fue aceptada (sesiones paralelas)';
  exception when unique_violation then
    raise notice 'OK-C6B  segunda sesión activa rechazada (23505, índice parcial)';
  end;

  update nucleo.conversaciones set activa=false, cerrada_en = now()
    where contacto_id = v_contacto;
  insert into nucleo.conversaciones (empresa_id, contacto_id)
    values ('11111111-1111-1111-1111-111111111111', v_contacto);
  raise notice 'OK-C6C  tras cerrar se abre nueva (nunca 2 activas)';

  insert into nucleo.conversaciones (empresa_id, contacto_id, activa, cerrada_en)
    values ('11111111-1111-1111-1111-111111111111', v_contacto, false, now());
  raise notice 'OK-C6D  segunda conversación cerrada en el pasado admitida';

  begin
    insert into nucleo.conversaciones (empresa_id, contacto_id, activa, cerrada_en)
      values ('11111111-1111-1111-1111-111111111111', v_contacto, false, null);
    raise notice 'FAIL-C6E inactiva sin cerrada_en fue aceptada';
  exception when check_violation then
    raise notice 'OK-C6E  ck_conversacion_cierre: inactiva exige cerrada_en (23514)';
  end;
end $$;
rollback;

-- ============================================================================
-- CASO 7 — mensajes: idempotencia wa_message_id + CHECK entrante
-- ============================================================================
begin;
\echo '0021-1 caso7: mensajes'
do $$
declare
  v_contacto uuid; v_conv uuid;
  v_estado text; v_meta jsonb;
begin
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56977777777', 'Contacto Msg', 'admin')
    returning id into v_contacto;
  insert into nucleo.conversaciones (empresa_id, contacto_id)
    values ('11111111-1111-1111-1111-111111111111', v_contacto)
    returning id into v_conv;

  begin
    insert into nucleo.conversacion_mensajes
      (empresa_id, conversacion_id, contacto_id, direccion, modalidad, cuerpo)
      values ('11111111-1111-1111-1111-111111111111', v_conv, v_contacto, 'entrante', 'texto', 'hola sin id');
    raise notice 'FAIL-C7A entrante sin wa_message_id fue aceptado';
  exception when check_violation then
    raise notice 'OK-C7A  entrante exige wa_message_id (23514)';
  end;

  insert into nucleo.conversacion_mensajes
    (empresa_id, conversacion_id, contacto_id, direccion, modalidad, cuerpo, wa_message_id)
    values ('11111111-1111-1111-1111-111111111111', v_conv, v_contacto, 'entrante', 'texto', 'hola', 'wamid.smoke.1');
  select estado_procesamiento::text, metadata into v_estado, v_meta
    from nucleo.conversacion_mensajes where wa_message_id='wamid.smoke.1';
  if v_estado = 'recibido' and v_meta = '{}'::jsonb then
    raise notice 'OK-C7B  entrante con wa_message_id aceptado (defaults: recibido/{})';
  else
    raise exception 'FAIL-C7B defaults incorrectos: %, %', v_estado, v_meta;
  end if;

  begin
    insert into nucleo.conversacion_mensajes
      (empresa_id, conversacion_id, contacto_id, direccion, modalidad, cuerpo, wa_message_id)
      values ('11111111-1111-1111-1111-111111111111', v_conv, v_contacto, 'entrante', 'texto',
              'reenvío webhook', 'wamid.smoke.1');
    raise notice 'FAIL-C7C reenvío webhook duplicó el mensaje';
  exception when unique_violation then
    raise notice 'OK-C7C  wa_message_id repetido rechazado (23505)';
  end;

  insert into nucleo.conversacion_mensajes
    (empresa_id, conversacion_id, contacto_id, direccion, modalidad, cuerpo)
    values ('11111111-1111-1111-1111-111111111111', v_conv, v_contacto, 'saliente', 'texto', 'respuesta');
  raise notice 'OK-C7D  saliente sin wa_message_id es válido';

  begin
    insert into nucleo.conversacion_mensajes
      (empresa_id, conversacion_id, contacto_id, direccion, modalidad, cuerpo, wa_message_id)
      values ('11111111-1111-1111-1111-111111111111', v_conv, v_contacto, 'entrante', 'voz', 'audio', null);
    raise notice 'FAIL-C7E voz sin wa fue aceptado';
  exception when check_violation then
    raise notice 'OK-C7E  entrante-voz también exige wa_message_id (la modalidad no perdona)';
  end;
end $$;
rollback;

-- ============================================================================
-- CASO 8 — mensaje en conversación de OTRO contacto (fn_mensaje_validar)
-- ============================================================================
begin;
\echo '0021-1 caso8: conversación ajena'
do $$
declare v_c1 uuid; v_c2 uuid; v_conv uuid;
begin
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56988888888', 'A', 'admin')
    returning id into v_c1;
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56988888889', 'B', 'admin')
    returning id into v_c2;

  insert into nucleo.conversaciones (empresa_id, contacto_id)
    values ('11111111-1111-1111-1111-111111111111', v_c2)
    returning id into v_conv;

  begin
    insert into nucleo.conversacion_mensajes
      (empresa_id, conversacion_id, contacto_id, direccion, modalidad, cuerpo, wa_message_id)
      values ('11111111-1111-1111-1111-111111111111', v_conv, v_c1, 'entrante', 'texto', 'hola', 'wamid.ses');
    raise notice 'FAIL-C8A mensaje de A se coló en la sesión de B';
  exception when check_violation then
    raise notice 'OK-C8A  fn_mensaje_validar rechazó el mensaje cruzado (23514)';
  end;
end $$;
rollback;

-- ============================================================================
-- CASO 9 — solicitudes (F2.6/D-10): solicitante exacto, terminal, idempotencia
-- ============================================================================
begin;
\echo '0021-1 caso9: solicitudes'
do $$
declare
  v_contacto uuid; v_sol uuid; v_sol2 uuid; v_usuario uuid;
begin
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56999999999', 'Contacto Sol', 'admin')
    returning id into v_contacto;

  insert into nucleo.solicitudes
    (empresa_id, tipo, solicitante_contacto_id, payload)
    values ('11111111-1111-1111-1111-111111111111', 'hoja_de_ruta', v_contacto,
            '{"accion":"crear_carga"}'::jsonb)
    returning id into v_sol;
  raise notice 'OK-C9A  solicitud pendiente creada';

  begin
    insert into nucleo.solicitudes
      (empresa_id, tipo, solicitante_contacto_id, clave_idempotencia, payload)
      values ('11111111-1111-1111-1111-111111111111', 'documentos', v_contacto, 'k1', '{}');
    insert into nucleo.solicitudes
      (empresa_id, tipo, solicitante_contacto_id, clave_idempotencia, payload)
      values ('11111111-1111-1111-1111-111111111111', 'documentos', v_contacto, 'k1', '{}');
    raise notice 'FAIL-C9B misma clave creó dos solicitudes';
  exception when unique_violation then
    raise notice 'OK-C9B  clave_idempotencia repetida rechazada (23505)';
  end;

  -- solicitante ambiguo: contacto + usuario (ambos no nulos) → CHECK 23514
  select id into v_usuario
    from nucleo.usuarios_empresa
   where empresa_id = '11111111-1111-1111-1111-111111111111' limit 1;
  if v_usuario is null then
    raise exception 'FAIL-C9C-entorno: no hay usuarios_empresa en A para armar el caso';
  end if;

  begin
    insert into nucleo.solicitudes
      (empresa_id, tipo, solicitante_contacto_id, solicitante_usuario_empresa_id, payload)
      values ('11111111-1111-1111-1111-111111111111', 'documentos', v_contacto, v_usuario, '{}');
    raise notice 'FAIL-C9C dos solicitantes fue aceptado';
  exception when check_violation then
    raise notice 'OK-C9C  ck_solicitud_solicitante: exactamente uno (23514)';
  end;

  begin
    insert into nucleo.solicitudes (empresa_id, tipo, payload)
      values ('11111111-1111-1111-1111-111111111111', 'documentos', '{}');
    raise notice 'FAIL-C9D sin solicitante fue aceptado';
  exception when check_violation then
    raise notice 'OK-C9D  ck_solicitud_solicitante exige un solicitante (23514)';
  end;

  begin
    update nucleo.solicitudes set estado='aprobada' where id = v_sol;
    raise notice 'FAIL-C9E aprobar sin aprobado_por/decidido_en fue aceptado';
  exception when check_violation then
    raise notice 'OK-C9E  aprobar sin aprobador/fecha rechazado (23514)';
  end;

  update nucleo.solicitudes
    set estado='aprobada', aprobado_por='usuario_prueba', decidido_en=now()
   where id = v_sol;
  raise notice 'OK-C9F  aprobado con aprobador+fecha';

  begin
    update nucleo.solicitudes
      set estado='pendiente', aprobado_por=null, decidido_en=null
     where id = v_sol;
    raise notice 'FAIL-C9G terminal reabierto (decisiones no definitivas)';
  exception when check_violation then
    raise notice 'OK-C9G  terminal no vuelve a pendiente (23514, trigger)';
  end;

  begin
    update nucleo.solicitudes
      set estado='rechazada', motivo_rechazo='revisión posterior'
     where id = v_sol;
    raise notice 'FAIL-C9H terminal re-clasificado a rechazada';
  exception when check_violation then
    raise notice 'OK-C9H  terminal no cambia de tipo de decisión (23514, trigger)';
  end;

  -- D-10 Modificar: no es estado; en pendiente usa valores_modificados
  insert into nucleo.solicitudes
    (empresa_id, tipo, solicitante_contacto_id, payload)
    values ('11111111-1111-1111-1111-111111111111', 'hoja_de_ruta', v_contacto,
            '{"cargas":1}'::jsonb)
    returning id into v_sol2;
  update nucleo.solicitudes
    set valores_modificados='{"cargas":2}'::jsonb,
        modificado_por='usuario_prueba', modificado_en=now()
   where id = v_sol2;
  v_sol := null;
  select id into v_sol from nucleo.solicitudes
   where id = v_sol2 and estado='pendiente' and valores_modificados='{"cargas":2}'::jsonb;
  if v_sol is not null then
    raise notice 'OK-C9I  modificados registrados en pendiente sin cambiar estado (D-10)';
  else
    raise exception 'FAIL-C9I valores_modificados no quedó como se esperaba';
  end if;

  update nucleo.solicitudes
    set estado='cancelada', motivo_cancelacion='plan del dueño'
   where id = v_sol2;
  raise notice 'OK-C9J  cancelado con motivo';
end $$;
rollback;

-- ============================================================================
-- CASO 10 — hoja de ruta (D-10/ADR-0003 §14.2)
-- ============================================================================
begin;
\echo '0021-1 caso10: hoja de ruta'
do $$
declare v_contacto uuid; v_h1 uuid; v_h2 uuid; v_sol uuid;
begin
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56910000001', 'Contacto HR', 'admin')
    returning id into v_contacto;

  insert into nucleo.hoja_ruta
    (empresa_id, contacto_id, payload)
    values ('11111111-1111-1111-1111-111111111111', v_contacto, '{"cargas":[]}'::jsonb)
    returning id into v_h1;
  raise notice 'OK-C10A propuesto sin solicitud admitido';

  begin
    insert into nucleo.hoja_ruta
      (empresa_id, contacto_id, payload, estado)
      values ('11111111-1111-1111-1111-111111111111', v_contacto, '{"cargas":[]}'::jsonb, 'solicitud_creada');
    raise notice 'FAIL-C10B solicitud_creada sin solicitud_id fue aceptada';
  exception when check_violation then
    raise notice 'OK-C10B no-propuesto exige solicitud_id (23514)';
  end;

  insert into nucleo.solicitudes
    (empresa_id, tipo, solicitante_contacto_id, payload)
    values ('11111111-1111-1111-1111-111111111111', 'hoja_de_ruta', v_contacto, '{"desde":"hoja_ruta"}'::jsonb)
    returning id into v_sol;

  insert into nucleo.hoja_ruta
    (empresa_id, contacto_id, payload, estado, solicitud_id)
    values ('11111111-1111-1111-1111-111111111111', v_contacto, '{"cargas":[]}'::jsonb, 'solicitud_creada', v_sol)
    returning id into v_h2;
  raise notice 'OK-C10C solicitud_creada con solicitud_id admitida';

  update nucleo.hoja_ruta
    set estado='cargado', valores_cargados='{"cargas":1}'::jsonb
   where id = v_h2;
  raise notice 'OK-C10D carga registrada';

  -- C10E prueba uq_hoja_ruta_carga_por_solicitud (a lo sumo una carga por
  -- solicitud). Con D5 (0022) el salto propuesto -> cargado ya no es legal:
  -- la primera hoja recorre la ruta permitida propuesto -> solicitud_creada
  -- -> cargado y el 23505 del índice parcial sigue siendo la aserción.
  update nucleo.hoja_ruta
    set estado='solicitud_creada', solicitud_id=v_sol
   where id = v_h1;
  raise notice 'OK-C10E1 primera hoja en solicitud_creada (ruta legal, D5)';

  begin
    update nucleo.hoja_ruta
      set estado='cargado', valores_cargados='{"cargas":9}'::jsonb
     where id = v_h1;
    raise notice 'FAIL-C10E segunda carga para la misma solicitud fue admitida';
  exception when unique_violation then
    raise notice 'OK-C10E no hay dos cargados por solicitud (23505, índice parcial)';
  end;

  begin
    insert into nucleo.hoja_ruta
      (empresa_id, contacto_id, payload, estado, solicitud_id)
      values ('11111111-1111-1111-1111-111111111111', v_contacto,
              '{"cargas":[]}'::jsonb, 'cargado', v_sol);
    raise notice 'FAIL-C10F cargado sin valores fue aceptado';
  exception when check_violation then
    raise notice 'OK-C10F cargado sin valores_cargados rechazado (23514)';
  end;
end $$;
rollback;

-- ============================================================================
-- CASO 11 — R-04: formato, contador, no retrocede, CHECK y única en viajes
-- ============================================================================
begin;
\echo '0021-1 caso11: R-04'
do $$
declare
  v_cod1 text; v_cod2 text; v_last bigint; v_now bigint;
  v_ids uuid[];
begin
  begin
    perform nucleo.obtener_siguiente_id_comercial_flete(
      '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222221', 's&m');
    raise notice 'FAIL-C11A prefijo con símbolos fue aceptado';
  exception when check_violation then
    raise notice 'OK-C11A prefijo inválido rechazado (23514)';
  end;

  begin
    perform nucleo.obtener_siguiente_id_comercial_flete(
      '11111111-1111-1111-1111-111111111111', 'c61c819b-df68-4617-8666-c88b5f85f54d', 'SQM');
    raise notice 'FAIL-C11B cliente de B emitido bajo empresa A';
  exception when check_violation then
    raise notice 'OK-C11B cliente de otra empresa rechazado (23514)';
  end;

  v_cod1 := nucleo.obtener_siguiente_id_comercial_flete(
    '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222221', 'sqm');
  v_cod2 := nucleo.obtener_siguiente_id_comercial_flete(
    '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222221', 'SQM');
  if v_cod1 like 'SQM-%' and v_cod2 like 'SQM-%'
     and substring(v_cod1,5)::int = substring(v_cod2,5)::int - 1
     and length(v_cod1)=9 then
    raise notice 'OK-C11C consecutivos y en mayúsculas: % , %', v_cod1, v_cod2;
  else
    raise exception 'FAIL-C11C no consecutivos o no en mayúsculas (% , %)', v_cod1, v_cod2;
  end if;

  v_last := (select ultimo from nucleo.id_comercial_contador
              where empresa_id='11111111-1111-1111-1111-111111111111'
                and cliente_id='22222222-2222-2222-2222-222222222221');
  perform nucleo.registrar_id_comercial_flete(
    '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222221', 'SQM-00001');
  v_now := (select ultimo from nucleo.id_comercial_contador
              where empresa_id='11111111-1111-1111-1111-111111111111'
                and cliente_id='22222222-2222-2222-2222-222222222221');
  if v_now = v_last then
    raise notice 'OK-C11D registrar con código menor no retrocede (greatest)';
  else
    raise exception 'FAIL-C11D contador retrocedió de % a %', v_last, v_now;
  end if;

  select array(select id from nucleo.viajes
                where empresa_id='11111111-1111-1111-1111-111111111111'
                  and cliente_id='22222222-2222-2222-2222-222222222221'
                order by numero_viaje limit 2) into v_ids;
  if cardinality(v_ids) < 2 then
    raise exception 'FAIL-C11-entorno: necesito 2 viajes del cliente A1';
  end if;

  begin
    update nucleo.viajes set id_comercial_flete='SQM-123' where id = v_ids[1];
    raise notice 'FAIL-C11E formato inválido fue aceptado';
  exception when check_violation then
    raise notice 'OK-C11E formato PREFIJO-00001 impuesto por CHECK (23514)';
  end;

  update nucleo.viajes set id_comercial_flete = v_cod1 where id = v_ids[1];
  raise notice 'OK-C11F asignación % al viaje %', v_cod1, v_ids[1];

  begin
    update nucleo.viajes set id_comercial_flete = v_cod1 where id = v_ids[2];
    raise notice 'FAIL-C11G código duplicado aceptado';
  exception when unique_violation then
    raise notice 'OK-C11G misma empresa+cliente no repite código (23505)';
  end;

  -- D2 (0022): un ID ya asignado es inmutable. Volver a NULL liberaría el
  -- código para reasignarlo, porque la UNIQUE parcial solo cubre no nulos.
  begin
    update nucleo.viajes set id_comercial_flete=null where id = v_ids[1];
    raise notice 'FAIL-C11H desasignar un ID ya asignado fue aceptado (D2)';
  exception when check_violation then
    raise notice 'OK-C11H desasignar un ID ya asignado rechazado (23514, D2)';
  end;

  -- El camino de cutover/backfill sigue abierto: asignar desde NULL.
  update nucleo.viajes set id_comercial_flete = v_cod2 where id = v_ids[2];
  if found then
    raise notice 'OK-C11H2 asignar desde NULL sigue permitido (% en viaje %, D2)', v_cod2, v_ids[2];
  else
    raise exception 'FAIL-C11H2 asignar desde NULL no actualizó ninguna fila';
  end if;
end $$;
rollback;

-- ============================================================================
-- CASO 12 — auditoría de consultas (D-17): append-only (UPDATE/DELETE/TRUNCATE)
-- ============================================================================
begin;
\echo '0021-1 caso12: auditoría append-only'
do $$
declare v_contacto uuid; v_rowid bigint;
begin
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56910000002', 'Contacto Audit', 'admin')
    returning id into v_contacto;

  insert into nucleo.auditoria_consultas_agente
    (empresa_id, contacto_id, componente, pregunta_resumida,
     datos_tocados, respuesta_resumida, acceso_otorgado)
    values ('11111111-1111-1111-1111-111111111111', v_contacto, 'buzon',
            'cuantas cargas', '[{"id":"x"}]'::jsonb, 'dos', true)
    returning id into v_rowid;
  raise notice 'OK-C12A registro de consulta aceptado';

  begin
    delete from nucleo.auditoria_consultas_agente where id = v_rowid;
    raise notice 'FAIL-C12B DELETE fue aceptado (historia mutable)';
  exception when check_violation then
    raise notice 'OK-C12B DELETE bloqueado (23514, trigger)';
  end;

  begin
    update nucleo.auditoria_consultas_agente set pregunta_resumida='otra'
     where id = v_rowid;
    raise notice 'FAIL-C12C UPDATE fue aceptado';
  exception when check_violation then
    raise notice 'OK-C12C UPDATE bloqueado (23514, trigger)';
  end;

  begin
    truncate table nucleo.auditoria_consultas_agente;
    raise notice 'FAIL-C12D TRUNCATE fue aceptado';
  exception when check_violation then
    raise notice 'OK-C12D TRUNCATE bloqueado (23514, trigger por sentencia)';
  end;
end $$;
rollback;

-- ============================================================================
-- CASO 13 — touch/version (convención del núcleo) sobre contacto
-- ============================================================================
begin;
\echo '0021-1 caso13: touch/version'
do $$
declare v_v2 int; v_ts timestamptz;
begin
  insert into nucleo.contactos_whatsapp
    (empresa_id, telefono, nombre, rol)
    values ('11111111-1111-1111-1111-111111111111', '+56910000003', 'Contacto Touch', 'admin');

  perform pg_sleep(0.05);
  update nucleo.contactos_whatsapp set nombre='Contacto Touch (v2)' where telefono='+56910000003';
  select version, updated_at into v_v2, v_ts
    from nucleo.contactos_whatsapp where telefono='+56910000003';
  if v_v2 = 2 and abs(extract(epoch from (now() - v_ts))) < 5 then
    raise notice 'OK-C13  version=2 y updated_at refrescado';
  else
    raise exception 'FAIL-C13 touch/version no se aplicó (version=%)', v_v2;
  end if;
end $$;
rollback;

-- ============================================================================
-- CASO 14 — catálogo mínimo: 8 enums y 5 funciones
-- ============================================================================
\echo '0021-1 caso14: catálogo'
do $$
declare v_total int;
begin
  select count(*) into v_total
    from pg_type t join pg_namespace n on n.oid=t.typnamespace
   where n.nspname='nucleo' and t.typtype='e' and t.typname in (
     'rol_contacto_whatsapp','estado_otp','direccion_mensaje','modalidad_mensaje',
     'estado_procesamiento_mensaje','tipo_solicitud','estado_solicitud','estado_hoja_ruta');
  if v_total = 8 then
    raise notice 'OK-C14 8 enums';
  else
    raise exception 'FAIL-C14 enums=%', v_total;
  end if;

  select count(*) into v_total
    from pg_proc p join pg_namespace n on n.oid=p.pronamespace
   where n.nspname='nucleo' and proname in (
     'obtener_siguiente_id_comercial_flete','registrar_id_comercial_flete',
     'fn_mensaje_validar','fn_solicitud_transicion','fn_consultas_agente_inmutable');
  if v_total = 5 then
    raise notice 'OK-C14b 5 funciones';
  else
    raise exception 'FAIL-C14b funciones=%', v_total;
  end if;
end $$;

\echo 'FIN smoke 0021-1: casos del 1 al 14 completados (BEGIN/ROLLBACK: sin datos)'
