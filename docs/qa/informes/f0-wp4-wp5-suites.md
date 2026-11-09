> ⚠️ **Aviso de vigencia (2026-11-01):** cita archivos/cifras anteriores al retiro del legacy (`public`, `lib/api.ts`, `backend/app/api/routes/*`, `kpi_engine.py`). No citar como estado actual; ver `docs/estado.md` §2–§6 y `docs/PLAN_DESARROLLO.md`.

# F0 — WP-4/WP-5: Ejecución de suites y reproducibilidad

> Autor: `qa` · Fecha: 2026-10-29 · Método: ejecución real de las suites contra
> Supabase local, antes y después de `db-reset` autorizado (una sola vez).
> Niveles: 🟢 verificado (salida pegada) · 🟡 inferido · 🔴 no determinable.
> Ningún archivo de código, prueba ni migración fue modificado.

## 1. Entorno detectado (preflight)

| Elemento | Estado | Evidencia |
|---|---|---|
| Supabase local | 🟢 arriba, healthy | puertos 54322 (postgres) y 54321 (kong) abiertos (TCP); backend :8000 → HTTP 307; frontend :3000 → HTTP 307 |
| Migraciones aplicadas (pre-reset) | 🟢 **14/19** (0001–0014) | `supabase_migrations.schema_migrations` |
| Migraciones en disco | 🟢 19 | `ls supabase/migrations/` |
| `NUCLEO_TEST_DATABASE_URL` | 🟢 no definida en el shell | Python `os.environ` |
| `DATABASE_URL` | 🟢 no definida en el shell (vive en `backend/.env`, no leído) | Python `os.environ`; `backend/app/core/config.py:5-7,17` |
| `psql` en host | 🔴 no instalado | `which psql` → not found; se usó `docker exec supabase_db_TRANSTEI psql` |
| `supabase test db` | 🟡 existe (pg_prove) | `supabase test --help` |
| Rama / git | 🟢 `main`; solo `M docs/INDEX.md` y `?? docs/PLAN_DESARROLLO.md` ajenos | `git status --short` |

**Verificación de la afirmación del orquestador (archivo:línea):**

- `make test` exporta `NUCLEO_TEST_DATABASE_URL` con default de Makefile
  (`Makefile:6` `DB_URL_LOCAL`, `Makefile:62-70`) → `postgresql+psycopg://…@127.0.0.1:54322/postgres` (credencial seed-local documentada en `make help`).
- `conftest.py:61-67` fixture `db`: **usa `settings.DATABASE_URL`** (no `NUCLEO_TEST_DATABASE_URL`).
- `test_reglas_negocio.py:114-120` fixture `sesion_aislada`: **usa `settings.DATABASE_URL`**.
- `settings.DATABASE_URL` proviene de `backend/.env` (`app/core/config.py:5-7,17`).
- Prueba de que `settings.DATABASE_URL` apunta a la **misma base local** (no a una base separada): con un lock `ACCESS EXCLUSIVE` sobre `public.choferes` tomado en la base local, el test `test_r01_viaje_finalizado_no_facturado_no_genera_comision` tardó **7.77s** (bloqueado por el lock; suelto, ~0.4s) → 🟢 las pruebas de R-01/R-02 escriben en la base local de la app.

## 2. Hallazgo crítico previo al reset: deriva del ledger de migraciones

**La base pre-reset tenía objetos de las migraciones 0015–0019 aunque el ledger
solo registraba hasta 0014.** La premisa "0015–0019 NO aplicadas" es cierta para
la tabla `supabase_migrations.schema_migrations` pero **falsa para el catálogo**:

| Objeto probado (pre-reset) | Migración | Presente |
|---|---|---|
| `nucleo.fn_viaje_reservas()` con cuerpo "Regla 0015…" | 0015 | 🟢 sí |
| `trg_viajes_05_documentos` | 0015 | 🟢 sí |
| `nucleo.fn_viaje_documentos()` | 0015 | 🟢 sí |
| `trg_viajes_03_licencia_a5` | 0016 | 🟢 sí |
| default `nucleo.choferes.porcentaje_comision = 0.10` | 0017 | 🟢 sí |
| default `nucleo.empresas.dias_alerta_documentos = 14` | 0016 | 🟢 sí |
| choferes TEI con `porcentaje_comision = 0` | 0019 | 🟢 0 filas (backfill aplicado) |
| ledger `schema_migrations` | — | 🟢 solo 0001–0014 |

Por eso las pruebas SQL de 0015/0016 **pasaron contra la base "sin 0015/0016"**.
Causa no determinada (no se inventa): o los objetos se aplicaron fuera del
mecanismo `supabase db` o el ledger fue reiniciado. Consecuencia para WP-5: el
estado pre-reset era **no reproducible desde el repo** (un `db reset` de esa base
habría reaplicado 0015–0019 sobre objetos ya presentes).

## 3. FASE A — WP-4: ejecución contra la base actual (pre-reset, 20:00 local)

### 3.1 `make unit`

```
$ make unit
52 passed, 1 warning in 0.05s
```
🟢 52 passed / 0 failed / 0 skipped / 0 errores. 1 warning (DeprecationWarning
starlette testclient `anyio.abc.BlockingPortal`).

### 3.2 `make test`

```
$ make test
100 passed, 2 warnings in 3.46s
```
🟢 100 passed / 0 failed / **0 skipped** / 0 errores. Warnings: starlette +
`gotrue` deprecated (test_nucleo_facturacion). Distribución por archivo
(21 archivos, 100 tests): politicas 19 · reglas_negocio 14 · tiempo 11 ·
tarifas 9 · kpi_engine 9 · flujos_criticos 9 · schemas 7 · modelos 6 ·
permisos 2 · comercial 2 · bloqueos 2 · 11 archivos de integración con 1 c/u.

**Aislamiento (verificado):**

- La suite corre **contra la base de la app** (`127.0.0.1:54322/postgres`), tanto
  por `NUCLEO_TEST_DATABASE_URL` (default Makefile) como por `settings.DATABASE_URL`
  (`.env`). **No existe base de pruebas dedicada.**
- `test_reglas_negocio.py` revierte siempre (`join_transaction_mode="create_savepoint"`,
  `:105-136`): deja 0 filas en `public` (verificado: `public.viajes=1`, `facturas=0`).
- Los 13 archivos de integración (`test_nucleo_*`) **commitean y no limpian**:
  `test_nucleo_integracion.py:82,92,122,155,173,192,259` commitean;
  `:275-276` solo `engine.dispose()`. Residuo acumulado medido pre-reset:
  **393 empresas en `nucleo.empresas`** (prefijos por archivo: FAC 32, EXP 32,
  ALT 32, REN 32, GAS 32, POD 31, AUD 29, CON 29, CUT 29, BLQ 29, COM 29,
  MAE 28, TES 27), 471 viajes, 16 303 filas de auditoría.
- Las integraciones **no dependen de 0015–0019**: ninguna prueba del backend
  cubre las garantías DB de 0015/0016 (eso lo cubre solo `supabase/tests/`).

### 3.3 Pruebas SQL de `supabase/tests/` (README)

Ejecutadas con `docker exec -i supabase_db_TRANSTEI psql -U postgres -d postgres
-v ON_ERROR_STOP=1 -f -` (psql no existe en host; el README asume `psql` en PATH →
desviación de requisito). Concurrencia con `NUCLEO_TEST_DATABASE_URL` = cadena
seed-local del Makefile.

| Archivo | Resultado (pre-reset) |
|---|---|
| `fixtures_0015_0016.sql` | 🟢 OK (idempotente; TST15 ya existía) |
| `0015_01_confirmado_ocupa.sql` | 🟢 OK (1A, 1B, 1C) |
| `0015_02_concurrencia_rampla.py` | 🟢 OK — 2 conexiones reales, B bloqueada, `23P01 ex_reserva_rampla`, 1 reserva activa |
| `0015_03_confirmado_valida_documentos.sql` | 🟢 OK (3A, 3B) |
| `0016_01_licencia_clase_no_a5.sql` | 🟢 OK (1A, 1B, 1C — 23514 en INSERT y UPDATE) |
| `0016_02_licencia_por_vencer_no_bloquea.sql` | 🟢 OK |
| `0016_03_licencia_vencida_bloquea.sql` | 🟢 OK (+ control vigente) |
| `99_limpieza_viajes_prueba.sql` | 🟢 OK (borró 2 viajes/6 reservas de corridas previas) |

⚠️ **El paso 3.3 contradice la premisa del orquestador solo en apariencia**: las
pruebas pasan porque los objetos de 0015/0016 ya estaban en la base (hallazgo §2).
Sin el hallazgo §2, la lectura natural sería "0015 aplicada".

Desviaciones del README encontradas al ejecutar:
- **Rol superusuario:** el README dice `postgres` local; en esta base `postgres`
  es **NOSUPERUSER**; el superusuario real es `supabase_admin`. `99_limpieza`
  falla con `42501` usando `postgres` (`session_replication_role`).
- **PGOPTIONS no funciona:** `PGOPTIONS="-c nucleo.test_cleanup=si"` es ignorado
  (GUC no declarado en el servidor). Funciona `-c "set nucleo.test_cleanup='si'"`
  en la misma sesión, como documenta la variante del README (`99_limpieza:34-36`).
- **`supabase test db` (pg_prove) no sirve para estas pruebas:** ejecuta los
  `.sql` contra la base pero reporta "No subtests run" (no son pgTAP), y corre
  `99_limpieza` sin el GUC → ERROR "abortada". No es una puerta de pass/fail.

### 3.4 `make e2e` (Playwright, frontend :3000 corriendo)

```
9 passed (12.6s)
```
🟢 9/9 escenarios de `frontend/e2e/tei.spec.ts` (login/briefing, comercial,
despacho/disponibilidad, expediente/QR, cobranza/aging, auditoría, matriz de 8
roles, PWA conductor, cutover/runbook). Sin fallos ni screenshots.

### 3.5 FASE A — conclusión de aislamiento

- Los tests **no usan base separada**: todo cae sobre la base de la app.
- Los tests de integración **dejan datos residuales** que crecen en cada corrida
  (13 empresas + ~16 viajes + reservas/auditoría por `make test`).
- No se detectaron fallos atribuibles a migraciones ausentes en el backend:
  la suite pasa íntegra con la base "5 migraciones atrás" porque no prueba esas
  garantías.

## 4. FASE B — WP-5: reset autorizado (una vez) y re-ejecución

### 4.1 `make db-reset` (autorizado por el dueño; datos locales ficticios)

```
start: 2026-10-29 20:05:48 → end: 20:06:15 (27 s)
Applying migration 0007…0019 (todas)
no files matched pattern: supabase/seed.sql   ← benigno (no hay seed.sql)
Finished supabase db reset on branch main.
Seed local OK (usuarios, empresa_id del piloto)
```
🟢 19/19 migraciones aplicadas (`schema_migrations` = 19; tope 0019), seed sin
errores, 27 s. Post-reset: 1 empresa (TEI), 5 viajes, 8 reservas, auditoría 135.

### 4.2 Re-ejecución post-reset

| Comando | Resultado |
|---|---|
| `make test` | 🟢 **100 passed, 2 warnings, 3.24s** (idéntico a pre-reset) |
| `supabase/tests/*` (fixtures → 0015_01 → 0015_02 → 0015_03 → 0016_01/02/03 → 99) | 🟢 todos OK (mismas salidas; concurrencia OK con viaje `d23931fc…`; limpieza OK) |
| `make e2e` | 🟢 **9 passed (12.4s)** |

La suite es **reproducible sobre una base recién migrada + seed**: pre y post
reset dan los mismos resultados.

### 4.3 Flakiness y orden

- `make unit` ×2: 52/52 en 0.05s y 0.04s → estable.
- `test_reglas_negocio.py` ×2: **14 passed** en 0.74s y 0.77s → estable.
  (El docstring del archivo dice "11 passed" en `test_reglas_negocio.py:4-5`:
  **documentación obsoleta**, real = 14.)
- Datos acumulados: tras **un solo** `make test` post-reset quedan 13 empresas de
  prueba (ALT, AUD, BLQ, COM, CON, CUT, EXP, FAC, GAS, MAE, POD, REN, TES) +
  16 viajes de prueba + reservas/auditoría → **sin limpieza entre corridas**.
- Dependencia de orden: `supabase/tests` exige orden fixtures → pruebas →
  `99_limpieza` (documentado en su README; el concurrency deja datos
  commiteados a propósito). En backend no se observó dependencia de orden
  (UUIDs únicos por prueba).

## 5. Brechas de CI (`.github/workflows/ci.yml` — verificado)

| Pregunta | Respuesta | Evidencia |
|---|---|---|
| ¿Levanta PostgreSQL? | 🔴 **No** | job `backend` (`ci.yml:10-30`) no declara `services:` |
| ¿Aplica migraciones? | 🔴 **No** | solo `pip install`, import check y pytest (`ci.yml:23-30`) |
| ¿Corre integración/E2E? | 🔴 **No** | `python -m pytest` (`ci.yml:30`) con credenciales ausentes → las integraciones hacen `skip` (`conftest.py:45-47`, `test_reglas_negocio.py:114-118`, y los 12 `_url()` que omiten sin `NUCLEO_TEST_DATABASE_URL`); job `frontend` (`ci.yml:32-50`) solo `lint` + `build` |

Consecuencia 🟡 (inferida, no ejecutada en CI): en CI corren solo las unitarias
(52) y todo lo demás queda **skipped** — los skips de CI son "no ejecutado", no
aprobado. Nadie ejecuta `supabase/tests/` ni E2E en CI.

## 6. Tabla resumen

| Suite | Comando | Entorno | passed | failed | skipped | errores | Duración | Resultado |
|---|---|---|---|---|---|---|---|---|
| Unitaria | `make unit` | sin BD | 52 | 0 | 0 | 0 | 0.05s | 🟢 |
| Completa (pre-reset) | `make test` | Supabase local, ledger 0014, objetos 0015-19 | 100 | 0 | 0 | 0 | 3.46s | 🟢 |
| SQL 0015/0016 | psql vía docker exec | local | 6 archivos OK + concurrencia OK | 0 | 0 | 0 | ~2 min total | 🟢 |
| Concurrencia 0015_02 | python, 2 conexiones | local | OK (23P01) | 0 | 0 | 0 | ~2s | 🟢 |
| E2E (pre-reset) | `make e2e` | frontend :3000 + backend :8000 | 9 | 0 | 0 | 0 | 12.6s | 🟢 |
| Reset | `make db-reset` | autorizado, 1 vez | — | — | — | — | 27s | 🟢 19 migraciones + seed OK |
| Completa (post-reset) | `make test` | 19 migraciones | 100 | 0 | 0 | 0 | 3.24s | 🟢 |
| SQL 0015/0016 (post) | ídem | ídem | OK | 0 | 0 | 0 | — | 🟢 |
| E2E (post-reset) | `make e2e` | ídem | 9 | 0 | 0 | 0 | 12.4s | 🟢 |

## 7. Defectos / hallazgos reportados (no corregidos por QA)

1. **Deriva del ledger de migraciones (pre-reset)** — Severidad: alta para
   reproducibilidad. Ledger=0014 con objetos de 0015–0019 presentes (§2).
   Sugerido: `orquestador`/`datos` decidan si fue aplicación manual; no es
   corregible por QA.
2. **Tests sin base dedicada + sin limpieza** — `make test` escribe en la base de
   la app y acumula ~13 empresas y ~16 viajes por corrida
   (`test_nucleo_integracion.py:82-259` commitea; `:275-276` no borra).
   Sugerido: `backend`/`datos`.
3. **README `supabase/tests` desactualizado** — superusuario es `supabase_admin`
   (no `postgres`); `PGOPTIONS` no aplica el GUC. Sugerido: `datos`.
4. **`supabase test db` no es una puerta válida** para estas pruebas
   ("No subtests run"; corre `99_limpieza` sin GUC). Sugerido: `datos`/`orquestador`.
5. **Docstring obsoleto** `test_reglas_negocio.py:4-5` ("11 passed"; real 14).
   Sugerido: `qa` (futuro) — no se editó por alcance.
6. **CI sin PostgreSQL/migraciones/integración/E2E** (`ci.yml:30,45-50`) — la
   integración solo se valida en local y los skips de CI no son aprobados.
   Sugerido: `orquestador`.

## 8. Bloqueado / no cubierto

- 🔴 `psql` nativo: ausente; todo el SQL se ejecutó vía `docker exec` (resultados
  válidos, pero el README asume psql en PATH).
- 🔴 Mutación de las garantías 0015/0016: **no ejecutada** en esta misión
  (requiere retirar triggers/constraints en base desechable; fuera del alcance
  "solo ejecutar suites"). Queda como pendiente para la validación de
  `supabase/tests/mutacion.md`.
- 🔴 `make test` en CI: no ejecutado (no hay CI local); se infirió de `ci.yml`.

## 9. Verificaciones 🟢 / inferencias 🟡 / no determinable 🔴

- 🟢 Todo lo de las tablas §3/§4/§6 (salidas pegadas, comandos reales).
- 🟢 `settings.DATABASE_URL` → base local (prueba del lock, §1).
- 🟡 La causa de la deriva del ledger (§2) — el hecho está verificado; la causa no.
- 🟡 El comportamiento de CI (skips) — inferido del código, no ejecutado.
- 🔴 Mutaciones, psql nativo, CI real (ver §8).

## 10. Rollback / siguiente paso

Ningún artefacto quedó modificado (solo este informe). La base local quedó en el
estado post-reset autorizado: 19 migraciones, seed TEI, fixtures TST15 (maestros)
con viajes de prueba limpiados. Siguiente: `datos`/`orquestador` resuelven la
deriva del ledger (§7.1); `qa` puede retomar la mutación de 0015/0016 (§8).
