-- ============================================================================
-- Prueba 0025-1 — nómina del núcleo: total, inmutabilidad, imputación, redondeo
-- ============================================================================
-- Invariantes (docs/datos/invariantes.md §13):
--   INV-LIQ01 total = base + comisión + bonos - descuentos - anticipos (generada)
--   INV-LIQ02 una liquidación emitida no cambia ni se borra
--   INV-LIQ03 un anticipo/ajuste se imputa a lo sumo una vez y al mes declarado
--   INV-LIQ04 anticipos/ajustes no se borran: se anulan con motivo
--   INV-LIQ05 HALF_UP como único criterio de redondeo
--
-- Casos: CN-03 (paridad 530.000), CN-04 (HALF_UP vs HALF_EVEN), CN-05 (anticipo
-- de mes cerrado: la base impide imputarlo al mes equivocado; qué hace el
-- servicio con el huérfano es D-19).
--
-- Todo corre en una transacción con ROLLBACK: 0 filas residuales.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
--     -v ON_ERROR_STOP=1 < supabase/tests/0025_01_liquidaciones.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_tei    constant uuid := '11111111-1111-1111-1111-111111111111';
  v_chofer uuid;
  v_liq    uuid;
  v_liq2   uuid;
  v_liq3   uuid;
  v_ant    uuid;
  v_total  numeric;
  v_n      integer;
  v_ok     boolean;
begin
  select id into v_chofer from nucleo.choferes
   where empresa_id = v_tei order by rut limit 1;
  if v_chofer is null then
    raise exception 'ENTORNO 0025-1: falta un chofer de TEI en la base de prueba';
  end if;

  -- ---- 0. Mecanismo declarado ---------------------------------------------
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('liquidaciones', 'anticipos_chofer', 'ajustes_liquidacion')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 3 then
    raise exception 'FALLO 0025-1A: % de 3 tablas con RLS+FORCE', v_n;
  end if;
  select count(*) into v_n
    from pg_attribute
   where attrelid = 'nucleo.liquidaciones'::regclass
     and attname = 'total_liquido' and attgenerated = 's';
  if v_n <> 1 then
    raise exception 'FALLO 0025-1A: total_liquido no es columna generada';
  end if;
  raise notice 'OK 0025-1A mecanismo: 3 tablas RLS+FORCE, total_liquido generado';

  -- ---- 1. CN-03: paridad del líquido --------------------------------------
  insert into nucleo.liquidaciones
    (empresa_id, chofer_id, mes, sueldo_base, comision, bonos, descuentos, anticipos)
  values (v_tei, v_chofer, '2026-08', 400000, 180000, 50000, 100000, 0)
  returning id, total_liquido into v_liq, v_total;
  if v_total <> 530000 then
    raise exception 'FALLO 0025-1B (CN-03): total = % (esperado 530000)', v_total;
  end if;
  raise notice 'OK 0025-1B (CN-03): 400.000 + 180.000 + 50.000 - 100.000 = %', v_total;

  -- El total no se escribe desde la aplicación.
  begin
    insert into nucleo.liquidaciones
      (empresa_id, chofer_id, mes, sueldo_base, total_liquido)
    values (v_tei, v_chofer, '2026-07', 100000, 999999);
    raise exception 'FALLO 0025-1B: se pudo escribir total_liquido';
  exception
    when sqlstate '428C9' then
      raise notice 'OK 0025-1B total_liquido es `generated always` => 428C9';
  end;

  -- ---- 2. INV-LIQ05: HALF_UP ----------------------------------------------
  if nucleo.redondear_half_up(125001.125) <> 125001.13 then
    raise exception 'FALLO 0025-1C (CN-04): redondear_half_up(125001.125) = %',
      nucleo.redondear_half_up(125001.125);
  end if;
  -- Control: `round(numeric,int)` de PostgreSQL aleja del cero en el empate
  -- (HALF_UP para positivos). Por eso el helper es una sola envoltura: el
  -- backend NO debe usar `quantize` (HALF_EVEN, CN-04 => 125001.12).
  if round(125001.125::numeric, 2) <> 125001.13 then
    raise exception 'FALLO 0025-1C: round(numeric) dejó de ser half-away-from-zero';
  end if;
  if nucleo.redondear_half_up(0.005) <> 0.01 then
    raise exception 'FALLO 0025-1C: 0.005 => % (esperado 0.01)',
      nucleo.redondear_half_up(0.005);
  end if;
  raise notice 'OK 0025-1C (CN-04): HALF_UP 125001.125 => 125001.13 (HALF_EVEN/quantize habría dado 125001.12)';

  -- ---- 3. INV-LIQ02: emitida inmutable ------------------------------------
  update nucleo.liquidaciones set estado = 'emitida' where id = v_liq;
  select emitida_en is not null and emitida_por is not null into v_ok
    from nucleo.liquidaciones where id = v_liq;
  if not v_ok then
    raise exception 'FALLO 0025-1D: emitir no selló emitida_en/emitida_por';
  end if;

  begin
    update nucleo.liquidaciones set comision = 190000 where id = v_liq;
    raise exception 'FALLO 0025-1D: se recalculó una liquidación emitida';
  exception when check_violation then
    raise notice 'OK 0025-1D emitida: cambio de comisión => 23514';
  end;

  begin
    update nucleo.liquidaciones set estado = 'borrador' where id = v_liq;
    raise exception 'FALLO 0025-1D: una emitida volvió a borrador';
  exception when check_violation then
    raise notice 'OK 0025-1D emitida -> borrador => 23514';
  end;

  begin
    delete from nucleo.liquidaciones where id = v_liq;
    raise exception 'FALLO 0025-1D: se borró una liquidación emitida';
  exception when check_violation then
    raise notice 'OK 0025-1D DELETE de liquidación => 23514';
  end;

  -- ---- 4. INV-LIQ03: anticipo imputado una sola vez ------------------------
  insert into nucleo.anticipos_chofer
    (empresa_id, chofer_id, fecha, monto, mes_imputacion)
  values (v_tei, v_chofer, current_date, 150000, '2026-09')
  returning id into v_ant;

  -- Imputar a una liquidación **borrador** del mismo mes es el flujo normal.
  insert into nucleo.liquidaciones
    (empresa_id, chofer_id, mes, sueldo_base, comision, bonos, descuentos, anticipos)
  values (v_tei, v_chofer, '2026-09', 400000, 100000, 0, 0, 0)
  returning id into v_liq2;

  update nucleo.anticipos_chofer
     set liquidacion_id = v_liq2, estado = 'descontado'
   where id = v_ant;
  raise notice 'OK 0025-1E positivo: anticipo imputado a la liquidación del mismo mes';

  -- Reimputar a otra liquidación: prohibido.
  insert into nucleo.liquidaciones
    (empresa_id, chofer_id, mes, sueldo_base, comision, bonos, descuentos, anticipos)
  values (v_tei, v_chofer, '2026-10', 400000, 0, 0, 0, 0)
  returning id into v_liq3;
  begin
    update nucleo.anticipos_chofer set liquidacion_id = v_liq3 where id = v_ant;
    raise exception 'FALLO 0025-1E: se reimputó un anticipo';
  exception when check_violation then
    raise notice 'OK 0025-1E reimputar un anticipo => 23514';
  end;

  -- Limpiar la imputación también: prohibido.
  begin
    update nucleo.anticipos_chofer set liquidacion_id = null, estado = 'pendiente'
     where id = v_ant;
    raise exception 'FALLO 0025-1E: se limpió la imputación de un anticipo';
  exception when check_violation then
    raise notice 'OK 0025-1E limpiar la imputación => 23514';
  end;

  -- Mes distinto al declarado (CN-05): la base no deja imputarlo al mes erróneo.
  begin
    insert into nucleo.anticipos_chofer
      (empresa_id, chofer_id, monto, mes_imputacion, estado, liquidacion_id)
    values (v_tei, v_chofer, 50000, '2026-07', 'descontado', v_liq3);
    raise exception 'FALLO 0025-1E: se imputó un anticipo a un mes distinto del declarado';
  exception when check_violation then
    raise notice 'OK 0025-1E (CN-05) mes de imputación incoherente => 23514';
  end;

  -- ---- 5. INV-LIQ04: anticipos no se borran / anular exige motivo ----------
  begin
    delete from nucleo.anticipos_chofer where id = v_ant;
    raise exception 'FALLO 0025-1F: se borró un anticipo';
  exception when check_violation then
    raise notice 'OK 0025-1F DELETE de anticipo => 23514';
  end;
  begin
    update nucleo.anticipos_chofer set estado = 'anulado' where id = v_ant;
    raise exception 'FALLO 0025-1F: se anuló un anticipo sin motivo';
  exception when check_violation then
    raise notice 'OK 0025-1F anular anticipo sin motivo => 23514';
  end;

  -- ---- 6. Ajustes ---------------------------------------------------------
  insert into nucleo.ajustes_liquidacion
    (empresa_id, chofer_id, mes, tipo, concepto, monto)
  values (v_tei, v_chofer, '2026-09', 'bono', 'Bono de prueba', 25000);
  begin
    delete from nucleo.ajustes_liquidacion
     where empresa_id = v_tei and concepto = 'Bono de prueba';
    raise exception 'FALLO 0025-1G: se borró un ajuste';
  exception when check_violation then
    raise notice 'OK 0025-1G DELETE de ajuste => 23514';
  end;
  update nucleo.ajustes_liquidacion
     set estado = 'anulado', motivo_anulacion = 'duplicado'
   where empresa_id = v_tei and concepto = 'Bono de prueba';
  if (select estado from nucleo.ajustes_liquidacion
       where empresa_id = v_tei and concepto = 'Bono de prueba') <> 'anulado' then
    raise exception 'FALLO 0025-1G: el ajuste no quedó anulado';
  end if;
  raise notice 'OK 0025-1G ajuste anulado con motivo (no borrado)';

  -- ---- 7. Unicidad y tenant ------------------------------------------------
  begin
    insert into nucleo.liquidaciones (empresa_id, chofer_id, mes)
    values (v_tei, v_chofer, '2026-08');
    raise exception 'FALLO 0025-1H: dos liquidaciones del mismo chofer y mes';
  exception when unique_violation then
    raise notice 'OK 0025-1H (empresa, chofer, mes) duplicado => 23505';
  end;

  begin
    insert into nucleo.liquidaciones (empresa_id, chofer_id, mes)
    values ('22222222-2222-2222-2222-222222222222', v_chofer, '2026-11');
    raise exception 'FALLO 0025-1H: se cruzó un chofer de otra empresa';
  exception when foreign_key_violation then
    raise notice 'OK 0025-1H chofer de otra empresa => 23503';
  end;

  -- ---- 8. Anular la emitida, con motivo ------------------------------------
  update nucleo.liquidaciones
     set estado = 'anulada', motivo_anulacion = 'error de cálculo'
   where id = v_liq;
  select anulada_en is not null and anulada_por is not null into v_ok
    from nucleo.liquidaciones where id = v_liq;
  if not v_ok then
    raise exception 'FALLO 0025-1I: anular no selló anulada_en/por';
  end if;
  raise notice 'OK 0025-1I emitida -> anulada con motivo y sello';
end
$$;

rollback;

\echo '0025-1: OK (rollback; 0 filas residuales)'
