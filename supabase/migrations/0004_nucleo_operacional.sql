-- ============================================================================
-- TRANSTEI — Migración 0004: Núcleo operacional v2 (multiempresa)
-- ============================================================================
-- Este esquema es la fuente de verdad del nuevo núcleo operacional:
--   empresa -> cliente -> OC / tarifa -> viaje -> reservas de recursos.
--
-- Decisiones estructurales:
--   1. Todo el dominio vive en el schema `nucleo` para permitir una migración
--      strangler desde el MVP `public` sin romper las pantallas actuales.
--   2. La ocupación de tractos, ramplas y choferes se lleva en un libro único
--      de reservas (`nucleo.reservas_recurso`). Así una mantención, un descanso
--      o un viaje compiten por el mismo recurso y las restricciones de
--      exclusión cubren TODAS las fuentes de ocupación, no solo los viajes.
--   3. Las restricciones EXCLUDE usan `tstzrange` semiabierto `[inicio, fin)`,
--      en UTC. La zona horaria de la empresa se usa solo para numeración,
--      vencimientos de documentos y presentación.
--   4. Los documentos son versionados. Un documento vencido o faltante bloquea
--      la asignación en el servicio y, como última línea de defensa, en un
--      trigger de base de datos.
--   5. Los registros financieros no se borran. El viaje se anula con motivo y
--      los campos financieros se congelan al iniciar la ejecución.
-- ============================================================================

create schema if not exists nucleo;

-- btree_gist es obligatorio para combinar igualdad (uuid) con solapamiento
-- de rangos en una restricción EXCLUDE.
create extension if not exists btree_gist;
create extension if not exists pgcrypto;

-- ----------------------------------------------------------------------------
-- Tipos enumerados
-- ----------------------------------------------------------------------------
create type nucleo.estado_empresa as enum ('activa', 'inactiva');
create type nucleo.rol_empresa as enum (
  'admin', 'gerente', 'despacho', 'contador', 'tesoreria',
  'taller', 'conductor', 'auditor'
);
create type nucleo.estado_recurso as enum (
  'disponible', 'asignado', 'en_ruta', 'en_taller', 'en_descanso',
  'bloqueado', 'vacaciones', 'baja'
);
create type nucleo.tipo_rampla as enum (
  'plana', 'sider', 'refrigerada', 'portacontenedor', 'cisterna',
  'cama_baja', 'granelera', 'otra'
);
create type nucleo.tipo_carga as enum (
  'general', 'granel', 'pallets', 'contenedor', 'maquinaria',
  'refrigerada', 'peligrosa', 'sobredimensionada', 'ganado', 'otra'
);
create type nucleo.estado_viaje as enum (
  'borrador', 'cotizado', 'confirmado', 'asignado', 'en_carga', 'cargado',
  'en_ruta', 'en_descarga', 'descargado', 'pod_pendiente', 'cerrado',
  'facturado', 'cobrado', 'anulado'
);
create type nucleo.estado_oc as enum ('abierta', 'parcial', 'consumida', 'vencida', 'anulada');
create type nucleo.modalidad_tarifa as enum (
  'viaje', 'km', 'tonelada', 'tonelada_km', 'hora', 'contenedor', 'estadia', 'mixta'
);
create type nucleo.tipo_documento as enum (
  'revision_tecnica', 'permiso_circulacion', 'seguro_obligatorio', 'soap',
  'seguro_carga', 'tachografo', 'limitador_velocidad', 'certificado_gases',
  'permiso_carga_peligrosa', 'licencia_conducir', 'examen_medico',
  'curso_carga_peligrosa', 'curso_manejo_defensivo', 'contrato_laboral', 'otro'
);
create type nucleo.tipo_recurso as enum ('tracto', 'rampla', 'chofer');
create type nucleo.tipo_reserva as enum (
  'viaje', 'mantenimiento', 'descanso', 'vacaciones', 'bloqueo_manual', 'siniestro', 'otro'
);

-- ----------------------------------------------------------------------------
-- Utilidades de auditoría y concurrencia
-- ----------------------------------------------------------------------------
create or replace function nucleo.fn_touch()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  new.updated_by := coalesce(
    nullif(current_setting('nucleo.auth_id', true), ''),
    new.updated_by,
    'sistema'
  );
  return new;
end;
$$;

create or replace function nucleo.fn_version()
returns trigger
language plpgsql
as $$
begin
  new.version := old.version + 1;
  return new;
end;
$$;

-- ----------------------------------------------------------------------------
-- Empresas y membresías
-- ----------------------------------------------------------------------------
create table nucleo.empresas (
  id                         uuid primary key default gen_random_uuid(),
  codigo                     text not null unique,
  razon_social               text not null,
  nombre_fantasia            text,
  rut                        text not null,
  giro                       text,
  direccion                  text,
  comuna                     text,
  ciudad                     text,
  region                     text,
  pais                       char(2) not null default 'CL',
  zona_horaria               text not null default 'America/Santiago',
  moneda                     char(3) not null default 'CLP',
  buffer_operacional_min     integer not null default 90
                              check (buffer_operacional_min between 0 and 1440),
  dias_margen_documentos     integer not null default 0
                              check (dias_margen_documentos between 0 and 90),
  dias_alerta_documentos     integer not null default 30
                              check (dias_alerta_documentos between 0 and 365),
  exigir_soap                boolean not null default true,
  exigir_seguro_carga        boolean not null default true,
  exigir_curso_carga_peligrosa boolean not null default true,
  exigir_oc                  boolean not null default false,
  estado                     nucleo.estado_empresa not null default 'activa',
  created_at                 timestamptz not null default now(),
  created_by                 text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at                 timestamptz not null default now(),
  updated_by                 text,
  version                    integer not null default 1 check (version >= 1),
  constraint ck_empresa_moneda check (moneda ~ '^[A-Z]{3}$'),
  constraint ck_empresa_rut_no_vacio check (btrim(rut) <> '')
);

create unique index uq_empresas_rut_norm
  on nucleo.empresas (upper(regexp_replace(rut, '[^0-9K]', '', 'g')));

create table nucleo.usuarios_empresa (
  id          uuid primary key default gen_random_uuid(),
  empresa_id  uuid not null references nucleo.empresas(id) on delete restrict,
  auth_id     uuid not null,
  rol         nucleo.rol_empresa not null default 'despacho',
  activo      boolean not null default true,
  created_at  timestamptz not null default now(),
  created_by  text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at  timestamptz not null default now(),
  updated_by  text,
  version     integer not null default 1 check (version >= 1),
  unique (empresa_id, auth_id)
);

create index idx_usuarios_empresa_auth on nucleo.usuarios_empresa (auth_id) where activo;

-- ----------------------------------------------------------------------------
-- Clientes
-- ----------------------------------------------------------------------------
create table nucleo.clientes (
  id                  uuid primary key default gen_random_uuid(),
  empresa_id          uuid not null references nucleo.empresas(id) on delete restrict,
  razon_social        text not null,
  rut                 text not null,
  giro                text,
  direccion           text,
  comuna              text,
  ciudad              text,
  contacto_nombre     text,
  contacto_email      text,
  contacto_telefono   text,
  dias_pago           integer not null default 30 check (dias_pago between 0 and 365),
  credito_autorizado  numeric(16,2) not null default 0 check (credito_autorizado >= 0),
  exige_oc            boolean not null default false,
  activo              boolean not null default true,
  observaciones       text,
  created_at          timestamptz not null default now(),
  created_by          text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at          timestamptz not null default now(),
  updated_by          text,
  version             integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint ck_cliente_rut_no_vacio check (btrim(rut) <> '')
);

create unique index uq_clientes_empresa_rut_norm
  on nucleo.clientes (empresa_id, upper(regexp_replace(rut, '[^0-9K]', '', 'g')));
create index idx_clientes_empresa_activo on nucleo.clientes (empresa_id, activo);

-- ----------------------------------------------------------------------------
-- Flota: tractos
-- ----------------------------------------------------------------------------
create table nucleo.tractos (
  id                       uuid primary key default gen_random_uuid(),
  empresa_id               uuid not null references nucleo.empresas(id) on delete restrict,
  patente                  text not null,
  marca                    text,
  modelo                   text,
  ano                      integer check (ano between 1950 and 2100),
  vin                      text,
  color                    text,
  configuracion_ejes       text,
  peso_bruto_kg            numeric(12,3) not null check (peso_bruto_kg > 0),
  tara_kg                  numeric(12,3) not null check (tara_kg > 0),
  capacidad_carga_kg       numeric(12,3) not null check (capacidad_carga_kg > 0),
  volumen_m3               numeric(10,3) check (volumen_m3 > 0),
  km_actual                numeric(12,1) not null default 0 check (km_actual >= 0),
  horas_motor              numeric(12,1) not null default 0 check (horas_motor >= 0),
  licencias_permitidas     text[] not null default '{}'::text[],
  estado                   nucleo.estado_recurso not null default 'disponible',
  activo                   boolean not null default true,
  ubicacion_ciudad         text,
  ubicacion_lat            numeric(9,6) check (ubicacion_lat between -90 and 90),
  ubicacion_lon            numeric(9,6) check (ubicacion_lon between -180 and 180),
  ubicacion_actualizada_en timestamptz,
  observaciones            text,
  created_at               timestamptz not null default now(),
  created_by               text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at               timestamptz not null default now(),
  updated_by               text,
  version                  integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint ck_tracto_patente_no_vacia check (btrim(patente) <> ''),
  constraint ck_tracto_peso_coherente check (tara_kg < peso_bruto_kg),
  constraint ck_tracto_capacidad_coherente check (capacidad_carga_kg <= peso_bruto_kg - tara_kg)
);

create unique index uq_tractos_empresa_patente
  on nucleo.tractos (empresa_id, upper(regexp_replace(patente, '[^A-Z0-9]', '', 'g')));
create unique index uq_tractos_empresa_vin
  on nucleo.tractos (empresa_id, upper(vin)) where vin is not null;
create index idx_tractos_empresa_estado on nucleo.tractos (empresa_id, estado, activo);

-- ----------------------------------------------------------------------------
-- Flota: ramplas
-- ----------------------------------------------------------------------------
create table nucleo.ramplas (
  id                       uuid primary key default gen_random_uuid(),
  empresa_id               uuid not null references nucleo.empresas(id) on delete restrict,
  patente                  text not null,
  tipo                     nucleo.tipo_rampla not null default 'plana',
  marca                    text,
  modelo                   text,
  ano                      integer check (ano between 1950 and 2100),
  vin                      text,
  capacidad_carga_kg       numeric(12,3) not null check (capacidad_carga_kg > 0),
  volumen_m3               numeric(10,3) check (volumen_m3 > 0),
  largo_m                  numeric(8,3) check (largo_m > 0),
  ancho_m                  numeric(8,3) check (ancho_m > 0),
  alto_m                   numeric(8,3) check (alto_m > 0),
  peso_tara_kg             numeric(12,3) check (peso_tara_kg > 0),
  ejes                     integer check (ejes between 1 and 12),
  temperatura_min_c        numeric(5,2),
  temperatura_max_c        numeric(5,2),
  estado                   nucleo.estado_recurso not null default 'disponible',
  activo                   boolean not null default true,
  ubicacion_ciudad         text,
  ubicacion_lat            numeric(9,6) check (ubicacion_lat between -90 and 90),
  ubicacion_lon            numeric(9,6) check (ubicacion_lon between -180 and 180),
  ubicacion_actualizada_en timestamptz,
  observaciones            text,
  created_at               timestamptz not null default now(),
  created_by               text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at               timestamptz not null default now(),
  updated_by               text,
  version                  integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint ck_rampla_patente_no_vacia check (btrim(patente) <> ''),
  constraint ck_rampla_temperaturas check (
    temperatura_min_c is null or temperatura_max_c is null
    or temperatura_min_c <= temperatura_max_c
  )
);

create unique index uq_ramplas_empresa_patente
  on nucleo.ramplas (empresa_id, upper(regexp_replace(patente, '[^A-Z0-9]', '', 'g')));
create unique index uq_ramplas_empresa_vin
  on nucleo.ramplas (empresa_id, upper(vin)) where vin is not null;
create index idx_ramplas_empresa_tipo on nucleo.ramplas (empresa_id, tipo, activo);

-- ----------------------------------------------------------------------------
-- Choferes
-- ----------------------------------------------------------------------------
create table nucleo.choferes (
  id                        uuid primary key default gen_random_uuid(),
  empresa_id                uuid not null references nucleo.empresas(id) on delete restrict,
  rut                       text not null,
  nombre                    text not null,
  apellido_paterno          text,
  apellido_materno          text,
  fecha_nacimiento          date,
  telefono                  text,
  email                     text,
  direccion                 text,
  comuna                    text,
  ciudad                    text,
  numero_licencia           text,
  licencia_clase            text,
  licencia_restricciones    text,
  autorizado_carga_peligrosa boolean not null default false,
  sueldo_base               numeric(14,2) not null default 0 check (sueldo_base >= 0),
  porcentaje_comision       numeric(5,4) not null default 0
                             check (porcentaje_comision between 0 and 1),
  contacto_emergencia_nombre  text,
  contacto_emergencia_telefono text,
  estado                    nucleo.estado_recurso not null default 'disponible',
  activo                    boolean not null default true,
  observaciones             text,
  created_at                timestamptz not null default now(),
  created_by                text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at                timestamptz not null default now(),
  updated_by                text,
  version                   integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint ck_chofer_rut_no_vacio check (btrim(rut) <> ''),
  constraint ck_chofer_nombre_no_vacio check (btrim(nombre) <> '')
);

create unique index uq_choferes_empresa_rut_norm
  on nucleo.choferes (empresa_id, upper(regexp_replace(rut, '[^0-9K]', '', 'g')));
create unique index uq_choferes_empresa_licencia
  on nucleo.choferes (empresa_id, upper(numero_licencia)) where numero_licencia is not null;
create index idx_choferes_empresa_estado on nucleo.choferes (empresa_id, estado, activo);

-- ----------------------------------------------------------------------------
-- Documentos versionados por recurso
-- ----------------------------------------------------------------------------
create table nucleo.documentos (
  id              uuid primary key default gen_random_uuid(),
  empresa_id      uuid not null references nucleo.empresas(id) on delete restrict,
  recurso_tipo    nucleo.tipo_recurso not null,
  tracto_id       uuid,
  rampla_id       uuid,
  chofer_id       uuid,
  tipo            nucleo.tipo_documento not null,
  numero          text,
  entidad_emisora text,
  emitido_en      date,
  vence_en        date not null,
  archivo_url     text,
  hash_sha256     char(64),
  es_vigente      boolean not null default true,
  observaciones   text,
  created_at      timestamptz not null default now(),
  created_by      text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at      timestamptz not null default now(),
  updated_by      text,
  version         integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_doc_tracto foreign key (empresa_id, tracto_id)
    references nucleo.tractos (empresa_id, id) on delete restrict,
  constraint fk_doc_rampla foreign key (empresa_id, rampla_id)
    references nucleo.ramplas (empresa_id, id) on delete restrict,
  constraint fk_doc_chofer foreign key (empresa_id, chofer_id)
    references nucleo.choferes (empresa_id, id) on delete restrict,
  constraint ck_doc_un_solo_recurso check (
    (recurso_tipo = 'tracto' and tracto_id is not null and rampla_id is null and chofer_id is null)
    or (recurso_tipo = 'rampla' and rampla_id is not null and tracto_id is null and chofer_id is null)
    or (recurso_tipo = 'chofer' and chofer_id is not null and tracto_id is null and rampla_id is null)
  ),
  constraint ck_doc_fechas check (emitido_en is null or vence_en >= emitido_en)
);

create unique index uq_doc_tracto_vigente
  on nucleo.documentos (tracto_id, tipo)
  where tracto_id is not null and es_vigente;
create unique index uq_doc_rampla_vigente
  on nucleo.documentos (rampla_id, tipo)
  where rampla_id is not null and es_vigente;
create unique index uq_doc_chofer_vigente
  on nucleo.documentos (chofer_id, tipo)
  where chofer_id is not null and es_vigente;
create index idx_documentos_empresa_vence
  on nucleo.documentos (empresa_id, vence_en) where es_vigente;

-- ----------------------------------------------------------------------------
-- Tarifas
-- ----------------------------------------------------------------------------
create table nucleo.tarifas (
  id                       uuid primary key default gen_random_uuid(),
  empresa_id               uuid not null references nucleo.empresas(id) on delete restrict,
  cliente_id               uuid not null,
  codigo                   text not null,
  nombre                   text not null,
  descripcion              text,
  modalidad                nucleo.modalidad_tarifa not null,
  origen                   text,
  destino                  text,
  tipo_rampla              nucleo.tipo_rampla,
  tipo_carga               nucleo.tipo_carga,
  vigencia_desde           date not null default current_date,
  vigencia_hasta           date,
  moneda                   char(3) not null default 'CLP',
  precio_unitario          numeric(16,4) not null default 0 check (precio_unitario >= 0),
  minimo_cobro             numeric(14,2) not null default 0 check (minimo_cobro >= 0),
  incluye_peajes           boolean not null default false,
  incluye_combustible      boolean not null default false,
  precio_diesel_base       numeric(10,4) check (precio_diesel_base >= 0),
  rendimiento_km_l         numeric(6,3) check (rendimiento_km_l > 0),
  participacion_combustible numeric(5,4) check (participacion_combustible between 0 and 1),
  recargos                 jsonb not null default '{}'::jsonb,
  condiciones              jsonb not null default '{}'::jsonb,
  activo                   boolean not null default true,
  created_at               timestamptz not null default now(),
  created_by               text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at               timestamptz not null default now(),
  updated_by               text,
  version                  integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  unique (empresa_id, cliente_id, codigo),
  constraint fk_tarifa_cliente foreign key (empresa_id, cliente_id)
    references nucleo.clientes (empresa_id, id) on delete restrict,
  constraint ck_tarifa_moneda check (moneda ~ '^[A-Z]{3}$'),
  constraint ck_tarifa_vigencia check (vigencia_hasta is null or vigencia_hasta >= vigencia_desde)
);

create index idx_tarifas_cliente_vigencia
  on nucleo.tarifas (empresa_id, cliente_id, activo, vigencia_desde);

-- ----------------------------------------------------------------------------
-- Órdenes de compra del cliente
-- ----------------------------------------------------------------------------
create table nucleo.ordenes_compra (
  id                    uuid primary key default gen_random_uuid(),
  empresa_id            uuid not null references nucleo.empresas(id) on delete restrict,
  cliente_id            uuid not null,
  numero_oc             text not null,
  referencia_interna    text,
  fecha_emision         date not null default current_date,
  vigencia_desde        date not null default current_date,
  vigencia_hasta        date not null,
  monto_autorizado      numeric(16,2) not null check (monto_autorizado > 0),
  sobregiro_autorizado  numeric(16,2) not null default 0 check (sobregiro_autorizado >= 0),
  monto_consumido       numeric(16,2) not null default 0 check (monto_consumido >= 0),
  moneda                char(3) not null default 'CLP',
  centro_costo          text,
  proyecto              text,
  faena                 text,
  condiciones_pago_dias integer check (condiciones_pago_dias between 0 and 365),
  estado                nucleo.estado_oc not null default 'abierta',
  aprobado_por          text,
  aprobado_en           timestamptz,
  observaciones         text,
  created_at            timestamptz not null default now(),
  created_by            text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at            timestamptz not null default now(),
  updated_by            text,
  version               integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  unique (empresa_id, cliente_id, numero_oc),
  constraint fk_oc_cliente foreign key (empresa_id, cliente_id)
    references nucleo.clientes (empresa_id, id) on delete restrict,
  constraint ck_oc_moneda check (moneda ~ '^[A-Z]{3}$'),
  constraint ck_oc_vigencia check (vigencia_hasta >= vigencia_desde),
  constraint ck_oc_consumo check (monto_consumido <= monto_autorizado + sobregiro_autorizado)
);

create index idx_oc_cliente_estado
  on nucleo.ordenes_compra (empresa_id, cliente_id, estado, vigencia_hasta);

create table nucleo.ordenes_compra_lineas (
  id               uuid primary key default gen_random_uuid(),
  empresa_id       uuid not null references nucleo.empresas(id) on delete restrict,
  orden_compra_id  uuid not null,
  numero_linea     integer not null check (numero_linea > 0),
  descripcion      text not null,
  origen           text,
  destino          text,
  tarifa_id        uuid,
  cantidad_estimada numeric(14,3) not null default 0 check (cantidad_estimada >= 0),
  unidad           text not null default 'viaje',
  precio_unitario  numeric(16,4) not null default 0 check (precio_unitario >= 0),
  monto_linea      numeric(16,2) not null default 0 check (monto_linea >= 0),
  created_at       timestamptz not null default now(),
  created_by       text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at       timestamptz not null default now(),
  updated_by       text,
  version          integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  unique (orden_compra_id, numero_linea),
  constraint fk_ocl_oc foreign key (empresa_id, orden_compra_id)
    references nucleo.ordenes_compra (empresa_id, id) on delete cascade,
  constraint fk_ocl_tarifa foreign key (empresa_id, tarifa_id)
    references nucleo.tarifas (empresa_id, id) on delete restrict
);

create index idx_ocl_oc on nucleo.ordenes_compra_lineas (orden_compra_id);

-- ----------------------------------------------------------------------------
-- Folios legibles (concurrencia segura)
-- ----------------------------------------------------------------------------
create table nucleo.folio_contador (
  empresa_id uuid not null references nucleo.empresas(id) on delete restrict,
  tipo       text not null,
  periodo    text not null,
  ultimo     bigint not null default 0 check (ultimo >= 0),
  primary key (empresa_id, tipo, periodo)
);

create or replace function nucleo.siguiente_folio(
  p_empresa_id uuid,
  p_tipo text,
  p_periodo text
)
returns text
language plpgsql
as $$
declare
  v_numero bigint;
begin
  insert into nucleo.folio_contador (empresa_id, tipo, periodo, ultimo)
  values (p_empresa_id, p_tipo, p_periodo, 1)
  on conflict (empresa_id, tipo, periodo)
  do update set ultimo = nucleo.folio_contador.ultimo + 1
  returning ultimo into v_numero;

  return p_tipo || '-' || p_periodo || '-' || lpad(v_numero::text, 6, '0');
end;
$$;

-- Si un viaje se inserta con un folio explícito (migración, corrección
-- autorizada), el contador debe avanzar para que el próximo folio generado
-- no colisione. Es idempotente y nunca retrocede.
create or replace function nucleo.registrar_folio(
  p_empresa_id uuid,
  p_tipo text,
  p_periodo text,
  p_numero bigint
)
returns void
language plpgsql
as $$
begin
  insert into nucleo.folio_contador (empresa_id, tipo, periodo, ultimo)
  values (p_empresa_id, p_tipo, p_periodo, p_numero)
  on conflict (empresa_id, tipo, periodo)
  do update set ultimo = greatest(nucleo.folio_contador.ultimo, excluded.ultimo);
end;
$$;

-- ----------------------------------------------------------------------------
-- Viajes: el átomo del negocio
-- ----------------------------------------------------------------------------
create table nucleo.viajes (
  id                         uuid primary key default gen_random_uuid(),
  empresa_id                 uuid not null references nucleo.empresas(id) on delete restrict,
  numero_viaje               text not null,
  cliente_id                 uuid not null,
  orden_compra_id            uuid,
  tarifa_id                  uuid,
  tracto_id                  uuid,
  rampla_id                  uuid,
  chofer_id                  uuid,
  estado                     nucleo.estado_viaje not null default 'borrador',

  inicio_planificado         timestamptz not null,
  fin_planificado            timestamptz not null,
  fin_estimado               timestamptz,
  inicio_real                timestamptz,
  fin_real                   timestamptz,
  buffer_minutos             integer not null default 90
                              check (buffer_minutos between 0 and 1440),
  ventana                    tstzrange not null,

  prioridad                  smallint not null default 3 check (prioridad between 1 and 5),

  -- Datos de carga (Plan Maestro 5.3)
  tipo_carga                 nucleo.tipo_carga not null default 'general',
  descripcion_carga          text,
  codigo_carga_cliente       text,
  peso_bruto_kg              numeric(12,3) check (peso_bruto_kg > 0),
  peso_neto_kg               numeric(12,3) check (peso_neto_kg > 0),
  tara_kg                    numeric(12,3) check (tara_kg >= 0),
  volumen_m3                 numeric(10,3) check (volumen_m3 > 0),
  bultos                     integer check (bultos >= 0),
  largo_m                    numeric(8,3) check (largo_m > 0),
  ancho_m                    numeric(8,3) check (ancho_m > 0),
  alto_m                     numeric(8,3) check (alto_m > 0),
  valor_declarado            numeric(16,2) check (valor_declarado >= 0),
  moneda_valor               char(3) default 'CLP',
  carga_peligrosa            boolean not null default false,
  numero_un                  text,
  clase_peligro              text,
  msds_url                   text,
  refrigerada                boolean not null default false,
  temperatura_min_c          numeric(5,2),
  temperatura_max_c          numeric(5,2),
  sobredimensionada          boolean not null default false,
  permiso_vialidad           text,
  requiere_grua              boolean not null default false,
  requiere_montacargas       boolean not null default false,
  sellos                     jsonb not null default '[]'::jsonb,
  instrucciones_especiales   text,

  origen_nombre              text not null,
  origen_direccion           text,
  origen_comuna              text,
  origen_ciudad              text,
  origen_region              text,
  origen_lat                 numeric(9,6) check (origen_lat between -90 and 90),
  origen_lon                 numeric(9,6) check (origen_lon between -180 and 180),
  destino_nombre             text not null,
  destino_direccion          text,
  destino_comuna             text,
  destino_ciudad             text,
  destino_region             text,
  destino_lat                numeric(9,6) check (destino_lat between -90 and 90),
  destino_lon                numeric(9,6) check (destino_lon between -180 and 180),
  distancia_km               numeric(10,2) check (distancia_km >= 0),
  km_vacios                  numeric(10,2) check (km_vacios >= 0),
  tiempo_estimado_h          numeric(8,2) check (tiempo_estimado_h >= 0),

  ventana_carga_desde        timestamptz,
  ventana_carga_hasta        timestamptz,
  ventana_descarga_desde     timestamptz,
  ventana_descarga_hasta     timestamptz,
  contacto_origen_nombre     text,
  contacto_origen_telefono   text,
  contacto_destino_nombre    text,
  contacto_destino_telefono  text,

  -- Snapshot financiero (inmutable desde el inicio de la ejecución)
  valor_flete_neto           numeric(14,2) not null default 0 check (valor_flete_neto >= 0),
  monto_recargos             numeric(14,2) not null default 0 check (monto_recargos >= 0),
  monto_total_neto           numeric(14,2) generated always as (valor_flete_neto + monto_recargos) stored not null,
  moneda                     char(3) not null default 'CLP',
  condiciones_pago_dias      integer check (condiciones_pago_dias between 0 and 365),
  tarifa_snapshot            jsonb not null default '{}'::jsonb,
  oc_numero_snapshot         text,
  costo_variable_estimado    numeric(14,2) check (costo_variable_estimado >= 0),
  freight_score_estimado     numeric(5,2) check (freight_score_estimado between 0 and 100),
  freight_score_detalle      jsonb not null default '{}'::jsonb,

  motivo_anulacion           text,
  motivo_reasignacion        text,
  anulado_por                text,
  anulado_en                 timestamptz,
  observaciones              text,

  created_at                 timestamptz not null default now(),
  created_by                 text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at                 timestamptz not null default now(),
  updated_by                 text,
  version                    integer not null default 1 check (version >= 1),

  unique (empresa_id, id),
  unique (empresa_id, numero_viaje),
  constraint fk_viaje_cliente foreign key (empresa_id, cliente_id)
    references nucleo.clientes (empresa_id, id) on delete restrict,
  constraint fk_viaje_oc foreign key (empresa_id, orden_compra_id)
    references nucleo.ordenes_compra (empresa_id, id) on delete restrict,
  constraint fk_viaje_tarifa foreign key (empresa_id, tarifa_id)
    references nucleo.tarifas (empresa_id, id) on delete restrict,
  constraint fk_viaje_tracto foreign key (empresa_id, tracto_id)
    references nucleo.tractos (empresa_id, id) on delete restrict,
  constraint fk_viaje_rampla foreign key (empresa_id, rampla_id)
    references nucleo.ramplas (empresa_id, id) on delete restrict,
  constraint fk_viaje_chofer foreign key (empresa_id, chofer_id)
    references nucleo.choferes (empresa_id, id) on delete restrict,
  constraint ck_viaje_fechas check (fin_planificado > inicio_planificado),
  constraint ck_viaje_fin_estimado check (
    fin_estimado is null or fin_estimado > inicio_planificado
  ),
  constraint ck_viaje_fin_real check (
    fin_real is null or inicio_real is null or fin_real >= inicio_real
  ),
  constraint ck_viaje_buffer check (buffer_minutos between 0 and 1440),
  constraint ck_viaje_ventana check (
    not isempty(ventana)
    and lower(ventana) = inicio_planificado
    and upper(ventana) >= coalesce(fin_real, fin_estimado, fin_planificado)
  ),
  constraint ck_viaje_recursos_por_estado check (
    estado in ('borrador', 'cotizado', 'confirmado', 'anulado')
    or (tracto_id is not null and rampla_id is not null and chofer_id is not null)
  ),
  constraint ck_viaje_peso check (
    peso_neto_kg is null or peso_bruto_kg is null or peso_neto_kg <= peso_bruto_kg
  ),
  constraint ck_viaje_temperaturas check (
    temperatura_min_c is null or temperatura_max_c is null
    or temperatura_min_c <= temperatura_max_c
  ),
  constraint ck_viaje_peligrosa_un check (
    not carga_peligrosa or numero_un is not null
  ),
  constraint ck_viaje_anulacion check (
    estado <> 'anulado' or motivo_anulacion is not null
  ),
  constraint ck_viaje_moneda check (moneda ~ '^[A-Z]{3}$')
);

create index idx_viajes_empresa_estado_ini
  on nucleo.viajes (empresa_id, estado, inicio_planificado);
create index idx_viajes_empresa_cliente on nucleo.viajes (empresa_id, cliente_id, estado);
create index idx_viajes_empresa_oc on nucleo.viajes (empresa_id, orden_compra_id) where orden_compra_id is not null;
create index idx_viajes_tracto on nucleo.viajes (empresa_id, tracto_id, inicio_planificado) where tracto_id is not null;
create index idx_viajes_rampla on nucleo.viajes (empresa_id, rampla_id, inicio_planificado) where rampla_id is not null;
create index idx_viajes_chofer on nucleo.viajes (empresa_id, chofer_id, inicio_planificado) where chofer_id is not null;
create index idx_viajes_ventana on nucleo.viajes using gist (ventana);

-- ----------------------------------------------------------------------------
-- Libro único de reservas de recursos
-- ----------------------------------------------------------------------------
create table nucleo.reservas_recurso (
  id           uuid primary key default gen_random_uuid(),
  empresa_id   uuid not null references nucleo.empresas(id) on delete restrict,
  recurso_tipo nucleo.tipo_recurso not null,
  tracto_id    uuid,
  rampla_id    uuid,
  chofer_id    uuid,
  ventana      tstzrange not null,
  tipo_reserva nucleo.tipo_reserva not null default 'viaje',
  viaje_id     uuid,
  motivo       text,
  activa       boolean not null default true,
  creado_por   text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  updated_by   text,
  version      integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_reserva_tracto foreign key (empresa_id, tracto_id)
    references nucleo.tractos (empresa_id, id) on delete restrict,
  constraint fk_reserva_rampla foreign key (empresa_id, rampla_id)
    references nucleo.ramplas (empresa_id, id) on delete restrict,
  constraint fk_reserva_chofer foreign key (empresa_id, chofer_id)
    references nucleo.choferes (empresa_id, id) on delete restrict,
  constraint fk_reserva_viaje foreign key (viaje_id)
    references nucleo.viajes(id) on delete restrict,
  constraint ck_reserva_un_recurso check (
    (recurso_tipo = 'tracto' and tracto_id is not null and rampla_id is null and chofer_id is null)
    or (recurso_tipo = 'rampla' and rampla_id is not null and tracto_id is null and chofer_id is null)
    or (recurso_tipo = 'chofer' and chofer_id is not null and tracto_id is null and rampla_id is null)
  ),
  constraint ck_reserva_ventana check (
    not isempty(ventana)
    and lower(ventana) is not null
    and upper(ventana) is not null
  ),
  constraint ck_reserva_viaje check (viaje_id is null or tipo_reserva = 'viaje'),
  constraint ck_reserva_motivo check (tipo_reserva = 'viaje' or motivo is not null)
);

-- Restricciones de exclusión: la base impide el solapamiento, no el servicio.
alter table nucleo.reservas_recurso
  add constraint ex_reserva_tracto
  exclude using gist (tracto_id with =, ventana with &&)
  where (recurso_tipo = 'tracto' and activa);

alter table nucleo.reservas_recurso
  add constraint ex_reserva_rampla
  exclude using gist (rampla_id with =, ventana with &&)
  where (recurso_tipo = 'rampla' and activa);

alter table nucleo.reservas_recurso
  add constraint ex_reserva_chofer
  exclude using gist (chofer_id with =, ventana with &&)
  where (recurso_tipo = 'chofer' and activa);

create unique index uq_reserva_viaje_recurso_activa
  on nucleo.reservas_recurso (viaje_id, recurso_tipo)
  where viaje_id is not null and activa;

create index idx_reservas_empresa_recurso
  on nucleo.reservas_recurso (empresa_id, recurso_tipo, activa);
create index idx_reservas_upper_ventana
  on nucleo.reservas_recurso (upper(ventana))
  where activa;

-- ----------------------------------------------------------------------------
-- Máquina de estados explícita (no se puede reabrir un viaje cerrado)
-- ----------------------------------------------------------------------------
create table nucleo.transiciones_viaje (
  estado_origen  nucleo.estado_viaje not null,
  estado_destino nucleo.estado_viaje not null,
  requiere_motivo boolean not null default false,
  primary key (estado_origen, estado_destino)
);

insert into nucleo.transiciones_viaje (estado_origen, estado_destino, requiere_motivo) values
  ('borrador', 'cotizado', false),
  ('borrador', 'anulado', true),
  ('cotizado', 'confirmado', false),
  ('cotizado', 'borrador', false),
  ('cotizado', 'anulado', true),
  ('confirmado', 'asignado', false),
  ('confirmado', 'anulado', true),
  ('asignado', 'en_carga', false),
  ('asignado', 'confirmado', false),
  ('asignado', 'anulado', true),
  ('en_carga', 'cargado', false),
  ('en_carga', 'asignado', false),
  ('en_carga', 'anulado', true),
  ('cargado', 'en_ruta', false),
  ('cargado', 'en_carga', false),
  ('cargado', 'anulado', true),
  ('en_ruta', 'en_descarga', false),
  ('en_ruta', 'cargado', false),
  ('en_ruta', 'anulado', true),
  ('en_descarga', 'descargado', false),
  ('en_descarga', 'en_ruta', false),
  ('en_descarga', 'anulado', true),
  ('descargado', 'pod_pendiente', false),
  ('descargado', 'cerrado', false),
  ('descargado', 'anulado', true),
  ('pod_pendiente', 'cerrado', false),
  ('pod_pendiente', 'anulado', true),
  ('cerrado', 'facturado', false),
  ('facturado', 'cobrado', false);

-- ----------------------------------------------------------------------------
-- Auditoría inmutable
-- ----------------------------------------------------------------------------
create table nucleo.auditoria (
  id            bigint generated always as identity primary key,
  empresa_id    uuid,
  tabla         text not null,
  registro_id   uuid,
  operacion     text not null check (operacion in ('INSERT', 'UPDATE', 'DELETE')),
  datos_antes   jsonb,
  datos_despues jsonb,
  auth_id       text,
  request_id    text,
  ocurrido_en   timestamptz not null default now()
);

create index idx_auditoria_registro
  on nucleo.auditoria (empresa_id, tabla, registro_id, ocurrido_en desc);
create index idx_auditoria_fecha on nucleo.auditoria (ocurrido_en desc);

create or replace function nucleo.fn_auditoria()
returns trigger
language plpgsql
security definer
set search_path = nucleo, public
as $$
declare
  v_empresa uuid;
  v_registro uuid;
  v_antes jsonb;
  v_despues jsonb;
begin
  if tg_op = 'DELETE' then
    v_antes := to_jsonb(old);
    v_registro := (v_antes->>'id')::uuid;
    v_empresa := case
      when tg_table_name = 'empresas' then v_registro
      else (v_antes->>'empresa_id')::uuid
    end;
  else
    v_despues := to_jsonb(new);
    v_registro := (v_despues->>'id')::uuid;
    v_empresa := case
      when tg_table_name = 'empresas' then v_registro
      else (v_despues->>'empresa_id')::uuid
    end;
    if tg_op = 'UPDATE' then
      v_antes := to_jsonb(old);
    end if;
  end if;

  insert into nucleo.auditoria (
    empresa_id, tabla, registro_id, operacion,
    datos_antes, datos_despues, auth_id, request_id
  )
  values (
    v_empresa,
    tg_table_schema || '.' || tg_table_name,
    v_registro,
    tg_op,
    v_antes,
    v_despues,
    coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
    nullif(current_setting('nucleo.request_id', true), '')
  );

  return coalesce(new, old);
end;
$$;

create or replace function nucleo.fn_auditoria_inmutable()
returns trigger
language plpgsql
as $$
begin
  raise exception 'La auditoría es inmutable: no se permite % en nucleo.auditoria', tg_op
    using errcode = '23514';
end;
$$;

create trigger trg_auditoria_no_update
  before update or delete on nucleo.auditoria
  for each row execute function nucleo.fn_auditoria_inmutable();

-- ----------------------------------------------------------------------------
-- Funciones de negocio del viaje
-- ----------------------------------------------------------------------------

-- Ventana de reserva: [inicio, fin real/estimado/planificado + buffer)
create or replace function nucleo.fn_viaje_ventana()
returns trigger
language plpgsql
as $$
declare
  v_fin timestamptz;
  v_zona text;
  v_anio text;
  v_oc_numero text;
  v_tarifa_snapshot jsonb;
  v_recalcular_oc boolean := false;
  v_recalcular_tarifa boolean := false;
begin
  if new.inicio_planificado is null or new.fin_planificado is null then
    raise exception 'inicio_planificado y fin_planificado son obligatorios'
      using errcode = '23514';
  end if;

  if new.fin_planificado <= new.inicio_planificado then
    raise exception 'fin_planificado debe ser posterior a inicio_planificado'
      using errcode = '23514';
  end if;

  if new.buffer_minutos is null then
    new.buffer_minutos := 0;
  end if;

  v_fin := coalesce(new.fin_real, new.fin_estimado, new.fin_planificado);
  if v_fin <= new.inicio_planificado then
    raise exception 'El fin efectivo del viaje debe ser posterior al inicio'
      using errcode = '23514';
  end if;

  new.ventana := tstzrange(
    new.inicio_planificado,
    v_fin + make_interval(mins => new.buffer_minutos),
    '[)'
  );

  if new.numero_viaje is null then
    select zona_horaria into v_zona
      from nucleo.empresas where id = new.empresa_id;
    v_zona := coalesce(v_zona, 'America/Santiago');
    v_anio := to_char(new.inicio_planificado at time zone v_zona, 'YYYY');
    new.numero_viaje := nucleo.siguiente_folio(new.empresa_id, 'VJ', v_anio);
  elsif tg_op = 'INSERT'
        and new.numero_viaje ~ '^VJ-[0-9]{4}-[0-9]+$' then
    perform nucleo.registrar_folio(
      new.empresa_id,
      'VJ',
      substring(new.numero_viaje from 4 for 4),
      substring(new.numero_viaje from 9)::bigint
    );
  end if;

  if new.tarifa_id is null then
    if tg_op = 'UPDATE' and old.tarifa_id is not null then
      new.tarifa_snapshot := '{}'::jsonb;
    end if;
  else
    if tg_op = 'INSERT' then
      v_recalcular_tarifa := true;
    else
      v_recalcular_tarifa := old.tarifa_id is distinct from new.tarifa_id
                             or new.tarifa_snapshot = '{}'::jsonb;
    end if;

    if v_recalcular_tarifa then
      select jsonb_build_object(
        'tarifa_id', t.id,
        'codigo', t.codigo,
        'nombre', t.nombre,
        'modalidad', t.modalidad,
        'cliente_id', t.cliente_id,
        'origen', t.origen,
        'destino', t.destino,
        'moneda', t.moneda,
        'precio_unitario', t.precio_unitario,
        'minimo_cobro', t.minimo_cobro,
        'vigencia_desde', t.vigencia_desde,
        'vigencia_hasta', t.vigencia_hasta,
        'incluye_peajes', t.incluye_peajes,
        'incluye_combustible', t.incluye_combustible,
        'recargos', t.recargos,
        'condiciones', t.condiciones,
        'capturado_en', now()
      )
      into v_tarifa_snapshot
      from nucleo.tarifas t
      where t.id = new.tarifa_id and t.empresa_id = new.empresa_id;

      if v_tarifa_snapshot is not null then
        new.tarifa_snapshot := v_tarifa_snapshot;
      end if;
    end if;
  end if;

  if new.orden_compra_id is null then
    new.oc_numero_snapshot := null;
  else
    if tg_op = 'INSERT' then
      v_recalcular_oc := true;
    else
      v_recalcular_oc := old.orden_compra_id is distinct from new.orden_compra_id
                         or new.oc_numero_snapshot is null;
    end if;

    if v_recalcular_oc then
      select numero_oc into v_oc_numero
        from nucleo.ordenes_compra
       where id = new.orden_compra_id and empresa_id = new.empresa_id;
      new.oc_numero_snapshot := v_oc_numero;
    end if;
  end if;

  return new;
end;
$$;

-- Validación dura de cumplimiento, capacidad, compatibilidad y OC.
create or replace function nucleo.validar_documentos_recurso(
  p_empresa_id uuid,
  p_recurso_tipo nucleo.tipo_recurso,
  p_recurso_id uuid,
  p_hasta date,
  p_peligrosa boolean default false,
  p_refrigerada boolean default false
)
returns void
language plpgsql
as $$
declare
  v_empresa record;
  v_tipos nucleo.tipo_documento[];
  v_tipo nucleo.tipo_documento;
  v_vence date;
begin
  select * into v_empresa from nucleo.empresas where id = p_empresa_id;
  if not found then
    raise exception 'Empresa % no existe', p_empresa_id using errcode = '23514';
  end if;

  if p_recurso_tipo = 'tracto' then
    v_tipos := array[
      'revision_tecnica'::nucleo.tipo_documento,
      'permiso_circulacion'::nucleo.tipo_documento,
      'seguro_obligatorio'::nucleo.tipo_documento
    ];
    if v_empresa.exigir_soap then
      v_tipos := array_append(v_tipos, 'soap'::nucleo.tipo_documento);
    end if;
    if p_peligrosa then
      v_tipos := array_append(v_tipos, 'permiso_carga_peligrosa'::nucleo.tipo_documento);
    end if;
  elsif p_recurso_tipo = 'rampla' then
    v_tipos := array[
      'revision_tecnica'::nucleo.tipo_documento,
      'permiso_circulacion'::nucleo.tipo_documento
    ];
    if v_empresa.exigir_seguro_carga then
      v_tipos := array_append(v_tipos, 'seguro_carga'::nucleo.tipo_documento);
    end if;
    if p_refrigerada then
      v_tipos := array_append(v_tipos, 'certificado_gases'::nucleo.tipo_documento);
    end if;
    if p_peligrosa then
      v_tipos := array_append(v_tipos, 'permiso_carga_peligrosa'::nucleo.tipo_documento);
    end if;
  elsif p_recurso_tipo = 'chofer' then
    v_tipos := array[
      'licencia_conducir'::nucleo.tipo_documento,
      'examen_medico'::nucleo.tipo_documento
    ];
    if p_peligrosa and v_empresa.exigir_curso_carga_peligrosa then
      v_tipos := array_append(v_tipos, 'curso_carga_peligrosa'::nucleo.tipo_documento);
    end if;
  else
    raise exception 'Tipo de recurso no soportado: %', p_recurso_tipo
      using errcode = '23514';
  end if;

  foreach v_tipo in array v_tipos loop
    select max(d.vence_en) into v_vence
      from nucleo.documentos d
     where d.empresa_id = p_empresa_id
       and d.recurso_tipo = p_recurso_tipo
       and d.tipo = v_tipo
       and d.es_vigente
       and ((p_recurso_tipo = 'tracto' and d.tracto_id = p_recurso_id)
         or (p_recurso_tipo = 'rampla' and d.rampla_id = p_recurso_id)
         or (p_recurso_tipo = 'chofer' and d.chofer_id = p_recurso_id));

    if v_vence is null then
      raise exception 'Documento % faltante para % %',
        v_tipo, p_recurso_tipo, p_recurso_id
        using errcode = '23514';
    end if;

    if v_vence < p_hasta then
      raise exception 'Documento % vencido o insuficiente para % % (vence %, requerido hasta %)',
        v_tipo, p_recurso_tipo, p_recurso_id, v_vence, p_hasta
        using errcode = '23514';
    end if;
  end loop;
end;
$$;

create or replace function nucleo.fn_viaje_validar()
returns trigger
language plpgsql
as $$
declare
  v_empresa record;
  v_cliente record;
  v_tracto record;
  v_rampla record;
  v_chofer record;
  v_oc record;
  v_tarifa record;
  v_hasta date;
  v_fin_efectivo timestamptz;
  v_inicio_local date;
  v_fin_local date;
  v_consumido_neto numeric(16,2);
begin
  if new.estado in ('borrador', 'cotizado', 'confirmado', 'anulado') then
    return new;
  end if;

  -- La validación dura se exige al asignar o al mover recursos/ventana.
  -- Un cambio puro de estado operativo (en_carga -> cargado -> en_ruta) no
  -- debe quedar bloqueado si un documento vence durante el viaje: el viaje ya
  -- fue despachado y detenerlo en ruta sería más peligroso que dejarlo cerrar.
  if tg_op = 'UPDATE'
     and new.estado <> 'asignado'
     and new.tracto_id = old.tracto_id
     and new.rampla_id = old.rampla_id
     and new.chofer_id = old.chofer_id then
    return new;
  end if;

  if new.tracto_id is null or new.rampla_id is null or new.chofer_id is null then
    raise exception 'El viaje % requiere tracto, rampla y chofer para el estado %',
      new.numero_viaje, new.estado
      using errcode = '23514';
  end if;

  select * into v_empresa from nucleo.empresas where id = new.empresa_id;
  v_inicio_local := (new.inicio_planificado at time zone v_empresa.zona_horaria)::date;

  select * into v_cliente
    from nucleo.clientes
   where id = new.cliente_id and empresa_id = new.empresa_id;
  if not found then
    raise exception 'Cliente % no pertenece a la empresa %', new.cliente_id, new.empresa_id
      using errcode = '23514';
  end if;
  if not v_cliente.activo then
    raise exception 'El cliente % está inactivo', v_cliente.razon_social
      using errcode = '23514';
  end if;

  select * into v_tracto
    from nucleo.tractos
   where id = new.tracto_id and empresa_id = new.empresa_id;
  if not found or not v_tracto.activo then
    raise exception 'Tracto % no existe o está inactivo', new.tracto_id
      using errcode = '23514';
  end if;
  if v_tracto.estado = 'baja' then
    raise exception 'El tracto % está dado de baja', v_tracto.patente
      using errcode = '23514';
  end if;

  select * into v_rampla
    from nucleo.ramplas
   where id = new.rampla_id and empresa_id = new.empresa_id;
  if not found or not v_rampla.activo then
    raise exception 'Rampla % no existe o está inactiva', new.rampla_id
      using errcode = '23514';
  end if;
  if v_rampla.estado = 'baja' then
    raise exception 'La rampla % está dada de baja', v_rampla.patente
      using errcode = '23514';
  end if;

  select * into v_chofer
    from nucleo.choferes
   where id = new.chofer_id and empresa_id = new.empresa_id;
  if not found or not v_chofer.activo then
    raise exception 'Chofer % no existe o está inactivo', new.chofer_id
      using errcode = '23514';
  end if;
  if v_chofer.estado = 'baja' then
    raise exception 'El chofer % está dado de baja', new.chofer_id
      using errcode = '23514';
  end if;

  if new.peso_bruto_kg is null then
    raise exception 'El viaje % no tiene peso bruto de carga; no se puede validar capacidad',
      new.numero_viaje
      using errcode = '23514';
  end if;

  if v_tracto.capacidad_carga_kg is null or v_tracto.capacidad_carga_kg <= 0 then
    raise exception 'El tracto % no tiene capacidad de carga configurada', v_tracto.patente
      using errcode = '23514';
  end if;
  if v_rampla.capacidad_carga_kg is null or v_rampla.capacidad_carga_kg <= 0 then
    raise exception 'La rampla % no tiene capacidad de carga configurada', v_rampla.patente
      using errcode = '23514';
  end if;

  if new.peso_bruto_kg > v_tracto.capacidad_carga_kg then
    raise exception 'Sobrepeso: carga % kg > capacidad tracto % (% kg)',
      new.peso_bruto_kg, v_tracto.patente, v_tracto.capacidad_carga_kg
      using errcode = '23514';
  end if;
  if new.peso_bruto_kg > v_rampla.capacidad_carga_kg then
    raise exception 'Sobrepeso: carga % kg > capacidad rampla % (% kg)',
      new.peso_bruto_kg, v_rampla.patente, v_rampla.capacidad_carga_kg
      using errcode = '23514';
  end if;
  if new.volumen_m3 is not null and v_rampla.volumen_m3 is not null
     and new.volumen_m3 > v_rampla.volumen_m3 then
    raise exception 'Sobrevolumen: % m3 > capacidad rampla % (% m3)',
      new.volumen_m3, v_rampla.patente, v_rampla.volumen_m3
      using errcode = '23514';
  end if;

  if new.refrigerada and v_rampla.tipo <> 'refrigerada' then
    raise exception 'La carga es refrigerada y la rampla % es de tipo %',
      v_rampla.patente, v_rampla.tipo
      using errcode = '23514';
  end if;

  if new.refrigerada then
    if new.temperatura_min_c is null or new.temperatura_max_c is null then
      raise exception 'La carga refrigerada requiere temperatura mínima y máxima'
        using errcode = '23514';
    end if;
    if v_rampla.temperatura_min_c is not null
       and new.temperatura_min_c < v_rampla.temperatura_min_c then
      raise exception 'Temperatura mínima % °C bajo el límite de la rampla % (% °C)',
        new.temperatura_min_c, v_rampla.patente, v_rampla.temperatura_min_c
        using errcode = '23514';
    end if;
    if v_rampla.temperatura_max_c is not null
       and new.temperatura_max_c > v_rampla.temperatura_max_c then
      raise exception 'Temperatura máxima % °C sobre el límite de la rampla % (% °C)',
        new.temperatura_max_c, v_rampla.patente, v_rampla.temperatura_max_c
        using errcode = '23514';
    end if;
  end if;

  if new.carga_peligrosa and not v_chofer.autorizado_carga_peligrosa then
    raise exception 'El chofer % no está autorizado para carga peligrosa',
      v_chofer.nombre
      using errcode = '23514';
  end if;

  if new.tipo_carga = 'contenedor' and v_rampla.tipo <> 'portacontenedor' then
    raise exception 'La carga es contenedor y la rampla % es de tipo %',
      v_rampla.patente, v_rampla.tipo
      using errcode = '23514';
  end if;

  if new.sobredimensionada and v_rampla.tipo not in ('cama_baja', 'plana') then
    raise exception 'La carga sobredimensionada requiere rampla plana o cama baja; % es %',
      v_rampla.patente, v_rampla.tipo
      using errcode = '23514';
  end if;

  -- La clase de licencia es un control interno/documental, no una validación
  -- legal automática. Se informa como advertencia en el servicio; la vigencia
  -- del documento de licencia sí es un bloqueo duro.

  v_fin_efectivo := coalesce(new.fin_real, new.fin_estimado, new.fin_planificado)
                    + make_interval(mins => new.buffer_minutos);
  v_fin_local := (v_fin_efectivo at time zone v_empresa.zona_horaria)::date;
  v_hasta := v_fin_local + v_empresa.dias_margen_documentos;

  perform nucleo.validar_documentos_recurso(
    new.empresa_id, 'tracto', new.tracto_id, v_hasta,
    new.carga_peligrosa, new.refrigerada
  );
  perform nucleo.validar_documentos_recurso(
    new.empresa_id, 'rampla', new.rampla_id, v_hasta,
    new.carga_peligrosa, new.refrigerada
  );
  perform nucleo.validar_documentos_recurso(
    new.empresa_id, 'chofer', new.chofer_id, v_hasta,
    new.carga_peligrosa, new.refrigerada
  );

  if new.tarifa_id is null then
    raise exception 'El viaje % no tiene tarifa asignada; no se puede despachar',
      new.numero_viaje
      using errcode = '23514';
  end if;

  select * into v_tarifa
    from nucleo.tarifas
   where id = new.tarifa_id and empresa_id = new.empresa_id;
  if not found then
    raise exception 'La tarifa % no existe en la empresa', new.tarifa_id
      using errcode = '23514';
  end if;
  if not v_tarifa.activo then
    raise exception 'La tarifa % está inactiva', v_tarifa.codigo
      using errcode = '23514';
  end if;
  if v_tarifa.cliente_id <> new.cliente_id then
    raise exception 'La tarifa % pertenece a otro cliente', v_tarifa.codigo
      using errcode = '23514';
  end if;
  if v_inicio_local < v_tarifa.vigencia_desde
     or (v_tarifa.vigencia_hasta is not null and v_inicio_local > v_tarifa.vigencia_hasta) then
    raise exception 'La tarifa % no está vigente para la fecha del viaje',
      v_tarifa.codigo
      using errcode = '23514';
  end if;
  if new.tarifa_snapshot = '{}'::jsonb then
    raise exception 'El viaje % no tiene snapshot de tarifa', new.numero_viaje
      using errcode = '23514';
  end if;

  -- La OC es un requisito de FACTURACIÓN, no de despacho. Si existe, se
  -- valida aquí; si falta, el servicio advierte y el trigger de facturación
  -- impide pasar a estado 'facturado'.
  if new.orden_compra_id is not null then
    select * into v_oc
      from nucleo.ordenes_compra
     where id = new.orden_compra_id and empresa_id = new.empresa_id;
    if not found then
      raise exception 'OC % no existe en la empresa', new.orden_compra_id
        using errcode = '23514';
    end if;
    if v_oc.cliente_id <> new.cliente_id then
      raise exception 'La OC % pertenece a otro cliente', v_oc.numero_oc
        using errcode = '23514';
    end if;
    if v_oc.estado = 'anulada' then
      raise exception 'La OC % está anulada', v_oc.numero_oc
        using errcode = '23514';
    end if;
    if v_inicio_local < v_oc.vigencia_desde or v_inicio_local > v_oc.vigencia_hasta then
      raise exception 'La OC % no está vigente para la fecha del viaje (% a %)',
        v_oc.numero_oc, v_oc.vigencia_desde, v_oc.vigencia_hasta
        using errcode = '23514';
    end if;
    if v_fin_local > v_oc.vigencia_hasta then
      raise exception 'La OC % vence el %, antes del fin del viaje (%)',
        v_oc.numero_oc, v_oc.vigencia_hasta, v_fin_local
        using errcode = '23514';
    end if;
    if v_oc.estado = 'vencida' then
      raise exception 'La OC % está vencida', v_oc.numero_oc
        using errcode = '23514';
    end if;
    -- Al reasignar/actualizar un viaje que ya estaba confirmado, su monto
    -- ya está incluido en monto_consumido. Restarlo evita contarlo dos veces.
    if tg_op = 'UPDATE'
       and old.orden_compra_id = new.orden_compra_id
       and old.estado not in ('borrador', 'cotizado', 'anulado') then
      v_consumido_neto := greatest(
        0,
        v_oc.monto_consumido - (old.valor_flete_neto + old.monto_recargos)
      );
    else
      v_consumido_neto := v_oc.monto_consumido;
    end if;

    if (new.valor_flete_neto + new.monto_recargos) + v_consumido_neto
       > v_oc.monto_autorizado + v_oc.sobregiro_autorizado then
      raise exception 'La OC % no tiene saldo suficiente: consumido %, viaje %, autorizado %',
        v_oc.numero_oc, v_consumido_neto,
        (new.valor_flete_neto + new.monto_recargos),
        v_oc.monto_autorizado + v_oc.sobregiro_autorizado
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

-- Gate de facturación: sin OC no se factura. Es independiente del despacho.
create or replace function nucleo.fn_viaje_facturacion()
returns trigger
language plpgsql
as $$
declare
  v_empresa record;
  v_oc record;
  v_inicio_local date;
  v_fin_local date;
  v_fin_efectivo timestamptz;
begin
  if new.estado <> 'facturado' or old.estado = 'facturado' then
    return new;
  end if;

  if new.orden_compra_id is null then
    raise exception 'No se puede facturar el viaje % sin orden de compra',
      coalesce(new.numero_viaje, new.id::text)
      using errcode = '23514';
  end if;

  select * into v_empresa from nucleo.empresas where id = new.empresa_id;
  select * into v_oc
    from nucleo.ordenes_compra
   where id = new.orden_compra_id and empresa_id = new.empresa_id;
  if not found then
    raise exception 'La OC % no existe en la empresa', new.orden_compra_id
      using errcode = '23514';
  end if;
  if v_oc.estado = 'anulada' then
    raise exception 'La OC % está anulada; no se puede facturar', v_oc.numero_oc
      using errcode = '23514';
  end if;
  if v_oc.cliente_id <> new.cliente_id then
    raise exception 'La OC % pertenece a otro cliente', v_oc.numero_oc
      using errcode = '23514';
  end if;
  if v_oc.moneda <> new.moneda then
    raise exception 'La OC % está en % y el viaje en %',
      v_oc.numero_oc, v_oc.moneda, new.moneda
      using errcode = '23514';
  end if;

  v_inicio_local := (new.inicio_planificado at time zone v_empresa.zona_horaria)::date;
  v_fin_efectivo := coalesce(new.fin_real, new.fin_estimado, new.fin_planificado)
                    + make_interval(mins => new.buffer_minutos);
  v_fin_local := (v_fin_efectivo at time zone v_empresa.zona_horaria)::date;

  if v_inicio_local < v_oc.vigencia_desde or v_fin_local > v_oc.vigencia_hasta then
    raise exception 'La OC % no cubre la fecha del viaje (% a %)',
      v_oc.numero_oc, v_oc.vigencia_desde, v_oc.vigencia_hasta
      using errcode = '23514';
  end if;
  if v_oc.monto_consumido > v_oc.monto_autorizado + v_oc.sobregiro_autorizado then
    raise exception 'La OC % está sobreconsumida: consumido %, autorizado %',
      v_oc.numero_oc, v_oc.monto_consumido,
      v_oc.monto_autorizado + v_oc.sobregiro_autorizado
      using errcode = '23514';
  end if;

  return new;
end;
$$;

-- Congelamiento financiero y prohibición de borrado físico.
create or replace function nucleo.fn_viaje_proteccion()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'DELETE' then
    if old.estado not in ('borrador', 'cotizado') then
      raise exception 'No se puede borrar el viaje % en estado %; use anulación auditada',
        old.numero_viaje, old.estado
        using errcode = '23514';
    end if;
    return old;
  end if;

  if new.empresa_id <> old.empresa_id then
    raise exception 'No se puede cambiar la empresa de un viaje' using errcode = '23514';
  end if;

  if new.numero_viaje <> old.numero_viaje then
    raise exception 'El número de viaje es inmutable' using errcode = '23514';
  end if;

  if old.estado in (
       'en_carga', 'cargado', 'en_ruta', 'en_descarga', 'descargado',
       'pod_pendiente', 'cerrado', 'facturado', 'cobrado', 'anulado'
     ) then
    if new.valor_flete_neto <> old.valor_flete_neto
       or new.monto_recargos <> old.monto_recargos
       or new.tarifa_id is distinct from old.tarifa_id
       or new.tarifa_snapshot is distinct from old.tarifa_snapshot
       or new.moneda <> old.moneda
       or new.condiciones_pago_dias is distinct from old.condiciones_pago_dias
       or new.cliente_id <> old.cliente_id then
      if coalesce(current_setting('nucleo.ajuste_autorizado', true), '') <> 'on' then
        raise exception 'Viaje % en estado %: campos financieros congelados; use un ajuste auditado',
          old.numero_viaje, old.estado
          using errcode = '23514';
      end if;
    end if;
  end if;

  if old.estado = 'anulado' and new.estado <> 'anulado' then
    raise exception 'Un viaje anulado no se puede reabrir' using errcode = '23514';
  end if;

  -- La OC es una referencia de facturación: puede agregarse o corregirse
  -- mientras el viaje no esté facturado/cobrado/anulado. Queda en auditoría
  -- y su consumo se recalcula; el precio/tarifa sigue congelado.
  if old.estado in ('facturado', 'cobrado', 'anulado')
     and (new.orden_compra_id is distinct from old.orden_compra_id
          or new.oc_numero_snapshot is distinct from old.oc_numero_snapshot) then
    raise exception 'La OC de un viaje % es inmutable', old.estado
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create or replace function nucleo.fn_viaje_transicion()
returns trigger
language plpgsql
as $$
declare
  v_transicion record;
begin
  if new.estado = old.estado then
    return new;
  end if;

  select * into v_transicion
    from nucleo.transiciones_viaje
   where estado_origen = old.estado and estado_destino = new.estado;

  if not found then
    raise exception 'Transición de viaje no permitida: % -> %', old.estado, new.estado
      using errcode = '23514';
  end if;

  if v_transicion.requiere_motivo and new.motivo_anulacion is null then
    raise exception 'La transición % -> % requiere motivo', old.estado, new.estado
      using errcode = '23514';
  end if;

  if new.estado = 'anulado' then
    new.anulado_por := coalesce(
      nullif(current_setting('nucleo.auth_id', true), ''),
      new.anulado_por,
      'sistema'
    );
    new.anulado_en := coalesce(new.anulado_en, now());
  end if;

  return new;
end;
$$;

-- Recalcular consumo de OC de forma idempotente y serializada.
create or replace function nucleo.fn_oc_recalcular(p_oc_id uuid)
returns void
language plpgsql
as $$
declare
  v_consumido numeric(16,2);
  v_autorizado numeric(16,2);
  v_sobregiro numeric(16,2);
  v_estado nucleo.estado_oc;
begin
  if p_oc_id is null then
    return;
  end if;

  select monto_autorizado, sobregiro_autorizado, estado
    into v_autorizado, v_sobregiro, v_estado
    from nucleo.ordenes_compra
   where id = p_oc_id
   for update;

  if not found then
    return;
  end if;

  select coalesce(sum(v.monto_total_neto), 0)
    into v_consumido
    from nucleo.viajes v
   where v.orden_compra_id = p_oc_id
     and v.estado not in ('borrador', 'cotizado', 'anulado');

  if v_consumido > v_autorizado + v_sobregiro then
    raise exception 'La OC % no tiene saldo suficiente: consumido %, autorizado %',
      p_oc_id, v_consumido, v_autorizado + v_sobregiro
      using errcode = '23514';
  end if;

  update nucleo.ordenes_compra
     set monto_consumido = v_consumido,
         estado = case
           when estado = 'anulada' then 'anulada'::nucleo.estado_oc
           when estado = 'vencida' then 'vencida'::nucleo.estado_oc
           when v_consumido >= v_autorizado then 'consumida'::nucleo.estado_oc
           when v_consumido > 0 then 'parcial'::nucleo.estado_oc
           else 'abierta'::nucleo.estado_oc
         end
   where id = p_oc_id;
end;
$$;

create or replace function nucleo.fn_viaje_oc()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'DELETE' then
    perform nucleo.fn_oc_recalcular(old.orden_compra_id);
    return old;
  end if;

  if tg_op = 'UPDATE' then
    if old.orden_compra_id is distinct from new.orden_compra_id then
      perform nucleo.fn_oc_recalcular(old.orden_compra_id);
    end if;
  end if;

  perform nucleo.fn_oc_recalcular(new.orden_compra_id);
  return new;
end;
$$;

-- Sincronización atómica viaje -> libro de reservas.
create or replace function nucleo.fn_viaje_reservas()
returns trigger
language plpgsql
as $$
declare
  v_auth text := coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema');
begin
  update nucleo.reservas_recurso
     set activa = false
   where viaje_id = new.id and activa;

  if new.estado not in ('borrador', 'cotizado', 'confirmado', 'anulado')
     and new.tracto_id is not null
     and new.rampla_id is not null
     and new.chofer_id is not null then
    insert into nucleo.reservas_recurso (
      empresa_id, recurso_tipo, tracto_id, rampla_id, chofer_id, ventana,
      tipo_reserva, viaje_id, motivo, activa, creado_por
    ) values
      (new.empresa_id, 'tracto', new.tracto_id, null, null, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth),
      (new.empresa_id, 'rampla', null, new.rampla_id, null, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth),
      (new.empresa_id, 'chofer', null, null, new.chofer_id, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth);
  end if;

  return new;
end;
$$;

-- Validación de coherencia del libro de reservas.
create or replace function nucleo.fn_reserva_validar()
returns trigger
language plpgsql
as $$
begin
  if lower(new.ventana) is null or upper(new.ventana) is null or isempty(new.ventana) then
    raise exception 'La reserva debe tener una ventana finita y no vacía'
      using errcode = '23514';
  end if;

  if new.tipo_reserva = 'viaje' then
    if new.viaje_id is null then
      raise exception 'Una reserva de viaje requiere viaje_id' using errcode = '23514';
    end if;
    -- Una reserva histórica desactivada puede apuntar a un recurso que el
    -- viaje ya no usa (reasignación). Solo se exige coherencia si sigue activa.
    if new.activa and not exists (
      select 1
        from nucleo.viajes v
       where v.id = new.viaje_id
         and v.empresa_id = new.empresa_id
         and ((new.recurso_tipo = 'tracto' and v.tracto_id = new.tracto_id)
           or (new.recurso_tipo = 'rampla' and v.rampla_id = new.rampla_id)
           or (new.recurso_tipo = 'chofer' and v.chofer_id = new.chofer_id))
    ) then
      raise exception 'La reserva no coincide con los recursos del viaje %', new.viaje_id
        using errcode = '23514';
    end if;
  else
    if new.viaje_id is not null then
      raise exception 'Solo las reservas de viaje pueden tener viaje_id'
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

create or replace function nucleo.fn_reserva_no_borrar()
returns trigger
language plpgsql
as $$
begin
  raise exception 'Las reservas no se borran; se desactivan para conservar trazabilidad'
    using errcode = '23514';
end;
$$;

-- Un documento nuevo desactiva la versión anterior del mismo tipo. La
-- unicidad parcial es la última defensa ante dos inserciones concurrentes.
create or replace function nucleo.fn_documento_vigente_unico()
returns trigger
language plpgsql
as $$
begin
  if not new.es_vigente then
    return new;
  end if;

  if new.recurso_tipo = 'tracto' then
    update nucleo.documentos
       set es_vigente = false
     where empresa_id = new.empresa_id
       and tracto_id = new.tracto_id
       and tipo = new.tipo
       and es_vigente
       and id <> new.id;
  elsif new.recurso_tipo = 'rampla' then
    update nucleo.documentos
       set es_vigente = false
     where empresa_id = new.empresa_id
       and rampla_id = new.rampla_id
       and tipo = new.tipo
       and es_vigente
       and id <> new.id;
  elsif new.recurso_tipo = 'chofer' then
    update nucleo.documentos
       set es_vigente = false
     where empresa_id = new.empresa_id
       and chofer_id = new.chofer_id
       and tipo = new.tipo
       and es_vigente
       and id <> new.id;
  end if;

  return new;
end;
$$;

create or replace function nucleo.fn_documento_no_borrar()
returns trigger
language plpgsql
as $$
begin
  raise exception 'Los documentos no se borran; se reemplazan por una nueva versión'
    using errcode = '23514';
end;
$$;

-- ----------------------------------------------------------------------------
-- Triggers de mantenimiento y auditoría
-- ----------------------------------------------------------------------------
create trigger trg_empresas_touch before update on nucleo.empresas
  for each row execute function nucleo.fn_touch();
create trigger trg_empresas_version before update on nucleo.empresas
  for each row execute function nucleo.fn_version();
create trigger trg_empresas_audit after insert or update or delete on nucleo.empresas
  for each row execute function nucleo.fn_auditoria();

create trigger trg_usuarios_empresa_touch before update on nucleo.usuarios_empresa
  for each row execute function nucleo.fn_touch();
create trigger trg_usuarios_empresa_version before update on nucleo.usuarios_empresa
  for each row execute function nucleo.fn_version();
create trigger trg_usuarios_empresa_audit after insert or update or delete on nucleo.usuarios_empresa
  for each row execute function nucleo.fn_auditoria();

create trigger trg_clientes_touch before update on nucleo.clientes
  for each row execute function nucleo.fn_touch();
create trigger trg_clientes_version before update on nucleo.clientes
  for each row execute function nucleo.fn_version();
create trigger trg_clientes_audit after insert or update or delete on nucleo.clientes
  for each row execute function nucleo.fn_auditoria();

create trigger trg_tractos_touch before update on nucleo.tractos
  for each row execute function nucleo.fn_touch();
create trigger trg_tractos_version before update on nucleo.tractos
  for each row execute function nucleo.fn_version();
create trigger trg_tractos_audit after insert or update or delete on nucleo.tractos
  for each row execute function nucleo.fn_auditoria();

create trigger trg_ramplas_touch before update on nucleo.ramplas
  for each row execute function nucleo.fn_touch();
create trigger trg_ramplas_version before update on nucleo.ramplas
  for each row execute function nucleo.fn_version();
create trigger trg_ramplas_audit after insert or update or delete on nucleo.ramplas
  for each row execute function nucleo.fn_auditoria();

create trigger trg_choferes_touch before update on nucleo.choferes
  for each row execute function nucleo.fn_touch();
create trigger trg_choferes_version before update on nucleo.choferes
  for each row execute function nucleo.fn_version();
create trigger trg_choferes_audit after insert or update or delete on nucleo.choferes
  for each row execute function nucleo.fn_auditoria();

create trigger trg_documentos_touch before update on nucleo.documentos
  for each row execute function nucleo.fn_touch();
create trigger trg_documentos_version before update on nucleo.documentos
  for each row execute function nucleo.fn_version();
create trigger trg_documentos_vigente before insert or update on nucleo.documentos
  for each row execute function nucleo.fn_documento_vigente_unico();
create trigger trg_documentos_no_delete before delete on nucleo.documentos
  for each row execute function nucleo.fn_documento_no_borrar();
create trigger trg_documentos_audit after insert or update or delete on nucleo.documentos
  for each row execute function nucleo.fn_auditoria();

create trigger trg_tarifas_touch before update on nucleo.tarifas
  for each row execute function nucleo.fn_touch();
create trigger trg_tarifas_version before update on nucleo.tarifas
  for each row execute function nucleo.fn_version();
create trigger trg_tarifas_audit after insert or update or delete on nucleo.tarifas
  for each row execute function nucleo.fn_auditoria();

create trigger trg_oc_touch before update on nucleo.ordenes_compra
  for each row execute function nucleo.fn_touch();
create trigger trg_oc_version before update on nucleo.ordenes_compra
  for each row execute function nucleo.fn_version();
create trigger trg_oc_audit after insert or update or delete on nucleo.ordenes_compra
  for each row execute function nucleo.fn_auditoria();

create trigger trg_ocl_touch before update on nucleo.ordenes_compra_lineas
  for each row execute function nucleo.fn_touch();
create trigger trg_ocl_version before update on nucleo.ordenes_compra_lineas
  for each row execute function nucleo.fn_version();
create trigger trg_ocl_audit after insert or update or delete on nucleo.ordenes_compra_lineas
  for each row execute function nucleo.fn_auditoria();

-- El orden alfabético de los triggers BEFORE importa. Los prefijos numéricos
-- garantizan: ventana -> validación -> protección -> transición -> touch -> versión.
create trigger trg_viajes_00_ventana before insert or update on nucleo.viajes
  for each row execute function nucleo.fn_viaje_ventana();
create trigger trg_viajes_10_validar before insert or update on nucleo.viajes
  for each row execute function nucleo.fn_viaje_validar();
create trigger trg_viajes_15_facturacion before update on nucleo.viajes
  for each row execute function nucleo.fn_viaje_facturacion();
create trigger trg_viajes_20_proteccion before update or delete on nucleo.viajes
  for each row execute function nucleo.fn_viaje_proteccion();
create trigger trg_viajes_30_transicion before update on nucleo.viajes
  for each row execute function nucleo.fn_viaje_transicion();
create trigger trg_viajes_40_touch before update on nucleo.viajes
  for each row execute function nucleo.fn_touch();
create trigger trg_viajes_50_version before update on nucleo.viajes
  for each row execute function nucleo.fn_version();
create trigger trg_viajes_60_audit after insert or update or delete on nucleo.viajes
  for each row execute function nucleo.fn_auditoria();
create trigger trg_viajes_70_reservas after insert or update on nucleo.viajes
  for each row execute function nucleo.fn_viaje_reservas();
create trigger trg_viajes_80_oc after insert or update or delete on nucleo.viajes
  for each row execute function nucleo.fn_viaje_oc();

create trigger trg_reservas_touch before update on nucleo.reservas_recurso
  for each row execute function nucleo.fn_touch();
create trigger trg_reservas_version before update on nucleo.reservas_recurso
  for each row execute function nucleo.fn_version();
create trigger trg_reservas_validar before insert or update on nucleo.reservas_recurso
  for each row execute function nucleo.fn_reserva_validar();
create trigger trg_reservas_no_delete before delete on nucleo.reservas_recurso
  for each row execute function nucleo.fn_reserva_no_borrar();
create trigger trg_reservas_audit after insert or update or delete on nucleo.reservas_recurso
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- RLS: el backend entra con service_role/postgres; anon/authenticated no ven nada.
-- ----------------------------------------------------------------------------
alter table nucleo.empresas enable row level security;
alter table nucleo.usuarios_empresa enable row level security;
alter table nucleo.clientes enable row level security;
alter table nucleo.tractos enable row level security;
alter table nucleo.ramplas enable row level security;
alter table nucleo.choferes enable row level security;
alter table nucleo.documentos enable row level security;
alter table nucleo.tarifas enable row level security;
alter table nucleo.ordenes_compra enable row level security;
alter table nucleo.ordenes_compra_lineas enable row level security;
alter table nucleo.viajes enable row level security;
alter table nucleo.reservas_recurso enable row level security;
alter table nucleo.transiciones_viaje enable row level security;
alter table nucleo.auditoria enable row level security;
alter table nucleo.folio_contador enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant usage on schema nucleo to service_role;
    grant select, insert, update on all tables in schema nucleo to service_role;
    grant usage, select on all sequences in schema nucleo to service_role;
    -- La auditoría solo admite lectura e inserción; nunca update/delete.
    revoke update, delete on nucleo.auditoria from service_role;
    grant select, insert on nucleo.auditoria to service_role;
  end if;
end;
$$;

comment on schema nucleo is 'Núcleo operacional ERP Transportes TEI: multiempresa, viajes, disponibilidad y cumplimiento';
comment on table nucleo.viajes is 'Átomo del negocio: todo cuelga del viaje';
comment on table nucleo.reservas_recurso is 'Libro único de ocupación con EXCLUDE USING gist para tracto, rampla y chofer';
comment on table nucleo.documentos is 'Documentos versionados por recurso; vencidos o faltantes bloquean la asignación';
comment on table nucleo.auditoria is 'Log append-only de cambios; inmutable por trigger';
