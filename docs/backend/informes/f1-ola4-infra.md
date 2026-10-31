# F1 Ola 4 (backend) — Infra de request: SEC-021 y contexto por transacción

Fecha: 2026-10-30. Autor: agente `backend`. Riesgo: **Medio-Alto** (infra de
request/transacción). Base de prueba: `tei_test` (clon de la base local, 0019 +
0020 aplicada de forma manual; ver §7).

Alcance de esta ola: **preparar el terreno**. No se cambió el rol de
`DATABASE_URL` (sigue `postgres`, `rolbypassrls = true`): el ADR de tenancy está
en curso. Por lo tanto, aquí se implementa y se prueba el **mecanismo**, no el
aislamiento efectivo de RLS.

---

## 1. Cambio

| Archivo | Qué |
|---|---|
| `backend/app/main.py:26-178` | SEC-021: `LimiteCuerpoMiddleware` (ASGI puro) + cotas + `limite_para_cuerpo()`. Contexto: `ContextoRequestMiddleware`. Ambos registrados en `:176-177`. |
| `backend/app/core/contexto.py` (nuevo) | `ContextoRequest` (ContextVar), `contexto_de_request()`, `fijar_*`, `valores_contexto()`, `aplicar_contexto()`, `aplicar_contexto_sesion()`, `limpiar_request_id()`. |
| `backend/app/core/database.py:12-31` | Listener `begin` del engine: reaplica los GUCs en cada transacción. `get_engine()` lo engancha (`:45-49`). |
| `backend/app/nucleo/deps.py:65-66,94-95` | `get_contexto_empresa` fija `nucleo.auth_id`/`request_id` antes de la primera consulta y `app.empresa_id` al verificar la membresía, y sincroniza la transacción en curso. |
| `backend/tests/test_f1_ola4_infra.py` (nuevo, 16 pruebas) | Middleware, cotas, `ContextVar`, GUC tras commits, fail-closed, integración con `get_contexto_empresa`, HTTP 413 / no-regresión. |

No se tocaron migraciones, dependencias, servicios concretos ni el rol de
conexión. No se modificaron `test_nucleo_conductor.py` ni
`test_f1_ola2_adversarial.py`.

---

## 2. Contrato — tope de cuerpo (SEC-021)

**Aplica a:** todo `http` (no websocket), antes del parseo de formularios y de
las dependencias de auth (`fastapi/routing.py:247` → `request.form()` ocurre
antes de `solve_dependencies` en `:291`; `starlette/formparsers.py:135` usa
`max_files=1000`).

**Cotas:**

| Ruta | Cota | Por qué |
|---|---|---|
| Global (resto de la API) | 32 MB (`main.py:42`) | `storage.MAX_BYTES` = 10 MB por documento + margen multipart/JSON. No es una regla de negocio: es transporte. |
| `POST /api/v1/nucleo/expediente/viajes/{id}/pod` | 106 MB (`main.py:43-46`) | `MAX_FOTOS(10) × MAX_BYTES(10 MB) + MAX_FIRMA_BYTES(5 MB) + 1 MB` de holgura. Reproduce el tope que ya aceptan `api_pod.py`/`servicio_pod.py`; con 32 MB un POD legítimo de 4+ fotos de 10 MB pasaría a 413. |

**Detección:**
1. `Content-Length` declarado > cota → `413` **sin leer un solo byte** del cuerpo.
2. Sin `Content-Length` (chunked) → se cuenta cada `http.request` recibido y se
   corta al superar la cota.

**Respuesta:**

```http
HTTP/1.1 413 Payload Too Large
content-type: application/json
connection: close
```
```json
{"codigo": "CUERPO_EXCESO",
 "mensaje": "El cuerpo del request supera el máximo permitido (32 MB)."}
```

`connection: close` es deliberado: el cuerpo no se drena y reutilizar la
conexión desincronizaría HTTP. El mensaje nunca incluye datos del cliente.
**Estable:** `codigo` es el contrato; el texto puede cambiar.

**Compatibilidad:** ningún endpoint en uso cambia de contrato. Un request ≤ cota
sigue exactamente igual (verificado: multipart pequeño → 401 de auth, no 413;
los uploads 201 de `test_nucleo_pod.py` y `test_f1_ola3_recursos_decimal.py`
siguen verdes).

---

## 3. Contrato — contexto de empresa/auditoría por transacción

**GUCs fijados en cada transacción** (`contexto.py:63-67`, una sola ida y vuelta):

| GUC | Origen | Ausencia |
|---|---|---|
| `app.empresa_id` | `nucleo.empresas.id` resuelta desde `X-Empresa-ID` **verificando membresía** (`deps.py:68-95`) | `''` ⇒ `nucleo.ctx_empresa()` = NULL |
| `nucleo.auth_id` | `sub` del JWT validado contra JWKS (`security.py`), fijado **antes** de consultar la membresía | `''` ⇒ auditoría usa `'sistema'` |
| `nucleo.request_id` | header `X-Request-ID`, acotado a `^[A-Za-z0-9._:-]{1,128}$` | `''` ⇒ `NULL` en auditoría |

**Ciclo de vida:**
1. `ContextoRequestMiddleware` (`main.py:145-169`) abre un contexto limpio y lo
   resetea al terminar → un request no hereda el anterior.
2. `get_contexto_empresa` rellena `auth_id` y `request_id` y, tras verificar
   membresía + empresa activa, `empresa_id`. Es el **único** punto que rellena
   `app.empresa_id`; nunca sale del body.
3. `event.listen(engine, "begin")` (`database.py:29-30`) reaplica los tres GUCs
   al inicio de **cada** transacción: sobreviven a los `commit()` intermedios de
   los servicios sin tocarlos (31 sitios de `set_config` intactos).
4. Al cambiar el contexto dentro de una transacción ya abierta (paso 2),
   `aplicar_contexto_sesion(session)` (`deps.py:95`) la sincroniza.

Un `X-Request-ID` fuera de `^[A-Za-z0-9._:-]{1,128}$` se descarta tanto en el
contexto como en `ContextoEmpresa.request_id` (`deps.py:101`), que es lo que los
servicios escriben en `nucleo.auditoria`: no puede inyectar basura en la
auditoría.

**Fail-closed:** los GUCs se fijan siempre, con `''` si no hay contexto. No se
depende de "no fijar nada", y un valor `is_local=false` heredado de la conexión
queda neutralizado al abrir la transacción siguiente (probado). Con el rol
actual (`BYPASSRLS`) no hay filtrado observable todavía: el mecanismo queda
listo y probado para el cutover de rol.

**Nota de diseño:** `ContextoRequest` es mutable a propósito. Las dependencias
síncronas de FastAPI corren en un hilo del pool: el `ContextVar` se copia pero
la instancia se comparte, así que mutarla es lo que hace visible lo resuelto por
`get_contexto_empresa` en los demás hilos y en el listener de SQLAlchemy.

---

## 4. Autorización

- Sin cambios en autenticación ni permisos. `get_contexto_empresa` sigue
  resolviendo empresa y rol en el servidor (`deps.py:49-82`); el tenant no se
  acepta desde el body.
- El 413 ocurre **antes** de la auth: no revela si el recurso existe ni si el
  token es válido. Es un límite de transporte, no una decisión de negocio.
- El contexto no concede permisos: solo aporta el GUC que usará RLS cuando el
  rol deje de ser `BYPASSRLS`.

---

## 5. Transacción e idempotencia

- Una operación de negocio sigue siendo una transacción; este cambio **no**
  agrega commits ni los quita. Añade una sentencia por transacción (3
  `set_config` en un solo `SELECT`) y no altera el orden de locks.
- No aplica idempotencia: no hay dinero ni cambio de estado; es infraestructura
  de contexto por request.
- El listener no escribe datos ni DDL.

---

## 6. Pruebas (salidas reales)

```text
$ make unit
67 passed, 2 warnings in 0.51s

$ make test
219 passed, 2 warnings in 5.38s

$ cd backend && NUCLEO_TEST_DATABASE_URL=...tei_test \
    ../.venv/bin/python -m pytest tests/test_f1_ola4_infra.py
16 passed, 1 warning in 0.09s
```

Cobertura de las pruebas nuevas (`backend/tests/test_f1_ola4_infra.py`):

| Prueba | Qué garantiza |
|---|---|
| `:110` cota global | 32 MB documentado y fijado |
| `:115` cota POD | derivada de `MAX_FOTOS/MAX_BYTES/MAX_FIRMA_BYTES`; solo la ruta POD la recibe |
| `:125` 413 sin leer | `Content-Length` sobre cota ⇒ 413, `receive` **nunca** invocado, `connection: close` |
| `:151` borde exacto | `Content-Length == cota` pasa |
| `:165` chunked bajo cota | conteo real no bloquea un cuerpo válido |
| `:188` chunked sobre cota | corta en el chunk que excede (solo se leyó el primero) |
| `:220` limpieza | el `ContextVar` no se hereda entre requests |
| `:231` request-id | charset/longitud; valor inválido ⇒ `None` |
| `:265` commits intermedios | `app.empresa_id`/`auth_id`/`request_id` iguales antes y después de 2 `commit()` |
| `:283` fail-closed | sin contexto: GUCs `''` y `nucleo.ctx_empresa()` NULL |
| `:293` GUC de sesión previo | `set_config(...,false)` heredado queda neutralizado por el listener |
| `:344` integración `get_contexto_empresa` | la empresa sale de la membresía verificada y llega a la transacción (también tras commit) |
| `:366` sin membresía | `AccesoDenegado` y `app.empresa_id` queda `''` |
| `:392` HTTP 413 | POST sin token con `Content-Length` 32 MB+1 → 413 `CUERPO_EXCESO` (antes de auth) |
| `:406` cota POD por ruta | 32 MB+1 en el POD **no** da 413 (lo rechaza la auth) |
| `:419` no-regresión | multipart pequeño al POD → 401 de auth, no 413 |

**Prueba de mutación (manual, sin dejar cambios):** con un engine **sin** el
listener, el mismo flujo pierde el GUC en el `commit()`:

```text
antes del commit: ('156f29d7-…', None)
despues del commit: ('', None)
```

Es decir, `test_gucs_sobreviven_a_commits_intermedios` falla si se retira el
mecanismo (🟢).

Uploads legítimos con 201: los cubre la suite existente
(`test_nucleo_pod.py`, `test_f1_ola3_recursos_decimal.py::test_pod_10_fotos_acepta`)
que corrió verde en `make test`.

---

## 7. Compatibilidad y límites

- `frontend/`: sin cambios. El 413 es un caso nuevo que la UI debe poder
  mostrar; ver Handoff.
- Legacy (`public`): sin cambios de contrato. El listener fija GUCs inofensivos
  en sus transacciones; con el rol actual no cambia nada. Con un rol sin
  `BYPASSRLS`, **el legacy vería 0 filas** (las 17 tablas de `public` tienen RLS
  sin políticas) — ya documentado en `docs/datos/rls-multiempresa.md` §5 y fuera
  del alcance de esta ola.
- `make test` corre contra `tei_test`, que tiene las funciones `nucleo.ctx_*` y
  las 35 políticas de 0020 aplicadas **manualmente** (la tabla
  `supabase_migrations` marca hasta 0019). La prueba de fail-closed usa
  `nucleo.ctx_empresa()` solo para leer, así que no depende del rol.
- No se probó con `tei_app` (prohibido cambiar el rol en esta ola): el filtrado
  efectivo de filas por RLS queda 🔴 y lo cierra el ADR de tenancy.

---

## 8. Handoff

| Destinatario | Qué revisar / hacer |
|---|---|
| `frontend` | Manejar `413` con `codigo = "CUERPO_EXCESO"`: mensaje "archivo o envío demasiado grande" y no reintentar. Un POD con 10 fotos de 10 MB **sí** pasa (106 MB); el mensaje no debe culpar a una foto puntual. |
| `qa` | Adversariales: chunked sin `Content-Length` (atraviesa el tope), `Content-Length` mentiroso menor al cuerpo real (el conteo corta), 413 sin token, 413 no deja archivos temporales, POST de 33 MB a `/nucleo/viajes` no consume 33 MB del worker. `test_f1_ola4_infra.py:188` es la base del caso chunked. |
| `auditor-seguridad` | Revalidar SEC-021 con el middleware ya activo; residual: el POD admite 106 MB sin token (acotado, no infinito). Recomendación de borde: `client_max_body_size` en el proxy. |
| `arquitectura`/`datos` | Antes de cambiar `DATABASE_URL` a `tei_app`: (a) `GET /nucleo/mis-empresas` (`backend/app/nucleo/api.py:69-77`) no pasa por `get_contexto_empresa`, así que `nucleo.auth_id` no se fija en esa ruta y la política de `nucleo.empresas` no vería empresas. Necesita `fijar_auth_id(auth_id)` antes de `listar_empresas_usuario` (1 línea, fuera de los archivos de esta ola); (b) los servicios que fijan `nucleo.auth_id` con `set_config` siguen funcionando, pero ya no son necesarios para la empresa; (c) revisar `servicio_cutover.py` y scripts que creen engines propios: solo el engine de `get_engine()` tiene el listener. |

---

## 9. Riesgos y no verificado

- 🔴 **Filtrado RLS efectivo**: el rol es `postgres` (`BYPASSRLS`). Se verificó
  el GUC y el fail-closed del valor, no que las políticas devuelvan 0 filas con
  el rol de aplicación.
- 🟡 **Conexiones ajenas al engine**: sesiones creadas con `create_engine()`
  propio (varios tests, scripts) no reciben el listener. En la app todo pasa por
  `get_engine()`.
- 🟡 **Chunked**: el corte se probó con el middleware aislado (cota inyectada de
  10 bytes). No se enviaron 32 MB reales por socket; el conteo es el mismo
  camino de código.
- 🟡 **Proxy**: el tope es de aplicación. En producción conviene un límite
  equivalente en el proxy; no está en el repo.
- 🟢 No se modificó el rol, migraciones ni dependencias; `make unit` y
  `make test` verdes sin *skips*.

## Rollback

Revertir los 5 archivos (2 nuevos, 3 editados). Sin migraciones ni datos: el
listener y los middlewares desaparecen y el comportamiento vuelve al de 0019.
