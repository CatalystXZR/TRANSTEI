-- 0027 — GRANTs al rol de plataforma para los objetos de la Ola B
--
-- Motivo: las migraciones 0024–0026 se aplicaron en local como `supabase_admin`
-- (no por la cadena de `supabase db reset`), por lo que el rol de plataforma
-- usado por scripts (`postgres`, BYPASSRLS) quedó sin DML sobre esas tablas.
-- El cutover (`scripts/cutover_legacy.py`) corre como `postgres`.
--
-- RLS no cambia: `tei_app` sigue sujeto a las políticas; `postgres` es el rol de
-- plataforma (mismo criterio que el resto del esquema sembrado por el CLI).
-- Idempotente: GRANT repetido es no-op.

grant select, insert, update, delete
  on table nucleo.pautas_mantenimiento,
           nucleo.mantenimientos,
           nucleo.liquidaciones,
           nucleo.anticipos_chofer,
           nucleo.ajustes_liquidacion,
           nucleo.configuracion_empresa
  to postgres;

grant select on table nucleo.v_mantenimiento_estado to postgres;

-- Secuencias (si alguna migración futura agrega seriales en estas tablas).
grant usage, select on all sequences in schema nucleo to postgres;
