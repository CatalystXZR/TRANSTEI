-- ============================================================================
-- Prueba 0020-1 — RLS multiempresa, una sesión, rol de aplicación
-- ============================================================================
-- Demuestra INV-T01 (docs/datos/invariantes.md):
--   A) Sin contexto de empresa: 0 filas en toda tabla de tenant (fail-closed).
--   B) Con contexto de A: solo filas de A; una fila concreta de B no se ve.
--   C) Con contexto de B: solo filas de B (simétrico).
--   D) INSERT con empresa_id ajena ⇒ SQLSTATE 42501 (WITH CHECK).
--   E) INSERT con la empresa del contexto ⇒ permitido, y el trigger de
--      auditoría (SECURITY DEFINER) sigue registrando el cambio.
--   F) UPDATE de una fila ajena ⇒ 0 filas (ni error ni fuga).
--   G) Contexto con basura ('no-es-uuid') ⇒ 0 filas, sin excepción 22P02.
--   H) `empresas`/`usuarios_empresa`: la empresa actual + las del propio
--      auth_id; nunca la de otro tenant.
--   I) `auditoria`: INSERT solo con la empresa del contexto; UPDATE denegado.
--   J) Catálogos globales: `transiciones_viaje` lectura sí, escritura no.
--      (La tabla `cutover_control` fue retirada en la migración `0035`,
--      2026-11-12; su aserción histórica se eliminó de esta prueba.)
--   K) `siguiente_folio` con empresa ajena ⇒ 42501 (vía función del núcleo).
--   L) El contexto muere con el COMMIT: una transacción nueva en la MISMA
--      conexión (caso pool) ve 0 filas.
--
-- IMPORTANTE — esta prueba NO vale con `postgres`/`service_role`: esos roles
-- tienen BYPASSRLS y verían todo. El primer bloque aborta si el rol no es
-- `tei_app` (AGENTS.md §8, database-safety §5).
--
-- Datos: la empresa A es la del seed. La empresa B y su cliente los crea el
-- runner `0020_01_aislamiento.sh` (idempotente, como supabase_admin), de modo
-- que la prueba funciona sobre un `tei_test` recién clonado.
--   A = 11111111-1111-1111-1111-111111111111 (Transportes TEI SpA)
--   B = b0787fc9-ba4e-4005-9371-40cb7c0fbfa4 (empresa de pruebas)
--   cliente de B = 49f2d33e-7791-4fcd-88be-cef5bd366a43
-- No crea empresas. Todo INSERT/UPDATE va dentro de una transacción que
-- termina en ROLLBACK: no deja datos.
--
-- Uso:
--   bash supabase/tests/0020_01_aislamiento.sh
-- ============================================================================

\set ON_ERROR_STOP on

\echo '0020-1: rol efectivo'
do $$
declare
  v_bypass boolean;
begin
  select rolbypassrls into v_bypass from pg_roles where rolname = current_user;
  if current_user <> 'tei_app' or coalesce(v_bypass, true) then
    raise exception 'FALLO 0020-1: la prueba exige el rol tei_app sin BYPASSRLS, corre como % (bypass=%)',
      current_user, v_bypass;
  end if;
  raise notice 'OK 0020-1 rol: current_user=% bypass=%', current_user, v_bypass;
end $$;

begin;

-- ---------------------------------------------------------------------------
-- A) Sin contexto: 0 filas
-- ---------------------------------------------------------------------------
\echo '0020-1: sin contexto'
do $$
declare
  v_n bigint;
  r record;
begin
  -- Garantiza que no hay contexto previo en esta transacción.
  perform set_config('app.empresa_id', '', true);
  perform set_config('nucleo.auth_id', '', true);

  for r in
    select c.relname
      from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'nucleo' and c.relkind = 'r'
       and c.relname not in ('empresas', 'usuarios_empresa', 'auditoria',
                             'transiciones_viaje')
     order by c.relname
  loop
    execute format('select count(*) from nucleo.%I', r.relname) into v_n;
    if v_n <> 0 then
      raise exception 'FALLO 0020-1A: sin app.empresa_id, nucleo.% tiene % filas visibles', r.relname, v_n;
    end if;
  end loop;

  select count(*) into v_n from nucleo.auditoria;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1A: sin app.empresa_id, nucleo.auditoria tiene % filas visibles', v_n;
  end if;

  select count(*) into v_n from nucleo.empresas;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1A: sin contexto, nucleo.empresas tiene % filas', v_n;
  end if;
  select count(*) into v_n from nucleo.usuarios_empresa;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1A: sin contexto, nucleo.usuarios_empresa tiene % filas', v_n;
  end if;

  -- Catálogos globales: sí se leen (no son datos de tenant).
  select count(*) into v_n from nucleo.transiciones_viaje;
  if v_n = 0 then
    raise exception 'FALLO 0020-1A: transiciones_viaje debería ser legible (catálogo global) y devolvió 0';
  end if;

  raise notice 'OK 0020-1A sin contexto: 0 filas en tablas de tenant, catálogos globales legibles';
end $$;

-- ---------------------------------------------------------------------------
-- B/C) Contexto A y contexto B
-- ---------------------------------------------------------------------------
\echo '0020-1: contexto empresa A y empresa B'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_b uuid := 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  v_cliente_b uuid := '49f2d33e-7791-4fcd-88be-cef5bd366a43';
  v_cliente_a uuid;
  v_n bigint;
  v_ajenas bigint;
begin
  perform set_config('app.empresa_id', v_a::text, true);
  select id into v_cliente_a from nucleo.clientes where empresa_id = v_a order by razon_social limit 1;

  -- A
  select count(*) filter (where empresa_id <> v_a), count(*)
    into v_ajenas, v_n from nucleo.clientes;
  if v_n = 0 then
    raise exception 'FALLO 0020-1B: con empresa A no se ve ningún cliente de A';
  end if;
  if v_ajenas <> 0 then
    raise exception 'FALLO 0020-1B: con empresa A se ven % clientes de OTRA empresa', v_ajenas;
  end if;
  select count(*) into v_n from nucleo.clientes where id = v_cliente_b;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1B: un cliente de B es visible con contexto A';
  end if;
  select count(*) into v_n from nucleo.viajes where empresa_id <> v_a;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1B: con empresa A se ven viajes de otra empresa';
  end if;

  -- B
  perform set_config('app.empresa_id', v_b::text, true);
  select count(*) filter (where empresa_id <> v_b), count(*)
    into v_ajenas, v_n from nucleo.clientes;
  if v_n = 0 then
    raise exception 'FALLO 0020-1C: con empresa B no se ve ningún cliente de B';
  end if;
  if v_ajenas <> 0 then
    raise exception 'FALLO 0020-1C: con empresa B se ven % clientes de OTRA empresa', v_ajenas;
  end if;
  select count(*) into v_n from nucleo.clientes where id = v_cliente_b;
  if v_n <> 1 then
    raise exception 'FALLO 0020-1C: el cliente de B debería ser visible con contexto B (vistos %)', v_n;
  end if;
  select count(*) into v_n from nucleo.clientes where id = v_cliente_a;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1C: un cliente de A es visible con contexto B';
  end if;

  raise notice 'OK 0020-1B/C contexto: cada empresa ve solo sus filas y no ve la fila concreta de la otra';
end $$;

-- ---------------------------------------------------------------------------
-- D/E) INSERT: ajena ⇒ 42501, propia ⇒ permitida (+ auditoría del trigger)
-- ---------------------------------------------------------------------------
\echo '0020-1: INSERT con empresa ajena y propia'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_b uuid := 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  v_id uuid := gen_random_uuid();
  v_rut text := 'TEST-' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 8);
  v_msg text;
  v_n bigint;
  v_aceptado boolean := false;
begin
  perform set_config('app.empresa_id', v_a::text, true);

  -- D) empresa ajena
  begin
    insert into nucleo.clientes (id, empresa_id, razon_social, rut)
    values (v_id, v_b, 'Cliente cruzado', v_rut);
    v_aceptado := true;
  exception
    when insufficient_privilege then
      get stacked diagnostics v_msg = message_text;
      raise notice 'OK 0020-1D INSERT ajeno rechazado: SQLSTATE=42501 (%)', v_msg;
  end;
  if v_aceptado then
    raise exception 'FALLO 0020-1D: INSERT con empresa_id de B fue ACEPTADO con contexto A';
  end if;

  -- E) empresa propia
  insert into nucleo.clientes (id, empresa_id, razon_social, rut)
  values (v_id, v_a, 'Cliente del contexto', v_rut);
  select count(*) into v_n from nucleo.clientes where id = v_id;
  if v_n <> 1 then
    raise exception 'FALLO 0020-1E: el cliente insertado con la empresa del contexto no es visible';
  end if;

  -- El trigger de auditoría es SECURITY DEFINER: debe seguir escribiendo
  -- aunque la tabla tenga FORCE RLS.
  select count(*) into v_n from nucleo.auditoria where registro_id = v_id;
  if v_n <> 1 then
    raise exception 'FALLO 0020-1E: el trigger fn_auditoria no registró el INSERT (filas: %)', v_n;
  end if;
  raise notice 'OK 0020-1E INSERT propio aceptado, visible y auditado por el trigger';

  -- El alta de una empresa nueva NO es operación de la app (decisión 6).
  v_aceptado := false;
  begin
    insert into nucleo.empresas (id, codigo, razon_social, rut)
    values (gen_random_uuid(), 'TST20', 'Empresa nueva', '76.000.000-0');
    v_aceptado := true;
  exception
    when insufficient_privilege then
      raise notice 'OK 0020-1E alta de empresa rechazada (por diseño: la hace el seed)';
  end;
  if v_aceptado then
    raise exception 'FALLO 0020-1E: el alta de empresa fue ACEPTADA con tei_app';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- F) UPDATE de fila ajena ⇒ 0 filas
-- ---------------------------------------------------------------------------
\echo '0020-1: UPDATE de fila ajena'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_cliente_b uuid := '49f2d33e-7791-4fcd-88be-cef5bd366a43';
  v_n bigint;
begin
  perform set_config('app.empresa_id', v_a::text, true);
  update nucleo.clientes set razon_social = 'intento cruzado' where id = v_cliente_b;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1F: UPDATE de un cliente de B afectó % filas con contexto A', v_n;
  end if;
  raise notice 'OK 0020-1F UPDATE ajeno: 0 filas afectadas, sin error (no filtra existencia)';
end $$;

-- ---------------------------------------------------------------------------
-- G) Contexto inválido o vacío ⇒ 0 filas, sin 22P02
-- ---------------------------------------------------------------------------
\echo '0020-1: contexto inválido'
do $$
declare
  v_n bigint;
begin
  perform set_config('app.empresa_id', 'no-es-un-uuid', true);
  select count(*) into v_n from nucleo.viajes;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1G: con app.empresa_id basura se ven % viajes', v_n;
  end if;

  perform set_config('app.empresa_id', '', true);
  select count(*) into v_n from nucleo.viajes;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1G: con app.empresa_id vacío se ven % viajes', v_n;
  end if;
  raise notice 'OK 0020-1G contexto inválido/vacío: 0 filas sin excepción 22P02';
end $$;

-- ---------------------------------------------------------------------------
-- H) empresas / usuarios_empresa: lectura acotada al auth_id propio
-- ---------------------------------------------------------------------------
\echo '0020-1: mis-empresas (auth_id propio)'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_b uuid := 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  v_auth uuid;
  v_n bigint;
begin
  -- El auth_id se lee con contexto de empresa (la membresía es de A).
  perform set_config('app.empresa_id', v_a::text, true);
  select auth_id into v_auth
    from nucleo.usuarios_empresa
   where empresa_id = v_a and activo
   order by rol limit 1;
  if v_auth is null then
    raise exception 'FALLO 0020-1H: no hay membresía activa en A para tomar un auth_id de prueba';
  end if;

  -- Ahora solo auth_id (es el caso de GET /nucleo/mis-empresas).
  perform set_config('app.empresa_id', '', true);
  perform set_config('nucleo.auth_id', v_auth::text, true);

  select count(*) into v_n from nucleo.empresas where id = v_b;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1H: la empresa B es visible para un usuario que no le pertenece';
  end if;
  select count(*) into v_n from nucleo.empresas where id = v_a;
  if v_n <> 1 then
    raise exception 'FALLO 0020-1H: mis-empresas no ve la empresa del usuario (filas: %)', v_n;
  end if;

  -- Membresías: las propias; nunca las de otros usuarios.
  select count(*) into v_n from nucleo.usuarios_empresa where auth_id <> v_auth;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1H: se ven % membresías de otros usuarios', v_n;
  end if;

  -- Con contexto de empresa manda la empresa, no el auth_id.
  perform set_config('nucleo.auth_id', '', true);
  perform set_config('app.empresa_id', v_a::text, true);
  select count(*) into v_n from nucleo.empresas where id = v_a;
  if v_n <> 1 then
    raise exception 'FALLO 0020-1H: con contexto A no se ve la empresa A';
  end if;
  select count(*) into v_n from nucleo.empresas where id = v_b;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1H: con contexto A se ve la empresa B';
  end if;

  raise notice 'OK 0020-1H empresas/usuarios_empresa: solo la empresa actual y las membresías propias';
end $$;

-- ---------------------------------------------------------------------------
-- I) auditoria: INSERT solo con la empresa del contexto; UPDATE denegado
-- ---------------------------------------------------------------------------
\echo '0020-1: auditoria append-only'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_b uuid := 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  v_aceptado boolean;
begin
  perform set_config('app.empresa_id', v_a::text, true);

  v_aceptado := false;
  begin
    insert into nucleo.auditoria (empresa_id, tabla, operacion)
    values (v_b, 'nucleo.viajes', 'INSERT');
    v_aceptado := true;
  exception
    when insufficient_privilege then
      raise notice 'OK 0020-1I auditoria: INSERT con empresa ajena rechazado';
  end;
  if v_aceptado then
    raise exception 'FALLO 0020-1I: INSERT en auditoria con empresa B fue ACEPTADO con contexto A';
  end if;

  insert into nucleo.auditoria (empresa_id, tabla, operacion)
  values (v_a, 'nucleo.viajes', 'INSERT');
  raise notice 'OK 0020-1I auditoria: INSERT con la empresa del contexto aceptado';

  v_aceptado := false;
  begin
    update nucleo.auditoria set operacion = 'UPDATE' where empresa_id = v_a;
    v_aceptado := true;
  exception
    when insufficient_privilege then
      raise notice 'OK 0020-1I auditoria: UPDATE denegado (append-only)';
  end;
  if v_aceptado then
    raise exception 'FALLO 0020-1I: UPDATE en auditoria fue ACEPTADO';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- J) catálogos globales: lectura sí, escritura no
-- ---------------------------------------------------------------------------
\echo '0020-1: catalogos globales'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_aceptado boolean;
begin
  perform set_config('app.empresa_id', v_a::text, true);

  v_aceptado := false;
  begin
    insert into nucleo.transiciones_viaje (estado_origen, estado_destino, requiere_motivo)
    values ('borrador', 'en_ruta', false);
    v_aceptado := true;
  exception
    when insufficient_privilege then
      raise notice 'OK 0020-1J transiciones_viaje: escritura denegada';
  end;
  if v_aceptado then
    raise exception 'FALLO 0020-1J: INSERT en transiciones_viaje fue ACEPTADO';
  end if;

  v_aceptado := false;
  begin
    update nucleo.viaje_eventos set descripcion = 'x';
    v_aceptado := true;
  exception
    when insufficient_privilege then
      raise notice 'OK 0020-1J viaje_eventos: UPDATE denegado (append-only)';
    when others then
      raise notice 'OK 0020-1J viaje_eventos: UPDATE rechazado con SQLSTATE %', sqlstate;
  end;
  if v_aceptado then
    raise exception 'FALLO 0020-1J: UPDATE en viaje_eventos fue ACEPTADO';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- K) siguiente_folio con empresa ajena ⇒ 42501 (función invoker, no definer)
-- ---------------------------------------------------------------------------
\echo '0020-1: siguiente_folio'
do $$
declare
  v_a uuid := '11111111-1111-1111-1111-111111111111';
  v_b uuid := 'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4';
  v_folio text;
  v_aceptado boolean := false;
begin
  perform set_config('app.empresa_id', v_a::text, true);

  v_folio := nucleo.siguiente_folio(v_a, 'rls_test', '2026');
  raise notice 'OK 0020-1K siguiente_folio propio: %', v_folio;

  begin
    perform nucleo.siguiente_folio(v_b, 'rls_test', '2026');
    v_aceptado := true;
  exception
    when insufficient_privilege then
      raise notice 'OK 0020-1K siguiente_folio ajeno: rechazado por WITH CHECK';
  end;
  if v_aceptado then
    raise exception 'FALLO 0020-1K: siguiente_folio con empresa B funcionó con contexto A';
  end if;
end $$;

rollback;

-- ---------------------------------------------------------------------------
-- L) El contexto NO sobrevive al COMMIT (caso pool / conexión reutilizada)
-- ---------------------------------------------------------------------------
\echo '0020-1: el contexto no sobrevive al COMMIT'
begin;
select set_config('app.empresa_id', '11111111-1111-1111-1111-111111111111', true)
       is not null as contexto_fijado;
commit;

do $$
declare
  v_n bigint;
begin
  select count(*) into v_n from nucleo.viajes;
  if v_n <> 0 then
    raise exception 'FALLO 0020-1L: tras COMMIT se ven % viajes (el GUC sobrevivió a la transacción)', v_n;
  end if;
  raise notice 'OK 0020-1L tras COMMIT: 0 filas — una conexión del pool no hereda la empresa anterior';
end $$;

\echo '0020_01_aislamiento: OK'
