-- ============================================================================
-- Prueba 0030-3 — RLS de 0030 con el ROL REAL de la aplicación (`tei_app`)
-- ============================================================================
-- Se ejecuta como `supabase_admin` y cambia a `tei_app` con `SET LOCAL ROLE`
-- dentro de la transacción. Comprueba:
--   A) rol efectivo: tei_app, NOBYPASSRLS.
--   B) sin contexto (`app.empresa_id` vacío): 0 filas y escritura => 42501.
--   C) con contexto TEI: ve solo TEI; INSERT propio OK; insertar con
--      `empresa_id` ajeno => 42501; UPDATE de otra empresa => 0 filas;
--      DELETE => 42501 (privilegio revocado, no RLS).
--   D) con contexto TES: no ve TEI.
--
-- Todo termina en ROLLBACK: 0 filas residuales.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0030_03_rls_tei_app.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_tei     constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes     constant uuid := '22222222-2222-2222-2222-222222222222';
  v_cli_tei uuid;
  v_cli_tes uuid;
  v_rl_tei  uuid;
  v_rl_tes  uuid;
  v_s_tei   uuid;
  v_s_tes   uuid;
  v_n       integer;
  v_by      boolean;
begin
  -- ---- 0. Fixtures como rol de plataforma (BYPASSRLS) ---------------------
  select id into v_cli_tei from nucleo.clientes where empresa_id = v_tei order by id limit 1;
  select id into v_cli_tes from nucleo.clientes where empresa_id = v_tes order by id limit 1;
  if v_cli_tei is null or v_cli_tes is null then
    raise exception 'ENTORNO 0030-3: faltan clientes de TEI/TES en el seed';
  end if;

  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, cliente_id, clave, valor)
  values (v_tei, 'cliente', v_cli_tei, 'regla_base', to_jsonb(1))
  returning id into v_rl_tei;

  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, cliente_id, clave, valor)
  values (v_tes, 'cliente', v_cli_tes, 'regla_base', to_jsonb(1))
  returning id into v_rl_tes;

  insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
  values (v_tei, 'piloto') returning id into v_s_tei;
  insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
  values (v_tes, 'piloto') returning id into v_s_tes;

  -- ---- 1. Cambio al rol real ---------------------------------------------
  set local role tei_app;

  select rolbypassrls into v_by from pg_roles where rolname = current_user;
  if current_user <> 'tei_app' or coalesce(v_by, true) then
    raise exception 'FALLO 0030-3A rol: current_user=% bypass=%', current_user, v_by;
  end if;
  raise notice 'OK 0030-3A rol: current_user=% bypass=% (session_user conserva admin)', current_user, v_by;

  -- ---- 2. Sin contexto: 0 filas y escritura rechazada --------------------
  perform set_config('app.empresa_id', '', true);

  select count(*) into v_n from nucleo.tenant_reglas_entidad;
  if v_n <> 0 then
    raise exception 'FALLO 0030-3B: % reglas visibles sin contexto', v_n;
  end if;
  select count(*) into v_n from nucleo.tenant_suscripciones;
  if v_n <> 0 then
    raise exception 'FALLO 0030-3B: % suscripciones visibles sin contexto', v_n;
  end if;

  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor)
    values (v_tei, 'cliente', v_cli_tei, 'sin_contexto', to_jsonb(1));
    raise exception 'FALLO 0030-3B: INSERT de regla sin contexto aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0030-3B INSERT de regla sin contexto => 42501';
  end;

  begin
    insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
    values (v_tei, 'sin_contexto');
    raise exception 'FALLO 0030-3B: INSERT de suscripción sin contexto aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0030-3B INSERT de suscripción sin contexto => 42501';
  end;

  -- ---- 3. Contexto TEI ----------------------------------------------------
  perform set_config('app.empresa_id', v_tei::text, true);

  select count(*) into v_n from nucleo.tenant_reglas_entidad;
  if v_n <> 1 then
    raise exception 'FALLO 0030-3C: TEI ve % reglas (esperado 1)', v_n;
  end if;
  select count(*) into v_n from nucleo.tenant_suscripciones;
  if v_n <> 1 then
    raise exception 'FALLO 0030-3C: TEI ve % suscripciones (esperado 1)', v_n;
  end if;

  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, cliente_id, clave, valor)
  values (v_tei, 'cliente', v_cli_tei, 'regla_rls', to_jsonb(2));
  insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
  values (v_tei, 'basico');

  select count(*) into v_n from nucleo.tenant_reglas_entidad;
  if v_n <> 2 then
    raise exception 'FALLO 0030-3C: TEI ve % reglas tras insertar (esperado 2)', v_n;
  end if;
  select count(*) into v_n from nucleo.tenant_suscripciones;
  if v_n <> 2 then
    raise exception 'FALLO 0030-3C: TEI ve % suscripciones tras insertar (esperado 2)', v_n;
  end if;
  raise notice 'OK 0030-3C TEI: filas propias visibles y escribibles';

  -- Escribir con empresa_id ajeno: lo bloquea el WITH CHECK, no el servicio.
  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor)
    values (v_tes, 'cliente', v_cli_tes, 'regla_cruzada', to_jsonb(1));
    raise exception 'FALLO 0030-3C: INSERT de regla con empresa_id de TES aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0030-3C INSERT de regla con empresa de TES => 42501';
  end;

  begin
    insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
    values (v_tes, 'cruzada');
    raise exception 'FALLO 0030-3C: INSERT de suscripción de TES aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0030-3C INSERT de suscripción de TES => 42501';
  end;

  -- UPDATE de una fila ajena: 0 filas, ni error ni fuga.
  update nucleo.tenant_reglas_entidad set valor = to_jsonb(9) where empresa_id = v_tes;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0030-3C: UPDATE tocó % reglas de otra empresa', v_n;
  end if;
  update nucleo.tenant_suscripciones set estado = 'cancelada' where empresa_id = v_tes;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0030-3C: UPDATE tocó % suscripciones de otra empresa', v_n;
  end if;
  raise notice 'OK 0030-3C UPDATE de otra empresa: 0 filas';

  -- ---- 4. DELETE denegado por privilegio (no por RLS) --------------------
  begin
    delete from nucleo.tenant_reglas_entidad where id = v_rl_tei;
    raise exception 'FALLO 0030-3D: tei_app pudo borrar una regla';
  exception when insufficient_privilege then
    raise notice 'OK 0030-3D DELETE de regla => 42501';
  end;

  begin
    delete from nucleo.tenant_suscripciones where id = v_s_tei;
    raise exception 'FALLO 0030-3D: tei_app pudo borrar una suscripción';
  exception when insufficient_privilege then
    raise notice 'OK 0030-3D DELETE de suscripción => 42501';
  end;

  -- ---- 5. Contexto TES: no ve TEI ----------------------------------------
  perform set_config('app.empresa_id', v_tes::text, true);

  select count(*) into v_n from nucleo.tenant_reglas_entidad where empresa_id = v_tei;
  if v_n <> 0 then
    raise exception 'FALLO 0030-3E: TES ve % reglas de TEI', v_n;
  end if;
  select count(*) into v_n from nucleo.tenant_suscripciones where empresa_id = v_tei;
  if v_n <> 0 then
    raise exception 'FALLO 0030-3E: TES ve % suscripciones de TEI', v_n;
  end if;
  select count(*) into v_n from nucleo.tenant_reglas_entidad;
  if v_n <> 1 then
    raise exception 'FALLO 0030-3E: TES ve % reglas propias (esperado 1)', v_n;
  end if;
  raise notice 'OK 0030-3E contexto TES: 0 filas de TEI, solo las propias';

  reset role;

  raise notice 'OK 0030-3: aislamiento por empresa verificado con tei_app';
end
$$;

rollback;

\echo '0030-3: OK (rollback; 0 filas residuales)'
