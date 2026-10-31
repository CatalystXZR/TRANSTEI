-- ============================================================================
-- TRANSTEI — Migración 0025: liquidaciones, anticipos y ajustes (Ola B.2)
-- ============================================================================
--
-- OBJETIVO
--   Portar al núcleo la nómina mensual del legacy
--   (`public.liquidaciones`, `public.anticipos_chofer`,
--   `public.ajustes_liquidacion`, `0001:151-186`), que no tiene equivalente:
--   `nucleo.choferes.porcentaje_comision` es un campo, no un módulo.
--
--   Reglas portadas (retiro-legacy-modulos.md §3, RET-07):
--     total_liquido = sueldo_base + comision + bonos - descuentos - anticipos
--   impuesta como columna **generada** (misma técnica que
--   `nucleo.facturas_nucleo.total`, `0013`): el servicio no puede escribir un
--   total que no cuadre con sus componentes (corrige CN-09).
--
--   Correcciones obligatorias al portar (§3.5):
--     1. Redondeo único **HALF_UP**: `nucleo.redondear_half_up()` (el legacy
--        usaba `quantize` sin `rounding` = HALF_EVEN, `liquidaciones.py:95`).
--     2. Documento emitido inmutable: trigger que congela montos, chofer y mes
--        cuando `estado = 'emitida'`; no se borra nada.
--     3. Anticipo/ajuste imputado **una sola vez**: `liquidacion_id` no se
--        cambia ni se limpia una vez fijado (trigger), y el mes de imputación
--        debe coincidir con el de la liquidación.
--     4. Anticipos y ajustes no se borran: se anulan con motivo (el legacy hacía
--        `DELETE` sin rastro, `liquidaciones.py:146-156,206-216`).
--     5. `empresa_id` + FKs compuestas en todas las filas.
--
--   Objetos: 3 tablas, 1 función de cálculo (`redondear_half_up`), 4 funciones
--   de trigger, 12 triggers, RLS+FORCE, 3 políticas `tenant_empresa`, GRANTs a
--   `tei_app` (sin `delete`) y `COMMENT`s. Reutiliza `fn_touch`, `fn_version`,
--   `fn_auditoria` de `0004`.
--
-- NO IMPONE (declarado; lo decide el negocio, no `datos`)
--   · `total_liquido >= 0`: es `D-19`/`P-10` (¿un líquido negativo es deuda del
--     trabajador?). La columna lo permite y el hecho queda auditable.
--   · Composición legal (AFP, salud, cesantía, impuesto único, gratificación):
--     `P-02`. Esta tabla NO es una liquidación de remuneraciones válida.
--   · Arrastre de un anticipo imputado a un mes ya emitido (CN-05, `D-19`). La
--     base impide imputarlo a un mes distinto del declarado y no permite
--     reimputarlo; qué se hace con el huérfano es decisión del dueño.
--   · Que `bonos`/`descuentos`/`anticipos` de la cabecera cuadren con las filas
--     hijas: es un snapshot de emisión, no una suma viva (una liquidación
--     emitida no se recalcula). La regla de cuadre va en el servicio.
--   · Cálculo de la comisión (base facturada del mes, `D-01`): lo hace el
--     servicio con `redondear_half_up`; la base no conoce facturas.
--
-- PRECONDICIONES (detección; abortan con 23514)
--   P1  No existen `nucleo.liquidaciones`, `nucleo.anticipos_chofer` ni
--       `nucleo.ajustes_liquidacion`.
--   P2  `0020` aplicada (ctx_empresa, rol tei_app con USAGE, nucleo.empresas).
--   P3  `nucleo.choferes` tiene `UNIQUE (empresa_id, id)` (FK compuesta).
--   P4  Las 3 tablas nacen vacías (verificado tras el DDL).
--
-- IMPACTO EN DATOS Y LOCKS
--   · Tres `CREATE TABLE` vacías: sin backfill, sin UPDATE/DELETE de datos
--     existentes, sin reescritura. Locks de catálogo por milisegundos.
--   · Índices no concurrentes sobre tablas vacías.
--   · El legacy `public` NO se toca (no se migran filas en esta migración):
--     los datos históricos son la Ola D (ADR-0002) con backup y autorización.
--   · La app actual (rol `postgres`) no cambia: nadie lee estas tablas aún.
--
-- ROLLBACK
--   `supabase/tests/0025_99_rollback.sql`: drop de las 3 tablas y de las 4
--   funciones de trigger + `redondear_half_up`. Pérdida: liquidaciones,
--   anticipos y ajustes creados desde la aplicación (hoy 0 filas). No toca
--   `nucleo.choferes` ni el legacy.
--
-- INVARIANTES (docs/datos/invariantes.md §13)
--   INV-LIQ01  total_liquido = sueldo_base + comision + bonos - descuentos - anticipos
--   INV-LIQ02  Una liquidación emitida no cambia montos, chofer ni mes; no se borra.
--   INV-LIQ03  Un anticipo/ajuste se imputa a lo sumo una vez y al mes declarado.
--   INV-LIQ04  Anticipos y ajustes no se borran: se anulan con motivo.
--   INV-LIQ05  Un solo criterio de redondeo monetario: HALF_UP.
--   INV-LIQ06  Toda fila es invisible/inescribible fuera de `app.empresa_id`.
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  if to_regclass('nucleo.liquidaciones') is not null
     or to_regclass('nucleo.anticipos_chofer') is not null
     or to_regclass('nucleo.ajustes_liquidacion') is not null then
    raise exception 'PRECONDICIÓN P1: ya existe alguna tabla de nómina en nucleo; 0025 no se re-aplica'
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

  if not exists (
    select 1 from pg_constraint
     where conrelid = 'nucleo.choferes'::regclass and contype = 'u'
       and conkey = array[
         (select attnum from pg_attribute
           where attrelid = 'nucleo.choferes'::regclass and attname = 'empresa_id'),
         (select attnum from pg_attribute
           where attrelid = 'nucleo.choferes'::regclass and attname = 'id')]::smallint[]
  ) then
    raise exception 'PRECONDICIÓN P3: nucleo.choferes sin UNIQUE (empresa_id, id)'
      using errcode = '23514';
  end if;
end
$$;

-- ----------------------------------------------------------------------------
-- 1. Redondeo único del dinero: HALF_UP
--    `round(numeric, int)` de PostgreSQL redondea el empate ALEJÁNDOSE DE CERO;
--    para montos positivos es HALF_UP. Se deja una sola definición para que el
--    backend no repita `quantize` con otro criterio (CN-04).
-- ----------------------------------------------------------------------------
create or replace function nucleo.redondear_half_up(
  p_monto numeric,
  p_decimales integer default 2
)
returns numeric
language plpgsql
immutable
strict
set search_path to 'pg_catalog'
as $$
begin
  if p_decimales < 0 or p_decimales > 6 then
    raise exception 'redondear_half_up: decimales fuera de rango (0..6): %', p_decimales
      using errcode = '22023';
  end if;
  return round(p_monto, p_decimales);
end;
$$;

comment on function nucleo.redondear_half_up(numeric, integer) is
  'Redondeo monetario único (HALF_UP para montos positivos). Reemplaza el '
  'HALF_EVEN implícito de `quantize` en liquidaciones.py:95. Inmutable.';

-- ----------------------------------------------------------------------------
-- 2. Liquidación mensual por chofer
-- ----------------------------------------------------------------------------
create table nucleo.liquidaciones (
  id                uuid not null default gen_random_uuid(),
  empresa_id        uuid not null,
  chofer_id         uuid not null,
  mes               text not null,
  sueldo_base       numeric(14,2) not null default 0,
  comision          numeric(14,2) not null default 0,
  bonos             numeric(14,2) not null default 0,
  descuentos        numeric(14,2) not null default 0,
  anticipos         numeric(14,2) not null default 0,
  total_liquido     numeric(14,2)
                    generated always as (sueldo_base + comision + bonos - descuentos - anticipos) stored,
  estado            text not null default 'borrador',
  emitida_en        timestamptz,
  emitida_por       text,
  anulada_en        timestamptz,
  anulada_por       text,
  motivo_anulacion  text,
  notas             text,
  created_at        timestamptz not null default now(),
  created_by        text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at        timestamptz not null default now(),
  updated_by        text,
  version           integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_liquidaciones_empresa_id_id unique (empresa_id, id),
  constraint uq_liquidacion_chofer_mes unique (empresa_id, chofer_id, mes),
  constraint fk_liquidacion_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint fk_liquidacion_chofer foreign key (empresa_id, chofer_id)
    references nucleo.choferes (empresa_id, id) on delete restrict,
  constraint ck_liquidacion_mes check (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  constraint ck_liquidacion_montos check (
    sueldo_base >= 0 and comision >= 0 and bonos >= 0
    and descuentos >= 0 and anticipos >= 0
  ),
  constraint ck_liquidacion_estado check (estado in ('borrador', 'emitida', 'anulada')),
  constraint ck_liquidacion_emision check (
    estado = 'borrador'
    or (emitida_en is not null and btrim(coalesce(emitida_por, '')) <> '')
  ),
  constraint ck_liquidacion_anulacion check (
    estado <> 'anulada'
    or (btrim(coalesce(motivo_anulacion, '')) <> ''
        and anulada_en is not null and btrim(coalesce(anulada_por, '')) <> '')
  )
);

comment on table nucleo.liquidaciones is
  'Nómina mensual por chofer (paridad con public.liquidaciones). NO es una '
  'liquidación de remuneraciones legal: no modela AFP/salud/impuesto (P-02). '
  'Una liquidación emitida es inmutable; se anula con motivo.';
comment on column nucleo.liquidaciones.mes is
  'Mes de la nómina en formato YYYY-MM (texto, como el legacy). No es fecha: '
  'es un período contable, por eso no se usa date.';
comment on column nucleo.liquidaciones.total_liquido is
  'Columna generada = sueldo_base + comision + bonos - descuentos - anticipos. '
  'No se escribe desde la aplicación. Puede ser negativo: D-19/P-10 abiertos.';
comment on column nucleo.liquidaciones.anticipos is
  'Snapshot de los anticipos imputados al emitir. No se recalcula.';

create index idx_liquidaciones_empresa_mes
  on nucleo.liquidaciones (empresa_id, mes, estado);
create index idx_liquidaciones_chofer
  on nucleo.liquidaciones (empresa_id, chofer_id, mes desc);

-- ----------------------------------------------------------------------------
-- 3. Anticipos
-- ----------------------------------------------------------------------------
create table nucleo.anticipos_chofer (
  id                uuid not null default gen_random_uuid(),
  empresa_id        uuid not null,
  chofer_id         uuid not null,
  fecha             date not null default current_date,
  monto             numeric(14,2) not null,
  mes_imputacion    text not null,
  estado            text not null default 'pendiente',
  liquidacion_id    uuid,
  motivo_anulacion  text,
  anulada_en        timestamptz,
  anulada_por       text,
  notas             text,
  created_at        timestamptz not null default now(),
  created_by        text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at        timestamptz not null default now(),
  updated_by        text,
  version           integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_anticipos_empresa_id_id unique (empresa_id, id),
  constraint fk_anticipo_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint fk_anticipo_chofer foreign key (empresa_id, chofer_id)
    references nucleo.choferes (empresa_id, id) on delete restrict,
  constraint fk_anticipo_liquidacion foreign key (empresa_id, liquidacion_id)
    references nucleo.liquidaciones (empresa_id, id) on delete restrict,
  constraint ck_anticipo_monto check (monto > 0),
  constraint ck_anticipo_mes check (mes_imputacion ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  constraint ck_anticipo_estado check (estado in ('pendiente', 'descontado', 'anulado')),
  constraint ck_anticipo_imputado check (estado <> 'descontado' or liquidacion_id is not null),
  constraint ck_anticipo_liquidacion check (
    liquidacion_id is null or estado in ('descontado', 'anulado')
  ),
  constraint ck_anticipo_anulacion check (
    estado <> 'anulado'
    or (btrim(coalesce(motivo_anulacion, '')) <> ''
        and anulada_en is not null and btrim(coalesce(anulada_por, '')) <> '')
  )
);

comment on table nucleo.anticipos_chofer is
  'Anticipos de sueldo (paridad con public.anticipos_chofer). No se borran: se '
  'anulan con motivo. Un anticipo se imputa a lo sumo a una liquidación.';
comment on column nucleo.anticipos_chofer.mes_imputacion is
  'Mes YYYY-MM al que se descuenta. Debe coincidir con liquidaciones.mes del '
  'anticipo imputado (trigger). El arrastre de un mes cerrado es D-19.';
comment on column nucleo.anticipos_chofer.liquidacion_id is
  'Liquidación que lo descuenta. Inmutable una vez fijado: no se reimputa.';

create index idx_anticipos_empresa_mes
  on nucleo.anticipos_chofer (empresa_id, mes_imputacion, estado);
create index idx_anticipos_chofer
  on nucleo.anticipos_chofer (empresa_id, chofer_id, fecha desc);

-- ----------------------------------------------------------------------------
-- 4. Ajustes (bonos y descuentos)
-- ----------------------------------------------------------------------------
create table nucleo.ajustes_liquidacion (
  id                uuid not null default gen_random_uuid(),
  empresa_id        uuid not null,
  chofer_id         uuid not null,
  mes               text not null,
  tipo              text not null,
  concepto          text not null,
  monto             numeric(14,2) not null,
  estado            text not null default 'vigente',
  liquidacion_id    uuid,
  motivo_anulacion  text,
  anulada_en        timestamptz,
  anulada_por       text,
  created_at        timestamptz not null default now(),
  created_by        text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at        timestamptz not null default now(),
  updated_by        text,
  version           integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_ajustes_empresa_id_id unique (empresa_id, id),
  constraint fk_ajuste_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint fk_ajuste_chofer foreign key (empresa_id, chofer_id)
    references nucleo.choferes (empresa_id, id) on delete restrict,
  constraint fk_ajuste_liquidacion foreign key (empresa_id, liquidacion_id)
    references nucleo.liquidaciones (empresa_id, id) on delete restrict,
  constraint ck_ajuste_mes check (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  constraint ck_ajuste_tipo check (tipo in ('bono', 'descuento')),
  constraint ck_ajuste_concepto check (btrim(concepto) <> ''),
  -- El legacy permitía 0 (0001:168). Se conserva la paridad; el servicio puede
  -- exigir > 0 sin que la base invente una regla.
  constraint ck_ajuste_monto check (monto >= 0),
  constraint ck_ajuste_estado check (estado in ('vigente', 'anulado')),
  constraint ck_ajuste_anulacion check (
    estado <> 'anulado'
    or (btrim(coalesce(motivo_anulacion, '')) <> ''
        and anulada_en is not null and btrim(coalesce(anulada_por, '')) <> '')
  )
);

comment on table nucleo.ajustes_liquidacion is
  'Bonos y descuentos imputables a un mes de nómina (paridad con '
  'public.ajustes_liquidacion). No se borran: se anulan con motivo.';
comment on column nucleo.ajustes_liquidacion.monto is
  'Monto >= 0; el signo lo aporta `tipo` (bono suma, descuento resta). Paridad '
  'con el legacy, que aceptaba 0.';

create index idx_ajustes_empresa_mes
  on nucleo.ajustes_liquidacion (empresa_id, mes, estado);
create index idx_ajustes_chofer
  on nucleo.ajustes_liquidacion (empresa_id, chofer_id, mes);

-- ----------------------------------------------------------------------------
-- 5. Funciones de trigger
-- ----------------------------------------------------------------------------

-- Máquina de estados de la liquidación + inmutabilidad del documento emitido.
create or replace function nucleo.fn_liquidacion_estado()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
begin
  if tg_op = 'INSERT' then
    if new.estado = 'anulada' then
      raise exception 'liquidación: nace borrador o emitida; no se inserta anulada'
        using errcode = '23514';
    end if;
    if new.estado = 'emitida' then
      new.emitida_en := coalesce(new.emitida_en, now());
      new.emitida_por := coalesce(
        nullif(btrim(coalesce(new.emitida_por, '')), ''),
        nullif(current_setting('nucleo.auth_id', true), ''),
        new.created_by, 'sistema');
    end if;
    return new;
  end if;

  if new.empresa_id is distinct from old.empresa_id then
    raise exception 'liquidación: empresa_id es inmutable'
      using errcode = '23514';
  end if;
  if old.estado = 'anulada' then
    raise exception 'liquidación: una liquidación anulada es terminal; cree un documento nuevo'
      using errcode = '23514';
  end if;

  if old.estado = 'emitida' then
    if new.estado not in ('emitida', 'anulada') then
      raise exception 'liquidación: una liquidación emitida no vuelve a %', new.estado
        using errcode = '23514';
    end if;
    if new.chofer_id is distinct from old.chofer_id
       or new.mes is distinct from old.mes
       or new.sueldo_base is distinct from old.sueldo_base
       or new.comision is distinct from old.comision
       or new.bonos is distinct from old.bonos
       or new.descuentos is distinct from old.descuentos
       or new.anticipos is distinct from old.anticipos then
      raise exception 'liquidación: emitida es inmutable en montos, chofer y mes (INV-LIQ02)'
        using errcode = '23514';
    end if;
  end if;

  if new.estado = 'emitida' and old.estado = 'borrador' then
    new.emitida_en := coalesce(old.emitida_en, now());
    new.emitida_por := coalesce(
      nullif(btrim(coalesce(old.emitida_por, '')), ''),
      nullif(current_setting('nucleo.auth_id', true), ''),
      new.updated_by, 'sistema');
  end if;

  if new.estado = 'anulada' and old.estado <> 'anulada' then
    if btrim(coalesce(new.motivo_anulacion, '')) = '' then
      raise exception 'liquidación: anular exige motivo_anulacion'
        using errcode = '23514';
    end if;
    new.anulada_en := coalesce(new.anulada_en, now());
    new.anulada_por := coalesce(
      nullif(btrim(coalesce(new.anulada_por, '')), ''),
      nullif(current_setting('nucleo.auth_id', true), ''),
      new.updated_by, 'sistema');
  end if;

  return new;
end;
$$;

comment on function nucleo.fn_liquidacion_estado() is
  'borrador -> emitida -> anulada. Congela montos/chofer/mes al emitir y hace '
  'terminal el estado anulado. 23514 en toda violación.';

-- Validación común de imputación (anticipos y ajustes), por `to_jsonb` para
-- tolerar que el nombre del mes difiera entre tablas.
create or replace function nucleo.fn_imputacion_validar()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
declare
  v_mes          text;
  v_liq_mes      text;
  v_liq_estado   text;
  v_old_liq      uuid;
  v_old_estado   text;
  v_reg          jsonb := to_jsonb(new);
begin
  v_mes := coalesce(v_reg->>'mes_imputacion', v_reg->>'mes');

  if tg_op = 'UPDATE' then
    v_old_liq := old.liquidacion_id;
    v_old_estado := old.estado;
    -- Imputación única: una vez fijada la liquidación, no se cambia ni se limpia.
    if v_old_liq is not null and new.liquidacion_id is distinct from v_old_liq then
      raise exception '%: ya imputado a la liquidación %; no se reimputa (INV-LIQ03)',
        tg_table_name, v_old_liq
        using errcode = '23514';
    end if;
  end if;

  if new.liquidacion_id is not null then
    select l.mes, l.estado into v_liq_mes, v_liq_estado
      from nucleo.liquidaciones l
     where l.empresa_id = new.empresa_id and l.id = new.liquidacion_id;
    if not found then
      raise exception '%: la liquidación % no existe en la empresa %',
        tg_table_name, new.liquidacion_id, new.empresa_id
        using errcode = '23503';
    end if;
    if v_liq_estado = 'anulada' then
      raise exception '%: no se imputa a una liquidación anulada', tg_table_name
        using errcode = '23514';
    end if;
    if v_mes is distinct from v_liq_mes then
      raise exception '%: el mes declarado (%) no coincide con la liquidación (%)',
        tg_table_name, v_mes, v_liq_mes
        using errcode = '23514';
    end if;
  end if;

  if new.estado = 'anulado' and v_old_estado is distinct from 'anulado' then
    if btrim(coalesce(new.motivo_anulacion, '')) = '' then
      raise exception '%: anular exige motivo_anulacion', tg_table_name
        using errcode = '23514';
    end if;
    new.anulada_en := coalesce(new.anulada_en, now());
    new.anulada_por := coalesce(
      nullif(btrim(coalesce(new.anulada_por, '')), ''),
      nullif(current_setting('nucleo.auth_id', true), ''), 'sistema');
  end if;

  return new;
end;
$$;

comment on function nucleo.fn_imputacion_validar() is
  'Anticipos/ajustes: imputación única, mes coherente con la liquidación y '
  'anulación con motivo + sello. 23514/23503.';

-- El histórico de nómina no se borra.
create or replace function nucleo.fn_nomina_no_borrar()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
begin
  raise exception '%: no se borra; anule con motivo (INV-LIQ04)', tg_table_name
    using errcode = '23514';
end;
$$;

comment on function nucleo.fn_nomina_no_borrar() is
  'Bloquea DELETE en liquidaciones/anticipos/ajustes (23514).';

-- ----------------------------------------------------------------------------
-- 6. Triggers
-- ----------------------------------------------------------------------------
create trigger trg_liquidaciones_estado
  before insert or update on nucleo.liquidaciones
  for each row execute function nucleo.fn_liquidacion_estado();
create trigger trg_liquidaciones_no_borrar
  before delete on nucleo.liquidaciones
  for each row execute function nucleo.fn_nomina_no_borrar();
create trigger trg_liquidaciones_touch
  before update on nucleo.liquidaciones
  for each row execute function nucleo.fn_touch();
create trigger trg_liquidaciones_version
  before update on nucleo.liquidaciones
  for each row execute function nucleo.fn_version();
create trigger trg_liquidaciones_audit
  after insert or update or delete on nucleo.liquidaciones
  for each row execute function nucleo.fn_auditoria();

create trigger trg_anticipos_validar
  before insert or update on nucleo.anticipos_chofer
  for each row execute function nucleo.fn_imputacion_validar();
create trigger trg_anticipos_no_borrar
  before delete on nucleo.anticipos_chofer
  for each row execute function nucleo.fn_nomina_no_borrar();
create trigger trg_anticipos_touch
  before update on nucleo.anticipos_chofer
  for each row execute function nucleo.fn_touch();
create trigger trg_anticipos_version
  before update on nucleo.anticipos_chofer
  for each row execute function nucleo.fn_version();
create trigger trg_anticipos_audit
  after insert or update or delete on nucleo.anticipos_chofer
  for each row execute function nucleo.fn_auditoria();

create trigger trg_ajustes_validar
  before insert or update on nucleo.ajustes_liquidacion
  for each row execute function nucleo.fn_imputacion_validar();
create trigger trg_ajustes_no_borrar
  before delete on nucleo.ajustes_liquidacion
  for each row execute function nucleo.fn_nomina_no_borrar();
create trigger trg_ajustes_touch
  before update on nucleo.ajustes_liquidacion
  for each row execute function nucleo.fn_touch();
create trigger trg_ajustes_version
  before update on nucleo.ajustes_liquidacion
  for each row execute function nucleo.fn_version();
create trigger trg_ajustes_audit
  after insert or update or delete on nucleo.ajustes_liquidacion
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- 7. RLS + políticas
-- ----------------------------------------------------------------------------
alter table nucleo.liquidaciones enable row level security;
alter table nucleo.liquidaciones force row level security;
alter table nucleo.anticipos_chofer enable row level security;
alter table nucleo.anticipos_chofer force row level security;
alter table nucleo.ajustes_liquidacion enable row level security;
alter table nucleo.ajustes_liquidacion force row level security;

drop policy if exists tenant_empresa on nucleo.liquidaciones;
create policy tenant_empresa on nucleo.liquidaciones
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

drop policy if exists tenant_empresa on nucleo.anticipos_chofer;
create policy tenant_empresa on nucleo.anticipos_chofer
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

drop policy if exists tenant_empresa on nucleo.ajustes_liquidacion;
create policy tenant_empresa on nucleo.ajustes_liquidacion
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

-- ----------------------------------------------------------------------------
-- 8. GRANTs (R-6 ADR-0005). Sin `delete`: el rastro no se borra.
--    El salario es dato sensible: `anon`/`authenticated` no reciben nada.
-- ----------------------------------------------------------------------------
grant select, insert, update on table nucleo.liquidaciones to tei_app;
grant select, insert, update on table nucleo.anticipos_chofer to tei_app;
grant select, insert, update on table nucleo.ajustes_liquidacion to tei_app;

do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on table nucleo.liquidaciones from %I', r);
      execute format('revoke all on table nucleo.anticipos_chofer from %I', r);
      execute format('revoke all on table nucleo.ajustes_liquidacion from %I', r);
    end if;
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 9. Verificación en la transacción
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  select count(*) into v_n from nucleo.liquidaciones;
  if v_n <> 0 then
    raise exception 'PRECONDICIÓN P4: liquidaciones con % filas; debe nacer vacía', v_n
      using errcode = '23514';
  end if;
  select count(*) into v_n from nucleo.anticipos_chofer;
  if v_n <> 0 then
    raise exception 'PRECONDICIÓN P4: anticipos con % filas; debe nacer vacía', v_n
      using errcode = '23514';
  end if;
  select count(*) into v_n from nucleo.ajustes_liquidacion;
  if v_n <> 0 then
    raise exception 'PRECONDICIÓN P4: ajustes con % filas; debe nacer vacía', v_n
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('liquidaciones', 'anticipos_chofer', 'ajustes_liquidacion')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 3 then
    raise exception 'VERIFICACIÓN: % de 3 tablas con RLS+FORCE', v_n
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('liquidaciones', 'anticipos_chofer', 'ajustes_liquidacion')
     and policyname = 'tenant_empresa'
     and coalesce(qual, '') like '%ctx_empresa%'
     and coalesce(with_check, '') like '%ctx_empresa%';
  if v_n <> 3 then
    raise exception 'VERIFICACIÓN: % de 3 políticas tenant_empresa', v_n
      using errcode = '23514';
  end if;

  if not has_table_privilege('tei_app', 'nucleo.liquidaciones', 'SELECT')
     or not has_table_privilege('tei_app', 'nucleo.liquidaciones', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.liquidaciones', 'UPDATE')
     or not has_table_privilege('tei_app', 'nucleo.anticipos_chofer', 'SELECT')
     or not has_table_privilege('tei_app', 'nucleo.anticipos_chofer', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.anticipos_chofer', 'UPDATE')
     or not has_table_privilege('tei_app', 'nucleo.ajustes_liquidacion', 'SELECT')
     or not has_table_privilege('tei_app', 'nucleo.ajustes_liquidacion', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.ajustes_liquidacion', 'UPDATE') then
    raise exception 'VERIFICACIÓN: tei_app sin SELECT/INSERT/UPDATE en nómina'
      using errcode = '23514';
  end if;
  if has_table_privilege('tei_app', 'nucleo.liquidaciones', 'DELETE')
     or has_table_privilege('tei_app', 'nucleo.anticipos_chofer', 'DELETE')
     or has_table_privilege('tei_app', 'nucleo.ajustes_liquidacion', 'DELETE') then
    raise exception 'VERIFICACIÓN: tei_app NO debe tener DELETE en nómina'
      using errcode = '23514';
  end if;

  -- La columna total_liquido debe ser generada, no escribible.
  select count(*) into v_n
    from pg_attribute
   where attrelid = 'nucleo.liquidaciones'::regclass
     and attname = 'total_liquido'
     and attgenerated = 's';
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: total_liquido no es columna generada'
      using errcode = '23514';
  end if;

  raise notice 'OK 0025: 3 tablas, total generado, 15 triggers, RLS+FORCE, 3 políticas, GRANTs; 0 filas';
end
$$;

commit;

-- ============================================================================
-- VERIFICACIÓN POST: supabase/tests/0025_01_liquidaciones.sql,
-- 0025_02_concurrencia_anticipo.py y 0026_02_rls_tei_app.sql.
-- ============================================================================
