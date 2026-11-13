-- ============================================================================
-- TRANSTEI — Migración 0035: retiro de `nucleo.cutover_control` (resto del cutover)
-- ============================================================================
-- OBJETIVO
--   Eliminar la tabla de control del cutover legacy. Con el retiro físico de
--   `public` (`0028`, 2026-11-01) y la eliminación del código de cutover del
--   backend, del frontend y de los scripts (2026-11-12, ver
--   `docs/orquestacion/registro.md`), la tabla ya no tiene consumidor:
--   `grep -rni "cutover" backend/app backend/tests frontend/src` devuelve 0
--   coincidencias. Queda `nucleo` como única fuente de verdad, con 50 tablas.
--
-- OBJETOS AFECTADOS
--   · `nucleo.cutover_control` (`0014_cutover.sql:8-31`): la tabla, su fila
--     única, el RLS enable, el grant a `service_role` (`0014:26`) y el COMMENT.
--   · Sus políticas `cutover_lectura` y `cutover_actualizacion`
--     (`0020_rls_multiempresa.sql:374-382`) y el revoke/grant a `tei_app`
--     (`0020:274-275`) caen al borrar la tabla (los ACLs y las policies viven
--     en la tabla misma).
--   · No toca ninguna otra tabla de `nucleo` ni
--     `supabase_migrations.schema_migrations`.
--
-- PRECONDICIONES (detección; abortan con error sin borrar nada)
--   1. La tabla existe; si ya fue retirada, la migración es idempotente y
--      termina sin acción.
--   2. Sin dependencias entrantes: ninguna vista/regla (`pg_depend` +
--      `pg_rewrite`) ni FK ajena (`pg_constraint.confrelid`) apunta a ella.
--   3. Contenido inesperado: ≤ 1 fila (diseño de fila única, `0014:18`). Si
--      hubiera más, aborta: reportar, no borrar.
--   4. 0 referencias en código de aplicación: verificadas por el orquestador
--      el 2026-11-12 (backend/app, backend/tests, frontend/src, scripts,
--      Makefile). El SQL no puede demostrarlo; la evidencia vive en el
--      registro de orquestación.
--
-- IMPACTO
--   · Datos: se descarta la fila de control del cutover (flag). El cutover ya
--     se ejecutó (Ola D, 2026-11-01); el registro queda en
--     `docs/_archivo/cutover-ejecutado-2026-11-01.md`.
--   · Locks: `DROP TABLE` toma ACCESS EXCLUSIVE sobre la tabla; tiene 0
--     consumidores de aplicación, no hay riesgo operativo.
--   · `nucleo` pasa de 51 a 50 tablas.
--
-- ROLLBACK
--   No automático: los datos del flag no son recuperables salvo backup. Para
--   revertir el esquema, recrear la tabla con el DDL de `0014_cutover.sql:8-31`
--   y volver a aplicar las policies de `0020_rls_multiempresa.sql:374-382`.
--   La simulación no destructiva está en
--   `supabase/tests/0035_99_rollback.sql` (transacción con ROLLBACK).
--
-- COMPATIBILIDAD (verificada 2026-11-12)
--   · Backend, frontend, scripts y Makefile: 0 referencias (grep en 0).
--   · `supabase/tests/0020_01_aislamiento.sql`: la aserción de 1 fila sobre
--     `cutover_control` se retiró en esta misma entrega; el resto de la prueba
--     de aislamiento RLS queda intacta.
--
-- PRUEBAS
--   · `supabase/tests/0035_01_retiro_cutover.sql` — la tabla no existe,
--     `nucleo` tiene 50 tablas y una tabla representativa sigue viva.
--   · `supabase/tests/0035_99_rollback.sql` — simula el rollback recreando la
--     tabla en una transacción con ROLLBACK y verificando que no deja rastro.
-- ============================================================================

begin;

do $$
declare
  v_existe boolean;
  v_deps   int;
  v_filas  int;
begin
  v_existe := to_regclass('nucleo.cutover_control') is not null;

  if not v_existe then
    raise notice 'OK 0035: nucleo.cutover_control no existe; nada que hacer (idempotente)';
    return;
  end if;

  -- Precondición 2a: ninguna vista/regla depende de la tabla.
  select count(*) into v_deps
    from pg_depend d
    join pg_rewrite r on r.oid = d.objid and d.classid = 'pg_rewrite'::regclass
    join pg_class c on c.oid = r.ev_class
   where d.refobjid = 'nucleo.cutover_control'::regclass
     and c.relname <> 'cutover_control';
  if v_deps <> 0 then
    raise exception 'FALLO 0035: % vista(s)/regla(s) dependen de nucleo.cutover_control', v_deps;
  end if;

  -- Precondición 2b: ninguna FK ajena apunta a la tabla.
  select count(*) into v_deps
    from pg_constraint
   where confrelid = 'nucleo.cutover_control'::regclass;
  if v_deps <> 0 then
    raise exception 'FALLO 0035: % FK(s) apuntan a nucleo.cutover_control', v_deps;
  end if;

  -- Precondición 3: contenido inesperado.
  select count(*) into v_filas from nucleo.cutover_control;
  if v_filas > 1 then
    raise exception 'FALLO 0035: cutover_control tiene % fila(s) (se esperaba ≤ 1); reportar, no borrar', v_filas;
  end if;

  drop table nucleo.cutover_control;
  raise notice 'OK 0035: nucleo.cutover_control retirada (% fila de control descartada)', v_filas;
end
$$;

commit;
