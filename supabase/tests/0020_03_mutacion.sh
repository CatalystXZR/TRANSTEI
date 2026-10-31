#!/usr/bin/env bash
# ============================================================================
# Prueba 0020-3 — MUTACIÓN: la prueba falla si se retira el mecanismo
# ============================================================================
# Una prueba que no falla al quitar la garantía no prueba nada (AGENTS.md §7,
# database-safety §5). Aquí se retira, de a una, cada pieza y se comprueba que
# el aislamiento se rompe:
#
#   M1  ALTER ROLE tei_app BYPASSRLS
#       ⇒ la sesión de A ve los viajes de B. Es el estado de hoy con `postgres`:
#         demuestra que el ROL es la pieza que hace que el RLS aplique.
#   M2  ALTER POLICY tenant_empresa ON nucleo.clientes USING (true)
#       ⇒ la sesión de A ve los clientes de B. Demuestra que la POLÍTICA es la
#         que filtra (no el GRANT ni el trigger).
#   M3  ALTER TABLE nucleo.clientes NO FORCE ROW LEVEL SECURITY
#       ⇒ NO cambia nada para tei_app (no es dueño). FORCE es defensa en
#         profundidad, no el mecanismo. Se comprueba para no vender humo.
#
# Al terminar restaura todo (trap EXIT), incluso si algo falla a mitad.
# Solo debe ejecutarse en una base DESECHABLE (tei_test): durante unos segundos
# el aislamiento está roto a propósito.
#
# Uso:
#   PSQL_ADMIN="docker exec -i supabase_db_TRANSTEI psql" \
#   PSQL="docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1" \
#   ./supabase/tests/0020_03_mutacion.sh
# ============================================================================
set -uo pipefail

PSQL="${PSQL:-psql}"                 # rol de aplicación (tei_app)
PSQL_ADMIN="${PSQL_ADMIN:-psql}"     # rol administrador (dueño del esquema)
DB="${TEI_DB:-tei_test}"
APP_USER="${TEI_APP_USER:-tei_app}"
EMPRESA_A="${TEI_EMPRESA_A:-11111111-1111-1111-1111-111111111111}"
EMPRESA_B="${TEI_EMPRESA_B:-b0787fc9-ba4e-4005-9371-40cb7c0fbfa4}"

# shellcheck disable=SC2086
admin() { $PSQL_ADMIN -d "$DB" -qAt -v ON_ERROR_STOP=1 "$@"; }
# shellcheck disable=SC2086
app()   { $PSQL -U "$APP_USER" -d "$DB" -qAt -v ON_ERROR_STOP=1 "$@"; }

# Consulta como tei_app con contexto de A: cuántos clientes de OTRA empresa ve.
app_clientes_ajenos() {
  app <<SQL
begin;
select set_config('app.empresa_id', '$EMPRESA_A', true) is not null;
select count(*) from nucleo.clientes where empresa_id <> '$EMPRESA_A';
rollback;
SQL
}
app_viajes_ajenos() {
  app <<SQL
begin;
select set_config('app.empresa_id', '$EMPRESA_A', true) is not null;
select count(*) from nucleo.viajes where empresa_id <> '$EMPRESA_A';
rollback;
SQL
}

RESTAURAR=0
restaurar() {
  if [ "$RESTAURAR" = "1" ]; then
    echo "0020-3: restaurando mecanismos..."
    admin <<'SQL' || echo "AVISO: falló la restauración de la política" >&2
begin;
alter policy tenant_empresa on nucleo.clientes
  using (empresa_id = nucleo.ctx_empresa())
  with check (empresa_id = nucleo.ctx_empresa());
alter table nucleo.clientes force row level security;
alter role tei_app nobypassrls;
commit;
SQL
    RESTAURAR=0
  fi
}
trap restaurar EXIT

fallo() {
  echo "FALLO 0020-3: $*" >&2
  exit 1
}

# --- Línea base: el aislamiento funciona -----------------------------------
BASE_CLI="$(app_clientes_ajenos | tail -1)"
BASE_VIA="$(app_viajes_ajenos | tail -1)"
[ "$BASE_CLI" = "0" ] || fallo "línea base rota: tei_app ve $BASE_CLI clientes ajenos (¿0020 aplicada?)"
[ "$BASE_VIA" = "0" ] || fallo "línea base rota: tei_app ve $BASE_VIA viajes ajenos"
echo "OK 0020-3 base: 0 filas ajenas con tei_app"

# --- M1: BYPASSRLS en el rol de la aplicación ------------------------------
RESTAURAR=1
admin -c "alter role tei_app bypassrls" >/dev/null
M1="$(app_viajes_ajenos | tail -1)"
[ "$M1" -gt 0 ] || fallo "M1: con BYPASSRLS el rol SIGUE sin ver viajes ajenos (la prueba no prueba nada)"
echo "OK 0020-3 M1: con tei_app BYPASSRLS se ven $M1 viajes ajenos ⇒ el ROL es el mecanismo"
admin -c "alter role tei_app nobypassrls" >/dev/null

# --- M2: política permisiva ------------------------------------------------
admin -c "alter policy tenant_empresa on nucleo.clientes using (true) with check (true)" >/dev/null
M2="$(app_clientes_ajenos | tail -1)"
[ "$M2" -gt 0 ] || fallo "M2: con USING(true) el rol no ve clientes ajenos (la prueba no prueba nada)"
echo "OK 0020-3 M2: con USING(true) se ven $M2 clientes ajenos ⇒ la POLÍTICA es el mecanismo"
admin -c "alter policy tenant_empresa on nucleo.clientes using (empresa_id = nucleo.ctx_empresa()) with check (empresa_id = nucleo.ctx_empresa())" >/dev/null

# --- M3: quitar FORCE (no debe cambiar nada para tei_app) ------------------
admin -c "alter table nucleo.clientes no force row level security" >/dev/null
M3="$(app_clientes_ajenos | tail -1)"
[ "$M3" = "0" ] || fallo "M3: sin FORCE tei_app ve $M3 clientes ajenos (inesperado: revisar dueño del esquema)"
echo "OK 0020-3 M3: sin FORCE tei_app sigue viendo 0 (FORCE no es el mecanismo para un rol no-dueño)"
admin -c "alter table nucleo.clientes force row level security" >/dev/null

# --- Restauración y verificación ------------------------------------------
restaurar

FIN_CLI="$(app_clientes_ajenos | tail -1)"
FIN_VIA="$(app_viajes_ajenos | tail -1)"
[ "$FIN_CLI" = "0" ] || fallo "tras restaurar, tei_app sigue viendo $FIN_CLI clientes ajenos"
[ "$FIN_VIA" = "0" ] || fallo "tras restaurar, tei_app sigue viendo $FIN_VIA viajes ajenos"
BYPASS="$(admin -tA -c "select rolbypassrls from pg_roles where rolname='tei_app'")"
[ "$BYPASS" = "f" ] || fallo "tei_app quedó con BYPASSRLS=$BYPASS: RESTAURAR A MANO"

echo "OK 0020-3 restaurado: 0 filas ajenas, tei_app.rolbypassrls=$BYPASS"
echo "0020_03_mutacion: OK"
