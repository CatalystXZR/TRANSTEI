-- ============================================================================
-- Prueba 0016-2 — licencia A5 que vence en 10 días: NO bloquea (advertencia)
-- ============================================================================
-- Demuestra INV-R02-03 (advertencia de servicio, NO constraint):
--   chofer A5 cuya licencia_conducir vence en 10 días, viaje que termina en
--   2 días  => el viaje se ACEPTA y ocupa el libro (3 reservas).
--
-- Por qué este caso importa: si alguien "endureciera" la ventana de aviso de
-- 14 días convirtiéndola en constraint, este test fallaría. El bloqueo duro de
-- 0004 compara contra el FIN DEL VIAJE (+ dias_margen_documentos), no contra
-- hoy+14 (ver cabecera de 0016, §ADVERTENCIA).
--
-- Depende de la fixture: empresa TST15 con dias_margen_documentos = 0.
-- Si ese valor cambia, el resultado cambia: es intencional y está documentado.
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -f supabase/tests/0016_02_licencia_por_vencer_no_bloquea.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_empresa uuid := '00000015-0000-4000-8000-000000000001';
  v_cliente uuid := '00000015-0000-4000-8000-000000000002';
  v_tracto  uuid := '00000015-0000-4000-8000-000000000003';
  v_rampla  uuid := '00000015-0000-4000-8000-000000000005';
  v_chofer  uuid := '00000015-0000-4000-8000-000000000008';  -- A5, licencia +10 días
  v_tarifa  uuid := '00000015-0000-4000-8000-00000000000b';
  v_viaje   uuid := gen_random_uuid();
  v_dias    integer;
  v_n       integer;
begin
  -- Verificación del escenario: la licencia vence en 10 días (1..14 => aviso).
  select d.vence_en - current_date into v_dias
    from nucleo.documentos d
   where d.chofer_id = v_chofer
     and d.tipo = 'licencia_conducir'
     and d.es_vigente;
  if v_dias is null then
    raise exception 'FALLO 0016-2: la fixture no tiene licencia vigente para el chofer %', v_chofer;
  end if;
  if v_dias <> 10 then
    raise exception 'FALLO 0016-2: se esperaba una licencia a 10 días, está a % días', v_dias;
  end if;

  -- El viaje termina en 2 días: la licencia sigue vigente durante todo el viaje.
  insert into nucleo.viajes (
    id, empresa_id, cliente_id, tarifa_id, tracto_id, rampla_id, chofer_id,
    estado, inicio_planificado, fin_planificado, buffer_minutos, peso_bruto_kg,
    origen_nombre, destino_nombre, valor_flete_neto
  ) values (
    v_viaje, v_empresa, v_cliente, v_tarifa, v_tracto, v_rampla, v_chofer,
    'confirmado',
    now() + interval '2 days',
    now() + interval '2 days 6 hours',
    60, 20000,
    'Santiago', 'Curicó', 75000
  );

  select count(*) into v_n
    from nucleo.reservas_recurso
   where viaje_id = v_viaje and activa;
  if v_n <> 3 then
    raise exception 'FALLO 0016-2: el viaje debía ocupar 3 reservas, hay %', v_n;
  end if;

  raise notice 'OK 0016-2: licencia A5 a 10 días NO bloquea (aviso de servicio) y el viaje ocupa 3 reservas';
end;
$$;

rollback;

\echo '0016_02_licencia_por_vencer_no_bloquea: OK'
