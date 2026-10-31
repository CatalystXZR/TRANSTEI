-- ============================================================================
-- TRANSTEI — Migración 0023: flag de módulo por empresa (llave 1 del gate)
-- ============================================================================
--
-- OBJETIVO
--   Crear `nucleo.modulos_empresa`, el flag por empresa que el gate del agente
--   WhatsApp necesita como PRIMERA llave ("módulo activo por empresa"):
--
--     · diseño y nombres: docs/arquitectura/conector-agente-whatsapp.md §2.7
--       (`:260-311`), DDL propuesto íntegro;
--     · uso en el gate: §4.3 paso 4 y §4.4 "Llave 1" (`:500-551`), la consulta
--       es `where empresa_id = :empresa_id and modulo_id = 'agente-whatsapp'`
--       bajo `app.empresa_id` y rol `tei_app` (sin BYPASSRLS);
--     · criterio de aceptación: §9.9 handoff a `datos` (`:1509-1520`).
--
--   Objetos: 1 tabla nueva (PK compuesta, FK a `nucleo.empresas`, 2 CHECK),
--   2 triggers (`fn_touch`/`fn_version` de 0004), RLS + FORCE, 1 política
--   `tenant_empresa`, GRANT `select, insert, update` a `tei_app` (SIN `delete`)
--   y `COMMENT`s. CERO funciones nuevas: reutiliza el mecanismo existente
--   (`nucleo.fn_touch()` 0004:74-86, `nucleo.fn_version()` 0004:89-96).
--
--   NACE VACÍA, sin fila semilla. La ausencia de fila = módulo apagado
--   (fail-closed). Encender el módulo es una operación con su propio registro
--   (`habilitado_en`/`habilitado_por`), no un efecto de aplicar una migración.
--   Una fila con `habilitado = false` es el mismo estado que la ausencia, pero
--   conserva el rastro de que el módulo estuvo encendido y se apagó.
--
-- REQUISITO DE ORDEN
--   Después de 0020 (rol `tei_app`, `nucleo.ctx_empresa()`, USAGE en `nucleo`),
--   de 0021 (persistencia del módulo) y de 0022 (endurecimiento). Las
--   dependencias duras de ESTA migración son 0004/0020; 0021/0022 se exigen
--   porque el flag sin el módulo que gobierna deja el gate sin nada que leer.
--
-- PRECONDICIONES (detección; todas abortan con 23514 si fallan, no "arreglan")
--   P1  `nucleo.modulos_empresa` NO existe (ni tabla ni vista materializada).
--       Si existe: se reporta, no se sobreescribe; forward-only manda.
--   P2  0020 aplicada: existe `nucleo.ctx_empresa()`, el rol `tei_app` tiene
--       USAGE sobre el esquema `nucleo` y existe `nucleo.empresas` (destino FK).
--   P3  0021 aplicada: existen las 8 tablas del módulo agente.
--   P4  0022 aplicada: existen sus 3 funciones de trigger.
--   P5  0 filas: no hay filas que migrar. Es consecuencia de P1 (tabla nueva)
--       y se VERIFICA dentro de la misma transacción tras el DDL: si alguien
--       sembrara filas en el mismo instante, la migración aborta en lugar de
--       committear un estado no declarado.
--   Medido en `tei_test` antes de aplicar (2026-10-30):
--       P1=0, P2=1/1/1/1, P3=8, P4=3, P5=0.
--
-- IMPACTO EN DATOS Y LOCKS
--   · CREATE TABLE vacía: sin reescritura, sin backfill, sin UPDATE/DELETE
--     sobre datos existentes. Locks de catálogo (ACCESS EXCLUSIVE solo sobre la
--     tabla nueva, que nadie más puede estar usando) por milisegundos.
--   · Ningún índice nuevo sobre tablas existentes: la PK `(empresa_id,
--     modulo_id)` es el único índice y sirve tal cual a la consulta del gate
--     (igualdad por ambas columnas). No se agrega índice parcial por
--     `habilitado`: la tabla es de decenas de filas y el acceso es por PK.
--   · El legacy `public` NO se toca: ninguna sentencia referencia `public`.
--   · La app actual (rol `postgres`, BYPASSRLS) no cambia de comportamiento:
--     nada lee esta tabla todavía (módulo apagado, DEC-10).
--
-- LO QUE ESTA MIGRACIÓN NO IMPONE (declarado, no maquillado)
--   · Que `habilitado = true` traiga `habilitado_en`/`habilitado_por`: el
--     contrato §2.7 no fija quién escribe esos campos ni con qué reloj, y el
--     gate solo lee `habilitado`. Añadir ese CHECK convertiría una escritura
--     legítima del backend en 23514 por una regla que nadie acordó. Handoff:
--     `backend` los escribe al encender (§9.9) — si el negocio exige la
--     coherencia, va en una migración posterior con el contrato actualizado.
--   · Auditoría en `nucleo.auditoria`: `fn_auditoria()` (0004:830-878) extrae
--     `new.id::uuid` y esta tabla no tiene columna `id` (PK compuesta), así que
--     la fila de auditoría no podría identificar el módulo. No se instala un
--     trigger que registraría `registro_id = NULL`. El rastro disponible es
--     `created_by/updated_by/updated_at/version` + `habilitado_en/por`; si el
--     negocio quiere auditoría completa, es una migración con función propia.
--   · Borrado del rastro: `tei_app` no tiene `DELETE` (el flag se apaga, no se
--     borra). El dueño del esquema sí puede `DELETE`; no se instala trigger
--     `no_delete` porque el contrato no lo pide y el rollback debe poder
--     `drop table`.
--
-- COMPATIBILIDAD CON RLS (ADR-0005)
--   · Patrón exacto de 0020:273-298 / 0021:799-825: política `tenant_empresa`
--     `for all to public` con `USING` + `WITH CHECK` por
--     `empresa_id = nucleo.ctx_empresa()` ⇒ sin GUC, cero filas y escritura
--     rechazada (fail-closed).
--   · `ENABLE` + `FORCE ROW LEVEL SECURITY`, patrón 0020:386-400 y 0021:826-851.
--   · Sin GRANT a `anon`/`authenticated`. Hoy además esas dos no tienen USAGE
--     sobre `nucleo` (`nspacl` medido: `postgres=UC`, `tei_app=U`); el REVOKE
--     explícito es defensa en profundidad y hace la propiedad verificable.
--   · El wiring del rol en el backend (criterio O7.1) no lo resuelve esta
--     migración: mientras el backend conecte como `postgres`, RLS sigue inerte
--     (INV-T01 / RA-03, docs/estado.md).
--
-- ROLLBACK (orden inverso, sin datos de negocio)
--   `supabase/tests/0023_99_rollback.sql`: `drop table nucleo.modulos_empresa`.
--   Con la tabla caen PK, FK, CHECKs, índices, triggers, política y GRANTs.
--   Pérdida prevista: SOLO los flags de módulo por empresa (hoy 0 filas). Ningún
--   dato de negocio, ninguna tabla existente, ninguna función compartida
--   (`fn_touch`/`fn_version` son de 0004 y NO se tocan). Es reversible en el
--   sentido de "el esquema vuelve al estado anterior"; no hay datos que
--   restaurar porque la tabla nace vacía.
--
-- INVARIANTES
--   INV-AW17 (registro en docs/datos/invariantes.md §12):
--     "El módulo no opera para una empresa sin una fila con habilitado=true;
--      la ausencia y el false son el mismo estado."
--     Mecanismo en DB: PK `(empresa_id, modulo_id)` + `habilitado not null
--     default false` + RLS de tenant. La lectura "ausencia = false" la hace el
--     gate (no se puede imponer una ausencia por constraint).
--   INV-AW16 (tenant, heredado): toda fila es invisible/inescribible fuera de
--     `app.empresa_id`; sin contexto, cero filas. Mecanismo: política + FORCE +
--     GRANT. Prueba: sonda propia con `tei_app` (informe) + `0021_03` (regresión
--     del patrón en las 8 tablas del módulo).
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones defendidas (23514 con mensaje; no reparan nada)
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  -- P1: el objeto no existe.
  if to_regclass('nucleo.modulos_empresa') is not null then
    raise exception 'PRECONDICIÓN P1: nucleo.modulos_empresa ya existe; 0023 no se re-aplica'
      using errcode = '23514';
  end if;

  -- P2: 0020 aplicada (función de contexto, rol y destino de la FK).
  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
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

  -- P3: 0021 aplicada.
  select count(*) into v_n
    from pg_tables
   where schemaname = 'nucleo' and tablename in (
     'contactos_whatsapp','permisos_contacto','conversaciones',
     'conversacion_mensajes','solicitudes','hoja_ruta',
     'id_comercial_contador','auditoria_consultas_agente');
  if v_n <> 8 then
    raise exception 'PRECONDICIÓN P3: % de 8 tablas del módulo agente; aplicar 0021 primero', v_n
      using errcode = '23514';
  end if;

  -- P4: 0022 aplicada.
  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo' and p.proname in (
     'fn_contador_no_retrocede','fn_viaje_id_comercial_inmutable',
     'fn_hoja_ruta_transicion');
  if v_n <> 3 then
    raise exception 'PRECONDICIÓN P4: % de 3 funciones de 0022; aplicar 0022 primero', v_n
      using errcode = '23514';
  end if;
end
$$;

-- ----------------------------------------------------------------------------
-- 1. Tabla de flag por empresa (contrato §2.7, nombres exactos)
--    Sin `id` sintético: la PK natural es (empresa_id, modulo_id). No hay tabla
--    hija que necesite `(empresa_id, id)`, así que no se agrega el UNIQUE
--    auxiliar que el resto del núcleo usa para FKs compuestas.
-- ----------------------------------------------------------------------------
create table nucleo.modulos_empresa (
  empresa_id     uuid not null,
  modulo_id      text not null,
  habilitado     boolean not null default false,
  habilitado_en  timestamptz,
  habilitado_por text,
  created_at     timestamptz not null default now(),
  created_by     text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at     timestamptz not null default now(),
  updated_by     text,
  version        integer not null default 1 check (version >= 1),
  primary key (empresa_id, modulo_id),
  constraint fk_modulos_empresa_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  -- Formato del contrato §2.7 (`agente-whatsapp`): minúsculas, sin espacios.
  constraint ck_modulo_id_formato check (modulo_id ~ '^[a-z][a-z0-9-]{2,63}$'),
  -- Redundante con el formato a propósito: hace explícita la regla "no vacío"
  -- con nombre propio, para que retirar el formato no abra la puerta a ''.
  constraint ck_modulo_id_no_vacio check (btrim(modulo_id) <> '')
);

comment on table nucleo.modulos_empresa is
  'Llave 1 del gate del agente (conector-agente-whatsapp.md §2.7): módulo '
  'activo por empresa. Fail-closed: sin fila, o con habilitado=false, el '
  'módulo NO opera. Tei_app puede leer y escribir el flag pero no borrarlo '
  '(se apaga, no se borra).';
comment on column nucleo.modulos_empresa.modulo_id is
  'Identificador estable del módulo; el gate lee "agente-whatsapp". '
  'Formato ^[a-z][a-z0-9-]{2,63}$ (no es FK a un catálogo: no existe uno).';
comment on column nucleo.modulos_empresa.habilitado is
  'true = módulo encendido para la empresa. false y ausencia de fila son el '
  'mismo estado: apagado. El gate solo lee esta columna.';
comment on column nucleo.modulos_empresa.habilitado_en is
  'Cuándo se encendió/apagó (UTC). Lo escribe la plataforma al cambiar el '
  'flag; la base no lo infiere. NULL = nunca se registró el cambio.';
comment on column nucleo.modulos_empresa.habilitado_por is
  'Actor que cambió el flag (nucleo.auth_id): texto, no FK, porque puede ser '
  'un humano o la plataforma.';

-- ----------------------------------------------------------------------------
-- 2. Triggers convencionales: updated_at/updated_by y version (mecanismo de
--    0004:74-96, mismo patrón que las tablas del módulo en 0021:737-790).
--    BEFORE UPDATE por fila; nombres con sufijo `touch`/`version` como en 0021.
-- ----------------------------------------------------------------------------
create trigger trg_modulos_empresa_touch
  before update on nucleo.modulos_empresa
  for each row execute function nucleo.fn_touch();

create trigger trg_modulos_empresa_version
  before update on nucleo.modulos_empresa
  for each row execute function nucleo.fn_version();

-- ----------------------------------------------------------------------------
-- 3. RLS: ENABLE + FORCE y política de tenant (patrón 0020:273-298 y
--    0021:799-851). Sin contexto => 0 filas y escritura rechazada.
-- ----------------------------------------------------------------------------
alter table nucleo.modulos_empresa enable row level security;
alter table nucleo.modulos_empresa force row level security;

drop policy if exists tenant_empresa on nucleo.modulos_empresa;
create policy tenant_empresa on nucleo.modulos_empresa
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

-- ----------------------------------------------------------------------------
-- 4. GRANTs: tei_app lee y escribe el flag; NO borra (se apaga).
--    `anon`/`authenticated` no reciben nada (defensa en profundidad: hoy
--    tampoco tienen USAGE sobre el esquema).
-- ----------------------------------------------------------------------------
grant select, insert, update on table nucleo.modulos_empresa to tei_app;

do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on table nucleo.modulos_empresa from %I', r);
    end if;
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 5. Verificación dentro de la transacción: si algo no quedó como se declara,
--    aborta y no deja un estado intermedio. No reemplaza las pruebas
--    (supabase/tests/0023_99_rollback.sql + sondas con tei_app), las precede.
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  -- P5: la tabla nace vacía (sin fila semilla).
  select count(*) into v_n from nucleo.modulos_empresa;
  if v_n <> 0 then
    raise exception 'PRECONDICIÓN P5: nucleo.modulos_empresa tiene % filas; debe nacer vacía', v_n
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'modulos_empresa'
     and c.relkind = 'r' and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: modulos_empresa sin RLS+FORCE (encontrado %)', v_n
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo' and tablename = 'modulos_empresa'
     and policyname = 'tenant_empresa'
     and coalesce(qual, '') like '%ctx_empresa%'
     and coalesce(with_check, '') like '%ctx_empresa%';
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta la política tenant_empresa con ctx_empresa'
      using errcode = '23514';
  end if;

  if not has_table_privilege('tei_app', 'nucleo.modulos_empresa', 'SELECT')
     or not has_table_privilege('tei_app', 'nucleo.modulos_empresa', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.modulos_empresa', 'UPDATE') then
    raise exception 'VERIFICACIÓN: tei_app sin SELECT/INSERT/UPDATE sobre modulos_empresa'
      using errcode = '23514';
  end if;
  if has_table_privilege('tei_app', 'nucleo.modulos_empresa', 'DELETE') then
    raise exception 'VERIFICACIÓN: tei_app NO debe tener DELETE sobre modulos_empresa'
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_trigger t join pg_class c on c.oid = t.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'modulos_empresa'
     and not t.tgisinternal
     and t.tgname in ('trg_modulos_empresa_touch','trg_modulos_empresa_version');
  if v_n <> 2 then
    raise exception 'VERIFICACIÓN: se esperaban 2 triggers touch/version, hay %', v_n
      using errcode = '23514';
  end if;

  raise notice 'OK 0023: tabla, PK, FK, 2 CHECK, 2 triggers, RLS+FORCE, política y GRANTs listos; 0 filas';
end
$$;

commit;

-- ============================================================================
-- VERIFICACIÓN POST (ejecutada en `tei_test`, 2026-10-30)
--   1) Catálogo: tabla/PK/FK/CHECKs/triggers/RLS+FORCE/política/ACL
--      (consultas §6 del informe de `datos`).
--   2) Sonda con el rol REAL `tei_app` (transacción + ROLLBACK,
--      `app.empresa_id` por `set_config(..., true)`):
--        · sin contexto: SELECT 0 filas; INSERT => 42501 (WITH CHECK).
--        · contexto A: INSERT habilitado=true => permitido; SELECT 1 fila.
--        · contexto A + empresa_id B: INSERT => 42501.
--        · DELETE => 42501 (privilegio revocado).
--        · UPDATE => version 1->2 y updated_by por fn_touch.
--   3) Regresión: 0021_01 (63 OK), 0021_02 (concurrencia), 0021_03 (tei_app),
--      0021_04 (mutación) en verde, sin tocar esas suites.
--   4) Rollback `supabase/tests/0023_99_rollback.sql` ejecutado y re-aplicación
--      limpia.
--   Lo no cubierto: base de la app (🔴), pooler en modo transacción (🔴),
--   concurrencia sobre el flag (no la hay: es una fila por empresa, el
--   `UPDATE` serializa por fila y no hay invariante de carrera que imponer).
-- ============================================================================
