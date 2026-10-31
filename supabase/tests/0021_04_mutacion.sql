-- ============================================================================
-- Prueba 0021-4 — MUTACIÓN: sin el mecanismo, la garantía se rompe
-- ============================================================================
-- Una prueba que no falla al retirar la garantía no prueba nada (AGENTS.md §7,
-- mutacion.md §2). Aquí se retira UN mecanismo por bloque DENTRO de la misma
-- transacción, se ejecuta la aserción que debería fallar y se confirma que
-- efectivamente se rompe. Todo termina en ROLLBACK: la base no queda mutada.
--
-- Garantías y mecanismos retirados
--   M1  Idempotencia del webhook  → DROP INDEX nucleo.uq_mensaje_wa_message_id
--       Baseline: 2.º INSERT con el mismo wa_message_id ⇒ 23505.
--       Mutado:   el duplicado ENTRA (2 filas).
--   M2  Decisión definitiva       → DROP TRIGGER trg_solicitudes_10_transicion
--       Baseline: reabrir una solicitud aprobada ⇒ 23514.
--       Mutado:   la solicitud vuelve a 'pendiente'.
--   M3  Auditoría append-only     → DROP TRIGGER trg_consultas_agente_no_update
--                                   DROP TRIGGER trg_consultas_agente_no_truncate
--       Baseline: UPDATE y TRUNCATE ⇒ 23514.
--       Mutado:   UPDATE afecta 1 fila y TRUNCATE vacía la tabla.
--   M4  R-04 árbitro final        → DROP INDEX nucleo.uq_viajes_id_comercial
--       Baseline: dos viajes del mismo (empresa, cliente) con el mismo código
--                 ⇒ 23505.
--       Mutado:   el duplicado entra (2 viajes con el mismo código).
--   M5  RLS del módulo            → ALTER POLICY tenant_empresa USING (true)
--       Baseline: tei_app con contexto A NO ve el contacto de B.
--       Mutado:   lo ve (fuga entre empresas).
--   M6  D3 contador no retrocede  → DROP TRIGGER trg_contador_10_no_retrocede
--       Baseline: 500 -> 0 ⇒ 23514.
--       Mutado:   el contador baja a 0.
--   M7  D2 ID comercial inmutable → DROP TRIGGER trg_viajes_10_id_comercial_inmutable
--       Baseline: QAM-00001 -> QAM-00002 y -> NULL ⇒ 23514; NULL -> valor sí.
--       Mutado:   el ID cambia de QAM-00001 a QAM-00002.
--   M8  D5 transición hoja_ruta   → DROP TRIGGER trg_hoja_ruta_10_transicion
--       Baseline: propuesto -> cargado y cambio de payload ⇒ 23514.
--       Mutado:   ambos se aceptan.
--   M9  D9 tope 99999             → CREATE OR REPLACE función sin el tope (0021)
--       Baseline: contador 99999 ⇒ 23514 y sigue en 99999.
--       Mutado:   emite SQM-10000 (truncado) y deja 100000.
--
-- Lo que este archivo NO muta y por qué
--   · C1 (contador atómico): el mecanismo es el lock de fila del
--     `INSERT ... ON CONFLICT DO UPDATE` dentro de la función. Reemplazar la
--     función requiere COMMIT para que otras sesiones la vean, así que no puede
--     retirarse "dentro de una transacción". Su evidencia es la prueba real con
--     8 conexiones (0021_02 C1); M4 muta el árbitro UNIQUE que queda detrás.
--   · El gate de ACL por ausencia de fila en `permisos_contacto` NO es un
--     mecanismo de base: lo impone el backend (O2.2). Ver informe.
--
-- ROL: exige un superusuario local (`supabase_admin`) porque DROP INDEX/TRIGGER
-- y ALTER POLICY requieren ser dueño del esquema. `postgres` local NO es dueño
-- (relowner = supabase_admin) y fallaría con 42501: eso no es un defecto de la
-- garantía, es el rol equivocado.
--
-- USO:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0021_04_mutacion.sql
--
-- SALIDA: NOTICE 'OK 0021-4 Mx ...' por mutación confirmada. Un 'FALLO ...'
-- significa que retirar el mecanismo NO rompió la aserción: la prueba no vale.
-- ============================================================================

\set ON_ERROR_STOP on

\echo '0021-4: rol con privilegios de dueño'
do $$
declare
  v_super boolean;
begin
  select rolsuper into v_super from pg_roles where rolname = current_user;
  if not coalesce(v_super, false) then
    raise exception 'FALLO 0021-4 rol: se exige superusuario local (supabase_admin) para DROP/ALTER; current_user=%',
      current_user;
  end if;
  raise notice 'OK 0021-4 rol: % superusuario (puede retirar mecanismos)', current_user;
end $$;

-- ============================================================================
-- M1 — idempotencia por wa_message_id (índice único parcial)
-- ============================================================================
\echo '0021-4 M1: uq_mensaje_wa_message_id'
begin;
do $$
declare
  v_contacto uuid;
  v_conv uuid;
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_n bigint;
begin
  insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
    values (v_a, '+56930000001', 'QA mutación M1', 'admin')
    returning id into v_contacto;
  insert into nucleo.conversaciones (empresa_id, contacto_id)
    values (v_a, v_contacto) returning id into v_conv;

  insert into nucleo.conversacion_mensajes
    (empresa_id, conversacion_id, contacto_id, wa_message_id, direccion, modalidad, cuerpo)
    values (v_a, v_conv, v_contacto, 'wamid.mut.m1', 'entrante', 'texto', 'primero');

  begin
    insert into nucleo.conversacion_mensajes
      (empresa_id, conversacion_id, contacto_id, wa_message_id, direccion, modalidad, cuerpo)
      values (v_a, v_conv, v_contacto, 'wamid.mut.m1', 'entrante', 'texto', 'duplicado');
    raise exception 'FALLO 0021-4 M1 base: el duplicado fue ACEPTADO con el índice presente';
  exception when unique_violation then
    raise notice 'OK 0021-4 M1 base: duplicado rechazado (23505) con uq_mensaje_wa_message_id';
  end;

  execute 'drop index nucleo.uq_mensaje_wa_message_id';

  insert into nucleo.conversacion_mensajes
    (empresa_id, conversacion_id, contacto_id, wa_message_id, direccion, modalidad, cuerpo)
    values (v_a, v_conv, v_contacto, 'wamid.mut.m1', 'entrante', 'texto', 'duplicado mutado');

  select count(*) into v_n from nucleo.conversacion_mensajes where wa_message_id = 'wamid.mut.m1';
  if v_n <> 2 then
    raise exception 'FALLO 0021-4 M1 mutado: se esperaban 2 filas duplicadas, hay %', v_n;
  end if;
  raise notice 'OK 0021-4 M1 mutado: sin el índice entran 2 mensajes con el mismo wa_message_id';
end $$;
rollback;

-- ============================================================================
-- M2 — decisión definitiva de una solicitud (trigger)
-- ============================================================================
\echo '0021-4 M2: trg_solicitudes_10_transicion'
begin;
do $$
declare
  v_contacto uuid;
  v_sol uuid;
  v_estado nucleo.estado_solicitud;
  v_a uuid := '11111111-1111-1111-1111-111111111111';
begin
  insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
    values (v_a, '+56930000002', 'QA mutación M2', 'admin')
    returning id into v_contacto;
  insert into nucleo.solicitudes (empresa_id, tipo, solicitante_contacto_id, payload)
    values (v_a, 'documentos', v_contacto, '{}'::jsonb)
    returning id into v_sol;

  update nucleo.solicitudes
     set estado = 'aprobada', aprobado_por = 'qa-mut', decidido_en = now()
   where id = v_sol;

  begin
    update nucleo.solicitudes
       set estado = 'pendiente', aprobado_por = null, decidido_en = null
     where id = v_sol;
    raise exception 'FALLO 0021-4 M2 base: reabrir una aprobada fue ACEPTADO con el trigger';
  exception when check_violation then
    raise notice 'OK 0021-4 M2 base: reapertura rechazada (23514) por trg_solicitudes_10_transicion';
  end;

  execute 'drop trigger trg_solicitudes_10_transicion on nucleo.solicitudes';

  update nucleo.solicitudes
     set estado = 'pendiente', aprobado_por = null, decidido_en = null
   where id = v_sol;

  select estado into v_estado from nucleo.solicitudes where id = v_sol;
  if v_estado <> 'pendiente' then
    raise exception 'FALLO 0021-4 M2 mutado: el estado quedó en %, se esperaba pendiente', v_estado;
  end if;
  raise notice 'OK 0021-4 M2 mutado: sin el trigger una solicitud aprobada vuelve a pendiente';
end $$;
rollback;

-- ============================================================================
-- M3 — auditoría de consultas append-only (UPDATE y TRUNCATE)
-- ============================================================================
\echo '0021-4 M3: trg_consultas_agente_no_update / _no_truncate'
begin;
do $$
declare
  v_contacto uuid;
  v_id bigint;
  v_n bigint;
  v_a uuid := '11111111-1111-1111-1111-111111111111';
begin
  insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
    values (v_a, '+56930000003', 'QA mutación M3', 'admin')
    returning id into v_contacto;
  insert into nucleo.auditoria_consultas_agente
    (empresa_id, contacto_id, componente, acceso_otorgado)
    values (v_a, v_contacto, 'buzon', true)
    returning id into v_id;

  begin
    update nucleo.auditoria_consultas_agente set acceso_otorgado = false where id = v_id;
    raise exception 'FALLO 0021-4 M3 base: UPDATE fue ACEPTADO con el trigger';
  exception when check_violation then
    raise notice 'OK 0021-4 M3 base: UPDATE rechazado (23514) por trg_consultas_agente_no_update';
  end;

  begin
    execute 'truncate table nucleo.auditoria_consultas_agente';
    raise exception 'FALLO 0021-4 M3 base: TRUNCATE fue ACEPTADO con el trigger';
  exception when check_violation then
    raise notice 'OK 0021-4 M3 base: TRUNCATE rechazado (23514) por trg_consultas_agente_no_truncate';
  end;

  execute 'drop trigger trg_consultas_agente_no_update on nucleo.auditoria_consultas_agente';
  update nucleo.auditoria_consultas_agente set acceso_otorgado = false where id = v_id;
  get diagnostics v_n = row_count;
  if v_n <> 1 then
    raise exception 'FALLO 0021-4 M3 mutado: el UPDATE afectó % filas, se esperaba 1', v_n;
  end if;

  execute 'drop trigger trg_consultas_agente_no_truncate on nucleo.auditoria_consultas_agente';
  execute 'truncate table nucleo.auditoria_consultas_agente';
  select count(*) into v_n from nucleo.auditoria_consultas_agente;
  if v_n <> 0 then
    raise exception 'FALLO 0021-4 M3 mutado: tras TRUNCATE quedan % filas', v_n;
  end if;
  raise notice 'OK 0021-4 M3 mutado: sin los triggers la historia se puede editar y truncar';
end $$;
rollback;

-- ============================================================================
-- M4 — R-04: UNIQUE (empresa, cliente, id_comercial_flete) como árbitro final
-- ============================================================================
\echo '0021-4 M4: uq_viajes_id_comercial'
begin;
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_cli uuid := '22222222-2222-2222-2222-222222222221';
  v_ids uuid[];
  v_n bigint;
begin
  select array(
           select id from nucleo.viajes
            where empresa_id = v_a and cliente_id = v_cli
            order by numero_viaje limit 2
         ) into v_ids;
  if cardinality(v_ids) < 2 then
    raise exception 'FALLO 0021-4 M4 entorno: se necesitan 2 viajes del cliente A1';
  end if;

  update nucleo.viajes set id_comercial_flete = 'QAM-00001' where id = v_ids[1];

  begin
    update nucleo.viajes set id_comercial_flete = 'QAM-00001' where id = v_ids[2];
    raise exception 'FALLO 0021-4 M4 base: el código duplicado fue ACEPTADO con el índice';
  exception when unique_violation then
    raise notice 'OK 0021-4 M4 base: código duplicado rechazado (23505) por uq_viajes_id_comercial';
  end;

  execute 'drop index nucleo.uq_viajes_id_comercial';
  update nucleo.viajes set id_comercial_flete = 'QAM-00001' where id = v_ids[2];

  select count(*) into v_n from nucleo.viajes
   where empresa_id = v_a and cliente_id = v_cli and id_comercial_flete = 'QAM-00001';
  if v_n <> 2 then
    raise exception 'FALLO 0021-4 M4 mutado: se esperaban 2 viajes con el mismo código, hay %', v_n;
  end if;
  raise notice 'OK 0021-4 M4 mutado: sin el índice dos viajes del mismo cliente comparten QAM-00001';
end $$;
rollback;

-- ============================================================================
-- M5 — RLS: la política es el filtro (no el GRANT ni el FORCE)
-- ============================================================================
\echo '0021-4 M5: ALTER POLICY tenant_empresa'
begin;
insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
values ('b0787fc9-ba4e-4005-9371-40cb7c0fbfa4', '+56930000005', 'QA mutación M5 (B)', 'admin');

set local role tei_app;
select set_config('app.empresa_id', '11111111-1111-1111-1111-111111111111', true) is not null;
do $$
declare
  v_n bigint;
begin
  select count(*) into v_n from nucleo.contactos_whatsapp
   where empresa_id = 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  if v_n <> 0 then
    raise exception 'FALLO 0021-4 M5 base: tei_app ya ve % contactos de B ANTES de mutar', v_n;
  end if;
  raise notice 'OK 0021-4 M5 base: tei_app con contexto A ve 0 contactos de B';
end $$;
reset role;

alter policy tenant_empresa on nucleo.contactos_whatsapp
  using (true) with check (true);

set local role tei_app;
do $$
declare
  v_n bigint;
begin
  select count(*) into v_n from nucleo.contactos_whatsapp
   where empresa_id = 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  if v_n = 0 then
    raise exception 'FALLO 0021-4 M5 mutado: con USING(true) tei_app SIGUE sin ver B (la prueba no prueba nada)';
  end if;
  raise notice 'OK 0021-4 M5 mutado: con USING(true) tei_app ve % contacto(s) de B ⇒ la POLÍTICA filtra', v_n;
end $$;
reset role;
rollback;

-- ============================================================================
-- M6 — D3: el contador comercial no retrocede (trigger)
-- ============================================================================
\echo '0021-4 M6: trg_contador_10_no_retrocede'
begin;
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_cli uuid := '22222222-2222-2222-2222-222222222221';
  v_ult bigint;
begin
  delete from nucleo.id_comercial_contador
   where empresa_id = v_a and cliente_id = v_cli;
  insert into nucleo.id_comercial_contador (empresa_id, cliente_id, ultimo)
    values (v_a, v_cli, 500);

  begin
    update nucleo.id_comercial_contador set ultimo = 0
     where empresa_id = v_a and cliente_id = v_cli;
    raise exception 'FALLO 0021-4 M6 base: bajar el contador fue ACEPTADO con el trigger';
  exception when check_violation then
    raise notice 'OK 0021-4 M6 base: retroceso 500 -> 0 rechazado (23514) por trg_contador_10_no_retrocede';
  end;

  execute 'drop trigger trg_contador_10_no_retrocede on nucleo.id_comercial_contador';
  update nucleo.id_comercial_contador set ultimo = 0
   where empresa_id = v_a and cliente_id = v_cli;
  select ultimo into v_ult from nucleo.id_comercial_contador
   where empresa_id = v_a and cliente_id = v_cli;
  if v_ult <> 0 then
    raise exception 'FALLO 0021-4 M6 mutado: el contador quedó en %, se esperaba 0', v_ult;
  end if;
  raise notice 'OK 0021-4 M6 mutado: sin el trigger el contador retrocede 500 -> 0';
end $$;
rollback;

-- ============================================================================
-- M7 — D2: ID comercial inmutable una vez asignado (trigger)
-- ============================================================================
\echo '0021-4 M7: trg_viajes_10_id_comercial_inmutable'
begin;
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_cli uuid := '22222222-2222-2222-2222-222222222221';
  v_ids uuid[];
  v_cod text;
begin
  select array(
           select id from nucleo.viajes
            where empresa_id = v_a and cliente_id = v_cli
            order by numero_viaje limit 2
         ) into v_ids;
  if cardinality(v_ids) < 2 then
    raise exception 'FALLO 0021-4 M7 entorno: se necesitan 2 viajes del cliente A1';
  end if;

  update nucleo.viajes set id_comercial_flete = 'QAM-00001' where id = v_ids[1];
  raise notice 'OK 0021-4 M7 base: asignar desde NULL permitido (QAM-00001)';

  begin
    update nucleo.viajes set id_comercial_flete = 'QAM-00002' where id = v_ids[1];
    raise exception 'FALLO 0021-4 M7 base: reasignar un ID fue ACEPTADO con el trigger';
  exception when check_violation then
    raise notice 'OK 0021-4 M7 base: reasignación QAM-00001 -> QAM-00002 rechazada (23514)';
  end;

  begin
    update nucleo.viajes set id_comercial_flete = null where id = v_ids[1];
    raise exception 'FALLO 0021-4 M7 base: desasignar fue ACEPTADO con el trigger';
  exception when check_violation then
    raise notice 'OK 0021-4 M7 base: desasignación QAM-00001 -> NULL rechazada (23514)';
  end;

  execute 'drop trigger trg_viajes_10_id_comercial_inmutable on nucleo.viajes';
  update nucleo.viajes set id_comercial_flete = 'QAM-00002' where id = v_ids[1];
  select id_comercial_flete into v_cod from nucleo.viajes where id = v_ids[1];
  if v_cod <> 'QAM-00002' then
    raise exception 'FALLO 0021-4 M7 mutado: el ID quedó en %, se esperaba QAM-00002', v_cod;
  end if;
  raise notice 'OK 0021-4 M7 mutado: sin el trigger el ID cambia QAM-00001 -> QAM-00002';
end $$;
rollback;

-- ============================================================================
-- M8 — D5: máquina de estados de hoja_ruta + payload inmutable (trigger)
-- ============================================================================
\echo '0021-4 M8: trg_hoja_ruta_10_transicion'
begin;
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_contacto uuid;
  v_sol uuid;
  v_hr uuid;
  v_estado nucleo.estado_hoja_ruta;
  v_payload jsonb;
begin
  insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
    values (v_a, '+56930000006', 'QA mutación M8', 'admin')
    returning id into v_contacto;
  insert into nucleo.solicitudes (empresa_id, tipo, solicitante_contacto_id, payload)
    values (v_a, 'hoja_de_ruta', v_contacto, '{}'::jsonb)
    returning id into v_sol;
  insert into nucleo.hoja_ruta (empresa_id, contacto_id, solicitud_id, payload)
    values (v_a, v_contacto, v_sol, '{"cargas":[]}'::jsonb)
    returning id into v_hr;

  begin
    update nucleo.hoja_ruta set payload = '{"cargas":[1]}'::jsonb where id = v_hr;
    raise exception 'FALLO 0021-4 M8 base: cambiar el payload fue ACEPTADO con el trigger';
  exception when check_violation then
    raise notice 'OK 0021-4 M8 base: payload inmutable rechazado (23514)';
  end;

  begin
    update nucleo.hoja_ruta
       set estado = 'cargado', valores_cargados = '{}'::jsonb
     where id = v_hr;
    raise exception 'FALLO 0021-4 M8 base: propuesto -> cargado fue ACEPTADO con el trigger';
  exception when check_violation then
    raise notice 'OK 0021-4 M8 base: propuesto -> cargado rechazado (23514, D5)';
  end;

  execute 'drop trigger trg_hoja_ruta_10_transicion on nucleo.hoja_ruta';
  update nucleo.hoja_ruta
     set estado = 'cargado', valores_cargados = '{}'::jsonb
   where id = v_hr;
  select estado into v_estado from nucleo.hoja_ruta where id = v_hr;
  if v_estado <> 'cargado' then
    raise exception 'FALLO 0021-4 M8 mutado: el estado quedó en %, se esperaba cargado', v_estado;
  end if;

  update nucleo.hoja_ruta set payload = '{"cargas":[1]}'::jsonb where id = v_hr;
  select payload into v_payload from nucleo.hoja_ruta where id = v_hr;
  if v_payload <> '{"cargas":[1]}'::jsonb then
    raise exception 'FALLO 0021-4 M8 mutado: el payload no cambió (queda %)', v_payload;
  end if;
  raise notice 'OK 0021-4 M8 mutado: sin el trigger se aceptan la transición ilegal y el cambio de payload';
end $$;
rollback;

-- ============================================================================
-- M9 — D9: tope de 5 dígitos (el mecanismo está en el cuerpo de la función)
--      Se reemplaza la función por la versión de 0021 dentro de la transacción
--      y se hace ROLLBACK: PostgreSQL revierte el CREATE OR REPLACE.
-- ============================================================================
\echo '0021-4 M9: tope 99999 de obtener_siguiente_id_comercial_flete'
begin;
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_cli uuid := '22222222-2222-2222-2222-222222222221';
  v_ult bigint;
begin
  delete from nucleo.id_comercial_contador
   where empresa_id = v_a and cliente_id = v_cli;
  insert into nucleo.id_comercial_contador (empresa_id, cliente_id, ultimo)
    values (v_a, v_cli, 99999);

  begin
    perform nucleo.obtener_siguiente_id_comercial_flete(v_a, v_cli, 'SQM');
    raise exception 'FALLO 0021-4 M9 base: el tope 99999 fue ACEPTADO con el mecanismo';
  exception when check_violation then
    raise notice 'OK 0021-4 M9 base: 99999 -> 100000 rechazado (23514, D9)';
  end;

  select ultimo into v_ult from nucleo.id_comercial_contador
   where empresa_id = v_a and cliente_id = v_cli;
  if v_ult <> 99999 then
    raise exception 'FALLO 0021-4 M9 base: el rechazo quemó el número (ultimo=%)', v_ult;
  end if;
  raise notice 'OK 0021-4 M9 base: el incremento se revirtió (ultimo=99999)';
end $$;

-- Mutación: cuerpo exacto de 0021:603-636, sin el tope de 0022.
create or replace function nucleo.obtener_siguiente_id_comercial_flete(
  p_empresa_id uuid,
  p_cliente_id uuid,
  p_prefijo    text
)
returns text
language plpgsql
as $$
declare
  v_numero bigint;
begin
  if p_prefijo is null or p_prefijo !~ '^[A-Za-z0-9]{2,8}$' then
    raise exception 'Prefijo comercial inválido: % (2 a 8 caracteres alfanuméricos)', coalesce(p_prefijo, 'NULL')
      using errcode = '23514';
  end if;

  if not exists (
    select 1 from nucleo.clientes c
     where c.id = p_cliente_id and c.empresa_id = p_empresa_id
  ) then
    raise exception 'El cliente % no pertenece a la empresa % (la secuencia es por empresa-cliente)',
      p_cliente_id, p_empresa_id
      using errcode = '23514';
  end if;

  insert into nucleo.id_comercial_contador (empresa_id, cliente_id, ultimo)
    values (p_empresa_id, p_cliente_id, 1)
    on conflict (empresa_id, cliente_id)
    do update set ultimo = nucleo.id_comercial_contador.ultimo + 1
    returning ultimo into v_numero;

  return upper(p_prefijo) || '-' || lpad(v_numero::text, 5, '0');
end;
$$;

do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_cli uuid := '22222222-2222-2222-2222-222222222221';
  v_cod text;
  v_ult bigint;
begin
  v_cod := nucleo.obtener_siguiente_id_comercial_flete(v_a, v_cli, 'SQM');
  select ultimo into v_ult from nucleo.id_comercial_contador
   where empresa_id = v_a and cliente_id = v_cli;
  if v_cod <> 'SQM-10000' then
    raise exception 'FALLO 0021-4 M9 mutado: código %, se esperaba SQM-10000 truncado', v_cod;
  end if;
  if v_ult <> 100000 then
    raise exception 'FALLO 0021-4 M9 mutado: ultimo=%, se esperaba 100000', v_ult;
  end if;
  raise notice 'OK 0021-4 M9 mutado: sin el tope se emite % y el contador queda en % (código truncado)', v_cod, v_ult;
end $$;
rollback;

-- El ROLLBACK debe haber restaurado la función de 0022 (no un residuo mutado).
do $$
declare
  v_n integer;
begin
  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname = 'obtener_siguiente_id_comercial_flete'
     and p.prosrc like '%99999%';
  if v_n <> 1 then
    raise exception 'FALLO 0021-4 M9: el ROLLBACK NO restauró la función de 0022';
  end if;
  raise notice 'OK 0021-4 M9: ROLLBACK restauró la función de 0022 (tope presente)';
end $$;

-- Sanidad final: los 3 triggers y las 3 funciones de 0022 siguen vigentes.
do $$
declare
  v_n integer;
begin
  select count(*) into v_n
    from pg_trigger t
    join pg_class c on c.oid = t.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and not t.tgisinternal
     and t.tgname in ('trg_contador_10_no_retrocede',
                      'trg_viajes_10_id_comercial_inmutable',
                      'trg_hoja_ruta_10_transicion');
  if v_n <> 3 then
    raise exception 'FALLO 0021-4: tras los ROLLBACK hay % de 3 triggers de 0022', v_n;
  end if;

  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('fn_contador_no_retrocede',
                       'fn_viaje_id_comercial_inmutable',
                       'fn_hoja_ruta_transicion');
  if v_n <> 3 then
    raise exception 'FALLO 0021-4: tras los ROLLBACK hay % de 3 funciones de 0022', v_n;
  end if;
  raise notice 'OK 0021-4: los 3 triggers y 3 funciones de 0022 siguen vigentes tras las mutaciones';
end $$;

\echo '0021-4: todas las mutaciones revertidas (sin cambios persistentes)'
\echo '0021_04_mutacion: OK'
