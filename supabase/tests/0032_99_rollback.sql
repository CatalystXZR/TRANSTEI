-- ============================================================================
-- Rollback de 0032 — SIMULACIÓN no destructiva del drop de la tabla
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0032_agente_capacidades.sql:
--   drop table if exists nucleo.agente_capacidades cascade;
-- Con la tabla caen PK, UNIQUE (empresa_id, agente, capacidad), CHECKs, FK,
-- índices, triggers, política, RLS y GRANTs. No hay funciones propias que
-- borrar: se reutilizan fn_touch/fn_version/fn_auditoria (0004).
--
-- DIFERENCIA CON 0031_99: aquí el drop se ejecuta dentro de `begin`/`rollback`
-- para NO destruir la tabla real. Este archivo demuestra que el drop deja
-- `to_regclass` en NULL y que el ROLLBACK restaura la tabla.
--
-- NO toca:
--   · nucleo.empresas (solo pierde la FK que apuntaba a ella),
--   · nucleo.auditoria (append-only: sus filas NO se borran),
--   · las funciones compartidas fn_touch/fn_version/fn_auditoria,
--   · ninguna otra tabla de negocio.
--
-- PÉRDIDA PREVISTA si se ejecutara de verdad: los overrides escritos (ninguno
-- al aplicar la migración). Con datos reales, exporte antes y exija
-- autorización del dueño.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0032_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_filas bigint := 0;
  v_n     integer;
  v_trg   text;
begin
  if to_regclass('nucleo.agente_capacidades') is null then
    raise exception '0032-99: nucleo.agente_capacidades no existe; no hay nada que simular';
  end if;

  select count(*) into v_filas from nucleo.agente_capacidades;

  -- Simulación del rollback documentado.
  drop table if exists nucleo.agente_capacidades cascade;

  -- ---- Verificación: 0 objetos de 0032 -----------------------------------
  if to_regclass('nucleo.agente_capacidades') is not null then
    raise exception '0032-99 FALLO: la tabla sigue existiendo tras el drop';
  end if;

  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'agente_capacidades';
  if v_n <> 0 then
    raise exception '0032-99 FALLO: quedan % objeto(s) con el nombre de la tabla', v_n;
  end if;

  foreach v_trg in array array[
    'trg_agente_capacidades_touch',
    'trg_agente_capacidades_version',
    'trg_agente_capacidades_audit'
  ] loop
    select count(*) into v_n
      from pg_trigger
     where tgname = v_trg and not tgisinternal;
    if v_n <> 0 then
      raise exception '0032-99 FALLO: queda el trigger %', v_trg;
    end if;
  end loop;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo' and tablename = 'agente_capacidades';
  if v_n <> 0 then
    raise exception '0032-99 FALLO: quedan % política(s) de 0032', v_n;
  end if;

  select count(*) into v_n
    from pg_indexes
   where schemaname = 'nucleo'
     and indexname like 'agente_capacidades%';
  if v_n <> 0 then
    raise exception '0032-99 FALLO: quedan % índice(s) de 0032', v_n;
  end if;

  -- Las tablas que NO se tocan siguen existiendo.
  if to_regclass('nucleo.empresas') is null
     or to_regclass('nucleo.auditoria') is null then
    raise exception '0032-99 FALLO: se perdió una tabla que no debía tocarse';
  end if;

  raise notice '0032-99: drop simulado OK; % fila(s) se perderían; empresas/auditoria intactas', v_filas;
end
$$;

rollback;

-- Tras el ROLLBACK la tabla real debe seguir viva.
do $$
begin
  if to_regclass('nucleo.agente_capacidades') is null then
    raise exception '0032-99 FALLO: el ROLLBACK no restauró nucleo.agente_capacidades';
  end if;
  raise notice '0032-99: ROLLBACK restauró nucleo.agente_capacidades (la tabla real sigue viva)';
end
$$;

\echo '0032-99: OK (rollback simulado; tabla real intacta)'
