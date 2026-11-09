-- ============================================================================
-- Prueba 0030-2 — suscripciones: estado, plan, vigencia y solape
-- ============================================================================
-- Invariantes (docs/datos/invariantes.md §14):
--   INV-TEN06 no hay dos suscripciones solapadas por (empresa, plan)
--   INV-TEN07 a lo sumo una suscripción abierta por (empresa, plan)
--   INV-TEN08 estado ∈ {activa, suspendida, cancelada}
--   (formatos de plan_codigo y vigencia, Apéndice A.4)
--
-- Lo que esta prueba NO puede probar (y no finge):
--   · precio, moneda, cupos o límites: las columnas no existen por D-25/D-26.
--   · cierre automático de vigencia: no hay historial decidido.
--
-- Corre como `supabase_admin` (BYPASSRLS). El aislamiento por empresa con el
-- rol real está en 0030_03_rls_tei_app.sql. TODO termina en ROLLBACK.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0030_02_suscripciones.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_tei    constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes    constant uuid := '22222222-2222-2222-2222-222222222222';
  v_id     uuid;
  v_id2    uuid;
  v_ini    timestamptz;
  v_cierre timestamptz;
  v_n      integer;
  v_ver    integer;
  v_cols   text;
begin
  -- ---- 0. Mecanismo -------------------------------------------------------
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'tenant_suscripciones'
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 1 then
    raise exception 'FALLO 0030-2A: tenant_suscripciones sin RLS+FORCE';
  end if;

  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.tenant_suscripciones'::regclass and contype = 'x';
  if v_n <> 1 then
    raise exception 'FALLO 0030-2A: falta el EXCLUDE de vigencia (hay %)', v_n;
  end if;

  select count(*) into v_n
    from pg_indexes
   where schemaname = 'nucleo' and tablename = 'tenant_suscripciones'
     and indexname = 'uq_suscripcion_vigente';
  if v_n <> 1 then
    raise exception 'FALLO 0030-2A: falta el UNIQUE parcial uq_suscripcion_vigente';
  end if;

  select count(*) into v_n
    from pg_trigger
   where tgrelid = 'nucleo.tenant_suscripciones'::regclass and not tgisinternal
     and tgname in ('trg_tenant_suscripciones_touch',
                    'trg_tenant_suscripciones_version',
                    'trg_tenant_suscripciones_audit');
  if v_n <> 3 then
    raise exception 'FALLO 0030-2A: % de 3 triggers en tenant_suscripciones', v_n;
  end if;

  -- Prohibiciones de A.4: ni precio/moneda/cupos/limites/habilitado.
  select string_agg(a.attname, ', ' order by a.attname) into v_cols
    from pg_attribute a
   where a.attrelid = 'nucleo.tenant_suscripciones'::regclass
     and a.attnum > 0 and not a.attisdropped
     and a.attname in ('precio', 'moneda', 'cupos', 'limites', 'habilitado');
  if v_cols is not null then
    raise exception 'FALLO 0030-2A: columnas prohibidas en suscripciones: %', v_cols;
  end if;
  raise notice 'OK 0030-2A mecanismo: RLS+FORCE, EXCLUDE, UNIQUE parcial, 3 triggers, sin columnas prohibidas';

  -- ---- 1. Alta válida -----------------------------------------------------
  insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
  values (v_tei, 'piloto')
  returning id, vigente_desde into v_id, v_ini;

  if (select estado from nucleo.tenant_suscripciones where id = v_id) <> 'activa' then
    raise exception 'FALLO 0030-2B: el default de estado no es activa';
  end if;
  raise notice 'OK 0030-2B alta válida: plan piloto, estado activa por defecto';

  -- ---- 2. INV-TEN08: estados permitidos y rechazados ----------------------
  insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo, estado)
  values (v_tei, 'basico', 'suspendida');
  insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo, estado)
  values (v_tei, 'cancelado_ok', 'cancelada');

  begin
    insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo, estado)
    values (v_tei, 'estado_malo', 'vencida');
    raise exception 'FALLO 0030-2C: estado fuera del CHECK aceptado';
  exception when check_violation then
    raise notice 'OK 0030-2C estado vencida => 23514';
  end;

  begin
    update nucleo.tenant_suscripciones set estado = 'prueba' where id = v_id;
    raise exception 'FALLO 0030-2C: UPDATE a estado ilegal aceptado';
  exception when check_violation then
    raise notice 'OK 0030-2C UPDATE a estado ilegal => 23514';
  end;

  -- ---- 3. Formato de plan_codigo -----------------------------------------
  begin
    insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
    values (v_tei, 'Piloto');
    raise exception 'FALLO 0030-2D: plan con mayúsculas aceptado';
  exception when check_violation then
    raise notice 'OK 0030-2D plan con mayúsculas => 23514';
  end;

  begin
    insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
    values (v_tei, 'ab');
    raise exception 'FALLO 0030-2D: plan demasiado corto aceptado';
  exception when check_violation then
    raise notice 'OK 0030-2D plan de 2 caracteres => 23514';
  end;

  begin
    insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
    values (v_tei, '1plan');
    raise exception 'FALLO 0030-2D: plan que empieza con número aceptado';
  exception when check_violation then
    raise notice 'OK 0030-2D plan que empieza con número => 23514';
  end;

  -- ---- 4. Vigencia que retrocede -----------------------------------------
  begin
    insert into nucleo.tenant_suscripciones
      (empresa_id, plan_codigo, vigente_desde, vigente_hasta)
    values (v_tei, 'vigencia_mala', now(), now() - interval '1 hour');
    raise exception 'FALLO 0030-2E: se aceptó vigente_hasta <= vigente_desde';
  exception when check_violation then
    raise notice 'OK 0030-2E vigencia que retrocede => 23514';
  end;

  -- ---- 5. INV-TEN07: dos abiertas del mismo plan -------------------------
  begin
    insert into nucleo.tenant_suscripciones (empresa_id, plan_codigo)
    values (v_tei, 'piloto');
    raise exception 'FALLO 0030-2F: dos suscripciones abiertas del mismo plan';
  exception when unique_violation or exclusion_violation then
    raise notice 'OK 0030-2F segunda abierta del mismo plan => 23505/23P01';
  end;

  -- ---- 6. INV-TEN06: solape histórico (aislado del UNIQUE parcial) -------
  v_cierre := v_ini + interval '30 days';
  update nucleo.tenant_suscripciones set vigente_hasta = v_cierre where id = v_id;

  begin
    insert into nucleo.tenant_suscripciones
      (empresa_id, plan_codigo, vigente_desde, vigente_hasta)
    values (v_tei, 'piloto', v_ini + interval '1 day', v_cierre - interval '1 day');
    raise exception 'FALLO 0030-2G: se aceptó un solape histórico';
  exception when exclusion_violation then
    raise notice 'OK 0030-2G solape histórico => 23P01';
  end;

  -- Borde semiabierto: empezar en el cierre exacto es válido.
  insert into nucleo.tenant_suscripciones
    (empresa_id, plan_codigo, vigente_desde)
  values (v_tei, 'piloto', v_cierre)
  returning id into v_id2;
  raise notice 'OK 0030-2G borde: vigencia en el cierre exacto aceptada';

  -- Otro plan con el mismo período no colisiona.
  insert into nucleo.tenant_suscripciones
    (empresa_id, plan_codigo, vigente_desde, vigente_hasta)
  values (v_tei, 'empresa_plus', v_ini, v_cierre);
  raise notice 'OK 0030-2G plan distinto con el mismo período aceptado';

  -- ---- 7. version: fn_touch/fn_version en UPDATE --------------------------
  update nucleo.tenant_suscripciones
     set referencia_externa = 'EXT-0030'
   where id = v_id2
  returning version into v_ver;
  if v_ver <> 2 then
    raise exception 'FALLO 0030-2H: version esperada 2, quedó %', v_ver;
  end if;
  raise notice 'OK 0030-2H version = 2 tras UPDATE';

  -- ---- 8. Misma empresa + plan cerrado; otra empresa es independiente ----
  insert into nucleo.tenant_suscripciones
    (empresa_id, plan_codigo, vigente_desde, vigente_hasta)
  values (v_tes, 'piloto', v_ini, v_cierre);
  raise notice 'OK 0030-2I la misma vigencia en otra empresa es independiente';

  raise notice 'OK 0030-2: estado, plan, vigencia, solape y unicidad verificados';
end
$$;

rollback;

\echo '0030-2: OK (rollback; 0 filas residuales)'
