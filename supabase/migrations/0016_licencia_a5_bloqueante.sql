-- ============================================================================
-- TRANSTEI — Migración 0016
-- R-02: la única clase de licencia asignable es A5 (bloqueo en la base) y la
-- ventana de aviso de documentos por defecto es 14 días.
-- ============================================================================
--
-- OBJETIVO
--   Imponer en PostgreSQL la regla aprobada por el dueño: "A5, ninguna otra
--   sirve". Un chofer con clase distinta de A5, o sin clase registrada, no
--   puede quedar asignado a un viaje. La vigencia del documento de licencia
--   ya es bloqueo duro desde 0004 (validar_documentos_recurso, 0004:1080-1102:
--   faltante en 1091-1094, vencido en 1097-1101); esta migración NO la relaja
--   ni la convierte en advertencia.
--
--   Además deja la ventana de aviso por defecto en 14 días
--   (empresas.dias_alerta_documentos), sin reescribir filas existentes.
--
-- INVARIANTES QUE IMPONE
--   INV-R02-01 (bloqueante, DB)
--     Si nucleo.viajes.chofer_id no es nulo y estado <> 'anulado', entonces
--     upper(btrim(nucleo.choferes.licencia_clase)) = 'A5'.
--     Mecanismo: trigger BEFORE INSERT OR UPDATE en nucleo.viajes.
--     SQLSTATE: 23514.
--   INV-R02-02 (bloqueante, DB, ya existente)
--     El documento 'licencia_conducir' del chofer debe vencer en o después
--     del fin efectivo del viaje (+ margen). Vencido => 23514.
--     Mecanismo: nucleo.validar_documentos_recurso (0004:1019-1104),
--     aplicado a todo viaje con los tres recursos por 0015.
--   INV-R02-03 (ADVERTENCIA, no DB)
--     Licencia que vence entre 14 y 1 días: el servicio avisa, NO bloquea.
--     No se convierte en constraint: es notificación, no una regla de
--     integridad. Ver §ADVERTENCIA.
--
-- DECISIÓN DE DISEÑO — dónde vive la regla
--   El dueño dijo "A5, ninguna otra sirve, así de simple": la regla es GLOBAL,
--   no configurable por tracto. Por eso NO se implementa en
--   nucleo.tractos.licencias_permitidas (0004:207, array configurable) sino en
--   un trigger sobre el viaje.
--   Qué pasa con el array (decisión explícita, no olvido):
--     * NO se borra, NO se restringe y NO se reescribe: contiene datos y la UI
--       de maestros lo muestra/edita (frontend/src/components/maestros/config.ts:76).
--     * Se marca DEPRECADO con COMMENT: ya no otorga ni restringe permisos.
--     * Si algún tracto lo tiene con valores distintos de A5, la configuración
--       miente (sugiere que A3/A4 sirven). Se detecta con P2.3 y se corrige
--       con una sentencia separada y auditada, no dentro de esta migración.
--     * No se agrega CHECK al array porque eso rechazaría la edición de filas
--       existentes desde la UI (rompería maestros) sin mejorar la garantía,
--       que ya es global. Handoff: `frontend` debe dejar de ofrecer el campo y
--       `backend` debe dejar de validar contra él (politicas.py:297-320).
--   Por qué el bloqueo va en el VIAJE y no en choferes.licencia_clase:
--     R-02 dice "bloqueo de la asignación". Un CHECK en la tabla de choferes
--     impediría registrar un conductor con clase distinta (dato histórico o
--     de otra función) y obligaría a un backfill destructivo. El trigger sobre
--     el viaje bloquea exactamente lo que la regla prohíbe.
--
--   GAP RESIDUAL DECLARADO (no garantizado por esta migración):
--     "Un chofer asignado a un viaje vigente no puede ser degradado de A5 a
--      otra clase en nucleo.choferes". No se impone trigger en choferes
--      porque excede R-02 ("la asignación") y podría bloquear correcciones de
--      datos. Se detecta con P2.1 y, una vez que el chofer queda inválido, la
--      siguiente (re)asignación o cualquier UPDATE con estado 'asignado' falla.
--      Registrado como riesgo abierto en docs/datos/migraciones/0016-licencia-a5.md.
--
-- OBJETOS AFECTADOS
--   * nucleo.empresas.dias_alerta_documentos — ALTER COLUMN SET DEFAULT 14.
--     (No se toca el CHECK 0..365 de 0004:121.)
--   * nucleo.fn_viaje_licencia_a5() — NUEVA.
--   * trigger trg_viajes_03_licencia_a5 en nucleo.viajes — NUEVO.
--   * COMMENT en nucleo.tractos.licencias_permitidas y
--     nucleo.choferes.licencia_clase.
--   * Sin cambios de datos, sin DROP, sin backfill.
--
-- PRECONDICIONES (ejecutar ANTES de aplicar)
--   P2.1 — viajes vigentes con chofer de clase distinta de A5 (deriva previa).
--          Informe obligatorio; NO se corrigen ni se borran aquí.
--          Se espera 0. Si > 0 son asignaciones que la regla considera
--          inválidas: operación decide reasignar o corregir la clase.
--
--     select v.empresa_id, v.numero_viaje, v.estado,
--            c.nombre, c.licencia_clase
--       from nucleo.viajes v
--       join nucleo.choferes c
--         on c.id = v.chofer_id and c.empresa_id = v.empresa_id
--      where v.estado <> 'anulado'
--        and upper(btrim(coalesce(c.licencia_clase, ''))) <> 'A5'
--      order by v.empresa_id, v.inicio_planificado;
--
--   P2.2 — choferes activos que ya no podrán asignarse (universo del bloqueo):
--
--     select empresa_id, rut, nombre, licencia_clase, estado
--       from nucleo.choferes
--      where activo and estado <> 'baja'
--        and upper(btrim(coalesce(licencia_clase, ''))) <> 'A5'
--      order by empresa_id, nombre;
--
--   P2.3 — tractos cuya configuración de licencias contradice R-02
--          (el array deja de tener efecto; se reporta para limpieza aparte):
--
--     select empresa_id, patente, licencias_permitidas
--       from nucleo.tractos
--      where licencias_permitidas <> '{}'::text[]
--        and not (licencias_permitidas <@ array['A5']::text[])
--      order by empresa_id, patente;
--
--   P2.4 — efecto del cambio de default (NO cambia filas existentes):
--
--     select id, codigo, dias_alerta_documentos
--       from nucleo.empresas
--      order by codigo;
--
-- IMPACTO EN DATOS Y LOCKS
--   * ALTER TABLE ... SET DEFAULT: solo catálogo, AccessExclusiveLock de
--     milisegundos, sin reescritura de tabla.
--   * CREATE OR REPLACE FUNCTION + CREATE TRIGGER: ShareRowExclusiveLock breve
--     sobre nucleo.viajes.
--   * COMMENT: catálogo.
--   * Sin backfill => sin locks largos, sin pérdida de datos.
--   * public (legacy): NO se toca. El legacy no tiene clase de licencia
--     (0001) y no se ve afectado.
--
-- §ADVERTENCIA — ventana de 14 días (servicio, NO base)
--   R-02 pide avisar (no bloquear) cuando la licencia vence entre 14 y 1 días.
--   Eso es notificación: vive en el servicio
--   (backend/app/nucleo/servicio_alertas.py:125, servicio_disponibilidad.py:245,
--   ambos leen empresas.dias_alerta_documentos). Esta migración NO agrega
--   ninguna constraint de "por vencer".
--   Interacción que debe quedar clara: el bloqueo duro de 0004 compara contra
--   el FIN DEL VIAJE (+ dias_margen_documentos, 0004:1276-1279), no contra
--   "hoy + 14". Una licencia que vence en 10 días NO bloquea un viaje que
--   termina en 2 días; sí bloquea uno que termina después del vencimiento,
--   porque entonces la licencia está vencida durante el viaje (correcto).
--   Si una empresa sube dias_margen_documentos, el bloqueo puede ocurrir
--   antes de la ventana de aviso: son perillas distintas y así se documenta.
--
-- §DEFAULT 14 — qué cambia y qué NO
--   alter table ... set default 14 cambia el valor para INSERT futuros.
--   Las filas EXISTENTES conservan 30 (o el valor que tengan) hasta que se
--   actualicen explícitamente. No hay backfill en esta migración: reescribir
--   configuración de empresas sin constancia es exactamente lo que AGENTS.md §8
--   prohíbe. Si el dueño quiere 14 en las empresas existentes, es un paso
--   SEPARADO, autorizado y con conteos:
--
--     -- [REQUIERE AUTORIZACIÓN EXPLÍCITA] paso separado, fuera de esta migración
--     select count(*) from nucleo.empresas where dias_alerta_documentos = 30;
--     update nucleo.empresas
--        set dias_alerta_documentos = 14,
--            updated_by = 'migracion_0016_backfill'
--      where dias_alerta_documentos = 30;
--     -- queda registrado por trg_empresas_audit (0004:1760-1761)
--
--   Ojo: backend/app/nucleo/models.py:221 tiene default=30 en Python. Un
--   INSERT del backend envía 30 explícito y el DEFAULT de la base NO se
--   aplica. Handoff a `backend`: cambiar ese default a 14 (o dejar que la
--   base decida). Mismo caso en scripts/seed_local.py:162-166, que inserta 30
--   literal.
--
-- ROLLBACK (exacto, sin pérdida de datos)
--   1. drop trigger if exists trg_viajes_03_licencia_a5 on nucleo.viajes;
--      drop function if exists nucleo.fn_viaje_licencia_a5();
--   2. alter table nucleo.empresas
--        alter column dias_alerta_documentos set default 30;
--   3. comment on column nucleo.tractos.licencias_permitidas is null;
--      comment on column nucleo.choferes.licencia_clase is null;
--   No hay datos que revertir. El rollback vuelve a permitir asignar
--   cualquier clase de licencia: es un incidente, no una operación rutinaria.
--
-- VERIFICACIÓN POST
--   V1. insert/update de un viaje con chofer clase A3 -> 23514 con mensaje
--       'Licencia A5 requerida' (supabase/tests/0016_01_...).
--   V2. viaje con chofer A5 cuya licencia vence en 10 días y viaje que termina
--       antes -> se acepta (supabase/tests/0016_02_...).
--   V3. viaje con chofer A5 y licencia vencida -> 23514
--       (supabase/tests/0016_03_...).
--   V4. select column_default from information_schema.columns
--        where table_schema='nucleo' and table_name='empresas'
--          and column_name='dias_alerta_documentos';  -> '14'
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Ventana de aviso por defecto: 14 días (sin tocar filas existentes)
-- ----------------------------------------------------------------------------
alter table nucleo.empresas
  alter column dias_alerta_documentos set default 14;

comment on column nucleo.empresas.dias_alerta_documentos is
  'Días de anticipación para AVISAR (no bloquear) documentos por vencer. '
  'Default 14 desde 0016 (R-02). Las filas creadas antes de 0016 conservan su '
  'valor hasta que se actualicen explícitamente.';

-- ----------------------------------------------------------------------------
-- 2. Clase de licencia A5 obligatoria en la asignación
-- ----------------------------------------------------------------------------
create or replace function nucleo.fn_viaje_licencia_a5()
returns trigger
language plpgsql
as $$
declare
  v_clase  text;
  v_chofer text;
begin
  -- Sin chofer no hay asignación que validar. Un viaje anulado libera recursos.
  if new.chofer_id is null then
    return new;
  end if;
  if new.estado = 'anulado' then
    return new;
  end if;

  -- Misma excepción operativa que 0004:1128-1138 y 0015: un viaje ya
  -- despachado que solo cambia de estado no se congela por una corrección
  -- posterior en los maestros. El bloqueo se aplica al (re)asignar.
  if tg_op = 'UPDATE' then
    if new.estado <> 'asignado' and new.chofer_id = old.chofer_id then
      return new;
    end if;
  end if;

  select upper(btrim(coalesce(c.licencia_clase, ''))),
         coalesce(
           nullif(btrim(c.nombre || ' ' || coalesce(c.apellido_paterno, '')), ''),
           c.rut
         )
    into v_clase, v_chofer
    from nucleo.choferes c
   where c.id = new.chofer_id
     and c.empresa_id = new.empresa_id;

  -- Si el chofer no existe, la FK compuesta (0004:656-657) o fn_viaje_validar
  -- dan el error correcto; aquí no se inventa otro.
  if not found then
    return new;
  end if;

  if v_clase <> 'A5' then
    raise exception 'Licencia A5 requerida (R-02): el chofer % tiene clase %',
      v_chofer,
      case when v_clase = '' then 'sin registrar' else '"' || v_clase || '"' end
      using errcode = '23514',
            hint = 'Solo la clase A5 puede asignarse a un viaje';
  end if;

  return new;
end;
$$;

comment on function nucleo.fn_viaje_licencia_a5() is
  'R-02/INV-R02-01: bloquea asignar a un viaje un chofer cuya licencia no sea '
  'clase A5 (incluye clase ausente). Regla global, no configurable por tracto.';

-- Orden de disparo (alfabético en PostgreSQL):
--   00_ventana -> 03_licencia_a5 -> 05_documentos (0015) -> 10_validar -> ...
-- Se revisa la clase antes que los documentos para que el mensaje sea el
-- correcto: un chofer A3 con licencia vencida falla por clase, no por fecha.
drop trigger if exists trg_viajes_03_licencia_a5 on nucleo.viajes;
create trigger trg_viajes_03_licencia_a5
  before insert or update on nucleo.viajes
  for each row execute function nucleo.fn_viaje_licencia_a5();

-- ----------------------------------------------------------------------------
-- 3. Deprecación explícita de la configuración por tracto
-- ----------------------------------------------------------------------------
comment on column nucleo.tractos.licencias_permitidas is
  'DEPRECADO (0016 / R-02): la clase válida es A5 para toda la flota. Este '
  'array YA NO otorga ni restringe permisos; la regla se impone en '
  'nucleo.fn_viaje_licencia_a5. Se conserva por compatibilidad de datos y UI; '
  'no se debe usar para autorizar asignaciones.';

comment on column nucleo.choferes.licencia_clase is
  'Clase de licencia de conducir. R-02 (0016): solo A5 es asignable a un viaje; '
  'clase distinta o ausente bloquea la asignación en la base (23514).';

-- ============================================================================
-- Fin de 0016. Re-ejecutable: ALTER ... SET DEFAULT es idempotente,
-- CREATE OR REPLACE + DROP TRIGGER IF EXISTS también. No modifica datos.
-- ============================================================================
