-- ============================================================================
-- Prueba 0024-1 — mantenimiento en el núcleo: positivo, violatorio y bordes
-- ============================================================================
-- Invariantes (docs/datos/invariantes.md §13):
--   INV-MANT01 costo >= 0                     => 23514
--   INV-MANT02 proximo = ultimo + intervalo    => vista / snapshot inmutable
--   INV-MANT03 editar la pauta no reescribe    => snapshot congelado (23514)
--   INV-MANT04 recurso y pauta de la misma empresa y tipo => 23503 / 23514
--   INV-MANT05 una sola definición del semáforo (vista, no columna)
--
-- Datos: usa un tracto y una rampla de la empresa TEI (seed local) DENTRO de una
-- transacción con ROLLBACK: 0 filas residuales. El trigger de odómetro modifica
-- `nucleo.tractos.km_actual`; el ROLLBACK lo revierte.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
--     -v ON_ERROR_STOP=1 < supabase/tests/0024_01_mantenimiento.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_tei   constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes   constant uuid := '22222222-2222-2222-2222-222222222222';
  v_tracto uuid;
  v_rampla uuid;
  v_pauta  uuid;
  v_pauta2 uuid;
  v_km     numeric;
  v_estado text;
  v_prox   numeric;
  v_rest   numeric;
  v_n      integer;
  v_snap   integer;
begin
  -- ---- 0. Entorno: hay un tracto y una rampla de TEI ------------------------
  select id into v_tracto from nucleo.tractos
   where empresa_id = v_tei order by patente limit 1;
  select id into v_rampla from nucleo.ramplas
   where empresa_id = v_tei order by patente limit 1;
  if v_tracto is null or v_rampla is null then
    raise exception 'ENTORNO 0024-1: faltan tracto/rampla de TEI en la base de prueba';
  end if;

  -- ---- 1. Mecanismo declarado ----------------------------------------------
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('pautas_mantenimiento', 'mantenimientos')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 2 then
    raise exception 'FALLO 0024-1A: % de 2 tablas con RLS+FORCE', v_n;
  end if;
  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('pautas_mantenimiento', 'mantenimientos')
     and policyname = 'tenant_empresa';
  if v_n <> 2 then
    raise exception 'FALLO 0024-1A: % de 2 políticas tenant_empresa', v_n;
  end if;
  if to_regclass('nucleo.v_mantenimiento_estado') is null then
    raise exception 'FALLO 0024-1A: falta nucleo.v_mantenimiento_estado';
  end if;
  raise notice 'OK 0024-1A mecanismo: 2 tablas RLS+FORCE, 2 políticas, vista presente';

  -- ---- 2. Positivo: pauta + mantenimiento, snapshot desde la pauta ---------
  insert into nucleo.pautas_mantenimiento
    (empresa_id, recurso_tipo, item, intervalo_km, alerta_km, orden)
  values (v_tei, 'tracto', 'Aceite motor (prueba 0024)', 20000, 5000, 1)
  returning id into v_pauta;

  insert into nucleo.mantenimientos
    (empresa_id, tracto_id, pauta_id, fecha, km, costo, observaciones)
  values (v_tei, v_tracto, v_pauta, current_date, 100000, 150000, 'prueba')
  returning intervalo_km_snapshot into v_snap;
  if v_snap <> 20000 then
    raise exception 'FALLO 0024-1B: snapshot de intervalo = % (esperado 20000)', v_snap;
  end if;
  raise notice 'OK 0024-1B positivo: registro creado con snapshot 20000 km';

  -- El odómetro del tracto sube al km registrado (regla legacy).
  select km_actual into v_km from nucleo.tractos where id = v_tracto;
  if v_km < 100000 then
    raise exception 'FALLO 0024-1B: km_actual = % (esperado >= 100000)', v_km;
  end if;

  -- ---- 3. Bordes del semáforo (CN-08) --------------------------------------
  select estado, proximo_km, restante_km into v_estado, v_prox, v_rest
    from nucleo.v_mantenimiento_estado
   where empresa_id = v_tei and pauta_id = v_pauta and recurso_id = v_tracto;
  if v_prox <> 120000 or v_rest <> 20000 or v_estado <> 'ok' then
    raise exception 'FALLO 0024-1C: proximo=% restante=% estado=% (esperado 120000/20000/ok)',
      v_prox, v_rest, v_estado;
  end if;

  update nucleo.tractos set km_actual = 120000 where id = v_tracto;
  select estado, restante_km into v_estado, v_rest
    from nucleo.v_mantenimiento_estado
   where empresa_id = v_tei and pauta_id = v_pauta and recurso_id = v_tracto;
  if v_estado <> 'pendiente' or v_rest <> 0 then
    raise exception 'FALLO 0024-1C: restante 0 => estado=% (esperado pendiente)', v_estado;
  end if;

  update nucleo.tractos set km_actual = 115000 where id = v_tracto;
  select estado into v_estado from nucleo.v_mantenimiento_estado
   where empresa_id = v_tei and pauta_id = v_pauta and recurso_id = v_tracto;
  if v_estado <> 'por_vencer' then
    raise exception 'FALLO 0024-1C: restante=alerta => estado=% (esperado por_vencer)', v_estado;
  end if;

  update nucleo.tractos set km_actual = 114999 where id = v_tracto;
  select estado into v_estado from nucleo.v_mantenimiento_estado
   where empresa_id = v_tei and pauta_id = v_pauta and recurso_id = v_tracto;
  if v_estado <> 'ok' then
    raise exception 'FALLO 0024-1C: restante=alerta+1 => estado=% (esperado ok)', v_estado;
  end if;
  raise notice 'OK 0024-1C bordes: restante 20000/0/5000/5001 => ok/pendiente/por_vencer/ok';

  -- ---- 4. sin_registro y sin_odometro -------------------------------------
  insert into nucleo.pautas_mantenimiento
    (empresa_id, recurso_tipo, item, intervalo_km, orden)
  values (v_tei, 'tracto', 'Filtro de aire (prueba 0024)', 40000, 2)
  returning id into v_pauta2;
  select estado into v_estado from nucleo.v_mantenimiento_estado
   where empresa_id = v_tei and pauta_id = v_pauta2 and recurso_id = v_tracto;
  if v_estado <> 'sin_registro' then
    raise exception 'FALLO 0024-1D: sin registro => % (esperado sin_registro)', v_estado;
  end if;

  begin
    insert into nucleo.mantenimientos
      (empresa_id, rampla_id, pauta_id, fecha, km, costo)
    values (v_tei, v_rampla, v_pauta, current_date, 50000, 10000);
    raise exception 'FALLO 0024-1D: se aceptó una pauta de tracto con una rampla';
  exception when check_violation then
    raise notice 'OK 0024-1D sin_registro + pauta/recurso incoherente => 23514';
  end;
end
$$;

do $$
declare
  v_tei    constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes    constant uuid := '22222222-2222-2222-2222-222222222222';
  v_tracto uuid;
  v_rampla uuid;
  v_pauta  uuid;
  v_ram    uuid;
begin
  select id into v_tracto from nucleo.tractos where empresa_id = v_tei order by patente limit 1;
  select id into v_rampla from nucleo.ramplas where empresa_id = v_tei order by patente limit 1;
  select id into v_pauta from nucleo.pautas_mantenimiento
   where empresa_id = v_tei and item = 'Aceite motor (prueba 0024)';

  -- ---- 5. Rampla con su propia pauta (positivo) ---------------------------
  insert into nucleo.pautas_mantenimiento
    (empresa_id, recurso_tipo, item, intervalo_km, orden)
  values (v_tei, 'rampla', 'Engrase (prueba 0024)', 5000, 3)
  returning id into v_ram;
  insert into nucleo.mantenimientos (empresa_id, rampla_id, pauta_id, km, costo)
  values (v_tei, v_rampla, v_ram, 50000, 0);
  raise notice 'OK 0024-1E positivo: rampla con pauta de rampla y costo 0';

  -- ---- 6. Violaciones -----------------------------------------------------
  begin
    insert into nucleo.mantenimientos (empresa_id, tracto_id, pauta_id, km, costo)
    values (v_tei, v_tracto, v_pauta, 100000, -1);
    raise exception 'FALLO 0024-1F: se aceptó costo negativo';
  exception when check_violation then
    raise notice 'OK 0024-1F costo < 0 => 23514';
  end;

  begin
    insert into nucleo.mantenimientos (empresa_id, tracto_id, pauta_id, km, costo)
    values (v_tei, v_tracto, v_pauta, -1, 0);
    raise exception 'FALLO 0024-1F: se aceptó km negativo';
  exception when check_violation then
    raise notice 'OK 0024-1F km < 0 => 23514';
  end;

  begin
    insert into nucleo.mantenimientos (empresa_id, tracto_id, rampla_id, pauta_id, km, costo)
    values (v_tei, v_tracto, v_rampla, v_pauta, 100000, 0);
    raise exception 'FALLO 0024-1F: se aceptaron tracto y rampla a la vez';
  exception when check_violation then
    raise notice 'OK 0024-1F tracto+rampla => 23514';
  end;

  -- Otra empresa con un tracto de TEI: la FK compuesta no lo permite.
  begin
    insert into nucleo.pautas_mantenimiento (empresa_id, recurso_tipo, item, intervalo_km)
    values (v_tes, 'tracto', 'Pauta cruzada (prueba 0024)', 10000);
    insert into nucleo.mantenimientos (empresa_id, tracto_id, pauta_id, km, costo)
    values (v_tes,
            v_tracto,
            (select id from nucleo.pautas_mantenimiento
              where empresa_id = v_tes and item = 'Pauta cruzada (prueba 0024)'),
            100000, 0);
    raise exception 'FALLO 0024-1F: se cruzó una empresa con un tracto ajeno';
  exception when foreign_key_violation then
    raise notice 'OK 0024-1F tracto de otra empresa => 23503';
  end;

  -- ---- 7. INV-MANT03: el snapshot no se reescribe --------------------------
  begin
    update nucleo.mantenimientos
       set intervalo_km_snapshot = 30000
     where empresa_id = v_tei and pauta_id = v_pauta and tracto_id = v_tracto;
    raise exception 'FALLO 0024-1G: se reescribió el snapshot del intervalo';
  exception when check_violation then
    raise notice 'OK 0024-1G snapshot inmutable => 23514';
  end;

  -- La pauta editada NO cambia el cálculo del registro ya hecho.
  update nucleo.pautas_mantenimiento set intervalo_km = 25000 where id = v_pauta;
  if (select proximo_km from nucleo.v_mantenimiento_estado
       where empresa_id = v_tei and pauta_id = v_pauta and recurso_id = v_tracto) <> 120000 then
    raise exception 'FALLO 0024-1G: editar la pauta reescribió el histórico (CN-08 borde)';
  end if;
  raise notice 'OK 0024-1G editar la pauta no reescribe el histórico';

  -- ---- 8. Ítem activo duplicado -------------------------------------------
  begin
    insert into nucleo.pautas_mantenimiento
      (empresa_id, recurso_tipo, item, intervalo_km, orden)
    values (v_tei, 'tracto', 'aceite motor (PRUEBA 0024)', 10000, 9);
    raise exception 'FALLO 0024-1H: se aceptó un ítem activo duplicado (case-insensitive)';
  exception when unique_violation then
    raise notice 'OK 0024-1H ítem activo duplicado => 23505';
  end;

  -- ---- 9. No se borra: se anula con motivo --------------------------------
  begin
    delete from nucleo.mantenimientos where empresa_id = v_tei and pauta_id = v_pauta;
    raise exception 'FALLO 0024-1I: se permitió DELETE del histórico';
  exception when check_violation then
    raise notice 'OK 0024-1I DELETE del histórico => 23514';
  end;

  begin
    update nucleo.mantenimientos set estado = 'anulado'
     where empresa_id = v_tei and pauta_id = v_pauta and tracto_id = v_tracto;
    raise exception 'FALLO 0024-1I: se anuló sin motivo';
  exception when check_violation then
    raise notice 'OK 0024-1I anular sin motivo => 23514';
  end;

  update nucleo.mantenimientos
     set estado = 'anulado', motivo_anulacion = 'error de digitación'
   where empresa_id = v_tei and pauta_id = v_pauta and tracto_id = v_tracto;
  if (select count(*) from nucleo.mantenimientos
       where empresa_id = v_tei and pauta_id = v_pauta and tracto_id = v_tracto
         and estado = 'anulado' and anulada_en is not null) <> 1 then
    raise exception 'FALLO 0024-1I: la anulación no dejó el sello anulada_en';
  end if;
  raise notice 'OK 0024-1I anular con motivo deja el registro (no lo borra)';

  -- Un registro anulado no cuenta para el semáforo.
  if (select estado from nucleo.v_mantenimiento_estado
       where empresa_id = v_tei and pauta_id = v_pauta and recurso_id = v_tracto)
     <> 'sin_registro' then
    raise exception 'FALLO 0024-1I: un registro anulado sigue contando en el semáforo';
  end if;
  raise notice 'OK 0024-1I el registro anulado no cuenta en el semáforo';
end
$$;

rollback;

\echo '0024-1: OK (rollback; 0 filas residuales)'
