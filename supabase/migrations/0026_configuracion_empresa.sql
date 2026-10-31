-- ============================================================================
-- TRANSTEI — Migración 0026: configuración por empresa con vigencia (Ola B.4)
-- ============================================================================
--
-- OBJETIVO
--   Reemplazar la configuración global del legacy (`public.configuracion`,
--   `0001:212-215`: clave/valor `text`, sin empresa, sin validación, sin
--   historial) por una configuración **por empresa**, tipada (`jsonb`) y
--   **versionada por vigencia**, que es lo que el núcleo ya asume.
--
--   Se siembra `iva_porcentaje = 19` para las empresas existentes al aplicar:
--   es el mismo valor del seed legacy (`0001:291`) y **no** es una afirmación
--   tributaria. La tasa vigente, el crédito fiscal y el F29 son `P-01`/`P-09`
--   (contador) y `D-21` (dueño): esta migración solo da el soporte.
--
--   Reglas (retiro-legacy-modulos.md §6, RET-04):
--     · una sola fila "vigente" por (empresa, clave) ⇒ UNIQUE parcial;
--     · el historial no se edita: para cambiar un valor se cierra la vigencia
--       (`vigente_hasta`) y se inserta una fila nueva;
--     · dos vigencias de la misma clave no se solapan ⇒ EXCLUDE gist;
--     · la tasa IVA se acota a 0..100 **en la base**; lo demás es del servicio.
--
--   Objetos: 1 tabla, 1 función de lectura (`config_vigente`), 3 funciones de
--   trigger, 5 triggers, RLS+FORCE, 1 política `tenant_empresa`, GRANTs a
--   `tei_app` (sin `delete`), seed de `iva_porcentaje` y `COMMENT`s.
--
-- REQUISITO DE ORDEN
--   Después de `0004` (btree_gist, fn_touch/fn_version/fn_auditoria) y `0020`
--   (rol `tei_app`, `nucleo.ctx_empresa()`, USAGE en `nucleo`).
--
-- PRECONDICIONES (detección; abortan con 23514)
--   P1  `nucleo.configuracion_empresa` no existe.
--   P2  `0020` aplicada y `btree_gist` disponible (lo exige el EXCLUDE).
--   P3  Ninguna empresa tiene ya una fila `iva_porcentaje` vigente (la tabla es
--       nueva, así que es consecuencia de P1; se verifica tras el DDL).
--
-- IMPACTO EN DATOS Y LOCKS
--   · `CREATE TABLE` vacía + seed de 1 fila por empresa. En la base local son
--     decenas de filas; en una base con muchas empresas es un INSERT pequeño.
--   · `INSERT` sobre tabla nueva: sin locks sobre tablas existentes. El seed
--     escribe `nucleo.auditoria` (1 fila por empresa, append-only por diseño).
--   · El legacy `public.configuracion` NO se toca y sigue siendo la fuente
--     mientras `/configuracion` tenga lectores (G0.3). No se apaga nada aquí.
--   · La app actual (rol `postgres`) no cambia: nadie lee esta tabla aún.
--
-- LO QUE ESTA MIGRACIÓN NO IMPONE
--   · Qué claves existen y qué tipos tienen (salvo `iva_porcentaje`): el
--     catálogo es del servicio; inventarlo convertiría una clave nueva legítima
--     del backend en 23514.
--   · Que `iva_porcentaje` sea 19, 21 o 0: el seed es paridad con el legacy,
--     no una norma (`P-01`).
--   · Qué pasa si un período ya declarado usó otra tasa: es `D-21`.
--   · Quién puede cambiar la tasa: es autorización de `backend` (rol admin).
--     La base da el mecanismo (historial), no el permiso.
--
-- ROLLBACK
--   `supabase/tests/0026_99_rollback.sql`: drop table + drop function
--   `config_vigente`. Pérdida: la configuración por empresa (hoy el seed de
--   `iva_porcentaje`). El legacy no se toca; su tabla sigue con el 19.
--
-- INVARIANTES (docs/datos/invariantes.md §13)
--   INV-CFG01  A lo sumo una fila vigente por (empresa, clave).
--   INV-CFG02  Las vigencias de una clave no se solapan ni retroceden.
--   INV-CFG03  El valor de una fila cerrada no se edita (historial append-only).
--   INV-CFG04  `iva_porcentaje` es numérico y está en [0, 100].
--   INV-CFG05  Toda fila es invisible/inescribible fuera de `app.empresa_id`.
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
  if to_regclass('nucleo.configuracion_empresa') is not null then
    raise exception 'PRECONDICIÓN P1: nucleo.configuracion_empresa ya existe; 0026 no se re-aplica'
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
  if not exists (select 1 from pg_extension where extname = 'btree_gist') then
    raise exception 'PRECONDICIÓN P2: falta la extensión btree_gist (EXCLUDE)'
      using errcode = '23514';
  end if;
end
$$;

-- ----------------------------------------------------------------------------
-- 1. Tabla
-- ----------------------------------------------------------------------------
create table nucleo.configuracion_empresa (
  id             uuid not null default gen_random_uuid(),
  empresa_id     uuid not null,
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
  constraint uq_config_empresa_id unique (empresa_id, id),
  constraint fk_config_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint ck_config_clave_formato check (clave ~ '^[a-z][a-z0-9_]{2,63}$'),
  constraint ck_config_vigencia check (
    vigente_hasta is null or vigente_hasta > vigente_desde
  ),
  -- Acotar la tasa es estructural (0..100). El valor concreto (19/21) es negocio.
  constraint ck_config_iva_porcentaje check (
    clave <> 'iva_porcentaje'
    or case
         when (valor #>> '{}') ~ '^[0-9]{1,3}(\.[0-9]+)?$'
           then (valor #>> '{}')::numeric >= 0 and (valor #>> '{}')::numeric <= 100
         else false
       end
  ),
  -- No hay dos filas de la misma clave con vigencias solapadas. El rango
  -- semiabierto [desde, hasta) es el estándar del núcleo (0004).
  constraint ex_config_vigencia exclude using gist (
    empresa_id with =,
    clave with =,
    tstzrange(vigente_desde, vigente_hasta, '[)') with &&
  )
);

comment on table nucleo.configuracion_empresa is
  'Parámetros por empresa con vigencia e historial. Reemplazo de '
  'public.configuracion (global, sin validación ni historial). Un cambio de '
  'valor = cerrar la vigencia e insertar una fila nueva; nunca UPDATE del valor.';
comment on column nucleo.configuracion_empresa.clave is
  'Identificador estable del parámetro (minúsculas). El catálogo y los tipos '
  'viven en el servicio; la base solo acota la forma y, para iva_porcentaje, '
  'el rango 0..100.';
comment on column nucleo.configuracion_empresa.valor is
  'Valor tipado en jsonb. Para iva_porcentaje se espera un número (19, 19.0).';
comment on column nucleo.configuracion_empresa.vigente_desde is
  'Inicio de vigencia (UTC). Se toma al insertar; no se edita.';
comment on column nucleo.configuracion_empresa.vigente_hasta is
  'Fin de vigencia (UTC), exclusivo. NULL = vigente. Una vez fijado no se '
  'edita ni se limpia: la fila pasa a ser historial inmutable.';

-- Una sola fila vigente por (empresa, clave). Refuerza el EXCLUDE con un error
-- explícito (23505) para el caso normal "ya hay un valor vigente".
create unique index uq_config_empresa_clave_vigente
  on nucleo.configuracion_empresa (empresa_id, clave)
  where vigente_hasta is null;

create index idx_config_empresa_clave
  on nucleo.configuracion_empresa (empresa_id, clave, vigente_desde desc);

-- ----------------------------------------------------------------------------
-- 2. Lectura canónica de la fila vigente (una sola definición)
--    SECURITY INVOKER: si la consulta `tei_app`, RLS filtra por empresa.
-- ----------------------------------------------------------------------------
create or replace function nucleo.config_vigente(p_empresa_id uuid, p_clave text)
returns jsonb
language sql
stable
set search_path to 'nucleo', 'pg_catalog'
as $$
  select c.valor
    from nucleo.configuracion_empresa c
   where c.empresa_id = p_empresa_id
     and c.clave = p_clave
     and c.vigente_hasta is null;
$$;

comment on function nucleo.config_vigente(uuid, text) is
  'Valor vigente de un parámetro por empresa (NULL si no está configurado). '
  'Corre con los privilegios de quien llama: RLS aplica.';

-- ----------------------------------------------------------------------------
-- 3. Funciones de trigger
-- ----------------------------------------------------------------------------

-- Historial append-only: identidad inmutable, valor congelado y cierre único.
create or replace function nucleo.fn_config_empresa_inmutable()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
begin
  if tg_op = 'INSERT' then
    return new;
  end if;

  if new.empresa_id is distinct from old.empresa_id
     or new.clave is distinct from old.clave then
    raise exception 'configuracion_empresa: empresa_id y clave son inmutables'
      using errcode = '23514';
  end if;

  if old.vigente_hasta is not null then
    raise exception 'configuracion_empresa: la fila ya está cerrada; el historial no se edita (INV-CFG03)'
      using errcode = '23514';
  end if;

  if new.valor is distinct from old.valor
     or new.vigente_desde is distinct from old.vigente_desde then
    raise exception 'configuracion_empresa: el valor no se edita; cierre la vigencia e inserte una fila nueva (INV-CFG03)'
      using errcode = '23514';
  end if;

  -- Solo se permite cerrar la vigencia (una vez) o tocar columnas de control.
  return new;
end;
$$;

comment on function nucleo.fn_config_empresa_inmutable() is
  'Impide reescribir el valor o la identidad de una fila; solo permite fijar '
  'vigente_hasta una vez (cierre de vigencia).';

create or replace function nucleo.fn_config_empresa_no_borrar()
returns trigger
language plpgsql
set search_path to 'nucleo', 'pg_catalog'
as $$
begin
  raise exception 'configuracion_empresa: el historial no se borra; cierre la vigencia (INV-CFG03)'
    using errcode = '23514';
end;
$$;

comment on function nucleo.fn_config_empresa_no_borrar() is
  'Bloquea DELETE en nucleo.configuracion_empresa (23514).';

-- ----------------------------------------------------------------------------
-- 4. Triggers
-- ----------------------------------------------------------------------------
create trigger trg_config_empresa_inmutable
  before update on nucleo.configuracion_empresa
  for each row execute function nucleo.fn_config_empresa_inmutable();
create trigger trg_config_empresa_no_borrar
  before delete on nucleo.configuracion_empresa
  for each row execute function nucleo.fn_config_empresa_no_borrar();
create trigger trg_config_empresa_touch
  before update on nucleo.configuracion_empresa
  for each row execute function nucleo.fn_touch();
create trigger trg_config_empresa_version
  before update on nucleo.configuracion_empresa
  for each row execute function nucleo.fn_version();
create trigger trg_config_empresa_audit
  after insert or update or delete on nucleo.configuracion_empresa
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- 5. RLS + política
-- ----------------------------------------------------------------------------
alter table nucleo.configuracion_empresa enable row level security;
alter table nucleo.configuracion_empresa force row level security;

drop policy if exists tenant_empresa on nucleo.configuracion_empresa;
create policy tenant_empresa on nucleo.configuracion_empresa
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

-- ----------------------------------------------------------------------------
-- 6. GRANTs (R-6 ADR-0005): sin `delete`; el historial se cierra, no se borra.
-- ----------------------------------------------------------------------------
grant select, insert, update on table nucleo.configuracion_empresa to tei_app;
grant execute on function nucleo.config_vigente(uuid, text) to tei_app;

do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on table nucleo.configuracion_empresa from %I', r);
      execute format('revoke all on function nucleo.config_vigente(uuid, text) from %I', r);
    end if;
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 7. Seed de paridad: iva_porcentaje = 19 (mismo valor que 0001:291)
--    No es una afirmación tributaria: P-01 / P-09 / D-21.
-- ----------------------------------------------------------------------------
do $$
declare
  v_emp   record;
  v_n     integer := 0;
begin
  for v_emp in select id from nucleo.empresas loop
    insert into nucleo.configuracion_empresa (empresa_id, clave, valor)
    values (v_emp.id, 'iva_porcentaje', to_jsonb(19));
    v_n := v_n + 1;
  end loop;
  raise notice '0026: iva_porcentaje=19 sembrado para % empresa(s)', v_n;
end
$$;

-- ----------------------------------------------------------------------------
-- 8. Verificación en la transacción
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
  v_emp integer;
begin
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'configuracion_empresa'
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: configuracion_empresa sin RLS+FORCE'
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo' and tablename = 'configuracion_empresa'
     and policyname = 'tenant_empresa'
     and coalesce(qual, '') like '%ctx_empresa%'
     and coalesce(with_check, '') like '%ctx_empresa%';
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta la política tenant_empresa con ctx_empresa'
      using errcode = '23514';
  end if;

  if not has_table_privilege('tei_app', 'nucleo.configuracion_empresa', 'SELECT')
     or not has_table_privilege('tei_app', 'nucleo.configuracion_empresa', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.configuracion_empresa', 'UPDATE') then
    raise exception 'VERIFICACIÓN: tei_app sin SELECT/INSERT/UPDATE en configuracion_empresa'
      using errcode = '23514';
  end if;
  if has_table_privilege('tei_app', 'nucleo.configuracion_empresa', 'DELETE') then
    raise exception 'VERIFICACIÓN: tei_app NO debe tener DELETE en configuracion_empresa'
      using errcode = '23514';
  end if;

  select count(*) into v_emp from nucleo.empresas;
  select count(*) into v_n
    from nucleo.configuracion_empresa
   where clave = 'iva_porcentaje' and vigente_hasta is null;
  if v_n <> v_emp then
    raise exception 'VERIFICACIÓN: iva_porcentaje vigente en % de % empresas', v_n, v_emp
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.configuracion_empresa'::regclass
     and contype = 'x';
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta el EXCLUDE de vigencia'
      using errcode = '23514';
  end if;

  raise notice 'OK 0026: tabla, EXCLUDE de vigencia, 5 triggers, RLS+FORCE, política, GRANTs; iva_porcentaje=19 en % empresa(s)', v_emp;
end
$$;

commit;

-- ============================================================================
-- VERIFICACIÓN POST: supabase/tests/0026_01_configuracion.sql
-- y 0026_02_rls_tei_app.sql (cubre 0024/0025/0026 con el rol tei_app).
-- ============================================================================
