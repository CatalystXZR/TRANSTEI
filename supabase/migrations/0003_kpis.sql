-- ============================================================
-- TRANSTEI — Migración 0003: KPIs configurables
-- ============================================================

create table if not exists kpis (
  id          uuid primary key default gen_random_uuid(),
  nombre      text not null,
  descripcion text,
  ambito      text not null default 'global' check (ambito in ('global', 'viaje')),
  formula     text not null,
  formato     text not null default 'numero' check (formato in ('clp', 'numero', 'porcentaje')),
  periodo     text not null default 'mes',
  reglas_color jsonb not null default '[]'::jsonb,
  uso         text not null default 'dashboard' check (uso in ('dashboard', 'rentabilidad_viaje', 'interno')),
  activo      boolean not null default true,
  orden       integer not null default 0,
  created_by  uuid references usuarios(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists idx_kpis_activo on kpis(activo, uso);

create trigger trg_kpis_updated before update on kpis for each row execute function set_updated_at();

alter table kpis enable row level security;

-- ------------------------------------------------------------
-- Seed: KPIs de ejemplo
-- ------------------------------------------------------------
insert into kpis (nombre, descripcion, ambito, formula, formato, reglas_color, uso, orden) values
(
  'Margen del Mes (%)',
  'Margen bruto del mes como porcentaje de los ingresos.',
  'global',
  'SI(ingresos_mes = 0, 0, margen_bruto / ingresos_mes * 100)',
  'porcentaje',
  '[{"operador":"<","valor":10,"color":"rojo"},{"operador":"<","valor":20,"color":"amarillo"},{"operador":">=","valor":20,"color":"verde"}]'::jsonb,
  'dashboard',
  1
),
(
  'Cuentas por Cobrar',
  'Monto total de facturas pendientes de pago.',
  'global',
  'cuentas_por_cobrar',
  'clp',
  '[{"operador":">=","valor":5000000,"color":"rojo"},{"operador":">=","valor":1000000,"color":"amarillo"}]'::jsonb,
  'dashboard',
  2
),
(
  'Viajes del Mes',
  'Cantidad de viajes finalizados o facturados en el mes.',
  'global',
  'viajes_mes',
  'numero',
  '[]'::jsonb,
  'dashboard',
  3
),
(
  'Rentabilidad por Viaje (%)',
  'Margen del viaje (flete - gastos - comisión chofer) como % del flete.',
  'viaje',
  'SI(flete_viaje = 0, 0, margen_viaje / flete_viaje * 100)',
  'porcentaje',
  '[{"operador":"<","valor":10,"color":"rojo"},{"operador":"<","valor":25,"color":"amarillo"},{"operador":">=","valor":25,"color":"verde"}]'::jsonb,
  'rentabilidad_viaje',
  4
);
