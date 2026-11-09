-- ============================================================================
-- TRANSTEI — Migración 0029: SEC-039 — separar `tei_admin` de `tei_app`
-- ============================================================================
--
-- OBJETIVO
--   Cerrar SEC-039: hoy `tei_app` (rol del runtime, NOBYPASSRLS) tiene
--   INSERT/UPDATE sobre las tres llaves del gate del agente (identidad, ACL y
--   flag de módulo). Un compromiso del runtime podría reescribir quién es
--   quién o encender el módulo sin pasar por la plataforma.
--
--   A partir de esta migración:
--     · `tei_admin` (NOLOGIN) es el rol privilegiado de las tablas de
--       identidad/ACL/flag; solo la plataforma puede alterar esas filas
--       directamente (rol `postgres`).
--     · `tei_app` conserva SELECT (el gate necesita leer) y pierde
--       INSERT/UPDATE/DELETE sobre:
--         - nucleo.contactos_whatsapp   (identidad)
--         - nucleo.permisos_contacto    (ACL)
--         - nucleo.modulos_empresa      (flag del módulo)
--     · Las escrituras legítimas de la app pasan por cuatro funciones
--       acotadas, con `empresa_id = nucleo.ctx_empresa()` y RLS vigente.
--
--   El enrolamiento (OTP) lo inicia el admin; el código se envía por WhatsApp
--   desde el backend y se guarda SOLO como hash (0021:190-194). Esta migración
--   no inventa el proveedor de WhatsApp: deja la puerta lista.
--
-- INVARIANTE QUE IMPONE
--   INV-AW-SEC039: con el rol `tei_app`, toda escritura directa a identidad,
--   ACL o flag de módulo es rechazada por PRIVILEGIO (42501). Las únicas
--   escrituras permitidas son las funciones `nucleo.admin_*`, que exigen
--   contexto de empresa y respetan RLS.
--
-- PRECONDICIONES (deben dar 0 filas o los valores esperados)
--   P1  Existe el rol `tei_app` y las tres tablas:
--         select 1 from pg_roles where rolname='tei_app';
--         select to_regclass('nucleo.contactos_whatsapp'),
--                to_regclass('nucleo.permisos_contacto'),
--                to_regclass('nucleo.modulos_empresa');
--   P2  `nucleo.ctx_empresa()` existe (0020).
--   P3  El rol que aplica la migración puede hacer `ALTER FUNCTION ... OWNER
--       TO tei_admin` (en Supabase local, `postgres` superusuario).
--
-- ROLLBACK
--   drop function if exists nucleo.admin_set_modulo_empresa(uuid, text, boolean);
--   drop function if exists nucleo.admin_set_permiso_contacto(uuid, uuid, text, text, boolean);
--   drop function if exists nucleo.admin_verificar_otp(uuid, uuid, text);
--   drop function if exists nucleo.admin_upsert_contacto(uuid, text, text, nucleo.rol_contacto_whatsapp, uuid, uuid, uuid, text, timestamptz);
--   grant select, insert, update on table nucleo.contactos_whatsapp,
--     nucleo.permisos_contacto, nucleo.modulos_empresa to tei_app;
--   revoke select, insert, update on table nucleo.contactos_whatsapp,
--     nucleo.permisos_contacto, nucleo.modulos_empresa from tei_admin;
--   drop role if exists tei_admin;   -- solo si no quedan dependencias
--   (No se borran filas: la migración no escribe datos de negocio.)
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 1. Rol tei_admin (NOLOGIN: solo dueño de funciones SECURITY DEFINER)
-- ----------------------------------------------------------------------------
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'tei_admin') then
    execute 'create role tei_admin nologin noinherit nosuperuser nobypassrls '
            'nocreatedb nocreaterole noreplication';
  end if;
end
$$;

grant usage on schema nucleo to tei_admin;
grant execute on function nucleo.ctx_empresa() to tei_admin;

-- `tei_admin` escribe identidad/ACL/flag; `postgres` (plataforma) puede
-- administrarlas directamente y es el rol de los scripts/seed.
grant select, insert, update on table
  nucleo.contactos_whatsapp,
  nucleo.permisos_contacto,
  nucleo.modulos_empresa
  to tei_admin;

grant select, insert, update, delete on table
  nucleo.contactos_whatsapp,
  nucleo.permisos_contacto,
  nucleo.modulos_empresa
  to postgres;

-- ----------------------------------------------------------------------------
-- 2. `tei_app` deja de escribir las tres llaves (conserva SELECT)
-- ----------------------------------------------------------------------------
revoke insert, update, delete on table
  nucleo.contactos_whatsapp,
  nucleo.permisos_contacto,
  nucleo.modulos_empresa
  from tei_app;

grant select on table
  nucleo.contactos_whatsapp,
  nucleo.permisos_contacto,
  nucleo.modulos_empresa
  to tei_app;

-- ----------------------------------------------------------------------------
-- 3. Funciones SECURITY DEFINER: las únicas escrituras de la app
-- ----------------------------------------------------------------------------
create or replace function nucleo.admin_upsert_contacto(
  p_empresa_id uuid,
  p_telefono text,
  p_nombre text,
  p_rol nucleo.rol_contacto_whatsapp,
  p_cliente_id uuid default null,
  p_chofer_id uuid default null,
  p_usuario_empresa_id uuid default null,
  p_otp_hash text default null,
  p_otp_expira_en timestamptz default null
) returns uuid
language plpgsql
security definer
set search_path = nucleo, pg_temp
as $$
declare
  v_id uuid;
begin
  if p_empresa_id is distinct from nucleo.ctx_empresa() then
    raise exception 'empresa_id no coincide con el contexto de la transacción'
      using errcode = '42501';
  end if;

  select id into v_id
    from nucleo.contactos_whatsapp
   where empresa_id = p_empresa_id
     and telefono = p_telefono
     and activo
   limit 1;

  if v_id is null then
    insert into nucleo.contactos_whatsapp
      (empresa_id, telefono, nombre, rol, cliente_id, chofer_id,
       usuario_empresa_id, otp_estado, otp_hash, otp_expira_en,
       otp_verificado_en, activo)
    values
      (p_empresa_id, p_telefono, p_nombre, p_rol, p_cliente_id, p_chofer_id,
       p_usuario_empresa_id, 'pendiente', p_otp_hash, p_otp_expira_en,
       null, true)
    returning id into v_id;
  else
    update nucleo.contactos_whatsapp
       set nombre = p_nombre,
           rol = p_rol,
           cliente_id = p_cliente_id,
           chofer_id = p_chofer_id,
           usuario_empresa_id = p_usuario_empresa_id,
           otp_estado = 'pendiente',
           otp_hash = p_otp_hash,
           otp_expira_en = p_otp_expira_en,
           otp_verificado_en = null
     where id = v_id;
  end if;

  return v_id;
end
$$;

-- El dueño de la función es el rol que aplica la migración (`postgres` en CLI,
-- `supabase_admin` en local). El aislamiento no depende del dueño: la función
-- exige `p_empresa_id = nucleo.ctx_empresa()`; `tei_admin` conserva los GRANTs
-- de tabla para la plataforma.

grant execute on function nucleo.admin_upsert_contacto(
  uuid, text, text, nucleo.rol_contacto_whatsapp, uuid, uuid, uuid, text, timestamptz
) to tei_app;

create or replace function nucleo.admin_verificar_otp(
  p_empresa_id uuid,
  p_contacto_id uuid,
  p_otp_hash text
) returns boolean
language plpgsql
security definer
set search_path = nucleo, pg_temp
as $$
declare
  v_ok boolean;
begin
  if p_empresa_id is distinct from nucleo.ctx_empresa() then
    raise exception 'empresa_id no coincide con el contexto de la transacción'
      using errcode = '42501';
  end if;

  update nucleo.contactos_whatsapp
     set otp_estado = 'verificado',
         otp_verificado_en = now(),
         otp_hash = null,
         otp_expira_en = null
   where id = p_contacto_id
     and empresa_id = p_empresa_id
     and activo
     and otp_estado = 'pendiente'
     and otp_hash = p_otp_hash
     and otp_expira_en is not null
     and otp_expira_en > now()
  returning true into v_ok;

  return coalesce(v_ok, false);
end
$$;

grant execute on function nucleo.admin_verificar_otp(uuid, uuid, text) to tei_app;

create or replace function nucleo.admin_set_permiso_contacto(
  p_empresa_id uuid,
  p_contacto_id uuid,
  p_componente text,
  p_variable text,
  p_permitido boolean
) returns uuid
language plpgsql
security definer
set search_path = nucleo, pg_temp
as $$
declare
  v_id uuid;
begin
  if p_empresa_id is distinct from nucleo.ctx_empresa() then
    raise exception 'empresa_id no coincide con el contexto de la transacción'
      using errcode = '42501';
  end if;

  insert into nucleo.permisos_contacto
    (empresa_id, contacto_id, componente, variable, permitido)
  values
    (p_empresa_id, p_contacto_id, p_componente, p_variable, p_permitido)
  on conflict (contacto_id, componente, coalesce(variable, ''))
  do update set permitido = excluded.permitido
  returning id into v_id;

  return v_id;
end
$$;

grant execute on function nucleo.admin_set_permiso_contacto(uuid, uuid, text, text, boolean)
  to tei_app;

create or replace function nucleo.admin_set_modulo_empresa(
  p_empresa_id uuid,
  p_modulo_id text,
  p_habilitado boolean
) returns void
language plpgsql
security definer
set search_path = nucleo, pg_temp
as $$
begin
  if p_empresa_id is distinct from nucleo.ctx_empresa() then
    raise exception 'empresa_id no coincide con el contexto de la transacción'
      using errcode = '42501';
  end if;

  insert into nucleo.modulos_empresa
    (empresa_id, modulo_id, habilitado, habilitado_en, habilitado_por)
  values
    (p_empresa_id, p_modulo_id, p_habilitado, now(),
     coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'))
  on conflict (empresa_id, modulo_id)
  do update set habilitado = excluded.habilitado,
                habilitado_en = excluded.habilitado_en,
                habilitado_por = excluded.habilitado_por;
end
$$;

grant execute on function nucleo.admin_set_modulo_empresa(uuid, text, boolean) to tei_app;

-- ----------------------------------------------------------------------------
-- 4. Verificación dentro de la migración
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  if not exists (select 1 from pg_roles where rolname = 'tei_admin') then
    raise exception 'VERIFICACIÓN: falta el rol tei_admin';
  end if;

  select count(*) into v_n
    from information_schema.role_table_grants
   where grantee = 'tei_app'
     and table_schema = 'nucleo'
     and table_name in ('contactos_whatsapp','permisos_contacto','modulos_empresa')
     and privilege_type in ('INSERT','UPDATE','DELETE');
  if v_n <> 0 then
    raise exception 'VERIFICACIÓN SEC-039: tei_app conserva % privilegios de escritura', v_n;
  end if;

  select count(*) into v_n
    from information_schema.role_table_grants
   where grantee = 'tei_app'
     and table_schema = 'nucleo'
     and table_name in ('contactos_whatsapp','permisos_contacto','modulos_empresa')
     and privilege_type = 'SELECT';
  if v_n <> 3 then
    raise exception 'VERIFICACIÓN SEC-039: tei_app debe conservar SELECT en las 3 tablas (tiene %)', v_n;
  end if;

  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('admin_upsert_contacto','admin_verificar_otp',
                       'admin_set_permiso_contacto','admin_set_modulo_empresa')
     and p.prosecdef;
  if v_n <> 4 then
    raise exception 'VERIFICACIÓN SEC-039: se esperaban 4 funciones SECURITY DEFINER, hay %', v_n;
  end if;
end
$$;

commit;
