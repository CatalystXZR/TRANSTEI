-- ============================================================================
-- Prueba 0015-1 — un viaje 'confirmado' con los tres recursos OCUPA el libro
-- ============================================================================
-- Demuestra INV-D04:
--   A) 'confirmado' + tracto + rampla + chofer  => 3 reservas activas con la
--      misma ventana del viaje (antes de 0015: 0 filas).
--   B) el mismo viaje pasa a 'anulado' => 0 reservas activas y 3 inactivas
--      (trazabilidad: se desactiva, no se borra).
--   C) FRONTERA DECLARADA: 'confirmado' con recursos PARCIALES (solo tracto)
--      NO ocupa. Es la decisión 2 de 0015 (asignación completa).
--
-- Todo ocurre en una transacción que termina en ROLLBACK: no deja datos.
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -f supabase/tests/0015_01_confirmado_ocupa.sql
-- Requiere haber corrido antes fixtures_0015_0016.sql.
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_tracto  uuid := '00000015-0000-4000-8000-000000000003';
  v_rampla  uuid := '00000015-0000-4000-8000-000000000005';
  v_chofer  uuid := '00000015-0000-4000-8000-000000000007';
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
    now() + interval '30 days',
    now() + interval '30 days 8 hours',
    60, 20000,
    'Santiago', 'Valparaíso', 100000
  );

  -- A) tres reservas activas, una por tipo de recurso
  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and activa;
  if v_n <> 3 then
    raise exception 'FALLO 0015-1A: se esperaban 3 reservas activas para el viaje confirmado, hay %', v_n;
  end if;

  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and activa and recurso_tipo = 'tracto'
     and tracto_id = v_tracto;
  if v_n <> 1 then
    raise exception 'FALLO 0015-1A: falta la reserva del tracto (n=%)', v_n;
  end if;

  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and activa and recurso_tipo = 'rampla'
     and rampla_id = v_rampla;
  if v_n <> 1 then
    raise exception 'FALLO 0015-1A: falta la reserva de la rampla (n=%)', v_n;
  end if;

  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and activa and recurso_tipo = 'chofer'
     and chofer_id = v_chofer;
  if v_n <> 1 then
    raise exception 'FALLO 0015-1A: falta la reserva del chofer (n=%)', v_n;
  end if;

  -- la ventana de la reserva es exactamente la del viaje (incluye buffer)
  select count(*) into v_n
    from nucleo.reservas_recurso r
    join nucleo.viajes v on v.id = r.viaje_id
   where r.viaje_id = v_viaje and r.activa and r.ventana = v.ventana;
  if v_n <> 3 then
    raise exception 'FALLO 0015-1A: las reservas no comparten la ventana del viaje (n=%)', v_n;
  end if;

  raise notice 'OK 0015-1A: viaje confirmado con 3 recursos => 3 reservas activas, ventana = viaje.ventana';

  -- B) anulación: libera el libro sin borrar historia
  update nucleo.viajes
     set estado = 'anulado',
         motivo_anulacion = 'prueba 0015-1B'
   where id = v_viaje;

  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and activa;
  if v_n <> 0 then
    raise exception 'FALLO 0015-1B: un viaje anulado sigue con % reservas activas', v_n;
  end if;

  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and not activa;
  if v_n <> 3 then
    raise exception 'FALLO 0015-1B: se esperaban 3 reservas históricas desactivadas, hay %', v_n;
  end if;

  raise notice 'OK 0015-1B: anulado => 0 activas y 3 desactivadas (sin borrar)';
end;
$$;

-- C) frontera: recursos parciales no ocupan
do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_tracto  uuid := '00000015-0000-4000-8000-000000000004';
  v_tarifa  uuid := '00000015-0000-4000-8000-00000000000b';
  v_viaje   uuid := gen_random_uuid();
  v_n       integer;
begin
  insert into nucleo.viajes (
    id, empresa_id, cliente_id, tarifa_id, tracto_id, rampla_id, chofer_id,
    estado, inicio_planificado, fin_planificado, buffer_minutos, peso_bruto_kg,
    origen_nombre, destino_nombre, valor_flete_neto
  ) values (
    v_viaje, v_empresa, v_cliente, v_tarifa, v_tracto, null, null,
    'confirmado',
    now() + interval '60 days',
    now() + interval '60 days 4 hours',
    0, 20000,
    'Santiago', 'Rancagua', 50000
  );

  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and activa;
  if v_n <> 0 then
    raise exception 'FALLO 0015-1C: un viaje con recursos parciales no debería ocupar el libro (n=%)', v_n;
  end if;

  raise notice 'OK 0015-1C: recursos parciales NO ocupan (frontera declarada en 0015, decisión 2)';
end;
$$;

rollback;

\echo '0015_01_confirmado_ocupa: OK'
