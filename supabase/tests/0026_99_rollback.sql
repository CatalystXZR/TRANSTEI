-- ============================================================================
-- Rollback de 0026 — retira la configuración por empresa
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0026_configuracion_empresa.sql:
--   drop table    nucleo.configuracion_empresa
--   drop function nucleo.config_vigente(uuid, text)
--   drop function nucleo.fn_config_empresa_inmutable()
--   drop function nucleo.fn_config_empresa_no_borrar()
-- Con la tabla caen PK, UNIQUE (empresa_id, id), UNIQUE parcial de la fila
-- vigente, EXCLUDE de vigencia, FK a empresas, CHECKs, índices, los 5 triggers,
-- la política tenant_empresa, RLS ENABLE/FORCE y los GRANTs.
--
-- NO toca:
--   · `public.configuracion` (el legacy sigue siendo la fuente de `/configuracion`),
--   · las tablas de 0024/0025,
--   · las funciones compartidas fn_touch/fn_version/fn_auditoria (0004),
--   · `nucleo.auditoria` (append-only por diseño: las filas del seed NO se borran).
--
-- PÉRDIDA PREVISTA: la configuración por empresa (el seed `iva_porcentaje = 19`
-- de las empresas existentes) y su historial. El trigger `no_borrar` NO se opone
-- a `DROP TABLE`; el rollback funciona con un rol dueño del esquema.
-- Si ya hay tasas u otros parámetros reales, exporte la tabla antes (el script
-- imprime el conteo) y exija autorización del dueño.
--
-- Es idempotente: si no existe, avisa y termina sin error.
-- Requiere un rol dueño del esquema (supabase_admin/postgres en local).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d postgres \
--     -v ON_ERROR_STOP=1 < supabase/tests/0026_99_rollback.sql
--   (mismo comando con -d tei_test para el clon)
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_filas bigint := 0;
  v_n     integer;
begin
  if to_regclass('nucleo.configuracion_empresa') is null then
    raise notice '0026-99: nucleo.configuracion_empresa no existe; nada que revertir';
  else
    execute 'select count(*) from nucleo.configuracion_empresa' into v_filas;

    select count(*) into v_n
      from pg_policies where schemaname = 'nucleo' and tablename = 'configuracion_empresa';
    if v_n <> 1 then
      raise exception '0026-99: se esperaba 1 política en configuracion_empresa, hay %', v_n;
    end if;

    -- Sin CASCADE: si apareciera una dependencia no prevista, aborta.
    execute 'drop table nucleo.configuracion_empresa';
    raise notice '0026-99: tabla eliminada; % fila(s) de configuración perdidas', v_filas;
  end if;

  if to_regclass('nucleo.configuracion_empresa') is not null then
    raise exception '0026-99 FALLO: sigue nucleo.configuracion_empresa';
  end if;

  -- Las funciones se retiran solo si existen (idempotente).
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'config_vigente') then
    execute 'drop function nucleo.config_vigente(uuid, text)';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'fn_config_empresa_inmutable') then
    execute 'drop function nucleo.fn_config_empresa_inmutable()';
  end if;
  if exists (select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
              where n.nspname = 'nucleo' and p.proname = 'fn_config_empresa_no_borrar') then
    execute 'drop function nucleo.fn_config_empresa_no_borrar()';
  end if;

  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('config_vigente','fn_config_empresa_inmutable','fn_config_empresa_no_borrar');
  if v_n <> 0 then
    raise exception '0026-99 FALLO: quedan % funciones de 0026', v_n;
  end if;

  -- El legacy sigue intacto.
  if to_regclass('public.configuracion') is null then
    raise exception '0026-99 FALLO: se perdió public.configuracion (no debía tocarse)';
  end if;

  raise notice '0026-99: OK; esquema como antes de 0026, legacy intacto';
end
$$;

commit;
