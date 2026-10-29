-- ============================================================================
-- TRANSTEI — Migración 0019: comisión del 10 % en los choferes del piloto
-- ============================================================================
--
-- OBJETIVO
--   Alinear `nucleo.choferes.porcentaje_comision` con R-01 (10 % de la
--   producción facturada del mes) en los choferes de la empresa operativa que
--   quedaron en 0 por el seed anterior a la regla.
--
--   La migración 0017 cambió el DEFAULT de la columna, no las filas existentes
--   (un 0 puede ser intencional). Aquí se decide explícitamente por la empresa
--   operativa: R-05 del registro de orquestación reportó 58 filas en 0 en toda
--   la base; la mayoría son empresas de prueba.
--
-- OBJETOS AFECTADOS
--   * nucleo.choferes.porcentaje_comision — UPDATE de filas de `TEI` con valor 0.
--   * No se toca `public.choferes.porcentaje_produccion` (nómina legacy):
--     SEC-003 sigue abierto y lo resuelve un ADR, no una migración.
--
-- PRECONDICIONES (informativas)
--   P19.1 — choferes TEI activos con comisión 0:
--
--     select c.rut, c.nombre, c.porcentaje_comision
--       from nucleo.choferes c join nucleo.empresas e on e.id=c.empresa_id
--      where e.codigo='TEI' and c.activo and c.estado<>'baja'
--        and c.porcentaje_comision = 0;
--
-- IMPACTO Y LOCKS
--   * UPDATE acotado por empresa. Pocas filas. Sin cambios de esquema.
--
-- ROLLBACK
--   Los RUT afectados se imprimen en el NOTICE:
--
--     update nucleo.choferes set porcentaje_comision = 0
--      where id = any (array[...]::uuid[]);
--
-- COMPATIBILIDAD
--   * `public.*`: intacto.
--   * `servicio_gastos.py:460` (costo/margen) empieza a usar 10 % para esos
--     choferes; la nómina legacy sigue usando `public.choferes`. La divergencia
--     SEC-003 queda registrada hasta que el ADR decida la fuente canónica.
-- ============================================================================

do $$
declare
  v_empresa uuid;
  v_ruts text[];
begin
  select id into v_empresa from nucleo.empresas where codigo = 'TEI';
  if v_empresa is null then
    raise notice '0019: no existe empresa TEI; nada que alinear.';
    return;
  end if;

  with act as (
    update nucleo.choferes c
       set porcentaje_comision = 0.10
     where c.empresa_id = v_empresa
       and c.activo and c.estado <> 'baja'
       and c.porcentaje_comision = 0
    returning c.rut
  )
  select coalesce(array_agg(rut), '{}') into v_ruts from act;

  raise notice '0019: choferes TEI con comisión alineada a 10%% = %, ruts=%',
    coalesce(array_length(v_ruts, 1), 0), v_ruts;
end $$;
