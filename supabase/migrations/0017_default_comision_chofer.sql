-- ============================================================================
-- TRANSTEI — Migración 0017: default de comisión del chofer = 10 %
-- ============================================================================
--
-- OBJETIVO
--   Alinear el valor por defecto de la comisión del conductor con la regla
--   R-01 aprobada por el dueño el 2026-10-29: la comisión es el 10 % de la
--   facturación del mes, configurable por chofer.
--
--   Hoy `nucleo.choferes.porcentaje_comision` nace en 0 (0004:300-301), de modo
--   que un chofer creado sin especificar porcentaje devenga 0 % de comisión.
--   Es un error de dinero silencioso: no falla, paga de menos.
--
-- OBJETOS AFECTADOS
--   * nucleo.choferes.porcentaje_comision — ALTER COLUMN SET DEFAULT 0.10.
--     No se modifica el CHECK (between 0 and 1) de 0004:301.
--
-- ALCANCE DE DATOS
--   * El cambio de default afecta SOLO a filas nuevas. Las filas existentes
--     conservan su valor, incluido 0.
--   * NO se hace backfill: un 0 existente puede ser intencional (chofer sin
--     comisión). Convertirlo a 10 % cambiaría dinero ya pactado. La consulta
--     P17.1 lo reporta para que negocio decida caso a caso.
--
-- PRECONDICIONES (ejecutar antes; informativas, no bloquean)
--   P17.1 — choferes con comisión 0 (revisar si es intencional):
--
--     select empresa_id, rut, nombre, porcentaje_comision
--       from nucleo.choferes
--      where porcentaje_comision = 0
--      order by empresa_id, nombre;
--
-- IMPACTO Y LOCKS
--   * ALTER COLUMN SET DEFAULT: cambio de catálogo, no reescribe filas,
--     no toma lock de filas. Instantáneo.
--
-- ROLLBACK
--   alter table nucleo.choferes alter column porcentaje_comision set default 0;
--
-- COMPATIBILIDAD
--   * public.*: intacto (la comisión legacy vive en public.choferes y ya se
--     alineó en el modelo y el seed).
--   * backend: `nucleo/models.py` ya declara default 0.10; este cambio alinea
--     la base con el modelo para altas que no envían el campo.
-- ============================================================================

alter table nucleo.choferes
  alter column porcentaje_comision set default 0.10;

comment on column nucleo.choferes.porcentaje_comision is
  'R-01: comisión sobre facturación del mes. Default 10 %; configurable por chofer.';
