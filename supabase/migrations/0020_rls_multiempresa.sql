-- ============================================================================
-- TRANSTEI — Migración 0020
-- Aislamiento multiempresa REAL en PostgreSQL (RLS con políticas + rol de app)
-- ============================================================================
--
-- OBJETIVO
--   Convertir las 31 tablas de `nucleo` —hoy con RLS habilitado y CERO
--   políticas (F0: docs/qa/informes/f0-wp3-deriva-modelo.md §0.3)— en un
--   aislamiento por empresa que PostgreSQL impone, no que el servicio promete.
--   Para eso hacen falta las TRES piezas, en este orden: un rol sin BYPASSRLS,
--   un contexto de empresa por transacción y políticas USING + WITH CHECK.
--   Sin la primera, las políticas son decorativas; sin la segunda, la política
--   no sabe qué empresa es la actual; sin la tercera, no hay filtro.
--
-- INVARIANTES QUE IMPONE (docs/datos/invariantes.md INV-T01)
--   INV-T01  Con el rol de la aplicación, toda lectura y escritura sobre
--            `nucleo.*` queda restringida a la empresa del contexto de la
--            transacción. Sin contexto válido: 0 filas (fail-closed).
--
-- DECISIONES DE DISEÑO (leer antes de "arreglar" esto)
--   1. ROL DEDICADO. `tei_app`: LOGIN, NOINHERIT, NOSUPERUSER, NOBYPASSRLS,
--      NOCREATEDB, NOCREATEROLE, NOREPLICATION. No es dueño de nada. La
--      migración NO define contraseña: eso es un secreto de despliegue
--      (`ALTER ROLE tei_app PASSWORD '…'` fuera del repo). Sin contraseña, el
--      rol solo puede entrar por socket local con `trust`/`peer` (desarrollo).
--   2. CONTEXTO POR TRANSACCIÓN: `app.empresa_id` (uuid como texto) fijado con
--      `set_config('app.empresa_id', :id, true)` / `SET LOCAL`. El `true` de
--      `set_config` (is_local) es lo que hace que el valor muera en el COMMIT:
--      una conexión reutilizada del pool NO hereda la empresa anterior.
--      NO se usa `nucleo.auth_id` para la empresa porque ese GUC ya tiene otro
--      dueño (auditoría) y se fija por servicio, no por request.
--   3. Se descartó usar los claims del JWT de Supabase (`auth.jwt()`): el
--      backend valida el JWT él mismo y no lo entrega a PostgreSQL; depender de
--      `request.jwt.claims` obligaría a propagar el token completo hasta la
--      conexión, y el pool en modo transacción lo haría más frágil, no menos.
--      El GUC propio tiene el mismo efecto con menos superficie y ya se usa
--      (`set_config('nucleo.auth_id'/'nucleo.request_id', …, true)`).
--   4. Se descartó "seguir con `postgres` + FORCE RLS": `postgres` tiene
--      `rolbypassrls = true`, y BYPASSRLS gana sobre FORCE (verificado en
--      supabase/tests: con FORCE activo, `postgres` sigue viendo las 553 filas
--      de `nucleo.viajes`). FORCE se activa igual, como defensa en profundidad
--      para el día en que otro rol SIN bypass sea dueño de las tablas. No
--      neutraliza a `postgres` ni a `service_role`.
--   5. Políticas `TO PUBLIC` (no `TO tei_app`): cualquier rol futuro que reciba
--      GRANT sobre `nucleo` queda automáticamente filtrado. Un rol sin GRANT no
--      ve nada. Los dos caminos son fail-closed; PUBLIC evita el olvido.
--   6. Excepciones deliberadas y acotadas (sin datos de tenant):
--        - `nucleo.transiciones_viaje`: catálogo global de estados. SELECT para
--          todos; INSERT/UPDATE/DELETE denegados (lo gobiernan las migraciones).
--        - `nucleo.cutover_control`: fila única de control del cutover.
--          SELECT y UPDATE para todos; INSERT/DELETE denegados (la fila la crea
--          0014; `id` es boolean, no puede haber una segunda).
--        - `nucleo.empresas` y `nucleo.usuarios_empresa`: además de la empresa
--          actual, se permite LEER la empresa y las membresías del propio
--          `auth_id` (`GET /nucleo/mis-empresas`, api.py:69, no tiene
--          X-Empresa-ID). Es la única lectura "cruzada" permitida y no expone
--          datos de tenant: solo empresas a las que el usuario ya pertenece.
--          Escritura: solo la empresa actual. Crear una empresa nueva NO es una
--          operación de la app (la hacen seed/cutover con `postgres`).
--        - `nucleo.auditoria`: `empresa_id` es nullable, pero la política exige
--          `empresa_id = ctx` para leer e insertar. Las filas con `empresa_id`
--          NULL (si alguna vez existen) quedan visibles solo para el dueño.
--          El trigger `fn_auditoria` es SECURITY DEFINER: sigue escribiendo.
--
-- ALCANCE / NO ALCANCE
--   · Solo `nucleo`. `public` (legacy) NO se toca: no tiene `empresa_id` y 17
--     de sus tablas tienen RLS habilitado sin políticas (verificado). Un rol
--     sin BYPASSRLS vería 0 filas en el legacy ⇒ el legacy NO puede pasar a
--     `tei_app` sin un ADR; ver docs/datos/rls-multiempresa.md §5.
--   · No cambia dueños de tabla, no crea índices (ver nota de `auditoria`).
--   · No se aplica a la base de la app desde este archivo: lo hace el
--     orquestador con autorización explícita.
--
-- PRECONDICIONES (ejecutar ANTES; deben devolver 0 filas)
--   P1  Políticas preexistentes en `nucleo` (solo se esperan las de 0020 en un
--       re-run):
--         select tablename, policyname from pg_policies where schemaname='nucleo';
--   P2  Filas de tenant con `empresa_id` NULL (quedarían invisibles para la app):
--         do $$ declare r record; n bigint; begin
--           for r in select table_name from information_schema.columns
--                     where table_schema='nucleo' and column_name='empresa_id' loop
--             execute format('select count(*) from nucleo.%I where empresa_id is null',
--                            r.table_name) into n;
--             if n > 0 then raise notice 'P2 % -> % filas NULL', r.table_name, n; end if;
--           end loop; end $$;
--       Resultado esperado: 0 avisos (verificado en tei_test).
--   P3  Tablas con `empresa_id` sin índice cuyo prefijo sea `empresa_id`
--       (el filtro de la política debe poder usar índice):
--         select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
--          where n.nspname='nucleo' and c.relkind='r'
--            and exists (select 1 from information_schema.columns col
--                         where col.table_schema='nucleo' and col.table_name=c.relname
--                           and col.column_name='empresa_id')
--            and not exists (select 1 from pg_index i
--                             where i.indrelid=c.oid and i.indkey[0] = (
--                               select attnum from pg_attribute
--                                where attrelid=c.oid and attname='empresa_id'));
--       Resultado esperado: 0 filas.
--   P4  `nucleo.auditoria` con `empresa_id` NULL (permitido, pero hay que
--       saberlo: esas filas pasan a ser solo del dueño):
--         select count(*) from nucleo.auditoria where empresa_id is null;
--   P5  `nucleo.reservas_recurso` apuntando a un viaje de otra empresa
--       (INV-T02, FK simple en 0004:727-728 — no es fuga bajo RLS, es deuda):
--         select count(*) from nucleo.reservas_recurso r
--           join nucleo.viajes v on v.id = r.viaje_id
--          where v.empresa_id <> r.empresa_id;
--   P6  El rol `tei_app` no existe o existe sin membresías:
--         select r.rolname, m.roleid from pg_auth_members m
--           join pg_roles r on r.oid = m.member where r.rolname = 'tei_app';
--   Si alguna devuelve filas: REPORTAR, no borrar ni "arreglar" aquí.
--
-- IMPACTO Y LOCKS
--   · CREATE POLICY / DROP POLICY / ALTER TABLE … FORCE / GRANT / REVOKE son
--     cambios de catálogo: sin reescritura de tabla, sin escaneo, sin índices.
--     Cada sentencia toma ACCESS EXCLUSIVE sobre su tabla y, al ir todo en una
--     transacción, los locks se retienen hasta el COMMIT. Con los tamaños
--     actuales (máx. `auditoria` ~20.5k filas) el bloqueo total es de
--     milisegundos; en una base grande, igual: no depende del volumen.
--   · La app actual (rol `postgres`, BYPASSRLS) NO cambia de comportamiento:
--     es el punto central de compatibilidad y está probado (ver
--     docs/datos/rls-multiempresa.md §7.1).
--   · El rol `tei_app` es a nivel de CLÚSTER (roles no son por base). Crearlo
--     no da acceso a nada en otra base; queda inerte hasta que se le otorguen
--     GRANTs ahí.
--   · Índice recomendado (NO incluido, para no mezclar locks con esta
--     migración): `create index concurrently idx_auditoria_empresa on
--     nucleo.auditoria (empresa_id, ocurrido_en desc);` — evaluar con EXPLAIN
--     sobre volumen real antes de crearlo.
--
-- ROLLBACK (ver docs/datos/rls-multiempresa.md §8)
--   Núcleo del rollback: borrar las políticas de `nucleo`, quitar FORCE,
--   revocar GRANTs y (opcional) `drop role tei_app`. No borra datos.
--   Irreversible solo si ya se cambió el backend a `tei_app`: hay que volver
--   el rol de conexión a `postgres` en el mismo despliegue.
--
-- ORDEN DE DESPLIEGUE (handoff a `backend`, ver §9 del documento)
--   1) esta migración (inerte para la app actual);
--   2) backend: fijar `app.empresa_id` y `nucleo.auth_id` por request;
--   3) backend: cambiar `DATABASE_URL` a `tei_app`;
--   4) verificar y solo entonces considerar cerrado RA-03.
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. Rol de aplicación
-- ----------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'tei_app') then
    create role tei_app;
  end if;
end
$$;

-- Idempotente. `nosuperuser` se omite a propósito: solo un superusuario puede
-- fijar ese atributo, y `supabase db reset` aplica como `postgres` (CREATEROLE,
-- no superuser). El rol nace NOSUPERUSER por defecto; en una base existente lo
-- garantiza `scripts/bootstrap_db_roles.sh` (supabase_admin).
do $$
begin
  begin
    alter role tei_app with
      login
      noinherit
      nobypassrls
      nocreatedb
      nocreaterole
      noreplication
      connection limit -1;
  exception when insufficient_privilege then
    raise notice '0020: sin privilegios para fijar atributos de tei_app; se asume bootstrap previo.';
  end;
end
$$;

comment on role tei_app is
  'Rol de aplicación del núcleo (0020). Sin BYPASSRLS: toda lectura/escritura '
  'en nucleo queda filtrada por app.empresa_id. Password fuera del repo.';

-- ----------------------------------------------------------------------------
-- 2. Funciones de contexto
--    Deben ser tolerantes: un GUC ausente o basura devuelve NULL (0 filas),
--    nunca error. Un `''::uuid` lanzaría 22P02 dentro de cada política.
-- ----------------------------------------------------------------------------
create or replace function nucleo.ctx_empresa()
returns uuid
language sql
stable
set search_path = pg_catalog
as $$
  select case
           when v.valor ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
             then v.valor::uuid
           else null
         end
    from (select coalesce(nullif(current_setting('app.empresa_id', true), ''), '')
                 as valor) as v
$$;

comment on function nucleo.ctx_empresa() is
  'Empresa del contexto de la transacción (GUC app.empresa_id). NULL si falta o '
  'es inválido ⇒ las políticas RLS devuelven 0 filas (fail-closed).';

create or replace function nucleo.ctx_auth_id()
returns uuid
language sql
stable
set search_path = pg_catalog
as $$
  select case
           when v.valor ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
             then v.valor::uuid
           else null
         end
    from (select coalesce(nullif(current_setting('nucleo.auth_id', true), ''), '')
                 as valor) as v
$$;

comment on function nucleo.ctx_auth_id() is
  'auth_id del contexto (GUC nucleo.auth_id, ya usado por auditoría). NULL si '
  'falta ⇒ solo se ven las empresas de la empresa actual.';

-- Empresas del usuario autenticado, para GET /nucleo/mis-empresas.
-- SECURITY DEFINER: lee usuarios_empresa sin pasar por su política (evita
-- recursión y permite resolver antes de tener empresa). Deriva el usuario del
-- GUC, NUNCA de un parámetro: un parámetro sería un enumerador de tenants.
create or replace function nucleo.empresas_del_usuario()
returns setof uuid
language sql
stable
security definer
set search_path = pg_catalog, nucleo
as $$
  select u.empresa_id
    from nucleo.usuarios_empresa u
   where u.auth_id = nucleo.ctx_auth_id()
     and u.activo
$$;

comment on function nucleo.empresas_del_usuario() is
  'Empresas activas del auth_id del contexto. Devuelve vacío si nucleo.auth_id '
  'no está fijado. Usada solo por la política SELECT de nucleo.empresas.';

revoke all on function nucleo.empresas_del_usuario() from public;
grant execute on function nucleo.empresas_del_usuario() to tei_app;

-- ----------------------------------------------------------------------------
-- 3. GRANTs mínimos
--    Base: mismo conjunto que hoy tiene service_role en la base de la app
--    (SELECT/INSERT/UPDATE; sin DELETE en ninguna tabla; auditoría y
--    viaje_eventos solo SELECT/INSERT). Verificado con has_table_privilege en
--    docs/datos/rls-multiempresa.md §4.2.
-- ----------------------------------------------------------------------------
grant usage on schema nucleo to tei_app;

grant select, insert, update on all tables in schema nucleo to tei_app;
grant usage, select on all sequences in schema nucleo to tei_app;
grant execute on all functions in schema nucleo to tei_app;

-- Append-only: ni UPDATE ni DELETE (ni TRUNCATE).
revoke all on table nucleo.auditoria from tei_app;
grant select, insert on table nucleo.auditoria to tei_app;

revoke all on table nucleo.viaje_eventos from tei_app;
grant select, insert on table nucleo.viaje_eventos to tei_app;

-- Catálogo global: solo lectura.
revoke all on table nucleo.transiciones_viaje from tei_app;
grant select on table nucleo.transiciones_viaje to tei_app;

-- Control del cutover: la fila la crea 0014; la app solo la lee y la actualiza.
revoke all on table nucleo.cutover_control from tei_app;
grant select, update on table nucleo.cutover_control to tei_app;

-- ----------------------------------------------------------------------------
-- 4. Políticas de tenant (genéricas)
--    Todas las tablas con `empresa_id` salvo las tres con política especial
--    (`empresas`, `usuarios_empresa`, `auditoria`).
-- ----------------------------------------------------------------------------
do $$
declare
  r record;
begin
  for r in
    select c.relname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'nucleo'
       and c.relkind = 'r'
       and c.relname not in ('empresas', 'usuarios_empresa', 'auditoria')
       and exists (
             select 1 from information_schema.columns col
              where col.table_schema = 'nucleo'
                and col.table_name = c.relname
                and col.column_name = 'empresa_id')
     order by c.relname
  loop
    execute format('drop policy if exists tenant_empresa on nucleo.%I', r.relname);
    execute format(
      'create policy tenant_empresa on nucleo.%I for all to public '
      'using (empresa_id = nucleo.ctx_empresa()) '
      'with check (empresa_id = nucleo.ctx_empresa())', r.relname);
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 5. Políticas especiales
-- ----------------------------------------------------------------------------

-- 5.1 empresas: la empresa actual + las empresas del propio usuario (lectura).
drop policy if exists empresas_lectura on nucleo.empresas;
create policy empresas_lectura on nucleo.empresas
  for select to public
  using (
    id = nucleo.ctx_empresa()
    or id in (select nucleo.empresas_del_usuario())
  );

drop policy if exists empresas_escritura on nucleo.empresas;
create policy empresas_escritura on nucleo.empresas
  for all to public
  using (id = nucleo.ctx_empresa())
  with check (id = nucleo.ctx_empresa());

comment on policy empresas_escritura on nucleo.empresas is
  'Alta de empresa NO es operación de la app (WITH CHECK id = empresa actual). '
  'El alta la hacen seed/cutover con un rol privilegiado.';

-- 5.2 usuarios_empresa: membresías de la empresa actual + las propias.
drop policy if exists usuarios_empresa_lectura on nucleo.usuarios_empresa;
create policy usuarios_empresa_lectura on nucleo.usuarios_empresa
  for select to public
  using (
    empresa_id = nucleo.ctx_empresa()
    or auth_id = nucleo.ctx_auth_id()
  );

drop policy if exists usuarios_empresa_escritura on nucleo.usuarios_empresa;
create policy usuarios_empresa_escritura on nucleo.usuarios_empresa
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

-- 5.3 auditoria: append-only, filtrada por empresa.
drop policy if exists auditoria_lectura on nucleo.auditoria;
create policy auditoria_lectura on nucleo.auditoria
  for select to public
  using (empresa_id = nucleo.ctx_empresa());

drop policy if exists auditoria_insercion on nucleo.auditoria;
create policy auditoria_insercion on nucleo.auditoria
  for insert to public
  with check (empresa_id = nucleo.ctx_empresa());

comment on policy auditoria_insercion on nucleo.auditoria is
  'Las filas que escribe el trigger fn_auditoria (SECURITY DEFINER, dueño con '
  'BYPASSRLS) no pasan por esta política. Un INSERT directo de la app debe '
  'declarar la empresa del contexto.';

-- 5.4 transiciones_viaje: catálogo global de estados (sin empresa).
drop policy if exists transiciones_lectura on nucleo.transiciones_viaje;
create policy transiciones_lectura on nucleo.transiciones_viaje
  for select to public
  using (true);

comment on policy transiciones_lectura on nucleo.transiciones_viaje is
  'Catálogo global: no contiene datos de tenant. Sin política de escritura y sin '
  'GRANT: solo las migraciones lo modifican.';

-- 5.5 cutover_control: fila única de control (sin empresa).
drop policy if exists cutover_lectura on nucleo.cutover_control;
create policy cutover_lectura on nucleo.cutover_control
  for select to public
  using (true);

drop policy if exists cutover_actualizacion on nucleo.cutover_control;
create policy cutover_actualizacion on nucleo.cutover_control
  for update to public
  using (true)
  with check (true);

comment on policy cutover_actualizacion on nucleo.cutover_control is
  'Control global de cutover: no tiene empresa. La autorización (rol admin) es '
  'del backend; la base impone que solo exista una fila (id boolean) y que no '
  'se cree ni se borre desde la app.';

-- ----------------------------------------------------------------------------
-- 6. FORCE ROW LEVEL SECURITY
--    No afecta a `postgres`/`service_role` (BYPASSRLS gana sobre FORCE). Es
--    defensa en profundidad para dueños futuros sin bypass.
-- ----------------------------------------------------------------------------
do $$
declare
  r record;
begin
  for r in
    select c.relname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'nucleo' and c.relkind = 'r'
     order by c.relname
  loop
    execute format('alter table nucleo.%I force row level security', r.relname);
  end loop;
end
$$;

comment on schema nucleo is
  'Núcleo operacional ERP Transportes TEI: multiempresa, viajes, disponibilidad '
  'y cumplimiento. Desde 0020: RLS con políticas por empresa (app.empresa_id) y '
  'rol de aplicación tei_app sin BYPASSRLS.';

commit;

-- ============================================================================
-- VERIFICACIÓN POST (ejecutar con el rol de la app, nunca con postgres)
--   1) 0 filas visibles sin contexto:
--        begin; select count(*) from nucleo.viajes; rollback;            --> 0
--   2) Solo la empresa del contexto:
--        begin; select set_config('app.empresa_id', '<A>', true);
--        select count(*) from nucleo.viajes;                              --> solo A
--        insert into nucleo.clientes (empresa_id, ...) values ('<B>', …); --> 42501
--   3) El GUC no sobrevive al COMMIT (pool):
--        begin; set local app.empresa_id = '<A>'; commit;
--        select count(*) from nucleo.viajes;                              --> 0
-- ============================================================================
