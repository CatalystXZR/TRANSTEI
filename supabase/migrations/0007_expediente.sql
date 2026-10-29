-- ============================================================================
-- TRANSTEI — Migración 0007: Expediente del viaje (P0-05)
-- ============================================================================
-- El viaje es el átomo del negocio. El expediente agrega:
--   - Paradas (origen, carga, descarga, intermedias).
--   - Checklist operativo con ítems obligatorios.
--   - Eventos inmutables (bitácora).
--   - Incidentes con severidad y resolución.
--   - Documentos propios del viaje (guías, permisos, evidencias).
--
-- No se duplican datos del viaje: todo cuelga de `nucleo.viajes`.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Paradas
-- ----------------------------------------------------------------------------
create table nucleo.viaje_paradas (
  id                uuid primary key default gen_random_uuid(),
  empresa_id        uuid not null references nucleo.empresas(id) on delete restrict,
  viaje_id          uuid not null,
  orden             integer not null check (orden > 0),
  tipo              text not null default 'intermedia',
  nombre            text not null,
  direccion         text,
  comuna            text,
  ciudad            text,
  contacto_nombre   text,
  contacto_telefono text,
  ventana_desde     timestamptz,
  ventana_hasta     timestamptz,
  estado            text not null default 'pendiente',
  notas             text,
  activo            boolean not null default true,
  created_at        timestamptz not null default now(),
  created_by        text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at        timestamptz not null default now(),
  updated_by        text,
  version           integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  unique (viaje_id, orden),
  constraint fk_parada_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_parada_tipo check (tipo in ('origen', 'carga', 'descarga', 'intermedia', 'devolucion')),
  constraint ck_parada_estado check (estado in ('pendiente', 'en_curso', 'completada', 'omitida')),
  constraint ck_parada_ventana check (
    ventana_desde is null or ventana_hasta is null or ventana_hasta >= ventana_desde
  ),
  constraint ck_parada_nombre check (btrim(nombre) <> '')
);

create index idx_paradas_viaje on nucleo.viaje_paradas (empresa_id, viaje_id, orden);

create trigger trg_paradas_touch before update on nucleo.viaje_paradas
  for each row execute function nucleo.fn_touch();
create trigger trg_paradas_version before update on nucleo.viaje_paradas
  for each row execute function nucleo.fn_version();
create trigger trg_paradas_audit after insert or update or delete on nucleo.viaje_paradas
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Checklist
-- ----------------------------------------------------------------------------
create table nucleo.viaje_checklist (
  id              uuid primary key default gen_random_uuid(),
  empresa_id      uuid not null references nucleo.empresas(id) on delete restrict,
  viaje_id        uuid not null,
  orden           integer not null default 1 check (orden > 0),
  categoria       text not null default 'general',
  item            text not null,
  requerido       boolean not null default true,
  completado      boolean not null default false,
  completado_por  text,
  completado_en   timestamptz,
  evidencia_url   text,
  notas           text,
  created_at      timestamptz not null default now(),
  created_by      text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at      timestamptz not null default now(),
  updated_by      text,
  version         integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_checklist_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_checklist_item check (btrim(item) <> ''),
  constraint ck_checklist_completado check (
    completado = false or completado_en is not null
  )
);

create index idx_checklist_viaje on nucleo.viaje_checklist (empresa_id, viaje_id, orden);

create trigger trg_checklist_touch before update on nucleo.viaje_checklist
  for each row execute function nucleo.fn_touch();
create trigger trg_checklist_version before update on nucleo.viaje_checklist
  for each row execute function nucleo.fn_version();
create trigger trg_checklist_audit after insert or update or delete on nucleo.viaje_checklist
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Eventos (bitácora inmutable)
-- ----------------------------------------------------------------------------
create table nucleo.viaje_eventos (
  id          uuid primary key default gen_random_uuid(),
  empresa_id  uuid not null references nucleo.empresas(id) on delete restrict,
  viaje_id    uuid not null,
  tipo        text not null default 'nota',
  descripcion text not null,
  ocurrido_en timestamptz not null default now(),
  payload     jsonb not null default '{}'::jsonb,
  auth_id     text,
  created_at  timestamptz not null default now(),
  unique (empresa_id, id),
  constraint fk_evento_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_evento_descripcion check (btrim(descripcion) <> '')
);

create index idx_eventos_viaje
  on nucleo.viaje_eventos (empresa_id, viaje_id, ocurrido_en desc);

create or replace function nucleo.fn_evento_inmutable()
returns trigger
language plpgsql
as $$
begin
  raise exception 'Los eventos del viaje son inmutables: no se permite %', tg_op
    using errcode = '23514';
end;
$$;

create trigger trg_eventos_inmutable before update or delete on nucleo.viaje_eventos
  for each row execute function nucleo.fn_evento_inmutable();
create trigger trg_eventos_audit after insert on nucleo.viaje_eventos
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Incidentes
-- ----------------------------------------------------------------------------
create table nucleo.viaje_incidentes (
  id              uuid primary key default gen_random_uuid(),
  empresa_id      uuid not null references nucleo.empresas(id) on delete restrict,
  viaje_id        uuid not null,
  tipo            text not null,
  severidad       text not null default 'media',
  descripcion     text not null,
  estado          text not null default 'abierto',
  ocurrido_en     timestamptz not null default now(),
  reportado_por   text,
  resolucion      text,
  resuelto_por    text,
  resuelto_en     timestamptz,
  created_at      timestamptz not null default now(),
  created_by      text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at      timestamptz not null default now(),
  updated_by      text,
  version         integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_incidente_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_incidente_severidad check (severidad in ('baja', 'media', 'alta', 'critica')),
  constraint ck_incidente_estado check (estado in ('abierto', 'en_revision', 'resuelto', 'cerrado')),
  constraint ck_incidente_descripcion check (btrim(descripcion) <> ''),
  constraint ck_incidente_resolucion check (
    estado not in ('resuelto', 'cerrado') or resolucion is not null
  )
);

create index idx_incidentes_viaje
  on nucleo.viaje_incidentes (empresa_id, viaje_id, estado, severidad);

create trigger trg_incidentes_touch before update on nucleo.viaje_incidentes
  for each row execute function nucleo.fn_touch();
create trigger trg_incidentes_version before update on nucleo.viaje_incidentes
  for each row execute function nucleo.fn_version();
create trigger trg_incidentes_audit after insert or update or delete on nucleo.viaje_incidentes
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Documentos del viaje
-- ----------------------------------------------------------------------------
create table nucleo.viaje_documentos (
  id           uuid primary key default gen_random_uuid(),
  empresa_id   uuid not null references nucleo.empresas(id) on delete restrict,
  viaje_id     uuid not null,
  tipo         text not null default 'otro',
  nombre       text not null,
  archivo_url  text not null,
  hash_sha256  char(64),
  content_type text,
  tamano_bytes bigint check (tamano_bytes >= 0),
  observaciones text,
  activo       boolean not null default true,
  created_at   timestamptz not null default now(),
  created_by   text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at   timestamptz not null default now(),
  updated_by   text,
  version      integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_doc_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_doc_viaje_nombre check (btrim(nombre) <> '')
);

create index idx_docs_viaje on nucleo.viaje_documentos (empresa_id, viaje_id, activo);

create trigger trg_docs_viaje_touch before update on nucleo.viaje_documentos
  for each row execute function nucleo.fn_touch();
create trigger trg_docs_viaje_version before update on nucleo.viaje_documentos
  for each row execute function nucleo.fn_version();
create trigger trg_docs_viaje_audit after insert or update or delete on nucleo.viaje_documentos
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- Backfill para viajes existentes: origen/destino + checklist estándar
-- ----------------------------------------------------------------------------
insert into nucleo.viaje_paradas
  (empresa_id, viaje_id, orden, tipo, nombre, direccion, comuna, ciudad,
   ventana_desde, ventana_hasta, estado)
select v.empresa_id, v.id, 1, 'origen', v.origen_nombre, v.origen_direccion,
       v.origen_comuna, v.origen_ciudad, v.inicio_planificado, null, 'pendiente'
  from nucleo.viajes v
 where not exists (
   select 1 from nucleo.viaje_paradas p
    where p.empresa_id = v.empresa_id and p.viaje_id = v.id
 );

insert into nucleo.viaje_paradas
  (empresa_id, viaje_id, orden, tipo, nombre, direccion, comuna, ciudad,
   ventana_desde, ventana_hasta, estado)
select v.empresa_id, v.id, 2, 'descarga', v.destino_nombre, v.destino_direccion,
       v.destino_comuna, v.destino_ciudad, null, v.fin_planificado, 'pendiente'
  from nucleo.viajes v
 where not exists (
   select 1 from nucleo.viaje_paradas p
    where p.empresa_id = v.empresa_id and p.viaje_id = v.id and p.orden = 2
 );

insert into nucleo.viaje_checklist
  (empresa_id, viaje_id, orden, categoria, item, requerido)
select v.empresa_id, v.id, x.orden, x.categoria, x.item, x.requerido
  from nucleo.viajes v
 cross join (values
   (1, 'documentos', 'Documentos del viaje revisados y vigentes', true),
   (2, 'carga', 'Carga asegurada, sujeta y sellos verificados', true),
   (3, 'ruta', 'Ruta, ventanas y contactos confirmados con el cliente', true),
   (4, 'seguridad', 'Extintor, botiquín y EPP revisados', true),
   (5, 'entrega', 'Recepción conforme y evidencia de entrega', true)
 ) as x(orden, categoria, item, requerido)
 where not exists (
   select 1 from nucleo.viaje_checklist c
    where c.empresa_id = v.empresa_id and c.viaje_id = v.id
 );

-- ----------------------------------------------------------------------------
-- RLS y permisos
-- ----------------------------------------------------------------------------
alter table nucleo.viaje_paradas enable row level security;
alter table nucleo.viaje_checklist enable row level security;
alter table nucleo.viaje_eventos enable row level security;
alter table nucleo.viaje_incidentes enable row level security;
alter table nucleo.viaje_documentos enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select, insert, update on nucleo.viaje_paradas to service_role;
    grant select, insert, update on nucleo.viaje_checklist to service_role;
    grant select, insert on nucleo.viaje_eventos to service_role;
    revoke update, delete on nucleo.viaje_eventos from service_role;
    grant select, insert, update on nucleo.viaje_incidentes to service_role;
    grant select, insert, update on nucleo.viaje_documentos to service_role;
  end if;
end;
$$;

comment on table nucleo.viaje_eventos is 'Bitácora inmutable del expediente del viaje';
comment on table nucleo.viaje_checklist is 'Checklist de cierre; los ítems requeridos bloquean el cierre';
