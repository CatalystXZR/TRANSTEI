# F1 — Tests de backend aislados de la base de la aplicación

> Copia de trabajo en `docs/backend/informes/` (permiso de `backend`). El
> entregable oficial va en `docs/qa/informes/f1-tests-aislados.md` (permiso de
> `qa`); este contenido se entregó también en la respuesta final de la tarea.

Fecha: 2026-10-29 · Agente: `backend` · Objetivo: los tests de backend dejan de
leer/escribir la base de la app (`postgres`) y usan exclusivamente la base de
test dedicada (`tei_test`).

## Resultado

Los tests de backend ya no se conectan a la base de la aplicación. Tres cambios
en archivos de prueba + una guarda anti-misconfiguración. Criterios A–E
verificados con salidas reales (abajo). **Hallazgo de entorno crítico**: hoy
`backend/.env` define `NUCLEO_TEST_DATABASE_URL` apuntando a la propia base de la
app (`postgres`), no a `tei_test`; la guarda lo detecta y omite la integración
(RA-13). Corresponde al orquestador corregir `.env`.

## Cambio (archivo:línea)

### `backend/tests/conftest.py`
- `conftest.py:30` — `_APP_DATABASE_URL = getattr(settings, "DATABASE_URL")`:
  captura la URL de la app **antes** de redirigir; solo se usa para comparar
  (los tests jamás se conectan a ella).
- `conftest.py:36-37` — redirección: si `NUCLEO_TEST_DATABASE_URL` está
  definida, se asigna a `DATABASE_URL` del singleton `settings` antes de que
  `get_engine()` cree el motor (es lazy, `backend/app/core/database.py:10-24`).
  Así la app bajo `TestClient` (p. ej. `test_flujos_criticos.py`) escribe en la
  base de test, no en la de la app.
- `conftest.py:40-54` — `_base_url_test()`: skip si la variable falta
  («NUCLEO_TEST_DATABASE_URL no definida; integración omitida») o si apunta a
  la base de la app («…apunta a la base de la aplicación… (RA-13)»).
- `conftest.py:57-60` — fixture `base_url_test` (session).
- `conftest.py:63-67` — fixture `client` ahora depende de `base_url_test`:
  sin base de test válida, los flujos HTTP se omiten.
- `conftest.py:102-107` — fixture `db` usa `base_url_test` (antes
  `settings.DATABASE_URL`, la base de la app — defecto RA-13 original).

### `backend/tests/test_reglas_negocio.py`
- `test_reglas_negocio.py:104-118` — `sesion_aislada(base_url_test)` crea el
  motor desde la URL validada (antes `settings.DATABASE_URL`). El skip queda en
  el fixture de conftest con el mensaje nuevo.
- `test_reglas_negocio.py:62` — se elimina el import de `settings` (sin uso).

### `backend/tests/test_nucleo_integracion.py` (solo limpieza/teardown)
- `test_nucleo_integracion.py:52-59` — `_url()` delega en
  `conftest._base_url_test()` (misma guarda RA-13).
- `test_nucleo_integracion.py:60-75` — la prueba corre ahora dentro de una
  transacción que **siempre** se revierte (`conn.begin()` +
  `Session(bind=conn, join_transaction_mode="create_savepoint")`); el cuerpo
  (aserciones y `commit()` internos) queda **intacto**.
- `test_nucleo_integracion.py:286-292` — `finally`: rollback + cierre.
- Por qué rollback y no DELETE: el núcleo es inmutable por diseño.
  `trg_reservas_no_delete` (`supabase/migrations/0004_nucleo_operacional.sql:1859-1860`,
  `fn_reserva_no_borrar` en `:1692-1699`) **rechaza todo DELETE de
  `nucleo.reservas_recurso`** («Las reservas no se borran; se desactivan…»), y
  `fk_reserva_viaje … on delete restrict` (`:727-728`) + `trg_auditoria_no_update`
  (`:890-895`) hacen imposible borrar la cadena reserva→viaje→empresa. La
  reversión es la única limpieza posible sin violar los invariantes; es el
  mismo patrón que `sesion_aislada` en `test_reglas_negocio.py:126-133`.

## Criterios de aceptación — evidencia

### A. `grep -rn "settings.DATABASE_URL" backend/tests` → 0 coincidencias
```text
$ grep -rn "settings.DATABASE_URL" backend/tests/
(exit 1 = sin coincidencias)
```
🟢 Ningún test lee `settings.DATABASE_URL`. (La captura/redirección en conftest
usa `getattr`/`setattr` con comentario explícito, `conftest.py:24-37`.)

### B. `make unit` → 52 passed
```text
$ make unit
52 passed, 1 warning in 0.04s
```
🟢 Sin regresiones.

### C. Suite completa con `NUCLEO_TEST_DATABASE_URL=…/tei_test`
```text
$ cd backend && NUCLEO_TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:54322/tei_test" \
  TEST_ADMIN_EMAIL=admin@tei.local TEST_ADMIN_PASSWORD=TEI2026! \
  TEST_CONTABILIDAD_EMAIL=contador@tei.local TEST_CONTABILIDAD_PASSWORD=TEI2026! \
  ../.venv/bin/python -m pytest tests -p no:warnings --tb=short
100 passed in 3.41s   (segunda corrida idéntica: 100 passed in 3.25s)
```
🟢 100 passed, 0 failed, 0 skipped. Nota: sin las credenciales TEST_* (comando
literal del criterio, solo con la URL) el resultado es `92 passed, 8 skipped`
(los 8 flujos HTTP de `test_flujos_criticos.py` se omiten por credenciales,
igual que antes del cambio).

### D. Prueba de aislamiento (2 corridas, conteos antes/después)

`select count(*)` en `nucleo.empresas`, `nucleo.viajes`, residuo `TEST-%`
(empresas/viajes/reservas) y `public.kpis` «KPI Temporal Test»:

| Métrica | app (postgres) ANTES | app DESPUÉS | tei_test ANTES | tei_test DESPUÉS |
|---|---|---|---|---|
| empresas | 15 | 15 | 135 | 159 |
| viajes | 21 | 21 | 141 | 165 |
| TEST- empresas | 1 | 1 | 1 | 1 |
| TEST- viajes | 4 | 4 | 4 | 4 |
| TEST- reservas | 3 | 3 | 3 | 3 |
| kpis «KPI Temporal Test» | 3 | 3 | 5 | 7 |

```text
docker exec supabase_db_TRANSTEI psql -U postgres -d <postgres|tei_test> -tA -c "select count(*) from nucleo.empresas; …"
```

🟢 **La base de la app quedó EXACTAMENTE igual** (15/21/1/4/3/3 antes y
después). 🟢 **La suite no dejó residuo TEST- nuevo** en `tei_test` (1/4/3 →
1/4/3; el delta de empresas/viajes del núcleo en `tei_test` proviene de otros
archivos de test fuera del alcance, ver hallazgos).

### E. Variable sin definir → skip, no falla

E-1 (variable realmente ausente; CWD=raíz para que `backend/.env` no interfiera):
```text
$ env -u NUCLEO_TEST_DATABASE_URL PYTHONPATH=backend .venv/bin/python -m pytest \
  backend/tests/test_nucleo_integracion.py backend/tests/test_reglas_negocio.py -rs
15 skipped in 0.01s   (exit 0)
SKIPPED [1] backend/tests/conftest.py:48: NUCLEO_TEST_DATABASE_URL no definida; integración omitida
SKIPPED [1] backend/tests/test_reglas_negocio.py:474: NUCLEO_TEST_DATABASE_URL no definida; integración omitida
… (todas con el mensaje nuevo)
```

E-2 (variable ausente del entorno y `backend/.env` apuntando a la base de la app
— configuración inválida detectada por la guarda):
```text
$ env -u NUCLEO_TEST_DATABASE_URL … pytest tests/test_flujos_criticos.py tests/test_reglas_negocio.py tests/test_nucleo_integracion.py -rs
24 skipped in 0.01s   (exit 0)
SKIPPED [1] tests/conftest.py:50: NUCLEO_TEST_DATABASE_URL apunta a la base de la aplicación; integración omitida (RA-13)
```
🟢 En ambos casos: skipped, 0 failed.

## Estado final — qué lee cada test (archivo:línea)

| Archivo | Mecanismo de base | Línea |
|---|---|---|
| `conftest.py` (fixtures `client`, `db`, `base_url_test`) | `settings.NUCLEO_TEST_DATABASE_URL` validada ≠ base app | `conftest.py:36-37, 46, 105` |
| `test_reglas_negocio.py` (`sesion_aislada`) | fixture `base_url_test` | `test_reglas_negocio.py:118` |
| `test_nucleo_integracion.py` | `conftest._base_url_test()` | `test_nucleo_integracion.py:52-59` |
| Resto de `test_nucleo_*.py` | `os.environ.get("NUCLEO_TEST_DATABASE_URL") or settings.NUCLEO_TEST_DATABASE_URL` (ya era así; sin guarda RA-13) | p. ej. `test_nucleo_facturacion.py:54-56` |
| App bajo `TestClient` (`test_flujos_criticos.py`) | `settings.DATABASE_URL` **redirigido** a la base de test | `conftest.py:36-37` |

## Hallazgos

1. 🔴 **`backend/.env` está mal configurado**: `NUCLEO_TEST_DATABASE_URL`
   apunta a la base de la app (`postgres`), no a `tei_test` (verificado con
   `urlsplit(settings…).path` → `postgres` para ambas variables; no se imprimió
   la URL completa). Con esa configuración, correr `pytest` local sin pasar la
   variable por entorno ejecutaría integración contra la base de la app. La
   guarda de `conftest.py:40-54` protege los fixtures/`_url()` de los archivos
   de este cambio; los otros `test_nucleo_*.py` (fuera de alcance) conservan su
   `_url()` local sin guarda. **Acción para el orquestador**: corregir
   `backend/.env` (apuntar a `tei_test`) o dejar de definirla ahí (Makefile/CI
   la inyectan por entorno).
2. 🟡 **Residuo TEST- preexistente e inmutable**: `TEST-f246f6ad` (1 empresa,
   4 viajes, 3 reservas) existe en **ambas** bases desde corridas anteriores.
   No es borrable por DELETE (trigger de inmutabilidad de reservas, ver
   arriba). La suite ya no genera residuo nuevo. Limpiarlo en la base de la app
   requiere decisión autorizada del orquestador/`datos` (p. ej. reset local o
   intervención quirúrgica); en `tei_test`, `make test-db` no lo elimina porque
   el clon proviene de la app contaminada.
3. 🟡 **Otros archivos dejan residuo en `tei_test` con prefijos no-TEST-**
   (ALT-, COM-, FAC-, GAS-, …): `test_nucleo_*.py` crean empresas/viajes y no
   limpian; `tei_test.nucleo` creció +12 empresas/viajes por corrida completa.
   Estaba fuera del alcance de esta tarea (archivos no autorizados). La
   limpieza de fondo es `make test-db` (drop + re-clon).
4. 🟡 **`test_flujos_criticos.py` deja KPI soft-deleted** («KPI Temporal
   Test», `activo=false`) +1 por corrida en `tei_test.public.kpis`; fuera de
   alcance (archivo no autorizado). Además, **durante el diagnóstico de este
   trabajo** quedaron 2 filas «KPI Temporal Test» soft-deleted en la base de la
   app (creadas por corridas de prueba bajo el `.env` mal configurado, antes de
   añadir la guarda). No se borraron (prohibido sin autorización); el
   orquestador puede eliminarlas o resetear.
5. 🟡 Auth local respondió una vez HTTP 500 en `/auth/v1/token`
   («write: broken pipe» hacia PostgreSQL, log de `supabase_auth_TRANSTEI`):
   transitorio; al reintentar, la suite pasó. No relacionado con este cambio.
6. 🟡 Ruff: los 3 archivos conservan errores preexistentes (conftest F401/I001;
   reglas 34; integración 16); este cambio no añade ninguno (verificado:
   reglas 34→34, integración 16→16, conftest 2→2 con `noqa: B009/B010` en las
   líneas nuevas). CI de backend no ejecuta ruff hoy.

## Riesgo residual

- Si `backend/.env` no se corrige, los `test_nucleo_*.py` restantes (con
  `_url()` propio) siguen ejecutando contra `postgres` en corridas locales sin
  la variable de entorno. La protección está en la infraestructura de conftest;
  el resto requiere la corrección de `.env` (1 línea) o una fase F2 que delegue
  todos los `_url()` a la guarda.

## Rollback

`git checkout -- backend/tests/conftest.py backend/tests/test_reglas_negocio.py
backend/tests/test_nucleo_integracion.py` (no se tocó app, migraciones, Makefile
ni ci.yml). Sin efectos fuera de los 3 archivos de test.
