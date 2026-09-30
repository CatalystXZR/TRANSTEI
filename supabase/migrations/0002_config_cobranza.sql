-- ============================================================
-- TRANSTEI — Migración 0002: Config cobranza, índice, bucket, control de migraciones
-- ============================================================

-- Control de migraciones aplicadas
create table if not exists _migraciones (
  nombre      text primary key,
  aplicada_en timestamptz not null default now()
);

-- Días de anticipación para semáforo de cobranzas (amarillo)
insert into configuracion (clave, valor) values ('dias_alerta_cobranza', '5')
on conflict (clave) do nothing;

-- Índice para consultar viajes asociados a una factura
create index if not exists idx_factura_viaje_viaje on factura_viaje(viaje_id);

-- Bucket de respaldos (boletas, PDFs) — privado
insert into storage.buckets (id, name, public) values ('respaldos', 'respaldos', false)
on conflict (id) do nothing;
