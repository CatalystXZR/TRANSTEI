-- ============================================================================
-- Prueba 0015-3 — un viaje 'confirmado' con los tres recursos VALIDA DOCUMENTOS
-- ============================================================================
-- Demuestra INV-DOC04 (la mitad documental del agujero):
--   A) 'confirmado' + 3 recursos + chofer sin expediente documental
--      => 23514 'Documento ... faltante'. Antes de 0015 este INSERT pasaba:
--      fn_viaje_validar devolvía temprano para 'confirmado' (0004:1124-1126).
--   B) FRONTERA: recursos parciales no se validan (decisión 2 de 0015).
--
-- Si se retira trg_viajes_05_documentos, el caso A deja de fallar: esa es la
-- prueba de mutación (ver mutacion.md).
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -f supabase/tests/0015_03_confirmado_valida_documentos.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

-- A) chofer A5 SIN documentos (fixture 00000015-...-000d)
do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_tracto  uuid := '00000015-0000-4000-8000-000000000003';
  v_rampla  uuid := '00000015-0000-4000-8000-000000000005';
  v_chofer  uuid := '00000015-0000-4000-8000-00000000000d';
  v_tarifa  uuid := '00000015-0000-4000-8000-00000000000b';
begin
  begin
    insert into nucleo.viajes (
      id, empresa_id, cliente_id, tarifa_id, tracto_id, rampla_id, chofer_id,
      estado, inicio_planificado, fin_planificado, buffer_minutos, peso_bruto_kg,
      origen_nombre, destino_nombre, valor_flete_neto
    ) values (
      gen_random_uuid(), v_empresa, v_cliente, v_tarifa, v_tracto, v_rampla, v_chofer,
      'confirmado',
      now() + interval '20 days',
      now() + interval '20 days 6 hours',
      60, 20000,
      'Santiago', 'Chillán', 80000
    );
    raise exception 'FALLO 0015-3A: un viaje confirmado con chofer sin documentos fue ACEPTADO';
  exception
    when sqlstate '23514' then
      if position('faltante' in sqlerrm) = 0 then
        raise exception 'FALLO 0015-3A: rechazado por un motivo inesperado: %', sqlerrm;
      end if;
      raise notice 'OK 0015-3A: rechazado con 23514 -> %', sqlerrm;
  end;
end;
$$;

-- B) frontera: con recursos parciales no se valida documentación
do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_chofer  uuid := '00000015-0000-4000-8000-00000000000d';
  v_tarifa  uuid := '00000015-0000-4000-8000-00000000000b';
  v_viaje   uuid := gen_random_uuid();
begin
  insert into nucleo.viajes (
    id, empresa_id, cliente_id, tarifa_id, chofer_id,
    estado, inicio_planificado, fin_planificado, buffer_minutos, peso_bruto_kg,
    origen_nombre, destino_nombre, valor_flete_neto
  ) values (
    v_viaje, v_empresa, v_cliente, v_tarifa, v_chofer,
    'cotizado',
    now() + interval '40 days',
    now() + interval '40 days 3 hours',
    0, 15000,
    'Santiago', 'Talca', 40000
  );

  raise notice 'OK 0015-3B: recursos parciales no disparan validación documental (frontera declarada)';
end;
$$;

rollback;

\echo '0015_03_confirmado_valida_documentos: OK'
