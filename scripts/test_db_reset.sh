#!/usr/bin/env bash
# Crea/refresca la base de test `tei_test` como copia de la base local de la app.
# - Idempotente; destructivo SOLO sobre tei_test (data ficticia, autorizado por el dueño).
# - Nunca toca la base de la app (`postgres`).
# - Requiere el stack Supabase local arriba (`make db-up`).
# - Usa el socket local del contenedor (trust) como supabase_admin, que es el superusuario
#   del cluster (el rol `postgres` no lo es: rolsuper=f, rolbypassrls=t).
set -euo pipefail

CONTAINER="${SUPABASE_DB_CONTAINER:-supabase_db_TRANSTEI}"
APP_DB="${APP_DB:-postgres}"
TEST_DB="${TEST_DB:-tei_test}"

echo "== [1/4] descartando ${TEST_DB} previa (solo la de test) =="
docker exec "$CONTAINER" psql -U supabase_admin -d template1 \
  -c "DROP DATABASE IF EXISTS ${TEST_DB} WITH (FORCE);" >/dev/null

echo "== [2/4] creando ${TEST_DB} =="
docker exec "$CONTAINER" createdb -U supabase_admin -T template0 "$TEST_DB"

echo "== [3/5] copiando esquema+datos desde ${APP_DB} (pg_dump | psql) =="
# --no-owner: evita fallos de propiedad; se conservan los GRANTs (roles son
# cluster-wide y ya existen), necesarios para tei_app en las tablas del agente.
docker exec "$CONTAINER" bash -c \
  "pg_dump -U supabase_admin -d ${APP_DB} --no-owner \
   | psql -U supabase_admin -d ${TEST_DB} -v ON_ERROR_STOP=1" >/dev/null

echo "== [4/4] permisos para el rol de la app (postgres) =="
docker exec "$CONTAINER" psql -U supabase_admin -d "$TEST_DB" -c "
ALTER SCHEMA public OWNER TO postgres;
ALTER SCHEMA nucleo OWNER TO postgres;
GRANT USAGE ON SCHEMA auth, storage, public, nucleo TO postgres;
GRANT SELECT ON ALL TABLES IN SCHEMA auth TO postgres;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA nucleo, public, auth TO postgres;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA nucleo, public TO postgres;
GRANT ALL ON ALL TABLES IN SCHEMA nucleo, public TO postgres;" >/dev/null

echo "== [5/5] RLS en el clon + credencial local del rol de app =="
# El clon ya trae el estado final (el dump copia policies, ACLs y datos). Estas
# re-aplicaciones son replay de la historia correctiva en ORDEN: con `0035` la
# tabla `nucleo.cutover_control` no existe en el dump, así que `0020` (que la
# referenciaba) solo resuelve si se recrea primero con `0014` y se vuelve a
# retirar con `0035`. Cadena completa: 0014 → 0020 → 0029 → 0033 → 0034 → 0035.
if [ -f supabase/migrations/0014_cutover.sql ]; then
  docker exec -i "$CONTAINER" psql -U supabase_admin -d "$TEST_DB" -v ON_ERROR_STOP=1 \
    < supabase/migrations/0014_cutover.sql >/dev/null
fi
if [ -f supabase/migrations/0020_rls_multiempresa.sql ]; then
  docker exec -i "$CONTAINER" psql -U supabase_admin -d "$TEST_DB" -v ON_ERROR_STOP=1 \
    < supabase/migrations/0020_rls_multiempresa.sql >/dev/null
fi
# SEC-039: 0020 re-concede escritura a `tei_app` sobre todas las tablas; 0029
# la vuelve a revocar sobre identidad/ACL/flag. Se re-aplica para que el clon
# de test refleje el esquema real de la app.
if [ -f supabase/migrations/0029_tei_admin_gate.sql ]; then
  docker exec -i "$CONTAINER" psql -U supabase_admin -d "$TEST_DB" -v ON_ERROR_STOP=1 \
    < supabase/migrations/0029_tei_admin_gate.sql >/dev/null
fi
# SEC-056/068 (0033): 0020 también re-concede UPDATE en el historial del chat y
# escritura en `tenant_suscripciones`. Se re-aplica para que el clon de test
# tenga los mismos privilegios que la base de la app.
if [ -f supabase/migrations/0033_privilegios_tei_app.sql ]; then
  docker exec -i "$CONTAINER" psql -U supabase_admin -d "$TEST_DB" -v ON_ERROR_STOP=1 \
    < supabase/migrations/0033_privilegios_tei_app.sql >/dev/null
fi
# SEC-066 residual: la función de módulos es de plataforma; el clon debe perder
# el EXECUTE que PostgreSQL concede a PUBLIC por defecto.
if [ -f supabase/migrations/0034_revoke_modulo_app.sql ]; then
  docker exec -i "$CONTAINER" psql -U supabase_admin -d "$TEST_DB" -v ON_ERROR_STOP=1 \
    < supabase/migrations/0034_revoke_modulo_app.sql >/dev/null
fi
# 0035: retiro de `cutover_control`; el replay termina con la tabla ausente,
# igual que en la base de la app.
if [ -f supabase/migrations/0035_retiro_cutover_control.sql ]; then
  docker exec -i "$CONTAINER" psql -U supabase_admin -d "$TEST_DB" -v ON_ERROR_STOP=1 \
    < supabase/migrations/0035_retiro_cutover_control.sql >/dev/null
fi
# Credencial local/CI documentada (tei_test es desechable; nunca datos reales).
docker exec "$CONTAINER" psql -U supabase_admin -d postgres \
  -c "ALTER ROLE tei_app PASSWORD 'tei_app';" >/dev/null 2>&1 || true

echo "== listo: ${TEST_DB} =="
docker exec "$CONTAINER" psql -U postgres -d "$TEST_DB" -tA -c \
  "select 'migraciones='||count(*) from supabase_migrations.schema_migrations; \
   select 'nucleo_tablas='||count(*) from pg_tables where schemaname='nucleo'; \
   select 'public_tablas='||count(*) from pg_tables where schemaname='public';"
