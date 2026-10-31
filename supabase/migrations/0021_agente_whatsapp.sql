-- ============================================================================
-- TRANSTEI — Migración 0021: Módulo Agente WhatsApp (parte Núcleo, F2.5/F2.6)
-- ============================================================================
--
-- OBJETIVO
--   Crear la persistencia del módulo agente WhatsApp (ADR-0003, ADR-0004,
--   docs/negocio/agente-whatsapp-roles.md, tarea O1.1 de
--   docs/desarrollo/plan-modulo-agente-whatsapp.md):
--
--     1. nucleo.contactos_whatsapp        teléfono → empresa + rol + entidad,
--                                         estado OTP, activo (D-09/D-12 parcial)
--     2. nucleo.permisos_contacto         ACL por (contacto, componente,
--                                         variable); deny-by-default (D-09)
--     3. nucleo.conversaciones            sesión activa por contacto, cierre
--                                         por inactividad, resumen compactado
--     4. nucleo.conversacion_mensajes     mensajes multimodales con
--                                         idempotencia por wa_message_id
--     5. nucleo.solicitudes               F2.6 NO existía en ninguna migración
--                                         (grep verificado 2026-10-31): estados
--                                         pendiente/aprobada/rechazada/cancelada
--                                         con Confirmar/Rechazar/Modificar (D-10)
--     6. nucleo.hoja_ruta                 payload JSON, estado propuesto →
--                                         solicitud_creada → cargado/rechazado
--                                         (ADR-0003 §14, D-10)
--     7. nucleo.viajes.id_comercial_flete R-04: ID comercial `SQM-00001` por
--                                         (empresa, cliente), UNIQUE +
--                                         generación atómica (ADR-0003 §16, D-16)
--     8. nucleo.auditoria_consultas_agente D-17: log append-only de cada
--                                         consulta del agente (patrón de
--                                         nucleo.auditoria, 0004:880-892)
--
-- REQUISITO DE ORDEN: aplicar DESPUÉS de 0020_rls_multiempresa.sql.
--   Crea GRANTs para el rol `tei_app` (ADR-0005) y usa `nucleo.ctx_empresa`.
--   Si 0020 no fue aplicada, los GRANT fallan con error explícito: esa es la
--   defensa, no un accidente (regla R-6 del ADR-0005: toda tabla nueva en
--   `nucleo` necesita GRANT + política + FORCE o tei_app no la ve).
--
-- PRECONDICIONES (deben dar 0 filas; verificadas en tei_test 2026-10-31,
--   ver docs/datos/agente-esquema.md §2)
--   P1  Sin tablas del módulo (contactos_whatsapp, permisos_contacto,
--       conversaciones, conversacion_mensajes, solicitudes, hoja_ruta,
--       id_comercial_contador, auditoria_consultas_agente).
--   P2  Sin columna nucleo.viajes.id_comercial_flete.
--   P3  Sin tipos del módulo (rol_contacto_whatsapp, estado_otp,
--       direccion_mensaje, modalidad_mensaje, estado_procesamiento_mensaje,
--       tipo_solicitud, estado_solicitud, estado_hoja_ruta).
--   P4  Dependencia (debe dar > 0, no 0): políticas de 0020 vigentes
--       (>= 35 en tei_test). Si da 0: aplicar 0020 primero, NO improvisar aquí.
--   Las P1-P3 están defendidas dentro del SQL con `raise exception 23514`
--   para que una re-aplicación accidental falle en lugar de romper objetos.
--
-- IMPACTO EN DATOS Y LOCKS
--   · ADD-only: 8 tablas nuevas; 1 columna nullable en nucleo.viajes;
--     1 índice único en nucleo.usuarios_empresa (empresa_id, id) — imposible
--     que choque: `id` ya es PK (0004:140). Ningún UPDATE/DELETE/backfill
--     sobre filas existentes.
--   · ADD COLUMN es metadata-only (no reescribe la tabla; en PG11+ el valor
--     NULL no requiere reescritura): lock breve ACCESS EXCLUSIVE por sentencia
--     de catálogo, retención de milisegundos, independiente del volumen.
--   · El CHECK nuevo sobre viajes valida las filas existentes (NULL pasa;
--     en tei_test se midió: ver docs/datos/agente-esquema.md §2; si se aplica
--     a una base grande usar NOT VALID + VALIDATE CONSTRAINT).
--   · El legacy `public` NO se toca: ninguna sentencia referencia `public`.
--   · La app actual (rol postgres, BYPASSRLS) no cambia de comportamiento:
--     nada en el backend lee estas tablas todavía (módulo apagado, DEC-10).
--
-- COMPATIBILIDAD CON RLS (ADR-0005)
--   · Políticas TO PUBLIC según el patrón 0020:273-298, con USING + WITH
--     CHECK por `empresa_id = nucleo.ctx_empresa()` => fail-closed sin GUC.
--   · FORCE ROW LEVEL SECURITY en las 8 tablas (defensa en profundidad,
--     0020:386-400).
--   · auditoria_consultas_agente usa el patrón especial de auditoria
--     (0020:339-347): SELECT/INSERT por empresa; el trigger impide
--     UPDATE/DELETE/TRUNCATE incluso al dueño.
--   · Si ADR-0005 se ratifica tal cual, nada cambia. El wiring del rol en el
--     backend (criterio O7.1) sigue abierto y no lo resuelve esta migración.
--
-- ROLLBACK (orden inverso de dependencias)
--   Ver supabase/tests/0021_99_rollback.sql. Purga EXCLUSIVAMENTE objetos del
--   módulo: tablas nuevas, columna/indexes/check de `viajes.id_comercial_flete`,
--   índice de usuarios_empresa, tipos, funciones, triggers, políticas y
--   GRANTs de 0021. Pérdida prevista: SOLO datos de las tablas del módulo
--   (contactos, conversaciones, auditoría de consultas) — retención P-07/D-17
--   aún abierta. Cero erosión de datos de negocio (viajes, facturas, OC,
--   pagos). Antes de revertir contra una base en producción, decisión del dueño.
--
-- INVARIANTES (detalle por invariante con mecanismo/SQLSTATE/pruebas:
--   docs/datos/agente-esquema.md §3, IDs AW-01..AW-16 para handoff qa/O2)
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones defendidas (fallan con mensaje explícito; no "arreglan")
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
begin
  select count(*) into v_n from pg_tables
   where schemaname = 'nucleo' and tablename in (
     'contactos_whatsapp','permisos_contacto','conversaciones',
     'conversacion_mensajes','solicitudes','hoja_ruta',
     'id_comercial_contador','auditoria_consultas_agente');
  if v_n > 0 then
    raise exception 'PRECONDICIÓN P1: existen % tablas del módulo agente; reportar, no sobreescribir', v_n
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_attribute a
    join pg_class c on c.oid = a.attrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'viajes'
     and a.attname = 'id_comercial_flete' and a.attnum > 0;
  if v_n > 0 then
    raise exception 'PRECONDICIÓN P2: nucleo.viajes.id_comercial_flete ya existe'
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_type t join pg_namespace n on n.oid = t.typnamespace
   where n.nspname = 'nucleo' and t.typname in (
     'rol_contacto_whatsapp','estado_otp','direccion_mensaje','modalidad_mensaje',
     'estado_procesamiento_mensaje','tipo_solicitud','estado_solicitud','estado_hoja_ruta');
  if v_n > 0 then
    raise exception 'PRECONDICIÓN P3: existen % tipos del módulo agente', v_n
      using errcode = '23514';
  end if;

  select count(*) into v_n from pg_policies where schemaname = 'nucleo';
  if v_n < 35 then
    raise exception
      'PRECONDICIÓN P4: % políticas en nucleo (se esperaban >= 35 de 0020). '
      'Aplicar 0020 antes; esta migración no impone aislamiento sola.', v_n
      using errcode = '23514';
  end if;
end;
$$;

-- ----------------------------------------------------------------------------
-- 1. Tipos enumerados (ASCII, convención del repo)
--    rol_contacto_whatsapp NO reusa nucleo.rol_empresa (0004:35-38): el
--    contacto puede ser cliente/conductor sin membresía en usuarios_empresa.
--    D-09 trata "administrador o dueño" como una sola clase de operador: un
--    solo valor 'admin' evita dos estados equivalentes que el gate tendría
--    que acordar. Si el dueño quisiera distinguir, `alter type ... add value`
--    sin migración de datos. Reportado en docs/datos/agente-esquema.md §4.1.
-- ----------------------------------------------------------------------------
create type nucleo.rol_contacto_whatsapp as enum ('admin', 'cliente_final', 'conductor');
create type nucleo.estado_otp as enum ('pendiente', 'verificado');
create type nucleo.direccion_mensaje as enum ('entrante', 'saliente');
create type nucleo.modalidad_mensaje as enum ('texto', 'voz', 'imagen', 'pdf');
create type nucleo.estado_procesamiento_mensaje as enum (
  'recibido', 'procesando', 'interpretado', 'respondido', 'fallado'
);
-- Categorías extensibles; casos nuevos de negocio entran con alter type add
-- value; 'otra' absorbe lo no mapeado.
create type nucleo.tipo_solicitud as enum ('agendamiento', 'documentos', 'hoja_de_ruta', 'otra');
create type nucleo.estado_solicitud as enum ('pendiente', 'aprobada', 'rechazada', 'cancelada');
create type nucleo.estado_hoja_ruta as enum ('propuesto', 'solicitud_creada', 'cargado', 'rechazado');

-- ----------------------------------------------------------------------------
-- 2. Índice único que habilita FKs compuestas hacia usuarios_empresa
--    (patrón del núcleo VERIFICADO: unique (empresa_id, id); en
--    usuarios_empresa faltaba — 0004:139-151 solo tiene (empresa_id, auth_id)).
--    ADD-only, sin contraste posible: id ya es PK.
-- ----------------------------------------------------------------------------
create unique index uq_usuarios_empresa_empresa
  on nucleo.usuarios_empresa (empresa_id, id);

-- ----------------------------------------------------------------------------
-- 3. Contactos de WhatsApp (D-09/D-12 parcial)
--    Un teléfono ACTIVO tiene una sola fila en todo el sistema: la resolución
--    número→(empresa, rol, entidad) no puede ser ambigua (fundamento y
--    compensación en docs/datos/agente-esquema.md §4.2).
-- ----------------------------------------------------------------------------
create table nucleo.contactos_whatsapp (
  id                     uuid primary key default gen_random_uuid(),
  empresa_id             uuid not null references nucleo.empresas(id) on delete restrict,
  telefono               text not null,
  nombre                 text not null,
  rol                    nucleo.rol_contacto_whatsapp not null,
  -- Entidad según rol (patrón de nucleo.documentos, 0004:354-358): FKs
  -- compuestas por empresa; admin puede (opcional) vincular su usuario.
  cliente_id             uuid,
  chofer_id              uuid,
  usuario_empresa_id     uuid,
  -- OTP (D-12 parcial). El código nunca va en claro: solo hash.
  otp_estado             nucleo.estado_otp not null default 'pendiente',
  otp_expira_en          timestamptz,
  otp_verificado_en      timestamptz,
  otp_hash               text,
  activo                 boolean not null default true,
  created_at             timestamptz not null default now(),
  created_by             text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at             timestamptz not null default now(),
  updated_by             text,
  version                integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_contacto_cliente foreign key (empresa_id, cliente_id)
    references nucleo.clientes (empresa_id, id) on delete restrict,
  constraint fk_contacto_chofer foreign key (empresa_id, chofer_id)
    references nucleo.choferes (empresa_id, id) on delete restrict,
  constraint fk_contacto_usuario foreign key (empresa_id, usuario_empresa_id)
    references nucleo.usuarios_empresa (empresa_id, id) on delete restrict,
  constraint ck_contacto_telefono_e164 check (telefono ~ '^\+[1-9][0-9]{7,14}$'),
  constraint ck_contacto_nombre_no_vacio check (btrim(nombre) <> ''),
  constraint ck_contacto_entidad check (
    (rol = 'cliente_final' and cliente_id is not null and chofer_id is null)
    or (rol = 'conductor' and chofer_id is not null and cliente_id is null)
    or (rol = 'admin' and cliente_id is null and chofer_id is null)
  ),
  constraint ck_contacto_otp_estado check (otp_estado <> 'verificado' or otp_verificado_en is not null)
);

-- Un único contacto ACTIVO por teléfono. Parcial (WHERE activo): la revocación
-- libera el número para re-enrolarlo (D-12). GLOBAL (sin empresa_id): la
-- resolución teléfono→empresa debe ser única; dos empresas con el mismo
-- número activo = ambigüedad de identidad = fuga potencial.
create unique index uq_contactos_telefono_activo
  on nucleo.contactos_whatsapp (telefono) where activo;

create index idx_contactos_empresa
  on nucleo.contactos_whatsapp (empresa_id, activo, rol);

comment on table nucleo.contactos_whatsapp is
  'Contactos del agente WhatsApp: teléfono → empresa/rol/entidad con estado '
  'OTP. Deny-by-default: número sin contacto activo no se interpreta '
  '(ADR-0003 §5, anti-enumeración).';
comment on column nucleo.contactos_whatsapp.otp_hash is
  'Hash del código OTP vigente (estado pendiente); se descarta al verificar. '
  'La política de emisión/revocación es D-12 y vive en el backend.';

-- ----------------------------------------------------------------------------
-- 4. ACL por contacto: (componente, variable) con deny-by-default (D-09 §13)
--    1 fila por (contacto, componente, variable); variable NULL = el "botón
--    por módulo". La ABSENCIA de fila es DENY y la impone el gate del backend
--    (la base no puede obligar por ausencia); la base impone estructura,
--    unicidad y FKs por empresa.
-- ----------------------------------------------------------------------------
create table nucleo.permisos_contacto (
  id            uuid primary key default gen_random_uuid(),
  empresa_id    uuid not null references nucleo.empresas(id) on delete restrict,
  contacto_id   uuid not null,
  componente    text not null,
  variable      text,
  permitido     boolean not null,
  created_at    timestamptz not null default now(),
  created_by    text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at    timestamptz not null default now(),
  updated_by    text,
  version       integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_permiso_contacto foreign key (empresa_id, contacto_id)
    references nucleo.contactos_whatsapp (empresa_id, id) on delete restrict,
  constraint ck_permiso_componente_no_vacio check (btrim(componente) <> ''),
  constraint ck_permiso_variable_no_vacia check (variable is null or btrim(variable) <> '')
);

create unique index uq_permisos_contacto_valor
  on nucleo.permisos_contacto (contacto_id, componente, coalesce(variable, ''));
create index idx_permisos_empresa
  on nucleo.permisos_contacto (empresa_id, contacto_id);

comment on table nucleo.permisos_contacto is
  'ACL del agente por número (D-09): toggle por componente y variable '
  'administrado desde la plataforma. Ausencia de fila = sin acceso '
  '(deny-by-default); la resolución vive en el gate del backend (O2.2).';

-- ----------------------------------------------------------------------------
-- 5. Conversaciones (sesión activa + resumen compactado, ADR-0003 §3.5)
-- ----------------------------------------------------------------------------
create table nucleo.conversaciones (
  id                 uuid primary key default gen_random_uuid(),
  empresa_id         uuid not null references nucleo.empresas(id) on delete restrict,
  contacto_id        uuid not null,
  activa             boolean not null default true,
  abierta_en         timestamptz not null default now(),
  cerrada_en         timestamptz,
  resumen            text,
  resumen_en         timestamptz,
  created_at         timestamptz not null default now(),
  created_by         text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at         timestamptz not null default now(),
  updated_by         text,
  version            integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_conversacion_contacto foreign key (empresa_id, contacto_id)
    references nucleo.contactos_whatsapp (empresa_id, id) on delete restrict,
  constraint ck_conversacion_cierre check (activa or cerrada_en is not null)
);

-- Una sesión activa por contacto: sesiones paralelas fragmentarían el
-- contexto (§3.5); cierre a 15 min lo impone el orquestador (O3.5), la base
-- impone que no coexistan.
create unique index uq_conversacion_activa
  on nucleo.conversaciones (contacto_id) where activa;

create index idx_conversaciones_empresa
  on nucleo.conversaciones (empresa_id, contacto_id, activa);

comment on table nucleo.conversaciones is
  'Sesión de conversación por contacto; el cierre por inactividad (15 min) y '
  'la ventana de contexto (~200k tokens) los gobierna el orquestador (O3.5). '
  'El contexto vive en el ERP, nunca en objetos del proveedor (ADR-0003 §3.5).';
comment on column nucleo.conversaciones.resumen is
  'Resumen compactado al cerrar la sesión; NO es fuente de verdad del negocio '
  '(§3.5): los valores que producen efectos llegan por el DI y las tools.';

-- ----------------------------------------------------------------------------
-- 6. Mensajes de conversación (multimodal, idempotente por wa_message_id)
-- ----------------------------------------------------------------------------
create table nucleo.conversacion_mensajes (
  id                    uuid primary key default gen_random_uuid(),
  empresa_id            uuid not null references nucleo.empresas(id) on delete restrict,
  conversacion_id       uuid not null,
  contacto_id           uuid not null,  -- denormalizado para consulta; coherencia por trigger
  wa_message_id         text,
  direccion             nucleo.direccion_mensaje not null,
  modalidad             nucleo.modalidad_mensaje not null,
  cuerpo                text,           -- texto del mensaje o respuesta enviada
  transcripcion         text,           -- ASR (modalidad 'voz'; puede fallar: asr_failed)
  fecha_whatsapp        timestamptz,    -- si el webhook entrega fecha; UTC
  estado_procesamiento  nucleo.estado_procesamiento_mensaje not null default 'recibido',
  metadata              jsonb not null default '{}'::jsonb, -- expediente del mensaje (§3.1.4)
  created_at            timestamptz not null default now(),
  created_by            text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at            timestamptz not null default now(),
  updated_by            text,
  version               integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_mensaje_conversacion foreign key (empresa_id, conversacion_id)
    references nucleo.conversaciones (empresa_id, id) on delete restrict,
  constraint fk_mensaje_contacto foreign key (empresa_id, contacto_id)
    references nucleo.contactos_whatsapp (empresa_id, id) on delete restrict,
  constraint ck_mensaje_entrante_idempotente check (
    direccion <> 'entrante' or wa_message_id is not null
  )
);

-- Idempotencia GLOBAL del webhook: un wa_message_id entra una sola vez,
-- aunque el BSP reenvíe el webhook (ADR-0003 §3.1.2; no puede encenderse el
-- ASR/visión dos veces por el mismo mensaje).
create unique index uq_mensaje_wa_message_id
  on nucleo.conversacion_mensajes (wa_message_id) where wa_message_id is not null;

create index idx_mensajes_empresa_conversacion
  on nucleo.conversacion_mensajes (empresa_id, conversacion_id, created_at desc);
create index idx_mensajes_empresa_contacto
  on nucleo.conversacion_mensajes (empresa_id, contacto_id, created_at desc);

comment on table nucleo.conversacion_mensajes is
  'Mensaje multimodal del agente. Modalidad declarada por el webhook, nunca '
  'inferida (ADR-0003 §3.1.1). Idempotente por wa_message_id.';

-- Coherencia mensaje ↔ conversación: sin esto, un mensaje podría colarse en
-- la conversación de otro contacto de la misma empresa y contaminar su
-- contexto ( extensión de la fila "fugas entre sesiones", ADR-0003 §3.5).
create or replace function nucleo.fn_mensaje_validar()
returns trigger
language plpgsql
as $$
begin
  if exists (
    select 1
      from nucleo.conversaciones c
     where c.id = new.conversacion_id
       and c.empresa_id = new.empresa_id
       and c.contacto_id <> new.contacto_id
  ) then
    raise exception 'El mensaje de contacto % no pertenece a la conversación % (contacto distinto)',
      new.contacto_id, new.conversacion_id
      using errcode = '23514';
  end if;
  return new;
end;
$$;

-- ----------------------------------------------------------------------------
-- 7. Solicitudes + buzón (F2.6, DEC-11, D-10)
--    Estados: pendiente → aprobada | rechazada | cancelada (definitivos).
--    "Modificar" (D-10) NO es estado: son valores_modificados + quién/cuándo
--    mientras sigue pendiente; al Confirmar se cargan los modificados.
--    Rechazar solo logea (motivo_rechazo): el resto del Núcleo no muta.
-- ----------------------------------------------------------------------------
create table nucleo.solicitudes (
  id                             uuid primary key default gen_random_uuid(),
  empresa_id                     uuid not null references nucleo.empresas(id) on delete restrict,
  tipo                           nucleo.tipo_solicitud not null,
  -- Solicitante: contacto de WhatsApp O usuario del núcleo; exactamente uno
  -- (DEC-11: toda escritura tiene origen humano trazable).
  solicitante_contacto_id        uuid,
  solicitante_usuario_empresa_id uuid,
  -- Flete de destino (opcional): deep-link del buzón (O4.4); el desglose va
  -- en payload.
  viaje_id                       uuid,
  payload                        jsonb not null default '{}'::jsonb,
  valores_modificados            jsonb,
  clave_idempotencia             text,
  estado                         nucleo.estado_solicitud not null default 'pendiente',
  aprobado_por                   text,
  decidido_en                    timestamptz,
  motivo_rechazo                 text,
  motivo_cancelacion             text,
  modificado_por                 text,
  modificado_en                  timestamptz,
  created_at                     timestamptz not null default now(),
  created_by                     text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at                     timestamptz not null default now(),
  updated_by                     text,
  version                        integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_solicitud_contacto foreign key (empresa_id, solicitante_contacto_id)
    references nucleo.contactos_whatsapp (empresa_id, id) on delete restrict,
  constraint fk_solicitud_usuario foreign key (empresa_id, solicitante_usuario_empresa_id)
    references nucleo.usuarios_empresa (empresa_id, id) on delete restrict,
  constraint fk_solicitud_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_solicitud_solicitante check (
    (solicitante_contacto_id is null) <> (solicitante_usuario_empresa_id is null)
  ),
  constraint ck_solicitud_aprobada check (
    estado <> 'aprobada' or (aprobado_por is not null and decidido_en is not null)
  ),
  constraint ck_solicitud_rechazada check (
    estado <> 'rechazada' or (motivo_rechazo is not null and decidido_en is not null)
  ),
  constraint ck_solicitud_cancelada check (
    estado <> 'cancelada' or motivo_cancelacion is not null
  )
);

-- Idempotencia de creación: la misma clave no produce dos solicitudes
-- (doble entrega del webhook, doble clic del dueño).
create unique index uq_solicitud_idempotencia
  on nucleo.solicitudes (empresa_id, clave_idempotencia) where clave_idempotencia is not null;

create index idx_solicitudes_empresa_estado
  on nucleo.solicitudes (empresa_id, estado, tipo, created_at desc);
create index idx_solicitudes_empresa_viaje
  on nucleo.solicitudes (empresa_id, viaje_id) where viaje_id is not null;

comment on table nucleo.solicitudes is
  'Solicitud (DEC-11): el agente SOLO crea filas aquí; la escritura ejecuta '
  'el componente dueño tras aprobación humana (ADR-0003 §4). Confirmar '
  '(carga), Rechazar (log, estado intacto) y Modificar (valores corregidos) '
  '(D-10).';
comment on column nucleo.solicitudes.valores_modificados is
  'D-10 Modificar: plantilla editable pre-cargada; los valores corregidos '
  'viven aquí y son los que se cargan al Confirmar. El original queda en payload.';

-- Máquina de estados: la decisión es definitiva. Dos aprobadores de la misma
-- solicitud: el UPDATE atómico deja una sola ganadora (prueba con 2 conexiones
-- reales en 0021_02; el trigger es la defensa si un servicio no filtra por
-- estado previo: SQLSTATE 23514).
create or replace function nucleo.fn_solicitud_transicion()
returns trigger
language plpgsql
as $$
begin
  if old.estado in ('aprobada', 'rechazada', 'cancelada') then
    raise exception 'La solicitud % ya está en estado definitivo %: no se puede reabrir ni reclasificar',
      old.id, old.estado
      using errcode = '23514';
  end if;

  if new.estado = 'aprobada' then
    if new.aprobado_por is null or new.decidido_en is null then
      raise exception 'Aprobar la solicitud % exige aprobado_por y decidido_en', new.id
        using errcode = '23514';
    end if;
  elsif new.estado = 'rechazada' then
    if new.motivo_rechazo is null or new.decidido_en is null then
      raise exception 'Rechazar la solicitud % exige motivo_rechazo y decidido_en', new.id
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

comment on function nucleo.fn_solicitud_transicion() is
  'Decisión definitiva (D-10): estado terminal no cambia (23514). Los CHECKs '
  'de la tabla cubren INSERT con estado terminal; el trigger cubre UPDATE.';

-- ----------------------------------------------------------------------------
-- 8. Hoja de ruta (objeto nuevo decidido en D-10; ADR-0003 §14.2)
--    Estados: propuesto → solicitud_creada → cargado | rechazado. El payload
--    propuesto no se reescribe con la corrección: los valores cargados y la
--    plantilla modificada quedan en columnas aparte (§14.2 invariante 3).
-- ----------------------------------------------------------------------------
create table nucleo.hoja_ruta (
  id                uuid primary key default gen_random_uuid(),
  empresa_id        uuid not null references nucleo.empresas(id) on delete restrict,
  contacto_id       uuid not null,
  mensaje_id        uuid,
  solicitud_id      uuid,
  viaje_id          uuid,   -- flete dominante (los demás van en payload)
  payload           jsonb not null,
  estado            nucleo.estado_hoja_ruta not null default 'propuesto',
  valores_cargados  jsonb,
  motivo_rechazo    text,
  created_at        timestamptz not null default now(),
  created_by        text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at        timestamptz not null default now(),
  updated_by        text,
  version           integer not null default 1 check (version >= 1),
  unique (empresa_id, id),
  constraint fk_hr_contacto foreign key (empresa_id, contacto_id)
    references nucleo.contactos_whatsapp (empresa_id, id) on delete restrict,
  constraint fk_hr_mensaje foreign key (empresa_id, mensaje_id)
    references nucleo.conversacion_mensajes (empresa_id, id) on delete restrict,
  constraint fk_hr_solicitud foreign key (empresa_id, solicitud_id)
    references nucleo.solicitudes (empresa_id, id) on delete restrict,
  constraint fk_hr_viaje foreign key (empresa_id, viaje_id)
    references nucleo.viajes (empresa_id, id) on delete restrict,
  constraint ck_hr_estado_solicitud check (estado = 'propuesto' or solicitud_id is not null),
  constraint ck_hr_rechazo_con_motivo check (estado <> 'rechazado' or motivo_rechazo is not null),
  constraint ck_hr_carga_registrada check (estado <> 'cargado' or valores_cargados is not null)
);

-- A lo sumo una carga confirmada por solicitud (ADR-0003 §14.2.1). La
-- idempotencia real del cargado la lleva el componente dueño (O2.5); esto es
-- la barrera de base sobre el objeto hoja de ruta.
create unique index uq_hoja_ruta_carga_por_solicitud
  on nucleo.hoja_ruta (solicitud_id) where estado = 'cargado';

create index idx_hoja_ruta_empresa
  on nucleo.hoja_ruta (empresa_id, contacto_id, created_at desc);
create index idx_hoja_ruta_viaje
  on nucleo.hoja_ruta (empresa_id, viaje_id) where viaje_id is not null;

comment on table nucleo.hoja_ruta is
  'Hoja de ruta del conductor (D-10): JSON propuesto → solicitud en el buzón '
  '→ Confirmar/Rechazar/Modificar. SIN carga automática; rechazar no toca '
  'nada del núcleo.';

-- ----------------------------------------------------------------------------
-- 9. R-04 — ID comercial de flete (D-16; ADR-0003 §16)
--    `SQM-00001`: prefijo por cliente + 5 dígitos; creciente, sin
--    reutilización. Columna nullable (ADD-only) + UNIQUE (empresa, cliente,
--    código) + contador atómico por (empresa, cliente): el lock de fila del
--    ON CONFLICT DO UPDATE serializa; la UNIQUE de viajes es el árbitro final.
-- ----------------------------------------------------------------------------
alter table nucleo.viajes
  add column id_comercial_flete text;

alter table nucleo.viajes
  add constraint ck_viaje_id_comercial_flete
  check (id_comercial_flete ~ '^[A-Z0-9]{2,8}-[0-9]{5}$');

create unique index uq_viajes_id_comercial
  on nucleo.viajes (empresa_id, cliente_id, id_comercial_flete)
  where id_comercial_flete is not null;

-- Resolución código→flete (tool de lectura, §16.2): al recibir "SQM-00001"
-- NO se conoce cliente_id; el índice de resolución debe poder arrancar por
-- (empresa, código). Prefijo empresa_id = checklist P3 de 0020.
create index idx_viajes_id_comercial
  on nucleo.viajes (empresa_id, id_comercial_flete)
  where id_comercial_flete is not null;

comment on column nucleo.viajes.id_comercial_flete is
  'R-04: ID comercial por cliente (SQM-00001). Identifica, NO autoriza '
  '(ADR-0003 §16.2): todo acceso pasa por la ACL del contacto. No editable '
  'después de asignado (recomendación conservadora de roles.md §5: una '
  'corrección se documenta como cambio de relación flete↔ID, sin renumerar).';

create table nucleo.id_comercial_contador (
  empresa_id  uuid not null,
  cliente_id  uuid not null,
  ultimo      bigint not null default 0 check (ultimo >= 0),
  created_at  timestamptz not null default now(),
  created_by  text not null default coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema'),
  updated_at  timestamptz not null default now(),
  updated_by  text,
  version     integer not null default 1 check (version >= 1),
  primary key (empresa_id, cliente_id),
  constraint fk_contador_cliente foreign key (empresa_id, cliente_id)
    references nucleo.clientes (empresa_id, id) on delete restrict,
  constraint fk_contador_empresa foreign key (empresa_id)
    references nucleo.empresas (id) on delete restrict
);

create index idx_contador_empresa
  on nucleo.id_comercial_contador (empresa_id);

comment on table nucleo.id_comercial_contador is
  'Contador de IDs comerciales por (empresa, cliente). El `ultimo` nunca '
  'retrocede en transacciones confirmadas (sin reutilización de códigos, R-04).';

-- ----------------------------------------------------------------------------
-- 9.1 Funciones de generación / registro (patrón de siguiente_folio, 0004:498-537)
--     El INSERT ... ON CONFLICT DO UPDATE toma el lock de la fila del
--     contador: dos transacciones concurrentes se serializan ahí y devuelven
--     números DISTINCTOS; la constraint UNIQUE de viajes está detrás.
--     Un ROLLBACK libera el número nunca publicado (mismo criterio de
--     folio_contador, 0004:519-521).
-- ----------------------------------------------------------------------------
create or replace function nucleo.obtener_siguiente_id_comercial_flete(
  p_empresa_id uuid,
  p_cliente_id uuid,
  p_prefijo    text
)
returns text
language plpgsql
as $$
declare
  v_numero bigint;
begin
  if p_prefijo is null or p_prefijo !~ '^[A-Za-z0-9]{2,8}$' then
    raise exception 'Prefijo comercial inválido: % (2 a 8 caracteres alfanuméricos)', coalesce(p_prefijo, 'NULL')
      using errcode = '23514';
  end if;

  if not exists (
    select 1 from nucleo.clientes c
     where c.id = p_cliente_id and c.empresa_id = p_empresa_id
  ) then
    raise exception 'El cliente % no pertenece a la empresa % (la secuencia es por empresa-cliente)',
      p_cliente_id, p_empresa_id
      using errcode = '23514';
  end if;

  insert into nucleo.id_comercial_contador (empresa_id, cliente_id, ultimo)
    values (p_empresa_id, p_cliente_id, 1)
    on conflict (empresa_id, cliente_id)
    do update set ultimo = nucleo.id_comercial_contador.ultimo + 1
    returning ultimo into v_numero;

  return upper(p_prefijo) || '-' || lpad(v_numero::text, 5, '0');
end;
$$;

-- Igual que nucleo.registrar_folio (0004:522-537): al avanzar por códigos ya
-- asignados (cutover/backfill) el contador nunca retrocede.
create or replace function nucleo.registrar_id_comercial_flete(
  p_empresa_id uuid,
  p_cliente_id uuid,
  p_codigo     text
)
returns void
language plpgsql
as $$
declare
  v_numero bigint;
begin
  if p_codigo is null or p_codigo !~ '^[A-Z0-9]{2,8}-[0-9]{5}$' then
    raise exception 'Código comercial inválido: % (formato PREFIJO-00001)', coalesce(p_codigo, 'NULL')
      using errcode = '23514';
  end if;
  if not exists (
    select 1 from nucleo.clientes c
     where c.id = p_cliente_id and c.empresa_id = p_empresa_id
  ) then
    raise exception 'El cliente % no pertenece a la empresa %', p_cliente_id, p_empresa_id
      using errcode = '23514';
  end if;

  v_numero := split_part(p_codigo, '-', 2)::bigint;

  insert into nucleo.id_comercial_contador (empresa_id, cliente_id, ultimo)
    values (p_empresa_id, p_cliente_id, v_numero)
    on conflict (empresa_id, cliente_id)
    do update set ultimo = greatest(nucleo.id_comercial_contador.ultimo, excluded.ultimo);
end;
$$;

-- ----------------------------------------------------------------------------
-- 10. Auditoría de consultas del agente (D-17; ADR-0003 §13.4)
--     Append-only con el patrón de nucleo.auditoria (0004:880-892), más
--     guardia de TRUNCATE por statement (el gap INV-A01 de 0004:890-892,
--     cerrado AQUÍ para esta tabla).
-- ----------------------------------------------------------------------------
create table nucleo.auditoria_consultas_agente (
  id                bigint generated always as identity primary key,
  empresa_id        uuid not null references nucleo.empresas(id) on delete restrict,
  contacto_id       uuid not null,
  conversacion_id   uuid,
  mensaje_id        uuid,
  componente        text,
  variable          text,
  herramienta       text,
  pregunta_resumida text,
  datos_tocados     jsonb,
  respuesta_resumida text,
  acceso_otorgado   boolean not null,
  request_id        text,
  ocurrido_en       timestamptz not null default now(),
  constraint fk_consulta_contacto foreign key (empresa_id, contacto_id)
    references nucleo.contactos_whatsapp (empresa_id, id) on delete restrict,
  constraint fk_consulta_conversacion foreign key (empresa_id, conversacion_id)
    references nucleo.conversaciones (empresa_id, id) on delete restrict,
  constraint fk_consulta_mensaje foreign key (empresa_id, mensaje_id)
    references nucleo.conversacion_mensajes (empresa_id, id) on delete restrict,
  constraint ck_consulta_compuesto check (
    componente is not null or herramienta is not null
  )
);

create index idx_consultas_agente_empresa
  on nucleo.auditoria_consultas_agente (empresa_id, contacto_id, ocurrido_en desc);
create index idx_consultas_agente_empresa_fecha
  on nucleo.auditoria_consultas_agente (empresa_id, ocurrido_en desc);

comment on table nucleo.auditoria_consultas_agente is
  'D-17: cada consulta del agente queda append-only: quién, qué preguntó, '
  'qué tool/módulo, qué datos tocó, respuesta resumida y timestamp '
  '(ADR-0003 §13.4). Incluye consultas denegadas (acceso_otorgado=false): '
  'una consulta libre no es un hoyo de auditoría.';
comment on column nucleo.auditoria_consultas_agente.datos_tocados is
  'Referencias de entidades devueltas (IDs), nunca el contenido íntegro: no '
  'dupliques datos de tenant en este log.';

-- Append-only, patrón 0004:880-888, + guardia de TRUNCATE (por sentencia).
create or replace function nucleo.fn_consultas_agente_inmutable()
returns trigger
language plpgsql
as $$
begin
  raise exception 'Las consultas del agente son append-only: no se permite % en nucleo.auditoria_consultas_agente', tg_op
    using errcode = '23514';
end;
$$;

create trigger trg_consultas_agente_no_update
  before update or delete on nucleo.auditoria_consultas_agente
  for each row execute function nucleo.fn_consultas_agente_inmutable();

create trigger trg_consultas_agente_no_truncate
  before truncate on nucleo.auditoria_consultas_agente
  for each statement execute function nucleo.fn_consultas_agente_inmutable();

-- ----------------------------------------------------------------------------
-- 11. Triggers convencionales del núcleo (touch / version / audit)
--     Mismo patrón de 0004:1756-1878. Guardias VALIDADORas antes de touch.
-- ----------------------------------------------------------------------------
create trigger trg_contactos_touch before update on nucleo.contactos_whatsapp
  for each row execute function nucleo.fn_touch();
create trigger trg_contactos_version before update on nucleo.contactos_whatsapp
  for each row execute function nucleo.fn_version();
create trigger trg_contactos_audit after insert or update or delete on nucleo.contactos_whatsapp
  for each row execute function nucleo.fn_auditoria();

create trigger trg_permisos_touch before update on nucleo.permisos_contacto
  for each row execute function nucleo.fn_touch();
create trigger trg_permisos_version before update on nucleo.permisos_contacto
  for each row execute function nucleo.fn_version();
create trigger trg_permisos_audit after insert or update or delete on nucleo.permisos_contacto
  for each row execute function nucleo.fn_auditoria();

create trigger trg_conversaciones_touch before update on nucleo.conversaciones
  for each row execute function nucleo.fn_touch();
create trigger trg_conversaciones_version before update on nucleo.conversaciones
  for each row execute function nucleo.fn_version();
create trigger trg_conversaciones_audit after insert or update or delete on nucleo.conversaciones
  for each row execute function nucleo.fn_auditoria();

create trigger trg_mensajes_10_validar before insert or update on nucleo.conversacion_mensajes
  for each row execute function nucleo.fn_mensaje_validar();
create trigger trg_mensajes_touch before update on nucleo.conversacion_mensajes
  for each row execute function nucleo.fn_touch();
create trigger trg_mensajes_version before update on nucleo.conversacion_mensajes
  for each row execute function nucleo.fn_version();
create trigger trg_mensajes_audit after insert or update or delete on nucleo.conversacion_mensajes
  for each row execute function nucleo.fn_auditoria();

create trigger trg_solicitudes_10_transicion before update on nucleo.solicitudes
  for each row execute function nucleo.fn_solicitud_transicion();
create trigger trg_solicitudes_touch before update on nucleo.solicitudes
  for each row execute function nucleo.fn_touch();
create trigger trg_solicitudes_version before update on nucleo.solicitudes
  for each row execute function nucleo.fn_version();
create trigger trg_solicitudes_audit after insert or update or delete on nucleo.solicitudes
  for each row execute function nucleo.fn_auditoria();

create trigger trg_hoja_ruta_touch before update on nucleo.hoja_ruta
  for each row execute function nucleo.fn_touch();
create trigger trg_hoja_ruta_version before update on nucleo.hoja_ruta
  for each row execute function nucleo.fn_version();
create trigger trg_hoja_ruta_audit after insert or update or delete on nucleo.hoja_ruta
  for each row execute function nucleo.fn_auditoria();

create trigger trg_contador_touch before update on nucleo.id_comercial_contador
  for each row execute function nucleo.fn_touch();
create trigger trg_contador_version before update on nucleo.id_comercial_contador
  for each row execute function nucleo.fn_version();
create trigger trg_contador_audit after insert or update or delete on nucleo.id_comercial_contador
  for each row execute function nucleo.fn_auditoria();

-- ----------------------------------------------------------------------------
-- 12. RLS: políticas del patrón de 0020 (TO PUBLIC; USING + WITH CHECK por
--     empresa; fail-closed sin contexto). Checklist R-6 de ADR-0005:
--     GRANT + política + FORCE en cada tabla nueva.
-- ----------------------------------------------------------------------------
do $$
declare
  r text;
begin
  foreach r in array array[
    'contactos_whatsapp','permisos_contacto','conversaciones',
    'conversacion_mensajes','solicitudes','hoja_ruta','id_comercial_contador'
  ] loop
    execute format('drop policy if exists tenant_empresa on nucleo.%I', r);
    execute format(
      'create policy tenant_empresa on nucleo.%I for all to public '
      'using (empresa_id = nucleo.ctx_empresa()) '
      'with check (empresa_id = nucleo.ctx_empresa())', r);
  end loop;
end;
$$;

-- Tabla especial append-only (patrón de auditoria, 0020:339-347).
drop policy if exists consultas_agente_lectura on nucleo.auditoria_consultas_agente;
create policy consultas_agente_lectura on nucleo.auditoria_consultas_agente
  for select to public
  using (empresa_id = nucleo.ctx_empresa());

drop policy if exists consultas_agente_insercion on nucleo.auditoria_consultas_agente;
create policy consultas_agente_insercion on nucleo.auditoria_consultas_agente
  for insert to public
  with check (empresa_id = nucleo.ctx_empresa());

comment on policy consultas_agente_insercion on nucleo.auditoria_consultas_agente is
  'El runtime inserta con app.empresa_id del contacto resuelto. Intentos de '
  'números NO registrados NO se registran aquí: sin empresa no hay contexto y '
  'la política los rechaza; su log vive en el runtime (ADR-0003 §5, '
  'anti-enumeración).';

do $$
declare
  r text;
begin
  foreach r in array array[
    'contactos_whatsapp','permisos_contacto','conversaciones',
    'conversacion_mensajes','solicitudes','hoja_ruta',
    'id_comercial_contador','auditoria_consultas_agente'
  ] loop
    -- enable explícito: las tablas NUEVAS no heredan el estado RLS de la base
    -- canónica vía pg_dump (ese fue el mecanismo en 0020); sin enable,
    -- `force row level security` no impone nada (defecto detectado en la
    -- primera aplicación a tei_test el 2026-10-30 y corregido aquí).
    execute format('alter table nucleo.%I enable row level security', r);
    execute format('alter table nucleo.%I force row level security', r);
  end loop;
end;
$$;

-- ----------------------------------------------------------------------------
-- 13. GRANTs a tei_app (mismo esquema de privilegios de 0020:247-266)
-- ----------------------------------------------------------------------------
grant select, insert, update
  on nucleo.contactos_whatsapp, nucleo.permisos_contacto,
     nucleo.conversaciones, nucleo.conversacion_mensajes,
     nucleo.solicitudes, nucleo.hoja_ruta,
     nucleo.id_comercial_contador
  to tei_app;

-- Append-only: sin UPDATE ni DELETE (además los bloquea el trigger al dueño).
revoke all on table nucleo.auditoria_consultas_agente from tei_app;
grant select, insert on table nucleo.auditoria_consultas_agente to tei_app;

-- Secuencias nuevas (identity de auditoria_consultas_agente) y funciones nuevas.
grant usage, select on all sequences in schema nucleo to tei_app;
grant execute on all functions in schema nucleo to tei_app;

commit;

-- ============================================================================
-- VERIFICACIÓN POST (en tei_test)
--   1) Objetos creados: 8 tablas, columna/índices/ CHECK en viajes,
--      políticas, FORCE, GRANTs (consultas de catálogo en
--      docs/datos/agente-esquema.md §6).
--   2) smoke con rol postgres: supabase/tests/0021_01_smoke.sql
--   3) Concurrencia REAL (dos conexiones): 0021_02_concurrencia_id_comercial.py
--   4) RLS con el rol REAL de la aplicación (tei_app): 0021_03_rls_tei_app.sql
--   5) Mutación: 0021_04_mutacion.sql (retira el mecanismo en transacción y
--      confirma que la prueba falla).
--   Cada caso abre BEGIN y cierra ROLLBACK: sin residuo en tei_test.
-- ============================================================================
