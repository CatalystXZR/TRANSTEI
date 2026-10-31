# F1 Ola 5 (backend) — Activación del aislamiento multiempresa: dos engines (ADR-0005)

Fecha: 2026-10-30. Autor: agente `backend`. Riesgo: **ALTO** (multiempresa,
autorización, camino de conexión). Base de prueba: `tei_test` con `0020` aplicada
(35 políticas en `nucleo`, 31 `FORCE`; verificado en esta sesión, §5).
Entorno: Supabase local arriba (`127.0.0.1:54322`); sin migraciones, sin
dependencias nuevas, sin `git commit`.

---

## 1. Cambio

| Archivo | Qué |
|---|---|
| `backend/app/core/config.py:18-21` | Campo `NUCLEO_DATABASE_URL: str = ""` (DSN del rol `tei_app`). |
| `backend/app/core/database.py:1-31` | Docstring con la decisión (dos engines, frontera por esquema, fallback declarado). |
| `backend/app/core/database.py:50-58` | Marcadores estables `RLS inerte: configure NUCLEO_DATABASE_URL` y `nucleo_rls_inactivo`; estado de ambos engines y de la verificación de rol. |
| `backend/app/core/database.py:83-109` | `_crear_engine()` + `get_engine()` (**intacto**: mismo DSN, mismo rol, mismo `get_session`). |
| `backend/app/core/database.py:115-130` | `url_nucleo()`: `NUCLEO_DATABASE_URL` o fallback a `DATABASE_URL` con WARNING. |
| `backend/app/core/database.py:133-180` | `_estado_rol()` (evidencia `current_user`/`rolbypassrls`) y `verificar_rol_nucleo()` (guarda 503 si el DSN explícito bypasea RLS). |
| `backend/app/core/database.py:183-214` | `get_engine_nucleo()` + `get_session_nucleo()` (guarda de rol lazy, una vez por proceso). |
| `backend/app/nucleo/deps.py:24,54` | `get_contexto_empresa` usa `get_session_nucleo` (motor del núcleo). Autorización sin cambios. |
| `backend/app/nucleo/api.py:19-20,49,56,73,78-82` | Las tres dependencias de sesión del módulo base usan el motor del núcleo; `mis-empresas` fija `nucleo.auth_id` **antes** de su primera consulta. |
| `backend/app/nucleo/api_{alertas,bloqueos,comercial,conductor,cutover,expediente,facturacion,gastos,maestros,permisos,pod,rentabilidad}.py` | Solo el import y `Depends(get_session_nucleo)` (wiring; ninguna lógica tocada). Total: 12 módulos `api_*`, 25 dependencias (+3 en `api.py`). |
| `backend/app/nucleo/servicio_cutover.py:91-104` | Excepción declarada: el conteo de `public.viajes` se hace con el **engine legacy explícito** en su propia sesión (antes usaba la sesión del núcleo, que ahora es `tei_app` y no tiene GRANT en `public`). `legacy_congelado()` (`:37-40`) sigue en el engine legacy: lo consume el middleware de rutas legacy y no debe depender del motor del núcleo. |
| `backend/tests/test_f1_ola5_dos_engines.py` (nuevo, 11 pruebas) | Rol por engine, RLS con dos empresas, fail-closed, `WITH CHECK`, HTTP de aislamiento, `mis-empresas`, fallback, guarda 503 (unitaria y HTTP), frontera estática. |
| `backend/tests/contexto_helpers.py` (nuevo) | `contexto_de_prueba()`: alinea el GUC con el `ContextoEmpresa` simulado en las pruebas que sustituyen `get_contexto_empresa`. |
| `backend/tests/test_f1_ola2_adversarial.py:108`, `test_f1_ola2_1_cierre.py:226,251,296`, `test_f1_ola3_recursos_decimal.py:218,238`, `test_upload_invalido_http.py:71` | Las pruebas que reemplazan `get_contexto_empresa` ahora fijan el GUC. |
| `backend/tests/conftest.py:39-54` | RA-13: si `NUCLEO_DATABASE_URL` apunta a otra base que la de test, se anula (el núcleo cae al fallback ya redirigido a `tei_test`). |

**No** se tocaron: migraciones, `backend/app/api/**` (el legacy conserva
`get_session` y su motor), dependencias, `.env`, frontend, ni lógica de negocio.

---

## 2. Contrato (lo observable por el cliente)

Sin cambios de request/response. Cambia el **modo de fallo** del módulo núcleo:

| Situación | Antes (mono-engine `postgres`) | Ahora (engine `tei_app`) |
|---|---|---|
| `X-Empresa-ID` de una empresa donde el usuario no es miembro | 403 `ACCESO_DENEGADO` | **igual** (membresía en `deps.py:68-79`) |
| `X-Empresa-ID` ausente | 422 (header obligatorio) | **igual** |
| `X-Empresa-ID` no UUID | 422 (validación) | **igual**, antes de tocar la base |
| Consulta sin `app.empresa_id` (transacción sin contexto) | veía todo (RLS inerte) | **0 filas** (fail-closed, `0020`) |
| INSERT con `empresa_id` de otra empresa | se escribía | **42501** → hoy 500 genérico (ver §7, deuda) |
| `NUCLEO_DATABASE_URL` ausente | — | funciona con `DATABASE_URL` + WARNING `RLS inerte: configure NUCLEO_DATABASE_URL` (**desviación declarada**, §3) |
| `NUCLEO_DATABASE_URL` configurada pero el rol tiene `BYPASSRLS` | — | **503** en `/nucleo/*` + ERROR `nucleo_rls_inactivo` |
| Rutas legacy | sin cambios | sin cambios (mismo DSN, mismo rol, mismo `get_session`) |

Headers del núcleo: `X-Empresa-ID` (obligatorio), `X-Request-ID` (opcional,
trazabilidad). Idempotencia: no aplica a esta ola (no se modifica ninguna
operación de dinero/estado).

---

## 3. Desviación declarada respecto del ADR-0005 §3.2.2

El ADR (aceptado) pide **sin fallback**: sin `NUCLEO_DATABASE_URL`, `/nucleo/*`
responde 503. La orden de esta ola pide lo contrario para no romper el arranque
local: **fallback con warning** y una prueba que demuestre que el sistema sigue
funcionando sin la variable.

Implementado: fallback + WARNING (`database.py:115-130`) **y**, para no perder la
propiedad "un RLS apagado no puede pasar inadvertido", la guarda de rol del ADR
§3.2.3: si la variable **está** configurada y el rol efectivo tiene
`BYPASSRLS`, se registra `nucleo_rls_inactivo` (ERROR) y el módulo responde 503
(`database.py:146-180`, probado por HTTP en
`test_http_nucleo_responde_503_si_el_dsn_bypasea_rls`).

**Decisión pendiente para `arquitectura`/`orquestador`:** ¿se retira el fallback
en el release de producción (paso 3 del ADR)? Hoy el único camino que degrada en
silencio es "variable ausente", y deja un WARNING por proceso, no por request. El
release de producción define el DSN, así que ese camino no debería alcanzarse;
si se quiere exactamente el ADR, el cambio es de 3 líneas (`url_nucleo()` pasa a
levantar 503).

---

## 4. Autorización, transacción e idempotencia

- **Orden de dependencias (verificado con dos motores).** `get_contexto_empresa`
  fija `nucleo.auth_id` (`deps.py:65`) **antes** de la consulta de membresía; esa
  consulta ya resuelve bajo RLS porque la política `usuarios_empresa_lectura`
  permite `auth_id = nucleo.ctx_auth_id()`. `app.empresa_id` se fija **solo**
  después de verificar membresía y estado de empresa (`deps.py:94-95`). La
  empresa nunca sale del body.
- **`mis-empresas`** (sin `X-Empresa-ID`) fijaba `auth_id` en un objeto local y no
  en el contexto: con RLS habría devuelto `[]`. Corregido en `api.py:78-82`
  (defecto real de wiring, no de negocio).
- **Tenant:** el GUC `app.empresa_id` se reaplica en **cada** transacción
  (listener `begin`, Ola 4) y ahora también en el engine del núcleo: los 54
  `commit()` intermedios no pierden empresa ni `auth_id`. Probado
  (`test_rls_aisla_empresas_y_es_fail_closed`, bloque "tras commit").
- **Frontera de esquema:** el único acceso del núcleo a `public` es
  `servicio_cutover.estado()` y usa el engine legacy explícito, en su propia
  sesión. Prueba estática que falla si aparece otro
  (`test_solo_servicio_cutover_usa_el_engine_legacy`).
- **Idempotencia:** sin cambios (esta ola no crea ni modifica operaciones con
  dinero/estado).
- **Pools:** siguen los defaults de SQLAlchemy ⇒ dos pools por proceso. No se
  fijaron límites porque no hay cifra verificada del proveedor (RA del ADR §10
  R-3). **Riesgo abierto** para operación.

---

## 5. Pruebas (salidas reales, 2026-10-30)

### 5.1 Evidencia de rol por engine (script de lectura, contra `tei_test`)

```
$ DEBUG=false NUCLEO_DATABASE_URL=postgresql+psycopg://tei_app:***@127.0.0.1:54322/tei_test \
  ../.venv/bin/python -c "... _estado_rol(get_engine()) / _estado_rol(get_engine_nucleo())"
engine legacy  -> ('postgres', True)
engine nucleo  -> ('tei_app', False)
legacy DSN rol -> postgres
nucleo DSN rol -> tei_app
```

### 5.2 Estado de RLS en la base de prueba (consulta de control)

```
nucleo tei_app public.viajes SELECT -> False
nucleo tei_app nucleo.viajes SELECT -> True
nucleo politicas nucleo -> 35
nucleo tablas FORCE RLS -> 31
```

### 5.3 Pruebas nuevas

```
$ cd backend && DEBUG=false NUCLEO_TEST_DATABASE_URL=postgres://postgres@127.0.0.1:54322/tei_test \
  NUCLEO_DATABASE_URL=postgres://tei_app@127.0.0.1:54322/tei_test \
  ../.venv/bin/python -m pytest tests/test_f1_ola5_dos_engines.py -v -o addopts=""
tests/.../test_nucleo_corre_como_rol_sin_bypassrls PASSED
tests/.../test_legacy_conserva_su_rol PASSED
tests/.../test_rls_aisla_empresas_y_es_fail_closed PASSED
tests/.../test_empresa_ajena_no_se_puede_escribir PASSED
tests/.../test_http_aislamiento_entre_empresas PASSED
tests/.../test_http_mis_empresas_resuelve_por_auth_id PASSED
tests/.../test_fallback_sin_nucleo_database_url_funciona_y_avisa PASSED
tests/.../test_guarda_rechaza_dsn_explicito_con_bypassrls PASSED
tests/.../test_http_nucleo_responde_503_si_el_dsn_bypasea_rls PASSED
tests/.../test_guarda_en_fallback_solo_avisa PASSED
tests/.../test_solo_servicio_cutover_usa_el_engine_legacy PASSED
======================== 11 passed, 1 warning in 0.19s =========================
```

### 5.4 Regresión completa

```
$ make unit
67 passed, 2 warnings in 0.51s          # línea base: 67

$ make test
230 passed, 2 warnings in 5.18s         # línea base: 219 (+11 nuevas), 0 skip
```

### 5.5 Modo fallback (sin `NUCLEO_DATABASE_URL`), suite completa

```
$ cd backend && NUCLEO_DATABASE_URL= NUCLEO_TEST_DATABASE_URL=.../tei_test pytest tests -o addopts=""
215 passed, 15 skipped, 2 warnings in 4.20s
```
Los 3 skips atribuibles a esta ola son `test_nucleo_corre_como_rol_sin_bypassrls`,
`test_rls_aisla_empresas_y_es_fail_closed` y `test_empresa_ajena_no_se_puede_escribir`
(mensaje: "Sin NUCLEO_DATABASE_URL; … Ejecute `make test`"). Los otros 12 son
preexistentes (sin `TEST_ADMIN_EMAIL/PASSWORD` en esa invocación manual).

### 5.6 Mutación (copia desechable en `$TMPDIR`, no en el repo)

`get_engine_nucleo()` mutado para devolver el engine legacy (wiring regresado):

```
FAILED test_nucleo_corre_como_rol_sin_bypassrls
FAILED test_legacy_conserva_su_rol
FAILED test_rls_aisla_empresas_y_es_fail_closed
FAILED test_empresa_ajena_no_se_puede_escribir
FAILED test_http_aislamiento_entre_empresas
FAILED test_http_mis_empresas_resuelve_por_auth_id
```
⇒ las pruebas fallan si el núcleo vuelve al rol privilegiado. La otra mutación
está registrada por observación: **antes** de `contexto_de_prueba()` (ver §6),
25 pruebas HTTP existentes fallaban con 404 porque el contexto simulado no
llegaba a la base.

---

## 6. Compatibilidad

- **Legacy:** sin cambios de motor, DSN, rol ni sesión. `make test` cubre las
  rutas legacy (401/409 y flujos con token real) y sigue verde.
- **Frontend:** sin cambios de contrato; no requiere cambios (el cliente ya envía
  `X-Empresa-ID`). **No revisé** `frontend/` (fuera de mi alcance).
- **Pruebas existentes:** 4 archivos sustituían `get_contexto_empresa` con un
  `ContextoEmpresa` ya construido. Al correr el núcleo como `tei_app`, ese atajo
  dejaba la transacción **sin GUC** → 404 fail-closed. No era un defecto del
  código: era la prueba la que asumía acceso global. Se ajustaron con
  `contexto_de_prueba()` (fija `auth_id`/`empresa` del contexto simulado, sin
  reintroducir autorización: la membresía la decidió el fixture). Mismo patrón,
  misma causa documentada en `tests/contexto_helpers.py`.
- **Servicios del núcleo:** no se tocó ninguno. La frontera de esquema se cumple
  (grep: única referencia a `public.` en `backend/app/nucleo` es
  `servicio_cutover.py:97`).

---

## 7. Handoff

- **`qa`:** (a) el test HTTP de aislamiento prueba que A no ve B y que B da 403
  **también** con el rol privilegiado, porque el servicio filtra por empresa
  (defensa en profundidad); la prueba que aísla RLS como mecanismo es la de
  `tei_app` con dos contextos y la de mutación — conviene mantener ambas; (b)
  falta concurrencia real de dos conexiones `tei_app` con empresas distintas en
  esta ola (la cubre `supabase/tests/0020_02_dos_conexiones.sh`, según el informe
  de `datos`); (c) los 503 por `nucleo_rls_inactivo` deben alertar en operación.
- **`auditor-seguridad`:** (a) revisar la desviación del §3 (fallback);
  (b) R-1 del ADR sigue latente: el GUC de empresa viene de un header no
  confiable y las políticas de `usuarios_empresa`/`empresas` lo usan junto con
  `auth_id`; hoy ningún endpoint consulta `usuarios_empresa` antes de
  `get_contexto_empresa`, pero no hay prueba que lo impida; (c) `tei_app` puede
  insertar en `nucleo.auditoria` de su propia empresa (deuda declarada del ADR).
- **`datos`:** falta el mapeo `42501` → 403/404 vs 500 en `app/main.py`
  (ADR criterio 10). Hoy un INSERT cross-empresa devuelve 500 genérico; **no lo
  implementé** porque la orden de esta ola no lo incluía y toca el handler global
  usado por el legacy. `test_empresa_ajena_no_se_puede_escribir` documenta el
  comportamiento actual a nivel de driver.
- **`operacion`:** `make backend` y `make test` ya exportan el DSN de `tei_app`;
  en producción falta el secreto real y decidir el fallback (§3). Dos pools por
  proceso: workers × (legacy + núcleo) ≤ límite del plan (sin cifra verificada).

---

## 8. Veredicto de aislamiento

**El aislamiento multiempresa del núcleo está ACTIVO en `tei_test` y en el
arranque local (`make backend`), y el legacy no cambió.**

- Núcleo: engine `tei_app`, `rolbypassrls = false` ⇒ RLS vigente 🟢 (§5.1).
- Sin `app.empresa_id` válido, las tablas de tenant devuelven 0 filas 🟢 (§5.3).
- Empresa A no ve ni escribe datos de B (`USING` y `WITH CHECK`) 🟢 (§5.3).
- `X-Empresa-ID` de una empresa ajena ⇒ 403 sin fuga 🟢 (§5.3).
- `tei_app` no puede leer `public` (`has_table_privilege = false`) y ninguna ruta
  del núcleo lo intenta salvo el conteo declarado 🟢 (§5.2, §5.3).
- **No verificado:** comportamiento en la base de la aplicación / producción con
  el DSN real; PgBouncer/Supavisor en modo `transaction` (ADR R-2); límites de
  pool (ADR R-3); concurrencia de dos conexiones `tei_app` en esta suite.
- **Desviación:** el fallback a `DATABASE_URL` deja RLS inerte con un WARNING
  (orden de esta ola); decisión de retirarlo pendiente (§3).
