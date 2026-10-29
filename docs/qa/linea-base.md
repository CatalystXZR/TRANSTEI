# Línea base de la suite — ERP Transportes TEI

> **Pregunta que responde:** ¿qué pruebas existen, cuáles se ejecutaron y qué se puede afirmar hoy?
> **Dueño:** `qa` · **Verificado:** 2026-10-29 · **Método:** ejecución (`make unit`) + `lsof` + lectura
> **Caduca si:** cambia el `Makefile`, se agrega/borra un módulo de prueba o cambia el entorno local.
> **Re-verificar con:** §6 de este documento.

> Este archivo es un **corte fechado**, no un estado permanente. La cifra viva del
> sistema está en `docs/estado.md` §2. Una afirmación sin salida pegada es 🟡 o 🔴,
> nunca 🟢. Un `skip` no es un aprobado.

---

## 1. Entorno de esta sesión (2026-10-29)

| Elemento | Estado | Evidencia |
|---|---|---|
| Rama / árbol | `main` con trabajo sin commitear | `git status --short` (más de 50 entradas) |
| PostgreSQL `:54322` | 🔴 **no confirmado como Supabase local** | `lsof -nP -iTCP:54322 -sTCP:LISTEN` → `ssh 1789 pc … TCP *:54322 (LISTEN)`: es un **túnel SSH**, no el contenedor |
| Backend `:8000` | 🟡 listener presente (2 procesos Python) | `lsof -nP -iTCP:8000 -sTCP:LISTEN` |
| Frontend `:3000` | 🟡 listener presente (node) | `lsof -nP -iTCP:3000 -sTCP:LISTEN` |
| `NUCLEO_TEST_DATABASE_URL` | 🔴 **no definida** en esta sesión | `[ -n "$NUCLEO_TEST_DATABASE_URL" ]` → vacío |
| `DATABASE_URL` (backend) | 🔴 no verificada (no se lee `.env`) | — |
| Python | `.venv/bin/python` (3.13) | usado por `make unit` |
| Migraciones en disco | 19 (`0001`–`0019`) | `ls supabase/migrations \| wc -l` |

**Consecuencia directa:** con `:54322` apuntando a un túnel sin confirmar, **ninguna
prueba de integración puede declararse ejecutada contra Supabase local**. Todo lo que
requiera base queda 🔴 en este corte.

---

## 2. `make unit` — ejecutado

Comando exacto (desde la raíz del repo):

```bash
make unit
```

Salida real (cola):

```text
....................................................                     [100%]
=============================== warnings summary ===============================
../.venv/lib/python3.13/site-packages/starlette/testclient.py:37
  … DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated …
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
52 passed, 1 warning in 0.04s
```

`52 passed` es real de esta sesión. `make unit` selecciona **5 módulos**
(`Makefile:54-60`): `test_nucleo_tiempo.py` (11), `test_nucleo_politicas.py` (19),
`test_nucleo_schemas.py` (7), `test_nucleo_modelos.py` (6), `test_nucleo_tarifas.py` (9)
= 52. **`test_kpi_engine.py` (9 pruebas puras) no está en `make unit`**: no se ejecutó
en esta corrida.

---

## 3. Suite completa (`make test`) — 🔴 no ejecutada aquí

No se ejecutó por dos motivos: (a) `:54322` no está confirmado como Supabase local;
(b) `make test` depende de `db-up`, que arranca Colima/Supabase y escribe datos de
prueba (requiere autorización, `AGENTS.md` §10).

Qué la habilita:

1. Supabase local arriba en `127.0.0.1:54322` (`make db-up`) con las migraciones aplicadas.
2. `NUCLEO_TEST_DATABASE_URL` apuntando a esa base (la exporta `Makefile:65` por defecto).
3. `TEST_ADMIN_EMAIL/PASSWORD` y `TEST_CONTABILIDAD_EMAIL/PASSWORD` (el `Makefile:66-69`
   las exporta por defecto; `conftest.py:42-47` omite los flujos si faltan).
4. **`DATABASE_URL` definida**: `test_reglas_negocio.py:114-120` y el fixture `db`
   (`conftest.py:61-67`) usan `settings.DATABASE_URL`, **no** `NUCLEO_TEST_DATABASE_URL`
   (SEC-010 sigue abierto).

Evidencia heredada (no re-ejecutada aquí, nivel 🟡): el informe
`docs/qa/informes/2026-10-29-r01-r02-suite-verde.md:55-61` registra `97 passed in 3.11s`
con las 6 variables exportadas. No es un resultado de esta sesión.

---

## 4. E2E — 9 definidos, 0 ejecutados

| Dato | Valor | Comando |
|---|---|---|
| Escenarios definidos | **9** | `grep -cE "^\s*test\(" frontend/e2e/tei.spec.ts` → `9` |
| Ejecutados en esta sesión | **0** | no se corrió `make e2e` |
| Requisitos | frontend `:3000`, backend `:8000`, base con seed, navegador Playwright | `frontend/playwright.config.ts:11,22-27` |

Los 9 escenarios están en `frontend/e2e/tei.spec.ts:14,23,34,42,57,67,75,84,90`.
Dos de ellos tienen aserciones que **pueden pasar sin probar el flujo** (SEC-011):
`tei.spec.ts:48-54` (bloque `if` sobre el enlace "Abrir") y `:96-100`
(`/^(Congelada|Abierta)$/` acepta ambos estados). Un E2E verde no equivale a cobertura
hasta corregirlos.

---

## 5. Qué se puede afirmar hoy

| Afirmación | Evidencia | Nivel |
|---|---|---|
| Las 52 pruebas unitarias seleccionadas por `make unit` pasan | salida §2 | 🟢 |
| `make unit` ejecuta 5 módulos y deja fuera `test_kpi_engine.py` | `Makefile:54-60`; conteos por archivo | 🟢 |
| Existen 21 módulos `test_*.py` + `conftest.py` en `backend/tests/` (22 archivos) | `find backend/tests -maxdepth 1 -type f \| wc -l` → `22` | 🟢 |
| Hay 9 escenarios E2E escritos | `grep -c` → `9` | 🟢 |
| `backend/tests/test_reglas_negocio.py` existe (sin trackear en git) | `git ls-files --others backend/tests` | 🟢 |
| La suite completa está en verde | no ejecutada; requiere base | 🔴 |
| Los E2E pasan | 0 ejecutados | 🔴 |
| `127.0.0.1:54322` es el Supabase local | el listener es `ssh`, no Docker/Supabase | 🔴 |
| Las pruebas SQL de `supabase/tests/` pasan | escritas, **no ejecutadas** (`supabase/tests/README.md:4-7`) | 🔴 |
| La concurrencia real está probada | `supabase/tests/0015_02_concurrencia_rampla.py` usa 2 conexiones pero no se ejecutó | 🔴 |
| Backend y frontend responden | hay listeners, no se hizo request de salud | 🟡 |
| El informe del 2026-10-29 obtuvo 97 passed | `docs/qa/informes/2026-10-29-r01-r02-suite-verde.md:55-61` | 🟡 |

---

## 6. Protocolo para llenar esta línea base en cada sesión

1. **Registrar el entorno, no suponerlo:**
   `git status --short`, `git branch --show-current`,
   `lsof -nP -iTCP:54322 -sTCP:LISTEN` (¿`ssh` o `com.docker`/`postgres`?),
   `lsof -nP -iTCP:8000 -sTCP:LISTEN`, `lsof -nP -iTCP:3000 -sTCP:LISTEN`,
   `[ -n "$NUCLEO_TEST_DATABASE_URL" ] && echo definida` (sin imprimir el valor).
2. **Unitarias siempre:** `make unit`; pegar la línea `N passed` y la fecha.
3. **Contar, no recordar:** `grep -cE "^\s*test\(" frontend/e2e/tei.spec.ts`;
   `find backend/tests -maxdepth 1 -name 'test_*.py' | wc -l`.
4. **Si hay base confirmada:** `make test` y pegar `N passed / N failed / N skipped`.
   Contar los `skipped` como **no ejecutados**, nunca como aprobados.
5. **Si hay frontend + base + seed:** `make e2e` y pegar el resumen de Playwright.
   Adjuntar `trace`/`screenshot` de los fallos.
6. **Si algo no se pudo correr:** escribir 🔴 con el motivo exacto y qué lo habilitaría.
7. **Actualizar `docs/estado.md` §2** si el corte cambia una cifra viva; este archivo
   conserva el corte fechado.

---

## 7. Límites de este corte

- No se ejecutó integración, E2E, SQL de `supabase/tests/` ni pruebas de concurrencia.
- No se verificó el rol efectivo de la conexión ni el estado de RLS (RA-03).
- No se leyó `.env` ni se imprimieron credenciales.
- La cifra `52` corresponde a **esta** corrida; si se agrega una prueba unitaria, cambia.
