-- ============================================================================
-- TRANSTEI — Migración 0009: POD y evidencia (P0-06)
-- ============================================================================
-- Prueba de Entrega (POD): firma, fotos, receptor, RUT, geolocalización,
-- fecha/hora y daños. La facturación queda bloqueada sin POD.
-- ============================================================================

create table nucleo.pod (
  id              uuid primary key default gen_random_uuid(),
  empresa_id      uuid not null references nucleo.empresas(id) on delete restrict,
  viaje_id        uuid not null,
  receptor_nombre text not null,
  receptor_rut    text,
  receptor_cargo  text,
  fecha_hora      timestamptz not null default now(),
  lat             numeric(9,6) check (lat between -90 and 90),
  lon             numeric(9,6) check (lon between -180 and 180),
  firma_url       text not null,
  firma_hash      char(64),
  fotos           jsonb not null default '[]'::jsonb,
  danios          text,
  observaciones   text,
  created_at      timestamptz not null default now(),
  created_by      text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at      timestamptz not null default now(),
  updated_by      text,
  version         integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  unique (viaje_id),
  constraint fk_pod_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_pod_receptor check (btrim(receptor_nombre) <> ''),
  constraint ck_pod_rut check (receptor_rut is null or btrim(receptor_rut) <> ''),
  constraint ck_pod_fotos check (jsonb_typeof(fotos) = 'array'),
  constraint ck_pod_firma check (btrim(firma_url) <> '')
);

create index idx_pod_empresa_fecha on nucleo.pod (empresa_id, fecha_hora desc);

create trigger trg_pod_touch before update on nucleo.pod
  for each row execute function nucleo.fn_touch();
create trigger trg_pod_version before update on nucleo.pod
  for each row execute function nucleo.fn_version();
create trigger trg_pod_audit after insert or update or delete on nucleo.pod
  for each row execute function nucleo.fn_auditoria();

-- El POD no se borra: se reemplaza con una nueva versión auditada.
create or replace function nucleo.fn_pod_no_borrar()
returns trigger
language plpgsql
as $$
begin
  raise exception 'El POD no se borra; se reemplaza con una nueva versión auditada'
    using errcode = '23514';
end;
$$;

create trigger trg_pod_no_delete before delete on nucleo.pod
  for each row execute function nucleo.fn_pod_no_borrar();

-- ----------------------------------------------------------------------------
-- Gate de facturación: sin POD no se puede pasar a 'facturado'.
-- Se reemplaza la función de 0004 conservando todas sus validaciones de OC.
-- ----------------------------------------------------------------------------
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

  if not exists (
    select 1 from nucleo.pod p
     where p.empresa_id = new.empresa_id and p.viaje_id = new.id
  ) then
    raise exception 'No se puede facturar el viaje % sin POD',
      coalesce(new.numero_viaje, new.id::text)
      using errcode = '23514';
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

-- ----------------------------------------------------------------------------
-- RLS y permisos
-- ----------------------------------------------------------------------------
alter table nucleo.pod enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select, insert, update on nucleo.pod to service_role;
    revoke delete on nucleo.pod from service_role;
  end if;
end;
$$;

comment on table nucleo.pod is 'Prueba de entrega: firma, fotos, receptor y geolocalización; bloquea facturación sin POD';
