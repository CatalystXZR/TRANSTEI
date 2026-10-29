-- ============================================================================
-- TRANSTEI — Migración 0012: Configuración de costos y rentabilidad (P0-09)
-- ============================================================================
-- Parámetros por empresa para tarifa piso, margen objetivo y Freight Score.
-- El cálculo se hace en backend y se explica componente por componente.
-- ============================================================================

create table nucleo.configuracion_costos (
  id                         uuid primary key default gen_random_uuid(),
  empresa_id                 uuid not null unique references nucleo.empresas(id) on delete restrict,
  costo_fijo_mensual         numeric(14,2) not null default 0 check (costo_fijo_mensual >= 0),
  viajes_estimados_mes       integer not null default 60 check (viajes_estimados_mes > 0),
  margen_objetivo            numeric(5,4) not null default 0.25 check (margen_objetivo between 0 and 0.95),
  benchmark_margen_km        numeric(14,2) not null default 1200 check (benchmark_margen_km > 0),
  contribucion_minima        numeric(14,2) not null default 100000 check (contribucion_minima >= 0),
  costo_variable_km_estandar numeric(14,2) not null default 900 check (costo_variable_km_estandar >= 0),
  rendimiento_km_l           numeric(6,3) not null default 2.5 check (rendimiento_km_l > 0),
  precio_diesel              numeric(10,4) not null default 1000 check (precio_diesel >= 0),
  created_at                 timestamptz not null default now(),
  created_by                 text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at                 timestamptz not null default now(),
  updated_by                 text,
  version                    integer not null default 1 check (version >= 1),
  unique (empresa_id, id)
);

create trigger trg_config_costos_touch before update on nucleo.configuracion_costos
  for each row execute function nucleo.fn_touch();
create trigger trg_config_costos_version before update on nucleo.configuracion_costos
  for each row execute function nucleo.fn_version();
create trigger trg_config_costos_audit after insert or update or delete on nucleo.configuracion_costos
  for each row execute function nucleo.fn_auditoria();

alter table nucleo.configuracion_costos enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select, insert, update on nucleo.configuracion_costos to service_role;
  end if;
end;
$$;

comment on table nucleo.configuracion_costos is
  'Parámetros de costo, margen objetivo, tarifa piso y Freight Score por empresa';
