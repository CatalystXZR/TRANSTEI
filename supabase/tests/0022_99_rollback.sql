-- ============================================================================
-- Rollback de 0022 — retira el endurecimiento del módulo agente WhatsApp
-- ============================================================================
-- Revierte EXACTAMENTE lo que crea 0022_agente_whatsapp_endurecimiento.sql:
--   · trg_hoja_ruta_10_transicion      + fn_hoja_ruta_transicion()
--   · trg_viajes_10_id_comercial_inmutable + fn_viaje_id_comercial_inmutable()
--   · trg_contador_10_no_retrocede     + fn_contador_no_retrocede()
--   · restaurar nucleo.obtener_siguiente_id_comercial_flete al cuerpo de
--     0021:603-636 (sin tope de 99999)
--
-- NO toca datos, tablas, columnas, políticas ni GRANTs. Solo catálogo.
-- Es idempotente (`if exists` / `create or replace`).
--
-- ORDEN: ejecutar ANTES de 0021_99_rollback.sql. Si 0022 no está aplicada,
-- el script no falla: deja la función en la versión de 0021 y avisa.
--
-- ADVERTENCIA: revertir REABRE D2, D3, D5 y D9. La base vuelve a aceptar
-- reasignación/desasignación de ID comercial, retroceso del contador,
-- transiciones ilegales de hoja_ruta y códigos truncados a partir de 99999.
-- Es un rollback de emergencia, no un estado operativo deseado.
--
-- Requiere un rol dueño del esquema (supabase_admin/postgres dueño).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0022_99_rollback.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

-- 0) Precondición: 0021 aplicada (sin ella no hay función que restaurar).
do $$
begin
  if not exists (
    select 1 from pg_tables
     where schemaname = 'nucleo' and tablename = 'id_comercial_contador'
  ) then
    raise exception '0022_99: falta 0021 (nucleo.id_comercial_contador); no hay módulo que revertir'
      using errcode = '23514';
  end if;
end
$$;

-- 1) D5 — hoja de ruta: trigger antes que función (dependencia).
drop trigger if exists trg_hoja_ruta_10_transicion on nucleo.hoja_ruta;
drop function if exists nucleo.fn_hoja_ruta_transicion();

-- 2) D2 — ID comercial inmutable.
drop trigger if exists trg_viajes_10_id_comercial_inmutable on nucleo.viajes;
drop function if exists nucleo.fn_viaje_id_comercial_inmutable();

-- 3) D3 — contador no retrocede.
drop trigger if exists trg_contador_10_no_retrocede on nucleo.id_comercial_contador;
drop function if exists nucleo.fn_contador_no_retrocede();

-- 4) D9 — restaurar la versión de 0021:603-636, misma firma y mismo formato,
--    sin el tope. `create or replace` conserva GRANTs y dependencias.
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

-- 5) Verificación dentro de la misma transacción (si algo no desapareció,
--    el rollback aborta y no deja un estado intermedio).
do $$
declare
  v_n integer;
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
    raise exception '0022_99 FALLO: quedan triggers de 0022: %', v_detalle;
  end if;

  select string_agg(p.proname, ', ') into v_detalle
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('fn_contador_no_retrocede',
                       'fn_viaje_id_comercial_inmutable',
                       'fn_hoja_ruta_transicion');
  if v_detalle is not null then
    raise exception '0022_99 FALLO: quedan funciones de 0022: %', v_detalle;
  end if;

  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname = 'obtener_siguiente_id_comercial_flete'
     and p.prosrc like '%99999%';
  if v_n <> 0 then
    raise exception '0022_99 FALLO: obtener_siguiente_id_comercial_flete todavía contiene el tope D9';
  end if;

  raise notice 'OK 0022-99: 3 triggers y 3 funciones retirados; función restaurada a 0021';
end
$$;

commit;

\echo '0022_99_rollback: OK (D2/D3/D5/D9 reabiertos; datos intactos)'
