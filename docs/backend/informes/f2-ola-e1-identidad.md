# F2 · Ola E1 — identidad sin `public.usuarios`

- **Fecha:** 2026-11-01
- **Rol:** `backend`
- **Riesgo:** ALTO (autenticación)
- **Alcance verificado:** `backend/app/**`, `backend/tests/**`, `docs/backend/**`.
- **Fuera de alcance (no tocado):** migraciones (0028 la aplica `datos`),
  `frontend/`, dependencias, `git commit`.

## Resultado

`GET /api/v1/auth/me` resuelve la identidad desde el JWT de Supabase Auth y el
rol de menú desde `nucleo.usuarios_empresa`; ya no importa ni consulta
`public.usuarios`. Se retiraron el gate legacy, `LEGACY_EMPRESA_ID`,
`tiene_membresia_activa`, `es_legacy`, `app.models` y
`app.core.settings_db` (sin uso tras el retiro). Suites: `make unit` 128
passed; `make test` 404 passed, 0 skipped.

## Cambios (archivo:línea)

| Archivo | Qué cambió |
|---|---|
| `backend/app/api/deps.py:36-47` | Mapeo `RolEmpresa → RolMenu` (admin/gerente→admin; despacho/taller/conductor→operacion; contador/tesoreria/auditor→contabilidad). |
| `backend/app/api/deps.py:50-77` | Desempate determinista `admin > operacion > contabilidad` y `rol_menu_efectivo()`. |
| `backend/app/api/deps.py:79-90` | `_membresias_utilizables()`: fija `nucleo.auth_id` y reutiliza `listar_empresas_usuario` (membresía activa + empresa activa, misma regla del núcleo). |
| `backend/app/api/deps.py:92-124` | `get_current_user()` devuelve `Identidad` desde el JWT; `sub` no UUID → 401; sin membresía → 403; `nombre` = `user_metadata.nombre` → `email` → `sub`. |
| `backend/app/core/security.py:45-70` | Nuevo `payload_from_credentials()` (payload verificado, 401 sin token/sub); `auth_id_from_credentials()` delega en él. Se eliminó `tiene_membresia_activa` y sus imports legacy (`get_engine`, `text`, `UUID`). |
| `backend/app/api/routes/auth.py:9-22` | `/auth/me` responde `{id=auth_id, nombre, email, rol}`; sin `es_legacy`. |
| `backend/app/api/deps.py` | `require_roles()` se eliminó: no tenía consumidores tras el retiro de los routers legacy (grep sin referencias) y dependía de `public.usuarios`. |
| `backend/app/schemas/__init__.py:6-30` | `RolMenu` local; `UsuarioOut` sin `es_legacy`; `id` documentado como `sub`. |
| `backend/app/main.py:145-158` | Se retiró `GateLegacyMiddleware`, `es_ruta_legacy`, `_token_bearer`, `_responder_legacy_denegado` y `_RUTAS_EXENTAS`. |
| `backend/app/main.py:182-187` | Pila de middlewares sin el gate. Se conserva `congelar_escritura_legacy` (la usan las pruebas del cutover). |
| `backend/app/core/config.py:24-25` | Se eliminó `LEGACY_EMPRESA_ID`. |
| `backend/app/models/__init__.py` | **Eliminado** (solo lo usaban los schemas legacy retirados y `settings_db`). |
| `backend/app/core/settings_db.py` | **Eliminado** (leía `public.configuracion`; sin consumidores de aplicación). |
| `backend/app/schemas/catalogos.py`, `viajes.py`, `facturas.py` | **Eliminados** (schemas de los routers legacy retirados; sin importadores). `kpis.py` se dejó porque no depende de `app.models` y queda fuera del objetivo. |
| `backend/tests/test_f2_tenant2_gate_legacy.py` | **Retirado**: probaba el gate eliminado y el `es_legacy`. La regresión de aislamiento se trasladó a `test_f2_ola_e1_identidad.py:291-315`. |
| `backend/tests/test_f2_ola_e1_identidad.py` | **Nuevo**: mapeo, contrato `/auth/me` (TEI/TES/contabilidad), 401/403, RLS por `auth_id`, guardas estáticas y aislamiento TES. |
| `backend/tests/test_seguridad_ola2.py` | Se retiró la prueba F-08 de `get_config_decimal` (módulo eliminado). |

## Contrato

Documento de contrato: `docs/backend/contratos/auth-me.md`.

`GET /api/v1/auth/me` → 200 `{id, nombre, email, rol}`; 401 sin token/inválido;
403 sin membresía utilizable; sin `X-Empresa-ID`; sin `es_legacy`.

## Autorización

- El `auth_id` sale del JWT verificado; la membresía se consulta por `auth_id`
  con RLS (`usuarios_empresa_lectura`, `0020_rls_multiempresa.sql:332-339`) y el
  GUC `nucleo.auth_id` fijado antes de la primera consulta
  (`backend/app/api/deps.py:85-90`).
- Deny-by-default: sin membresía activa en empresa activa → 403
  (`backend/app/api/deps.py:108-112`).
- La autorización real de negocio sigue en `get_contexto_empresa` +
  `nucleo/permisos.py`; el rol de `/auth/me` es solo navegación.

## Transacción e idempotencia

`/auth/me` es solo lectura: una transacción corta, sin escrituras, sin locks
explícitos y sin idempotencia necesaria. No hay efectos externos.

## Pruebas (salidas reales)

```text
$ make unit
128 passed, 2 warnings in 0.71s

$ make test
Supabase local arriba (detalle en …/tei-supabase-start.log)
404 passed, 2 warnings in 7.58s
```

No se ejecutó `make db-reset` ni `make test-db` (indicación de la tarea). No hay
`skip`/`xfail` en la salida. La suite usó `tei_test` (TEI y TES sembrados) y
JWT reales de Supabase para TEI, TES y contabilidad.

Ruff sobre los archivos tocados: solo reglas preexistentes del repo (`B008` por
`Depends` en defaults, `BLE001` del `except` de `decode_token`); sin imports
muertos nuevos.

## Compatibilidad

- **Frontend:** `frontend/src/context/auth-context.tsx:61` y
  `frontend/src/types/index.ts:3-12` ya esperan exactamente
  `{id, nombre, email, rol}`; no usan `es_legacy`. Sin cambios requeridos.
- **`id`:** cambia de `public.usuarios.id` a `sub` del JWT. Ningún consumidor
  del repo lo cruza con otra tabla.
- **Rutas:** `/api/v1/*` fuera de `/nucleo` y `/auth` ya no existe (404); el
  retiro de routers de la Ola C se mantiene (`test_f2_ola_c_retiro_routers.py`
  verde).

## Bloqueo de permisos: `scripts/` no se pudo editar

El prompt de la tarea autoriza `scripts/seed_local.py`,
`scripts/seed_segundo_tenant.py` y `scripts/cutover_legacy.py`, pero la
configuración del agente `backend` solo permite editar `backend/app/**`,
`backend/tests/**` y `docs/backend/**` (`.opencode/agents/backend.md:19-31`).
La herramienta devolvió `Permission denied: edit` para `scripts/seed_local.py`.
Por la regla de precedencia de `AGENTS.md` (gana la más restrictiva) **no se
editó** ni se sorteó el permiso. Queda pendiente para el orquestador:

### `scripts/seed_local.py`

1. Docstring (líneas 2-3): describir que el seed escribe solo `nucleo` + Auth.
2. Eliminar `ROL_LEGACY` (líneas 101-110).
3. Eliminar el bloque `insert into public.usuarios …` dentro del bucle de
   `USUARIOS` (líneas 207-216).
4. Eliminar el bloque `insert into public.clientes …` (líneas 244-251).
5. Eliminar el bloque `insert into public.tractos …` (líneas 279-292).
6. Eliminar el bloque `insert into public.ramplas …` (líneas 314-323).
7. Eliminar el bloque `insert into public.choferes …` (líneas 346-358).
8. Conservar íntegro el seed de `nucleo` (incluye `iva_porcentaje = 19` en
   `nucleo.configuracion_empresa`, líneas 178-187).

### `scripts/seed_segundo_tenant.py`

1. `USUARIOS` (líneas 23-27): quitar el cuarto elemento (`rol legacy`) y el
   comentario de `public.usuarios`.
2. Comprensión de `auth_ids` (líneas 37-40) y bucle (línea 74): desempaquetar
   tres valores.
3. Eliminar el espejo `insert into public.usuarios …` (líneas 85-97).
4. Docstring (líneas 9-10): quitar la referencia al acceso legacy por gate.

### `scripts/cutover_legacy.py`

Insertar el guard tras resolver `empresa_id` (línea 145) y **antes** de
`select * from public.clientes` (línea 147):

```python
            # Ola E1 (2026-11-01): `public` se retira con la migración 0028.
            # Sin `public.clientes` el cutover ya se ejecutó: script histórico,
            # sale con éxito sin tocar nada.
            cur.execute("select to_regclass('public.clientes')")
            if cur.fetchone()[0] is None:
                print("Cutover ya ejecutado: `public.clientes` no existe.")
                return
```

Mientras esto no se aplique, `make seed` sobre una base sin `public` fallará en
el primer `insert into public.*`.

## Handoff

- **Orquestador:** aplicar los tres parches de `scripts/` de la sección
  anterior **antes** de que `datos` aplique la 0028.
- **`qa`:** añadir a la guarda estática `scripts/*.py` (hoy solo cubre
  `backend/app`, `test_f2_ola_e1_identidad.py:224-236`) cuando los seeds estén
  limpios; probar `/auth/me` contra una base sin `public` tras la 0028.
- **`auditor-seguridad`:** revisar de forma independiente que (a) ningún camino
  de auth depende de `public`, (b) el 403 por membresía no filtra datos, (c) la
  precedencia de rol entre empresas no otorga permisos reales (solo menú).
- **`negocio-finanzas`:** los documentos `docs/negocio/catalogo-reglas.md:34,100`,
  `docs/negocio/implementacion.md:96`,
  `docs/backend/contratos/liquidaciones-comision-r01.md:65` y
  `docs/orquestacion/registro.md:320` citan `schemas/catalogos.py` /
  `schemas/viajes.py`, eliminados con los routers legacy. Hay que actualizar la
  cita (la regla R-01 vigente está en `nucleo/models.py` y `0017`/`0019`).

## Riesgos y no verificado

- 🔴 **`scripts/` sin limpiar** (bloqueo de permisos): los seeds aún escriben
  `public.usuarios`, `public.clientes`, `public.tractos`, `public.ramplas` y
  `public.choferes`.
- 🔴 **No probado contra una base sin `public`**: la 0028 no está aplicada y no
  se ejecutó `make db-reset`/`make test-db`. La independencia se sostiene con
  código + guarda estática + pruebas con JWT real, no con la tabla ausente.
- 🟡 **Decisión de rol entre empresas:** se eligió el menú de mayor alcance
  (`admin > operacion > contabilidad`). No hay regla de negocio documentada para
  el caso multiempresa; es solo presentación y está aislada en
  `rol_menu_efectivo`. Si el dueño quiere otro criterio, se cambia en un punto.
- 🟡 **Membresía en empresa inactiva:** se reutiliza `listar_empresas_usuario`,
  que exige empresa `activa`; el 403 se dispara aunque la membresía esté
  `activo=true`. Es coherente con `get_contexto_empresa`, pero es una decisión
  documentada, no una regla escrita por el dueño.
- 🟢 `backend/app/nucleo/__init__.py:3` aún menciona `app.models` en un
  comentario; el archivo no estaba en la lista permitida y no se tocó.
