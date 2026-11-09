-- ============================================================================
-- TRANSTEI — Migración 0030: configuración de tenant por entidad y suscripciones
-- ============================================================================
--
-- OBJETIVO
--   Implementar el Apéndice A del ADR-0008 (config de tenant y autoridad de
--   estados) en su parte NO condicional:
--     1. `nucleo.tipo_entidad_regla` (enum) + `nucleo.tenant_reglas_entidad`:
--        reglas por empresa y por entidad concreta (cliente, chofer, tracto,
--        rampla, contacto), tipadas en jsonb y versionadas por vigencia.
--     2. `nucleo.tenant_suscripciones`: suscripción comercial por empresa y
--        plan, con vigencia. Solo `plan_codigo`/`estado`; NO precio, moneda,
--        cupos, `limites jsonb` ni `habilitado` (A.4 y `D-25`/`D-26`).
--
--   `tenant_config` NO se crea: el ADR-0008 (§B.0) concluyó que duplicaría
--   `nucleo.configuracion_empresa` y reabriría una segunda fuente de verdad.
--   `tenant_config` es una vista de solo lectura en el ADR; aquí no se crea.
--
--   Por qué una tabla aparte de `configuracion_empresa` (0026): la regla por
--   entidad necesita integridad referencial a la entidad concreta. El
--   polimorfismo queda resuelto con 5 FKs nullable + un CHECK de coherencia,
--   no con un `entidad_id uuid` sin FK (A.3, B.2).
--
-- OBJETOS
--   · enum  nucleo.tipo_entidad_regla ('cliente','chofer','tracto','rampla','contacto')
--   · tabla nucleo.tenant_reglas_entidad
--       - UNIQUE (empresa_id, id) y FK simple a nucleo.empresas (RESTRICT)
--       - 5 FKs compuestas (empresa_id, <fk>_id) → tabla destino (empresa_id, id)
--         ON DELETE RESTRICT
--       - ck_regla_una_entidad: exactamente una FK no nula y coherente con `entidad`
--       - ck_regla_vigencia, ck_regla_clave_formato
--       - EXCLUDE gist con expresiones centinela (9 claves) y
--         UNIQUE parcial uq_regla_vigente (fila abierta)
--   · tabla nucleo.tenant_suscripciones
--       - UNIQUE (empresa_id, id), FK a empresas (RESTRICT)
--       - ck_suscripcion_estado, ck_suscripcion_plan_formato, ck_suscripcion_vigencia
--       - EXCLUDE gist (empresa_id, plan_codigo, rango) y UNIQUE parcial de vigente
--   · función  nucleo.fn_regla_entidad_inmutable()
--   · 4 triggers en tenant_reglas_entidad (inmutable, touch, version, audit)
--   · 3 triggers en tenant_suscripciones (touch, version, audit)
--   · RLS ENABLE + FORCE, política `tenant_empresa`, GRANTs (tei_app sin DELETE),
--     revocaciones a anon/authenticated, COMMENTs
--
-- REQUISITO DE ORDEN
--   Después de `0004` (btree_gist, fn_touch/fn_version/fn_auditoria), `0020`
--   (rol `tei_app`, `nucleo.ctx_empresa()`), `0026` (configuración por empresa)
--   y `0029` (separación `tei_admin`). No depende de `0029` para funcionar.
--
-- PRECONDICIONES (Apéndice A.2; abortan con 23514 y no crean nada)
--   P1  Estado parcial: si existe SOLO una de las dos tablas, aborta. Si existen
--       ambas, la migración es re-ejecutable (NOTICE) y no duplica objetos.
--   P2  `nucleo.ctx_empresa()` existe; rol `tei_app` existe y tiene USAGE sobre
--       `nucleo`.
--   P3  Extensión `btree_gist` instalada (la exigen los dos EXCLUDE).
--   P4  `nucleo.empresas` y `nucleo.configuracion_empresa` existen.
--   P5  `nucleo.modulos_empresa` existe (el flag de módulo NO se reimplementa).
--   P6  `select count(*) from nucleo.empresas where estado <> 'activa'` es
--       informativo (NOTICE), no aborta.
--   P7  Las 5 tablas destino tienen UNIQUE (empresa_id, id); sin eso las FKs
--       compuestas no compilan y se reporta cuáles faltan.
--
-- IMPACTO EN DATOS Y LOCKS
--   · `CREATE TYPE`, `CREATE TABLE` vacía, índices, triggers y GRANTs: no hay
--     filas de negocio que migrar. La migración NO siembra reglas ni
--     suscripciones.
--   · Los `CREATE TABLE`/`CREATE INDEX` toman locks sobre objetos NUEVOS: no
--     bloquean `empresas`, `clientes`, `choferes`, `tractos`, `ramplas` ni
--     `contactos_whatsapp`, solo agregan FKs que apuntan a ellos (sin
--     reescritura de esas tablas).
--   · `ALTER TABLE ... ENABLE/FORCE RLS` y `CREATE POLICY` sobre tablas nuevas:
--     instantáneo.
--   · Ningún escritor actual conoce estas tablas: el backend y el frontend
--     siguen funcionando (no se modifica ningún contrato HTTP).
--   · `nucleo.modulos_empresa` y `nucleo.configuracion_empresa` NO se tocan.
--
-- COMPATIBILIDAD
--   · No cambia columnas, constraints ni permisos de tablas existentes.
--   · `tei_app` recibe SELECT/INSERT/UPDATE sobre las tablas nuevas; el código
--     actual no las consulta, así que el cambio es aditivo.
--
-- LO QUE ESTA MIGRACIÓN NO IMPONE (y no debe fingir)
--   · Qué claves de regla existen y qué forma tiene `valor`: el catálogo es del
--     servicio (`D-27`). La base solo acota `clave` por formato y exige jsonb.
--   · Qué es un "plan", su precio, moneda, periodicidad, cupos o límites:
--     `D-25`/`D-26` (dueño + contador). Por eso esas columnas NO existen.
--   · Que un estado de suscripción apague módulos: el único gate sigue siendo
--     `nucleo.modulos_empresa.habilitado` + `empresas.estado` (ADR-0008 Ap. C.1).
--   · Cierre automático de vigencia de suscripciones: no hay historial decidido
--     (`D-25`); el cambio se hace cerrando a mano e insertando una fila nueva.
--   · Inmutabilidad de `tenant_suscripciones`: el contrato A.5 no la pide; el
--     DELETE queda reservado al rol de plataforma (`postgres`).
--   · Inmutabilidad de una regla **abierta**: mientras `vigente_hasta IS NULL`
--     se pueden editar `valor`, las FKs y `clave`. El contrato A.3/A.5 solo
--     congela la fila cerrada.
--   · Aislamiento efectivo con el rol desplegado: probado con `tei_app`
--     (NOBYPASSRLS) en `supabase/tests/0030_03_rls_tei_app.sql`. Si el runtime
--     conecta con un rol BYPASSRLS, RLS es inerte (`R-10`).
--
-- ROLLBACK
--   `supabase/tests/0030_99_rollback.sql`: drop de triggers, tablas, función
--   nueva y enum. Pérdida: las reglas y suscripciones escritas (ninguna al
--   aplicar). `empresas`, `configuracion_empresa`, `modulos_empresa`, las
--   tablas de entidades y `nucleo.auditoria` NO se tocan.
--   La migración es re-ejecutable tras el rollback (NO se edita una migración
--   ya aplicada: se crea la siguiente; esto solo permite el ciclo local).
--
-- INVARIANTES (docs/datos/invariantes.md §14)
--   INV-TEN01  Una regla tiene exactamente una entidad destino y es coherente
--              con `entidad`.
--   INV-TEN02  La entidad destino pertenece a la misma empresa que la regla.
--   INV-TEN03  No hay dos reglas de la misma (empresa, entidad, clave, destino)
--              con vigencias solapadas.
--   INV-TEN04  A lo sumo una regla abierta por (empresa, entidad, clave, destino).
--   INV-TEN05  Una regla cerrada es historial inmutable; las reglas no se borran.
--   INV-TEN06  No hay dos suscripciones solapadas por (empresa, plan).
--   INV-TEN07  A lo sumo una suscripción abierta por (empresa, plan).
--   INV-TEN08  `estado` de suscripción ∈ {activa, suspendida, cancelada}.
--   INV-TEN09  Toda fila es invisible/inescribible fuera de `app.empresa_id`.
--   INV-TEN10  `tei_app` no puede borrar reglas ni suscripciones (42501).
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones (P1–P7)
-- ----------------------------------------------------------------------------
do $$
declare
  v_reglas   regclass := to_regclass('nucleo.tenant_reglas_entidad');
  v_susc     regclass := to_regclass('nucleo.tenant_suscripciones');
  v_n        integer;
  v_faltan   text;
begin
  -- P1: estado parcial prohibido; si ambas existen, es re-ejecución idempotente.
  if (v_reglas is null) <> (v_susc is null) then
    raise exception 'PRECONDICIÓN P1: estado parcial (reglas=%, suscripciones=%); 0030 no continúa',
      v_reglas, v_susc
      using errcode = '23514';
  end if;
  if v_reglas is not null then
    raise notice 'PRECONDICIÓN P1: 0030 ya aplicada; se re-verifica sin duplicar objetos';
  end if;

  -- P2: ctx_empresa, rol tei_app y USAGE.
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

  -- P3: btree_gist.
  if not exists (select 1 from pg_extension where extname = 'btree_gist') then
    raise exception 'PRECONDICIÓN P3: falta la extensión btree_gist (EXCLUDE)'
      using errcode = '23514';
  end if;

  -- P4 / P5.
  if to_regclass('nucleo.empresas') is null then
    raise exception 'PRECONDICIÓN P4: falta nucleo.empresas'
      using errcode = '23514';
  end if;
  if to_regclass('nucleo.configuracion_empresa') is null then
    raise exception 'PRECONDICIÓN P4: falta nucleo.configuracion_empresa; aplicar 0026 primero'
      using errcode = '23514';
  end if;
  if to_regclass('nucleo.modulos_empresa') is null then
    raise exception 'PRECONDICIÓN P5: falta nucleo.modulos_empresa (el flag no se reimplementa)'
      using errcode = '23514';
  end if;

  -- P7: UNIQUE (empresa_id, id) en las 5 tablas destino.
  select string_agg(t.nombre, ', ' order by t.nombre) into v_faltan
    from (values ('clientes'), ('choferes'), ('tractos'), ('ramplas'),
                 ('contactos_whatsapp')) as t(nombre)
   where not exists (
     select 1
       from pg_constraint c
      where c.conrelid = to_regclass('nucleo.' || t.nombre)
        and c.contype = 'u'
        and (
          select array_agg(a.attname order by a.attname)
            from unnest(c.conkey) as k(attnum)
            join pg_attribute a
              on a.attrelid = c.conrelid and a.attnum = k.attnum
        ) = array['empresa_id', 'id']::name[]
   );
  if v_faltan is not null then
    raise exception 'PRECONDICIÓN P7: sin UNIQUE (empresa_id, id): %', v_faltan
      using errcode = '23514';
  end if;

  -- P6: informativo.
  select count(*) into v_n from nucleo.empresas where estado <> 'activa';
  raise notice 'PRECONDICIÓN P6: % empresa(s) no activas (informativo)', v_n;
end
$$;

-- ----------------------------------------------------------------------------
-- 1. Enum
-- ----------------------------------------------------------------------------
do $$
begin
  if not exists (
    select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
     where n.nspname = 'nucleo' and t.typname = 'tipo_entidad_regla'
  ) then
    create type nucleo.tipo_entidad_regla as enum
      ('cliente', 'chofer', 'tracto', 'rampla', 'contacto');
  end if;
end
$$;

comment on type nucleo.tipo_entidad_regla is
  'Entidad destino de una regla de tenant. Agregar un valor exige migración Y '
  'una columna FK nueva en tenant_reglas_entidad (evita polimorfismo sin integridad).';

-- ----------------------------------------------------------------------------
-- 2. tenant_reglas_entidad
-- ----------------------------------------------------------------------------
create table if not exists nucleo.tenant_reglas_entidad (
  id             uuid not null default gen_random_uuid(),
  empresa_id     uuid not null,
  entidad        nucleo.tipo_entidad_regla not null,
  cliente_id     uuid,
  chofer_id      uuid,
  tracto_id      uuid,
  rampla_id      uuid,
  contacto_id    uuid,
  clave          text not null,
  valor          jsonb not null,
  vigente_desde  timestamptz not null default now(),
  vigente_hasta  timestamptz,
  created_at     timestamptz not null default now(),
  created_by     text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at     timestamptz not null default now(),
  updated_by     text,
  version        integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_reglas_entidad_empresa_id unique (empresa_id, id),
  constraint fk_reglas_entidad_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint fk_reglas_entidad_cliente foreign key (empresa_id, cliente_id)
    references nucleo.clientes (empresa_id, id) on delete restrict,
  constraint fk_reglas_entidad_chofer foreign key (empresa_id, chofer_id)
    references nucleo.choferes (empresa_id, id) on delete restrict,
  constraint fk_reglas_entidad_tracto foreign key (empresa_id, tracto_id)
    references nucleo.tractos (empresa_id, id) on delete restrict,
  constraint fk_reglas_entidad_rampla foreign key (empresa_id, rampla_id)
    references nucleo.ramplas (empresa_id, id) on delete restrict,
  constraint fk_reglas_entidad_contacto foreign key (empresa_id, contacto_id)
    references nucleo.contactos_whatsapp (empresa_id, id) on delete restrict,
  constraint ck_regla_clave_formato check (clave ~ '^[a-z][a-z0-9_]{2,63}$'),
  constraint ck_regla_vigencia check (
    vigente_hasta is null or vigente_hasta > vigente_desde
  ),
  -- Exactamente una entidad destino, y coherente con el enum `entidad`.
  constraint ck_regla_una_entidad check (
    num_nonnulls(cliente_id, chofer_id, tracto_id, rampla_id, contacto_id) = 1
    and (entidad <> 'cliente'  or cliente_id  is not null)
    and (entidad <> 'chofer'   or chofer_id   is not null)
    and (entidad <> 'tracto'   or tracto_id   is not null)
    and (entidad <> 'rampla'   or rampla_id   is not null)
    and (entidad <> 'contacto' or contacto_id is not null)
  ),
  -- Sobre columnas nullable un EXCLUDE no detectaría solapes: se usa una
  -- expresión centinela por cada FK (Apéndice A.3). El rango es semiabierto
  -- [vigente_desde, vigente_hasta) y NULL en el extremo = abierto.
  constraint ex_regla_vigencia exclude using gist (
    empresa_id with =,
    entidad with =,
    clave with =,
    (coalesce(cliente_id,  '00000000-0000-0000-0000-000000000000'::uuid)) with =,
    (coalesce(chofer_id,   '00000000-0000-0000-0000-000000000000'::uuid)) with =,
    (coalesce(tracto_id,   '00000000-0000-0000-0000-000000000000'::uuid)) with =,
    (coalesce(rampla_id,   '00000000-0000-0000-0000-000000000000'::uuid)) with =,
    (coalesce(contacto_id, '00000000-0000-0000-0000-000000000000'::uuid)) with =,
    tstzrange(vigente_desde, vigente_hasta, '[)') with &&
  )
);

comment on table nucleo.tenant_reglas_entidad is
  'Reglas por empresa y por entidad concreta, tipadas en jsonb y versionadas por '
  'vigencia. Un cambio = cerrar vigente_hasta e insertar una fila nueva; una fila '
  'cerrada es historia inmutable y no se borra.';
comment on column nucleo.tenant_reglas_entidad.entidad is
  'Tipo de entidad destino; debe coincidir con la única FK no nula '
  '(ck_regla_una_entidad).';
comment on column nucleo.tenant_reglas_entidad.clave is
  'Identificador estable de la regla (minúsculas). El catálogo y los tipos viven '
  'en el servicio; la base solo acota el formato.';
comment on column nucleo.tenant_reglas_entidad.valor is
  'Valor tipado en jsonb. La base no valida su forma: no existe catálogo en base '
  '(D-27).';
comment on column nucleo.tenant_reglas_entidad.vigente_desde is
  'Inicio de vigencia (UTC). Se toma al insertar; no se edita en una fila cerrada.';
comment on column nucleo.tenant_reglas_entidad.vigente_hasta is
  'Fin de vigencia (UTC), exclusivo. NULL = vigente. Una vez fijado no se edita '
  'ni se limpia: la fila pasa a ser historial inmutable.';

-- Una sola fila abierta por (empresa, entidad, clave, destino). El EXCLUDE ya
-- lo impide; este índice da el error explícito 23505 para el caso normal.
create unique index if not exists uq_regla_vigente
  on nucleo.tenant_reglas_entidad (
    empresa_id, entidad, clave,
    (coalesce(cliente_id,  '00000000-0000-0000-0000-000000000000'::uuid)),
    (coalesce(chofer_id,   '00000000-0000-0000-0000-000000000000'::uuid)),
    (coalesce(tracto_id,   '00000000-0000-0000-0000-000000000000'::uuid)),
    (coalesce(rampla_id,   '00000000-0000-0000-0000-000000000000'::uuid)),
    (coalesce(contacto_id, '00000000-0000-0000-0000-000000000000'::uuid))
  )
  where vigente_hasta is null;

create index if not exists idx_reglas_entidad_lookup
  on nucleo.tenant_reglas_entidad (empresa_id, entidad, clave, vigente_desde desc);

-- ----------------------------------------------------------------------------
-- 3. tenant_suscripciones
-- ----------------------------------------------------------------------------
create table if not exists nucleo.tenant_suscripciones (
  id                 uuid not null default gen_random_uuid(),
  empresa_id         uuid not null,
  plan_codigo        text not null,
  estado             text not null default 'activa',
  referencia_externa text,
  vigente_desde      timestamptz not null default now(),
  vigente_hasta      timestamptz,
  created_at         timestamptz not null default now(),
  created_by         text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at         timestamptz not null default now(),
  updated_by         text,
  version            integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_suscripciones_empresa_id unique (empresa_id, id),
  constraint fk_suscripciones_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint ck_suscripcion_plan_formato check (plan_codigo ~ '^[a-z][a-z0-9_-]{2,63}$'),
  constraint ck_suscripcion_estado check (estado in ('activa', 'suspendida', 'cancelada')),
  constraint ck_suscripcion_vigencia check (
    vigente_hasta is null or vigente_hasta > vigente_desde
  ),
  constraint ex_suscripcion_vigencia exclude using gist (
    empresa_id with =,
    plan_codigo with =,
    tstzrange(vigente_desde, vigente_hasta, '[)') with &&
  )
);

comment on table nucleo.tenant_suscripciones is
  'Suscripción comercial por empresa y plan, con vigencia. NO contiene precio, '
  'moneda, cupos ni límites: D-25/D-26 no están decididos. El apagado de módulos '
  'sigue escribiéndose en nucleo.modulos_empresa (ADR-0008 Ap. C.1).';
comment on column nucleo.tenant_suscripciones.plan_codigo is
  'Código del plan (minúsculas). El catálogo de planes vive en el código; '
  'D-25 no ha decidido su contenido comercial.';
comment on column nucleo.tenant_suscripciones.estado is
  'Estado acotado: activa | suspendida | cancelada. La base no decide qué '
  'estado apaga un módulo.';
comment on column nucleo.tenant_suscripciones.referencia_externa is
  'Identificador opcional del sistema de facturación/suscripciones. Nullable: '
  'la base no inventa proveedor ni formato.';
comment on column nucleo.tenant_suscripciones.vigente_hasta is
  'Fin de vigencia (UTC), exclusivo. NULL = vigente. Sin cierre automático: '
  'D-25 no decidió historial ni reglas de renovación.';

create unique index if not exists uq_suscripcion_vigente
  on nucleo.tenant_suscripciones (empresa_id, plan_codigo)
  where vigente_hasta is null;

create index if not exists idx_suscripciones_empresa_plan
  on nucleo.tenant_suscripciones (empresa_id, plan_codigo, vigente_desde desc);

-- ----------------------------------------------------------------------------
-- 4. Funciones de trigger
-- ----------------------------------------------------------------------------

-- Historial inmutable para reglas por entidad. No reutiliza
-- fn_config_empresa_inmutable: esa función no conoce `entidad` ni las 5 FKs.
create or replace function nucleo.fn_regla_entidad_inmutable()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'tenant_reglas_entidad: las reglas no se borran; cierre la vigencia (INV-TEN05)'
      using errcode = '23514';
  end if;

  if tg_op = 'INSERT' then
    return new;
  end if;

  -- Fila cerrada = historial inmutable. Solo se permiten las columnas de
  -- control (updated_at/updated_by/version), que fn_touch/fn_version escriben.
  if old.vigente_hasta is not null then
    if new.empresa_id    is distinct from old.empresa_id
       or new.entidad       is distinct from old.entidad
       or new.cliente_id    is distinct from old.cliente_id
       or new.chofer_id     is distinct from old.chofer_id
       or new.tracto_id     is distinct from old.tracto_id
       or new.rampla_id     is distinct from old.rampla_id
       or new.contacto_id   is distinct from old.contacto_id
       or new.clave         is distinct from old.clave
       or new.valor         is distinct from old.valor
       or new.vigente_desde is distinct from old.vigente_desde
       or new.vigente_hasta is distinct from old.vigente_hasta then
      raise exception 'tenant_reglas_entidad: la fila está cerrada; el historial no se edita (INV-TEN05)'
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

comment on function nucleo.fn_regla_entidad_inmutable() is
  'Impide borrar reglas y editar identidad/valor/vigencia de una fila cerrada '
  '(23514). Permite cerrar la vigencia de una fila abierta una sola vez.';

-- ----------------------------------------------------------------------------
-- 5. Triggers
--    `create or replace trigger` mantiene la migración re-ejecutable.
-- ----------------------------------------------------------------------------
create or replace trigger trg_tenant_reglas_inmutable
  before update or delete on nucleo.tenant_reglas_entidad
  for each row execute function nucleo.fn_regla_entidad_inmutable();
create or replace trigger trg_tenant_reglas_touch
  before update on nucleo.tenant_reglas_entidad
  for each row execute function nucleo.fn_touch();
create or replace trigger trg_tenant_reglas_version
  before update on nucleo.tenant_reglas_entidad
  for each row execute function nucleo.fn_version();
create or replace trigger trg_tenant_reglas_audit
  after insert or update or delete on nucleo.tenant_reglas_entidad
  for each row execute function nucleo.fn_auditoria();

create or replace trigger trg_tenant_suscripciones_touch
  before update on nucleo.tenant_suscripciones
  for each row execute function nucleo.fn_touch();
create or replace trigger trg_tenant_suscripciones_version
  before update on nucleo.tenant_suscripciones
  for each row execute function nucleo.fn_version();
create or replace trigger trg_tenant_suscripciones_audit
  after insert or update or delete on nucleo.tenant_suscripciones
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- 6. RLS + políticas
-- ----------------------------------------------------------------------------
alter table nucleo.tenant_reglas_entidad enable row level security;
alter table nucleo.tenant_reglas_entidad force row level security;
alter table nucleo.tenant_suscripciones enable row level security;
alter table nucleo.tenant_suscripciones force row level security;

drop policy if exists tenant_empresa on nucleo.tenant_reglas_entidad;
create policy tenant_empresa on nucleo.tenant_reglas_entidad
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

drop policy if exists tenant_empresa on nucleo.tenant_suscripciones;
create policy tenant_empresa on nucleo.tenant_suscripciones
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

-- ----------------------------------------------------------------------------
-- 7. GRANTs
--    `tei_app`: SELECT/INSERT/UPDATE, NUNCA DELETE (historial / privilegio).
--    `postgres`: rol de plataforma (patrón 0027), incluido DELETE.
-- ----------------------------------------------------------------------------
grant select, insert, update on table nucleo.tenant_reglas_entidad to tei_app;
grant select, insert, update on table nucleo.tenant_suscripciones to tei_app;

grant select, insert, update, delete on table nucleo.tenant_reglas_entidad to postgres;
grant select, insert, update, delete on table nucleo.tenant_suscripciones to postgres;

do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on table nucleo.tenant_reglas_entidad from %I', r);
      execute format('revoke all on table nucleo.tenant_suscripciones from %I', r);
    end if;
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 8. Verificación en la transacción (A.6)
-- ----------------------------------------------------------------------------
do $$
declare
  v_n      integer;
  v_tab    text;
  v_trg    text;
  v_filas  bigint;
begin
  -- RLS ENABLE + FORCE.
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('tenant_reglas_entidad', 'tenant_suscripciones')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 2 then
    raise exception 'VERIFICACIÓN: RLS+FORCE en % de 2 tablas', v_n
      using errcode = '23514';
  end if;

  -- Una política tenant_empresa por tabla, con ctx_empresa en USING y WITH CHECK.
  foreach v_tab in array array['tenant_reglas_entidad', 'tenant_suscripciones'] loop
    select count(*) into v_n
      from pg_policies
     where schemaname = 'nucleo' and tablename = v_tab
       and policyname = 'tenant_empresa'
       and coalesce(qual, '') like '%ctx_empresa%'
       and coalesce(with_check, '') like '%ctx_empresa%';
    if v_n <> 1 then
      raise exception 'VERIFICACIÓN: falta la política tenant_empresa con ctx_empresa en %', v_tab
        using errcode = '23514';
    end if;
  end loop;

  -- Privilegios de tei_app.
  foreach v_tab in array array['tenant_reglas_entidad', 'tenant_suscripciones'] loop
    if not has_table_privilege('tei_app', 'nucleo.' || v_tab, 'SELECT')
       or not has_table_privilege('tei_app', 'nucleo.' || v_tab, 'INSERT')
       or not has_table_privilege('tei_app', 'nucleo.' || v_tab, 'UPDATE') then
      raise exception 'VERIFICACIÓN: tei_app sin SELECT/INSERT/UPDATE en %', v_tab
        using errcode = '23514';
    end if;
    if has_table_privilege('tei_app', 'nucleo.' || v_tab, 'DELETE') then
      raise exception 'VERIFICACIÓN: tei_app NO debe tener DELETE en %', v_tab
        using errcode = '23514';
    end if;
  end loop;

  -- Exactamente un EXCLUDE en reglas (y uno en suscripciones).
  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.tenant_reglas_entidad'::regclass and contype = 'x';
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: se esperaba 1 EXCLUDE en tenant_reglas_entidad, hay %', v_n
      using errcode = '23514';
  end if;
  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.tenant_suscripciones'::regclass and contype = 'x';
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: se esperaba 1 EXCLUDE en tenant_suscripciones, hay %', v_n
      using errcode = '23514';
  end if;

  -- Índices únicos parciales de la fila abierta.
  if to_regclass('nucleo.uq_regla_vigente') is null then
    raise exception 'VERIFICACIÓN: falta uq_regla_vigente' using errcode = '23514';
  end if;
  if to_regclass('nucleo.uq_suscripcion_vigente') is null then
    raise exception 'VERIFICACIÓN: falta uq_suscripcion_vigente' using errcode = '23514';
  end if;

  -- Triggers por nombre.
  foreach v_trg in array array[
    'trg_tenant_reglas_inmutable', 'trg_tenant_reglas_touch',
    'trg_tenant_reglas_version', 'trg_tenant_reglas_audit',
    'trg_tenant_suscripciones_touch', 'trg_tenant_suscripciones_version',
    'trg_tenant_suscripciones_audit'
  ] loop
    select count(*) into v_n from pg_trigger where tgname = v_trg and not tgisinternal;
    if v_n <> 1 then
      raise exception 'VERIFICACIÓN: falta el trigger %', v_trg
        using errcode = '23514';
    end if;
  end loop;

  -- Sin datos de negocio sembrados (NOTICE, no aborta si hubiera filas).
  execute 'select count(*) from nucleo.tenant_reglas_entidad' into v_filas;
  raise notice 'VERIFICACIÓN: tenant_reglas_entidad = % fila(s)', v_filas;
  execute 'select count(*) from nucleo.tenant_suscripciones' into v_filas;
  raise notice 'VERIFICACIÓN: tenant_suscripciones = % fila(s)', v_filas;

  raise notice 'OK 0030: enum, 2 tablas, 2 EXCLUDE, 2 UNIQUE parciales, 7 triggers, RLS+FORCE, políticas y GRANTs';
end
$$;

commit;

-- ============================================================================
-- VERIFICACIÓN POST (base local de test):
--   supabase/tests/0030_01_reglas_entidad.sql
--   supabase/tests/0030_02_suscripciones.sql
--   supabase/tests/0030_03_rls_tei_app.sql
--   supabase/tests/0030_99_rollback.sql
-- ============================================================================
