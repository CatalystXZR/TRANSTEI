-- ============================================================================
-- Prueba 0026-1 — configuración por empresa: vigencia, historial y rango de IVA
-- ============================================================================
-- Invariantes (docs/datos/invariantes.md §13):
--   INV-CFG01 a lo sumo una fila vigente por (empresa, clave)
--   INV-CFG02 las vigencias no se solapan ni retroceden
--   INV-CFG03 el valor de una fila cerrada no se edita; no se borra
--   INV-CFG04 iva_porcentaje numérico en [0, 100]
--
-- Transacción con ROLLBACK: no deja filas ni cierra la vigencia sembrada.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
--     -v ON_ERROR_STOP=1 < supabase/tests/0026_01_configuracion.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_tei    constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes    constant uuid := '22222222-2222-2222-2222-222222222222';
  v_id     uuid;
  v_desde  timestamptz;
  v_hasta  timestamptz;
  v_val    jsonb;
  v_n      integer;
begin
  -- ---- 0. Mecanismo --------------------------------------------------------
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'configuracion_empresa'
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 1 then
    raise exception 'FALLO 0026-1A: configuracion_empresa sin RLS+FORCE';
  end if;
  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.configuracion_empresa'::regclass and contype = 'x';
  if v_n <> 1 then
    raise exception 'FALLO 0026-1A: falta el EXCLUDE de vigencia';
  end if;
  select count(*) into v_n
    from pg_indexes
   where schemaname = 'nucleo' and tablename = 'configuracion_empresa'
     and indexname = 'uq_config_empresa_clave_vigente';
  if v_n <> 1 then
    raise exception 'FALLO 0026-1A: falta el UNIQUE parcial de la fila vigente';
  end if;
  raise notice 'OK 0026-1A mecanismo: RLS+FORCE, EXCLUDE de vigencia, UNIQUE parcial';

  -- ---- 1. Seed de paridad -------------------------------------------------
  v_val := nucleo.config_vigente(v_tei, 'iva_porcentaje');
  if v_val is distinct from to_jsonb(19) then
    raise exception 'FALLO 0026-1B: iva vigente de TEI = % (esperado 19)', v_val;
  end if;
  if nucleo.config_vigente(v_tes, 'iva_porcentaje') is distinct from to_jsonb(19) then
    raise exception 'FALLO 0026-1B: iva vigente de TES no es 19';
  end if;
  raise notice 'OK 0026-1B seed: iva_porcentaje = 19 por empresa (paridad 0001:291)';

  select id, vigente_desde into v_id, v_desde
    from nucleo.configuracion_empresa
   where empresa_id = v_tei and clave = 'iva_porcentaje' and vigente_hasta is null;

  -- ---- 2. INV-CFG01: una sola fila vigente --------------------------------
  begin
    insert into nucleo.configuracion_empresa (empresa_id, clave, valor)
    values (v_tei, 'iva_porcentaje', to_jsonb(21));
    raise exception 'FALLO 0026-1C: dos filas vigentes para la misma clave';
  exception
    when unique_violation or exclusion_violation then
      raise notice 'OK 0026-1C segunda fila vigente => 23505/23P01';
  end;

  -- ---- 3. INV-CFG03: el valor vigente no se edita -------------------------
  begin
    update nucleo.configuracion_empresa set valor = to_jsonb(21) where id = v_id;
    raise exception 'FALLO 0026-1D: se editó el valor de la fila vigente';
  exception when check_violation then
    raise notice 'OK 0026-1D UPDATE del valor vigente => 23514';
  end;

  -- ---- 4. Cambio de valor: cerrar + insertar ------------------------------
  v_hasta := now();
  update nucleo.configuracion_empresa set vigente_hasta = v_hasta where id = v_id;
  insert into nucleo.configuracion_empresa (empresa_id, clave, valor, vigente_desde)
  values (v_tei, 'iva_porcentaje', to_jsonb(21), v_hasta);

  if nucleo.config_vigente(v_tei, 'iva_porcentaje') is distinct from to_jsonb(21) then
    raise exception 'FALLO 0026-1E: config_vigente no devolvió 21 tras el cambio';
  end if;
  raise notice 'OK 0026-1E cambio de valor: cierre + fila nueva; vigente = 21';

  -- ---- 5. INV-CFG03: la fila cerrada es historial inmutable --------------
  begin
    update nucleo.configuracion_empresa set valor = to_jsonb(19) where id = v_id;
    raise exception 'FALLO 0026-1F: se editó el valor de una fila cerrada';
  exception when check_violation then
    raise notice 'OK 0026-1F UPDATE de fila cerrada => 23514';
  end;
  begin
    update nucleo.configuracion_empresa set vigente_hasta = null where id = v_id;
    raise exception 'FALLO 0026-1F: se reabrió una vigencia cerrada';
  exception when check_violation then
    raise notice 'OK 0026-1F reabrir vigencia cerrada => 23514';
  end;
  begin
    delete from nucleo.configuracion_empresa where id = v_id;
    raise exception 'FALLO 0026-1F: se borró una fila del historial';
  exception when check_violation then
    raise notice 'OK 0026-1F DELETE del historial => 23514';
  end;

  -- ---- 6. INV-CFG02: las vigencias no se solapan --------------------------
  begin
    insert into nucleo.configuracion_empresa
      (empresa_id, clave, valor, vigente_desde, vigente_hasta)
    values (v_tei, 'iva_porcentaje', to_jsonb(20),
            v_desde + interval '1 second', v_hasta - interval '1 second');
    raise exception 'FALLO 0026-1G: se aceptó una vigencia solapada';
  exception when exclusion_violation then
    raise notice 'OK 0026-1G vigencia solapada => 23P01';
  end;

  begin
    insert into nucleo.configuracion_empresa
      (empresa_id, clave, valor, vigente_desde, vigente_hasta)
    values (v_tei, 'otra_clave_prueba', to_jsonb(1), now(), now() - interval '1 hour');
    raise exception 'FALLO 0026-1G: se aceptó vigente_hasta <= vigente_desde';
  exception when check_violation then
    raise notice 'OK 0026-1G vigencia que retrocede => 23514';
  end;

  raise notice 'OK 0026-1: vigencia, historial y unicidad verificados (el rango de IVA va aparte)';
end
$$;

-- ---------------------------------------------------------------------------
-- INV-CFG04 aislado: se cierra la vigente para que el CHECK de rango sea el
-- primer obstáculo (si no, la UNIQUE de vigente gana y no se probaría el CHECK).
-- `clock_timestamp()` (no `now()`) para que el cierre sea posterior al inicio.
-- ---------------------------------------------------------------------------
do $$
declare
  v_tei constant uuid := '11111111-1111-1111-1111-111111111111';
  v_ini timestamptz;
begin
  update nucleo.configuracion_empresa
     set vigente_hasta = clock_timestamp()
   where empresa_id = v_tei and clave = 'iva_porcentaje' and vigente_hasta is null;

  begin
    insert into nucleo.configuracion_empresa (empresa_id, clave, valor)
    values (v_tei, 'iva_porcentaje', to_jsonb(101));
    raise exception 'FALLO 0026-1H: el CHECK de rango no rechazó 101';
  exception when check_violation then
    raise notice 'OK 0026-1H aislado: iva = 101 => 23514';
  end;

  begin
    insert into nucleo.configuracion_empresa (empresa_id, clave, valor)
    values (v_tei, 'iva_porcentaje', to_jsonb(-1));
    raise exception 'FALLO 0026-1H: el CHECK de rango no rechazó -1';
  exception when check_violation then
    raise notice 'OK 0026-1H aislado: iva = -1 => 23514';
  end;

  begin
    insert into nucleo.configuracion_empresa (empresa_id, clave, valor)
    values (v_tei, 'iva_porcentaje', '"diecinueve"');
    raise exception 'FALLO 0026-1H: el CHECK de rango no rechazó un texto';
  exception when check_violation then
    raise notice 'OK 0026-1H aislado: iva no numérico => 23514';
  end;

  -- El borde superior es válido y el formato numérico se conserva.
  insert into nucleo.configuracion_empresa (empresa_id, clave, valor, vigente_desde)
  values (v_tei, 'iva_porcentaje', to_jsonb(100), clock_timestamp());
  if nucleo.config_vigente(v_tei, 'iva_porcentaje') is distinct from to_jsonb(100) then
    raise exception 'FALLO 0026-1H: el borde 100 no quedó vigente';
  end if;
  raise notice 'OK 0026-1H borde 100 aceptado y vigente';
end
$$;

rollback;

\echo '0026-1: OK (rollback; vigencia sembrada intacta)'
