-- ============================================================================
-- Prueba 0016-3 — licencia VENCIDA: bloqueo duro (R-02)
-- ============================================================================
-- Demuestra INV-R02-02:
--   chofer A5 con licencia_conducir vencida ayer + viaje que empieza en 2 días
--   => 23514 'Documento licencia_conducir vencido o insuficiente'.
--
-- Doble valor de esta prueba:
--   1. Confirma que la vigencia documental sigue siendo bloqueo (0004:1097-1101)
--      y que 0016 no la convirtió en advertencia.
--   2. Prueba la mitad documental de 0015: el viaje está en 'confirmado' y,
--      antes de 0015, fn_viaje_validar devolvía temprano para ese estado.
--      Si se retira trg_viajes_05_documentos, este caso deja de fallar.
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -f supabase/tests/0016_03_licencia_vencida_bloquea.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_tracto  uuid := '00000015-0000-4000-8000-000000000003';
  v_rampla  uuid := '00000015-0000-4000-8000-000000000005';
  v_chofer  uuid := '00000015-0000-4000-8000-00000000000c';  -- A5, licencia -1 día
  v_tarifa  uuid := '00000015-0000-4000-8000-00000000000b';
  v_dias    integer;
begin
  select d.vence_en - current_date into v_dias
    from nucleo.documentos d
   where d.chofer_id = v_chofer
     and d.tipo = 'licencia_conducir'
     and d.es_vigente;
  if v_dias is null or v_dias >= 0 then
    raise exception 'FALLO 0016-3: la fixture debía tener la licencia vencida (días=%)', v_dias;
  end if;

  begin
    insert into nucleo.viajes (
      id, empresa_id, cliente_id, tarifa_id, tracto_id, rampla_id, chofer_id,
      estado, inicio_planificado, fin_planificado, buffer_minutos, peso_bruto_kg,
      origen_nombre, destino_nombre, valor_flete_neto
    ) values (
      gen_random_uuid(), v_empresa, v_cliente, v_tarifa, v_tracto, v_rampla, v_chofer,
      'confirmado',
      now() + interval '2 days',
      now() + interval '2 days 6 hours',
      60, 20000,
      'Santiago', 'Linares', 65000
    );
    raise exception 'FALLO 0016-3: se aceptó un viaje con licencia VENCIDA';
  exception
    when sqlstate '23514' then
      if position('licencia_conducir' in sqlerrm) = 0
         or position('vencido o insuficiente' in sqlerrm) = 0 then
        raise exception 'FALLO 0016-3: rechazado por otro motivo: %', sqlerrm;
      end if;
      raise notice 'OK 0016-3: licencia vencida bloquea con 23514 -> %', sqlerrm;
  end;
end;
$$;

-- Control: el mismo INSERT sin la licencia vencida (chofer A5 con docs largos)
-- sí pasa. Demuestra que el rechazo anterior es por la fecha, no por otra causa.
do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_tracto  uuid := '00000015-0000-4000-8000-000000000003';
  v_rampla  uuid := '00000015-0000-4000-8000-000000000005';
  v_chofer  uuid := '00000015-0000-4000-8000-000000000007';  -- A5, docs +3650
  v_tarifa  uuid := '00000015-0000-4000-8000-00000000000b';
  v_viaje   uuid := gen_random_uuid();
  v_n       integer;
begin
  insert into nucleo.viajes (
    id, empresa_id, cliente_id, tarifa_id, tracto_id, rampla_id, chofer_id,
    estado, inicio_planificado, fin_planificado, buffer_minutos, peso_bruto_kg,
    origen_nombre, destino_nombre, valor_flete_neto
  ) values (
    v_viaje, v_empresa, v_cliente, v_tarifa, v_tracto, v_rampla, v_chofer,
    'confirmado',
    now() + interval '3 days',
    now() + interval '3 days 6 hours',
    60, 20000,
    'Santiago', 'Linares', 65000
  );

  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and activa;
  if v_n <> 3 then
    raise exception 'FALLO 0016-3 (control): el caso válido debía crear 3 reservas, hay %', v_n;
  end if;

  raise notice 'OK 0016-3 (control): mismo escenario con licencia vigente => aceptado';
end;
$$;

rollback;

\echo '0016_03_licencia_vencida_bloquea: OK'
