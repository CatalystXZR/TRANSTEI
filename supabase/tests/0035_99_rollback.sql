-- ============================================================================
-- Rollback de 0035 — SIMULACIÓN no destructiva: recrea la tabla y revierte
-- ============================================================================
-- Demuestra que el rollback documentado (recrear `nucleo.cutover_control` con
-- el DDL de `0014` y las policies de `0020`) es ejecutable sin bloqueos y sin
-- dejar rastro. Todo corre dentro de una transacción que termina en ROLLBACK.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0035_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

do $$
begin
  if to_regclass('nucleo.cutover_control') is not null then
    raise exception '0035-99: nucleo.cutover_control ya existe; el rollback simulado no aplica';
  end if;
end
$$;

begin;

create table nucleo.cutover_control (
  id                         boolean primary key default true check (id),
  legacy_escritura_congelada boolean not null default false,
  congelada_en               timestamptz,
  congelada_por              text,
  motivo                     text,
  updated_at                 timestamptz not null default now()
);

insert into nucleo.cutover_control (id) values (true);
alter table nucleo.cutover_control enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select, insert, update on nucleo.cutover_control to service_role;
  end if;
end;
$$;

revoke all on table nucleo.cutover_control from tei_app;
grant select, update on table nucleo.cutover_control to tei_app;

create policy cutover_lectura on nucleo.cutover_control
  for select to public
  using (true);

create policy cutover_actualizacion on nucleo.cutover_control
  for update to public
  using (true)
  with check (true);

do $$
begin
  if to_regclass('nucleo.cutover_control') is null then
    raise exception '0035-99: la recreación de la tabla falló';
  end if;
  raise notice 'OK 0035-99: tabla recreada con DDL de 0014 + policies de 0020 (simulación)';
end
$$;

rollback;

do $$
begin
  if to_regclass('nucleo.cutover_control') is not null then
    raise exception '0035-99: la simulación dejó rastro; nucleo.cutover_control existe';
  end if;
  raise notice 'OK 0035-99: ROLLBACK sin rastro';
end
$$;
