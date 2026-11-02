# F2 — Ola C: retiro de las sistemáticas legacy (backend)

> **Nota (2026-11-01, Ola E1):** este informe describe el estado tras la Ola C.
> La Ola E retiró además la identidad legacy: `get_current_user` y `/auth/me` ya
> no leen `public.usuarios`. Ver
> `docs/backend/informes/f2-ola-e1-identidad.md`.

- **Fecha:** 2026-10-31 · **Agente:** `backend` · **Riesgo:** **Alto** (se retiran
  endpoints; la superficie pública de la API cambia).
- **Alcance:** ola **C** de `docs/arquitectura/adr/ADR-0002-retiro-del-legacy.md`
  §6.5 (API pura, sin migración de datos).
- **Método:** lectura de código, `grep` de consumidores, suites ejecutadas
  (`make test`), smoke HTTP contra `:8000` con recarga automática. Sin
  migraciones, sin frontend, sin dependencias, sin `git commit`.
- **Entorno:** repositorio local, Supabase local arriba (`:54321/:54322`),
  backend `:8000` (`uvicorn --reload`), `tei_test` ya existente.

---

## 1. Cambio

### 1.1 Routers desmontados (11)

| Router eliminado | Archivo borrado | Compuerta ADR |
|---|---|---|
| catalogos | `backend/app/api/routes/catalogos.py` | C.2 (muere con B.1) |
| viajes | `backend/app/api/routes/viajes.py` | C.1 |
| gastos | `backend/app/api/routes/gastos.py` | C.1 |
| dashboard | `backend/app/api/routes/dashboard.py` | C.1 (RET-06) |
| facturas | `backend/app/api/routes/facturas.py` | C.1 (RET-03/04) |
| finanzas | `backend/app/api/routes/finanzas.py` | C.1 / B.3 |
| mantenimiento | `backend/app/api/routes/mantenimiento.py` | B.1 |
| liquidaciones | `backend/app/api/routes/liquidaciones.py` | B.2 (RET-07) |
| configuracion | `backend/app/api/routes/configuracion.py` | B.4 |
| export | `backend/app/api/routes/export.py` | B.2 / C.1 |
| kpis | `backend/app/api/routes/kpis.py` | C.1 (RET-05) |

`backend/app/api/router.py` queda con **un solo** router legacy (`auth`) y los
15 `include_router` del núcleo. Se eliminaron también los imports.

### 1.2 Código sin consumidores

| Archivo | Qué | Evidencia de que nadie lo usa |
|---|---|---|
| `backend/app/services/kpi_engine.py` | motor de fórmulas de KPI | `grep -rn "kpi_engine" backend --include="*.py"` → 0 fuera del propio archivo y su test (borrado) |
| `backend/app/services/__init__.py` | paquete que quedó vacío | `grep -rn "app.services" backend scripts` → 0 |

Los **modelos** de `backend/app/models/__init__.py` **no se tocaron** (los usan
`auth`/`deps`, `core/settings_db.py`, los schemas y los scripts de seed/cutover).

### 1.3 Pruebas

| Archivo | Acción | Motivo |
|---|---|---|
| `tests/test_flujos_criticos.py` | **borrado** (9 pruebas) | todas pegaban a rutas legacy desmontadas |
| `tests/test_kpi_engine.py` | **borrado** (11 pruebas) | el motor ya no existe |
| `tests/test_reglas_negocio.py` | **borrado** (13 pruebas) | R-01 era legacy (**retirado**); **R-02 no** — ver §1.4 |
| `tests/test_r02_licencia_nucleo.py` | **nuevo** (6 pruebas) | R-02 extraída desde `test_reglas_negocio.py` |
| `tests/test_f2_ola_c_retiro_routers.py` | **nuevo** (31 pruebas) | guarda de regresión del retiro + OpenAPI + 404 HTTP |
| `tests/test_f1_ola2_adversarial.py` | ajustado | 3 pruebas legacy borradas; 4 del middleware adaptadas a 404 |
| `tests/test_f2_tenant2_gate_legacy.py` | ajustado | 2 pruebas HTTP que esperaban 200/401 de una ruta retirada |
| `tests/test_seguridad_ola2.py` | ajustado | se retiró `test_kpi_valores_registra_fallo_de_metricas` |
| `tests/test_f1_ola3_recursos_decimal.py`, `tests/conftest.py` | solo docstring | citaban `test_kpi_engine.py` |

**1.4 Desviación justificada respecto de la instrucción.** La instrucción pedía
borrar `test_reglas_negocio.py` "R-01/R-02 legacy". La evidencia dice que **solo
R-01 era legacy**: las pruebas de R-02 usan `sesion_aislada` +
`nucleo.servicio_disponibilidad` (sin HTTP, sin `public`). Borrarlas habría
eliminado la cobertura de una regla **bloqueante vigente** (`LICENCIA_NO_AUTORIZADA`
→ 409). Se extrajeron a `test_r02_licencia_nucleo.py` —mismo cuerpo, mismos
ids— y se borraron únicamente las de R-01. AGENTS §7.6 lo exige: "se reescriben
contra `nucleo`, no se borran para que pasen".

**1.5 Sobre `test_f1_ola2_adversarial.py`.** De las 7 pruebas que tocaban el
legacy:

- 4 del **middleware de congelamiento** se conservaron. Su contrato sigue vivo
  (`backend/app/main.py:326-351` no se toca en esta ola, `main.py` está fuera de
  mi alcance) y el 409 se emite **antes** del enrutado. Se actualizó la
  aserción de lectura de `401` a `404` y se documentó en el docstring que la
  ruta es deliberadamente una ruta retirada.
- 3 se borraron por depender funcionalmente de un endpoint eliminado
  (`POST /choferes` 23505, `POST /viajes/{id}/gastos` 23514, `POST
  /liquidaciones/calcular` concurrencia). Cobertura equivalente y **gap
  declarado** en el propio archivo (ver §7).

---

## 2. Contrato

### 2.1 Superficie activa (verificado vía `app.openapi()`)

```
$ cd backend && ../.venv/bin/python -c "from app.main import app; ..."
total paths: 101
legacy restantes: ['/health']      # fuera de /api/v1, no es legacy de negocio
auth: ['/api/v1/auth/me']
```

- **Routers de módulo activos: 20**:
  - **legacy (1):** `auth` (`/api/v1/auth/me`).
  - **núcleo (15, `include_router` en `api/router.py`):** `api` (raíz del
    núcleo), `agente`, `agente_solicitudes`, `maestros`, `comercial`, `bloqueos`,
    `expediente`, `pod`, `conductor`, `gastos`, `rentabilidad`, `facturacion`,
    `alertas`, `permisos`, `cutover`.
  - **Ola B (4, agregados por `nucleo/api.py:47` → `nucleo/router.py`):**
    `mantenimiento`, `nomina`, `iva/configuracion`, `export`.
- Invariante del estado final del ADR §4.1.1: **ninguna** ruta bajo
  `/api/v1` fuera de `/nucleo` y `/auth` (probado en
  `test_no_quedan_rutas_de_negocio_fuera_de_nucleo_y_auth`).

### 2.2 Rutas retiradas → 404

`GET`, `POST`, `PATCH`, `DELETE` sobre las rutas antiguas responden **404**
`{"detail":"Not Found"}` (FastAPI estándar). Verificado:

```
$ curl -s http://127.0.0.1:8000/api/v1/clientes
{"detail":"Not Found"}
PATCH /api/v1/viajes/x/estado -> 404
POST /api/v1/facturas -> 404
```

Inventario probado (OpenAPI + HTTP) en `tests/test_f2_ola_c_retiro_routers.py`:
`/clientes`, `/choferes`, `/viajes`, `/viajes/{id}/estado`, `/viajes/{id}/gastos`,
`/dashboard`, `/facturas`, `/facturas/{id}/estado`, `/cobranzas`, `/iva/resumen`,
`/pautas`, `/anticipos`, `/configuracion`, `/export/viajes`, `/kpis`.

**No se añadió un handler global de 404 "con mensaje claro"** (ADR §6.5): un
`@app.exception_handler` para `/api/v1/*` legacy enmascararía los 404 legítimos
del núcleo (recurso de otra empresa, id inexistente). El 404 por defecto no
filtra estructura interna y no rompe el contrato del núcleo.

### 2.3 Lo que **no** cambia

- `GET /api/v1/auth/me` sigue montado (contrato, headers y `es_legacy` intactos).
- Todo `/api/v1/nucleo/*` sigue igual.
- RLS, gate `LEGACY_SOLO_TEI` y middleware de congelamiento: **sin cambios**
  (`main.py` no se tocó).

---

## 3. Autorización

- No se relaja ni se retira ninguna dependencia de autorización. Lo que se retira
  es la **superficie**: no hay endpoint que pueda quedar sin permiso.
- `auth` conserva `get_current_user` (JWKS + `public.usuarios`).
- El núcleo sigue con `get_contexto_empresa` + `requiere_permiso` por endpoint.
- Las pruebas del gate se mantienen: **`test_http_tenant2_no_entra_al_legacy`
  sigue esperando 403 `LEGACY_SOLO_TEI`** (el gate corta antes del 404).
- Se adaptaron 2 pruebas HTTP del gate que esperaban 200/401 de una ruta hoy
  inexistente. El mecanismo del gate no cambió y sus pruebas aisladas (ASGI) no
  se tocaron. Esto **contradice literalmente** ADR §9.8 ("sin cambios"), pero el
  retiro hace imposible mantener 200/401 sobre `/clientes`; se documenta y queda
  para revisión de `arquitectura`.

---

## 4. Transacción e idempotencia

No aplica: esta ola **no escribe datos ni mueve filas**. `public` queda como
archivo de solo lectura y ninguna operación de negocio cambió de transacción.
Rollback = `git revert` del `include_router` y de los borrados; las rutas vuelven
sin pérdida porque no se movió ningún dato (ADR §10).

---

## 5. Pruebas

### 5.1 Suite completa

```
$ make test
...
405 passed, 2 warnings in 7.08s
```

**0 failed, 0 skipped** (los `skip` por credenciales no aparecen porque la
variable `TEST_ADMIN_*` la provee el target).

### 5.2 Selección unitaria (equivalente a `make unit`)

`make unit` **falla** porque el Makefile lista `tests/test_kpi_engine.py`, que
esta ola borró (y editar el Makefile está fuera de mi alcance):

```
$ make unit
ERROR: file or directory not found: tests/test_kpi_engine.py
make: *** [unit] Error 4
```

Ejecutando exactamente la misma lista **sin** ese archivo (más la guarda nueva):

```
$ cd backend && ../.venv/bin/python -m pytest tests/test_nucleo_tiempo.py \
    tests/test_nucleo_politicas.py tests/test_nucleo_schemas.py \
    tests/test_nucleo_modelos.py tests/test_nucleo_tarifas.py \
    tests/test_f1_ola3_recursos_decimal.py tests/test_agente_manifest.py \
    tests/test_agente_gate.py tests/test_agente_redaccion.py \
    tests/test_f2_ola_c_retiro_routers.py -o addopts=""
159 passed, 2 warnings in 1.08s
```

**Acción requerida (orquestador), única línea a cambiar en `Makefile:73`:**

```diff
-		tests/test_kpi_engine.py \
```

### 5.3 Foco: gate, adversariales y R-02

```
$ cd backend && ../.venv/bin/python -m pytest tests/test_f2_tenant2_gate_legacy.py \
    tests/test_f1_ola2_adversarial.py tests/test_r02_licencia_nucleo.py \
    -o addopts="" -q
68 passed, 3 skipped   # sin TEST_ADMIN_* en el shell; con `make test`: 0 skipped
```

Las 3 omisiones son sólo la falta de credenciales en esa invocación manual
(`-rs` lo dice); en `make test` esas mismas pruebas corren y pasan.

### 5.4 Smoke HTTP con el backend arriba

```
health=200
GET /api/v1/clientes -> 404
GET /api/v1/viajes -> 404
GET /api/v1/dashboard -> 404
GET /api/v1/facturas -> 404
GET /api/v1/cobranzas -> 404
GET /api/v1/iva/resumen -> 404
GET /api/v1/pautas -> 404
GET /api/v1/anticipos -> 404
GET /api/v1/configuracion -> 404
GET /api/v1/export/viajes -> 404
GET /api/v1/kpis -> 404
GET /api/v1/auth/me (sin token) -> 401
GET /api/v1/nucleo/clientes (sin contexto) -> 422
```

`/auth/me` **200** con JWT real: `make test` →
`test_f2_tenant2_gate_legacy.py::test_http_auth_me_expoe_es_legacy_por_tenant`
PASSED (TEI 200 `es_legacy=true`, TES 200 `es_legacy=false`). El `401` en vivo
demuestra que la ruta sigue montada y exige identidad (no es un 404).

---

## 6. Compatibilidad

- **Frontend:** `grep -rn "@/lib/api" frontend/src` → **0**; `lib/api.ts` y
  `lib/download.ts` **ya no existen**; `importar-csv.tsx` (huérfano que llamaba
  `/export/import/*`) **ya no existe**. No queda ningún consumidor de las rutas
  retiradas. C2 (cero consumidores) se cumple del lado UI.
- **Legacy:** `public` intacto; `auth` intacto; `GateLegacyMiddleware` y
  middleware de congelamiento intactos.
- **Scripts:** `grep -rn "api/v1\|httpx\|requests" scripts/cutover_legacy.py`
  → 0 (usa la base, no la API). `scripts/seed_local.py` usa `httpx` **solo**
  contra Supabase Auth (`/auth/v1/admin/users`), no contra esta API. Ningún
  script invoca un router retirado.
- **Tests:** ver §5; no quedan referencias a módulos borrados (ver §7).

---

## 7. Handoff

**`orquestador`**
1. Quitar `tests/test_kpi_engine.py` de `Makefile:73` (§5.2). Hasta entonces
   `make unit` está rojo por esa única causa.
2. Registrar en `docs/estado.md` que la superficie legacy de la API quedó en 1
   router (`auth`) y enlazar este informe.

**`arquitectura`**
3. ADR §9.8 dice que las pruebas del gate pasan "sin cambios"; 2 pruebas HTTP
   tuvieron que adaptarse (200/401 → 404) porque la ruta dejó de existir. El
   mecanismo sí quedó intacto. Confirmar o corregir el criterio.
4. ADR §5.1 declaraba C.2 "diferido hasta que B cierre" para `catalogos`,
   `mantenimiento`, `liquidaciones`, `configuracion`, `finanzas` (`/iva/resumen`) y
   `export` (`/liquidaciones`). La Ola B (núcleo) ya está en el árbol y la UI ya
   migró; por eso esta ola los desmontó **antes** de la Ola D. Si el ADR exige el
   orden estricto B→C, esto es una desviación de secuencia que debe quedar escrita.

**`qa`**
5. **Gap declarado:** no existe prueba de **concurrencia real sobre la creación**
   de la liquidación del núcleo (`(chofer, mes)`). La prueba legacy análoga se
   borró. La emisión sí tiene concurrencia
   (`test_nomina_concurrencia_emision_imputa_una_sola_vez`).
6. Adversariales nuevos sugeridos: `POST /api/v1/{legacy}` con token de TEI debe
   dar 404 (no 500, no 403); y el gate debe seguir dando 403 a TES **antes** del
   404.

**`auditor-seguridad`**
7. Revisar que el 404 uniforme no filtre existencia de recursos y que el
   `middleware` de congelamiento sobre rutas inexistentes no se convierta en un
   oráculo (409 vs 404 según el flag).

---

## 8. Riesgos y no verificado

| # | Ítem | Nivel | Detalle |
|---|---|---|---|
| R1 | RET-05 (motor de KPIs) sigue **abierta** en el ADR | 🟡 | Eliminé `kpi_engine.py` porque quedó sin consumidores, pero la decisión "¿el motor sobrevive?" es del dueño. Recuperable con `git show <commit>:backend/app/services/kpi_engine.py`; el rollback es trivial porque no hay datos asociados. |
| R2 | `make unit` rojo | 🟢 | Causa exacta y fix de una línea en §5.2; no es un fallo de código. |
| R3 | Campos huérfanos fuera de mi alcance | 🟡 | `backend/app/schemas/{catalogos,viajes,facturas}.py` y `backend/app/core/settings_db.py` quedan usados solo por `auth`/tests. No los borré: `app/schemas/**` y `app/core/**` no están en los archivos permitidos. Candidatos a la Ola E. |
| R4 | Gate + middleware sobre rutas inexistentes | 🟡 | Siguen activos y probados; su valor real termina en la Ola E.4/E.3. |
| R5 | Informes históricos con cifras viejas | 🟢 | `f2-tenant2-gate-legacy.md` y `contratos/liquidaciones-comision-r01.md` llevan aviso de retiro; no se reescribió su historia. |
| R6 | Documentos con referencias a archivos borrados | 🔴 | `docs/estado.md:122`, `docs/seguridad/hallazgos.md:47,120,332,339`, `docs/negocio/catalogo-reglas.md:81,288-359`, `docs/qa/matriz-trazabilidad.md` y los informes históricos `docs/backend/informes/f1-*.md` citan `test_reglas_negocio.py`, `test_flujos_criticos.py`, `test_kpi_engine.py`, `routes/kpis.py` o `kpi_engine.py`. No los edité: son de otras carpetas y son informes fechados. `arquitectura`/`qa` deben actualizarlos al registrar la ola. |
| R7 | OpenAPI con 101 rutas | 🟢 | No se comparó con el conteo previo (no había línea base de esta sesión); la evidencia es la lista actual. |
| R8 | Migraciones / datos | 🟢 | Ninguna migración ni escritura en `public`/`nucleo` en esta ola. |

---

## 9. Verificado 🟢 / Inferido 🟡 / No determinable 🔴

- 🟢 Routers retirados ausentes de `include_router` y de OpenAPI (salida pegada).
- 🟢 Rutas retiradas 404 en vivo y en `TestClient`.
- 🟢 `/auth/me` 200 con JWT real (suite) y 401 sin token (vivo).
- 🟢 `make test`: 405 passed, 0 skipped.
- 🟢 Sin imports a módulos borrados
  (`grep -rn "app\.services\|api\.routes\.(…)\|routes import (…)" backend --include="*.py"` → 0).
- 🟢 Sin consumidores frontend (`grep "@/lib/api"` → 0; `api.ts`/`download.ts`/`importar-csv.tsx` no existen).
- 🟡 `make unit` verde tras editar `Makefile:73` (no ejecutado: no puedo editar Makefile).
- 🔴 Conteo de rutas previo (no hay línea base registrada en esta sesión).
