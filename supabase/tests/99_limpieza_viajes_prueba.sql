-- ============================================================================
-- Limpieza de datos de prueba — viajes y reservas de la empresa TST15
-- ============================================================================
-- SOLO BASE LOCAL DESECHABLE (127.0.0.1:54322). NUNCA en staging/producción.
--
-- Para qué existe
--   La prueba de concurrencia (0015_02_concurrencia_rampla.py) debe COMMITEAR
--   el viaje ganador: si no commitea, la segunda conexión no recibe 23P01.
--   Ese viaje 'confirmado' con los tres recursos queda protegido
--   (fn_viaje_proteccion impide el DELETE y fk_reserva_viaje es ON DELETE
--   RESTRICT). Este script lo retira junto con sus reservas.
--
-- Qué borra (y solo esto)
--   1. reservas de la empresa de prueba 00000015-0000-4000-8000-000000000001
--   2. filas dependientes de SUS viajes: viaje_paradas, viaje_checklist,
--      viaje_eventos, viaje_incidentes, viaje_documentos, pod, viaje_gastos
--   3. los viajes de esa empresa
--
-- Qué NO toca, a propósito
--   * nucleo.auditoria (append-only; es historia, no datos de prueba)
--   * cualquier otra empresa, incluida la del piloto/seed
--   * documentos, maestros, tarifas ni clientes de la fixture (los reutiliza
--     la siguiente corrida; fixtures_0015_0016.sql es idempotente)
--   * facturas: si algún viaje de prueba estuviera facturado, el script
--     ABORTA en vez de borrar documentos financieros.
--
-- Requisitos
--   * GUC de seguridad: nucleo.test_cleanup='si' (sin él, el script aborta).
--   * Rol superusuario (el `postgres` local de Supabase lo es): se necesita
--     `session_replication_role = replica` para saltar los triggers de
--     protección y de auditoría. Sin superusuario, ver §Alternativa.
--
-- Uso
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -c "set nucleo.test_cleanup='si'" \
--        -f supabase/tests/99_limpieza_viajes_prueba.sql
--
--   `-c` y `-f` se ejecutan en la MISMA sesión de psql, en el orden dado, así
--   que el GUC queda activo para el archivo. Alternativa equivalente:
--        PGOPTIONS="-c nucleo.test_cleanup=si" \
--        psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--             -f supabase/tests/99_limpieza_viajes_prueba.sql
--
-- §Alternativa sin superusuario (base local propia, nunca compartida)
--   set local session_replication_role = replica;   -- no disponible
--   alter table nucleo.viajes disable trigger user;
--   alter table nucleo.reservas_recurso disable trigger user;
--   ... deletes ...
--   alter table nucleo.viajes enable trigger user;
--   alter table nucleo.reservas_recurso enable trigger user;
--   Requiere ser dueño de las tablas. Deja la base con los triggers
--   re-habilitados: verifique con
--     select tgname, tgenabled from pg_trigger
--      where tgrelid in ('nucleo.viajes'::regclass,
--                        'nucleo.reservas_recurso'::regclass)
--        and not tgisinternal;
--   (tgenabled = 'O' en todas).
-- ============================================================================

\set ON_ERROR_STOP on

begin;

-- ----------------------------------------------------------------------------
-- 0. Guardas: GUC, empresa de prueba y ausencia de documentos financieros
-- ----------------------------------------------------------------------------
do $$
declare
  v_empresa  uuid := '00000015-0000-4000-8000-000000000001';
  v_codigo   text;
  v_viajes   integer;
  v_reservas integer;
  v_facturas integer;
  v_super    text := current_setting('is_superuser', true);
begin
  if coalesce(current_setting('nucleo.test_cleanup', true), '') <> 'si' then
    raise exception '99_limpieza abortada: defina nucleo.test_cleanup=''si'' para confirmar que esta es una base local desechable'
      using errcode = '23514',
            hint = 'PGOPTIONS="-c nucleo.test_cleanup=si" psql ... -f supabase/tests/99_limpieza_viajes_prueba.sql';
  end if;

  select e.codigo into v_codigo from nucleo.empresas e where e.id = v_empresa;
  if v_codigo is null then
    raise notice '99_limpieza: la empresa % no existe; nada que limpiar', v_empresa;
    return;
  end if;
  if v_codigo <> 'TST15' then
    raise exception '99_limpieza abortada: la empresa % tiene codigo %, se esperaba TST15. No se borra nada.',
      v_empresa, v_codigo
      using errcode = '23514';
  end if;

  select count(*) into v_facturas
    from nucleo.factura_viajes fv
    join nucleo.viajes v on v.id = fv.viaje_id
   where v.empresa_id = v_empresa;
  if v_facturas > 0 then
    raise exception '99_limpieza abortada: % viaje(s) de prueba estan ligados a facturas. No se borran documentos financieros: revise a mano.',
      v_facturas
      using errcode = '23514';
  end if;

  select count(*) into v_viajes   from nucleo.viajes           where empresa_id = v_empresa;
  select count(*) into v_reservas from nucleo.reservas_recurso where empresa_id = v_empresa;

  if coalesce(v_super, 'off') <> 'on' then
    raise exception '99_limpieza abortada: se requiere superusuario para session_replication_role = replica'
      using errcode = '42501',
            hint = 'Use el rol postgres de la base local, o la §Alternativa del encabezado (DISABLE TRIGGER USER).';
  end if;

  raise notice '99_limpieza: antes -> viajes=%, reservas=%', v_viajes, v_reservas;
end;
$$;

-- ----------------------------------------------------------------------------
-- 1. Saltar triggers (protección de viajes, no-borrado de reservas, auditoría)
--    y triggers internos de FK (por eso el orden de borrado importa).
-- ----------------------------------------------------------------------------
set local session_replication_role = replica;

-- ----------------------------------------------------------------------------
-- 2. Dependientes de los viajes de prueba (no hay cascada con replica)
-- ----------------------------------------------------------------------------
delete from nucleo.viaje_paradas
 where viaje_id in (select id from nucleo.viajes
                     where empresa_id = '00000015-0000-4000-8000-000000000001');

delete from nucleo.viaje_checklist
 where viaje_id in (select id from nucleo.viajes
                     where empresa_id = '00000015-0000-4000-8000-000000000001');

delete from nucleo.viaje_eventos
 where viaje_id in (select id from nucleo.viajes
                     where empresa_id = '00000015-0000-4000-8000-000000000001');

delete from nucleo.viaje_incidentes
 where viaje_id in (select id from nucleo.viajes
                     where empresa_id = '00000015-0000-4000-8000-000000000001');

delete from nucleo.viaje_documentos
 where viaje_id in (select id from nucleo.viajes
                     where empresa_id = '00000015-0000-4000-8000-000000000001');

delete from nucleo.pod
 where viaje_id in (select id from nucleo.viajes
                     where empresa_id = '00000015-0000-4000-8000-000000000001');

delete from nucleo.viaje_gastos
 where viaje_id in (select id from nucleo.viajes
                     where empresa_id = '00000015-0000-4000-8000-000000000001');

-- ----------------------------------------------------------------------------
-- 3. Reservas y viajes
-- ----------------------------------------------------------------------------
delete from nucleo.reservas_recurso
 where empresa_id = '00000015-0000-4000-8000-000000000001';

delete from nucleo.viajes
 where empresa_id = '00000015-0000-4000-8000-000000000001';

-- ----------------------------------------------------------------------------
-- 4. Volver al modo normal y verificar
-- ----------------------------------------------------------------------------
set local session_replication_role = origin;

do $$
declare
  v_viajes   integer;
  v_reservas integer;
begin
  select count(*) into v_viajes
    from nucleo.viajes where empresa_id = '00000015-0000-4000-8000-000000000001';
  select count(*) into v_reservas
    from nucleo.reservas_recurso where empresa_id = '00000015-0000-4000-8000-000000000001';

  if v_viajes <> 0 or v_reservas <> 0 then
    raise exception '99_limpieza FALLO: quedan viajes=% reservas=% de la empresa de prueba', v_viajes, v_reservas;
  end if;

  raise notice '99_limpieza: despues -> viajes=0, reservas=0. Maestros de TST15 intactos.';
end;
$$;

commit;

\echo '99_limpieza_viajes_prueba: OK'
