-- ============================================================================
-- TRANSTEI — Migración 0022: endurecimiento del módulo agente WhatsApp
-- ============================================================================
--
-- OBJETIVO
--   Cerrar en PostgreSQL cuatro defectos verificados de 0021 (ver
--   docs/datos/agente-esquema.md §8) sin tocar el esquema ni los datos:
--
--     D3  El contador de IDs comerciales NO retrocede.
--         nucleo.id_comercial_contador.ultimo es monótono no decreciente.
--         Antes: `tei_app` tiene UPDATE sobre la tabla y un UPDATE directo
--         bajaba `ultimo` (500 -> 0 aceptado), con lo que el siguiente código
--         repetía `SQM-00001`. El `COMMENT` de 0021:591-593 lo afirmaba; no
--         estaba impuesto.
--         Mecanismo: trigger BEFORE UPDATE `trg_contador_10_no_retrocede`
--         (nombre 10: corre antes de touch/version, orden alfabético de
--         triggers BEFORE). SQLSTATE 23514.
--         `nucleo.registrar_id_comercial_flete` usa `greatest(ultimo, …)`
--         (0021:668): nunca decrementa, no se rompe.
--
--     D9  Tope de 5 dígitos fail-closed en la generación.
--         Antes: con el contador en 99999, `lpad(v_numero::text, 5, '0')`
--         truncaba 100000 -> `SQM-10000` (9 caracteres, 6 dígitos) y
--         reutilizaba códigos ya emitidos.
--         Mecanismo: `nucleo.obtener_siguiente_id_comercial_flete` (misma
--         firma, `create or replace`) lanza 23514 si `v_numero > 99999`
--         DESPUÉS del upsert. El `raise` aborta la transacción del llamador:
--         el incremento se revierte y el número no se quema (mismo criterio
--         de 0021:600-601 y de `nucleo.folio_contador`, 0004:519-521).
--         Formato y `lpad` intactos: no se emite ningún código de 6 dígitos.
--
--     D2  El ID comercial de un viaje es inmutable una vez asignado.
--         Antes: `UPDATE nucleo.viajes SET id_comercial_flete=…` cambiaba
--         `SQM-00001` -> `SQM-09999` (y a NULL) sin objeción, contra el
--         `COMMENT` de 0021:566-570 y R-04 (sin renumerar).
--         Mecanismo: trigger BEFORE UPDATE `trg_viajes_10_id_comercial_inmutable`
--         que rechaza, con 23514:
--             old.id_comercial_flete is not null
--             and new.id_comercial_flete is distinct from old.id_comercial_flete
--         Asignar desde NULL (primer valor) SIGUE permitido: es el camino de
--         cutover/backfill. Asignar NULL sobre un valor asignado NO: liberaría
--         el código y permitiría reasignarlo a otro viaje (la UNIQUE parcial
--         solo cubre valores no nulos).
--         Corrección excepcional (p. ej. código emitido al viaje equivocado):
--         NO se hace por UPDATE. Requiere `alter table … disable trigger` como
--         dueño del esquema en una migración/operación deliberada, y queda
--         registrado por `trg_viajes_60_audit` + `nucleo.auditoria`. Es la
--         recomendación conservadora de roles.md §5 (cambio de relación
--         flete↔ID, sin renumerar).
--
--     D5  Máquina de estados de `nucleo.hoja_ruta`.
--         Antes: `rechazado -> cargado` y `cargado -> propuesto` eran
--         aceptados; la UNIQUE parcial `uq_hoja_ruta_carga_por_solicitud`
--         (0021:528-529) solo limita el `cargado` vigente, no el histórico.
--         Mecanismo: trigger BEFORE UPDATE `trg_hoja_ruta_10_transicion`,
--         análogo a `fn_solicitud_transicion` (0021:458-487). Transiciones
--         permitidas y únicas:
--             propuesto      -> solicitud_creada
--             solicitud_creada -> cargado | rechazado
--         `cargado` y `rechazado` son terminales: cualquier cambio de `estado`
--         desde ellos -> 23514.
--         Además `payload` es inmutable en UPDATE (ADR-0003 §14.2: el payload
--         propuesto no se reescribe; la corrección va en `valores_cargados`).
--         `valores_cargados` NO se restringe: es donde se corrige.
--
--   FUERA DE ALCANCE (decidido, no es olvido)
--     · D4 (prefijo colisionante / resolución por código): depende de D-16,
--       que no fijó prefijo único por cliente. Sigue abierto; documentado.
--     · D8 (`wa_message_id` único global): riesgo multiempresa aceptado; el
--       índice no se toca.
--     · D6 (rechazo solo-logra): es del backend (O2.5).
--     · D1 (script de rollback de 0021): lo escribe `qa`; aquí solo se
--       describe el rollback de 0022.
--
-- REQUISITO DE ORDEN: aplicar DESPUÉS de 0021_agente_whatsapp.sql (y esta,
--   después de 0020). Las precondiciones P1-P2 abortan con 23514 si falta.
--
-- PRECONDICIONES (deben dar el valor esperado; medidas en tei_test 2026-10-30
--   antes de aplicar: P1=8 tablas, P1b=2 funciones + 1 columna, P2=0, P3=0,
--   P4: 220 viajes / 0 con ID / 0 hoja_ruta / 0 contadores)
--   P1  Las 8 tablas del módulo existen (0021 aplicada).
--   P1b `nucleo.viajes.id_comercial_flete` y las 2 funciones de generación de
--       0021 existen (la columna y la función son el objeto de D2/D9).
--   P2  Los 3 triggers y las 3 funciones de 0022 NO existen (una
--       re-aplicación accidental falla en vez de reemplazar objetos).
--   P3  `obtener_siguiente_id_comercial_flete` es la versión de 0021: su
--       `prosrc` NO contiene el tope (99999). Si lo contiene, 0022 ya se
--       aplicó: no se re-aplica.
--   P4  Datos compatibles con los triggers (solo informativo + guarda):
--       · `viajes` con `id_comercial_flete` no nulo = 0 o valores que el
--         CHECK de 0021 ya valida (el trigger no valida filas existentes).
--       · `hoja_ruta`: sin filas en estado terminal que se actualicen en
--         esta migración (no se actualiza ninguna fila).
--       Si P4 encontrara algo inesperado, se reporta; NO se borra nada.
--
-- IMPACTO EN DATOS Y LOCKS
--   · 4 `CREATE FUNCTION` (3 nuevas + 1 `create or replace` sobre la de 0021)
--     y 3 `CREATE TRIGGER`. Cero INSERT/UPDATE/DELETE/backfill: **no se toca
--     ninguna fila**.
--   · Locks: `CREATE FUNCTION`/`CREATE TRIGGER` toman locks breves de catálogo
--     (ACCESS EXCLUSIVE sobre el catálogo; SHARE ROW EXCLUSIVE sobre la tabla
--     para crear el trigger). No reescriben la tabla; la duración no depende
--     del volumen. `create or replace function` no invalida datos: las
--     llamadas en curso terminan con la versión anterior.
--   · Costo en escritura: 1 llamada plpgsql por UPDATE de
--     `id_comercial_contador` (los contadores se actualizan una vez por ID
--     emitido), de `viajes` (tráfico normal) y de `hoja_ruta` (bajo). Medible,
--     no medido en producción.
--   · El legacy `public` NO se toca: ninguna sentencia referencia `public`.
--   · La app actual no cambia de comportamiento: ningún writer de
--     `backend/**` escribe `id_comercial_flete` (grep 2026-10-30: solo lo
--     nombran los tests de `supabase/tests/`) ni `hoja_ruta` (módulo apagado,
--     DEC-10).
--
-- COMPATIBILIDAD CON ESCRITORES EXISTENTES
--   · `obtener_siguiente_id_comercial_flete`: misma firma/retorno; sigue
--     emitiendo 1..99999 con el mismo formato. Solo agrega el rechazo en
--     100000 (antes: código truncado y reutilizado).
--   · `registrar_id_comercial_flete`: `greatest` (0021:668) => no decrece =>
--     el trigger D3 no lo afecta.
--   · `INSERT` de viaje con `id_comercial_flete` NULL o directo: sin trigger
--     en INSERT; sin cambios.
--   · `0021_01_smoke.sql` tiene DOS aserciones que describen el comportamiento
--     anterior y ahora abortan con `ON_ERROR_STOP`:
--       - C10E (`:566-578`) usa `propuesto -> cargado` directo para provocar el
--         23505 de `uq_hoja_ruta_carga_por_solicitud`; con D5 la transición se
--         rechaza antes con 23514.
--       - C11H (`:669-670`) afirma que se puede volver a NULL un ID asignado;
--         D2 lo prohíbe por diseño (liberaría el código).
--     Editar `supabase/tests/` es de `qa`, no de esta migración. Ver
--     docs/datos/agente-esquema.md §8.1.
--
-- ROLLBACK (orden inverso; no pierde datos, no revierte filas)
--   begin;
--     drop trigger if exists trg_hoja_ruta_10_transicion on nucleo.hoja_ruta;
--     drop function if exists nucleo.fn_hoja_ruta_transicion();
--     drop trigger if exists trg_viajes_10_id_comercial_inmutable on nucleo.viajes;
--     drop function if exists nucleo.fn_viaje_id_comercial_inmutable();
--     drop trigger if exists trg_contador_10_no_retrocede on nucleo.id_comercial_contador;
--     drop function if exists nucleo.fn_contador_no_retrocede();
--     -- restaurar la versión de 0021:603-636 (sin tope):
--     create or replace function nucleo.obtener_siguiente_id_comercial_flete(
--       p_empresa_id uuid, p_cliente_id uuid, p_prefijo text)
--     returns text language plpgsql as $$
--     declare v_numero bigint;
--     begin
--       if p_prefijo is null or p_prefijo !~ '^[A-Za-z0-9]{2,8}$' then
--         raise exception 'Prefijo comercial inválido: % (2 a 8 caracteres alfanuméricos)',
--           coalesce(p_prefijo, 'NULL') using errcode = '23514';
--       end if;
--       if not exists (select 1 from nucleo.clientes c
--                       where c.id = p_cliente_id and c.empresa_id = p_empresa_id) then
--         raise exception 'El cliente % no pertenece a la empresa % (la secuencia es por empresa-cliente)',
--           p_cliente_id, p_empresa_id using errcode = '23514';
--       end if;
--       insert into nucleo.id_comercial_contador (empresa_id, cliente_id, ultimo)
--         values (p_empresa_id, p_cliente_id, 1)
--         on conflict (empresa_id, cliente_id)
--         do update set ultimo = nucleo.id_comercial_contador.ultimo + 1
--         returning ultimo into v_numero;
--       return upper(p_prefijo) || '-' || lpad(v_numero::text, 5, '0');
--     end; $$;
--   commit;
--   Revertir REABRE D2, D3, D5 y D9: la base vuelve a aceptar reasignación de
--   ID, retroceso del contador, transiciones ilegales y códigos truncados.
--   No hay pérdida de datos: no se revierte ninguna fila y los triggers de
--   auditoría de 0021 siguen vigentes.
--
-- PRUEBAS (todas BEGIN/ROLLBACK; ver docs/datos/agente-esquema.md §8.1)
--   1. Sondas D2/D3/D5/D9 con rol `postgres` (BYPASSRLS) y con `tei_app`:
--      antes aceptaban (baseline 2026-10-30), después fallan con 23514.
--   2. Mutación de 0022: retirar cada trigger/función en una transacción y
--      confirmar que el caso ilegal vuelve a aceptarse (revertido con ROLLBACK).
--   3. Regresión de 0021: `0021_02` (concurrencia real), `0021_03` (RLS con
--      `tei_app`) y `0021_04` (mutación) verdes. `0021_01_smoke.sql` NO queda
--      14/14: sus aserciones C10E (`:566-578`) y C11H (`:669-670`) describen
--      el comportamiento anterior a D5/D2. No se editó `supabase/tests/`
--      (dueño: `qa`); con esas dos aserciones adaptadas, los casos 1-14 corren
--      sin errores (verificado en copia fuera del repo).
--
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- 0. Precondiciones defendidas (fallan con mensaje explícito; no "arreglan")
-- ----------------------------------------------------------------------------
do $$
declare
  v_n integer;
  v_detalle text;
begin
  -- P1: 0021 aplicada (8 tablas del módulo)
  select count(*) into v_n
    from pg_tables
   where schemaname = 'nucleo'
     and tablename in ('contactos_whatsapp','permisos_contacto','conversaciones',
                       'conversacion_mensajes','solicitudes','hoja_ruta',
                       'id_comercial_contador','auditoria_consultas_agente');
  if v_n <> 8 then
    raise exception 'PRECONDICIÓN P1: % de 8 tablas del módulo agente (falta aplicar 0021)', v_n
      using errcode = '23514';
  end if;

  -- P1b: columna y funciones de 0021 que 0022 endurece
  select count(*) into v_n
    from pg_attribute a
    join pg_class c on c.oid = a.attrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'viajes'
     and a.attname = 'id_comercial_flete' and a.attnum > 0 and not a.attisdropped;
  if v_n <> 1 then
    raise exception 'PRECONDICIÓN P1b: falta nucleo.viajes.id_comercial_flete'
      using errcode = '23514';
  end if;

  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname in ('obtener_siguiente_id_comercial_flete',
                       'registrar_id_comercial_flete');
  if v_n <> 2 then
    raise exception 'PRECONDICIÓN P1b: % de 2 funciones de ID comercial (falta 0021)', v_n
      using errcode = '23514';
  end if;

  -- P2: los mecanismos de 0022 no existen (no reemplazar en silencio)
  select string_agg(t.tgname, ', ') into v_detalle
    from pg_trigger t
    join pg_class c on c.oid = t.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and not t.tgisinternal
     and t.tgname in ('trg_contador_10_no_retrocede',
                      'trg_viajes_10_id_comercial_inmutable',
                      'trg_hoja_ruta_10_transicion');
  if v_detalle is not null then
    raise exception 'PRECONDICIÓN P2: ya existen triggers de 0022: %', v_detalle
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
    raise exception 'PRECONDICIÓN P2: ya existen funciones de 0022: %', v_detalle
      using errcode = '23514';
  end if;

  -- P3: la función sigue siendo la de 0021 (D9 sin aplicar)
  select count(*) into v_n
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
   where n.nspname = 'nucleo'
     and p.proname = 'obtener_siguiente_id_comercial_flete'
     and p.prosrc like '%99999%';
  if v_n > 0 then
    raise exception 'PRECONDICIÓN P3: obtener_siguiente_id_comercial_flete ya tiene el tope; 0022 ya fue aplicada'
      using errcode = '23514';
  end if;

  -- P4: datos existentes compatibles (solo lectura; se reportan por NOTICE)
  select count(*) into v_n from nucleo.viajes where id_comercial_flete is not null;
  raise notice 'P4 nucleo.viajes con id_comercial_flete no nulo: %', v_n;
  select count(*) into v_n from nucleo.hoja_ruta;
  raise notice 'P4 nucleo.hoja_ruta filas: %', v_n;
  select count(*) into v_n from nucleo.id_comercial_contador;
  raise notice 'P4 nucleo.id_comercial_contador filas: %', v_n;
end;
$$;

-- ----------------------------------------------------------------------------
-- 1. D3 — el contador comercial no retrocede
--    Mecanismo en la tabla, no en la función: cubre a TODOS los escritores
--    (las 2 funciones del núcleo, `tei_app` por UPDATE directo, scripts y
--    seeds). `ultimo` es bigint NOT NULL (0021:575); comparar es total.
--    Nombre `trg_contador_10_…`: los triggers BEFORE se ejecutan en orden
--    alfabético y "10" < "audit"/"touch"/"version".
-- ----------------------------------------------------------------------------
create or replace function nucleo.fn_contador_no_retrocede()
returns trigger
language plpgsql
as $$
begin
  if new.ultimo < old.ultimo then
    raise exception
      'El contador de IDs comerciales (cliente %) no retrocede: % -> % (R-04: sin reutilización de códigos)',
      new.cliente_id, old.ultimo, new.ultimo
      using errcode = '23514';
  end if;
  return new;
end;
$$;

comment on function nucleo.fn_contador_no_retrocede() is
  'R-04/D3: nucleo.id_comercial_contador.ultimo es monótono no decreciente. '
  'Cubre también un UPDATE directo de tei_app. Bajar el contador (corregir '
  'una carga errónea) exige deshabilitar el trigger como dueño en una '
  'operación deliberada y auditada, no un UPDATE de aplicación.';

create trigger trg_contador_10_no_retrocede
  before update on nucleo.id_comercial_contador
  for each row execute function nucleo.fn_contador_no_retrocede();

-- ----------------------------------------------------------------------------
-- 2. D2 — ID comercial inmutable una vez asignado
--    `before update` (sin lista de columnas): también detecta una escritura
--    del ID hecha por otro trigger, no solo por la sentencia del cliente.
--    Insertar con NULL o con valor (cutover/backfill) no pasa por aquí.
-- ----------------------------------------------------------------------------
create or replace function nucleo.fn_viaje_id_comercial_inmutable()
returns trigger
language plpgsql
as $$
begin
  if old.id_comercial_flete is not null
     and new.id_comercial_flete is distinct from old.id_comercial_flete then
    raise exception
      'El ID comercial del viaje % es inmutable una vez asignado (% -> %). '
      'Una corrección excepcional requiere migración/operación deliberada como dueño del esquema (queda auditada)',
      old.id, old.id_comercial_flete, coalesce(new.id_comercial_flete, 'NULL')
      using errcode = '23514';
  end if;
  return new;
end;
$$;

comment on function nucleo.fn_viaje_id_comercial_inmutable() is
  'R-04/D2: nucleo.viajes.id_comercial_flete no cambia después de asignado '
  '(incluido el paso a NULL: liberaría el código para reasignarlo, porque la '
  'UNIQUE parcial solo cubre valores no nulos). Asignar desde NULL sigue '
  'permitido (cutover/backfill). Corregir un código mal emitido se hace como '
  'cambio de relación flete↔ID con migración deliberada, sin renumerar.';

create trigger trg_viajes_10_id_comercial_inmutable
  before update on nucleo.viajes
  for each row execute function nucleo.fn_viaje_id_comercial_inmutable();

-- ----------------------------------------------------------------------------
-- 3. D5 — máquina de estados de la hoja de ruta + payload inmutable
--    Terminales: cargado y rechazado. Cambiar cualquier OTRA columna en un
--    estado terminal sigue permitido (p. ej. `valores_cargados`, que es donde
--    se corrige): solo `estado` y `payload` quedan restringidos.
-- ----------------------------------------------------------------------------
create or replace function nucleo.fn_hoja_ruta_transicion()
returns trigger
language plpgsql
as $$
begin
  if new.payload is distinct from old.payload then
    raise exception
      'El payload de la hoja de ruta % es inmutable: la corrección va en valores_cargados (ADR-0003 §14.2)',
      old.id
      using errcode = '23514';
  end if;

  if new.estado is distinct from old.estado then
    if old.estado = 'propuesto' and new.estado = 'solicitud_creada' then
      return new;
    elsif old.estado = 'solicitud_creada' and new.estado in ('cargado', 'rechazado') then
      return new;
    elsif old.estado in ('cargado', 'rechazado') then
      raise exception
        'La hoja de ruta % está en estado terminal %: no admite transición a %',
        old.id, old.estado, new.estado
        using errcode = '23514';
    else
      raise exception
        'Transición de hoja de ruta no permitida: % -> % '
        '(permitidas: propuesto->solicitud_creada y solicitud_creada->cargado|rechazado)',
        old.estado, new.estado
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

comment on function nucleo.fn_hoja_ruta_transicion() is
  'D-10/D5: propuesto -> solicitud_creada -> cargado|rechazado; cargado y '
  'rechazado son terminales. El payload propuesto no se reescribe '
  '(ADR-0003 §14.2); la corrección va en valores_cargados. INSERT no se '
  'restringe aquí: los CHECK de la tabla (0021:520-522) cubren el alta.';

create trigger trg_hoja_ruta_10_transicion
  before update on nucleo.hoja_ruta
  for each row execute function nucleo.fn_hoja_ruta_transicion();

-- ----------------------------------------------------------------------------
-- 4. D9 — tope de 5 dígitos fail-closed
--    Misma firma y mismo formato que 0021:603-636; solo agrega el rechazo
--    después del upsert. El `raise` revierte el incremento de la transacción
--    (el número no se quema). `lpad` no cambia: nunca se emite un código de
--    6 dígitos.
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

  -- D9: el formato es PREFIJO-99999. Superar el tope NO se trunca ni se
  -- reutiliza: se rechaza y la transacción revierte el incremento.
  if v_numero > 99999 then
    raise exception
      'Tope de numeración comercial agotado para empresa % / cliente %: % excede 99999 (R-04, 5 dígitos). '
      'No se emite código; el incremento del contador se revierte con la transacción',
      p_empresa_id, p_cliente_id, v_numero
      using errcode = '23514';
  end if;

  return upper(p_prefijo) || '-' || lpad(v_numero::text, 5, '0');
end;
$$;

commit;

-- ============================================================================
-- VERIFICACIÓN POST (en tei_test; todas las sondas BEGIN/ROLLBACK)
--   1) D3: `update nucleo.id_comercial_contador set ultimo = 0` con `ultimo`
--      = 500 => 23514 ("no retrocede"); el contador sigue en 500.
--   2) D9: contador en 99999 => `obtener_siguiente…` => 23514 y el contador
--      sigue en 99999 (no se quemó ningún número). 99998 => devuelve
--      PREFIJO-99999.
--   3) D2: SQM-00001 -> SQM-09999 => 23514; SQM-00001 -> NULL => 23514;
--      NULL -> SQM-00001 => aceptado.
--   4) D5: rechazado->cargado, cargado->propuesto, propuesto->cargado =>
--      23514; propuesto->solicitud_creada->cargado => aceptado; cambio de
--      `payload` => 23514; cambio de `valores_cargados` => aceptado.
--   5) Regresión: 0021_01_smoke.sql, 0021_02_concurrencia_id_comercial.py,
--      0021_03_rls_tei_app.sql, 0021_04_mutacion.sql.
-- ============================================================================
