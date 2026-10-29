-- ============================================================================
-- TRANSTEI — Migración 0005: Comercial editable (P0-03)
-- ============================================================================
-- Agrega:
--   1. Catálogo de centros de costo por empresa.
--   2. Centro de costo y flujo de aprobación de sobregiro en la OC.
--   3. Líneas de OC activas/inactivas (nunca se borran).
--
-- Las tarifas y OC ya existen en 0004. Esta migración no cambia los triggers
-- de consumo: `fn_oc_recalcular` sigue siendo la fuente de verdad del saldo.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Centros de costo
-- ----------------------------------------------------------------------------
create table nucleo.centros_costo (
  id          uuid primary key default gen_random_uuid(),
  empresa_id  uuid not null references nucleo.empresas(id) on delete restrict,
  codigo      text not null,
  nombre      text not null,
  descripcion text,
  activo      boolean not null default true,
  created_at  timestamptz not null default now(),
  created_by  text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at  timestamptz not null default now(),
  updated_by  text,
  version     integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  unique (empresa_id, codigo),
  constraint ck_centro_costo_codigo check (btrim(codigo) <> ''),
  constraint ck_centro_costo_nombre check (btrim(nombre) <> '')
);

create index idx_centros_costo_empresa_activo
  on nucleo.centros_costo (empresa_id, activo);

create trigger trg_centros_costo_touch before update on nucleo.centros_costo
  for each row execute function nucleo.fn_touch();
create trigger trg_centros_costo_version before update on nucleo.centros_costo
  for each row execute function nucleo.fn_version();
create trigger trg_centros_costo_audit after insert or update or delete on nucleo.centros_costo
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- OC: centro de costo + flujo de sobregiro
-- ----------------------------------------------------------------------------
alter table nucleo.ordenes_compra
  add column centro_costo_id uuid,
  add column sobregiro_estado text not null default 'sin_solicitud',
  add column sobregiro_solicitado numeric(16,2) not null default 0,
  add column sobregiro_motivo text,
  add column sobregiro_solicitado_por text,
  add column sobregiro_solicitado_en timestamptz,
  add column sobregiro_aprobado_por text,
  add column sobregiro_aprobado_en timestamptz,
  add column sobregiro_resolucion text;

alter table nucleo.ordenes_compra
  add constraint fk_oc_centro_costo foreign key (empresa_id, centro_costo_id)
    references nucleo.centros_costo (empresa_id, id) on delete restrict,
  add constraint ck_oc_sobregiro_estado check (
    sobregiro_estado in ('sin_solicitud', 'pendiente', 'aprobado', 'rechazado')
  ),
  add constraint ck_oc_sobregiro_solicitado check (sobregiro_solicitado >= 0),
  add constraint ck_oc_sobregiro_pendiente check (
    sobregiro_estado <> 'pendiente'
    or (sobregiro_solicitado > 0 and sobregiro_solicitado_por is not null)
  );

create index idx_oc_centro_costo
  on nucleo.ordenes_compra (empresa_id, centro_costo_id)
  where centro_costo_id is not null;
create index idx_oc_sobregiro_pendiente
  on nucleo.ordenes_compra (empresa_id)
  where sobregiro_estado = 'pendiente';

-- ----------------------------------------------------------------------------
-- Líneas de OC: borrado lógico y centro de costo
-- ----------------------------------------------------------------------------
alter table nucleo.ordenes_compra_lineas
  add column activa boolean not null default true,
  add column centro_costo_id uuid;

alter table nucleo.ordenes_compra_lineas
  add constraint fk_ocl_centro_costo foreign key (empresa_id, centro_costo_id)
    references nucleo.centros_costo (empresa_id, id) on delete restrict;

create index idx_ocl_oc_activa
  on nucleo.ordenes_compra_lineas (orden_compra_id, activa);

-- ----------------------------------------------------------------------------
-- RLS y permisos (mismo criterio que 0004: el backend usa service role)
-- ----------------------------------------------------------------------------
alter table nucleo.centros_costo enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select, insert, update on nucleo.centros_costo to service_role;
  end if;
end;
$$;

comment on table nucleo.centros_costo is 'Catálogo de centros de costo para OC y líneas';
comment on column nucleo.ordenes_compra.sobregiro_estado is 'Flujo: sin_solicitud -> pendiente -> aprobado|rechazado';
comment on column nucleo.ordenes_compra_lineas.activa is 'Las líneas no se borran: se desactivan para conservar historial';
