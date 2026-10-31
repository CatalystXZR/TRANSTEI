# F2 — Onboarding del segundo tenant: puerta del legacy + `es_legacy`

Fecha: 2026-10-31. Autor: agente `backend`. Riesgo: **Alto** (aislamiento entre
empresas). Base de prueba: `tei_test` refrescada con `make test-db` (clon de la
base local: 23 migraciones, TEI + TES). Entorno: Supabase local + backend
`:8000` con recarga automática + frontend `:3000`.

---

## 1. Cambio

| Archivo | Qué |
|---|---|
| `backend/app/main.py:147-302` | Clasificador `es_ruta_legacy()`, `_token_bearer()`, `_responder_legacy_denegado()` y `GateLegacyMiddleware` (ASGI puro, patrón de `LimiteCuerpoMiddleware`). Registro en `:302`. |
| `backend/app/core/config.py:27-31` | `LEGACY_EMPRESA_ID` (default `11111111-1111-1111-1111-111111111111`). |
| `backend/app/core/security.py:70-110` | `tiene_membresia_activa(auth_id, empresa_id)`: consulta `nucleo.usuarios_empresa` con el **engine legacy** (`BYPASSRLS`), fail-closed ante identificadores mal formados. |
| `backend/app/api/routes/auth.py:13-28` | `GET /auth/me` agrega `es_legacy`. |
| `backend/app/schemas/__init__.py:11-14` | `UsuarioOut.es_legacy: bool = False` (compatible: campo con default). |
| `backend/tests/test_f2_tenant2_gate_legacy.py` (nuevo, 35 pruebas) | Clasificador, gate aislado (todos los verbos), fail-closed de la membresía y HTTP con dos tenants. |

Sin migraciones, sin dependencias, sin cambios de contrato en los endpoints
legacy, sin tocar `public` ni `nucleo` en escritura.

**Hueco cerrado (verificado antes del cambio):** `admin2@tei.local` (tenant TES)
autenticado recibía **200** en `GET /api/v1/clientes` — el legacy es monoempresa
y no tiene `empresa_id` (`public.usuarios`, `public.clientes`). Salida real:

```
BASELINE admin2 GET /clientes: 200
BASELINE admin GET /clientes: 200
BASELINE admin2 /nucleo/clientes TES: 200
```

---

## 2. Contrato

### 2.1 Puerta legacy (middleware)

**Aplica a:** `settings.API_V1_PREFIX` (`/api/v1`) **salvo** los segmentos
`/nucleo` y `/auth`. Comparación por segmento: `/api/v1/nucleos` es legacy
(no se exenta por prefijo textual). `/health`, `/`, `/docs` quedan fuera porque
no cuelgan del prefijo.

| Situación | Respuesta | Cambia el contrato |
|---|---|---|
| Sin `Authorization: Bearer` | pasa a la ruta → **401** como siempre | no |
| Token mal formado/vencido/esquema ≠ Bearer | pasa a la ruta → **401** | no |
| Token válido, `sub` ausente | pasa a la ruta → **401** | no |
| Token válido, **sin** membresía activa en `LEGACY_EMPRESA_ID` | **403** `{"codigo":"LEGACY_SOLO_TEI","detail":…}` | sí (era 200) |
| Token válido, **con** membresía activa en `LEGACY_EMPRESA_ID` | pasa a la ruta (comportamiento previo) | no |

- Todos los verbos (`GET/POST/PUT/PATCH/DELETE`) pasan por la puerta. El orden
  con el control existente es `congelar_escritura_legacy` (409
  `CUTOVER_LEGACY_CONGELADO`) → CORS → **gate (403)** → tope de cuerpo →
  contexto → router.
- El 403 se emite con `content-type: application/json`, `content-length` y
  `connection: close` (no se lee el cuerpo del request; evita desincronizar la
  conexión con bytes pendientes, mismo criterio que el 413 de SEC-021).
- Cambio declarado: un usuario de Supabase **válido pero sin ninguna membresía**
  en el ERP recibe 403 (antes 401 en el legacy). Es la dirección segura:
  autenticado ≠ autorizado.
- El `detail` no revela estructura interna ni el rol de base de datos.

### 2.2 `GET /api/v1/auth/me`

```json
{"id":"<uuid>","nombre":"…","email":"…","rol":"admin","es_legacy":true}
```

`es_legacy` = membresía activa en `LEGACY_EMPRESA_ID` (misma consulta que la
puerta). Campos previos intactos; `es_legacy` tiene default `false`, así que
cualquier consumidor que no lo lea sigue funcionando. `auth/me` **no** pasa por
la puerta: el tenant 2 debe poder leer su perfil para que la UI sepa que no
tiene legacy.

---

## 3. Autorización

- **Deny-by-default en el legacy:** el permiso no viene del JWT ni de un header,
  sino de la membresía en `nucleo.usuarios_empresa` resuelta en el servidor.
- **Tenant desde el servidor:** `LEGACY_EMPRESA_ID` es configuración, no un
  valor del request. Nada del body/headers decide la empresa.
- **Núcleo sin cambios:** `/api/v1/nucleo/*` sigue autorizando con
  `get_contexto_empresa` (membresía + `X-Empresa-ID` + RLS), verificado hoy:
  `admin2` con `X-Empresa-ID=TES` → 200; con `X-Empresa-ID=TEI` → 403
  `ACCESO_DENEGADO`.
- **Por qué el engine legacy para leer la membresía:** las políticas RLS de
  `0020_rls_multiempresa.sql` limitan `usuarios_empresa` a la empresa del
  contexto (`app.empresa_id`); en el legacy no hay contexto, así que con
  `tei_app` la consulta vería 0 filas y negaría el acceso a todos. El engine
  legacy (`postgres`, `BYPASSRLS`) sí ve la membresía. Es una lectura de
  plataforma, no de datos de tenant.
- El middleware **solo** usa el claim `sub` del JWT (no requiere claims extra
  ni scopes). La ruta vuelve a validar el token con su dependencia habitual.

---

## 4. Transacción e idempotencia

- La puerta es **solo lectura**: `select 1 … where auth_id and empresa_id and
  activo`. No escribe, no abre transacción explícita (autocommit de lectura con
  rollback al cerrar la conexión) y no hay nada que compensar.
- No hay operación con dinero/estado en este cambio → **no aplica**
  idempotencia; el 403 es determinista para el mismo token.
- Coste: una consulta por request legacy con token válido (una por
  `auth/me`). Índice `idx_usuarios_empresa_auth (auth_id) where activo`
  (`0004_nucleo_operacional.sql:153`) + `unique (empresa_id, auth_id)` sostienen
  la consulta. No se cachea a propósito: desactivar una membresía debe surtir
  efecto en el siguiente request.
- JWT: se decodifica dos veces por request legacy (gate + dependencia de la
  ruta). La segunda usa la firma ya cacheada por `PyJWKClient`; el coste es
  verificación, no red. Ambas llamadas bloqueantes van por
  `run_in_threadpool` para no bloquear el event loop.
- **Fail-closed ante fallo de base:** `tiene_membresia_activa` no captura
  errores de conexión; el request termina en 5xx, nunca en acceso concedido.

---

## 5. Pruebas

### 5.1 Comandos y salidas reales

```text
$ make unit
135 passed, 2 warnings in 0.75s

$ make test
........................................................................ [ 18%]
...
388 passed, 2 warnings in 7.15s
```

`make test` = 353 previas + **35 nuevas**, sin `skip` ni `xfail`. Antes de la
suite se refrescó `tei_test` (el clon previo no tenía TES):

```text
$ make test-db
migraciones=23
nucleo_tablas=40
public_tablas=17
```

Cobertura nueva (`backend/tests/test_f2_tenant2_gate_legacy.py`):

| Grupo | Pruebas |
|---|---|
| Clasificador | 14 casos: legacy, `/nucleo`/`/auth`, `/health`, `/`, `/api/v1/nucleos`, `/api/v10/...` |
| Gate aislado (sin base) | sin token, token inválido, sin `sub`, sin membresía (403), con membresía, `Basic` no Bearer, `POST/PUT/PATCH/DELETE`, y que `/nucleo`, `/auth`, `/health` no consulten membresía |
| Membresía fail-closed | `LEGACY_EMPRESA_ID`/`sub` mal formados → `False` sin tocar la base |
| HTTP (base de test) | 403 legacy para TES, 200 núcleo TES con clientes solo de TES, 403 núcleo TEI para TES, 200 legacy para TEI, `es_legacy` true/false, 401 sin token |

### 5.2 Sanidad (mutación) — la prueba falla si se retira el mecanismo

En copia local, comentando `app.add_middleware(GateLegacyMiddleware)`:

```text
FAILED tests/test_f2_tenant2_gate_legacy.py::test_http_tenant2_no_entra_al_legacy
```

Restaurado y verificado (`grep` → `app/main.py:302`), sin restos de la mutación.

### 5.3 HTTP contra el backend real (`:8000`), tras el cambio

```text
1 admin2 GET /api/v1/clientes -> 403 codigo=LEGACY_SOLO_TEI
   detail='Su empresa no tiene acceso a las pantallas legacy (monoemp…'
2 admin2 GET /api/v1/nucleo/clientes X-Empresa-ID=TES -> 200 codigo=None
   clientes TES devueltos: 2 | razones sociales: ['Agro Los Ríos Ltda', 'Minera del Sur SpA']
3 admin GET /api/v1/clientes -> 200 codigo=None
4a admin GET /api/v1/auth/me -> 200 es_legacy=True
4b admin2 GET /api/v1/auth/me -> 200 es_legacy=False
5 sin token GET /api/v1/clientes -> 401 detail='Se requiere autenticación'
```

Los 4 escenarios de aceptación (403 legacy TES / 200 núcleo TES / 200 legacy TEI
+ `es_legacy=true` / `es_legacy=false`) están cubiertos en HTTP real y en la
suite (`TestClient`, misma app, base `tei_test`, rol `tei_app` con RLS).

---

## 6. Compatibilidad

- **Legacy:** para TEI nada cambia (mismo 200, misma forma de respuesta, mismo
  401 sin token). No se borró ni duplicó ninguna ruta legacy.
- **Frontend:** `UsuarioOut` gana un campo con default; consumidores previos no
  se rompen. El cliente puede usar `es_legacy` para ocultar el menú legacy; la
  autorización no depende de eso. Hay trabajo de frontend en paralelo
  (`docs/frontend/f2-tenant2-navegacion.md`, `frontend/src/...`), no tocado por
  este agente.
- **Tenant 2 en `/auth/me`:** el endpoint sigue leyendo `public.usuarios`
  (`get_current_user`), por eso el seed crea el espejo legacy del usuario. Si un
  usuario del tenant 2 no tiene fila en `public.usuarios`, `/auth/me` responde
  401 (comportamiento previo, no de este cambio).
- **Tests:** `make test` requiere `tei_test` con el segundo tenant; el clon
  viejo no lo tenía. La prueba HTTP falla con mensaje explícito si el usuario
  no existe (no se omite), indicando ejecutar `make test-db`.

---

## 7. Handoff

**Frontend**

- `GET /api/v1/auth/me` → nuevo campo booleano `es_legacy`. Ocultar navegación
  legacy cuando `false` y mostrar el aviso correspondiente.
- Cualquier llamada a `/api/v1/*` fuera de `/nucleo` y `/auth` puede devolver
  **403** `{"codigo":"LEGACY_SOLO_TEI","detail":…}`. Conviene mapearlo a un
  mensaje de "módulo no disponible para su empresa", no a un error genérico.
- `/nucleo/*` mantiene su contrato: `X-Empresa-ID` obligatorio y 403
  `ACCESO_DENEGADO` si la empresa no es del usuario.

**QA / auditor-seguridad (revisión independiente)**

- Repetir: `admin2` → 403 en legacy; `admin2` + `X-Empresa-ID=TES` → 200 en
  núcleo y solo clientes de TES; `admin` → 200 legacy y `es_legacy=true`.
- Adversariales sugeridos: token válido de usuario sin membresía; membresía
  desactivada (`activo=false`) debe cortar en el siguiente request; `PATCH`/
  `DELETE` legacy con token de TES; `/api/v1/nucleos` (no debe exentarse);
  cabecera `X-Empresa-ID` intentando abrir el núcleo ajeno (ya cubierto).
- Verificar que ningún endpoint legacy cuelga fuera de `/api/v1`: hoy el router
  legacy completo se monta bajo `API_V1_PREFIX` (`backend/app/api/router.py`).

---

## 8. Riesgos y no verificado

| Ítem | Nivel | Detalle |
|---|---|---|
| 403 real para TES y 200 real para TEI | 🟢 | Salidas de §5.3 contra `:8000`. |
| Suite completa en verde | 🟢 | 135 unitarias / 388 totales, sin skip. |
| La prueba detecta la ausencia del gate | 🟢 | Mutación §5.2. |
| Aislamiento del **legacy** por fila | 🔴 | No existe: `public` no tiene `empresa_id`. La única frontera es esta puerta y **no cubre** escrituras hechas por scripts/seed con el rol `postgres`. |
| RLS efectiva del núcleo | 🟢 hoy en `tei_test` | `tei_app` sin `BYPASSRLS`; en la base de la app depende del DSN configurado (ADR-0005). |
| Coste de la consulta por request | 🟡 | Una consulta indexada por request legacy; no medida bajo carga. Si aparece contención, la alternativa sería un `Idempotency`-style cache con TTL corto — **no implementado** (la revocación debe ser inmediata). |
| Latencia del gate | 🟡 | Añade verificación JWT + consulta a membresía antes de la ruta en cada request legacy. |
| Usuarios del tenant 2 sin espejo en `public.usuarios` | 🟢 documentado | `/auth/me` responde 401; el seed crea el espejo. No es un fallo del gate. |
| Endpoints legacy fuera de `/api/v1` | 🟢 | No hay: el router legacy se monta bajo el prefijo (`app/api/router.py`); `/health` y `/` no son legacy. |
| Caché de membresía | — | Decisión explícita: sin caché (seguridad > latencia). |

**Escalado pendiente (no bloqueante):** si el producto necesita que un usuario
de otro tenant use *alguna* pantalla legacy, eso exige partir el legacy por
empresa (plan de cutover/ADR), no relajar esta puerta. No se inventó ninguna
regla de negocio en este cambio.
