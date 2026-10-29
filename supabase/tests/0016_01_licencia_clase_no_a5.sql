-- ============================================================================
-- Prueba 0016-1 — clase de licencia distinta de A5: BLOQUEO (R-02)
-- ============================================================================
-- Demuestra INV-R02-01:
--   A) chofer con licencia_clase = 'A3' + documentos vigentes => 23514
--      'Licencia A5 requerida'. (Los documentos están OK: el rechazo es por
--      clase, no por fecha; el orden de triggers 03_licencia_a5 -> 05_documentos
--      lo garantiza.)
--   B) chofer con licencia_clase NULL ('sin registrar') => 23514
--   C) UPDATE que asigna un chofer A3 a un borrador existente => 23514
--      (no se puede "colar" la asignación por UPDATE).
--
-- Si se retira trg_viajes_03_licencia_a5, los tres casos pasan: esa es la
-- prueba de mutación (ver mutacion.md).
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -f supabase/tests/0016_01_licencia_clase_no_a5.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

-- A) clase A3
do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_tracto  uuid := '00000015-0000-4000-8000-000000000003';
  v_rampla  uuid := '00000015-0000-4000-8000-000000000005';
  v_chofer  uuid := '00000015-0000-4000-8000-000000000009';  -- clase A3
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
      now() + interval '25 days',
      now() + interval '25 days 5 hours',
      60, 20000,
      'Santiago', 'San Antonio', 70000
    );
    raise exception 'FALLO 0016-1A: se aceptó un viaje con chofer clase A3';
  exception
    when sqlstate '23514' then
      if position('Licencia A5 requerida' in sqlerrm) = 0 then
        raise exception 'FALLO 0016-1A: rechazado por otro motivo: %', sqlerrm;
      end if;
      raise notice 'OK 0016-1A: clase A3 rechazada con 23514 -> %', sqlerrm;
  end;
end;
$$;

-- B) clase ausente (NULL)
do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_tracto  uuid := '00000015-0000-4000-8000-000000000003';
  v_rampla  uuid := '00000015-0000-4000-8000-000000000005';
  v_chofer  uuid := '00000015-0000-4000-8000-00000000000a';  -- clase NULL
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
      now() + interval '26 days',
      now() + interval '26 days 5 hours',
      60, 20000,
      'Santiago', 'Quillota', 60000
    );
    raise exception 'FALLO 0016-1B: se aceptó un viaje con chofer SIN clase de licencia';
  exception
    when sqlstate '23514' then
      if position('sin registrar' in sqlerrm) = 0 then
        raise exception 'FALLO 0016-1B: rechazado por otro motivo: %', sqlerrm;
      end if;
      raise notice 'OK 0016-1B: clase ausente rechazada con 23514 -> %', sqlerrm;
  end;
end;
$$;

-- C) UPDATE que asigna un chofer A3 a un borrador
do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_chofer  uuid := '00000015-0000-4000-8000-000000000009';  -- clase A3
  v_tarifa  uuid := '00000015-0000-4000-8000-00000000000b';
  v_viaje   uuid := gen_random_uuid();
begin
  insert into nucleo.viajes (
    id, empresa_id, cliente_id, tarifa_id,
    estado, inicio_planificado, fin_planificado, buffer_minutos, peso_bruto_kg,
    origen_nombre, destino_nombre, valor_flete_neto
  ) values (
    v_viaje, v_empresa, v_cliente, v_tarifa,
    'borrador',
    now() + interval '50 days',
    now() + interval '50 days 4 hours',
    0, 18000,
    'Santiago', 'Melipilla', 45000
  );

  begin
    update nucleo.viajes set chofer_id = v_chofer where id = v_viaje;
    raise exception 'FALLO 0016-1C: un UPDATE pudo asignar un chofer clase A3';
  exception
    when sqlstate '23514' then
      if position('Licencia A5 requerida' in sqlerrm) = 0 then
        raise exception 'FALLO 0016-1C: rechazado por otro motivo: %', sqlerrm;
      end if;
      raise notice 'OK 0016-1C: asignación por UPDATE rechazada con 23514 -> %', sqlerrm;
  end;
end;
$$;

rollback;

\echo '0016_01_licencia_clase_no_a5: OK'
