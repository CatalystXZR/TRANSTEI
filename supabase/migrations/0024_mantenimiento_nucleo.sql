-- ============================================================================
-- TRANSTEI — Migración 0024: mantenimiento por km en el núcleo (Ola B.1)
-- ============================================================================
--
-- OBJETIVO
--   Portar al núcleo el módulo legacy de mantenimiento preventivo
--   (`public.pautas_mantenimiento` + `public.mantenimientos`, `0001:188-209`),
--   que es el **único** control de mantención de la flota y no tiene equivalente
--   en `nucleo` (solo existe la reserva de recurso tipo `mantenimiento`).
--
--   Reglas portadas (docs/negocio/retiro-legacy-modulos.md §5, RET-08):
--     · pauta por ítem con `intervalo_km > 0`, orden y baja lógica (`activo`);
--     · registro de mantención con recurso (tracto **o** rampla), fecha, km,
--       costo y observaciones;
--     · `proximo_km = ultimo_km + intervalo_km` y semáforo
--       `restante <= 0 -> pendiente`, `restante <= alerta_km -> por_vencer`,
--       si no `ok`, sin registro -> `sin_registro`.
--     · **no bloquea el despacho** (no se agrega ninguna dependencia con viajes).
--
--   Correcciones obligatorias al portar (§5.4):
--     1. `costo >= 0` impuesto en la base (el legacy no lo validaba: `0001:205`).
--     2. Snapshot del intervalo y de la alerta en cada registro: editar la pauta
--        **no** reinterpreta el histórico (defecto CN-08 borde).
--     3. `empresa_id` + FKs compuestas por empresa en todas las filas.
--     4. `respaldo_url` acotada (sin `..`, sin ruta absoluta) para boleta/foto.
--     5. Una sola definición del cálculo de estado: la vista
--        `nucleo.v_mantenimiento_estado` (no se guarda el semáforo en la fila,
--        que quedaría obsoleto al moverse el odómetro).
--
--   Objetos: 2 tablas, 1 vista (`security_invoker`),
--   2 funciones de trigger nuevas (`fn_mantenimiento_validar`,
--   `fn_mantenimiento_no_borrar`) + `fn_mantenimiento_odometro`, 9 triggers,
--   RLS `ENABLE`+`FORCE`, 2 políticas `tenant_empresa`, GRANTs a `tei_app`
--   (sin `delete`) y `COMMENT`s.
--   Reutiliza `nucleo.fn_touch()`, `nucleo.fn_version()` y `nucleo.fn_auditoria()`
--   de `0004`; NO las modifica.
--
-- REQUISITO DE ORDEN
--   Después de `0004` (tractos, ramplas, fn_touch/fn_version/fn_auditoria) y de
--   `0020` (rol `tei_app`, `nucleo.ctx_empresa()`, USAGE en `nucleo`).
--
-- PRECONDICIONES (detección; abortan con 23514, no "arreglan")
--   P1  Ni `nucleo.pautas_mantenimiento` ni `nucleo.mantenimientos` existen.
--   P2  `0020` aplicada: existe `nucleo.ctx_empresa()`, existe el rol `tei_app`
--       con USAGE sobre `nucleo`, y existe `nucleo.empresas`.
--   P3  `nucleo.tractos` y `nucleo.ramplas` tienen `UNIQUE (empresa_id, id)`
--       (sin eso no hay FK compuesta posible).
--   P4  Se siembran 0 pautas: la migración NO porta los seeds del legacy
--       (`0001:296-302`), porque sus intervalos no tienen fuente documental
--       (P-11). Se verifica dentro de la transacción tras el DDL.
--
-- IMPACTO EN DATOS Y LOCKS
--   · Dos `CREATE TABLE` vacías y una vista: sin reescritura, sin backfill, sin
--     UPDATE/DELETE sobre datos existentes. Locks de catálogo por milisegundos
--     sobre objetos nuevos.
--   · `CREATE INDEX` no concurrente sobre tablas **vacías** (el lock es
--     irrelevante; no se usa `CONCURRENTLY`, que no puede ir en transacción).
--   · La vista lee `nucleo.tractos`/`nucleo.ramplas`: no toma locks, no
--     materializa.
--   · El legacy `public` NO se toca: ninguna sentencia referencia `public`.
--   · La app actual (rol `postgres`, BYPASSRLS) no cambia de comportamiento:
--     nadie lee estas tablas todavía.
--
-- LO QUE ESTA MIGRACIÓN NO IMPONE (declarado)
--   · Unicidad del ítem **entre empresas**: la pauta es por empresa por diseño.
--   · Que una mantención vencida bloquee la asignación del tracto: el negocio no
--     lo definió (§5.3, pregunta abierta al dueño) y el legacy no lo hace.
--   · El costo dentro del costo del viaje / costo por km (`D-20`, abierto).
--   · Que `tractos.km_actual` sea el odómetro "verdadero": el trigger solo lo
--     **sube** al km registrado (regla legacy `mantenimiento.py:133-135`); un
--     km menor no lo reduce.
--   · Integración con `nucleo.configuracion_empresa` (clave
--     `alerta_km_mantenimiento`): llega en `0026`; la vista usa el default legacy
--     de 5.000 km cuando la pauta no fija `alerta_km` y lo documenta.
--
-- ROLLBACK (orden inverso, sin datos de negocio)
--   `supabase/tests/0024_99_rollback.sql`:
--     drop view  nucleo.v_mantenimiento_estado;
--     drop table nucleo.mantenimientos;
--     drop table nucleo.pautas_mantenimiento;
--     drop function nucleo.fn_mantenimiento_validar();
--     drop function nucleo.fn_mantenimiento_no_borrar();
--   Con las tablas caen PK, UNIQUE, FKs, CHECKs, índices, triggers, políticas y
--   GRANTs. Pérdida: las pautas y los registros de mantención creados desde la
--   aplicación (hoy 0 filas). No toca `nucleo.tractos` (el `km_actual` que el
--   trigger hubiera subido NO se revierte: es un hecho del odómetro).
--
-- INVARIANTES (registro en docs/datos/invariantes.md §13)
--   INV-MANT01  `costo >= 0` en todo registro de mantención.
--   INV-MANT02  `km >= 0` y `proximo = ultimo + intervalo` con el intervalo
--               **vigente al registrar** (snapshot inmutable).
--   INV-MANT03  Editar/desactivar una pauta no cambia el histórico ya registrado.
--   INV-MANT04  Un registro apunta a un recurso de su misma empresa y del tipo
--               de la pauta (FK compuesta + trigger).
--   INV-MANT05  El semáforo tiene una sola definición (vista) y no se almacena.
--   INV-MANT06  Toda fila es invisible/inescribible fuera de `app.empresa_id`.
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones defendidas
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  if to_regclass('nucleo.pautas_mantenimiento') is not null
     or to_regclass('nucleo.mantenimientos') is not null then
    raise exception 'PRECONDICIÓN P1: ya existe nucleo.pautas_mantenimiento o nucleo.mantenimientos; 0024 no se re-aplica'
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo' and p.proname = 'ctx_empresa';
  if v_n <> 1 then
    raise exception 'PRECONDICIÓN P2: falta nucleo.ctx_empresa(); aplicar 0020 primero'
      using errcode = '23514';
  end if;
  if not exists (select 1 from pg_roles where rolname = 'tei_app') then
    raise exception 'PRECONDICIÓN P2: falta el rol tei_app; aplicar 0020 primero'
      using errcode = '23514';
  end if;
  if not has_schema_privilege('tei_app', 'nucleo', 'USAGE') then
    raise exception 'PRECONDICIÓN P2: tei_app sin USAGE sobre nucleo; aplicar 0020 primero'
      using errcode = '23514';
  end if;
  if to_regclass('nucleo.empresas') is null then
    raise exception 'PRECONDICIÓN P2: falta nucleo.empresas (destino de la FK)'
      using errcode = '23514';
  end if;

  -- P3: FK compuesta posible.
  if not exists (
    select 1 from pg_constraint
     where conrelid = 'nucleo.tractos'::regclass and contype = 'u'
       and conkey = array[
         (select attnum from pg_attribute
           where attrelid = 'nucleo.tractos'::regclass and attname = 'empresa_id'),
         (select attnum from pg_attribute
           where attrelid = 'nucleo.tractos'::regclass and attname = 'id')]::smallint[]
  ) then
    raise exception 'PRECONDICIÓN P3: nucleo.tractos sin UNIQUE (empresa_id, id)'
      using errcode = '23514';
  end if;
  if not exists (
    select 1 from pg_constraint
     where conrelid = 'nucleo.ramplas'::regclass and contype = 'u'
       and conkey = array[
         (select attnum from pg_attribute
           where attrelid = 'nucleo.ramplas'::regclass and attname = 'empresa_id'),
         (select attnum from pg_attribute
           where attrelid = 'nucleo.ramplas'::regclass and attname = 'id')]::smallint[]
  ) then
    raise exception 'PRECONDICIÓN P3: nucleo.ramplas sin UNIQUE (empresa_id, id)'
      using errcode = '23514';
  end if;
end
$$;

-- ----------------------------------------------------------------------------
-- 1. Pautas de mantenimiento (por empresa y tipo de recurso)
-- ----------------------------------------------------------------------------
create table nucleo.pautas_mantenimiento (
  id              uuid not null default gen_random_uuid(),
  empresa_id      uuid not null,
  recurso_tipo    nucleo.tipo_recurso not null default 'tracto',
  item            text not null,
  intervalo_km    integer not null,
  intervalo_meses integer,
  alerta_km       integer,
  orden           integer not null default 0,
  activo          boolean not null default true,
  created_at      timestamptz not null default now(),
  created_by      text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at      timestamptz not null default now(),
  updated_by      text,
  version         integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_pautas_empresa_id_id unique (empresa_id, id),
  constraint fk_pautas_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  -- El legacy solo tenía tractos; la rampla entra con el mismo mecanismo.
  constraint ck_pauta_recurso_tipo check (recurso_tipo in ('tracto', 'rampla')),
  constraint ck_pauta_item_no_vacio check (btrim(item) <> ''),
  constraint ck_pauta_intervalo_km check (intervalo_km > 0),
  constraint ck_pauta_intervalo_meses check (intervalo_meses is null or intervalo_meses > 0),
  constraint ck_pauta_alerta_km check (alerta_km is null or alerta_km >= 0),
  constraint ck_pauta_orden check (orden >= 0)
);

comment on table nucleo.pautas_mantenimiento is
  'Pauta de mantención preventiva por empresa y tipo de recurso (tracto/rampla). '
  'Origen: public.pautas_mantenimiento (0001:188-196), sin los seeds del legacy: '
  'sus intervalos no tienen fuente documental (P-11). No bloquea el despacho.';
comment on column nucleo.pautas_mantenimiento.intervalo_km is
  'Intervalo en km > 0. `proximo_km = ultimo_km + intervalo_km`.';
comment on column nucleo.pautas_mantenimiento.intervalo_meses is
  'Intervalo calendario (opcional, > 0). Solo se usa para `proxima_fecha` en '
  'v_mantenimiento_estado; el semáforo legacy es por km (P-11 pendiente).';
comment on column nucleo.pautas_mantenimiento.alerta_km is
  'Umbral de aviso en km (>= 0). NULL = usar el default de la empresa '
  '(clave alerta_km_mantenimiento en nucleo.configuracion_empresa) y, mientras '
  'esa clave no exista, 5.000 km (default legacy, 0001:292).';
comment on column nucleo.pautas_mantenimiento.activo is
  'Baja lógica: una pauta inactiva no genera estado ni se puede registrar. '
  'Un ítem puede repetirse solo si el anterior está inactivo (histórico).';

-- Un ítem activo por (empresa, tipo). Los inactivos quedan como historial y
-- permiten recrear el ítem con otro intervalo sin reescribir el pasado.
create unique index uq_pautas_empresa_tipo_item_activa
  on nucleo.pautas_mantenimiento (empresa_id, recurso_tipo, lower(item))
  where activo;

create index idx_pautas_empresa_orden
  on nucleo.pautas_mantenimiento (empresa_id, recurso_tipo, orden)
  where activo;

-- ----------------------------------------------------------------------------
-- 2. Registros de mantención (histórico)
-- ----------------------------------------------------------------------------
create table nucleo.mantenimientos (
  id                      uuid not null default gen_random_uuid(),
  empresa_id              uuid not null,
  tracto_id               uuid,
  rampla_id               uuid,
  pauta_id                uuid not null,
  fecha                   date not null default current_date,
  km                      numeric(12,1) not null,
  costo                   numeric(14,2) not null default 0,
  estado                  text not null default 'realizado',
  motivo_anulacion        text,
  anulada_en              timestamptz,
  anulada_por             text,
  -- Snapshot de la pauta al momento del registro (CN-08 borde).
  intervalo_km_snapshot   integer not null,
  intervalo_meses_snapshot integer,
  alerta_km_snapshot      integer,
  observaciones           text,
  respaldo_url            text,
  created_at              timestamptz not null default now(),
  created_by              text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at              timestamptz not null default now(),
  updated_by              text,
  version                 integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_mantenimientos_empresa_id_id unique (empresa_id, id),
  constraint fk_mantenimiento_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint fk_mantenimiento_pauta foreign key (empresa_id, pauta_id)
    references nucleo.pautas_mantenimiento (empresa_id, id) on delete restrict,
  constraint fk_mantenimiento_tracto foreign key (empresa_id, tracto_id)
    references nucleo.tractos (empresa_id, id) on delete restrict,
  constraint fk_mantenimiento_rampla foreign key (empresa_id, rampla_id)
    references nucleo.ramplas (empresa_id, id) on delete restrict,
  -- Exactamente un recurso: tracto xor rampla.
  constraint ck_mantenimiento_un_recurso check (
    (tracto_id is not null and rampla_id is null)
    or (tracto_id is null and rampla_id is not null)
  ),
  constraint ck_mantenimiento_km check (km >= 0),
  constraint ck_mantenimiento_costo check (costo >= 0),
  constraint ck_mantenimiento_estado check (estado in ('realizado', 'anulado')),
  constraint ck_mantenimiento_anulacion check (
    estado <> 'anulado'
    or (btrim(coalesce(motivo_anulacion, '')) <> ''
        and anulada_en is not null and anulada_por is not null)
  ),
  constraint ck_mantenimiento_snapshot_km check (intervalo_km_snapshot > 0),
  constraint ck_mantenimiento_snapshot_meses check (
    intervalo_meses_snapshot is null or intervalo_meses_snapshot > 0
  ),
  constraint ck_mantenimiento_snapshot_alerta check (
    alerta_km_snapshot is null or alerta_km_snapshot >= 0
  ),
  -- Ruta acotada: relativa, sin `..`, sin esquema ni host (misma idea que
  -- nucleo/storage.py, que acota y valida extensiones por firma).
  constraint ck_mantenimiento_respaldo_url check (
    respaldo_url is null
    or (respaldo_url !~ '^/' and respaldo_url !~ '\.\.'
        and respaldo_url !~ '^[a-zA-Z]+:' and length(respaldo_url) <= 512)
  )
);

comment on table nucleo.mantenimientos is
  'Histórico de mantenciones realizadas por tracto o rampla. Origen: '
  'public.mantenimientos (0001:199-209). No se borra: se anula con motivo. '
  'El costo NO entra al costo del viaje (D-20 abierto).';
comment on column nucleo.mantenimientos.estado is
  'Estado del REGISTRO: realizado | anulado. NO es el semáforo por odómetro '
  '(ese se deriva en nucleo.v_mantenimiento_estado y nunca se almacena).';
comment on column nucleo.mantenimientos.intervalo_km_snapshot is
  'Intervalo de la pauta al registrar. Copia inmutable: editar la pauta no '
  'reescribe el pasado (CN-08 borde).';
comment on column nucleo.mantenimientos.respaldo_url is
  'Ruta relativa del respaldo (boleta/foto) en el bucket `respaldos`; sin `..`, '
  'sin ruta absoluta y <= 512 caracteres.';

create index idx_mantenimientos_tracto
  on nucleo.mantenimientos (empresa_id, tracto_id, km desc, fecha desc)
  where tracto_id is not null;
create index idx_mantenimientos_rampla
  on nucleo.mantenimientos (empresa_id, rampla_id, km desc, fecha desc)
  where rampla_id is not null;
create index idx_mantenimientos_pauta
  on nucleo.mantenimientos (empresa_id, pauta_id, km desc, fecha desc);

-- ----------------------------------------------------------------------------
-- 3. Funciones de trigger nuevas
-- ----------------------------------------------------------------------------

-- Valida coherencia recurso<->pauta, copia el snapshot en INSERT y lo congela
-- en UPDATE. Cualquier violación es 23514 (no 500 en el backend).
create or replace function nucleo.fn_mantenimiento_validar()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
declare
  v_tipo     nucleo.tipo_recurso;
  v_intervalo integer;
  v_meses    integer;
  v_alerta   integer;
begin
  select p.recurso_tipo, p.intervalo_km, p.intervalo_meses, p.alerta_km
    into v_tipo, v_intervalo, v_meses, v_alerta
    from nucleo.pautas_mantenimiento p
   where p.empresa_id = new.empresa_id and p.id = new.pauta_id;

  if not found then
    raise exception 'mantenimiento: la pauta % no existe en la empresa %',
      new.pauta_id, new.empresa_id
      using errcode = '23503';
  end if;

  if v_tipo = 'tracto' and new.rampla_id is not null then
    raise exception 'mantenimiento: la pauta % es de tracto; se envió una rampla',
      new.pauta_id using errcode = '23514';
  end if;
  if v_tipo = 'rampla' and new.tracto_id is not null then
    raise exception 'mantenimiento: la pauta % es de rampla; se envió un tracto',
      new.pauta_id using errcode = '23514';
  end if;

  if tg_op = 'INSERT' then
    if new.intervalo_km_snapshot is null then
      new.intervalo_km_snapshot := v_intervalo;
    elsif new.intervalo_km_snapshot <> v_intervalo then
      raise exception 'mantenimiento: intervalo_km_snapshot (%) no coincide con la pauta (%)',
        new.intervalo_km_snapshot, v_intervalo using errcode = '23514';
    end if;
    if new.intervalo_meses_snapshot is null then
      new.intervalo_meses_snapshot := v_meses;
    end if;
    if new.alerta_km_snapshot is null then
      new.alerta_km_snapshot := v_alerta;
    end if;
  else
    -- Histórico inmutable: el snapshot no se reescribe.
    if new.intervalo_km_snapshot is distinct from old.intervalo_km_snapshot
       or new.intervalo_meses_snapshot is distinct from old.intervalo_meses_snapshot
       or new.alerta_km_snapshot is distinct from old.alerta_km_snapshot then
      raise exception 'mantenimiento: el snapshot de la pauta es inmutable; cree un registro nuevo'
        using errcode = '23514';
    end if;
    if old.estado = 'anulado' and new is distinct from old then
      raise exception 'mantenimiento: un registro anulado es terminal'
        using errcode = '23514';
    end if;
    if new.estado = 'anulado' and old.estado <> 'anulado' then
      new.anulada_en := coalesce(new.anulada_en, now());
      new.anulada_por := coalesce(new.anulada_por, new.updated_by,
        nullif(current_setting('nucleo.auth_id', true), ''), 'sistema');
    end if;
  end if;

  return new;
end;
$$;

comment on function nucleo.fn_mantenimiento_validar() is
  'Coherencia recurso<->pauta, snapshot inmutable del intervalo y terminalidad '
  'del estado anulado en nucleo.mantenimientos.';

-- El histórico no se borra: se anula.
create or replace function nucleo.fn_mantenimiento_no_borrar()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
begin
  raise exception 'mantenimiento: el histórico no se borra; anule con motivo'
    using errcode = '23514';
end;
$$;

comment on function nucleo.fn_mantenimiento_no_borrar() is
  'Bloquea DELETE en nucleo.mantenimientos (23514). El registro se anula.';

-- Sube el odómetro del tracto al km registrado (regla legacy
-- mantenimiento.py:133-135: km_actual = max(km, km_actual)). Nunca lo baja.
create or replace function nucleo.fn_mantenimiento_odometro()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
begin
  if new.tracto_id is not null then
    update nucleo.tractos t
       set km_actual = new.km
     where t.empresa_id = new.empresa_id
       and t.id = new.tracto_id
       and t.km_actual < new.km;
  end if;
  return null;
end;
$$;

comment on function nucleo.fn_mantenimiento_odometro() is
  'AFTER INSERT en mantenimientos: tractos.km_actual = max(km_actual, km del '
  'registro). Nunca reduce el odómetro.';

-- ----------------------------------------------------------------------------
-- 4. Triggers convencionales (touch/version/audit) + propios
-- ----------------------------------------------------------------------------
create trigger trg_pautas_touch
  before update on nucleo.pautas_mantenimiento
  for each row execute function nucleo.fn_touch();
create trigger trg_pautas_version
  before update on nucleo.pautas_mantenimiento
  for each row execute function nucleo.fn_version();
create trigger trg_pautas_audit
  after insert or update or delete on nucleo.pautas_mantenimiento
  for each row execute function nucleo.fn_auditoria();

create trigger trg_mantenimientos_validar
  before insert or update on nucleo.mantenimientos
  for each row execute function nucleo.fn_mantenimiento_validar();
create trigger trg_mantenimientos_no_borrar
  before delete on nucleo.mantenimientos
  for each row execute function nucleo.fn_mantenimiento_no_borrar();
create trigger trg_mantenimientos_odometro
  after insert on nucleo.mantenimientos
  for each row execute function nucleo.fn_mantenimiento_odometro();
create trigger trg_mantenimientos_touch
  before update on nucleo.mantenimientos
  for each row execute function nucleo.fn_touch();
create trigger trg_mantenimientos_version
  before update on nucleo.mantenimientos
  for each row execute function nucleo.fn_version();
create trigger trg_mantenimientos_audit
  after insert or update or delete on nucleo.mantenimientos
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- 5. Vista única del semáforo (no se almacena)
--    `security_invoker` para que RLS de las tablas base aplique al rol que
--    consulta; sin eso la vista correría como su dueño y se saltaría el tenant.
-- ----------------------------------------------------------------------------
create view nucleo.v_mantenimiento_estado
with (security_invoker = true)
as
with recursos as (
  select t.empresa_id, 'tracto'::nucleo.tipo_recurso as recurso_tipo,
         t.id as recurso_id, t.km_actual as odometro
    from nucleo.tractos t
   where t.activo
  union all
  select r.empresa_id, 'rampla'::nucleo.tipo_recurso,
         r.id, null::numeric(12,1)
    from nucleo.ramplas r
   where r.activo
), ultimo as (
  select m.empresa_id, m.pauta_id,
         coalesce(m.tracto_id, m.rampla_id) as recurso_id,
         m.km, m.fecha,
         m.intervalo_km_snapshot, m.intervalo_meses_snapshot, m.alerta_km_snapshot,
         row_number() over (
           partition by m.empresa_id, m.pauta_id, coalesce(m.tracto_id, m.rampla_id)
           order by m.km desc, m.fecha desc, m.id desc
         ) as rn
    from nucleo.mantenimientos m
   where m.estado = 'realizado'
)
select r.empresa_id,
       r.recurso_tipo,
       r.recurso_id,
       p.id   as pauta_id,
       p.item,
       u.km   as ultimo_km,
       u.fecha as ultima_fecha,
       u.intervalo_km_snapshot as intervalo_km,
       u.alerta_km_snapshot    as alerta_km,
       case when u.km is null then null
            else u.km + u.intervalo_km_snapshot end as proximo_km,
       case when u.fecha is null or u.intervalo_meses_snapshot is null then null
            else (u.fecha + make_interval(months => u.intervalo_meses_snapshot))::date
       end as proxima_fecha,
       case when u.km is null or r.odometro is null then null
            else (u.km + u.intervalo_km_snapshot) - r.odometro end as restante_km,
       case
         when u.km is null then 'sin_registro'
         when r.odometro is null then 'sin_odometro'
         when (u.km + u.intervalo_km_snapshot) - r.odometro <= 0 then 'pendiente'
         when (u.km + u.intervalo_km_snapshot) - r.odometro
              <= coalesce(u.alerta_km_snapshot, 5000) then 'por_vencer'
         else 'ok'
       end as estado
  from recursos r
  join nucleo.pautas_mantenimiento p
    on p.empresa_id = r.empresa_id
   and p.recurso_tipo = r.recurso_tipo
   and p.activo
  left join ultimo u
    on u.empresa_id = p.empresa_id
   and u.pauta_id = p.id
   and u.recurso_id = r.recurso_id
   and u.rn = 1;

comment on view nucleo.v_mantenimiento_estado is
  'Única definición del semáforo de mantención: proximo_km = ultimo_km + '
  'intervalo del snapshot; restante <= 0 => pendiente, <= alerta_km => '
  'por_vencer, si no ok; sin registro => sin_registro; sin odómetro (rampla o '
  'tracto sin km) => sin_odometro. No se almacena: se deriva.';

-- ----------------------------------------------------------------------------
-- 6. RLS: ENABLE + FORCE y política de tenant (patrón 0020/0021/0023)
-- ----------------------------------------------------------------------------
alter table nucleo.pautas_mantenimiento enable row level security;
alter table nucleo.pautas_mantenimiento force row level security;
alter table nucleo.mantenimientos enable row level security;
alter table nucleo.mantenimientos force row level security;

drop policy if exists tenant_empresa on nucleo.pautas_mantenimiento;
create policy tenant_empresa on nucleo.pautas_mantenimiento
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

drop policy if exists tenant_empresa on nucleo.mantenimientos;
create policy tenant_empresa on nucleo.mantenimientos
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

-- ----------------------------------------------------------------------------
-- 7. GRANTs (R-6 de ADR-0005: sin GRANT no hay acceso aunque haya política).
--    tei_app lee y escribe; NO borra (baja lógica / anulación).
-- ----------------------------------------------------------------------------
grant select, insert, update on table nucleo.pautas_mantenimiento to tei_app;
grant select, insert, update on table nucleo.mantenimientos to tei_app;
grant select on table nucleo.v_mantenimiento_estado to tei_app;

do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on table nucleo.pautas_mantenimiento from %I', r);
      execute format('revoke all on table nucleo.mantenimientos from %I', r);
      execute format('revoke all on table nucleo.v_mantenimiento_estado from %I', r);
    end if;
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 8. Verificación dentro de la transacción
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  select count(*) into v_n from nucleo.pautas_mantenimiento;
  if v_n <> 0 then
    raise exception 'PRECONDICIÓN P4: pautas sembradas (%); esta migración no siembra', v_n
      using errcode = '23514';
  end if;
  select count(*) into v_n from nucleo.mantenimientos;
  if v_n <> 0 then
    raise exception 'PRECONDICIÓN P4: mantenimientos con % filas; la tabla debe nacer vacía', v_n
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('pautas_mantenimiento', 'mantenimientos')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 2 then
    raise exception 'VERIFICACIÓN: % de 2 tablas con RLS+FORCE', v_n
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('pautas_mantenimiento', 'mantenimientos')
     and policyname = 'tenant_empresa'
     and coalesce(qual, '') like '%ctx_empresa%'
     and coalesce(with_check, '') like '%ctx_empresa%';
  if v_n <> 2 then
    raise exception 'VERIFICACIÓN: % de 2 políticas tenant_empresa con ctx_empresa', v_n
      using errcode = '23514';
  end if;

  if not has_table_privilege('tei_app', 'nucleo.pautas_mantenimiento', 'SELECT')
     or not has_table_privilege('tei_app', 'nucleo.pautas_mantenimiento', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.pautas_mantenimiento', 'UPDATE') then
    raise exception 'VERIFICACIÓN: tei_app sin SELECT/INSERT/UPDATE sobre pautas_mantenimiento'
      using errcode = '23514';
  end if;
  if not has_table_privilege('tei_app', 'nucleo.mantenimientos', 'SELECT')
     or not has_table_privilege('tei_app', 'nucleo.mantenimientos', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.mantenimientos', 'UPDATE') then
    raise exception 'VERIFICACIÓN: tei_app sin SELECT/INSERT/UPDATE sobre mantenimientos'
      using errcode = '23514';
  end if;
  if has_table_privilege('tei_app', 'nucleo.mantenimientos', 'DELETE')
     or has_table_privilege('tei_app', 'nucleo.pautas_mantenimiento', 'DELETE') then
    raise exception 'VERIFICACIÓN: tei_app NO debe tener DELETE en mantenimiento'
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_trigger t join pg_class c on c.oid = t.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and ((c.relname = 'pautas_mantenimiento'
           and t.tgname in ('trg_pautas_touch','trg_pautas_version','trg_pautas_audit'))
       or (c.relname = 'mantenimientos'
           and t.tgname in ('trg_mantenimientos_validar','trg_mantenimientos_no_borrar',
                            'trg_mantenimientos_odometro','trg_mantenimientos_touch',
                            'trg_mantenimientos_version','trg_mantenimientos_audit')))
     and not t.tgisinternal;
  if v_n <> 9 then
    raise exception 'VERIFICACIÓN: se esperaban 9 triggers, hay %', v_n
      using errcode = '23514';
  end if;

  raise notice 'OK 0024: 2 tablas, vista de estado, 9 triggers, RLS+FORCE, 2 políticas, GRANTs; 0 filas';
end
$$;

commit;

-- ============================================================================
-- VERIFICACIÓN POST (ver docs/datos/retiro-legacy-modelo.md §4 y
-- supabase/tests/0024_01_mantenimiento.sql)
--   1) Catálogo: tablas, PK, UNIQUE compuesta, FKs (incl. compuestas), CHECKs,
--      índices, triggers, RLS+FORCE, políticas, ACL.
--   2) Sonda con `tei_app` (0026_02_rls_tei_app.sql, cubre 0024/0025/0026).
--   3) Positivo/violatorio/bordes: costo<0 => 23514; snapshot inmutable;
--      pauta de tracto con rampla => 23514; DELETE => 23514.
-- ============================================================================
