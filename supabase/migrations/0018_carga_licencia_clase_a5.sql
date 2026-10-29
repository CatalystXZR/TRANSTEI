-- ============================================================================
-- TRANSTEI — Migración 0018: carga de clase de licencia A5
-- ============================================================================
--
-- OBJETIVO
--   Cargar `nucleo.choferes.licencia_clase = 'A5'` en los choferes activos de
--   la empresa operativa que hoy no tienen clase registrada, para que R-02
--   (A5 obligatoria y bloqueante, migración 0016) no impida asignarlos.
--
--   Origen del dato: instrucción del dueño del 2026-10-29 ("carga el dato").
--   La clase A5 es la única que TEI acepta para su flota (R-02). NO se inventa
--   la clase de un chofer sin respaldo documental: solo se carga donde existe
--   un documento `licencia_conducir` vigente en `nucleo.documentos`. Los que no
--   lo tienen se reportan y quedan sin tocar.
--
--   🚩 PROCEDENCIA: esta carga NO fue contrastada contra la licencia física de
--   cada conductor. Es una declaración del dueño apoyada en la existencia del
--   documento. Si una licencia física dice otra clase, se corrige con un
--   `update` puntual y queda auditado por `trg_choferes_*`.
--
-- OBJETOS AFECTADOS
--   * nucleo.choferes.licencia_clase — UPDATE de filas (no cambia el esquema).
--   * No se agregan constraints, triggers ni columnas.
--
-- ALCANCE
--   * Solo empresa `TEI` (la operativa). Las empresas de prueba (`TST15`,
--     `QA-*`, `POD-*`, `ALT-*`, `AUD-*`) se dejan intactas a propósito: sus
--     fixtures necesitan clases ausentes y distintas de A5 para probar R-02.
--
-- PRECONDICIONES (informativas; se ejecutan antes y después)
--   P18.1 — choferes TEI activos sin clase:
--
--     select c.id, c.rut, c.nombre,
--            exists (select 1 from nucleo.documentos d
--                     where d.recurso_tipo='chofer' and d.chofer_id=c.id
--                       and d.tipo='licencia_conducir' and d.es_vigente) as tiene_doc
--       from nucleo.choferes c
--       join nucleo.empresas e on e.id = c.empresa_id
--      where e.codigo = 'TEI' and c.activo and c.estado <> 'baja'
--        and coalesce(btrim(c.licencia_clase), '') = ''
--      order by c.nombre;
--
--   P18.2 — de esos, sin documento (NO se tocan):
--     la misma consulta filtrando `tiene_doc = false`.
--
-- IMPACTO Y LOCKS
--   * UPDATE acotado por empresa y por `licencia_clase` vacía. En el piloto son
--     pocas filas. Toma lock de fila por fila; sin reescritura de tabla.
--
-- ROLLBACK
--   No hay forma automática de distinguir "A5 cargado por esta migración" de
--   "A5 declarado antes". Se revierte por lista explícita de RUT, que esta
--   migración imprime en su NOTICE. Si se necesita rollback:
--
--     update nucleo.choferes set licencia_clase = null
--      where id = any (array[...]::uuid[]);
--
--   (La lista se obtiene del log de aplicación; no se deja hardcodeada porque
--   depende de los datos del entorno.)
--
-- COMPATIBILIDAD
--   * `public.choferes` no tiene clase de licencia: no se toca.
--   * `trg_viajes_03_licencia_a5` (0016) empieza a permitir asignar esos
--     choferes, que es exactamente el objetivo.
-- ============================================================================

do $$
declare
  v_empresa uuid;
  v_ids uuid[];
  v_ruts text[];
  v_sin_doc int;
begin
  select id into v_empresa from nucleo.empresas where codigo = 'TEI';
  if v_empresa is null then
    raise notice '0018: no existe empresa TEI; nada que cargar.';
    return;
  end if;

  select count(*) into v_sin_doc
    from nucleo.choferes c
   where c.empresa_id = v_empresa
     and c.activo and c.estado <> 'baja'
     and coalesce(btrim(c.licencia_clase), '') = ''
     and not exists (
       select 1 from nucleo.documentos d
        where d.recurso_tipo = 'chofer' and d.chofer_id = c.id
          and d.tipo = 'licencia_conducir' and d.es_vigente);

  with objetivo as (
    select c.id, c.rut
      from nucleo.choferes c
     where c.empresa_id = v_empresa
       and c.activo and c.estado <> 'baja'
       and coalesce(btrim(c.licencia_clase), '') = ''
       and exists (
         select 1 from nucleo.documentos d
          where d.recurso_tipo = 'chofer' and d.chofer_id = c.id
            and d.tipo = 'licencia_conducir' and d.es_vigente)
  ), act as (
    update nucleo.choferes c
       set licencia_clase = 'A5'
      from objetivo o
     where c.id = o.id
    returning c.id, c.rut
  )
  select coalesce(array_agg(id), '{}'), coalesce(array_agg(rut), '{}')
    into v_ids, v_ruts
    from act;

  raise notice '0018: choferes TEI actualizados a A5=%, omitidos sin documento=%, ruts=%',
    coalesce(array_length(v_ids, 1), 0), v_sin_doc, v_ruts;
end $$;

comment on column nucleo.choferes.licencia_clase is
  'Clase de licencia. R-02 (dueño 2026-10-29): solo A5 es válida y bloqueante. Carga inicial de 0018 declarada por el dueño, no contrastada con la licencia física.';
