-- ============================================================================
-- TRANSTEI — Migración 0011: Gastos, combustible y costo real (P0-08)
-- ============================================================================
-- Gastos por viaje con respaldo, aprobación y rechazo. El costo variable real
-- se recalcula en PostgreSQL desde los gastos aprobados + comisión del chofer.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Precio diésel por fecha
-- ----------------------------------------------------------------------------
create table nucleo.precios_diesel (
  id          uuid primary key default gen_random_uuid(),
  empresa_id  uuid not null references nucleo.empresas(id) on delete restrict,
  fecha       date not null,
  precio_litro numeric(10,4) not null check (precio_litro >= 0),
  fuente      text,
  created_at  timestamptz not null default now(),
  created_by  text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  unique (empresa_id, id),
  unique (empresa_id, fecha)
);

create trigger trg_precios_diesel_audit after insert or update or delete on nucleo.precios_diesel
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Gastos del viaje
-- ----------------------------------------------------------------------------
create table nucleo.viaje_gastos (
  id                uuid primary key default gen_random_uuid(),
  empresa_id        uuid not null references nucleo.empresas(id) on delete restrict,
  viaje_id          uuid not null,
  tipo              text not null default 'otro',
  proveedor         text,
  numero_documento  text,
  fecha             date not null default current_date,
  monto_total       numeric(14,2) not null check (monto_total > 0),
  iva               numeric(14,2) not null default 0 check (iva >= 0),
  monto_neto        numeric(14,2) generated always as (monto_total - iva) stored,
  moneda            char(3) not null default 'CLP',
  litros            numeric(10,3) check (litros is null or litros > 0),
  precio_litro      numeric(10,4) check (precio_litro is null or precio_litro >= 0),
  km_odometro       numeric(12,1) check (km_odometro is null or km_odometro >= 0),
  estacion          text,
  tag               text,
  comprobante_url   text,
  estado            text not null default 'pendiente',
  motivo_rechazo    text,
  aprobado_por      text,
  aprobado_en       timestamptz,
  observaciones     text,
  activo            boolean not null default true,
  created_at        timestamptz not null default now(),
  created_by        text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at        timestamptz not null default now(),
  updated_by        text,
  version           integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_gasto_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_gasto_tipo check (tipo in (
    'combustible', 'peaje', 'estadia', 'viatico', 'mantenimiento',
    'lavado', 'pesaje', 'otro'
  )),
  constraint ck_gasto_estado check (estado in ('pendiente', 'aprobado', 'rechazado')),
  constraint ck_gasto_iva check (iva <= monto_total),
  constraint ck_gasto_rechazo check (estado <> 'rechazado' or motivo_rechazo is not null),
  constraint ck_gasto_aprobacion check (
    estado <> 'aprobado' or (aprobado_por is not null and aprobado_en is not null)
  )
);

create index idx_gastos_viaje on nucleo.viaje_gastos (empresa_id, viaje_id, estado, fecha);
create index idx_gastos_empresa_fecha on nucleo.viaje_gastos (empresa_id, fecha);

create trigger trg_gastos_touch before update on nucleo.viaje_gastos
  for each row execute function nucleo.fn_touch();
create trigger trg_gastos_version before update on nucleo.viaje_gastos
  for each row execute function nucleo.fn_version();
create trigger trg_gastos_audit after insert or update or delete on nucleo.viaje_gastos
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Costo real persistido en el viaje
-- ----------------------------------------------------------------------------
alter table nucleo.viajes
  add column costo_variable_real numeric(14,2) check (costo_variable_real >= 0),
  add column costo_total_real numeric(14,2) check (costo_total_real >= 0),
  add column costo_actualizado_en timestamptz;

create or replace function nucleo.fn_viaje_costos(p_viaje_id uuid)
returns void
language plpgsql
as $$
declare
  v_viaje record;
  v_chofer record;
  v_gastos numeric(14,2);
  v_comision numeric(14,2);
  v_total numeric(14,2);
begin
  select * into v_viaje from nucleo.viajes where id = p_viaje_id;
  if not found then
    return;
  end if;

  select coalesce(sum(g.monto_neto), 0)
    into v_gastos
    from nucleo.viaje_gastos g
   where g.viaje_id = p_viaje_id
     and g.empresa_id = v_viaje.empresa_id
     and g.estado = 'aprobado'
     and g.activo;

  v_comision := 0;
  if v_viaje.chofer_id is not null then
    select * into v_chofer from nucleo.choferes where id = v_viaje.chofer_id;
    if found then
      v_comision := round(
        coalesce(v_viaje.monto_total_neto, v_viaje.valor_flete_neto + v_viaje.monto_recargos)
        * coalesce(v_chofer.porcentaje_comision, 0),
        2
      );
    end if;
  end if;

  v_total := v_gastos + v_comision;

  update nucleo.viajes
     set costo_variable_real = v_total,
         costo_total_real = v_total,
         costo_actualizado_en = now()
   where id = p_viaje_id and empresa_id = v_viaje.empresa_id;
end;
$$;

create or replace function nucleo.fn_gasto_costos()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'DELETE' then
    perform nucleo.fn_viaje_costos(old.viaje_id);
    return old;
  end if;
  perform nucleo.fn_viaje_costos(new.viaje_id);
  if tg_op = 'UPDATE' and old.viaje_id is distinct from new.viaje_id then
    perform nucleo.fn_viaje_costos(old.viaje_id);
  end if;
  return new;
end;
$$;

create trigger trg_gastos_costos
  after insert or update or delete on nucleo.viaje_gastos
  for each row execute function nucleo.fn_gasto_costos();

-- Recalcular viajes existentes (idempotente).
do $$
declare
  v_id uuid;
begin
  for v_id in select id from nucleo.viajes loop
    perform nucleo.fn_viaje_costos(v_id);
  end loop;
end;
$$;

-- ----------------------------------------------------------------------------
-- RLS y permisos
-- ----------------------------------------------------------------------------
alter table nucleo.precios_diesel enable row level security;
alter table nucleo.viaje_gastos enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select, insert, update on nucleo.precios_diesel to service_role;
    grant select, insert, update on nucleo.viaje_gastos to service_role;
  end if;
end;
$$;

comment on table nucleo.viaje_gastos is 'Gastos del viaje con aprobación; el costo real se recalcula por trigger';
comment on function nucleo.fn_viaje_costos(uuid) is 'Costo variable real = gastos aprobados + comisión del chofer';
