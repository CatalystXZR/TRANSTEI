# Informe QA — adversariales de la Ola 4 y regresiones de la revisión independiente

- **Fecha:** 2026-11-09
- **Rama:** `main`
- **HEAD:** `ed514cc` (`chore(ci): corrige el nombre del paso de migraciones`).
  Las correcciones de producción de la revisión independiente están **en el
  working tree, sin commit**; se verificaron con `git diff` y lectura directa
  (§3). El código de negocio probado es el del working tree.
- **Dueño:** `qa` · **Alcance:** solo pruebas (`backend/tests/**`) e informes
  (`docs/qa/**`). No se modificó código de producción ni migraciones.
- **Informe de la matriz:** [`docs/qa/matriz-trazabilidad.md`](../matriz-trazabilidad.md) §19.

---

## 1. Entorno (🟢 verificado)

| Elemento | Estado / evidencia |
|---|---|
| Base de test | `tei_test` en `127.0.0.1:54322`, PostgreSQL **17.11** |
| Migraciones aplicadas | **33** (`supabase_migrations.schema_migrations`, última `0033`) |
| Tablas en `nucleo` | **52** |
| Privilegios `tei_app` | `UPDATE/DELETE` sobre `agente_chat_mensajes` = **false**; `INSERT` sobre `tenant_suscripciones` = **false** |
| Backend | `:8000` responde `200 /health` |
| Frontend | `:3000` responde `200 /login` |
| Supabase Auth | login real de `admin@tei.local` y `gerente@tei.local` funciona |
| `NUCLEO_TEST_DATABASE_URL` | definida por `make test`: `postgres:postgres@.../tei_test` |
| `NUCLEO_DATABASE_URL` | definida por `make test`: `tei_app:tei_app@.../tei_test` (sin `BYPASSRLS`) |
| Python / libs | 3.13.16 · FastAPI 0.162.0 · SQLAlchemy 2.0.55 · SQLModel 0.0.24 · psycopg 3.2.6 |
| Seed | TEI y TES presentes; `admin@tei.local` solo tiene membresía TEI; `gerente@tei.local` es `gerente` en TEI |
| No disponible | No se usó DDL sobre `postgres`: el rol no es owner (`supabase_admin`). La mutación DDL real no se ejecutó (ver §8). |

> No se leyeron `.env` ni secretos. Los valores de login usados son los del
> `Makefile`/seed local documentado.

---

## 2. Línea base y resultado final

| Comando | Resultado | Nivel |
|---|---|---|
| `make unit` | **135 passed**, 2 warnings (0.70 s) | 🟢 ejecutado |
| `make test` (antes de las correcciones, 27 pruebas nuevas) | **495: 494 passed, 1 failed, 0 skipped** | 🟢 ejecutado (rojo por QA-O4-01) |
| `make test` (después de las correcciones, 36 pruebas nuevas) | **504 passed, 0 failed, 0 skipped** (10.89 s) | 🟢 ejecutado |
| `make e2e` | **20 passed** (24.9 s) | 🟢 ejecutado |
| Regresión del área (transiciones + chat HTTP + buzón + LLM) | **75 passed** (2.41 s) | 🟢 ejecutado |
| `ruff check` de los 5 archivos de prueba nuevos | **All checks passed** | 🟢 ejecutado |

No se agregó ningún `skip`/`xfail`. El helper `ola4_helpers.sesion_aislada`
conserva el `skip` heredado para el caso de que falte la migración 0004; **no
ocurrió** en esta corrida. La prueba que antes era roja
(`test_panel_configuracion_agente_esta_montado`) ahora pasa.

---

## 3. Correcciones de producción verificadas (lectura + `git diff`)

| ID | Verificación en el código actual | Evidencia |
|---|---|---|
| **SEC-069** | `backend/app/api/router.py:12-14` importa `api_configuracion` y `:35` lo incluye. `backend/app/nucleo/agente/chat/api_configuracion.py:145` define `_agente_out`, que faltaba y causaba `NameError` en la primera petición. | `git diff HEAD -- backend/app/api/router.py backend/app/nucleo/agente/chat/api_configuracion.py`; prueba verde `test_panel_configuracion_agente_esta_montado` |
| **SEC-066** | `backend/app/nucleo/agente/api_contactos.py:172-174`: se retiró `PUT /modulos/{id}` y su `ModuloIn`; queda solo el comentario de plataforma. | `git diff HEAD -- .../api_contactos.py`; prueba `test_sec_066_put_modulos_retirado_es_404` (404) |
| **SEC-064** | `backend/app/nucleo/agente/solicitudes.py:471-485`: `_ejecutar_accion_operativa` fusiona `valores` (o `solicitud.valores_modificados`) sobre `payload["datos"]` antes de ejecutar. | `git diff`; pruebas `test_sec_064_modificar_crear_viaje_usa_el_valor_corregido` y `test_sec_064_modificar_anular_viaje_usa_el_motivo_corregido` |
| **SEC-063** | `backend/app/nucleo/agente/chat/capacidades.py:185-187`: `configuracion.escribir_catalogo` tiene `por_defecto={"gerente": False}`. | `git diff`; prueba `test_sec_063_catalogo_nace_deshabilitado_y_no_escribe` |
| **SEC-065** | `backend/app/core/config.py:47-48` define los topes; `runtime.py:569-605` valida por respuesta (`>8`) y por turno (`>16`) antes de ejecutar. | `git diff`; 3 pruebas `test_sec_065_*` |
| **SEC-056/068** | `supabase/migrations/0033_privilegios_tei_app.sql:54-60` revoca `UPDATE/DELETE` del historial e `INSERT/UPDATE/DELETE` de `tenant_suscripciones`; `scripts/test_db_reset.sh:53-55` la re-aplica. `tei_test` la tiene aplicada (33 migraciones). | Consultas `has_table_privilege`; prueba `test_0033_tei_app_no_actualiza_historial_ni_escribe_suscripcion` (42501) |

---

## 4. Pruebas creadas / ajustadas

| Archivo:línea | Qué cubre |
|---|---|
| `backend/tests/test_ola4_transiciones_adversarial.py:49` | `cerrado → cobrado` rechazado (vía facturación), estado intacto |
| `:77` | `confirmado → anulado` por `/transicion` **con motivo** ⇒ 409 `via=anulacion`; no anula ni deja evento |
| `:119` (4 parámetros) | motivo de anulación de 3/4 chars, solo espacios y 1 char útil ⇒ 422 y reservas activas |
| `:156` | anular viaje de otra empresa ⇒ 404, sin liberar reservas |
| `:186` | despacho (sin `comercial:aprobar`) ⇒ 403, sin liberar reservas |
| `:272` | concurrencia real de transición: 2 conexiones esperan el mismo `FOR UPDATE`; una gana, una 409 |
| `:334` | doble anulación concurrente: una gana y libera 3 reservas una sola vez; la otra 409 |
| `backend/tests/test_ola4_concurrencia_reservas.py:48` | `EXCLUDE` real: dos INSERT solapados concurrentes ⇒ una fila + `23P01`; borde semiabierto 12:00 válido |
| `backend/tests/test_ola4_chat_capacidades.py:203` | SEC-052: override `whatsapp.recordatorio=true` sin módulo ⇒ `upsell` y **no ejecuta** |
| `:247` | capacidad `configuracion.escribir_reglas=false` ⇒ tool `error` y sin escritura |
| `:284` | fila que habilita `operacion.anular_viaje` a la secretaria no se concede (catálogo manda; `actualizar` la rechaza) |
| `:338` | **SEC-069**: `GET /nucleo/agente/configuracion` con admin responde 200 (antes 404) |
| `:356` | SEC-055/061: aprobar como admin una propuesta del chat sobre un viaje de otra empresa ⇒ 404 y rollback; solicitud pendiente |
| `:431` | idempotencia concurrente: dos POST simultáneos con la misma `clave_idempotencia` ⇒ un turno y **una** llamada al LLM |
| `:541` | **SEC-064**: `crear_viaje` + `modificar` (`valor_declarado` 100000→250000) + `confirmar` ⇒ el viaje usa 250000 |
| `:607` | **SEC-064**: `anular_viaje` + `modificar` del motivo + `confirmar` ⇒ usa el motivo corregido (viaje y evento) |
| `:676` | **SEC-065**: respuesta con 9 `tool_call` (>8) ⇒ 502 estable, ninguna tool ejecutada, turno revertido |
| `:716` | **SEC-065**: 8 `tool_call` (≤8) sigue funcionando; 8 filas escritas |
| `:747` | **SEC-065**: 8+8+1 (17 >16) ⇒ 502 y rollback de las tools ya ejecutadas |
| `:787` | **SEC-063**: `configuracion.escribir_catalogo` con `por_defecto=false` y `habilitada=false`; la tool no escribe `iva_porcentaje` |
| `:833` | **SEC-066**: `PUT /nucleo/agente/modulos/agente-whatsapp` con admin ⇒ 404 |
| `:852` | **SEC-069**: `gerente` (sin `agente:configurar`) ⇒ 403 `ACCESO_DENEGADO` |
| `:869` | **0033**: con `tei_app`, UPDATE del historial e INSERT de suscripción ⇒ `42501` |
| `backend/tests/test_ola4_aislamiento_http.py:45` | JWT TEI + `X-Empresa-ID` TES ⇒ 403 en `GET /agente/chat/agentes` |
| `:54` | idem en `POST /agente/chat`; no persiste mensaje en TES |
| `:87` (2 parámetros) | idem en transición y anulación |
| `:97` | idem en `GET /agente/solicitudes` |
| `:110` | `empresa_id` en body del chat ⇒ 422 (`loc=empresa_id`), sin llamar al LLM |
| `:148` | `empresa_id` en body de transición ⇒ 422 |
| `:172` (3 parámetros) | sin `X-Empresa-ID` ⇒ 422, no hay empresa por defecto |
| `backend/tests/ola4_helpers.py` | constructores y sesiones compartidas (no es archivo de pruebas) |

**Total:** 36 pruebas nuevas, **36 verdes**. Las 27 de la primera entrega se
mantienen; se agregaron 9 regresiones de la revisión independiente.

---

## 5. Resultado por área

### 5.1 Transiciones y anulación (🟢)

| Caso | Esperado | Actual | Estado |
|---|---|---|---|
| `cerrado → cobrado` | 409 `via=facturacion`, estado `cerrado` | 409 `via=facturacion`, estado `cerrado` | 🟢 |
| `confirmado → anulado` con motivo por `/transicion` | 409 `via=anulacion`, sin evento `anulado` | 409 `via=anulacion`, sin evento | 🟢 |
| motivo `abc` / `abcd` / `"     "` / `"    x"` | 422, reservas activas | 422, reservas activas | 🟢 (4/4) |
| anular viaje de otra empresa | 404, sin cambios | 404, sin cambios | 🟢 |
| anular como despacho | 403, sin liberar | 403, reservas activas | 🟢 |
| transición concurrente | 1 éxito + 1 × 409 | 1 `asignado` + 1 `EstadoViajeInvalido` | 🟢 |
| doble anulación concurrente | 1 éxito + 1 × 409; 3 reservas liberadas una vez | 1 `anulado` + 3 liberadas + 1 × 409 | 🟢 |

### 5.2 Chat, capacidades y muro de pago (🟢)

| Caso | Esperado | Actual | Estado |
|---|---|---|---|
| Tool premium con override `true` y módulo inactivo | `estado=upsell`, `activo=false`, sin “preparado” | Igual | 🟢 |
| Capacidad deshabilitada por fila | Tool `error`, 0 filas de configuración | Igual | 🟢 |
| Fila gerente para secretaria | No aparece en `habilitadas`; `actualizar` rechaza | Igual (`no aplica`) | 🟢 |
| Idempotencia concurrente | 2 × 200, mismo `mensaje_id`, 1 llamada LLM | Igual | 🟢 |
| Aprobación chat de viaje ajeno | 404, rollback, solicitud pendiente | Igual | 🟢 |
| SEC-063 catálogo fiscal | `por_defecto=false`, `habilitada=false`; tool no escribe | Igual | 🟢 |
| SEC-064 crear viaje corregido | valor modificado 250000 | 250000 | 🟢 |
| SEC-064 anular con motivo corregido | motivo corregido en viaje y evento | Igual | 🟢 |
| SEC-065 tope por respuesta | 502, 0 tools, turno revertido | Igual | 🟢 |
| SEC-065 bajo el tope | 8 tools `ok` y 8 filas | Igual | 🟢 |
| SEC-065 tope por turno | 502 y rollback de lo ejecutado | Igual | 🟢 |
| SEC-069 panel admin | 200 | **200** | 🟢 |
| SEC-069 gerente | 403 | 403 | 🟢 |
| SEC-066 módulos retirado | 404 | 404 | 🟢 |
| 0033 privilegios `tei_app` | 42501 en UPDATE/INSERT | 42501 | 🟢 |

### 5.3 Aislamiento multiempresa (🟢)

Todas las rutas nuevas probadas con **JWT real de TEI** y `X-Empresa-ID` de TES
responden **403 `ACCESO_DENEGADO`** (no 200, no 404 con datos): `GET /agente/chat/agentes`,
`POST /agente/chat`, `POST /viajes/{id}/transicion`, `POST /viajes/{id}/anular`,
`GET /agente/solicitudes`. `empresa_id` en el body es **rechazado con 422**
(`extra="forbid"`), más estricto que “ignorarlo”: no hay segunda fuente de
verdad. Sin `X-Empresa-ID` la respuesta es 422 (header obligatorio).

### 5.4 Concurrencia real (🟢)

- **Reservas:** dos conexiones psycopg, INSERT solapados; A confirma y B recibe
  `SQLSTATE 23P01`; exactamente una reserva activa. Borde `[inicio, fin)`:
  12:00–16:00 convive con 08:00–12:00; 15:00–17:00 se rechaza. Evidencia: 1 passed.
- **Transición:** dos sesiones bloqueadas simultáneamente en `pg_stat_activity`
  (`wait_event_type='Lock'`); se libera el lock y gana una sola. Evidencia: 1 passed.
- **Anulación:** mismo patrón; una gana, libera 3 reservas y deja un evento; la
  otra recibe 409. Evidencia: 1 passed.
- **Chat:** dos POST HTTP simultáneos con la misma clave; un solo turno `user`,
  un solo `assistant`, una sola llamada al LLM. Evidencia: 1 passed.

### 5.5 Cambio E2E `0cf1be6` (🟢, sin debilitamiento)

El commit adapta el menú a **18 ítems** y filtra la factura del seed:

- `frontend/src/lib/navigation.ts:38-87` tiene **18 ítems para `admin`** (el
  nuevo `/agente/chat` en `:43`); el test agrega `/agente/chat` a
  `PANTALLAS_NUCLEO` y exige los 18, además de comprobar que las 9 rutas
  retiradas no aparezcan. Es **más estricto**, no más laxo.
- La factura se filtra por número (`frontend/e2e/tei.spec.ts:149-154`). El
  endpoint aplica `q` en servidor (`backend/app/nucleo/api_facturacion.py:64-74`);
  la base de la app tiene **133 facturas** y el listado por defecto trae 100, así
  que el filtro es necesario para que la aserción siga siendo real. No se cambió
  el `expect` de visibilidad.
- Ejecución: 3/3 del subconjunto (`cobranza`, menú TEI, menú TES) y **20/20** de
  `make e2e`.
- **Cobertura que sigue faltando:** `/configuracion/agentes` no se visita en E2E.
  Ahora el backend responde, pero el flujo de UI del panel sigue sin escenario.

---

## 6. Reproducción (comandos exactos)

Desde la raíz del repo, con la base local arriba:

```bash
# Unitarias (sin base)
make unit

# Suite completa contra tei_test (incluye las pruebas nuevas)
make test

# E2E (frontend :3000 y backend :8000 arriba, seed cargado)
make e2e

# Subconjunto nuevo (mismo entorno que `make test`)
cd backend
NUCLEO_TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:54322/tei_test" \
NUCLEO_DATABASE_URL="postgresql+psycopg://tei_app:tei_app@127.0.0.1:54322/tei_test" \
TEST_ADMIN_EMAIL="admin@tei.local" TEST_ADMIN_PASSWORD='TEI2026!' \
TEST_CONTABILIDAD_EMAIL="contador@tei.local" TEST_CONTABILIDAD_PASSWORD='TEI2026!' \
../.venv/bin/python -m pytest \
  tests/test_ola4_transiciones_adversarial.py \
  tests/test_ola4_concurrencia_reservas.py \
  tests/test_ola4_chat_capacidades.py \
  tests/test_ola4_aislamiento_http.py -q

# Lint de los archivos de prueba nuevos
../.venv/bin/ruff check \
  tests/ola4_helpers.py tests/test_ola4_transiciones_adversarial.py \
  tests/test_ola4_concurrencia_reservas.py tests/test_ola4_aislamiento_http.py \
  tests/test_ola4_chat_capacidades.py
```

---

## 7. Salida real (extractos)

### `make unit`

```text
135 passed, 2 warnings in 0.70s
```

### `make test` (después de las correcciones)

```text
........................................................................ [ 14%]
........................................................................ [ 28%]
........................................................................ [ 42%]
........................................................................ [ 57%]
........................................................................ [ 71%]
........................................................................ [ 85%]
........................................................................ [100%]
504 passed, 2 warnings in 10.89s
```

Antes de las correcciones, la misma suite daba `495: 494 passed, 1 failed`
(la prueba roja de QA-O4-01). El rojo se conservó como evidencia hasta que
`backend` montó el router; ahora **504/504 verdes**.

### `make e2e`

```text
Running 20 tests using 1 worker
...
20 passed (24.9s)
```

### Subconjunto nuevo (36 pruebas)

```text
36 passed, 1 warning in 1.65s
```

### `ruff check` de las pruebas nuevas

```text
All checks passed!
```

### Regresión del área

```text
75 passed, 1 warning in 2.41s
```

---

## 8. Sanidad (mutación)

No se editó código de producción. Se hicieron cuatro mutaciones controladas:

| # | Garantía | Mutación | Resultado | Conclusión |
|---|---|---|---|---|
| A | `EXCLUDE` de reservas | Copia temporal `CREATE TEMP TABLE ... (LIKE nucleo.reservas_recurso INCLUDING ALL)`; se eliminaron sus 3 constraints `EXCLUDE` (la tabla temporal sí es propiedad de `postgres`) y se insertaron dos ventanas solapadas. | **2 filas aceptadas** (sin la constraint) | La prueba de concurrencia depende realmente del `EXCLUDE`; sin él, el solape convive. |
| B | Idempotencia del chat | Copia temporal de `agente_chat_mensajes`; se eliminó su índice único de idempotencia y se insertaron dos filas con la misma `clave_idempotencia`. | **2 filas con la misma clave** | La garantía depende de `uq_agente_chat_msg_idempotencia`; sin el índice se duplica. |
| C | Guard `anulado` del servicio | En memoria, se reemplazó `servicio_transiciones.EstadoViaje` por un objeto falso para que la comparación `destino == EstadoViaje.anulado` no disparara; se llamó `transicionar(confirmado → anulado)` con motivo. | El trigger **`fn_viaje_transicion`** rechazó: “La transición confirmado -> anulado requiere motivo” (23514) | El guard del servicio es defensa en profundidad; la base también frena. Sin el guard, la prueba fallaría porque la respuesta ya no es el 409 `via=anulacion` esperado. |
| D | Guard `facturado` del servicio | En memoria, `ESTADOS_SOLO_FACTURACION = frozenset()`; se llamó `transicionar(cerrado → facturado)`. | El trigger **`fn_viaje_facturacion`** rechazó (`ReglaNegocioViolada`) | Igual: la base es el árbitro final; el guard del servicio da el error de dominio correcto. |

**Limitación declarada:** las mutaciones A/B se hicieron sobre copias temporales
porque `postgres` no es owner de las tablas reales (`supabase_admin`) y no se
autorizó DDL sobre ellas. Aun así, demuestran que la aserción de la prueba
(una sola fila / una sola clave) depende del mecanismo retirado.

---

## 9. Defectos detectados

### QA-O4-01 — Router del panel de capacidades ausente (✅ corregido)

- **Estado:** **corregido en el working tree** por `backend`; verificado en §3.
- **Verificación:** `backend/app/api/router.py:12-14,35` importa e incluye
  `api_configuracion`; `api_configuracion.py:145` agrega el `_agente_out` que
  faltaba. `GET /nucleo/agente/configuracion` con admin responde **200** y la
  prueba `test_panel_configuracion_agente_esta_montado` (línea 338) pasa.
- **Regresión adicional:** `gerente` sin `agente:configurar` recibe **403**
  (`test_sec_069_gerente_sin_agente_configurar_es_403`).
- **Pendiente de cobertura:** el E2E de `/configuracion/agentes` sigue sin
  escenario; el backend ya responde, pero el flujo de UI no está ejercitado.

No se detectaron defectos nuevos en esta continuación. Las regresiones de
SEC-063/064/065/066/069/0033 pasan con el código actual.

---

## 10. Cobertura faltante (deuda explícita)

| Tema | Por qué no se cubrió | Nivel |
|---|---|---|
| `facturado → cobrado` desde un viaje realmente `facturado` | Crear un viaje `facturado` exige factura/POD/OC; se probó `cerrado → cobrado` (que ya ejercita el filtro `ESTADOS_SOLO_FACTURACION`). El trigger `fn_viaje_facturacion` bloquea el UPDATE directo (mutación D). | 🟡 |
| `EXCLUDE` de **rampla** y **chofer** | Se probó tracto (misma definición y mecanismo). Las tres constraints son análogas, pero no se ejecutaron las otras dos. | 🟡 |
| RLS de `agente_chat_*` y `agente_capacidades` con `tei_app` en dos conexiones | La suite SQL `supabase/tests/0031_02_rls_tei_app.sql` existe, pero no se ejecutó en esta sesión (no es parte de `make test`). La prueba 0033 sí valida los **privilegios** de `tei_app` (42501), no la RLS fila a fila. | 🔴 no ejecutado |
| Panel `/configuracion/agentes` en E2E | No hay escenario que lo visite; el backend ya responde 200/403. | 🔴 sin cobertura E2E |
| `motivo` mínimo en la base | El mínimo de 5 caracteres vive en el schema Pydantic; la DB solo exige `motivo_anulacion` no nulo. Un llamador interno que evitara el schema podría guardar un motivo de 1 char. | 🟡 defensa en profundidad |
| Colisión de `clave_idempotencia` entre **dos usuarios** de la misma empresa | El índice único es por `(empresa_id, clave)` pero la búsqueda previa filtra por usuario; una colisión entre usuarios devolvería error de “turno en otra solicitud” en vez de reutilizar. UUID collision es despreciable; no se probó. | 🔴 no probado |
| DDL real sobre `reservas_recurso`/`agente_chat_mensajes` | El rol `postgres` no es owner (`supabase_admin`) y no se autorizó DDL destructivo. La mutación se hizo en copias temporales (§8). | 🔴 bloqueado por entorno/permisos |

---

## 11. Clasificación final

| Afirmación | Nivel |
|---|---|
| `make unit` 135 / `make test` 504 passed / `make e2e` 20/20 | 🟢 ejecutado, salida pegada |
| SEC-063 catálogo fiscal apagado y sin escritura por chat | 🟢 ejecutado |
| SEC-064 la corrección (`modificar`) manda en `crear_viaje` y `anular_viaje` | 🟢 ejecutado |
| SEC-065 topes por respuesta y por turno; rollback completo | 🟢 ejecutado |
| SEC-066 `PUT /modulos/{id}` retirado (404) | 🟢 ejecutado |
| SEC-069 panel montado (200 admin, 403 gerente) | 🟢 ejecutado |
| SEC-056/068 `tei_app` sin UPDATE del historial ni escritura de suscripción (42501) | 🟢 ejecutado |
| Transiciones, aislamiento y concurrencia de la primera entrega | 🟢 ejecutado y verificado |
| El cambio `0cf1be6` no debilitó el E2E | 🟢 verificado (diff + 20/20) |
| RLS de las tablas nuevas con `tei_app` (2 conexiones) | 🔴 no ejecutado en esta sesión |
| Mutación DDL sobre las tablas reales | 🔴 no determinable/bloqueado (owner `supabase_admin`, DDL no autorizado) |

---

## 12. Siguiente paso

1. `frontend`/`qa`: agregar E2E de `/configuracion/agentes` (GET, togglear una
   capacidad permitida, verificar el 403 de un rol sin `agente:configurar`).
2. `qa`: si se desea cerrar la deuda, ejecutar la suite SQL
   `supabase/tests/0033_01_privilegios_tei_app.sql` y
   `supabase/tests/0031_02_rls_tei_app.sql` (no forman parte de `make test`).
3. `datos`: evaluar si el `motivo` mínimo debe imponerse también en la base
   (hoy solo schema) y si el `EXCLUDE` de rampla/chofer merece prueba propia.
4. `backend`/`operacion`: commitear las correcciones y la migración `0033` que
   hoy están en el working tree; QA ya las validó con `make test`.
