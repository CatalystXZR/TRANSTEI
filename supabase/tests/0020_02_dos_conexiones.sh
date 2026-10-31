#!/usr/bin/env bash
# ============================================================================
# Prueba 0020-2 — DOS CONEXIONES REALES, dos empresas a la vez
# ============================================================================
# Demuestra INV-T01 en el escenario que importa: dos sesiones simultáneas,
# cada una con su propio contexto. No es "dos llamadas seguidas": ambas
# transacciones están abiertas al mismo tiempo (se verifica comparando los
# timestamps de inicio/fin de cada sesión).
#
# Qué se prueba
#   1. La sesión de A ve filas de A y CERO de otra empresa.
#   2. La sesión de B ve filas de B y CERO de otra empresa.
#   3. A no ve el cliente concreto de B; B no ve el de A.
#   4. A inserta un cliente SIN commitear y lo ve (1 fila). B, con su propia
#      conexión, no lo ve (0 filas): ni por RLS ni por aislamiento de
#      transacción.
#   5. Las dos ventanas se solapan en el tiempo (overlap > 0 s).
#
# Requisitos
#   · Migración 0020 aplicada y rol tei_app existente SIN contraseña (el script
#     entra por socket/host con trust en desarrollo).
#   · Fixture de la empresa B: `supabase/tests/0020_01_aislamiento.sh` lo crea
#     (empresa B + cliente). Empresas por defecto: A=TEI, B=empresa de pruebas.
#     Se pueden sobreescribir con TEI_EMPRESA_A / TEI_EMPRESA_B.
#   · psql disponible o un prefijo que lo envuelva (docker):
#       PSQL="docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1" \
#       ./supabase/tests/0020_02_dos_conexiones.sh
#     (La variable se usa con word splitting a propósito: es un prefijo.)
#
# No modifica datos: ambas sesiones hacen ROLLBACK.
# ============================================================================
set -uo pipefail

PSQL="${PSQL:-psql}"
DB="${TEI_DB:-tei_test}"
APP_USER="${TEI_APP_USER:-tei_app}"
EMPRESA_A="${TEI_EMPRESA_A:-11111111-1111-1111-1111-111111111111}"
EMPRESA_B="${TEI_EMPRESA_B:-b0787fc9-ba4e-4005-9371-40cb7c0fbfa4}"

# Prefijo con word splitting intencional (p. ej. "docker exec -i cont psql").
# shellcheck disable=SC2086
run_psql() { $PSQL -U "$APP_USER" -d "$DB" -qAt -v ON_ERROR_STOP=1 "$@"; }

TMPDIR_TEST="$(mktemp -d "${TMPDIR:-/tmp}/tei0020.XXXXXX")"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

fallo() {
  echo "FALLO 0020-2: $*" >&2
  echo "--- salida sesión A ---" >&2
  cat "$TMPDIR_TEST/a.out" 2>/dev/null >&2 || true
  echo "--- salida sesión B ---" >&2
  cat "$TMPDIR_TEST/b.out" 2>/dev/null >&2 || true
  exit 1
}

echo "0020-2: resolviendo fixtures con el rol de la aplicación (tei_app)"

CLIENTE_BASE_A="$(run_psql <<SQL | awk -F'|' '/^MARK/{print $2}'
begin;
select set_config('app.empresa_id', '$EMPRESA_A', true) is not null;
select 'MARK|' || id from nucleo.clientes order by razon_social limit 1;
rollback;
SQL
)"
CLIENTE_BASE_B="$(run_psql <<SQL | awk -F'|' '/^MARK/{print $2}'
begin;
select set_config('app.empresa_id', '$EMPRESA_B', true) is not null;
select 'MARK|' || id from nucleo.clientes order by razon_social limit 1;
rollback;
SQL
)"

[ -n "${CLIENTE_BASE_A:-}" ] || fallo "la empresa A ($EMPRESA_A) no tiene clientes visibles para tei_app"
[ -n "${CLIENTE_BASE_B:-}" ] || fallo "la empresa B ($EMPRESA_B) no tiene clientes visibles para tei_app"
echo "  cliente base de A: $CLIENTE_BASE_A"
echo "  cliente base de B: $CLIENTE_BASE_B"

CLIENTE_A="$(uuidgen | tr 'A-Z' 'a-z')"

# ---------------------------------------------------------------------------
# Sesión A: transacción abierta ~2 s, inserta un cliente sin commitear
# ---------------------------------------------------------------------------
cat > "$TMPDIR_TEST/a.sql" <<SQL
begin;
select set_config('app.empresa_id', '$EMPRESA_A', true) is not null;
select 'A|inicio|' || extract(epoch from clock_timestamp());
insert into nucleo.clientes (id, empresa_id, razon_social, rut)
values ('$CLIENTE_A', '$EMPRESA_A', 'Cliente rol A (0020)', 'TST20-A');
select 'A|clientes|' || count(*) from nucleo.clientes;
select 'A|ajenos|' || count(*) from nucleo.clientes where empresa_id <> '$EMPRESA_A';
select 'A|cliente_b_visible|' || count(*) from nucleo.clientes where id = '$CLIENTE_BASE_B';
select 'A|cliente_propio|' || count(*) from nucleo.clientes where id = '$CLIENTE_A';
select pg_sleep(2);
select 'A|clientes_tras_sleep|' || count(*) from nucleo.clientes;
select 'A|fin|' || extract(epoch from clock_timestamp());
rollback;
SQL

# ---------------------------------------------------------------------------
# Sesión B: arranca 0,4 s después (solape garantizado) y mira lo de A
# ---------------------------------------------------------------------------
cat > "$TMPDIR_TEST/b.sql" <<SQL
select pg_sleep(0.4);
begin;
select set_config('app.empresa_id', '$EMPRESA_B', true) is not null;
select 'B|inicio|' || extract(epoch from clock_timestamp());
select 'B|clientes|' || count(*) from nucleo.clientes;
select 'B|ajenos|' || count(*) from nucleo.clientes where empresa_id <> '$EMPRESA_B';
select 'B|cliente_a_visible|' || count(*) from nucleo.clientes where id = '$CLIENTE_BASE_A';
select 'B|cliente_de_a|' || count(*) from nucleo.clientes where id = '$CLIENTE_A';
select pg_sleep(2.5);
select 'B|clientes_tras_sleep|' || count(*) from nucleo.clientes;
select 'B|cliente_de_a_tras_commit_aparente|' || count(*) from nucleo.clientes where id = '$CLIENTE_A';
select 'B|fin|' || extract(epoch from clock_timestamp());
rollback;
SQL

# shellcheck disable=SC2086
$PSQL -U "$APP_USER" -d "$DB" -qAt -v ON_ERROR_STOP=1 -f - < "$TMPDIR_TEST/a.sql" > "$TMPDIR_TEST/a.out" 2>&1 &
PID_A=$!
# shellcheck disable=SC2086
$PSQL -U "$APP_USER" -d "$DB" -qAt -v ON_ERROR_STOP=1 -f - < "$TMPDIR_TEST/b.sql" > "$TMPDIR_TEST/b.out" 2>&1 &
PID_B=$!
wait $PID_A || fallo "la sesión A terminó con error (ver salida)"
wait $PID_B || fallo "la sesión B terminó con error (ver salida)"

echo "0020-2: salida de la sesión A"
grep -E '^A\|' "$TMPDIR_TEST/a.out" | sed 's/^/  /'
echo "0020-2: salida de la sesión B"
grep -E '^B\|' "$TMPDIR_TEST/b.out" | sed 's/^/  /'

valor() { awk -F'|' -v k="$2" -v s="$1" '$1==s && $2==k {print $3}' "$TMPDIR_TEST/$3.out"; }

A_CLIENTES="$(valor A clientes a)"
A_AJENOS="$(valor A ajenos a)"
A_CB="$(valor A cliente_b_visible a)"
A_CLI="$(valor A cliente_propio a)"
B_CLIENTES="$(valor B clientes b)"
B_AJENOS="$(valor B ajenos b)"
B_CA="$(valor B cliente_a_visible b)"
B_CLI="$(valor B cliente_de_a b)"
B_CLI2="$(valor B cliente_de_a_tras_commit_aparente b)"
A_INI="$(valor A inicio a)"; A_FIN="$(valor A fin a)"
B_INI="$(valor B inicio b)"; B_FIN="$(valor B fin b)"

[ -n "$A_CLIENTES" ] && [ "$A_CLIENTES" -gt 0 ] || fallo "A no ve clientes propios ($A_CLIENTES)"
[ -n "$B_CLIENTES" ] && [ "$B_CLIENTES" -gt 0 ] || fallo "B no ve clientes propios ($B_CLIENTES)"
[ "$A_AJENOS" = "0" ] || fallo "A ve $A_AJENOS clientes de otra empresa"
[ "$B_AJENOS" = "0" ] || fallo "B ve $B_AJENOS clientes de otra empresa"
[ "$A_CB" = "0" ] || fallo "A ve el cliente concreto de B"
[ "$B_CA" = "0" ] || fallo "B ve el cliente concreto de A"
[ "$A_CLI" = "1" ] || fallo "A no ve su propio cliente sin commitear ($A_CLI)"
[ "$B_CLI" = "0" ] || fallo "B ve el cliente sin commitear de A ($B_CLI)"
[ "$B_CLI2" = "0" ] || fallo "B ve el cliente de A después ($B_CLI2)"

OVERLAP="$(awk -v ai="$A_INI" -v af="$A_FIN" -v bi="$B_INI" -v bf="$B_FIN" \
  'BEGIN { s = (ai > bi ? ai : bi); e = (af < bf ? af : bf); printf "%.2f", e - s }')"
awk -v o="$OVERLAP" 'BEGIN { exit (o > 0 ? 0 : 1) }' \
  || fallo "las dos sesiones no estuvieron abiertas a la vez (solape ${OVERLAP}s)"

echo "  solape de las dos transacciones: ${OVERLAP}s"
echo "OK 0020-2: dos conexiones simultáneas, cada empresa aislada; A no ve B, B no ve A"
echo "0020_02_dos_conexiones: OK"
