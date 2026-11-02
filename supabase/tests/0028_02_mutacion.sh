#!/usr/bin/env bash
# ============================================================================
# Prueba de mutación 0028-2 — ¿la prueba 0028-1 prueba algo?
# ============================================================================
# `AGENTS.md` §7 y §8: una prueba de garantía debe **fallar** cuando se retira el
# mecanismo. Aquí el mecanismo es "public vacío", así que la mutación **recrea**
# un objeto del legacy y exige que `0028_01_retiro_public.sql` falle.
#
# Pasos:
#   1. `0028_01` sobre la base tal cual            ⇒ debe PASAR
#   2. se crea `public.mutacion_0028` (tabla) y
#      `public.handle_new_user()` (función)       ⇒ artefactos de mutación
#   3. `0028_01` con los artefactos                ⇒ debe FALLAR (relación)
#   4. se borra la tabla y queda **solo** la
#      función `public.handle_new_user()`         ⇒ mutación por función
#   5. `0028_01` solo con la función               ⇒ debe FALLAR (función)
#   6. se eliminan los artefactos y se repite      ⇒ debe PASAR
#
# No toca datos: crea y borra sus propios objetos. Idempotente.
#
# Uso:
#   ./supabase/tests/0028_02_mutacion.sh
# ============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTAINER="${SUPABASE_DB_CONTAINER:-supabase_db_TRANSTEI}"
PRUEBA="${REPO}/supabase/tests/0028_01_retiro_public.sql"

psql_super() {
  docker exec -i "$CONTAINER" psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1 "$@"
}

limpiar() {
  psql_super >/dev/null 2>&1 <<'SQL' || true
drop table if exists public.mutacion_0028 cascade;
drop function if exists public.handle_new_user();
SQL
}
trap limpiar EXIT

echo '== [1/6] 0028_01 sin mutación: debe pasar =='
if ! psql_super <"$PRUEBA" >/tmp/0028_mut_1.log 2>&1; then
  echo 'FALLO: 0028_01 no pasa ni siquiera sin mutación' >&2
  tail -20 /tmp/0028_mut_1.log >&2
  exit 1
fi
echo 'OK: 0028_01 pasa (base sin legacy)'

echo '== [2/6] creando artefactos de mutación en public =='
psql_super >/dev/null <<'SQL'
create table public.mutacion_0028 (id int primary key);
create function public.handle_new_user() returns trigger language plpgsql as $$
begin
  return new;
end;
$$;
SQL
echo 'OK: public.mutacion_0028 y public.handle_new_user() recreados'

echo '== [3/6] 0028_01 con la tabla mutada: debe fallar =='
set +e
psql_super <"$PRUEBA" >/tmp/0028_mut_2.log 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo 'FALLO DE MUTACIÓN: 0028_01 aprobó con el legacy recreado' >&2
  exit 1
fi
echo "OK: 0028_01 falló como debía (exit ${rc})"
grep -m3 -E 'FALLO 0028-1' /tmp/0028_mut_2.log || true

echo '== [4/6] dejando solo la función public.handle_new_user() =='
psql_super >/dev/null <<'SQL'
drop table public.mutacion_0028 cascade;
SQL
echo 'OK: mutación reducida a una función propia en public'

echo '== [5/6] 0028_01 con la función mutada: debe fallar =='
set +e
psql_super <"$PRUEBA" >/tmp/0028_mut_2b.log 2>&1
rc=$?
set -e
if [ "$rc" -eq 0 ]; then
  echo 'FALLO DE MUTACIÓN: 0028_01 aprobó con public.handle_new_user() recreada' >&2
  exit 1
fi
echo "OK: 0028_01 falló como debía (exit ${rc})"
grep -m3 -E 'FALLO 0028-1' /tmp/0028_mut_2b.log || true

echo '== [6/6] limpiando artefactos y repitiendo: debe pasar =='
limpiar
echo 'OK: artefactos eliminados'

if ! psql_super <"$PRUEBA" >/tmp/0028_mut_3.log 2>&1; then
  echo 'FALLO: 0028_01 no vuelve a pasar tras limpiar' >&2
  tail -20 /tmp/0028_mut_3.log >&2
  exit 1
fi
echo 'OK: 0028_01 pasa de nuevo'

echo '0028-2: OK (la prueba detecta el legacy recreado y se recupera)'
