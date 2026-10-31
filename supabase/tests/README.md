# Pruebas de garantía de base de datos — 0015, 0016 y 0020

> **Autor:** agente `datos` · **Fecha:** 2026-10-29 / 2026-10-30
> **Estado:** `0015`/`0016` escritas, **no ejecutadas** por este agente. Las de
> `0020` **sí se ejecutaron** el 2026-10-30 en el clon `tei_test`, con salida real
> en `docs/datos/rls-multiempresa.md` §7.
>
> Para `0015`/`0016` no hubo base levantada: 🔴 hasta que alguien las corra y
> pegue la salida. Para `0020` la evidencia existe, pero solo en el clon: en la
> base de la app el aislamiento sigue 🔴 porque el backend conecta como `postgres`.

## Qué prueba este directorio

| Archivo | Invariante | Tipo | Deja datos |
|---|---|---|---|
| `fixtures_0015_0016.sql` | — (prepara) | SQL | Sí (commitea, idempotente) |
| `0015_01_confirmado_ocupa.sql` | INV-D04: `confirmado` + 3 recursos ⇒ 3 reservas; `anulado` libera; parciales no ocupan | SQL, 1 sesión, `ROLLBACK` | No |
| `0015_02_concurrencia_rampla.py` | INV-D04 + `EXCLUDE`: dos conexiones, misma rampla ⇒ `23P01` | Python/psycopg, **2 conexiones** | Sí (viaje ganador; limpiar con `99_`) |
| `0015_03_confirmado_valida_documentos.sql` | INV-DOC04: `confirmado` + 3 recursos valida documentos | SQL, 1 sesión, `ROLLBACK` | No |
| `0016_01_licencia_clase_no_a5.sql` | INV-R02-01: clase ≠ A5 (incl. NULL) ⇒ `23514`, en INSERT y en UPDATE | SQL, 1 sesión, `ROLLBACK` | No |
| `0016_02_licencia_por_vencer_no_bloquea.sql` | INV-R02-03: licencia a 10 días **no** bloquea (es aviso) | SQL, 1 sesión, `ROLLBACK` | No |
| `0016_03_licencia_vencida_bloquea.sql` | INV-R02-02: licencia vencida ⇒ `23514` | SQL, 1 sesión, `ROLLBACK` | No |
| `99_limpieza_viajes_prueba.sql` | — (limpieza) | SQL | Borra datos de prueba |
| `mutacion.md` | Que las pruebas fallan sin el mecanismo | Procedimiento | — |
| `0020_01_aislamiento.sql` | INV-T01: sin contexto ⇒ 0 filas; cada empresa ve solo lo suyo; INSERT ajeno ⇒ 42501; el GUC no sobrevive al COMMIT | SQL, 1 sesión como `tei_app`, `ROLLBACK` | No |
| `0020_02_dos_conexiones.sh` | INV-T01 con **dos conexiones simultáneas**: A y B abiertas a la vez, sin verse; A inserta sin commitear y B no lo ve | bash + 2 `psql` en paralelo | No (`ROLLBACK`) |
| `0020_03_mutacion.sh` | Que la prueba de aislamiento falla si se retira el mecanismo (BYPASSRLS, `USING (true)`) | bash, restaura con `trap` | No |
| `0020_04_compatibilidad_postgres.sql` | La migración 0020 no rompe al rol actual (`postgres`/BYPASSRLS) | SQL, `ROLLBACK` | No |

Decisiones comunes:

- **Sin pgTAP.** No está instalado ni declarado en el repo; agregar una extensión
  es un cambio de infraestructura que excede este alcance. Las aserciones son
  bloques `DO` con `raise exception 'FALLO ...'`, y `psql -v ON_ERROR_STOP=1`
  convierte cualquier `FALLO` en código de salida ≠ 0. Es menos elegante y
  suficiente: la prueba falla cuando debe fallar.
- **Sin objetos auxiliares.** No se crean funciones, tablas ni esquemas de test;
  nada que limpiar ni que pueda quedar como dependencia.
- **UUID fijos** (`00000015-0000-4000-8000-0000000000NN`) para que las pruebas
  citen literales y no dependan de variables de `psql`.
- **Empresa aislada** `TST15`. Todo dato de prueba cuelga de ella; la limpieza
  borra solo esa empresa.

## Requisitos

- PostgreSQL local de Supabase arriba en `127.0.0.1:54322` (`make db-up`).
- Migraciones aplicadas hasta `0016`.
- `psql` en el `PATH`.
- Para `0015_02`: `psycopg` (el `.venv` del backend ya lo tiene).
- Rol superusuario (`postgres` local) para `99_limpieza` y para las mutaciones.

Variables de entorno (nunca se imprimen):

```bash
export NUCLEO_TEST_DATABASE_URL='postgresql://...@127.0.0.1:54322/postgres'
# o, si ya existe:
export DATABASE_URL='postgresql://...@127.0.0.1:54322/postgres'
```

`0015_02` usa `NUCLEO_TEST_DATABASE_URL` y cae a `DATABASE_URL`. Los `.sql` usan
la cadena que le pase `psql` explícitamente.

## Orden de ejecución

El orden importa: las fixtures crean la empresa y los maestros; las pruebas de
0016 asumen `dias_margen_documentos = 0` en `TST15`.

```bash
cd /ruta/al/repo

# 0. Migraciones ya aplicadas (no las aplica este directorio)
#    supabase/migrations/0015_*.sql  y  0016_*.sql

# 1. Fixtures (idempotente)
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/fixtures_0015_0016.sql

# 2. Ocupación
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0015_01_confirmado_ocupa.sql

# 3. Concurrencia real (dos conexiones). Commitea un viaje.
python supabase/tests/0015_02_concurrencia_rampla.py

# 4. Validación documental en 'confirmado'
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0015_03_confirmado_valida_documentos.sql

# 5. Licencia A5
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_01_licencia_clase_no_a5.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_02_licencia_por_vencer_no_bloquea.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/0016_03_licencia_vencida_bloquea.sql

# 6. Limpieza del viaje commiteado por el paso 3
PGOPTIONS="-c nucleo.test_cleanup=si" \
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
       -f supabase/tests/99_limpieza_viajes_prueba.sql
```

Salida esperada (resumen): cada `.sql` termina con
`<archivo>: OK` y código de salida 0; `0015_02` imprime tres líneas `OK 0015-2
paso N` y `0015_02_concurrencia_rampla: OK`.

## Pruebas de RLS multiempresa (0020)

Requieren la migración `supabase/migrations/0020_rls_multiempresa.sql` aplicada y
el rol `tei_app` (el rol es de clúster; la contraseña, si existe, es un secreto de
despliegue y **no** se escribe aquí). En local se entra por `127.0.0.1` con
`trust`. Donde no hay `psql` en el host, se usa el del contenedor como prefijo:

```bash
ADMIN="docker exec -i supabase_db_TRANSTEI psql -U supabase_admin"
APP="docker exec -i supabase_db_TRANSTEI psql -h 127.0.0.1"

# aplicar SOLO en una base desechable
$ADMIN -d tei_test -v ON_ERROR_STOP=1 \
  < supabase/migrations/0020_rls_multiempresa.sql

# 1) aislamiento en una sesión (rol tei_app; el runner crea el fixture de la empresa B)
bash supabase/tests/0020_01_aislamiento.sh

# 2) dos conexiones simultáneas
PSQL="$APP" ./supabase/tests/0020_02_dos_conexiones.sh

# 3) mutación (rompe el aislamiento a propósito y lo restaura)
PSQL_ADMIN="$ADMIN" PSQL="$APP" ./supabase/tests/0020_03_mutacion.sh

# 4) compatibilidad con el rol actual de la app
$APP -U postgres -d tei_test -v ON_ERROR_STOP=1 \
  < supabase/tests/0020_04_compatibilidad_postgres.sql
```

Empresas por defecto: A = `11111111-…-111111111111` (TEI), B =
`b0787fc9-ba4e-4005-9371-40cb7c0fbfa4`. Se sobreescriben con `TEI_EMPRESA_A` /
`TEI_EMPRESA_B`. Los viajes concretos se resuelven en tiempo de ejecución: las
pruebas **no** dependen de conteos fijos y sobreviven a un `reset` del clon.

## Pruebas del módulo agente WhatsApp (0021/0022)

Requieren `0021_agente_whatsapp.sql` y `0022_agente_whatsapp_endurecimiento.sql`
aplicadas en una base desechable. Roles: `0021_01`/`0021_02` con `postgres`
(BYPASSRLS), `0021_03` con `tei_app`, `0021_04`/rollbacks con `supabase_admin`.

| Archivo | Prueba | Tipo |
|---|---|---|
| `0021_01_smoke.sql` | 14 casos de constraints/triggers/funciones (C1–C14), con `ROLLBACK` | SQL, 1 sesión |
| `0021_02_concurrencia_id_comercial.py` | R-04 con 8 conexiones + barrera; D-10, webhook y folio con 2 conexiones | Python/psycopg |
| `0021_03_rls_tei_app.sql` | RLS+FORCE de las 8 tablas con el rol real `tei_app` | SQL, 1 sesión |
| `0021_04_mutacion.sql` | M1–M9: cada garantía se retira y la aserción debe romperse | SQL, `ROLLBACK` |
| `0022_99_rollback.sql` | Revierte D2/D3/D5/D9 y restaura la función de 0021 | SQL, `COMMIT` |
| `0021_99_rollback.sql` | Revierte 0021 completo (8 tablas, tipos, funciones, columna, índices) | SQL, `COMMIT` |

```bash
ADMIN="docker exec -i supabase_db_TRANSTEI psql -U supabase_admin"

# orden obligatorio: primero 0022, después 0021
$ADMIN -d tei_test -v ON_ERROR_STOP=1 < supabase/tests/0022_99_rollback.sql
$ADMIN -d tei_test -v ON_ERROR_STOP=1 < supabase/tests/0021_99_rollback.sql

# re-aplicar
$ADMIN -d tei_test -v ON_ERROR_STOP=1 < supabase/migrations/0021_agente_whatsapp.sql
$ADMIN -d tei_test -v ON_ERROR_STOP=1 < supabase/migrations/0022_agente_whatsapp_endurecimiento.sql
```

Salida real de este ciclo (4 suites verdes, 0 residuo) en
`docs/qa/informes/2026-10-31-o1.3-rollback-reaplicacion.md`. **Advertencia de
reproducibilidad:** re-aplicar `0021` como `supabase_admin` deja a `postgres`
solo con `SELECT` (hallazgo D10 del informe); `0021_01`/`0021_02` fallan con
`42501` hasta restaurar los `GRANT` de escritura que la migración no otorga.

## Cómo leer un fallo

| Mensaje | Qué significa |
|---|---|
| `FALLO 0015-1A: ... hay 0` | El trigger de reservas no está aplicado (¿0015 pendiente?) o `fn_viaje_reservas` es el de 0004 |
| `FALLO 0015-2: la sesión B NO quedó bloqueada` | No hay `EXCLUDE` efectivo sobre la rampla, o la sesión A no creó reservas |
| `FALLO 0015-2: se esperaba SQLSTATE 23P01, llegó ...` | El bloqueo ocurrió, pero por otra constraint/recurso: revise el nombre en el mensaje |
| `FALLO 0015-3A: ... fue ACEPTADO` | Falta `trg_viajes_05_documentos` (0015) |
| `FALLO 0016-1A/B/C` | Falta `trg_viajes_03_licencia_a5` (0016) |
| `FALLO 0016-2: se esperaba una licencia a 10 días, está a N` | Las fixtures se corrompieron o se corrió en otro día sin re-ejecutarlas: vuelva al paso 1 |
| `FALLO 0016-3: ... ACEPTADO` | Falta la validación documental (0015) o la licencia de la fixture no está vencida |
| `99_limpieza abortada: defina nucleo.test_cleanup='si'` | Falta el GUC de seguridad; es el comportamiento correcto |
| `99_limpieza abortada: ... ligados a facturas` | No borre a mano: revise si el viaje de prueba se facturó por error |

`FALLO` nunca significa "ajustar la prueba". Significa que la garantía no está.

## Lo que estas pruebas **no** cubren

- **Legacy `public`.** Nada de este directorio toca el legacy, y el legacy no
  escribe en `nucleo.reservas_recurso`: la disponibilidad sigue sin ser única
  entre esquemas (RA-02). La migración 0015 no cambia eso.
- **RLS / multiempresa.** Cubierto desde 2026-10-30 por `0020_01…04`, pero **solo
  en el clon `tei_test`**: en la base de la app el backend sigue conectando como
  `postgres` (BYPASSRLS) y el aislamiento es inerte (RA-03 / INV-T01).
  `0015`/`0016` no lo prueban.
- **Backfill sobre volumen real.** `fixtures` es mínimo. El backfill de 0015 se
  valida con las consultas V1/P1.x del encabezado de la migración sobre la base
  que corresponda, no aquí.
- **Concurrencia de tracto y chofer.** `0015_02` prueba solo rampla (una
  `EXCLUDE` por tipo; el patrón es el mismo, la prueba concreta es una).
- **Degradación de un chofer asignado** de A5 a otra clase: gap residual
  declarado en `0016-licencia-a5.md`.
- **Ventana de aviso de 14 días en el servicio**: es notificación de backend, no
  constraint; se prueba en `backend/tests`, no aquí.

## Mutación

Ver `mutacion.md`. Sin mutación, estas pruebas son una afirmación, no evidencia
de que prueban algo.
