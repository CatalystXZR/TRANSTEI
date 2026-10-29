-- ============================================================================
-- TRANSTEI — Migración 0013: Facturación y cobranza del núcleo (P0-10)
-- ============================================================================
-- Sin DTE real en el piloto: el folio se simula con `nucleo.siguiente_folio`.
-- Una factura agrupa viajes cerrados con POD; los pagos parciales y notas de
-- crédito actualizan el estado y el saldo. Al quedar pagada, los viajes pasan
-- a `cobrado`.
-- ============================================================================

create table nucleo.facturas_nucleo (
  id                 uuid primary key default gen_random_uuid(),
  empresa_id         uuid not null references nucleo.empresas(id) on delete restrict,
  numero_factura     text not null,
  cliente_id         uuid not null,
  orden_compra_id    uuid,
  fecha_emision      date not null default current_date,
  fecha_vencimiento  date not null,
  moneda             char(3) not null default 'CLP',
  neto               numeric(14,2) not null check (neto > 0),
  iva                numeric(14,2) not null default 0 check (iva >= 0),
  total              numeric(14,2) generated always as (neto + iva) stored,
  estado             text not null default 'emitida',
  observaciones      text,
  created_at         timestamptz not null default now(),
  created_by         text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at         timestamptz not null default now(),
  updated_by         text,
  version            integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  unique (empresa_id, numero_factura),
  constraint fk_factura_cliente foreign key (empresa_id, cliente_id)
    references nucleo.clientes (empresa_id, id) on delete restrict,
  constraint fk_factura_oc foreign key (empresa_id, orden_compra_id)
    references nucleo.ordenes_compra (empresa_id, id) on delete restrict,
  constraint ck_factura_estado check (estado in ('emitida', 'parcial', 'pagada', 'vencida', 'anulada')),
  constraint ck_factura_fechas check (fecha_vencimiento >= fecha_emision),
  constraint ck_factura_moneda check (moneda ~ '^[A-Z]{3}$')
);

create index idx_facturas_empresa_estado_fecha
  on nucleo.facturas_nucleo (empresa_id, estado, fecha_vencimiento);
create index idx_facturas_cliente on nucleo.facturas_nucleo (empresa_id, cliente_id);

create trigger trg_facturas_touch before update on nucleo.facturas_nucleo
  for each row execute function nucleo.fn_touch();
create trigger trg_facturas_version before update on nucleo.facturas_nucleo
  for each row execute function nucleo.fn_version();
create trigger trg_facturas_audit after insert or update or delete on nucleo.facturas_nucleo
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Viajes de la factura
-- ----------------------------------------------------------------------------
create table nucleo.factura_viajes (
  id          uuid primary key default gen_random_uuid(),
  empresa_id  uuid not null references nucleo.empresas(id) on delete restrict,
  factura_id  uuid not null,
  viaje_id    uuid not null,
  monto       numeric(14,2) not null check (monto >= 0),
  created_at  timestamptz not null default now(),
  unique (empresa_id, id),
  unique (empresa_id, factura_id, viaje_id),
  unique (empresa_id, viaje_id),
  constraint fk_fv_factura foreign key (empresa_id, factura_id)
    references nucleo.facturas_nucleo (empresa_id, id) on delete restrict,
  constraint fk_fv_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict
);

create index idx_fv_factura on nucleo.factura_viajes (empresa_id, factura_id);

create trigger trg_fv_audit after insert or update or delete on nucleo.factura_viajes
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Pagos
-- ----------------------------------------------------------------------------
create table nucleo.pagos_nucleo (
  id             uuid primary key default gen_random_uuid(),
  empresa_id     uuid not null references nucleo.empresas(id) on delete restrict,
  factura_id     uuid not null,
  fecha          date not null default current_date,
  monto          numeric(14,2) not null check (monto > 0),
  metodo         text not null default 'transferencia',
  referencia     text,
  observaciones  text,
  created_at     timestamptz not null default now(),
  created_by     text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at     timestamptz not null default now(),
  updated_by     text,
  version        integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_pago_factura foreign key (empresa_id, factura_id)
    references nucleo.facturas_nucleo (empresa_id, id) on delete restrict,
  constraint ck_pago_metodo check (metodo in (
    'transferencia', 'cheque', 'efectivo', 'tarjeta', 'condonacion', 'otro'
  ))
);

create index idx_pagos_factura on nucleo.pagos_nucleo (empresa_id, factura_id, fecha);

create trigger trg_pagos_touch before update on nucleo.pagos_nucleo
  for each row execute function nucleo.fn_touch();
create trigger trg_pagos_version before update on nucleo.pagos_nucleo
  for each row execute function nucleo.fn_version();
create trigger trg_pagos_audit after insert or update or delete on nucleo.pagos_nucleo
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Notas de crédito
-- ----------------------------------------------------------------------------
create table nucleo.notas_credito_nucleo (
  id          uuid primary key default gen_random_uuid(),
  empresa_id  uuid not null references nucleo.empresas(id) on delete restrict,
  factura_id  uuid not null,
  numero      text not null,
  fecha       date not null default current_date,
  monto       numeric(14,2) not null check (monto > 0),
  motivo      text not null,
  estado      text not null default 'aplicada',
  created_at  timestamptz not null default now(),
  created_by  text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  unique (empresa_id, id),
  unique (empresa_id, numero),
  constraint fk_nc_factura foreign key (empresa_id, factura_id)
    references nucleo.facturas_nucleo (empresa_id, id) on delete restrict,
  constraint ck_nc_estado check (estado in ('aplicada', 'anulada')),
  constraint ck_nc_motivo check (btrim(motivo) <> '')
);

create index idx_nc_factura on nucleo.notas_credito_nucleo (empresa_id, factura_id);

create trigger trg_nc_audit after insert or update or delete on nucleo.notas_credito_nucleo
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Promesas de pago
-- ----------------------------------------------------------------------------
create table nucleo.promesas_pago_nucleo (
  id                uuid primary key default gen_random_uuid(),
  empresa_id        uuid not null references nucleo.empresas(id) on delete restrict,
  factura_id        uuid not null,
  fecha_prometida   date not null,
  monto             numeric(14,2) not null check (monto > 0),
  estado            text not null default 'pendiente',
  notas             text,
  created_at        timestamptz not null default now(),
  created_by        text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  unique (empresa_id, id),
  constraint fk_promesa_factura foreign key (empresa_id, factura_id)
    references nucleo.facturas_nucleo (empresa_id, id) on delete restrict,
  constraint ck_promesa_estado check (estado in ('pendiente', 'cumplida', 'incumplida'))
);

create index idx_promesas_factura on nucleo.promesas_pago_nucleo (empresa_id, factura_id, estado);

create trigger trg_promesas_audit after insert or update or delete on nucleo.promesas_pago_nucleo
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Estado de la factura y viajes cobrados
-- ----------------------------------------------------------------------------
create or replace function nucleo.fn_factura_estado(p_factura_id uuid)
returns void
language plpgsql
as $$
declare
  v_factura record;
  v_pagos numeric(14,2);
  v_notas numeric(14,2);
  v_saldo numeric(14,2);
  v_nuevo text;
begin
  select * into v_factura from nucleo.facturas_nucleo where id = p_factura_id for update;
  if not found then
    return;
  end if;
  if v_factura.estado = 'anulada' then
    return;
  end if;

  select coalesce(sum(monto), 0) into v_pagos
    from nucleo.pagos_nucleo where factura_id = p_factura_id;
  select coalesce(sum(monto), 0) into v_notas
    from nucleo.notas_credito_nucleo
   where factura_id = p_factura_id and estado = 'aplicada';

  v_saldo := v_factura.total - v_pagos - v_notas;

  if v_saldo <= 0 then
    v_nuevo := 'pagada';
  elsif v_pagos > 0 or v_notas > 0 then
    v_nuevo := 'parcial';
  elsif v_factura.fecha_vencimiento < current_date then
    v_nuevo := 'vencida';
  else
    v_nuevo := 'emitida';
  end if;

  update nucleo.facturas_nucleo set estado = v_nuevo where id = p_factura_id;

  if v_nuevo = 'pagada' then
    update nucleo.viajes v
       set estado = 'cobrado'
      from nucleo.factura_viajes fv
     where fv.factura_id = p_factura_id
       and fv.viaje_id = v.id
       and v.empresa_id = v_factura.empresa_id
       and v.estado = 'facturado';
  end if;
end;
$$;

create or replace function nucleo.fn_pago_estado()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'DELETE' then
    perform nucleo.fn_factura_estado(old.factura_id);
    return old;
  end if;
  perform nucleo.fn_factura_estado(new.factura_id);
  if tg_op = 'UPDATE' and old.factura_id is distinct from new.factura_id then
    perform nucleo.fn_factura_estado(old.factura_id);
  end if;
  return new;
end;
$$;

create or replace function nucleo.fn_nota_estado()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'DELETE' then
    perform nucleo.fn_factura_estado(old.factura_id);
    return old;
  end if;
  perform nucleo.fn_factura_estado(new.factura_id);
  return new;
end;
$$;

create trigger trg_pagos_estado
  after insert or update or delete on nucleo.pagos_nucleo
  for each row execute function nucleo.fn_pago_estado();
create trigger trg_nc_estado
  after insert or update or delete on nucleo.notas_credito_nucleo
  for each row execute function nucleo.fn_nota_estado();

-- ----------------------------------------------------------------------------
-- RLS y permisos
-- ----------------------------------------------------------------------------
alter table nucleo.facturas_nucleo enable row level security;
alter table nucleo.factura_viajes enable row level security;
alter table nucleo.pagos_nucleo enable row level security;
alter table nucleo.notas_credito_nucleo enable row level security;
alter table nucleo.promesas_pago_nucleo enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select, insert, update on nucleo.facturas_nucleo to service_role;
    grant select, insert, update on nucleo.factura_viajes to service_role;
    grant select, insert, update on nucleo.pagos_nucleo to service_role;
    grant select, insert, update on nucleo.notas_credito_nucleo to service_role;
    grant select, insert, update on nucleo.promesas_pago_nucleo to service_role;
  end if;
end;
$$;

comment on table nucleo.facturas_nucleo is 'Factura simulada del piloto; agrupa viajes cerrados con POD';
comment on function nucleo.fn_factura_estado(uuid) is 'Recalcula estado, saldo y pasa viajes a cobrado cuando la factura se paga';
