-- ============================================================================
-- Rollback de 0021 — elimina el módulo agente WhatsApp del esquema nucleo
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0021_agente_whatsapp.sql, en orden inverso
-- de dependencias:
--   1. 8 tablas del módulo (auditoria_consultas_agente, hoja_ruta, solicitudes,
--      conversacion_mensajes, conversaciones, permisos_contacto,
--      id_comercial_contador, contactos_whatsapp)
--   2. 5 funciones (fn_mensaje_validar, fn_solicitud_transicion,
--      fn_consultas_agente_inmutable, obtener_siguiente_id_comercial_flete,
--      registrar_id_comercial_flete)
--   3. 8 tipos enumerados
--   4. columna nucleo.viajes.id_comercial_flete + CHECK + 2 índices
--   5. índice nucleo.uq_usuarios_empresa_empresa
--   6. triggers, políticas, GRANTs y secuencias: caen con las tablas/funciones
--
-- ORDEN: ejecutar 0022_99_rollback.sql ANTES. Sin eso, este script aborta con
-- un mensaje explícito (los mecanismos de 0022 se apoyan en objetos de 0021).
--
-- QUÉ NO REVIERTE Y POR QUÉ
--   · Datos de negocio (viajes, clientes, facturas, OC, pagos): intactos. Solo
--     se elimina la COLUMNA id_comercial_flete de viajes; ninguna fila se
--     borra (se verifica el conteo antes/después dentro de la transacción).
--   · Las 35 políticas de 0020: intactas. Las 9 del módulo caen con sus tablas;
--     el script verifica que nucleo vuelva a 35.
--   · `grant usage, select on all sequences in schema nucleo` y
--     `grant execute on all functions in schema nucleo` de 0021:866-868: NO se
--     revocan. Son aditivos, idénticos a los de 0020:250-251, y un REVOKE
--     rompería los privilegios que 0020 ya había otorgado. Los GRANT por tabla
--     del módulo caen con las tablas.
--   · Filas de nucleo.auditoria producidas por operaciones del módulo: son
--     append-only (0004) y no se borran; no pertenecen a las tablas eliminadas.
--
-- PÉRDIDA PREVISTA: los datos de las 8 tablas del módulo (contactos,
-- conversaciones, mensajes, solicitudes, hoja_ruta, contadores, ACL y auditoría
-- de consultas). La retención P-07/D-17 sigue abierta: en una base con datos
-- reales esto exige backup verificado y autorización explícita del dueño.
-- En `tei_test` (clon desechable) es parte del ciclo de rollback/re-aplicación.
--
-- Es idempotente (`if exists`). Requiere rol dueño del esquema.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0021_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

-- 0) Orden obligatorio: 0022 primero. Si quedan sus mecanismos, abortar sin
--    tocar nada (un rollback parcial dejaría funciones huérfanas).
do $$
declare
  v_detalle text;
begin
  select string_agg(t.tgname, ', ') into v_detalle
    from pg_trigger t
    join pg_class c on c.oid = t.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and not t.tgisinternal
     and t.tgname in ('trg_contador_10_no_retrocede',
                      'trg_viajes_10_id_comercial_inmutable',
                      'trg_hoja_ruta_10_transicion');
  if v_detalle is not null then
    raise exception '0021_99: quedan triggers de 0022 (%); ejecutar 0022_99_rollback.sql primero', v_detalle
      using errcode = '23514';
  end if;

  select string_agg(p.proname, ', ') into v_detalle
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('fn_contador_no_retrocede',
                       'fn_viaje_id_comercial_inmutable',
                       'fn_hoja_ruta_transicion');
  if v_detalle is not null then
    raise exception '0021_99: quedan funciones de 0022 (%); ejecutar 0022_99_rollback.sql primero', v_detalle
      using errcode = '23514';
  end if;

  if not exists (select 1 from pg_tables where schemaname = 'nucleo' and tablename = 'viajes') then
    raise exception '0021_99: falta nucleo.viajes; este no es el esquema esperado'
      using errcode = '23514';
  end if;

  -- Guarda de datos de negocio: el conteo debe ser el mismo al final.
  perform set_config('qa.viajes_antes', (select count(*)::text from nucleo.viajes), true);
end
$$;

-- 1) Tablas del módulo, de hojas a raíces (sin CASCADE: si algo inesperado
--    dependiera de ellas, el script falla en vez de arrastrarlo).
drop table if exists nucleo.auditoria_consultas_agente;
drop table if exists nucleo.hoja_ruta;
drop table if exists nucleo.solicitudes;
drop table if exists nucleo.conversacion_mensajes;
drop table if exists nucleo.conversaciones;
drop table if exists nucleo.permisos_contacto;
drop table if exists nucleo.id_comercial_contador;
drop table if exists nucleo.contactos_whatsapp;

-- 2) Funciones del módulo (los triggers ya cayeron con las tablas).
drop function if exists nucleo.fn_mensaje_validar();
drop function if exists nucleo.fn_solicitud_transicion();
drop function if exists nucleo.fn_consultas_agente_inmutable();
drop function if exists nucleo.obtener_siguiente_id_comercial_flete(uuid, uuid, text);
drop function if exists nucleo.registrar_id_comercial_flete(uuid, uuid, text);

-- 3) Tipos enumerados del módulo.
drop type if exists nucleo.rol_contacto_whatsapp;
drop type if exists nucleo.estado_otp;
drop type if exists nucleo.direccion_mensaje;
drop type if exists nucleo.modalidad_mensaje;
drop type if exists nucleo.estado_procesamiento_mensaje;
drop type if exists nucleo.tipo_solicitud;
drop type if exists nucleo.estado_solicitud;
drop type if exists nucleo.estado_hoja_ruta;

-- 4) R-04 sobre nucleo.viajes: CHECK, índices y columna. Solo metadata: las
--    filas de viajes no se tocan.
alter table nucleo.viajes drop constraint if exists ck_viaje_id_comercial_flete;
drop index if exists nucleo.uq_viajes_id_comercial;
drop index if exists nucleo.idx_viajes_id_comercial;
alter table nucleo.viajes drop column if exists id_comercial_flete;

-- 5) Índice que 0021 agregó a usuarios_empresa (las FKs del módulo ya no
--    existen).
drop index if exists nucleo.uq_usuarios_empresa_empresa;

-- 6) Verificación dentro de la misma transacción.
do $$
declare
  v_n integer;
  v_detalle text;
begin
  select count(*) into v_n
    from pg_tables
   where schemaname = 'nucleo'
     and tablename in ('contactos_whatsapp','permisos_contacto','conversaciones',
                       'conversacion_mensajes','solicitudes','hoja_ruta',
                       'id_comercial_contador','auditoria_consultas_agente');
  if v_n <> 0 then
    raise exception '0021_99 FALLO: quedan % tablas del módulo', v_n;
  end if;

  select count(*) into v_n
    from pg_type t join pg_namespace n on n.oid = t.typnamespace
   where n.nspname = 'nucleo'
     and t.typname in ('rol_contacto_whatsapp','estado_otp','direccion_mensaje',
                       'modalidad_mensaje','estado_procesamiento_mensaje',
                       'tipo_solicitud','estado_solicitud','estado_hoja_ruta');
  if v_n <> 0 then
    raise exception '0021_99 FALLO: quedan % tipos del módulo', v_n;
  end if;

  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('obtener_siguiente_id_comercial_flete','registrar_id_comercial_flete',
                       'fn_mensaje_validar','fn_solicitud_transicion',
                       'fn_consultas_agente_inmutable');
  if v_n <> 0 then
    raise exception '0021_99 FALLO: quedan % funciones del módulo', v_n;
  end if;

  select string_agg(t.tgname, ', ') into v_detalle
    from pg_trigger t
    join pg_class c on c.oid = t.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and not t.tgisinternal
     and t.tgname like any (array[
       'trg_contactos_%','trg_permisos_%','trg_conversaciones_%','trg_mensajes_%',
       'trg_solicitudes_%','trg_hoja_ruta_%','trg_contador_%','trg_consultas_agente_%']);
  if v_detalle is not null then
    raise exception '0021_99 FALLO: quedan triggers del módulo: %', v_detalle;
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename in ('contactos_whatsapp','permisos_contacto','conversaciones',
                       'conversacion_mensajes','solicitudes','hoja_ruta',
                       'id_comercial_contador','auditoria_consultas_agente');
  if v_n <> 0 then
    raise exception '0021_99 FALLO: quedan % políticas del módulo', v_n;
  end if;

  select count(*) into v_n from pg_policies where schemaname = 'nucleo';
  if v_n <> 35 then
    raise exception '0021_99 FALLO: quedan % políticas en nucleo (se esperaban 35, solo 0020)', v_n;
  end if;
  raise notice 'OK 0021-99: nucleo volvió a 35 políticas (solo 0020)';

  select count(*) into v_n
    from pg_attribute a
    join pg_class c on c.oid = a.attrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'viajes'
     and a.attname = 'id_comercial_flete' and a.attnum > 0 and not a.attisdropped;
  if v_n <> 0 then
    raise exception '0021_99 FALLO: sigue la columna nucleo.viajes.id_comercial_flete';
  end if;

  select count(*) into v_n
    from pg_indexes
   where schemaname = 'nucleo' and indexname = 'uq_usuarios_empresa_empresa';
  if v_n <> 0 then
    raise exception '0021_99 FALLO: sigue el índice uq_usuarios_empresa_empresa';
  end if;

  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relkind = 'S'
     and c.relname = 'auditoria_consultas_agente_id_seq';
  if v_n <> 0 then
    raise exception '0021_99 FALLO: sigue la secuencia identity de auditoria_consultas_agente';
  end if;

  -- Datos de negocio: viajes existe y conserva exactamente el mismo número
  -- de filas que antes del rollback (DROP COLUMN no borra filas).
  if (select count(*) from nucleo.viajes)::text
       <> current_setting('qa.viajes_antes') then
    raise exception '0021_99 FALLO: viajes cambió de % a % filas',
      current_setting('qa.viajes_antes'), (select count(*) from nucleo.viajes);
  end if;
  if not exists (select 1 from pg_tables where schemaname='nucleo' and tablename='clientes')
     or not exists (select 1 from pg_tables where schemaname='nucleo' and tablename='usuarios_empresa') then
    raise exception '0021_99 FALLO: faltan tablas de negocio del núcleo (clientes/usuarios_empresa)';
  end if;

  raise notice 'OK 0021-99: 8 tablas, 8 tipos, 5 funciones, triggers, 9 políticas, columna, índices y secuencia eliminados; viajes intacto (% filas)',
    (select count(*) from nucleo.viajes);
end
$$;

commit;

\echo '0021_99_rollback: OK (módulo eliminado; datos de negocio intactos)'
