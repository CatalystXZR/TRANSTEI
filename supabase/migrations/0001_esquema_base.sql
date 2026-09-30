-- ============================================================
-- TRANSTEI — Migración 0001: Esquema base ERP Transportes TEI SpA
-- Fuente de verdad: prompts.md + docs/PLAN_DESARROLLO.md
-- ============================================================

create extension if not exists "pgcrypto";

-- ------------------------------------------------------------
-- Tipos enumerados
-- ------------------------------------------------------------
create type rol_usuario as enum ('admin', 'operacion', 'contabilidad');
create type estado_viaje as enum ('programado', 'en_ruta', 'finalizado', 'facturado');
create type estado_factura as enum ('pendiente', 'pagada', 'anulada');
create type tipo_factura as enum ('afecta', 'exenta');
create type categoria_gasto as enum ('combustible', 'peaje', 'viatico', 'mantenimiento_ruta', 'otros');
create type tipo_rampla as enum ('plana', 'sider');
create type tipo_ajuste as enum ('bono', 'descuento');
create type estado_liquidacion as enum ('borrador', 'emitida');

-- ------------------------------------------------------------
-- Trigger genérico: updated_at
-- ------------------------------------------------------------
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

-- ------------------------------------------------------------
-- Tablas
-- ------------------------------------------------------------

-- Usuarios del sistema (espejo de auth.users con rol de negocio)
create table usuarios (
  id         uuid primary key default gen_random_uuid(),
  auth_id    uuid not null unique references auth.users(id) on delete cascade,
  nombre     text not null,
  email      text,
  rol        rol_usuario not null default 'operacion',
  activo     boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table clientes (
  id          uuid primary key default gen_random_uuid(),
  razon_social text not null,
  rut         text not null unique,
  giro        text,
  dias_pago   integer not null default 30,
  telefono    text,
  email       text,
  activo      boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table choferes (
  id                    uuid primary key default gen_random_uuid(),
  nombre                text not null,
  rut                   text not null unique,
  sueldo_base           numeric(14,2) not null default 0,
  porcentaje_produccion numeric(5,4) not null default 0 check (porcentaje_produccion >= 0 and porcentaje_produccion <= 1),
  vencimiento_licencia  date,
  activo                boolean not null default true,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

create table tractos (
  id                          uuid primary key default gen_random_uuid(),
  patente                     text not null unique,
  marca                       text,
  modelo                      text,
  ano                         integer,
  km_actual                   integer not null default 0,
  vencimiento_revision_tecnica date,
  vencimiento_seguro           date,
  activo                      boolean not null default true,
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);

create table ramplas (
  id                          uuid primary key default gen_random_uuid(),
  patente                     text not null unique,
  tipo                        tipo_rampla not null default 'plana',
  vencimiento_revision_tecnica date,
  activo                      boolean not null default true,
  created_at                  timestamptz not null default now(),
  updated_at                  timestamptz not null default now()
);

-- Núcleo del sistema
create table viajes (
  id               uuid primary key default gen_random_uuid(),
  fecha_inicio     date not null,
  fecha_fin        date,
  origen           text not null,
  destino          text not null,
  estado           estado_viaje not null default 'programado',
  valor_flete_neto numeric(14,2) not null default 0,
  cliente_id       uuid not null references clientes(id),
  chofer_id        uuid not null references choferes(id),
  tracto_id        uuid not null references tractos(id),
  rampla_id        uuid not null references ramplas(id),
  notas            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create table gastos_viaje (
  id               uuid primary key default gen_random_uuid(),
  viaje_id         uuid not null references viajes(id) on delete cascade,
  categoria        categoria_gasto not null,
  monto            numeric(14,2) not null check (monto >= 0),
  iva_recuperable  boolean not null default false,
  respaldo_url     text,
  fecha            date not null default current_date,
  notas            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create table facturas (
  id                 uuid primary key default gen_random_uuid(),
  numero_sii         text not null,
  cliente_id         uuid not null references clientes(id),
  tipo               tipo_factura not null default 'afecta',
  monto_neto         numeric(14,2) not null default 0,
  iva                numeric(14,2) not null default 0,
  total              numeric(14,2) not null default 0,
  fecha_emision      date not null default current_date,
  fecha_vencimiento  date,
  fecha_pago         date,
  estado             estado_factura not null default 'pendiente',
  notas              text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (numero_sii, cliente_id)
);

create table factura_viaje (
  factura_id uuid not null references facturas(id) on delete cascade,
  viaje_id   uuid not null references viajes(id),
  primary key (factura_id, viaje_id)
);

create table anticipos_chofer (
  id              uuid primary key default gen_random_uuid(),
  chofer_id       uuid not null references choferes(id) on delete cascade,
  fecha           date not null default current_date,
  monto           numeric(14,2) not null check (monto > 0),
  mes_liquidacion varchar(7) not null, -- formato YYYY-MM
  notas           text,
  created_at      timestamptz not null default now()
);

create table ajustes_liquidacion (
  id        uuid primary key default gen_random_uuid(),
  chofer_id uuid not null references choferes(id) on delete cascade,
  mes       varchar(7) not null, -- formato YYYY-MM
  tipo      tipo_ajuste not null,
  concepto  text not null,
  monto     numeric(14,2) not null check (monto >= 0),
  created_at timestamptz not null default now()
);

create table liquidaciones (
  id             uuid primary key default gen_random_uuid(),
  chofer_id      uuid not null references choferes(id),
  mes            varchar(7) not null, -- formato YYYY-MM
  sueldo_base    numeric(14,2) not null default 0,
  comision       numeric(14,2) not null default 0,
  total_anticipos numeric(14,2) not null default 0,
  total_ajustes  numeric(14,2) not null default 0,
  total_liquido  numeric(14,2) not null default 0,
  estado         estado_liquidacion not null default 'borrador',
  pdf_url        text,
  notas          text,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (chofer_id, mes)
);

-- Pauta de mantenimiento por flota (intervalos en km)
create table pautas_mantenimiento (
  id           uuid primary key default gen_random_uuid(),
  item         text not null,
  intervalo_km integer not null check (intervalo_km > 0),
  orden        integer not null default 0,
  activo       boolean not null default true,
  created_at   timestamptz not null default now()
);

-- Historial de mantenciones por tracto
create table mantenimientos (
  id           uuid primary key default gen_random_uuid(),
  tracto_id    uuid not null references tractos(id) on delete cascade,
  pauta_id     uuid not null references pautas_mantenimiento(id),
  fecha        date not null default current_date,
  km           integer not null,
  costo        numeric(14,2) not null default 0,
  notas        text,
  respaldo_url text,
  created_at   timestamptz not null default now()
);

-- Configuración global del sistema
create table configuracion (
  clave text primary key,
  valor text not null
);

-- ------------------------------------------------------------
-- Índices
-- ------------------------------------------------------------
create index idx_viajes_estado on viajes(estado);
create index idx_viajes_cliente on viajes(cliente_id);
create index idx_viajes_chofer on viajes(chofer_id);
create index idx_viajes_fechas on viajes(fecha_inicio, fecha_fin);
create index idx_gastos_viaje on gastos_viaje(viaje_id);
create index idx_facturas_estado on facturas(estado);
create index idx_facturas_vencimiento on facturas(fecha_vencimiento);
create index idx_facturas_cliente on facturas(cliente_id);
create index idx_anticipos_chofer_mes on anticipos_chofer(chofer_id, mes_liquidacion);
create index idx_ajustes_chofer_mes on ajustes_liquidacion(chofer_id, mes);
create index idx_mantenimientos_tracto on mantenimientos(tracto_id, pauta_id);

-- ------------------------------------------------------------
-- Triggers updated_at
-- ------------------------------------------------------------
create trigger trg_usuarios_updated before update on usuarios for each row execute function set_updated_at();
create trigger trg_clientes_updated before update on clientes for each row execute function set_updated_at();
create trigger trg_choferes_updated before update on choferes for each row execute function set_updated_at();
create trigger trg_tractos_updated before update on tractos for each row execute function set_updated_at();
create trigger trg_ramplas_updated before update on ramplas for each row execute function set_updated_at();
create trigger trg_viajes_updated before update on viajes for each row execute function set_updated_at();
create trigger trg_gastos_updated before update on gastos_viaje for each row execute function set_updated_at();
create trigger trg_facturas_updated before update on facturas for each row execute function set_updated_at();
create trigger trg_liquidaciones_updated before update on liquidaciones for each row execute function set_updated_at();

-- ------------------------------------------------------------
-- Trigger: crear perfil de usuario al registrarse en Supabase Auth
-- ------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.usuarios (auth_id, nombre, email, rol)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'nombre', split_part(coalesce(new.email, ''), '@', 1)), new.email, 'operacion');
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ------------------------------------------------------------
-- Row Level Security: la app solo accede vía backend (service_role)
-- ------------------------------------------------------------
alter table usuarios enable row level security;
alter table clientes enable row level security;
alter table choferes enable row level security;
alter table tractos enable row level security;
alter table ramplas enable row level security;
alter table viajes enable row level security;
alter table gastos_viaje enable row level security;
alter table facturas enable row level security;
alter table factura_viaje enable row level security;
alter table anticipos_chofer enable row level security;
alter table ajustes_liquidacion enable row level security;
alter table liquidaciones enable row level security;
alter table pautas_mantenimiento enable row level security;
alter table mantenimientos enable row level security;
alter table configuracion enable row level security;

-- El usuario autenticado solo puede leer su propio perfil (para ver su rol)
create policy "leer propio perfil" on usuarios
  for select using (auth.uid() = auth_id);

-- ------------------------------------------------------------
-- Seed: configuración y pauta de mantenimiento por defecto
-- ------------------------------------------------------------
insert into configuracion (clave, valor) values
  ('iva_porcentaje', '19'),
  ('alerta_km_mantenimiento', '5000'),
  ('dias_alerta_vencimientos', '30');

-- Valores por defecto (el cliente confirmará los reales en Fase 4)
insert into pautas_mantenimiento (item, intervalo_km, orden) values
  ('Cambio de aceite', 20000, 1),
  ('Filtro de aceite', 20000, 2),
  ('Filtro de aire', 40000, 3),
  ('Engrase', 5000, 4),
  ('Pastillas de freno', 60000, 5),
  ('Discos de freno', 120000, 6);
