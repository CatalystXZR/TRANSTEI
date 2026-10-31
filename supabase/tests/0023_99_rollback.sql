-- ============================================================================
-- Rollback de 0023 — retira el flag de módulo por empresa
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0023_modulos_empresa.sql:
--   drop table nucleo.modulos_empresa
-- Con la tabla caen, sin sentencias adicionales: PK (empresa_id, modulo_id),
-- FK a nucleo.empresas, CHECKs ck_modulo_id_formato/ck_modulo_id_no_vacio,
-- triggers trg_modulos_empresa_touch/version, política tenant_empresa, RLS
-- ENABLE/FORCE, GRANTs a tei_app y los COMMENTs.
--
-- NO toca:
--   · los datos de negocio (viajes, clientes, facturas, OC, pagos, empresas),
--   · las 8 tablas, 8 tipos y 5 funciones de 0021,
--   · los 3 triggers y 3 funciones de 0022,
--   · las funciones compartidas nucleo.fn_touch()/nucleo.fn_version() (0004),
--   · ninguna otra política de `nucleo`.
--
-- PÉRDIDA PREVISTA: los flags de módulo por empresa. La tabla nace vacía
-- (0023 no siembra filas), así que en el estado normal la pérdida es 0 filas.
-- Si ya hay filas con `habilitado = true`, revertir APAGA el módulo para esas
-- empresas: es un cambio operativo, no solo de esquema. El script imprime el
-- conteo antes de borrar; en una base con flags reales exige autorización del
-- dueño y un registro del valor (empresa_id, modulo_id, habilitado,
-- habilitado_en, habilitado_por) antes de ejecutarlo.
--
-- ORDEN: ejecutar ANTES de 0021_99_rollback.sql. 0023 no crea dependencias
-- sobre 0021 (solo exige que exista), pero revivir el módulo sin el flag deja
-- el gate sin llave 1; el orden mantiene el ciclo reversible.
--
-- Es idempotente: si la tabla no existe, no falla y avisa.
-- Requiere un rol dueño del esquema (supabase_admin/postgres dueño).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0023_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_existe    boolean;
  v_filas     bigint;
  v_pol_antes integer;
  v_pol_despues integer;
  v_n         integer;
  v_detalle   text;
begin
  v_existe := to_regclass('nucleo.modulos_empresa') is not null;

  if not v_existe then
    raise notice '0023-99: nucleo.modulos_empresa no existe; nada que revertir';
  else
    execute 'select count(*) from nucleo.modulos_empresa' into v_filas;

    -- Conteo de políticas del esquema: el DROP debe retirar exactamente 1.
    select count(*) into v_pol_antes
      from pg_policies where schemaname = 'nucleo';

    -- Sin CASCADE a propósito: si apareciera una dependencia no prevista,
    -- el DROP aborta en vez de arrastrar objetos ajenos.
    execute 'drop table nucleo.modulos_empresa';

    select count(*) into v_pol_despues
      from pg_policies where schemaname = 'nucleo';
    if v_pol_antes - v_pol_despues <> 1 then
      raise exception '0023_99 FALLO: se esperaba retirar 1 política, se retiraron %',
        v_pol_antes - v_pol_despues;
    end if;

    raise notice '0023-99: tabla eliminada; % fila(s) de flag perdidas (esperado 0)', v_filas;
  end if;

  -- 1) La tabla y todo lo que cuelga de ella ya no existen.
  if to_regclass('nucleo.modulos_empresa') is not null then
    raise exception '0023_99 FALLO: sigue nucleo.modulos_empresa';
  end if;
  select string_agg(p.polname, ', ') into v_detalle
    from pg_policy p
    join pg_class c on c.oid = p.polrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'modulos_empresa';
  if v_detalle is not null then
    raise exception '0023_99 FALLO: quedan políticas de 0023: %', v_detalle;
  end if;

  -- 2) 0021 intacta: 8 tablas del módulo.
  select count(*) into v_n
    from pg_tables
   where schemaname = 'nucleo' and tablename in (
     'contactos_whatsapp','permisos_contacto','conversaciones',
     'conversacion_mensajes','solicitudes','hoja_ruta',
     'id_comercial_contador','auditoria_consultas_agente');
  if v_n <> 8 then
    raise exception '0023_99 FALLO: 0021 debía quedar intacta; hay % de 8 tablas', v_n;
  end if;

  -- 3) 0022 intacta: 3 funciones de trigger.
  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo' and p.proname in (
     'fn_contador_no_retrocede','fn_viaje_id_comercial_inmutable',
     'fn_hoja_ruta_transicion');
  if v_n <> 3 then
    raise exception '0023_99 FALLO: 0022 debía quedar intacta; hay % de 3 funciones', v_n;
  end if;

  -- 4) Funciones compartidas del núcleo intactas (0023 NO las crea ni las toca).
  select count(*) into v_n
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo' and p.proname in ('fn_touch','fn_version');
  if v_n <> 2 then
    raise exception '0023_99 FALLO: faltan nucleo.fn_touch/fn_version (0004)';
  end if;

  -- 5) Datos de negocio intactos: empresas sigue existiendo y con filas.
  if to_regclass('nucleo.empresas') is null then
    raise exception '0023_99 FALLO: falta nucleo.empresas';
  end if;
  select count(*) into v_n from nucleo.empresas;
  if v_n = 0 then
    raise exception '0023_99 FALLO: nucleo.empresas quedó vacía';
  end if;

  raise notice 'OK 0023-99: flag eliminado; 0021/0022 y datos de negocio intactos (% empresas)', v_n;
end
$$;

commit;

\echo '0023_99_rollback: OK (nucleo.modulos_empresa eliminada; sin pérdida de datos de negocio)'
