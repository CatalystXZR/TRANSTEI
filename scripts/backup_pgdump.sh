#!/usr/bin/env bash
# ============================================================
# Backup manual de la base de datos TRANSTEI (PostgreSQL/Supabase)
# Verifica que el destino sea SIEMPRE el proyecto TRANSTEI.
# Requiere: pg_dump (cliente PostgreSQL) instalado.
# ============================================================
set -euo pipefail

REF_ESPERADO="luzxxhgozpqsxnwfookb"
REF_AJENO_REGEX="zawaevytpkvejhekyokw|issubzxwezcfwldzhjkc|mkxdiqfhlmmnmfqkdvhh"

DIR_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$DIR_SCRIPT/../backend/.env"
DIR_BACKUPS="${BACKUP_DIR:-$DIR_SCRIPT/../backups}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ABORTADO: no se encontró $ENV_FILE"
  exit 1
fi

DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)"
PG_URL="${DATABASE_URL/postgresql+psycopg:\/\//postgresql://}"

# --- Verificación de seguridad ---
if [[ "$PG_URL" != *"$REF_ESPERADO"* ]]; then
  echo "ABORTADO: el destino no es el proyecto TRANSTEI ($REF_ESPERADO)"
  exit 1
fi
if [[ "$PG_URL" =~ $REF_AJENO_REGEX ]]; then
  echo "ABORTADO: intento de backup a un proyecto ajeno"
  exit 1
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERROR: pg_dump no está instalado. Instale el cliente de PostgreSQL."
  exit 1
fi

mkdir -p "$DIR_BACKUPS"
ARCHIVO="$DIR_BACKUPS/transtei_$(date +%Y%m%d_%H%M%S).sql"

echo "Respaldando TRANSTEI ($REF_ESPERADO) → $ARCHIVO"
pg_dump "$PG_URL" --no-owner --no-privileges > "$ARCHIVO"

echo "Backup completado: $ARCHIVO ($(du -h "$ARCHIVO" | cut -f1))"
