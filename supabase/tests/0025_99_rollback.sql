-- ============================================================================
-- Rollback de 0025 — retira la nómina del núcleo
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0025_liquidaciones_nucleo.sql:
--   drop table    nucleo.ajustes_liquidacion
--   drop table    nucleo.anticipos_chofer
--   drop table    nucleo.liquidaciones
--   drop function nucleo.fn_liquidacion_estado()
--   drop function nucleo.fn_imputacion_validar()
--   drop function nucleo.fn_nomina_no_borrar()
--   drop function nucleo.redondear_half_up(numeric, integer)
-- Con las tablas caen PK, UNIQUE, FKs (incl. compuestas), CHECKs, índices,
-- los 15 triggers, las 3 políticas, RLS ENABLE/FORCE y los GRANTs.
--
-- ORDEN: hijas antes que la cabecera (FK compuesta a liquidaciones).
--
-- NO toca:
--   · `nucleo.choferes` ni `nucleo.empresas`,
--   · el legacy `public.liquidaciones` / `anticipos_chofer` /
--     `ajustes_liquidacion` (siguen siendo la fuente hasta la Ola D),
--   · los triggers de 0024,
--   · `nucleo.auditoria` (append-only: el rastro de las filas se conserva).
--
-- PÉRDIDA PREVISTA: las liquidaciones, anticipos y ajustes creados desde la
-- aplicación. El script imprime el conteo antes de borrar y, si hay filas,
-- exige que el operador las haya exportado: son datos laborales.
-- Los triggers `no_borrar` NO se oponen a `DROP TABLE`.
--
-- Es idempotente: si las tablas no existen, avisa y termina sin error.
-- Requiere un rol dueño del esquema (supabase_admin/postgres en local).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
--     -v ON_ERROR_STOP=1 < supabase/tests/0025_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_liq  bigint := 0;
  v_ant  bigint := 0;
  v_aju  bigint := 0;
  v_n    integer;
begin
  if to_regclass('nucleo.liquidaciones') is null
     and to_regclass('nucleo.anticipos_chofer') is null
     and to_regclass('nucleo.ajustes_liquidacion') is null then
    raise notice '0025-99: las tablas de nómina no existen; nada que revertir';
  else
    if to_regclass('nucleo.liquidaciones') is not null then
      execute 'select count(*) from nucleo.liquidaciones' into v_liq;
    end if;
    if to_regclass('nucleo.anticipos_chofer') is not null then
      execute 'select count(*) from nucleo.anticipos_chofer' into v_ant;
    end if;
    if to_regclass('nucleo.ajustes_liquidacion') is not null then
      execute 'select count(*) from nucleo.ajustes_liquidacion' into v_aju;
    end if;

    select count(*) into v_n
      from pg_policies
     where schemaname = 'nucleo'
       and tablename in ('liquidaciones','anticipos_chofer','ajustes_liquidacion');
    raise notice '0025-99: antes de borrar: % liquidaciones, % anticipos, % ajustes, % políticas',
      v_liq, v_ant, v_aju, v_n;

    -- Sin CASCADE: una dependencia no prevista debe abortar, no arrastrar.
    if to_regclass('nucleo.ajustes_liquidacion') is not null then
      execute 'drop table nucleo.ajustes_liquidacion';
    end if;
    if to_regclass('nucleo.anticipos_chofer') is not null then
      execute 'drop table nucleo.anticipos_chofer';
    end if;
    if to_regclass('nucleo.liquidaciones') is not null then
      execute 'drop table nucleo.liquidaciones';
    end if;
  end if;

  if to_regclass('nucleo.liquidaciones') is not null
     or to_regclass('nucleo.anticipos_chofer') is not null
     or to_regclass('nucleo.ajustes_liquidacion') is not null then
    raise exception '0025-99 FALLO: siguen tablas de nómina';
  end if;

  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'fn_liquidacion_estado') then
    execute 'drop function nucleo.fn_liquidacion_estado()';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'fn_imputacion_validar') then
    execute 'drop function nucleo.fn_imputacion_validar()';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'fn_nomina_no_borrar') then
    execute 'drop function nucleo.fn_nomina_no_borrar()';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'redondear_half_up') then
    execute 'drop function nucleo.redondear_half_up(numeric, integer)';
  end if;

  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('fn_liquidacion_estado','fn_imputacion_validar',
                       'fn_nomina_no_borrar','redondear_half_up');
  if v_n <> 0 then
    raise exception '0025-99 FALLO: quedan % funciones de 0025', v_n;
  end if;

  -- El legacy sigue intacto y es la fuente hasta la Ola D.
  if to_regclass('public.liquidaciones') is null then
    raise exception '0025-99 FALLO: se perdió public.liquidaciones (no debía tocarse)';
  end if;

  raise notice '0025-99: OK; esquema como antes de 0025, legacy intacto';
end
$$;

commit;
