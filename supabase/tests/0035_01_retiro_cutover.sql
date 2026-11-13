-- ============================================================================
-- Prueba 0035-1 — `nucleo.cutover_control` fue retirada y `nucleo` queda en 50 tablas
-- ============================================================================
-- Invariante: el último artefacto del cutover legacy ya no existe en la base;
-- el resto del esquema `nucleo` sigue íntegro.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0035_01_retiro_cutover.sql
--   (y contra la base de la app, base `postgres`)
-- ============================================================================

\set ON_ERROR_STOP on

do $$
declare
  v_n int;
begin
  if to_regclass('nucleo.cutover_control') is not null then
    raise exception 'FALLO 0035-1A: nucleo.cutover_control sigue existiendo';
  end if;
  raise notice 'OK 0035-1A: nucleo.cutover_control ya no existe';

  select count(*) into v_n from pg_tables where schemaname = 'nucleo';
  if v_n <> 50 then
    raise exception 'FALLO 0035-1B: nucleo tiene % tablas, se esperaban 50', v_n;
  end if;
  raise notice 'OK 0035-1B: nucleo tiene exactamente 50 tablas';

  if to_regclass('nucleo.viajes') is null then
    raise exception 'FALLO 0035-1C: nucleo.viajes no existe (daño colateral)';
  end if;
  raise notice 'OK 0035-1C: tablas representativas del núcleo intactas';
end
$$;
