-- ============================================================================
-- Rollback de 0030 — retira reglas por entidad y suscripciones
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0030_tenant_config_agentes.sql:
--   drop trigger  trg_tenant_reglas_* / trg_tenant_suscripciones_* (si existen)
--   drop table    nucleo.tenant_reglas_entidad, nucleo.tenant_suscripciones
--   drop function nucleo.fn_regla_entidad_inmutable()
--   drop type     nucleo.tipo_entidad_regla
-- Con las tablas caen PK, UNIQUE (empresa_id, id), FKs compuestas, CHECKs,
-- EXCLUDE, UNIQUE parciales, índices, triggers, políticas, RLS y GRANTs.
--
-- NO toca:
--   · nucleo.empresas, nucleo.clientes, nucleo.choferes, nucleo.tractos,
--     nucleo.ramplas, nucleo.contactos_whatsapp (solo se les quitan FKs que
--     apuntaban a ellas),
--   · nucleo.configuracion_empresa (0026) ni nucleo.modulos_empresa,
--   · las funciones compartidas fn_touch/fn_version/fn_auditoria (0004),
--   · nucleo.auditoria (append-only por diseño: sus filas NO se borran).
--
-- PÉRDIDA PREVISTA: las reglas y suscripciones escritas. Al aplicar 0030 no hay
-- ninguna; si ya hay datos reales, expórtelos y exija autorización del dueño.
-- El trigger de inmutabilidad no se opone a `DROP TABLE`; el rollback requiere
-- un rol dueño del esquema (supabase_admin/postgres en local).
--
-- Es idempotente: si los objetos no existen, avisa y termina sin error.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0030_99_rollback.sql
--   (mismo comando con -d postgres para la base de la app, solo con autorización)
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_filas bigint := 0;
  v_n     integer;
  v_trg   text;
begin
  -- Triggers primero (idempotente; si la tabla no existe, no hay trigger).
  if to_regclass('nucleo.tenant_reglas_entidad') is not null then
    foreach v_trg in array array[
      'trg_tenant_reglas_inmutable', 'trg_tenant_reglas_touch',
      'trg_tenant_reglas_version', 'trg_tenant_reglas_audit'
    ] loop
      execute format('drop trigger if exists %I on nucleo.tenant_reglas_entidad', v_trg);
    end loop;
  end if;
  if to_regclass('nucleo.tenant_suscripciones') is not null then
    foreach v_trg in array array[
      'trg_tenant_suscripciones_touch', 'trg_tenant_suscripciones_version',
      'trg_tenant_suscripciones_audit'
    ] loop
      execute format('drop trigger if exists %I on nucleo.tenant_suscripciones', v_trg);
    end loop;
  end if;

  -- Tablas (sin CASCADE: una dependencia no prevista aborta).
  if to_regclass('nucleo.tenant_reglas_entidad') is not null then
    execute 'select count(*) from nucleo.tenant_reglas_entidad' into v_filas;
    execute 'drop table nucleo.tenant_reglas_entidad';
    raise notice '0030-99: tenant_reglas_entidad eliminada; % fila(s) perdidas', v_filas;
  else
    raise notice '0030-99: nucleo.tenant_reglas_entidad no existe';
  end if;

  if to_regclass('nucleo.tenant_suscripciones') is not null then
    execute 'select count(*) from nucleo.tenant_suscripciones' into v_filas;
    execute 'drop table nucleo.tenant_suscripciones';
    raise notice '0030-99: tenant_suscripciones eliminada; % fila(s) perdidas', v_filas;
  else
    raise notice '0030-99: nucleo.tenant_suscripciones no existe';
  end if;

  -- Función nueva.
  if exists (
    select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'nucleo' and p.proname = 'fn_regla_entidad_inmutable'
  ) then
    execute 'drop function nucleo.fn_regla_entidad_inmutable()';
  end if;

  -- Enum al final: dependía de la tabla.
  if exists (
    select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
     where n.nspname = 'nucleo' and t.typname = 'tipo_entidad_regla'
  ) then
    execute 'drop type nucleo.tipo_entidad_regla';
  end if;

  -- ---- Verificación: 0 objetos de 0030 -----------------------------------
  if to_regclass('nucleo.tenant_reglas_entidad') is not null
     or to_regclass('nucleo.tenant_suscripciones') is not null then
    raise exception '0030-99 FALLO: quedan tablas de 0030';
  end if;

  if exists (
    select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'nucleo' and p.proname = 'fn_regla_entidad_inmutable'
  ) then
    raise exception '0030-99 FALLO: queda fn_regla_entidad_inmutable()';
  end if;

  if exists (
    select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
     where n.nspname = 'nucleo' and t.typname = 'tipo_entidad_regla'
  ) then
    raise exception '0030-99 FALLO: queda el enum tipo_entidad_regla';
  end if;

  select count(*) into v_n
    from pg_trigger
   where tgname in ('trg_tenant_reglas_inmutable', 'trg_tenant_reglas_touch',
                    'trg_tenant_reglas_version', 'trg_tenant_reglas_audit',
                    'trg_tenant_suscripciones_touch',
                    'trg_tenant_suscripciones_version',
                    'trg_tenant_suscripciones_audit')
     and not tgisinternal;
  if v_n <> 0 then
    raise exception '0030-99 FALLO: quedan % triggers de 0030', v_n;
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('tenant_reglas_entidad', 'tenant_suscripciones');
  if v_n <> 0 then
    raise exception '0030-99 FALLO: quedan % políticas de 0030', v_n;
  end if;

  -- Las tablas que NO se tocan siguen existiendo.
  if to_regclass('nucleo.empresas') is null
     or to_regclass('nucleo.configuracion_empresa') is null
     or to_regclass('nucleo.modulos_empresa') is null then
    raise exception '0030-99 FALLO: se perdió una tabla que no debía tocarse';
  end if;

  raise notice '0030-99: OK; 0 objetos de 0030; empresas/config/modulos intactos';
end
$$;

commit;

\echo '0030-99: OK (rollback aplicado; re-aplicar 0030 para volver al estado anterior)'
