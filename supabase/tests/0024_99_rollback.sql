-- ============================================================================
-- Rollback de 0024 — retira el mantenimiento del núcleo
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0024_mantenimiento_nucleo.sql:
--   drop view     nucleo.v_mantenimiento_estado
--   drop table    nucleo.mantenimientos
--   drop table    nucleo.pautas_mantenimiento
--   drop function nucleo.fn_mantenimiento_validar()
--   drop function nucleo.fn_mantenimiento_no_borrar()
--   drop function nucleo.fn_mantenimiento_odometro()
-- Con las tablas caen PK, UNIQUE compuesta, FKs (incl. compuestas a tractos y
-- ramplas), CHECKs, índices, los 9 triggers, las 2 políticas, RLS ENABLE/FORCE
-- y los GRANTs. La vista se retira antes que sus tablas base.
--
-- NO toca:
--   · `nucleo.tractos` ni `nucleo.ramplas` (el `km_actual` que el trigger subió
--     NO se revierte: es un hecho del odómetro, no un estado de la migración),
--   · el legacy `public.pautas_mantenimiento` / `public.mantenimientos`,
--   · las tablas de 0025/0026,
--   · `nucleo.auditoria` (append-only).
--
-- PÉRDIDA PREVISTA: las pautas y los registros de mantención creados desde la
-- aplicación. El script imprime el conteo antes de borrar. Si hay filas reales,
-- exporte primero y exija autorización: es el único control de mantenimiento
-- preventivo de la flota.
--
-- Es idempotente: si no existen, avisa y termina sin error.
-- Requiere un rol dueño del esquema (supabase_admin/postgres en local).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
--     -v ON_ERROR_STOP=1 < supabase/tests/0024_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_pautas bigint := 0;
  v_mants  bigint := 0;
  v_n      integer;
begin
  if to_regclass('nucleo.pautas_mantenimiento') is null
     and to_regclass('nucleo.mantenimientos') is null then
    raise notice '0024-99: las tablas de mantenimiento no existen; nada que revertir';
  else
    if to_regclass('nucleo.pautas_mantenimiento') is not null then
      execute 'select count(*) from nucleo.pautas_mantenimiento' into v_pautas;
    end if;
    if to_regclass('nucleo.mantenimientos') is not null then
      execute 'select count(*) from nucleo.mantenimientos' into v_mants;
    end if;
    select count(*) into v_n
      from pg_policies
     where schemaname = 'nucleo'
       and tablename in ('pautas_mantenimiento','mantenimientos');
    raise notice '0024-99: antes de borrar: % pautas, % mantenimientos, % políticas',
      v_pautas, v_mants, v_n;

    if to_regclass('nucleo.v_mantenimiento_estado') is not null then
      execute 'drop view nucleo.v_mantenimiento_estado';
    end if;
    if to_regclass('nucleo.mantenimientos') is not null then
      execute 'drop table nucleo.mantenimientos';
    end if;
    if to_regclass('nucleo.pautas_mantenimiento') is not null then
      execute 'drop table nucleo.pautas_mantenimiento';
    end if;
  end if;

  if to_regclass('nucleo.pautas_mantenimiento') is not null
     or to_regclass('nucleo.mantenimientos') is not null
     or to_regclass('nucleo.v_mantenimiento_estado') is not null then
    raise exception '0024-99 FALLO: siguen objetos de mantenimiento';
  end if;

  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'fn_mantenimiento_validar') then
    execute 'drop function nucleo.fn_mantenimiento_validar()';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'fn_mantenimiento_no_borrar') then
    execute 'drop function nucleo.fn_mantenimiento_no_borrar()';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'fn_mantenimiento_odometro') then
    execute 'drop function nucleo.fn_mantenimiento_odometro()';
  end if;

  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('fn_mantenimiento_validar','fn_mantenimiento_no_borrar',
                       'fn_mantenimiento_odometro');
  if v_n <> 0 then
    raise exception '0024-99 FALLO: quedan % funciones de 0024', v_n;
  end if;

  if to_regclass('public.mantenimientos') is null then
    raise exception '0024-99 FALLO: se perdió public.mantenimientos (no debía tocarse)';
  end if;

  raise notice '0024-99: OK; esquema como antes de 0024, legacy intacto';
end
$$;

commit;
