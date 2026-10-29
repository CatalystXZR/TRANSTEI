-- ============================================================================
-- TRANSTEI — Migración 0015
-- Todo viaje con los tres recursos ocupa el libro de ocupación y queda
-- sujeto a la validación documental, cualquiera sea su estado.
-- ============================================================================
--
-- OBJETIVO
--   Cerrar el agujero confirmado en ejecución: un viaje insertado en estado
--   'confirmado' CON tracto, rampla y chofer producía 0 filas en
--   nucleo.reservas_recurso y no validaba documentos.
--   Causa: nucleo.fn_viaje_reservas (0004:1632-1635) y
--   nucleo.fn_viaje_validar (0004:1124-1126) excluían por LISTA DE ESTADOS, y
--   ck_viaje_recursos_por_estado (0004:671-674) permite 'confirmado' con
--   recursos. scripts/cutover_legacy.py:361-388 inserta exactamente
--   'confirmado' con los tres recursos.
--
-- INVARIANTES QUE IMPONE (docs/datos/02-invariantes.md)
--   INV-D04  Si nucleo.viajes tiene tracto_id, rampla_id y chofer_id no nulos
--            y estado <> 'anulado', existen TRES reservas activas en
--            nucleo.reservas_recurso con la MISMA ventana del viaje.
--   INV-DOC04 Si nucleo.viajes tiene los tres recursos y estado <> 'anulado',
--            los documentos exigibles de tracto, rampla y chofer están
--            vigentes al menos hasta el fin efectivo del viaje (+ margen de
--            la empresa), sin importar el estado del viaje.
--
-- DECISIÓN DE DISEÑO (leer antes de "arreglar" esto)
--   1. La condición es "TIENE LOS TRES RECURSOS", no una lista de estados.
--      Se conserva una sola exclusión: 'anulado' es terminal y libera los
--      recursos (0004:1536-1543 lo trata como cierre con motivo).
--   2. Recursos PARCIALES (solo tracto, o tracto+rampla) NO ocupan y NO se
--      validan. Una asignación operativa es completa; reservar un borrador a
--      medio armar bloquearía el tracto por un viaje que puede no existir.
--      Consecuencia aceptada y explícita: dos borradores pueden "reservar" el
--      mismo tracto en el papel hasta que se complete la asignación. El libro
--      sigue siendo la verdad para toda asignación completa.
--   3. Efecto nuevo en 'borrador'/'cotizado' con los tres recursos: pasan a
--      ocupar y a exigir documentos. Es la regla aprobada ("sea cual sea su
--      estado"); el borrador parcial sigue siendo la vía para preparar sin
--      comprometer recursos.
--   4. Se conserva la excepción operativa documentada en 0004:1128-1138: un
--      viaje YA despachado que solo cambia de estado no se detiene en ruta
--      porque un documento venció después del despacho. La nueva validación
--      documental replica esa condición; no la endurece.
--   5. No se toca ck_viaje_recursos_por_estado ni fn_viaje_validar (validación
--      completa de despacho: capacidad, tarifa, OC). Esta migración solo
--      cierra la puerta documental y la del libro de ocupación.
--
-- OBJETOS AFECTADOS
--   * nucleo.fn_viaje_reservas()      — CREATE OR REPLACE (0004:1621-1650)
--   * nucleo.fn_viaje_documentos()    — NUEVA
--   * trigger trg_viajes_05_documentos en nucleo.viajes — NUEVO
--     (orden alfabético: 00_ventana -> 03_licencia_a5 (0016) -> 05_documentos
--      -> 10_validar -> 15_facturacion -> ... )
--   * Backfill de nucleo.reservas_recurso para viajes ya existentes.
--   * Sin cambios de columnas, sin DROP, sin pérdida de datos.
--
-- PRECONDICIONES (ejecutar ANTES de aplicar; ver docs/datos/migraciones/0015)
--   P1.1 — viajes en alcance que hoy NO tienen sus 3 reservas activas
--          (es el agujero; el backfill los adopta). Se espera > 0 si el
--          cutover o pruebas manuales corrieron:
--
--     select v.id, v.empresa_id, v.numero_viaje, v.estado
--       from nucleo.viajes v
--      where v.estado <> 'anulado'
--        and v.tracto_id is not null and v.rampla_id is not null
--        and v.chofer_id is not null
--        and 3 > (select count(*) from nucleo.reservas_recurso r
--                  where r.viaje_id = v.id and r.activa);
--
--   P1.2 — pares de viajes en alcance que se solapan sobre el mismo recurso.
--          DEBE DEVOLVER 0 FILAS. Si devuelve filas, la migración aborta con
--          23514: son dos viajes reales compitiendo por el mismo recurso y
--          eso lo resuelve OPERACIÓN (anular/reasignar), no una migración.
--          No se borra nada.
--
--     select a.numero_viaje as viaje_a, b.numero_viaje as viaje_b,
--            a.estado as estado_a, b.estado as estado_b, a.ventana
--       from nucleo.viajes a
--       join nucleo.viajes b
--         on a.id < b.id
--        and a.empresa_id = b.empresa_id
--        and a.ventana && b.ventana
--      where a.estado <> 'anulado' and b.estado <> 'anulado'
--        and a.tracto_id is not null and a.rampla_id is not null
--        and a.chofer_id is not null
--        and b.tracto_id is not null and b.rampla_id is not null
--        and b.chofer_id is not null
--        and (a.tracto_id = b.tracto_id or a.rampla_id = b.rampla_id
--             or a.chofer_id = b.chofer_id)
--        and ( 3 > (select count(*) from nucleo.reservas_recurso r
--                    where r.viaje_id = a.id and r.activa)
--           or 3 > (select count(*) from nucleo.reservas_recurso r
--                    where r.viaje_id = b.id and r.activa) );
--
--   P1.3 — reservas activas de viaje cuya ventana ya no coincide con la del
--          viaje (deriva). DEBE DEVOLVER 0 FILAS; si no, el backfill aborta
--          al no poder dejar el libro coherente:
--
--     select r.id, r.viaje_id, r.recurso_tipo, r.ventana, v.ventana as ventana_viaje
--       from nucleo.reservas_recurso r
--       join nucleo.viajes v on v.id = r.viaje_id
--      where r.activa and r.tipo_reserva = 'viaje'
--        and r.ventana <> v.ventana;
--
--   P1.4 — tamaño (dimensiona locks; medir, no suponer):
--
--     select relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid))
--       from pg_stat_user_tables
--      where schemaname = 'nucleo'
--        and relname in ('viajes','reservas_recurso');
--
-- IMPACTO EN DATOS Y LOCKS
--   * CREATE OR REPLACE FUNCTION: lock de catálogo, no bloquea filas.
--   * CREATE TRIGGER: ShareRowExclusiveLock breve sobre nucleo.viajes.
--   * Backfill: INSERT en nucleo.reservas_recurso (RowExclusiveLock + índices
--     GIST). Puede esperar/bloquear asignaciones concurrentes del mismo
--     recurso mientras corre. Volumen esperado: 3 filas por viaje adoptado.
--   * ANALYZE final: ShareUpdateExclusiveLock, segundos.
--   * public (legacy): NO se toca. Sin impacto.
--
-- COMPATIBILIDAD
--   * public.*: intacto. El legacy no escribe en nucleo.reservas_recurso, así
--     que la disponibilidad sigue sin ser única entre esquemas (RA-02).
--   * backend/app/nucleo: crear viaje (confirmado SIN recursos,
--     servicio_disponibilidad.py:946-971) no cambia. Asignar
--     (confirmado -> asignado CON recursos) ya creaba reservas; ahora además
--     valida documentos también en el camino 'confirmado' con recursos.
--   * scripts/cutover_legacy.py: QUEDA INCOMPATIBLE, ver §CUTOVER.
--
-- §CUTOVER — scripts/cutover_legacy.py:361-388
--   Ese script inserta viajes 'confirmado' CON tracto, rampla y chofer y NO
--   crea documentos en nucleo.documentos. Desde esta migración el INSERT
--   falla con 23514 ("Documento licencia_conducir faltante ...") y la
--   transacción completa del cutover se revierte. Se marca INCOMPATIBLE a
--   propósito: migrar viajes con recursos y sin expediente documental
--   equivale a despachar sin control. No se agrega una puerta trasera
--   (GUC de escape) porque sería un mecanismo fail-open, el mismo defecto
--   que RA-04.
--   Camino correcto (handoff a quien mantiene scripts/, NO a esta migración):
--     a) cargar primero nucleo.documentos de tracto/rampla/chofer, o
--     b) insertar los viajes migrados en 'borrador' (o 'cotizado') SIN
--        recursos y completar la asignación después de cargar documentos.
--   Los solapamientos del legacy (P1.2) también deben resolverse antes.
--
-- ROLLBACK (exacto, sin pérdida de datos)
--   1. drop trigger if exists trg_viajes_05_documentos on nucleo.viajes;
--      drop function if exists nucleo.fn_viaje_documentos();
--   2. create or replace function nucleo.fn_viaje_reservas() con el cuerpo de
--      0004:1621-1650 (copiado textualmente en
--      docs/datos/migraciones/0015-ocupacion-confirmado.md §Rollback).
--   3. Las reservas creadas por el backfill NO se borran: se desactivan
--        update nucleo.reservas_recurso
--           set activa = false,
--               cancelado_motivo = 'rollback 0015',
--               cancelado_por = 'migracion_0015',
--               cancelado_en = now()
--         where activa and creado_por = 'migracion_0015';
--      (columnas cancelado_* agregadas en 0006; el trigger
--      fn_reserva_no_borrar permite desactivar, no borrar.)
--   4. Verificar: select count(*) from nucleo.reservas_recurso
--                  where activa and creado_por = 'migracion_0015';  -> 0
--   El rollback devuelve el sistema al agujero: es un incidente, no una
--   operación rutinaria.
--
-- VERIFICACIÓN POST (después de aplicar)
--   V1. select count(*) from nucleo.viajes v
--        where v.estado <> 'anulado'
--          and v.tracto_id is not null and v.rampla_id is not null
--          and v.chofer_id is not null
--          and 3 > (select count(*) from nucleo.reservas_recurso r
--                    where r.viaje_id = v.id and r.activa and r.ventana = v.ventana);
--       -> 0
--   V2. Un viaje 'confirmado' nuevo con los tres recursos crea 3 reservas
--       (supabase/tests/0015_01_confirmado_ocupa.sql).
--   V3. Un viaje 'confirmado' con los tres recursos y un documento faltante o
--       vencido es rechazado con 23514
--       (supabase/tests/0015_03_confirmado_valida_documentos.sql).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Libro de ocupación: ocupa todo viaje con los tres recursos
-- ----------------------------------------------------------------------------
create or replace function nucleo.fn_viaje_reservas()
returns trigger
language plpgsql
as $$
declare
  v_auth text := coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema');
  v_ocupa boolean;
  v_ya_esta integer;
begin
  -- Regla 0015: ocupa el libro todo viaje que tenga los tres recursos,
  -- cualquiera sea su estado. 'anulado' es terminal y libera los recursos.
  v_ocupa := new.estado <> 'anulado'
             and new.tracto_id is not null
             and new.rampla_id is not null
             and new.chofer_id is not null;

  -- Camino rápido: el viaje ya está en el libro con sus tres recursos y la
  -- misma ventana. Evita desactivar/reinsertar en cada UPDATE irrelevante
  -- (antes solo pasaba en estados operativos; ahora también en confirmado).
  if v_ocupa then
    select count(*) into v_ya_esta
      from nucleo.reservas_recurso r
     where r.viaje_id = new.id
       and r.activa
       and r.ventana = new.ventana
       and ((r.recurso_tipo = 'tracto' and r.tracto_id = new.tracto_id)
         or (r.recurso_tipo = 'rampla' and r.rampla_id = new.rampla_id)
         or (r.recurso_tipo = 'chofer' and r.chofer_id = new.chofer_id));

    if v_ya_esta = 3 then
      return new;
    end if;
  end if;

  -- Reasignación / anulación / cambio de ventana: se libera lo anterior y se
  -- vuelve a reservar en la MISMA transacción (atómico).
  update nucleo.reservas_recurso
     set activa = false
   where viaje_id = new.id and activa;

  if v_ocupa then
    insert into nucleo.reservas_recurso (
      empresa_id, recurso_tipo, tracto_id, rampla_id, chofer_id, ventana,
      tipo_reserva, viaje_id, motivo, activa, creado_por
    ) values
      (new.empresa_id, 'tracto', new.tracto_id, null, null, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth),
      (new.empresa_id, 'rampla', null, new.rampla_id, null, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth),
      (new.empresa_id, 'chofer', null, null, new.chofer_id, new.ventana,
       'viaje', new.id, 'Viaje ' || new.numero_viaje, true, v_auth);
  end if;

  return new;
end;
$$;

comment on function nucleo.fn_viaje_reservas() is
  '0015: todo viaje con tracto, rampla y chofer ocupa el libro de reservas, '
  'cualquiera sea su estado; anulado libera. Antes excluía por lista de estados.';

-- ----------------------------------------------------------------------------
-- 2. Validación documental por recursos, no por estado
-- ----------------------------------------------------------------------------
create or replace function nucleo.fn_viaje_documentos()
returns trigger
language plpgsql
as $$
declare
  v_zona text;
  v_margen integer;
  v_fin_efectivo timestamptz;
  v_hasta date;
begin
  -- 'anulado' libera recursos y no exige expediente.
  if new.estado = 'anulado' then
    return new;
  end if;

  -- Sin los tres recursos no hay asignación que validar (ver decisión 2).
  if new.tracto_id is null or new.rampla_id is null or new.chofer_id is null then
    return new;
  end if;

  -- Excepción operativa heredada de 0004:1128-1138: un viaje ya despachado
  -- que solo cambia de estado no se detiene en ruta porque un documento
  -- venció después del despacho. No se endurece esa decisión aquí.
  if tg_op = 'UPDATE' then
    if new.estado <> 'asignado'
       and new.tracto_id = old.tracto_id
       and new.rampla_id = old.rampla_id
       and new.chofer_id = old.chofer_id then
      return new;
    end if;
  end if;

  select e.zona_horaria, e.dias_margen_documentos
    into v_zona, v_margen
    from nucleo.empresas e
   where e.id = new.empresa_id;

  v_zona := coalesce(v_zona, 'America/Santiago');
  v_margen := coalesce(v_margen, 0);

  v_fin_efectivo := coalesce(new.fin_real, new.fin_estimado, new.fin_planificado)
                    + make_interval(mins => new.buffer_minutos);
  v_hasta := (v_fin_efectivo at time zone v_zona)::date + v_margen;

  perform nucleo.validar_documentos_recurso(
    new.empresa_id, 'tracto', new.tracto_id, v_hasta,
    new.carga_peligrosa, new.refrigerada
  );
  perform nucleo.validar_documentos_recurso(
    new.empresa_id, 'rampla', new.rampla_id, v_hasta,
    new.carga_peligrosa, new.refrigerada
  );
  perform nucleo.validar_documentos_recurso(
    new.empresa_id, 'chofer', new.chofer_id, v_hasta,
    new.carga_peligrosa, new.refrigerada
  );

  return new;
end;
$$;

comment on function nucleo.fn_viaje_documentos() is
  '0015/INV-DOC04: valida documentos de tracto, rampla y chofer para todo viaje '
  'con los tres recursos, sin importar el estado (salvo anulado).';

drop trigger if exists trg_viajes_05_documentos on nucleo.viajes;
create trigger trg_viajes_05_documentos
  before insert or update on nucleo.viajes
  for each row execute function nucleo.fn_viaje_documentos();

-- ----------------------------------------------------------------------------
-- 3. Backfill: adoptar los viajes que ya estaban fuera del libro
-- ----------------------------------------------------------------------------
do $$
declare
  v_alcance      integer;
  v_faltantes    integer;
  v_insertadas   integer := 0;
  v_n            integer;
  v_antes        bigint;
  v_despues      bigint;
  v_conflictos   integer;
  v_ejemplo      text;
  v_pendientes   integer;
begin
  -- Universo: viajes con los tres recursos que deben ocupar el libro.
  select count(*) into v_alcance
    from nucleo.viajes v
   where v.estado <> 'anulado'
     and v.tracto_id is not null
     and v.rampla_id is not null
     and v.chofer_id is not null;

  select count(*) into v_faltantes
    from nucleo.viajes v
   where v.estado <> 'anulado'
     and v.tracto_id is not null
     and v.rampla_id is not null
     and v.chofer_id is not null
     and 3 > (select count(*) from nucleo.reservas_recurso r
               where r.viaje_id = v.id and r.activa
                 and r.ventana = v.ventana
                 and ((r.recurso_tipo = 'tracto' and r.tracto_id = v.tracto_id)
                   or (r.recurso_tipo = 'rampla' and r.rampla_id = v.rampla_id)
                   or (r.recurso_tipo = 'chofer' and r.chofer_id = v.chofer_id)));

  select count(*) into v_antes
    from nucleo.reservas_recurso r
   where r.activa and r.tipo_reserva = 'viaje';

  if v_faltantes = 0 then
    raise notice '0015: nada que adoptar (viajes con 3 recursos=%, reservas activas de viaje=%)',
      v_alcance, v_antes;
    return;
  end if;

  -- Detección previa (P1.2): dos viajes en alcance que comparten recurso y se
  -- solapan. Si existen, la migración ABORTA: no se borra ni se reasigna nada.
  select count(*), min(q.detalle)
    into v_conflictos, v_ejemplo
    from (
      select a.numero_viaje || ' / ' || b.numero_viaje as detalle
        from nucleo.viajes a
        join nucleo.viajes b
          on a.id < b.id
         and a.empresa_id = b.empresa_id
         and a.ventana && b.ventana
       where a.estado <> 'anulado' and b.estado <> 'anulado'
         and a.tracto_id is not null and a.rampla_id is not null
         and a.chofer_id is not null
         and b.tracto_id is not null and b.rampla_id is not null
         and b.chofer_id is not null
         and (a.tracto_id = b.tracto_id or a.rampla_id = b.rampla_id
              or a.chofer_id = b.chofer_id)
         and ( 3 > (select count(*) from nucleo.reservas_recurso r
                     where r.viaje_id = a.id and r.activa)
            or 3 > (select count(*) from nucleo.reservas_recurso r
                     where r.viaje_id = b.id and r.activa) )
    ) q;

  if v_conflictos > 0 then
    raise exception '0015 abortada: % par(es) de viajes con recursos se solapan sobre el mismo recurso (ej.: %). No se borra nada. Ejecute la consulta P1.2 del encabezado, resuelva con operación (anular o reasignar) y vuelva a aplicar.',
      v_conflictos, coalesce(v_ejemplo, '(sin detalle)')
      using errcode = '23514';
  end if;

  -- Backfill idempotente: una fila por (viaje, recurso_tipo) que falte.
  insert into nucleo.reservas_recurso (
    empresa_id, recurso_tipo, tracto_id, rampla_id, chofer_id, ventana,
    tipo_reserva, viaje_id, motivo, activa, creado_por
  )
  select v.empresa_id, 'tracto', v.tracto_id, null, null, v.ventana,
         'viaje', v.id, 'Backfill 0015 viaje ' || v.numero_viaje,
         true, 'migracion_0015'
    from nucleo.viajes v
   where v.estado <> 'anulado'
     and v.tracto_id is not null and v.rampla_id is not null
     and v.chofer_id is not null
     and not exists (
       select 1 from nucleo.reservas_recurso r
        where r.viaje_id = v.id and r.activa and r.recurso_tipo = 'tracto');
  get diagnostics v_n = row_count;
  v_insertadas := v_insertadas + v_n;

  insert into nucleo.reservas_recurso (
    empresa_id, recurso_tipo, tracto_id, rampla_id, chofer_id, ventana,
    tipo_reserva, viaje_id, motivo, activa, creado_por
  )
  select v.empresa_id, 'rampla', null, v.rampla_id, null, v.ventana,
         'viaje', v.id, 'Backfill 0015 viaje ' || v.numero_viaje,
         true, 'migracion_0015'
    from nucleo.viajes v
   where v.estado <> 'anulado'
     and v.tracto_id is not null and v.rampla_id is not null
     and v.chofer_id is not null
     and not exists (
       select 1 from nucleo.reservas_recurso r
        where r.viaje_id = v.id and r.activa and r.recurso_tipo = 'rampla');
  get diagnostics v_n = row_count;
  v_insertadas := v_insertadas + v_n;

  insert into nucleo.reservas_recurso (
    empresa_id, recurso_tipo, tracto_id, rampla_id, chofer_id, ventana,
    tipo_reserva, viaje_id, motivo, activa, creado_por
  )
  select v.empresa_id, 'chofer', null, null, v.chofer_id, v.ventana,
         'viaje', v.id, 'Backfill 0015 viaje ' || v.numero_viaje,
         true, 'migracion_0015'
    from nucleo.viajes v
   where v.estado <> 'anulado'
     and v.tracto_id is not null and v.rampla_id is not null
     and v.chofer_id is not null
     and not exists (
       select 1 from nucleo.reservas_recurso r
        where r.viaje_id = v.id and r.activa and r.recurso_tipo = 'chofer');
  get diagnostics v_n = row_count;
  v_insertadas := v_insertadas + v_n;

  select count(*) into v_despues
    from nucleo.reservas_recurso r
   where r.activa and r.tipo_reserva = 'viaje';

  -- Autochequeo: el libro debe quedar completo y con la ventana del viaje.
  select count(*) into v_pendientes
    from nucleo.viajes v
   where v.estado <> 'anulado'
     and v.tracto_id is not null
     and v.rampla_id is not null
     and v.chofer_id is not null
     and 3 > (select count(*) from nucleo.reservas_recurso r
               where r.viaje_id = v.id and r.activa
                 and r.ventana = v.ventana
                 and ((r.recurso_tipo = 'tracto' and r.tracto_id = v.tracto_id)
                   or (r.recurso_tipo = 'rampla' and r.rampla_id = v.rampla_id)
                   or (r.recurso_tipo = 'chofer' and r.chofer_id = v.chofer_id)));

  raise notice '0015: viajes con 3 recursos=%, por adoptar=%, reservas insertadas=%, reservas activas de viaje: % -> %',
    v_alcance, v_faltantes, v_insertadas, v_antes, v_despues;

  if v_pendientes > 0 then
    raise exception '0015: quedaron % viaje(s) con recursos sin sus 3 reservas activas en la ventana del viaje. Causas posibles: (a) reservas activas con ventana derivada (P1.3) o (b) reservas activas de otro tracto/rampla/chofer para el mismo viaje (reasignación manual). Reporte y resuelva con operación; no se borra nada.',
      v_pendientes
      using errcode = '23514';
  end if;
end;
$$;

analyze nucleo.reservas_recurso;

-- ============================================================================
-- Fin de 0015. Re-ejecutable: CREATE OR REPLACE + DROP TRIGGER IF EXISTS +
-- backfill idempotente (NOT EXISTS por viaje/recurso).
-- ============================================================================
