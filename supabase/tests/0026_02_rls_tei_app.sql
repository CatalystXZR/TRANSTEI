-- ============================================================================
-- Prueba 0026-2 — RLS de la Ola B con el ROL REAL de la aplicación (`tei_app`)
-- ============================================================================
-- Cubre las 3 migraciones de la Ola B:
--   0024: nucleo.pautas_mantenimiento, nucleo.mantenimientos, v_mantenimiento_estado
--   0025: nucleo.liquidaciones, nucleo.anticipos_chofer, nucleo.ajustes_liquidacion
--   0026: nucleo.configuracion_empresa, nucleo.config_vigente()
--
--   A) Sin contexto (`app.empresa_id` vacío): SELECT 0 filas en las 6 tablas e
--      INSERT rechazado con 42501 (WITH CHECK).
--   B) Con contexto TEI: se ven las filas de TEI; ninguna de TES; INSERT con
--      `empresa_id` de TES => 42501; `config_vigente` de otra empresa => NULL.
--   C) Con contexto TES: no se ven las filas de TEI.
--   D) `tei_app` sin DELETE (privilegio revocado, no RLS) => 42501.
--   E) Mecanismo: RLS+FORCE en las 6 tablas y 6 políticas con ctx_empresa.
--
-- POR QUÉ ES DISTINTA DE 0024_01/0025_01/0026_01: esas corren como
-- `supabase_admin` (BYPASSRLS) y prueban constraints/triggers, no aislamiento.
-- AGENTS.md §8: RLS sin el rol real no es aislamiento.
--
-- TODO termina en ROLLBACK: 0 filas residuales.
--
-- Uso (sin psql en el host, se usa el del contenedor):
--   docker exec -e PGPASSWORD=tei_app -i supabase_db_TRANSTEI \
--     psql -h 127.0.0.1 -U tei_app -d postgres -v ON_ERROR_STOP=1 \
--     < supabase/tests/0026_02_rls_tei_app.sql
-- ============================================================================

\set ON_ERROR_STOP on

\echo '0026-2: rol efectivo (exige tei_app sin BYPASSRLS)'
do $$
declare
  v_by boolean;
begin
  select rolbypassrls into v_by from pg_roles where rolname = current_user;
  if current_user <> 'tei_app' or coalesce(v_by, true) then
    raise exception 'FALLO 0026-2 rol: se exige tei_app sin BYPASSRLS; current_user=% bypass=%',
      current_user, v_by;
  end if;
  raise notice 'OK 0026-2 rol: current_user=% bypass=%', current_user, v_by;
end $$;

\echo '0026-2: mecanismo declarado (RLS + FORCE + 6 políticas)'
do $$
declare
  v_n integer;
begin
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('pautas_mantenimiento','mantenimientos','liquidaciones',
                       'anticipos_chofer','ajustes_liquidacion','configuracion_empresa')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 6 then
    raise exception 'FALLO 0026-2E: % de 6 tablas con RLS+FORCE', v_n;
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('pautas_mantenimiento','mantenimientos','liquidaciones',
                       'anticipos_chofer','ajustes_liquidacion','configuracion_empresa')
     and policyname = 'tenant_empresa'
     and coalesce(qual, '') like '%ctx_empresa%'
     and coalesce(with_check, '') like '%ctx_empresa%';
  if v_n <> 6 then
    raise exception 'FALLO 0026-2E: % de 6 políticas tenant_empresa', v_n;
  end if;
  raise notice 'OK 0026-2E mecanismo: 6 tablas RLS+FORCE y 6 políticas';
end $$;

begin;

\echo '0026-2A: sin contexto => 0 filas y escritura rechazada'
do $$
declare
  v_tei constant uuid := '11111111-1111-1111-1111-111111111111';
  v_n   integer;
  v_tot integer := 0;
  v_tab text;
begin
  perform set_config('app.empresa_id', '', true);

  foreach v_tab in array array['pautas_mantenimiento','mantenimientos','liquidaciones',
                               'anticipos_chofer','ajustes_liquidacion','configuracion_empresa'] loop
    execute format('select count(*) from nucleo.%I', v_tab) into v_n;
    if v_n <> 0 then
      raise exception 'FALLO 0026-2A: % filas visibles en % sin contexto', v_n, v_tab;
    end if;
    v_tot := v_tot + 1;
  end loop;

  begin
    insert into nucleo.pautas_mantenimiento (empresa_id, recurso_tipo, item, intervalo_km)
    values (v_tei, 'tracto', 'Sin contexto (0026-2)', 10000);
    raise exception 'FALLO 0026-2A: INSERT sin contexto fue aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0026-2A INSERT sin contexto => 42501';
  end;

  raise notice 'OK 0026-2A sin contexto: % tablas con 0 filas', v_tot;
end $$;

\echo '0026-2B: con contexto TEI => solo TEI; cruzar empresa => 42501'
do $$
declare
  v_tei     constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes     constant uuid := '22222222-2222-2222-2222-222222222222';
  v_tracto  uuid;
  v_chofer  uuid;
  v_pauta   uuid;
  v_liq     uuid;
  v_n       integer;
  v_val     jsonb;
begin
  perform set_config('app.empresa_id', v_tei::text, true);

  select id into v_tracto from nucleo.tractos
   where empresa_id = v_tei order by patente limit 1;
  select id into v_chofer from nucleo.choferes
   where empresa_id = v_tei order by rut limit 1;
  if v_tracto is null or v_chofer is null then
    raise exception 'ENTORNO 0026-2B: faltan tracto/chofer de TEI';
  end if;

  insert into nucleo.pautas_mantenimiento (empresa_id, recurso_tipo, item, intervalo_km)
  values (v_tei, 'tracto', 'Pauta RLS (0026-2)', 20000)
  returning id into v_pauta;

  insert into nucleo.mantenimientos (empresa_id, tracto_id, pauta_id, km, costo)
  values (v_tei, v_tracto, v_pauta, 90000, 1000);

  insert into nucleo.liquidaciones (empresa_id, chofer_id, mes, sueldo_base, comision)
  values (v_tei, v_chofer, '2026-08', 400000, 1000)
  returning id into v_liq;

  insert into nucleo.anticipos_chofer (empresa_id, chofer_id, monto, mes_imputacion)
  values (v_tei, v_chofer, 50000, '2026-08');

  insert into nucleo.ajustes_liquidacion (empresa_id, chofer_id, mes, tipo, concepto, monto)
  values (v_tei, v_chofer, '2026-08', 'bono', 'Bono RLS (0026-2)', 1000);

  insert into nucleo.configuracion_empresa (empresa_id, clave, valor)
  values (v_tei, 'clave_prueba_rls', to_jsonb('ok'::text));

  select count(*) into v_n from nucleo.liquidaciones;
  if v_n <> 1 then
    raise exception 'FALLO 0026-2B: TEI ve % liquidaciones (esperado 1)', v_n;
  end if;
  select count(*) into v_n from nucleo.mantenimientos;
  if v_n <> 1 then
    raise exception 'FALLO 0026-2B: TEI ve % mantenimientos (esperado 1)', v_n;
  end if;

  v_val := nucleo.config_vigente(v_tei, 'iva_porcentaje');
  if v_val is distinct from to_jsonb(19) then
    raise exception 'FALLO 0026-2B: config_vigente(TEI) = % (esperado 19)', v_val;
  end if;
  if nucleo.config_vigente(v_tes, 'iva_porcentaje') is not null then
    raise exception 'FALLO 0026-2B: config_vigente(TES) devolvió datos con contexto TEI';
  end if;
  raise notice 'OK 0026-2B contexto TEI: filas propias visibles; config_vigente(TES) = NULL';

  -- Cruzar la empresa en el INSERT: lo bloquea el WITH CHECK, no el servicio.
  begin
    insert into nucleo.pautas_mantenimiento (empresa_id, recurso_tipo, item, intervalo_km)
    values (v_tes, 'tracto', 'Pauta cruzada (0026-2)', 10000);
    raise exception 'FALLO 0026-2B: INSERT con empresa_id ajeno fue aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0026-2B INSERT con empresa_id de TES => 42501';
  end;

  begin
    insert into nucleo.liquidaciones (empresa_id, chofer_id, mes, sueldo_base)
    values (v_tes, v_chofer, '2026-08', 100000);
    raise exception 'FALLO 0026-2B: INSERT de nómina con empresa_id ajeno fue aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0026-2B INSERT de nómina ajena => 42501';
  end;

  begin
    insert into nucleo.configuracion_empresa (empresa_id, clave, valor)
    values (v_tes, 'clave_prueba_rls', to_jsonb('mal'::text));
    raise exception 'FALLO 0026-2B: INSERT de config ajena fue aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0026-2B INSERT de config ajena => 42501';
  end;

  -- UPDATE de una fila ajena: 0 filas (ni error ni fuga).
  update nucleo.liquidaciones set sueldo_base = 1 where empresa_id = v_tes;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0026-2B: UPDATE tocó % filas de otra empresa', v_n;
  end if;
  raise notice 'OK 0026-2B UPDATE de otra empresa: 0 filas';
end $$;

\echo '0026-2C: con contexto TES => no ve TEI'
do $$
declare
  v_tei constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes constant uuid := '22222222-2222-2222-2222-222222222222';
  v_n   integer;
begin
  perform set_config('app.empresa_id', v_tes::text, true);
  select count(*) into v_n from nucleo.liquidaciones;
  if v_n <> 0 then
    raise exception 'FALLO 0026-2C: TES ve % liquidaciones de TEI', v_n;
  end if;
  select count(*) into v_n from nucleo.pautas_mantenimiento;
  if v_n <> 0 then
    raise exception 'FALLO 0026-2C: TES ve % pautas de TEI', v_n;
  end if;
  select count(*) into v_n from nucleo.configuracion_empresa;
  if v_n <> 1 then
    raise exception 'FALLO 0026-2C: TES ve % filas de config (esperado 1: su iva)', v_n;
  end if;
  raise notice 'OK 0026-2C contexto TES: 0 filas de TEI; solo su propia config';
end $$;

\echo '0026-2D: tei_app no borra (privilegio revocado)'
do $$
declare
  v_tei constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tab text;
begin
  perform set_config('app.empresa_id', v_tei::text, true);
  foreach v_tab in array array['pautas_mantenimiento','mantenimientos','liquidaciones',
                               'anticipos_chofer','ajustes_liquidacion','configuracion_empresa'] loop
    begin
      execute format('delete from nucleo.%I', v_tab);
      raise exception 'FALLO 0026-2D: tei_app pudo borrar en %', v_tab;
    exception when insufficient_privilege then
      null;
    end;
  end loop;
  raise notice 'OK 0026-2D DELETE en las 6 tablas => 42501 (privilegio revocado)';
end $$;

rollback;

\echo '0026-2: OK (rollback; 0 filas residuales)'
