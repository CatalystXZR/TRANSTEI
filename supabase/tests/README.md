# Pruebas de garantía de base de datos — 0015 y 0016

> **Autor:** agente `datos` · **Fecha:** 2026-10-29
> **Estado:** escritas, **no ejecutadas** por este agente (contrato: `datos` no
> ejecuta SQL). 🔴 hasta que el orquestador/`qa` las corra y pegue la salida real.
>
> No hay base local levantada en esta sesión: **ningún resultado de este
> directorio es evidencia todavía**.

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
- **RLS / multiempresa.** No se prueba aislamiento por empresa (RA-03, INV-T01).
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
