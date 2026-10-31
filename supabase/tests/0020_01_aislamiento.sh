#!/usr/bin/env bash
# Runner de la prueba 0020-1 (aislamiento RLS de una sesión).
# - Crea el fixture de la empresa B + su cliente como supabase_admin (idempotente),
#   de modo que la prueba funciona sobre un `tei_test` recién clonado (solo trae
#   la empresa del seed).
# - Ejecuta el SQL como `tei_app` (la prueba aborta si el rol bypasea RLS).
set -euo pipefail

CONTAINER="${SUPABASE_DB_CONTAINER:-}"
if [ -z "$CONTAINER" ]; then
  CONTAINER=$(docker ps --format '{{.Names}}' | grep '^supabase_db_' | head -1)
fi
DB="${TEST_DB:-tei_test}"

echo "== fixture empresa B (supabase_admin, idempotente) =="
docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U supabase_admin -d "$DB" -v ON_ERROR_STOP=1 >/dev/null <<'SQL'
insert into nucleo.empresas (id, codigo, razon_social, rut)
values ('b0787fc9-ba4e-4005-9371-40cb7c0fbfa4', 'TEST-B', 'Empresa de pruebas (RLS)', '76000000-0')
on conflict do nothing;

insert into nucleo.clientes (id, empresa_id, razon_social, rut)
values ('49f2d33e-7791-4fcd-88be-cef5bd366a43',
        'b0787fc9-ba4e-4005-9371-40cb7c0fbfa4',
        'Cliente de pruebas B', '76000001-1')
on conflict do nothing;
SQL

echo "== prueba como tei_app =="
docker exec -i "$CONTAINER" psql -h 127.0.0.1 -U tei_app -d "$DB" -v ON_ERROR_STOP=1 \
  -f - < supabase/tests/0020_01_aislamiento.sql
