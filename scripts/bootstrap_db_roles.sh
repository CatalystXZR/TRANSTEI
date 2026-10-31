#!/usr/bin/env bash
# Crea/ajusta el rol de aplicación `tei_app` (cluster-level) como supabase_admin.
# Debe ejecutarse ANTES de aplicar migraciones en una base nueva: `supabase db
# reset` aplica como `postgres` (CREATEROLE, no superuser) y no puede fijar
# atributos como NOSUPERUSER.
# - Idempotente. Credencial local/CI documentada (igual que postgres:postgres).
# - Nunca se usa en staging/producción: allí el rol se crea por bootstrap seguro.
set -euo pipefail

CONTAINER="${SUPABASE_DB_CONTAINER:-}"
if [ -z "$CONTAINER" ]; then
  CONTAINER=$(docker ps --format '{{.Names}}' | grep '^supabase_db_' | head -1)
fi
if [ -z "$CONTAINER" ]; then
  echo "ERROR: no se encontró el contenedor supabase_db_* (¿está arriba el stack?)" >&2
  exit 1
fi

docker exec -i "$CONTAINER" psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1 <<'SQL'
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'tei_app') then
    create role tei_app;
  end if;
end
$$;
alter role tei_app with
  login
  noinherit
  nosuperuser
  nobypassrls
  nocreatedb
  nocreaterole
  noreplication
  connection limit -1;
SQL

# Credencial local/CI (tei_test es desechable; nunca datos reales).
docker exec "$CONTAINER" psql -U supabase_admin -d postgres \
  -c "ALTER ROLE tei_app PASSWORD 'tei_app';" >/dev/null

echo "rol tei_app listo (credencial local/CI)"
