-- ============================================================================
-- TRANSTEI — Migración 0014: control de cutover legacy (P0-13)
-- ============================================================================
-- Mientras el legacy `public` siga existiendo, el cutover puede congelar sus
-- escrituras para que la única fuente de verdad sea el schema `nucleo`.
-- ============================================================================

create table nucleo.cutover_control (
  id                         boolean primary key default true check (id),
  legacy_escritura_congelada boolean not null default false,
  congelada_en               timestamptz,
  congelada_por              text,
  motivo                     text,
  updated_at                 timestamptz not null default now()
);

insert into nucleo.cutover_control (id)
values (true)
on conflict (id) do nothing;

alter table nucleo.cutover_control enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select, insert, update on nucleo.cutover_control to service_role;
  end if;
end;
$$;

comment on table nucleo.cutover_control is
  'Estado del cutover: congela escrituras legacy cuando nucleo es la fuente de verdad';
