-- ============================================================================
-- TRANSTEI — Migración 0028: retiro físico del esquema legacy `public` (Ola E)
-- ============================================================================
--
-- OBJETIVO
--   Borrar los **datos y objetos** del legacy: las 17 relaciones de `public`,
--   los 8 `enum` y las 2 funciones propias (`handle_new_user`,
--   `set_updated_at`), y el trigger `on_auth_user_created` de `auth.users` que
--   mantenía el espejo de identidad en `public.usuarios`.
--
--   Autorización: el dueño autorizó la **Ola E completa** (ADR-0002 §6.7, E.5)
--   el 2026-11-01, sobre base local con datos ficticios. Esta migración es el
--   E.5 ejecutado **sin** `DROP SCHEMA`; ver "LO QUE ESTA MIGRACIÓN NO HACE".
--
--   Objetos que elimina (inventario medido el 2026-11-01 en la base local):
--     · 17 tablas: `_migraciones`, `ajustes_liquidacion`, `anticipos_chofer`,
--       `choferes`, `clientes`, `configuracion`, `factura_viaje`, `facturas`,
--       `gastos_viaje`, `kpis`, `liquidaciones`, `mantenimientos`,
--       `pautas_mantenimiento`, `ramplas`, `tractos`, `usuarios`, `viajes`.
--       Con ellas caen sus 37 índices, 15 FKs, 10 triggers `*_updated`, 1
--       política RLS (`usuarios.leer propio perfil`) y todos sus datos.
--     · 8 `enum` de `public`: `categoria_gasto`, `estado_factura`,
--       `estado_liquidacion`, `estado_viaje`, `rol_usuario`, `tipo_ajuste`,
--       `tipo_factura`, `tipo_rampla`.
--     · 2 funciones de `public`: `handle_new_user()` y `set_updated_at()`.
--     · 1 trigger en `auth.users`: `on_auth_user_created` (llamaba a
--       `public.handle_new_user()`; `0001_esquema_base.sql:248-263`).
--   0 secuencias, 0 vistas, 0 dominios y 0 `public`-types de otro tipo.
--
-- PRECONDICIONES (detección; abortan con 23514 sin borrar nada)
--   P0  Backup verificado y declarado:
--       `backups/cutover_pre_20261101_115202.sql` (2.180.084 bytes, sha256
--       `fbdd07c9b874883fbe7633e3a342c9c8be2c62d3af22866339cdc001d342c19f`),
--       tomado el 2026-11-01 11:52 y con las 17 tablas de `public` en su
--       contenido (`^COPY public.` = 17). El SQL **no** puede demostrar el
--       backup: es una precondición operativa, se declara aquí y en
--       `docs/datos/retiro-public.md`.
--   P1  0 FKs desde fuera de `public` hacia `public` (núcleo → legacy). Hoy: 0.
--   P2  0 vistas/materialized views fuera de `public` que dependan de `public`.
--   P3  0 columnas de otros esquemas tipadas con un tipo **no-extension** de
--       `public`. Las columnas `gbtreekey*` de `nucleo` son de la extensión
--       `btree_gist` y **no** se cuentan (ver "LO QUE ESTA MIGRACIÓN NO HACE").
--   P4  0 funciones de otros esquemas que dependan de funciones/tipos de
--       `public` (se excluyen `pg_catalog`, `information_schema` y `pg_toast`).
--   P5  Conteo de filas por tabla, emitido como `NOTICE` antes de cualquier
--       `DROP` (queda en el log de aplicación; copia en
--       `docs/datos/retiro-public.md`).
--
-- IMPACTO — DESTRUCTIVO E IRREVERSIBLE POR SQL
--   · `DROP TABLE ... CASCADE` es irreversible: no existe `ROLLBACK` en SQL.
--     El único rollback es **restaurar el backup** (P0) sobre una base vacía.
--   · Locks: `DROP TABLE` toma `ACCESS EXCLUSIVE` sobre cada tabla. En la base
--     local las tablas suman < 400 kB y no hay lectores concurrentes; en una
--     base con tráfico legacy esto exige ventana con escrituras en 0.
--   · Tras el `DROP`, cualquier `select ... from public.<tabla>` falla con
--     `42P01` (relación inexistente) o `42501` (sin `USAGE` en el esquema; ver
--     bloque 5).
--   · No toca `auth` (salvo el trigger de `auth.users`), `storage`,
--     `extensions`, `nucleo`, `realtime`, `vault` ni el bucket `respaldos`
--     (`0002_config_cobranza.sql:12-20`).
--   · No toca `supabase_migrations.schema_migrations` (registro de la CLI) ni
--     `nucleo.cutover_control`.
--
-- COMPATIBILIDAD (verificada en esta fecha, ver retiro-public.md)
--   · `backend/app/`: 0 lecturas/escrituras de `public.*` salvo
--     `nucleo/servicio_cutover.py:97`, que cuenta `public.viajes` dentro de
--     `try/except` y degrada a 0 con `warning` (`:103-109`). No rompe.
--   · Identidad: `deps.py:96` y `api/routes/auth.py:14` resuelven desde el JWT y
--     `nucleo.usuarios_empresa`; el trigger era el último escritor.
--   · Seeds: `scripts/seed_local.py` y `scripts/seed_segundo_tenant.py` solo
--     escriben `nucleo.*` ( `seed_local.py:180,190`; `seed_segundo_tenant.py:78`).
--   · `scripts/cutover_legacy.py:142` ya consulta `to_regclass('public.clientes')`
--     y se detiene si no existe.
--
-- LO QUE ESTA MIGRACIÓN NO HACE
--   · **No hace `DROP SCHEMA public`.** El esquema se conserva vacío: Supabase y
--     PostgREST lo esperan en `config.toml` (`schemas = ["public", ...]`,
--     `extra_search_path = ["public", ...]`) y `pg_database_owner` es su dueño.
--   · **No elimina `btree_gist`.** La extensión está instalada **en `public`**
--     (`0004_nucleo_operacional.sql:28` la crea sin `SCHEMA`) y de ella dependen
--     los 4 `EXCLUDE USING gist` del núcleo (`nucleo.reservas_recurso` ×3 y
--     `nucleo.configuracion_empresa` ×1). Por eso `public` no queda
--     literalmente vacío: conserva los objetos de la extensión. Borrarlos
--     rompería INV-001/INV-CFG02; moverlos de esquema es otra decisión.
--   · No retira el middleware de congelamiento, el flag `nucleo.cutover_control`
--     ni los modelos legacy de Python (E.3/E.4, otros dueños).
--   · No borra el backup ni el bucket `respaldos`.
--
-- ROLLBACK
--   No hay rollback SQL (los datos se destruyen). Procedimiento:
--     1. `supabase db reset` NO sirve (re-aplicaría `0028`).
--     2. Crear una base vacía y restaurar
--        `backups/cutover_pre_20261101_115202.sql` (contiene `public` completo,
--        `nucleo`, `auth` y `storage`), o restaurar solo `public` con
--        `pg_restore --section` equivalente + `0001`…`0028` para el resto.
--     3. Re-aplicar `0001`…`0027` si la restauración es parcial.
--   Riesgo residual: cualquier fila escrita en `public` **después** del backup
--   (11:52 del 2026-11-01) no existe en el backup. Se midió: 0 diferencia de
--   conteos entre el backup y la base al aplicar (ver doc).
--
-- IDEMPOTENCIA
--   Todo es `if exists`; los conteos se calculan sobre lo que haya. Re-aplicar
--   sobre una base ya migrada no cambia nada y deja el mismo `NOTICE`.
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones (abortan con 23514 sin borrar nada)
-- ----------------------------------------------------------------------------
do $$
declare
  v_n     bigint;
  v_lista text;
begin
  -- P1: FKs desde fuera de `public` hacia `public`.
  select count(*), string_agg(format('%s.%s -> public.%s',
                                     cn.nspname, cl.relname, pl.relname), ', ')
    into v_n, v_lista
    from pg_constraint c
    join pg_class cl on cl.oid = c.conrelid
    join pg_namespace cn on cn.oid = cl.relnamespace
    join pg_class pl on pl.oid = c.confrelid
    join pg_namespace pn on pn.oid = pl.relnamespace
   where c.contype = 'f'
     and pn.nspname = 'public'
     and cn.nspname <> 'public';
  if v_n > 0 then
    raise exception 'P1 FALLO: % FK(s) desde fuera de public hacia public: %',
      v_n, v_lista using errcode = '23514';
  end if;

  -- P2: vistas fuera de `public` que dependan de relaciones de `public`.
  select count(*), string_agg(format('%s.%s -> public.%s',
                                     dn.nspname, dc.relname, sc.relname), ', ')
    into v_n, v_lista
    from pg_depend d
    join pg_rewrite rw on rw.oid = d.objid
    join pg_class dc on dc.oid = rw.ev_class
    join pg_namespace dn on dn.oid = dc.relnamespace
    join pg_class sc on sc.oid = d.refobjid
    join pg_namespace sn on sn.oid = sc.relnamespace
   where sn.nspname = 'public'
     and dn.nspname not in ('public', 'pg_catalog', 'information_schema')
     and dc.relkind in ('v', 'm');
  if v_n > 0 then
    raise exception 'P2 FALLO: % vista(s) dependen de public: %',
      v_n, v_lista using errcode = '23514';
  end if;

  -- P3: columnas de otros esquemas con tipo NO-extension de `public`.
  select count(*), string_agg(format('%s.%s.%s: public.%s',
                                     dn.nspname, dc.relname, a.attname, t.typname), ', ')
    into v_n, v_lista
    from pg_attribute a
    join pg_class dc on dc.oid = a.attrelid
    join pg_namespace dn on dn.oid = dc.relnamespace
    join pg_type t on t.oid = a.atttypid
    join pg_namespace tn on tn.oid = t.typnamespace
    left join pg_depend dep on dep.objid = t.oid and dep.deptype = 'e'
   where a.attnum > 0
     and not a.attisdropped
     and tn.nspname = 'public'
     and dn.nspname not in ('public', 'pg_catalog', 'information_schema', 'pg_toast')
     and dep.objid is null;
  if v_n > 0 then
    raise exception 'P3 FALLO: % columna(s) usan un tipo de public: %',
      v_n, v_lista using errcode = '23514';
  end if;

  -- P4: funciones de otros esquemas que dependan de funciones/tipos de `public`.
  select count(*), string_agg(distinct format('%s.%s', dn.nspname, dc.proname), ', ')
    into v_n, v_lista
    from (
      -- refobj = función de `public`
      select d.objid
        from pg_depend d
        join pg_proc p on p.oid = d.refobjid
        join pg_namespace pn on pn.oid = p.pronamespace
       where d.classid = 'pg_proc'::regclass
         and pn.nspname = 'public'
      union all
      -- refobj = tipo de `public`
      select d.objid
        from pg_depend d
        join pg_type t on t.oid = d.refobjid
        join pg_namespace tn on tn.oid = t.typnamespace
       where d.classid = 'pg_type'::regclass
         and tn.nspname = 'public'
    ) dep
    join pg_proc dc on dc.oid = dep.objid
    join pg_namespace dn on dn.oid = dc.pronamespace
   where dn.nspname not in ('public', 'pg_catalog', 'information_schema', 'pg_toast');
  if v_n > 0 then
    raise exception 'P4 FALLO: % función(es) dependen de public: %',
      v_n, v_lista using errcode = '23514';
  end if;

  raise notice 'P1-P4 OK: 0 FKs, 0 vistas, 0 columnas y 0 funciones de otros esquemas dependen de public';
end
$$;

-- ----------------------------------------------------------------------------
-- 1. Conteos antes del DROP (P5) — quedan en el log como NOTICE
-- ----------------------------------------------------------------------------
do $$
declare
  r        record;
  v_n      bigint;
  v_total  bigint := 0;
  v_bytes  bigint := 0;
begin
  for r in
    select c.relname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public'
       and c.relkind in ('r', 'p')
     order by c.relname
  loop
    execute format('select count(*) from public.%I', r.relname) into v_n;
    v_total := v_total + v_n;
    raise notice 'CONTE0 public.% = % filas', r.relname, v_n;
  end loop;
  select coalesce(sum(pg_total_relation_size(c.oid)), 0) into v_bytes
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind in ('r', 'p');
  raise notice 'CONTE0 total: % filas en public, % kB', v_total, v_bytes / 1024;
end
$$;

-- ----------------------------------------------------------------------------
-- 2. Identidad: fuera el trigger de `auth.users` y su función
--    (firma real: `public.handle_new_user()` sin argumentos; `0001:248-263`)
-- ----------------------------------------------------------------------------
do $$
begin
  if to_regclass('auth.users') is not null then
    execute 'drop trigger if exists on_auth_user_created on auth.users';
  else
    raise notice 'AVISO: no existe auth.users; no había trigger de identidad que retirar';
  end if;
end
$$;

drop function if exists public.handle_new_user();

-- ----------------------------------------------------------------------------
-- 3. Tablas del legacy (17). CASCADE arrastra índices, FKs, triggers y políticas
--    propias; P1-P4 garantizan que no arrastra nada de otro esquema.
-- ----------------------------------------------------------------------------
drop table if exists public.factura_viaje        cascade;
drop table if exists public.gastos_viaje         cascade;
drop table if exists public.facturas             cascade;
drop table if exists public.liquidaciones        cascade;
drop table if exists public.anticipos_chofer     cascade;
drop table if exists public.ajustes_liquidacion  cascade;
drop table if exists public.mantenimientos       cascade;
drop table if exists public.kpis                 cascade;
drop table if exists public.viajes               cascade;
drop table if exists public.pautas_mantenimiento cascade;
drop table if exists public.tractos              cascade;
drop table if exists public.ramplas              cascade;
drop table if exists public.choferes             cascade;
drop table if exists public.clientes             cascade;
drop table if exists public.configuracion        cascade;
drop table if exists public.usuarios             cascade;
drop table if exists public._migraciones         cascade;

-- ----------------------------------------------------------------------------
-- 4. Funciones y tipos propios que quedaban en `public`
--    (sin CASCADE a propósito: si algo dependiera, aborta en vez de arrastrarlo)
-- ----------------------------------------------------------------------------
drop function if exists public.set_updated_at();

drop type if exists public.categoria_gasto;
drop type if exists public.estado_factura;
drop type if exists public.estado_liquidacion;
drop type if exists public.estado_viaje;
drop type if exists public.rol_usuario;
drop type if exists public.tipo_ajuste;
drop type if exists public.tipo_factura;
drop type if exists public.tipo_rampla;

-- ----------------------------------------------------------------------------
-- 5. Defecto seguro del esquema vacío
--    `public` conserva el GRANT implícito `USAGE` a `PUBLIC` que trae PostgreSQL
--    desde el clúster. Con el esquema sin tablas, ese GRANT solo sirve para que
--    un rol cualquiera resuelva nombres en `public` (y obtenga `42P01` en vez de
--    `42501`). Se revoca y se re-otorga explícitamente a los roles de Supabase,
--    de modo que un rol nuevo (o el rol de aplicación, `tei_app`) queda en
--    **deny por defecto**. `tei_app` no necesita `public`: `0020` le dio USAGE
--    en `nucleo` y los `EXCLUDE` del núcleo usan los objetos de `btree_gist`
--    por OID, no por nombre.
-- ----------------------------------------------------------------------------
do $$
declare
  r text;
begin
  revoke usage on schema public from public;
  foreach r in array array['postgres', 'service_role', 'anon', 'authenticated', 'authenticator']
  loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('grant usage on schema public to %I', r);
    end if;
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 6. Verificación posterior (falla la migración si el estado no es el buscado)
-- ----------------------------------------------------------------------------
do $$
declare
  v_n bigint;
begin
  -- 6.1 Sin relaciones propias en `public` (los objetos de extensión no cuentan).
  select count(*) into v_n
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    left join pg_depend d on d.objid = c.oid and d.deptype = 'e'
   where n.nspname = 'public'
     and d.objid is null
     and c.relkind in ('r', 'v', 'm', 'p', 'f', 'S');
  if v_n <> 0 then
    raise exception 'V1 FALLO: quedan % relación(es) propias en public', v_n
      using errcode = '23514';
  end if;

  -- 6.2 Sin funciones propias en `public`.
  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    left join pg_depend d on d.objid = p.oid and d.deptype = 'e'
   where n.nspname = 'public' and d.objid is null;
  if v_n <> 0 then
    raise exception 'V2 FALLO: quedan % función(es) propias en public', v_n
      using errcode = '23514';
  end if;

  -- 6.3 Sin enums propios en `public`.
  select count(*) into v_n
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    left join pg_depend d on d.objid = t.oid and d.deptype = 'e'
   where n.nspname = 'public' and t.typtype in ('e', 'd') and d.objid is null;
  if v_n <> 0 then
    raise exception 'V3 FALLO: quedan % tipo(s) propios en public', v_n
      using errcode = '23514';
  end if;

  -- 6.4 `auth.users` sin el trigger de identidad.
  if to_regclass('auth.users') is not null then
    select count(*) into v_n
      from pg_trigger
     where tgrelid = 'auth.users'::regclass
       and tgname = 'on_auth_user_created';
    if v_n <> 0 then
      raise exception 'V4 FALLO: el trigger on_auth_user_created sigue activo'
        using errcode = '23514';
    end if;
  end if;

  -- 6.5 El esquema `public` se conserva (PostgREST/Supabase lo esperan).
  select count(*) into v_n from pg_namespace where nspname = 'public';
  if v_n <> 1 then
    raise exception 'V5 FALLO: desapareció el esquema public' using errcode = '23514';
  end if;

  -- 6.6 Las garantías del núcleo que dependen de `btree_gist` siguen en pie.
  select count(*) into v_n
    from pg_constraint
   where contype = 'x' and connamespace = 'nucleo'::regnamespace;
  if v_n <> 4 then
    raise exception 'V6 FALLO: quedan % de 4 EXCLUDE en nucleo', v_n
      using errcode = '23514';
  end if;
  if not exists (select 1 from pg_extension where extname = 'btree_gist') then
    raise exception 'V6 FALLO: se perdió la extensión btree_gist' using errcode = '23514';
  end if;

  raise notice 'V1-V6 OK: public sin objetos propios, auth.users sin trigger, nucleo con sus 4 EXCLUDE';
end
$$;

commit;
