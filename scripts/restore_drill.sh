#!/usr/bin/env bash
# ============================================================
# Drill de backup/restore local para TRANSTEI (P0-13)
# - pg_dump del contenedor Supabase local
# - restore en una base temporal
# - verificación de tablas y conteos
# - limpieza de la base temporal
# Uso: scripts/restore_drill.sh
# ============================================================
set -euo pipefail

CONTENEDOR="${SUPABASE_DB_CONTAINER:-supabase_db_TRANSTEI}"
DIR_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR_BACKUPS="${BACKUP_DIR:-$DIR_SCRIPT/../backups}"
BASE_TEMP="transtei_restore_drill"
ARCHIVO="$DIR_BACKUPS/transtei_drill_$(date +%Y%m%d_%H%M%S).sql"

mkdir -p "$DIR_BACKUPS"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTENEDOR"; then
  echo "ABORTADO: el contenedor $CONTENEDOR no está corriendo."
  exit 1
fi

echo "1/5 Backup → $ARCHIVO"
docker exec "$CONTENEDOR" pg_dump -U postgres -d postgres --no-owner --no-privileges \
  --schema=nucleo --schema=public --schema=auth > "$ARCHIVO"
echo "   $(du -h "$ARCHIVO" | cut -f1)"

echo "2/5 Creando base temporal $BASE_TEMP"
docker exec "$CONTENEDOR" psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -c "drop database if exists $BASE_TEMP" \
  -c "create database $BASE_TEMP"
docker exec "$CONTENEDOR" psql -U postgres -d "$BASE_TEMP" -v ON_ERROR_STOP=1 \
  -c "create extension if not exists btree_gist" \
  -c "create extension if not exists pgcrypto" >/dev/null

echo "3/5 Restaurando"
sed -e "/SET log_min_messages TO/d" -e "/^CREATE SCHEMA public;$/d" "$ARCHIVO" \
  | docker exec -i "$CONTENEDOR" psql -U postgres -d "$BASE_TEMP" -v ON_ERROR_STOP=1 >/dev/null

echo "4/5 Verificando tablas y conteos"
docker exec "$CONTENEDOR" psql -U postgres -d "$BASE_TEMP" -v ON_ERROR_STOP=1 <<'SQL'
select 'empresas' as tabla, count(*) from nucleo.empresas
union all select 'clientes', count(*) from nucleo.clientes
union all select 'viajes', count(*) from nucleo.viajes
union all select 'facturas', count(*) from nucleo.facturas_nucleo
union all select 'pagos', count(*) from nucleo.pagos_nucleo
union all select 'auditoria', count(*) from nucleo.auditoria
order by tabla;
select 'restore_ok' as resultado
where exists (select 1 from nucleo.viajes limit 1)
  and exists (select 1 from nucleo.auditoria limit 1);
SQL

echo "5/5 Eliminando base temporal"
docker exec "$CONTENEDOR" psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -c "drop database if exists $BASE_TEMP" >/dev/null

echo "Restore drill OK. Backup conservado en $ARCHIVO"
