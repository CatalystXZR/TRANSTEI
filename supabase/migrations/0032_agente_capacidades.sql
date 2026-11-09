-- ============================================================================
-- TRANSTEI — Migración 0032: overrides de capacidades del chat in-app
-- ============================================================================
--
-- OBJETIVO
--   Persistir, por empresa y por agente (`gerente`, `secretaria`), qué
--   capacidades del catálogo del chat in-app quedan habilitadas o
--   deshabilitadas. Es una tabla de OVERRIDES: la ausencia de fila significa
--   "valor por defecto del código"; la fila explícita manda sobre ese defecto.
--
--   NO reemplaza ni duplica:
--     · `nucleo.tenant_reglas_entidad` (0030): reglas tipadas por entidad
--       concreta y con vigencia. Aquí no hay entidad ni vigencia.
--     · `nucleo.agente_chat_conversaciones` / `agente_chat_mensajes` (0031):
--       memoria del chat, no permisos.
--     · `nucleo.modulos_empresa` (0023): gate de módulos por empresa.
--     · `nucleo.usuarios_empresa.rol`: rol del usuario, no del agente LLM.
--   No se altera ninguna tabla existente.
--
-- OBJETOS
--   · tabla  nucleo.agente_capacidades (columnas y constraints del contrato)
--   · 3 triggers: trg_agente_capacidades_touch / _version / _audit
--   · RLS ENABLE + FORCE y política `tenant_empresa`
--   · GRANTs: `tei_app` SELECT/INSERT/UPDATE (sin DELETE);
--     `postgres` SELECT/INSERT/UPDATE/DELETE; revocación a anon/authenticated
--   · COMMENTs de tabla, columnas y política
--   · NO se crea un índice adicional (empresa_id, agente): el índice que
--     respalda el UNIQUE (empresa_id, agente, capacidad) ya sirve ese prefijo
--     (ver docs/datos/agente-capacidades.md §5, medido con EXPLAIN).
--
-- REQUISITO DE ORDEN
--   Después de 0004 (fn_touch/fn_version/fn_auditoria, gen_random_uuid),
--   0020 (rol `tei_app`, `nucleo.ctx_empresa()`, RLS de `nucleo.auditoria`) y
--   0028 (retiro de `public`). No depende de 0030/0031 para compilar.
--
-- PRECONDICIONES (abortan con 23514; no crean nada)
--   P1  `nucleo.agente_capacidades` NO existe. Si existe, aborta: la migración
--       NO es idempotente a propósito (sin `if not exists` ni `drop table`).
--       Re-ejecutarla exige el rollback documentado.
--   P2  `nucleo.empresas` y `nucleo.auditoria` existen.
--   P3  `nucleo.ctx_empresa()`, `nucleo.fn_touch()`, `nucleo.fn_version()` y
--       `nucleo.fn_auditoria()` existen (4 funciones).
--   P4  Rol `tei_app` existe, es NOBYPASSRLS y tiene USAGE sobre `nucleo`.
--
-- IMPACTO EN DATOS Y LOCKS
--   · ADD-only: una tabla NUEVA y vacía. Ningún UPDATE/DELETE/backfill.
--   · `CREATE TABLE` toma lock solo sobre el objeto nuevo; la FK a `empresas`
--     NO reescribe `nucleo.empresas`.
--   · `ENABLE/FORCE RLS`, `CREATE POLICY`, `GRANT` y `COMMENT` sobre la tabla
--     nueva: instantáneos.
--   · Ningún escritor actual conoce la tabla: el backend y el frontend siguen
--     funcionando (no se modifica ningún contrato HTTP).
--   · La migración NO siembra capacidades.
--
-- COMPATIBILIDAD
--   · No cambia columnas, constraints ni permisos de tablas existentes.
--   · `nucleo.auditoria` recibe filas nuevas de esta tabla vía `fn_auditoria`
--     (SECURITY DEFINER), sin cambiar su DDL ni sus políticas.
--
-- LO QUE ESTA MIGRACIÓN NO IMPONE (y no debe fingir)
--   · El catálogo de capacidades válidas: la base solo valida el FORMATO
--     (`^[a-z][a-z0-9_.]{2,80}$`). Un nombre que el código no conoce es un
--     dato que la base acepta y el servicio debe ignorar/rechazar.
--   · El valor por defecto de una capacidad ausente: vive en el código.
--   · Límites duros por agente (p. ej. "secretaria no emite facturas"): son
--     reglas del servicio; esta tabla solo expresa el override.
--   · Que el override se aplique al ejecutar la herramienta: lo impone el
--     backend al construir el catálogo del agente.
--   · Borrado lógico o historial: deshabilitar = `habilitada = false`.
--     `tei_app` no puede borrar; `postgres` sí (rol de plataforma).
--
-- ROLLBACK
--   drop table if exists nucleo.agente_capacidades;
--   Con la tabla caen PK, UNIQUE, CHECKs, FK, triggers, política, RLS y GRANTs.
--   No hay funciones propias que borrar: se reutilizan fn_touch/fn_version/
--   fn_auditoria. Pérdida: SOLO los overrides escritos (ninguno al aplicar).
--   `nucleo.empresas` y `nucleo.auditoria` NO se tocan; las filas de auditoría
--   ya escritas son append-only y NO se borran.
--   Simulación no destructiva: supabase/tests/0032_99_rollback.sql.
--
-- PRUEBAS
--   supabase/tests/0032_01_agente_capacidades.sql
--     constraints, RLS con `tei_app`, auditoría, touch/version y mutación.
--   supabase/tests/0032_99_rollback.sql
--     drop simulado dentro de begin/rollback.
--
-- INVARIANTES (docs/datos/invariantes.md §16, prefijo INV-AGCAP)
--   INV-AGCAP01  No hay dos filas para (empresa, agente, capacidad).
--   INV-AGCAP02  `agente` ∈ {gerente, secretaria} y `capacidad` cumple
--                ^[a-z][a-z0-9_.]{2,80}$.
--   INV-AGCAP03  Toda fila es invisible/inescribible fuera de app.empresa_id.
--   INV-AGCAP04  `tei_app` no puede borrar overrides (42501).
--   INV-AGCAP05  INSERT/UPDATE/DELETE dejan rastro en nucleo.auditoria.
--   INV-AGCAP06  Cada UPDATE refresca `updated_at` y sube `version`.
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones (P1–P4). No "arreglan" nada: abortan con mensaje.
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  -- P1: la tabla no debe existir. Sin idempotencia silenciosa.
  if to_regclass('nucleo.agente_capacidades') is not null then
    raise exception
      'PRECONDICIÓN P1: nucleo.agente_capacidades ya existe; 0032 no es idempotente. Ejecute el rollback documentado antes de re-aplicar'
      using errcode = '23514';
  end if;

  -- P2: tablas base.
  if to_regclass('nucleo.empresas') is null then
    raise exception 'PRECONDICIÓN P2: falta nucleo.empresas'
      using errcode = '23514';
  end if;
  if to_regclass('nucleo.auditoria') is null then
    raise exception 'PRECONDICIÓN P2: falta nucleo.auditoria'
      using errcode = '23514';
  end if;

  -- P3: las 4 funciones compartidas.
  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('ctx_empresa', 'fn_touch', 'fn_version', 'fn_auditoria');
  if v_n <> 4 then
    raise exception 'PRECONDICIÓN P3: faltan funciones del núcleo (% de 4); aplicar 0004/0020 primero', v_n
      using errcode = '23514';
  end if;

  -- P4: rol de aplicación, sin BYPASSRLS y con USAGE sobre el esquema.
  if not exists (select 1 from pg_roles where rolname = 'tei_app') then
    raise exception 'PRECONDICIÓN P4: falta el rol tei_app; aplicar 0020 primero'
      using errcode = '23514';
  end if;
  if (select rolbypassrls from pg_roles where rolname = 'tei_app') then
    raise exception 'PRECONDICIÓN P4: tei_app tiene BYPASSRLS; la RLS sería inerte (R-10)'
      using errcode = '23514';
  end if;
  if not has_schema_privilege('tei_app', 'nucleo', 'USAGE') then
    raise exception 'PRECONDICIÓN P4: tei_app sin USAGE sobre nucleo; aplicar 0020 primero'
      using errcode = '23514';
  end if;

  raise notice 'PRECONDICIÓN OK 0032: tabla ausente; empresas/auditoria y 4 funciones presentes; tei_app NOBYPASSRLS con USAGE';
end
$$;

-- ----------------------------------------------------------------------------
-- 1. Tabla de overrides
--    `empresa_id` con FK simple a `empresas`: la fila no referencia ninguna
--    otra entidad, así que no existe el cruce entre empresas que exige una FK
--    compuesta. El aislamiento lo impone RLS (INV-AGCAP03).
-- ----------------------------------------------------------------------------
create table nucleo.agente_capacidades (
  id uuid primary key default gen_random_uuid(),
  empresa_id uuid not null references nucleo.empresas(id) on delete restrict,
  agente text not null check (agente in ('gerente','secretaria')),
  capacidad text not null check (capacidad ~ '^[a-z][a-z0-9_.]{2,80}$'),
  habilitada boolean not null,
  created_at timestamptz not null default now(),
  created_by text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at timestamptz not null default now(),
  updated_by text,
  version integer not null default 1 check (version >= 1),
  constraint agente_capacidades_unica unique (empresa_id, agente, capacidad)
);

comment on table nucleo.agente_capacidades is
  'Override por empresa y agente de las capacidades del chat in-app. Fila '
  'ausente = valor por defecto del código. No es catálogo de capacidades ni '
  'gate de módulos: el catálogo y los límites duros viven en el backend.';
comment on column nucleo.agente_capacidades.agente is
  'Agente LLM del chat: gerente | secretaria. La base acota el valor '
  '(INV-AGCAP02); el catálogo de herramientas es del servicio.';
comment on column nucleo.agente_capacidades.capacidad is
  'Identificador de la capacidad (minúsculas, dígitos, punto y guion bajo; '
  '3–81 caracteres). La base solo valida el formato: un nombre inexistente en '
  'el código es dato basura que el servicio debe ignorar.';
comment on column nucleo.agente_capacidades.habilitada is
  'Valor explícito del override: true habilita, false deshabilita. No existe '
  'NULL = heredar ni borrado lógico; deshabilitar es habilitada = false.';
comment on column nucleo.agente_capacidades.created_by is
  'auth_id del contexto (nucleo.auth_id) al crear la fila; sistema si falta.';
comment on column nucleo.agente_capacidades.version is
  'Versión optimista de la fila; fn_version() la incrementa en cada UPDATE '
  '(INV-AGCAP06).';

-- Sin índice adicional (empresa_id, agente): el índice UNIQUE
-- (empresa_id, agente, capacidad) sirve el prefijo. Un índice extra solo
-- duplicaría escrituras. Evidencia con EXPLAIN en
-- docs/datos/agente-capacidades.md §5.

-- ----------------------------------------------------------------------------
-- 2. Triggers de control
--    touch/version en BEFORE UPDATE; auditoría en AFTER INSERT/UPDATE/DELETE.
--    La tabla es nueva: `create trigger` simple (sin OR REPLACE).
-- ----------------------------------------------------------------------------
create trigger trg_agente_capacidades_touch
  before update on nucleo.agente_capacidades
  for each row execute function nucleo.fn_touch();

create trigger trg_agente_capacidades_version
  before update on nucleo.agente_capacidades
  for each row execute function nucleo.fn_version();

create trigger trg_agente_capacidades_audit
  after insert or update or delete on nucleo.agente_capacidades
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- 3. RLS: ENABLE + FORCE y política `tenant_empresa` (patrón 0020/0030/0031).
--    Fail-closed sin app.empresa_id: ctx_empresa() devuelve NULL.
-- ----------------------------------------------------------------------------
alter table nucleo.agente_capacidades enable row level security;
alter table nucleo.agente_capacidades force row level security;

create policy tenant_empresa on nucleo.agente_capacidades
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

comment on policy tenant_empresa on nucleo.agente_capacidades is
  'Aislamiento por empresa de los overrides de capacidades: sin app.empresa_id '
  'el contexto es NULL y la política devuelve 0 filas / rechaza INSERT '
  '(fail-closed, INV-AGCAP03).';

-- ----------------------------------------------------------------------------
-- 4. GRANTs
--    tei_app: SELECT/INSERT/UPDATE, NUNCA DELETE (INV-AGCAP04).
--    postgres: rol de plataforma, incluido DELETE (patrón 0027/0030/0031).
-- ----------------------------------------------------------------------------
grant select, insert, update on table nucleo.agente_capacidades to tei_app;
grant select, insert, update, delete on table nucleo.agente_capacidades to postgres;

do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on table nucleo.agente_capacidades from %I', r);
    end if;
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 5. Verificación dentro de la transacción
-- ----------------------------------------------------------------------------
do $$
declare
  v_n     integer;
  v_trg   text;
  v_filas bigint;
  r       text;
begin
  -- RLS ENABLE + FORCE.
  select count(*) into v_n
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname = 'agente_capacidades'
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta RLS+FORCE en agente_capacidades'
      using errcode = '23514';
  end if;

  -- Política tenant_empresa con ctx_empresa en USING y WITH CHECK.
  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename = 'agente_capacidades'
     and policyname = 'tenant_empresa'
     and coalesce(qual, '') like '%ctx_empresa%'
     and coalesce(with_check, '') like '%ctx_empresa%';
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta la política tenant_empresa con ctx_empresa'
      using errcode = '23514';
  end if;

  -- UNIQUE (empresa_id, agente, capacidad).
  select count(*) into v_n
    from pg_constraint c
   where c.conrelid = 'nucleo.agente_capacidades'::regclass
     and c.contype = 'u'
     and c.conname = 'agente_capacidades_unica'
     and (
       select array_agg(a.attname order by k.ord)
         from unnest(c.conkey) with ordinality as k(attnum, ord)
         join pg_attribute a
           on a.attrelid = c.conrelid and a.attnum = k.attnum
     ) = array['empresa_id', 'agente', 'capacidad']::name[];
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta UNIQUE (empresa_id, agente, capacidad)'
      using errcode = '23514';
  end if;

  -- Tres CHECK: agente, capacidad y version.
  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.agente_capacidades'::regclass
     and contype = 'c';
  if v_n <> 3 then
    raise exception 'VERIFICACIÓN: se esperaban 3 CHECK, hay %', v_n
      using errcode = '23514';
  end if;

  -- FK a empresas con ON DELETE RESTRICT.
  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.agente_capacidades'::regclass
     and contype = 'f'
     and confrelid = 'nucleo.empresas'::regclass
     and confdeltype = 'r';
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta FK a empresas con ON DELETE RESTRICT'
      using errcode = '23514';
  end if;

  -- Privilegios.
  if not has_table_privilege('tei_app', 'nucleo.agente_capacidades', 'SELECT')
     or not has_table_privilege('tei_app', 'nucleo.agente_capacidades', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.agente_capacidades', 'UPDATE') then
    raise exception 'VERIFICACIÓN: tei_app sin SELECT/INSERT/UPDATE'
      using errcode = '23514';
  end if;
  if has_table_privilege('tei_app', 'nucleo.agente_capacidades', 'DELETE') then
    raise exception 'VERIFICACIÓN: tei_app NO debe tener DELETE (INV-AGCAP04)'
      using errcode = '23514';
  end if;
  if not has_table_privilege('postgres', 'nucleo.agente_capacidades', 'DELETE') then
    raise exception 'VERIFICACIÓN: postgres debe conservar DELETE'
      using errcode = '23514';
  end if;
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r)
       and has_table_privilege(r, 'nucleo.agente_capacidades', 'SELECT') then
      raise exception 'VERIFICACIÓN: % no debe tener privilegios sobre agente_capacidades', r
        using errcode = '23514';
    end if;
  end loop;

  -- Triggers por nombre y función.
  foreach v_trg in array array[
    'trg_agente_capacidades_touch',
    'trg_agente_capacidades_version',
    'trg_agente_capacidades_audit'
  ] loop
    select count(*) into v_n
      from pg_trigger
     where tgrelid = 'nucleo.agente_capacidades'::regclass
       and tgname = v_trg
       and not tgisinternal;
    if v_n <> 1 then
      raise exception 'VERIFICACIÓN: falta el trigger %', v_trg
        using errcode = '23514';
    end if;
  end loop;
  select count(*) into v_n
    from pg_trigger t
    join pg_proc p on p.oid = t.tgfoid
   where t.tgrelid = 'nucleo.agente_capacidades'::regclass
     and not t.tgisinternal
     and (
       (t.tgname = 'trg_agente_capacidades_touch'   and p.proname = 'fn_touch')
       or (t.tgname = 'trg_agente_capacidades_version' and p.proname = 'fn_version')
       or (t.tgname = 'trg_agente_capacidades_audit'   and p.proname = 'fn_auditoria')
     );
  if v_n <> 3 then
    raise exception 'VERIFICACIÓN: triggers mal enlazados (% de 3)', v_n
      using errcode = '23514';
  end if;

  -- La tabla nace vacía.
  execute 'select count(*) from nucleo.agente_capacidades' into v_filas;
  if v_filas <> 0 then
    raise exception 'VERIFICACIÓN: agente_capacidades debe nacer vacía, tiene % fila(s)', v_filas
      using errcode = '23514';
  end if;

  raise notice 'OK 0032: 1 tabla, UNIQUE, 3 CHECK, FK RESTRICT, 3 triggers, RLS+FORCE, política tenant_empresa y GRANTs';
end
$$;

commit;

-- ============================================================================
-- VERIFICACIÓN POST:
--   supabase/tests/0032_01_agente_capacidades.sql
--   supabase/tests/0032_99_rollback.sql
-- Detalle, evidencia y límites: docs/datos/agente-capacidades.md
-- ============================================================================
