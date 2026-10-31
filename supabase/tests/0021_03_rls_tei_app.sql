-- ============================================================================
-- Prueba 0021-3 — RLS del módulo agente con el ROL REAL de la aplicación
-- ============================================================================
-- Demuestra, con `tei_app` (sin BYPASSRLS), lo que el smoke 0021_01 no puede
-- probar porque corre como `postgres`:
--
--   A) Fail-closed sin contexto: `app.empresa_id` vacío ⇒ SELECT 0 filas en las
--      8 tablas del módulo e INSERT rechazado con 42501 (WITH CHECK).
--   B) Con contexto A: solo filas de A; ninguna fila de B; INSERT con
--      `empresa_id` de B rechazado con 42501; UPDATE de una fila de B afecta
--      0 filas (ni error ni fuga de existencia).
--   C) Simétrico con contexto B.
--   D) `auditoria_consultas_agente`: tei_app puede SELECT/INSERT, pero
--      UPDATE y DELETE reciben 42501 por PRIVILEGIO revocado (0021:863-864),
--      no por el trigger (que además existe, smoke C12 con postgres).
--   E) Mecanismo presente: RLS habilitado + FORCE en las 8 tablas y 9 políticas
--      con `nucleo.ctx_empresa()` (7 tenant_empresa + 2 de auditoría).
--
-- POR QUÉ ES UNA PRUEBA DISTINTA DE 0021_01
--   `postgres` local tiene BYPASSRLS: nada de lo anterior se ejecutaría. Ver
--   AGENTS.md §8 (RLS sin el rol real no es aislamiento).
--
-- DATOS
--   A = 11111111-1111-1111-1111-111111111111 (TEI)
--   B = b0787fc9-ba4e-4005-9371-40cb7c0fbfa4 (empresa de pruebas)
--   Clientes: A1 = 22222222-…-222221 ; B1 = c61c819b-df68-4617-8666-c88b5f85f54d
--   Las fixtures de A y B se crean DENTRO de la misma transacción (contexto A
--   para A, contexto B para B) y se ven entre sí porque el GUC cambia por
--   sentencia: así se prueba el filtro sin commitear datos de B.
--   Todo termina en ROLLBACK: 0 filas residuales.
--
-- USO (sin psql en el host, se usa el del contenedor):
--   docker exec -e PGPASSWORD=<credencial local del Makefile> -i supabase_db_TRANSTEI \
--     psql -h 127.0.0.1 -U tei_app -d tei_test -v ON_ERROR_STOP=1 \
--     < supabase/tests/0021_03_rls_tei_app.sql
--
-- SALIDA: NOTICE 'OK 0021-3x ...' por aserción; cualquier 'FALLO ...' aborta
-- con código ≠ 0. El script aborta si el rol no es tei_app sin BYPASSRLS.
-- ============================================================================

\set ON_ERROR_STOP on

\echo '0021-3: rol efectivo (exige tei_app sin BYPASSRLS)'
do $$
declare
  v_by boolean;
begin
  select rolbypassrls into v_by from pg_roles where rolname = current_user;
  if current_user <> 'tei_app' or coalesce(v_by, true) then
    raise exception 'FALLO 0021-3 rol: se exige tei_app sin BYPASSRLS; current_user=% bypass=%',
      current_user, v_by;
  end if;
  raise notice 'OK 0021-3 rol: current_user=% bypass=%', current_user, v_by;
end $$;

\echo '0021-3: mecanismo declarado (RLS + FORCE + 9 políticas)'
do $$
declare
  v_n integer;
begin
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('contactos_whatsapp','permisos_contacto','conversaciones',
                       'conversacion_mensajes','solicitudes','hoja_ruta',
                       'id_comercial_contador','auditoria_consultas_agente')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 8 then
    raise exception 'FALLO 0021-3E: % de 8 tablas con RLS habilitado + FORCE', v_n;
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('contactos_whatsapp','permisos_contacto','conversaciones',
                       'conversacion_mensajes','solicitudes','hoja_ruta',
                       'id_comercial_contador','auditoria_consultas_agente')
     and (coalesce(qual, '') like '%ctx_empresa%'
          or coalesce(with_check, '') like '%ctx_empresa%');
  if v_n <> 9 then
    raise exception 'FALLO 0021-3E: se esperaban 9 políticas con ctx_empresa, hay %', v_n;
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('contactos_whatsapp','permisos_contacto','conversaciones',
                       'conversacion_mensajes','solicitudes','hoja_ruta',
                       'id_comercial_contador')
     and cmd = 'ALL';
  if v_n <> 7 then
    raise exception 'FALLO 0021-3E: se esperaban 7 políticas FOR ALL de tenant, hay %', v_n;
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo' and tablename = 'auditoria_consultas_agente'
     and cmd in ('SELECT','INSERT');
  if v_n <> 2 then
    raise exception 'FALLO 0021-3E: auditoría de consultas debe tener solo SELECT+INSERT, hay %', v_n;
  end if;

  raise notice 'OK 0021-3E mecanismo: RLS+FORCE en 8 tablas, 9 políticas con ctx_empresa';
end $$;

begin;

-- ---------------------------------------------------------------------------
-- Fixtures: cadena completa de A y de B, cada una bajo su propio contexto
-- ---------------------------------------------------------------------------
\echo '0021-3: fixtures A y B dentro de la transacción'
do $$
declare
  v_a     uuid := '11111111-1111-1111-1111-111111111111';
  v_b     uuid := 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  v_a_cli uuid := '22222222-2222-2222-2222-222222222221';
  v_b_cli uuid := 'c61c819b-df68-4617-8666-c88b5f85f54d';
  v_id    uuid;
  v_big   bigint;
begin
  -- ---------- Empresa A ----------
  perform set_config('app.empresa_id', v_a::text, true);

  insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
    values (v_a, '+56922000001', 'QA RLS A', 'admin')
    returning id into v_id;
  perform set_config('qa.a_contacto', v_id::text, true);

  insert into nucleo.permisos_contacto (empresa_id, contacto_id, componente, permitido)
    values (v_a, v_id, 'buzon', true)
    returning id into v_id;
  perform set_config('qa.a_permiso', v_id::text, true);

  insert into nucleo.conversaciones (empresa_id, contacto_id)
    values (v_a, current_setting('qa.a_contacto')::uuid)
    returning id into v_id;
  perform set_config('qa.a_conversacion', v_id::text, true);

  insert into nucleo.conversacion_mensajes
    (empresa_id, conversacion_id, contacto_id, wa_message_id, direccion, modalidad, cuerpo)
    values (v_a, v_id, current_setting('qa.a_contacto')::uuid,
            'wamid.rls.a.1', 'entrante', 'texto', 'hola A')
    returning id into v_id;
  perform set_config('qa.a_mensaje', v_id::text, true);

  insert into nucleo.solicitudes (empresa_id, tipo, solicitante_contacto_id, payload)
    values (v_a, 'documentos', current_setting('qa.a_contacto')::uuid, '{"qa":"rls"}'::jsonb)
    returning id into v_id;
  perform set_config('qa.a_solicitud', v_id::text, true);

  insert into nucleo.hoja_ruta (empresa_id, contacto_id, payload)
    values (v_a, current_setting('qa.a_contacto')::uuid, '{"cargas":[]}'::jsonb)
    returning id into v_id;
  perform set_config('qa.a_hoja_ruta', v_id::text, true);

  insert into nucleo.id_comercial_contador (empresa_id, cliente_id, ultimo)
    values (v_a, v_a_cli, 1);

  insert into nucleo.auditoria_consultas_agente
    (empresa_id, contacto_id, componente, acceso_otorgado)
    values (v_a, current_setting('qa.a_contacto')::uuid, 'buzon', true)
    returning id into v_big;
  perform set_config('qa.a_auditoria', v_big::text, true);

  -- ---------- Empresa B ----------
  perform set_config('app.empresa_id', v_b::text, true);

  insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
    values (v_b, '+56922000002', 'QA RLS B', 'admin')
    returning id into v_id;
  perform set_config('qa.b_contacto', v_id::text, true);

  insert into nucleo.permisos_contacto (empresa_id, contacto_id, componente, permitido)
    values (v_b, v_id, 'buzon', true)
    returning id into v_id;
  perform set_config('qa.b_permiso', v_id::text, true);

  insert into nucleo.conversaciones (empresa_id, contacto_id)
    values (v_b, current_setting('qa.b_contacto')::uuid)
    returning id into v_id;
  perform set_config('qa.b_conversacion', v_id::text, true);

  insert into nucleo.conversacion_mensajes
    (empresa_id, conversacion_id, contacto_id, wa_message_id, direccion, modalidad, cuerpo)
    values (v_b, v_id, current_setting('qa.b_contacto')::uuid,
            'wamid.rls.b.1', 'entrante', 'texto', 'hola B')
    returning id into v_id;
  perform set_config('qa.b_mensaje', v_id::text, true);

  insert into nucleo.solicitudes (empresa_id, tipo, solicitante_contacto_id, payload)
    values (v_b, 'documentos', current_setting('qa.b_contacto')::uuid, '{"qa":"rls"}'::jsonb)
    returning id into v_id;
  perform set_config('qa.b_solicitud', v_id::text, true);

  insert into nucleo.hoja_ruta (empresa_id, contacto_id, payload)
    values (v_b, current_setting('qa.b_contacto')::uuid, '{"cargas":[]}'::jsonb)
    returning id into v_id;
  perform set_config('qa.b_hoja_ruta', v_id::text, true);

  insert into nucleo.id_comercial_contador (empresa_id, cliente_id, ultimo)
    values (v_b, v_b_cli, 1);

  insert into nucleo.auditoria_consultas_agente
    (empresa_id, contacto_id, componente, acceso_otorgado)
    values (v_b, current_setting('qa.b_contacto')::uuid, 'buzon', true)
    returning id into v_big;
  perform set_config('qa.b_auditoria', v_big::text, true);

  perform set_config('app.empresa_id', '', true);
  raise notice 'OK 0021-3F fixtures: cadena A y B creadas (8 tablas cada una)';
end $$;

-- ---------------------------------------------------------------------------
-- A) Sin contexto: fail-closed (0 filas) e INSERT rechazado
-- ---------------------------------------------------------------------------
\echo '0021-3: sin contexto (fail-closed)'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_n bigint;
  v_ok boolean := false;
  r record;
begin
  perform set_config('app.empresa_id', '', true);
  perform set_config('nucleo.auth_id', '', true);

  for r in
    select unnest(array['contactos_whatsapp','permisos_contacto','conversaciones',
                        'conversacion_mensajes','solicitudes','hoja_ruta',
                        'id_comercial_contador','auditoria_consultas_agente']) as t
  loop
    execute format('select count(*) from nucleo.%I', r.t) into v_n;
    if v_n <> 0 then
      raise exception 'FALLO 0021-3A: sin app.empresa_id nucleo.% tiene % filas visibles', r.t, v_n;
    end if;
  end loop;

  begin
    insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
      values (v_a, '+56922000009', 'Sin contexto', 'admin');
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3A: INSERT en contactos sin contexto fue ACEPTADO';
  end if;

  v_ok := false;
  begin
    insert into nucleo.auditoria_consultas_agente
      (empresa_id, contacto_id, componente, acceso_otorgado)
      values (v_a, current_setting('qa.a_contacto')::uuid, 'buzon', true);
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3A: INSERT en auditoría de consultas sin contexto fue ACEPTADO';
  end if;

  update nucleo.contactos_whatsapp set nombre = 'sin contexto'
   where id = current_setting('qa.a_contacto')::uuid;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0021-3A: UPDATE sin contexto afectó % filas', v_n;
  end if;

  raise notice 'OK 0021-3A sin contexto: 0 filas en 8 tablas, INSERT ⇒ 42501, UPDATE ⇒ 0 filas';
end $$;

-- ---------------------------------------------------------------------------
-- B) Contexto A: solo A; B invisible; INSERT ajeno ⇒ 42501
-- ---------------------------------------------------------------------------
\echo '0021-3: contexto A'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_b uuid := 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  v_n bigint;
  v_ajenas bigint;
  v_ok boolean := false;
  r record;
begin
  perform set_config('app.empresa_id', v_a::text, true);

  for r in
    select unnest(array['contactos_whatsapp','permisos_contacto','conversaciones',
                        'conversacion_mensajes','solicitudes','hoja_ruta',
                        'id_comercial_contador','auditoria_consultas_agente']) as t
  loop
    execute format('select count(*) from nucleo.%I', r.t) into v_n;
    if v_n = 0 then
      raise exception 'FALLO 0021-3B: con contexto A, nucleo.% no ve SU fila', r.t;
    end if;
    execute format('select count(*) from nucleo.%I where empresa_id <> %L', r.t, v_a)
      into v_ajenas;
    if v_ajenas <> 0 then
      raise exception 'FALLO 0021-3B: con contexto A, nucleo.% muestra % filas de B', r.t, v_ajenas;
    end if;
  end loop;

  select count(*) into v_n from nucleo.contactos_whatsapp
   where id = current_setting('qa.b_contacto')::uuid;
  if v_n <> 0 then
    raise exception 'FALLO 0021-3B: el contacto de B es visible con contexto A';
  end if;
  select count(*) into v_n from nucleo.solicitudes
   where id = current_setting('qa.b_solicitud')::uuid;
  if v_n <> 0 then
    raise exception 'FALLO 0021-3B: la solicitud de B es visible con contexto A';
  end if;
  select count(*) into v_n from nucleo.auditoria_consultas_agente
   where id = current_setting('qa.b_auditoria')::bigint;
  if v_n <> 0 then
    raise exception 'FALLO 0021-3B: la consulta auditada de B es visible con contexto A';
  end if;
  select count(*) into v_n from nucleo.id_comercial_contador
   where empresa_id = v_b;
  if v_n <> 0 then
    raise exception 'FALLO 0021-3B: el contador de B es visible con contexto A';
  end if;

  -- INSERT con empresa_id de B bajo contexto A ⇒ 42501 (WITH CHECK)
  begin
    insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
      values (v_b, '+56922000003', 'Cruzado', 'admin');
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3B: INSERT de contacto con empresa_id de B fue ACEPTADO';
  end if;

  v_ok := false;
  begin
    insert into nucleo.solicitudes (empresa_id, tipo, solicitante_contacto_id, payload)
      values (v_b, 'documentos', current_setting('qa.b_contacto')::uuid, '{}'::jsonb);
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3B: INSERT de solicitud con empresa_id de B fue ACEPTADO';
  end if;

  -- UPDATE de una fila de B con contexto A ⇒ 0 filas
  update nucleo.contactos_whatsapp set nombre = 'intento cruzado'
   where id = current_setting('qa.b_contacto')::uuid;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0021-3B: UPDATE de un contacto de B afectó % filas con contexto A', v_n;
  end if;

  -- Escape de tenant por UPDATE: mover una fila de A a B ⇒ WITH CHECK 42501
  v_ok := false;
  begin
    update nucleo.contactos_whatsapp set empresa_id = v_b
     where id = current_setting('qa.a_contacto')::uuid;
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3B: UPDATE movió una fila de A a la empresa B (fuga de tenant)';
  end if;

  raise notice 'OK 0021-3B contexto A: solo filas de A, B invisible, INSERT ajeno ⇒ 42501, UPDATE ajeno ⇒ 0 filas, cambio de empresa ⇒ 42501';
end $$;

-- ---------------------------------------------------------------------------
-- C) Simétrico: contexto B
-- ---------------------------------------------------------------------------
\echo '0021-3: contexto B'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_b uuid := 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  v_n bigint;
  v_ajenas bigint;
  v_ok boolean := false;
  r record;
begin
  perform set_config('app.empresa_id', v_b::text, true);

  for r in
    select unnest(array['contactos_whatsapp','permisos_contacto','conversaciones',
                        'conversacion_mensajes','solicitudes','hoja_ruta',
                        'id_comercial_contador','auditoria_consultas_agente']) as t
  loop
    execute format('select count(*) from nucleo.%I', r.t) into v_n;
    if v_n = 0 then
      raise exception 'FALLO 0021-3C: con contexto B, nucleo.% no ve SU fila', r.t;
    end if;
    execute format('select count(*) from nucleo.%I where empresa_id <> %L', r.t, v_b)
      into v_ajenas;
    if v_ajenas <> 0 then
      raise exception 'FALLO 0021-3C: con contexto B, nucleo.% muestra % filas ajenas', r.t, v_ajenas;
    end if;
  end loop;

  select count(*) into v_n from nucleo.contactos_whatsapp
   where id = current_setting('qa.a_contacto')::uuid;
  if v_n <> 0 then
    raise exception 'FALLO 0021-3C: el contacto de A es visible con contexto B';
  end if;

  begin
    insert into nucleo.contactos_whatsapp (empresa_id, telefono, nombre, rol)
      values (v_a, '+56922000004', 'Cruzado B', 'admin');
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3C: INSERT con empresa_id de A fue ACEPTADO con contexto B';
  end if;

  raise notice 'OK 0021-3C contexto B: solo filas de B; A invisible; INSERT ajeno ⇒ 42501';
end $$;

-- ---------------------------------------------------------------------------
-- D) Auditoría de consultas: SELECT/INSERT sí; UPDATE/DELETE ⇒ 42501
-- ---------------------------------------------------------------------------
\echo '0021-3: auditoría append-only por privilegio'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_id bigint;
  v_ok boolean;
  v_priv boolean;
begin
  perform set_config('app.empresa_id', v_a::text, true);

  insert into nucleo.auditoria_consultas_agente
    (empresa_id, contacto_id, componente, herramienta, acceso_otorgado)
    values (v_a, current_setting('qa.a_contacto')::uuid, 'buzon', 'qa_rls', false)
    returning id into v_id;

  v_ok := false;
  begin
    update nucleo.auditoria_consultas_agente set acceso_otorgado = true where id = v_id;
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3D: UPDATE de auditoría de consultas fue ACEPTADO por tei_app';
  end if;

  v_ok := false;
  begin
    delete from nucleo.auditoria_consultas_agente where id = v_id;
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3D: DELETE de auditoría de consultas fue ACEPTADO por tei_app';
  end if;

  select has_table_privilege('nucleo.auditoria_consultas_agente', 'SELECT') into v_priv;
  if not v_priv then raise exception 'FALLO 0021-3D: tei_app perdió SELECT sobre la auditoría'; end if;
  select has_table_privilege('nucleo.auditoria_consultas_agente', 'INSERT') into v_priv;
  if not v_priv then raise exception 'FALLO 0021-3D: tei_app perdió INSERT sobre la auditoría'; end if;
  select has_table_privilege('nucleo.auditoria_consultas_agente', 'UPDATE') into v_priv;
  if v_priv then raise exception 'FALLO 0021-3D: tei_app conserva UPDATE sobre la auditoría'; end if;
  select has_table_privilege('nucleo.auditoria_consultas_agente', 'DELETE') into v_priv;
  if v_priv then raise exception 'FALLO 0021-3D: tei_app conserva DELETE sobre la auditoría'; end if;

  raise notice 'OK 0021-3D auditoría: INSERT aceptado; UPDATE/DELETE ⇒ 42501 (privilegio revocado)';
end $$;

-- ---------------------------------------------------------------------------
-- E) Sin DELETE en las tablas de negocio del módulo (GRANT 0021:855-860)
-- ---------------------------------------------------------------------------
\echo '0021-3: sin DELETE para tei_app en tablas de negocio'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_ok boolean := false;
begin
  perform set_config('app.empresa_id', v_a::text, true);
  begin
    delete from nucleo.contactos_whatsapp
     where id = current_setting('qa.a_contacto')::uuid;
  exception when insufficient_privilege then
    v_ok := true;
  end;
  if not v_ok then
    raise exception 'FALLO 0021-3E: tei_app pudo hacer DELETE en contactos_whatsapp';
  end if;
  raise notice 'OK 0021-3E: DELETE en tablas del módulo ⇒ 42501 (no otorgado por 0021)';
end $$;

rollback;

\echo '0021-3: transacción revertida (0 filas residuales)'
\echo '0021_03_rls_tei_app: OK'
