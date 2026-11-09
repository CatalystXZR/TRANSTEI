-- ============================================================================
-- TRANSTEI — Migración 0031: memoria del chat in-app del agente (Ola 3)
-- ============================================================================
--
-- OBJETIVO
--   Persistir la memoria del chat in-app del dueño con dos agentes LLM
--   (`gerente`, `secretaria`) SIN reutilizar las tablas del agente WhatsApp:
--
--     1. nucleo.agente_chat_conversaciones  sesión activa por
--        (empresa, usuario_empresa, agente), con resumen compactado.
--     2. nucleo.agente_chat_mensajes        turnos del chat con roles LLM
--        (user/assistant/tool/system), tool_calls y clave de idempotencia.
--
--   POR QUÉ TABLAS NUEVAS Y NO `nucleo.conversaciones` /
--   `nucleo.conversacion_mensajes` (0021:275-356):
--     · `conversaciones.contacto_id uuid NOT NULL` → FK a
--       `contactos_whatsapp` (0021:290-292). Un usuario del núcleo no es un
--       contacto de WhatsApp; forzarlo exigiría un contacto ficticio por
--       usuario (segunda identidad, ambigüedad de tenant).
--     · `conversacion_mensajes` exige `contacto_id` y
--       `ck_mensaje_entrante_idempotente` (0021:338-340) amarra los entrantes
--       a `wa_message_id`; el chat in-app no tiene webhook de WhatsApp.
--     · El chat necesita roles LLM y `tool_calls`/`tool_call_id`, que el
--       modelo WhatsApp no tiene (allí la modalidad es texto/voz/imagen/pdf).
--   NO se alteran `conversaciones`, `conversacion_mensajes` ni `solicitudes`.
--
-- REQUISITO DE ORDEN
--   Después de 0004 (fn_touch/fn_version, gen_random_uuid), 0020 (rol
--   `tei_app`, `nucleo.ctx_empresa()`) y 0021 (índice único
--   `uq_usuarios_empresa_empresa`). Si el índice no existe, esta migración
--   aborta: no lo crea a escondidas.
--
-- PRECONDICIONES (se evalúan antes de crear nada; abortan con 23514)
--   P1  Estado parcial prohibido: si existe SOLO una de las dos tablas, aborta
--       y reporta. Si existen ambas, es re-ejecución: NOTICE y ningún objeto
--       duplicado (todas las sentencias son IF NOT EXISTS / OR REPLACE /
--       DROP POLICY IF EXISTS).
--   P2  `nucleo.ctx_empresa()` existe; rol `tei_app` existe y tiene USAGE
--       sobre `nucleo`.
--   P3  `nucleo.usuarios_empresa` tiene un índice/constraint ÚNICO sobre
--       `(empresa_id, id)` (0021:170-171). Sin eso la FK compuesta no compila.
--
-- IMPACTO EN DATOS Y LOCKS
--   · ADD-only: 2 tablas nuevas vacías, sus índices, triggers, políticas y
--     GRANTs. Ningún UPDATE/DELETE/backfill sobre filas existentes.
--   · `CREATE TABLE`/`CREATE INDEX` toman locks solo sobre objetos NUEVOS;
--     las FKs apuntan a `empresas` y `usuarios_empresa` sin reescribirlas.
--   · `ENABLE/FORCE RLS`, `CREATE POLICY` y `GRANT` sobre tablas nuevas:
--     instantáneos.
--   · Ningún escritor actual conoce estas tablas: el backend y el frontend
--     siguen funcionando (no se modifica ningún contrato HTTP).
--   · La migración NO siembra conversaciones ni mensajes.
--
-- COMPATIBILIDAD
--   · No cambia columnas, constraints ni permisos de tablas existentes.
--   · `tei_app` recibe SELECT/INSERT/UPDATE (sin DELETE) sobre las dos tablas;
--     `postgres` (plataforma) recibe además DELETE, como en 0030.
--
-- LO QUE ESTA MIGRACIÓN NO IMPONE (y no debe fingir)
--   · Que la conversación "cerrada" no vuelva a abrirse: `cerrada_en` es
--     informativo; el servicio decide el ciclo de vida. La base solo impide
--     DOS conversaciones activas simultáneas por (empresa, usuario, agente).
--   · Que `resumen` corresponda a los mensajes: es texto libre del runtime.
--   · La forma de `tool_calls`/`metadata`: jsonb sin catálogo (es del runtime).
--   · Que un mensaje `assistant` provenga del LLM o que `tool_call_id` exista
--     en un `tool_calls` previo: coherencia conversacional es del servicio.
--   · Auditoría por fila del chat: NO se agrega `fn_auditoria` a propósito
--     (append-only de diseño y evitar inundar `nucleo.auditoria`).
--
-- ROLLBACK
--   `supabase/tests/0031_99_rollback.sql`: drop de triggers y de las dos
--   tablas (con ellas caen PK, UNIQUE, FKs, CHECK, índices, políticas, RLS y
--   GRANTs). Pérdida: SOLO el historial de chat escrito (ninguno al aplicar).
--   `empresas`, `usuarios_empresa`, `conversaciones` (WhatsApp) y
--   `conversacion_mensajes` NO se tocan. Es re-ejecutable tras el rollback
--   (ciclo local; una migración aplicada no se edita: se crea la siguiente).
--
-- INVARIANTES (docs/datos/invariantes.md §15, prefijo INV-CHAT)
--   INV-CHAT01  Una conversación activa por (empresa, usuario_empresa, agente).
--   INV-CHAT02  `activa` y `cerrada_en` son coherentes: activa OR cerrada_en.
--   INV-CHAT03  El usuario de la conversación pertenece a la misma empresa.
--   INV-CHAT04  El mensaje pertenece a una conversación de la misma empresa.
--   INV-CHAT05  Un turno `tool` declara `tool_call_id`.
--   INV-CHAT06  Un turno deja contenido o tool_calls (tool/system exentos).
--   INV-CHAT07  Una `clave_idempotencia` no se repite dentro de la empresa.
--   INV-CHAT08  Toda fila es invisible/inescribible fuera de `app.empresa_id`.
--   INV-CHAT09  `tei_app` no puede borrar conversaciones ni mensajes (42501).
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones (P1–P3). No "arreglan" nada: abortan con mensaje.
-- ----------------------------------------------------------------------------
do $$
declare
  v_conv  regclass := to_regclass('nucleo.agente_chat_conversaciones');
  v_msg   regclass := to_regclass('nucleo.agente_chat_mensajes');
  v_n     integer;
  v_idx   text;
begin
  -- P1: estado parcial prohibido; si ambas existen, re-ejecución idempotente.
  if (v_conv is null) <> (v_msg is null) then
    raise exception
      'PRECONDICIÓN P1: estado parcial (conversaciones=%, mensajes=%); 0031 no continúa y no borra nada',
      v_conv, v_msg
      using errcode = '23514';
  end if;
  if v_conv is not null then
    raise notice 'PRECONDICIÓN P1: 0031 ya aplicada; se re-verifica sin duplicar objetos';
  end if;

  -- P2: función de contexto y rol de aplicación con USAGE.
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

  -- P3: UNIQUE (empresa_id, id) en usuarios_empresa (índice o constraint).
  select c.relname into v_idx
    from pg_index i
    join pg_class c on c.oid = i.indexrelid
   where i.indrelid = 'nucleo.usuarios_empresa'::regclass
     and i.indisunique
     and i.indpred is null
     and i.indexprs is null
     and (
       select array_agg(a.attname order by a.attname)
         from unnest(i.indkey::int2[]) as k(attnum)
         join pg_attribute a
           on a.attrelid = i.indrelid and a.attnum = k.attnum
     ) = array['empresa_id', 'id']::name[]
   limit 1;
  if v_idx is null then
    raise exception
      'PRECONDICIÓN P3: usuarios_empresa sin UNIQUE (empresa_id, id); aplicar 0021 primero'
      using errcode = '23514';
  end if;
end
$$;

-- ----------------------------------------------------------------------------
-- 1. Conversaciones del chat in-app
--    `usuario_empresa_id` + FK compuesta: la conversación no puede apuntar a
--    un usuario de otra empresa aunque se adivine el UUID.
-- ----------------------------------------------------------------------------
create table if not exists nucleo.agente_chat_conversaciones (
  id                  uuid not null default gen_random_uuid(),
  empresa_id          uuid not null,
  usuario_empresa_id  uuid not null,
  agente              text not null,
  activa              boolean not null default true,
  abierta_en          timestamptz not null default now(),
  cerrada_en          timestamptz,
  resumen             text,
  resumen_en          timestamptz,
  created_at          timestamptz not null default now(),
  created_by          text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at          timestamptz not null default now(),
  updated_by          text,
  version             integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_agente_chat_conv_empresa_id unique (empresa_id, id),
  constraint fk_agente_chat_conv_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint fk_agente_chat_conv_usuario foreign key (empresa_id, usuario_empresa_id)
    references nucleo.usuarios_empresa (empresa_id, id) on delete restrict,
  constraint ck_agente_chat_agente check (agente in ('gerente', 'secretaria')),
  constraint ck_agente_chat_conv_cierre check (activa or cerrada_en is not null)
);

comment on table nucleo.agente_chat_conversaciones is
  'Memoria del chat in-app del dueño con los agentes gerente/secretaria. '
  'Separada de nucleo.conversaciones (WhatsApp): aquí el dueño es un '
  'usuario_empresa, no un contacto de WhatsApp.';
comment on column nucleo.agente_chat_conversaciones.usuario_empresa_id is
  'Miembro de nucleo.usuarios_empresa dueño de la sesión; la FK compuesta '
  '(empresa_id, usuario_empresa_id) impide apuntar a otro tenant.';
comment on column nucleo.agente_chat_conversaciones.agente is
  'Agente LLM del chat: gerente | secretaria. La base acota el valor; el '
  'catálogo de herramientas es del servicio.';
comment on column nucleo.agente_chat_conversaciones.activa is
  'Sesión abierta. UNIQUE parcial garantiza una sola activa por '
  '(empresa, usuario, agente); cerrar exige cerrada_en (ck_agente_chat_conv_cierre).';
comment on column nucleo.agente_chat_conversaciones.resumen is
  'Resumen compactado de la sesión (texto libre del runtime). NO es fuente '
  'de verdad del negocio: los efectos pasan por las tools.';

-- Una sola conversación ACTIVA por (empresa, usuario, agente): sesiones
-- paralelas fragmentarían el contexto del chat.
create unique index if not exists uq_agente_chat_conv_activa
  on nucleo.agente_chat_conversaciones (empresa_id, usuario_empresa_id, agente)
  where activa;

create index if not exists idx_agente_chat_conv_usuario
  on nucleo.agente_chat_conversaciones
     (empresa_id, usuario_empresa_id, agente, abierta_en desc);

-- ----------------------------------------------------------------------------
-- 2. Mensajes del chat in-app (turnos con roles LLM)
--    `updated_at`/`updated_by` existen para que `nucleo.fn_touch()` (0004:74-87)
--    funcione en UPDATE: sin esas columnas el trigger fallaría con 42703. La
--    intención es append-only, pero la base no lo impone (no hay trigger de
--    inmutabilidad en el contrato).
-- ----------------------------------------------------------------------------
create table if not exists nucleo.agente_chat_mensajes (
  id                 uuid not null default gen_random_uuid(),
  empresa_id         uuid not null,
  conversacion_id    uuid not null,
  rol                text not null,
  contenido          text,
  tool_calls         jsonb,
  tool_call_id       text,
  nombre_herramienta text,
  clave_idempotencia text,
  metadata           jsonb not null default '{}'::jsonb,
  created_at         timestamptz not null default now(),
  created_by         text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at         timestamptz not null default now(),
  updated_by         text,
  version            integer not null default 1 check (version >= 1),
  primary key (id),
  constraint uq_agente_chat_msg_empresa_id unique (empresa_id, id),
  constraint fk_agente_chat_msg_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict,
  constraint fk_agente_chat_msg_conversacion foreign key (empresa_id, conversacion_id)
    references nucleo.agente_chat_conversaciones (empresa_id, id) on delete restrict,
  constraint ck_agente_chat_msg_rol check (rol in ('user', 'assistant', 'tool', 'system')),
  constraint ck_agente_chat_msg_tool_call check (rol <> 'tool' or tool_call_id is not null),
  constraint ck_agente_chat_msg_contenido check (
    contenido is not null or tool_calls is not null or rol in ('tool', 'system')
  )
);

comment on table nucleo.agente_chat_mensajes is
  'Turnos del chat in-app: contenido textual y/o tool_calls del LLM. '
  'Idempotente por (empresa_id, clave_idempotencia) para que un reintento del '
  'cliente no duplique el turno.';
comment on column nucleo.agente_chat_mensajes.rol is
  'Rol del turno LLM: user | assistant | tool | system. Un turno tool exige '
  'tool_call_id (ck_agente_chat_msg_tool_call).';
comment on column nucleo.agente_chat_mensajes.tool_calls is
  'Llamadas a herramientas emitidas por el modelo (jsonb). La base no valida '
  'su forma: el contrato es del runtime.';
comment on column nucleo.agente_chat_mensajes.clave_idempotencia is
  'Clave del cliente para no duplicar el turno; única POR EMPRESA (parcial, '
  'solo cuando no es NULL).';
comment on column nucleo.agente_chat_mensajes.metadata is
  'Metadatos del turno (tokens, modelo, latencias). No dupliques datos '
  'sensibles de tenant aquí.';

create unique index if not exists uq_agente_chat_msg_idempotencia
  on nucleo.agente_chat_mensajes (empresa_id, clave_idempotencia)
  where clave_idempotencia is not null;

create index if not exists idx_agente_chat_msg_conversacion
  on nucleo.agente_chat_mensajes (empresa_id, conversacion_id, created_at);

-- ----------------------------------------------------------------------------
-- 3. Triggers de control (touch/version). SIN fn_auditoria: el log de chat es
--    append-only por diseño y auditar cada token inundaría nucleo.auditoria.
--    `create or replace trigger` mantiene la migración re-ejecutable.
-- ----------------------------------------------------------------------------
create or replace trigger trg_agente_chat_conv_touch
  before update on nucleo.agente_chat_conversaciones
  for each row execute function nucleo.fn_touch();
create or replace trigger trg_agente_chat_conv_version
  before update on nucleo.agente_chat_conversaciones
  for each row execute function nucleo.fn_version();

create or replace trigger trg_agente_chat_msg_touch
  before update on nucleo.agente_chat_mensajes
  for each row execute function nucleo.fn_touch();
create or replace trigger trg_agente_chat_msg_version
  before update on nucleo.agente_chat_mensajes
  for each row execute function nucleo.fn_version();

-- ----------------------------------------------------------------------------
-- 4. RLS: ENABLE + FORCE y una política `tenant_empresa` por tabla
--    (patrón 0020:273-298 / 0030:461-476). Fail-closed sin app.empresa_id.
-- ----------------------------------------------------------------------------
alter table nucleo.agente_chat_conversaciones enable row level security;
alter table nucleo.agente_chat_conversaciones force row level security;
alter table nucleo.agente_chat_mensajes enable row level security;
alter table nucleo.agente_chat_mensajes force row level security;

drop policy if exists tenant_empresa on nucleo.agente_chat_conversaciones;
create policy tenant_empresa on nucleo.agente_chat_conversaciones
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

drop policy if exists tenant_empresa on nucleo.agente_chat_mensajes;
create policy tenant_empresa on nucleo.agente_chat_mensajes
  for all to public
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());

comment on policy tenant_empresa on nucleo.agente_chat_conversaciones is
  'Aislamiento por empresa del chat in-app: sin app.empresa_id el contexto es '
  'NULL y la política devuelve 0 filas / rechaza INSERT (fail-closed).';
comment on policy tenant_empresa on nucleo.agente_chat_mensajes is
  'Aislamiento por empresa de los turnos del chat in-app (fail-closed sin '
  'app.empresa_id).';

-- ----------------------------------------------------------------------------
-- 5. GRANTs
--    tei_app: SELECT/INSERT/UPDATE, NUNCA DELETE (historial del chat).
--    postgres: rol de plataforma (patrón 0027/0030), incluido DELETE.
-- ----------------------------------------------------------------------------
grant select, insert, update on table nucleo.agente_chat_conversaciones to tei_app;
grant select, insert, update on table nucleo.agente_chat_mensajes to tei_app;

grant select, insert, update, delete on table nucleo.agente_chat_conversaciones to postgres;
grant select, insert, update, delete on table nucleo.agente_chat_mensajes to postgres;

do $$
declare
  r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on table nucleo.agente_chat_conversaciones from %I', r);
      execute format('revoke all on table nucleo.agente_chat_mensajes from %I', r);
    end if;
  end loop;
end
$$;

-- ----------------------------------------------------------------------------
-- 6. Verificación dentro de la transacción
-- ----------------------------------------------------------------------------
do $$
declare
  v_n      integer;
  v_tab    text;
  v_trg    text;
  v_filas  bigint;
begin
  -- RLS ENABLE + FORCE en las dos tablas.
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname in ('agente_chat_conversaciones', 'agente_chat_mensajes')
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 2 then
    raise exception 'VERIFICACIÓN: RLS+FORCE en % de 2 tablas', v_n
      using errcode = '23514';
  end if;

  -- Una política tenant_empresa por tabla, con ctx_empresa en USING y WITH CHECK.
  foreach v_tab in array array['agente_chat_conversaciones', 'agente_chat_mensajes'] loop
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

  -- Privilegios de tei_app: SELECT/INSERT/UPDATE sí; DELETE no.
  foreach v_tab in array array['agente_chat_conversaciones', 'agente_chat_mensajes'] loop
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

  -- Índices únicos parciales y de consulta.
  foreach v_trg in array array['uq_agente_chat_conv_activa',
                               'uq_agente_chat_msg_idempotencia',
                               'idx_agente_chat_conv_usuario',
                               'idx_agente_chat_msg_conversacion'] loop
    if to_regclass('nucleo.' || v_trg) is null then
      raise exception 'VERIFICACIÓN: falta el índice %', v_trg
        using errcode = '23514';
    end if;
  end loop;

  -- FK compuestas por empresa (una por tabla, hacia usuarios_empresa y
  -- agente_chat_conversaciones respectivamente).
  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.agente_chat_conversaciones'::regclass
     and contype = 'f' and confrelid = 'nucleo.usuarios_empresa'::regclass;
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta la FK compuesta a usuarios_empresa (hay %)', v_n
      using errcode = '23514';
  end if;
  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.agente_chat_mensajes'::regclass
     and contype = 'f' and confrelid = 'nucleo.agente_chat_conversaciones'::regclass;
  if v_n <> 1 then
    raise exception 'VERIFICACIÓN: falta la FK compuesta a agente_chat_conversaciones (hay %)', v_n
      using errcode = '23514';
  end if;

  -- Triggers por nombre (touch + version; NO hay trigger de auditoría).
  foreach v_trg in array array[
    'trg_agente_chat_conv_touch', 'trg_agente_chat_conv_version',
    'trg_agente_chat_msg_touch', 'trg_agente_chat_msg_version'
  ] loop
    select count(*) into v_n from pg_trigger where tgname = v_trg and not tgisinternal;
    if v_n <> 1 then
      raise exception 'VERIFICACIÓN: falta el trigger %', v_trg
        using errcode = '23514';
    end if;
  end loop;

  -- Sin datos de negocio sembrados.
  execute 'select count(*) from nucleo.agente_chat_conversaciones' into v_filas;
  raise notice 'VERIFICACIÓN: agente_chat_conversaciones = % fila(s)', v_filas;
  execute 'select count(*) from nucleo.agente_chat_mensajes' into v_filas;
  raise notice 'VERIFICACIÓN: agente_chat_mensajes = % fila(s)', v_filas;

  raise notice 'OK 0031: 2 tablas, FKs compuestas, 2 UNIQUE parciales, 4 triggers, RLS+FORCE, políticas y GRANTs';
end
$$;

commit;

-- ============================================================================
-- VERIFICACIÓN POST (tei_test):
--   supabase/tests/0031_01_chat.sql
--   supabase/tests/0031_02_rls_tei_app.sql
--   supabase/tests/0031_99_rollback.sql
-- NO aplicar en la base `postgres` (la app) sin autorización explícita.
-- ============================================================================
