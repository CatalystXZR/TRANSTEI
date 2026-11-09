# Chat in-app del agente (`gerente`, `secretaria`)

**Ola 3 — runtime de chat con LLM y buzón de aprobación.**
Última verificación: **2026-11-02**, contra `tei_test` (migraciones `0030` y
`0031` aplicadas) y `make unit` / `make test`. Incluye las mitigaciones
SEC-051, SEC-052, SEC-053, SEC-055, SEC-057, SEC-061 y SEC-062 de las revisiones
independientes.

Este documento describe el contrato HTTP, las reglas del servidor, las tools por
agente, el muro de pago y lo que **no** quedó verificado. La UI no forma parte de
esta entrega.

---

## 1. Alcance

| Pieza | Archivo | Estado |
|---|---|---|
| Configuración (claves, modelo, límites, concurrencia) | `backend/app/core/config.py:42-66` | 🟢 |
| Cliente LLM OpenAI-compatible | `backend/app/nucleo/agente/chat/llm.py:64-197` | 🟢 |
| Personas y system prompts | `backend/app/nucleo/agente/chat/personas.py:23-136` | 🟢 |
| Tools y validadores | `backend/app/nucleo/agente/chat/herramientas.py:64-869` | 🟢 |
| Muro de pago | `backend/app/nucleo/agente/chat/servicio_modulos.py:27-112` | 🟢 |
| Runtime (memoria + bucle) | `backend/app/nucleo/agente/chat/runtime.py:56-766` | 🟢 |
| Endpoints + cupo de concurrencia | `backend/app/nucleo/agente/chat/api.py:37-180` | 🟢 |
| Ejecutor del buzón para `tipo='otra'` | `backend/app/nucleo/agente/solicitudes.py:409-488` | 🟢 |
| Permiso `agente:chat` (solo `admin`) | `backend/app/nucleo/permisos.py:18` | 🟢 |

La memoria vive en `nucleo.agente_chat_conversaciones` y
`nucleo.agente_chat_mensajes` (`supabase/migrations/0031_agente_chat_inapp.sql`).
No se reutilizan las tablas del agente WhatsApp ni se alteró `nucleo.solicitudes`.

---

## 2. Endpoints

Prefijo real: `settings.API_V1_PREFIX` + `/nucleo/agente/chat`
(hoy `/api/v1/nucleo/agente/chat`).

### 2.1 `GET /nucleo/agente/chat/agentes`

- **Permiso:** `agente:chat`.
- **Request:** sin body. Empresa por `X-Empresa-ID` (resuelta en servidor).
- **Response 200:**

```json
[
  {
    "clave": "gerente",
    "nombre": "Gerente",
    "configurado": true,
    "herramientas": ["gerente_leer_contexto", "..."]
  }
]
```

`configurado` solo indica si la variable de entorno tiene valor. **Nunca** se
devuelve la clave.

### 2.2 `POST /nucleo/agente/chat`

- **Permiso:** `agente:chat` (deny-by-default). Solo `admin`; `gerente` queda
  excluido junto con el resto de `PERMISOS_AGENTE` (AB-02).
- **Headers:** `Authorization: Bearer <JWT>` + `X-Empresa-ID`.
- **Request** (`extra="forbid"`, `backend/app/nucleo/agente/chat/api.py:74-80`):

```json
{
  "agente": "gerente | secretaria",
  "mensaje": "texto de 1 a 4000 caracteres",
  "conversacion_id": "uuid opcional",
  "clave_idempotencia": "obligatoria, 8 a 128 caracteres"
}
```

No existe `empresa_id` en el body: el tenant sale de `X-Empresa-ID` + membresía.
`clave_idempotencia` es **obligatoria** (SEC-062): la UI envía
`crypto.randomUUID()`; sin ella el backend responde 422 y no crea conversación.

- **Response 200:**

```json
{
  "conversacion_id": "uuid",
  "mensaje_id": "uuid",
  "agente": "gerente",
  "respuesta": "texto del asistente",
  "herramientas": [
    {"nombre": "gerente_upsert_directiva", "estado": "ok|sin_cambios|error|upsell", "resumen": "..."}
  ],
  "upsell": {"modulo": "whatsapp", "mensaje": "..."} 
}
```

`upsell` es `null` si ninguna tool devolvió un módulo inactivo.

- **Idempotencia:** `(empresa_id, clave_idempotencia)` es única en
  `agente_chat_mensajes` (índice parcial de `0031`). Misma clave + mismo cuerpo →
  misma respuesta y **no** se vuelve a llamar al LLM. Misma clave + cuerpo
  distinto → **422** `DATOS_INVALIDOS` (se guarda el hash de `agente+mensaje` en
  `metadata.hash`). La clave es obligatoria (SEC-062).
- **Deduplicación de tools por turno (SEC-062):** si el modelo emite dos
  `tool_call` idénticas (mismo nombre y argumentos canónicos), la tool se ejecuta
  **una sola vez**; el resultado se reutiliza para la segunda llamada y se
  persiste un turno `tool` por cada `tool_call_id` (el proveedor exige respuesta
  para cada id). La deduplicación es por turno, no global: repetir la acción en
  un turno posterior crea estado nuevo.
- **Códigos de error:**

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 401 | — | Sin JWT / JWT inválido (middleware de auth) |
| 403 | `ACCESO_DENEGADO` | Rol sin `agente:chat`, empresa inactiva, sin membresía |
| 404 | `RECURSO_NO_ENCONTRADO` | `conversacion_id` de otra empresa, otro usuario u otro agente |
| 422 | `DATOS_INVALIDOS` | Body inválido, mensaje vacío, clave de idempotencia reutilizada con otro cuerpo, argumentos de tool inválidos |
| 429 | `AGENTE_OCUPADO` | No hay cupo de turnos concurrentes (`AGENTE_CHAT_MAX_CONCURRENT`); no se toca la BD |
| 502 | `AGENTE_LLM_ERROR` | Respuesta ilegible/incompleta del proveedor, argumentos de tool que no son JSON, bucle de tools agotado |
| 503 | `AGENTE_NO_CONFIGURADO` | Falta la API key del agente o el proveedor la rechaza (401/403) |
| 504 | `AGENTE_TIMEOUT` | Timeout del proveedor (`AGENTE_LLM_TIMEOUT_S`) |

Ningún error incluye la API key, el cuerpo crudo del proveedor ni SQL.

### 2.3 `GET /nucleo/agente/chat/{conversacion_id}`

- **Permiso:** `agente:chat`.
- **Response 200:** `{"conversacion": {...}, "mensajes": [...]}` con hasta 100
  turnos ordenados por `created_at, id`.
- **404** si la conversación pertenece a otra empresa, a otro usuario o a otro
  agente. No se revela su existencia.

---

## 3. Agentes y tools

Catálogo: `backend/app/nucleo/agente/chat/personas.py:99-120`.

| Agente | Clave | Modelo | Tools |
|---|---|---|---|
| `gerente` | `GERENTE_API_KEY` | `GERENTE_LLM_MODELO` | `gerente_leer_contexto`, `gerente_upsert_directiva`, `gerente_upsert_regla_entidad`, `gerente_listar_reglas`, `gerente_solicitar_modulo` |
| `secretaria` | `SECRETARIA_API_KEY` | `SECRETARIA_LLM_MODELO` | `secretaria_consultar_viajes`, `secretaria_consultar_solicitudes`, `secretaria_crear_solicitud`, `secretaria_whatsapp_recordatorio` |

Reglas de ejecución (`runtime.py:635-670`):

1. La tool debe existir, estar en la allowlist de la persona y pertenecer a ese
   agente. Si no, se devuelve `error` al modelo sin ejecutar.
2. Si la tool declara `modulo`, se consulta el muro de pago **antes** de ejecutar.
3. Los errores de validación (`DatosInvalidos`, `RecursoNoEncontrado`,
   `AccesoDenegado`) se devuelven al modelo como resultado `error` para que los
   explique. Un error de PostgreSQL propaga y el endpoint hace rollback: no se
   sigue iterando sobre una transacción abortada.

### 3.1 Gerente

- `gerente_leer_contexto`: viajes de los últimos 30 días por estado, configuración
  vigente, reglas abiertas (máx. 50). Solo lectura.
- `gerente_upsert_directiva` (`herramientas.py:250`):
  - **solo** acepta `directiva_[a-z0-9_]{2,60}`;
  - las claves del catálogo (`iva_porcentaje`, `alerta_km_mantenimiento`,
    `dias_alerta_vencimientos`, `dias_alerta_cobranza`) se **rechazan** con 422
    "se cambia por el flujo de configuración, no por el chat" (SEC-051). El
    prompt lo prohíbe, pero el backend es la autoridad;
  - escribe con `actualizar_directiva(..., commit=False)`
    (`servicio_configuracion.py:166`): cierra la vigencia anterior e inserta la
    nueva con el mismo `now()`, valor idéntico = `sin_cambios`. Confirma el
    endpoint del turno;
  - cualquier otra clave → 422.
- `gerente_upsert_regla_entidad` (`herramientas.py:284`): valida entidad
  (`cliente|chofer|tracto|rampla|contacto`), existencia de la entidad **en la
  empresa**, clave `^[a-z][a-z0-9_]{2,63}$` y valor JSON. Cierra la regla abierta
  del mismo destino+clave e inserta la nueva; valor idéntico = `sin_cambios`. No
  toca filas cerradas (la inmutabilidad la impone `0030`).
- `gerente_listar_reglas`: reglas abiertas.
- `gerente_actualizar_catalogo` (`herramientas.py:1974`, SEC-063): es la **única**
  vía del chat para escribir el catálogo cerrado (`iva_porcentaje`, alertas).
  Capacidad `configuracion.escribir_catalogo`, que **nace apagada**; el admin la
  habilita en `/configuracion/agentes` (`GET/PUT
  /nucleo/agente/configuracion`, `api_configuracion.py`). Sin ese opt-in la tool no
  se ofrece al modelo y el runtime no la ejecuta. La escritura queda auditada por
  `trg_config_empresa_audit` (`0026`).
- `gerente_solicitar_modulo`: consulta el muro de pago; si está inactivo devuelve
  `upsell`, si está activo confirma. **No enciende** `modulos_empresa`: el
  endpoint `PUT /nucleo/agente/modulos/{id}` se retiró (SEC-066) y la activación
  queda para el rol de plataforma (RA-16). `tei_app` tampoco puede escribir
  `tenant_suscripciones` desde `0033` (SEC-068).

### 3.2 Secretaria

- `secretaria_consultar_viajes`: 10 viajes recientes + conteo por estado.
- `secretaria_consultar_solicitudes`: hasta 20 solicitudes pendientes.
- `secretaria_whatsapp_recordatorio` (`herramientas.py:508`): tool **premium**
  (`modulo="whatsapp"`). Valida el viaje de la empresa y devuelve
  `{estado:"preparado", enviado:false, canal:"whatsapp", ...}`. **No envía nada**
  (no hay proveedor). Si el módulo no está activo, el runtime la intercepta antes
  de ejecutarla y devuelve `upsell`.
- `secretaria_crear_solicitud` (`herramientas.py:552`):
  - acciones permitidas: `crear_viaje`, `crear_viajes_masivo`, `anular_viaje`,
    `cambiar_tarifa`; otra acción → 422;
  - `crear_viaje` valida con `ViajeCreateNucleo`;
  - `anular_viaje` exige `viaje_id` de la empresa y motivo válido
    (`SolicitudAnulacionViaje`, ≥ 5 caracteres);
  - las otras dos exigen `datos` no vacío;
  - inserta en `nucleo.solicitudes` con `tipo='otra'`,
    `payload={"accion": ..., "datos": ..., "origen": "chat_inapp",
    "agente": "secretaria"}`, el solicitante y una `clave_idempotencia`
    **única por invocación** (`chat-<uuid4>`). La idempotencia de reintentos del
    mismo turno la cubre `agente_chat_mensajes.clave_idempotencia`; repetir la
    misma acción meses después crea una solicitud nueva (SEC-057). El
    `on conflict` se mantiene como red de seguridad;
  - **no ejecuta** la acción. Devuelve `{solicitud_id, estado:"pendiente",
    mensaje:"Requiere aprobación del dueño"}`.

### 3.3 Aprobación de propuestas del chat (SEC-055)

Decisión del dueño (2026-11-02): una solicitud con
`payload.origen="chat_inapp"` puede aprobarla el **mismo** usuario que la pidió,
si su rol tiene `agente:aprobar`. No es autoaprobación de una acción propia: el
proponente es el agente y el humano confirma; además, `admin` ya puede ejecutar
esas acciones por los endpoints normales, así que no gana privilegio nuevo.

- La excepción vive en `_verificar_autoaprobacion`
  (`agente/solicitudes.py:524-555`) y exige `payload.origen == "chat_inapp"` **y**
  `tiene_permiso(contexto.rol, "agente:aprobar")`. Además, SEC-061 endurece el
  predicado (`_es_propuesta_del_chat`, `solicitudes.py:508`): exige
  `tipo='otra'` y que `payload.accion` esté en `ACCIONES_CRITICAS` (el mismo
  catálogo que usa la tool). Un `tipo='hoja_de_ruta'` o una acción inventada no
  heredan la excepción. Cualquier otra autoaprobación sigue en 403.
- La procedencia queda en el payload (`origen`, `agente`) y `aprobado_por` sigue
  siendo `agente:{auth_id}`; no se agregaron columnas.
- **Riesgo residual:** para propuestas del chat aprobadas por el mismo admin se
  pierde la segregación de funciones. Se acepta porque ese admin ya tiene el
  permiso directo; el control sigue vigente para solicitudes creadas fuera del
  chat.

---

## 4. Muro de pago

Catálogo en código (`servicio_modulos.py:27`):

```python
MODULOS = {
  "whatsapp":     {"modulo_id": "agente-whatsapp", "plan_requerido": True},
  "finanzas_pro": {"modulo_id": "finanzas-pro",   "plan_requerido": True},
}
```

Un módulo premium está activo solo si se cumplen **las dos** condiciones:

1. `nucleo.modulos_empresa.habilitado` para `(empresa, modulo_id)`;
2. una `nucleo.tenant_suscripciones` con `estado='activa'`, vigente y
   `plan_codigo` dentro de `AGENTE_PLANES_PREMIUM`.

Si falta cualquiera, la tool no se ejecuta y el runtime devuelve
`{"estado":"upsell","modulo":...,"mensaje":...}`. La tool real afectada es
`secretaria_whatsapp_recordatorio` (`modulo="whatsapp"`); el meta-tool
`gerente_solicitar_modulo` consulta el mismo estado. El estado de cada módulo
también se incluye en el system prompt para que el modelo ofrezca el upsell sin
inventar precios ni planes.

---

## 5. Transacción, locks e idempotencia

- Un turno = una transacción del endpoint (`api.py:146-168`). El runtime no hace
  `commit()` propio.
- La escritura del Gerente también participa de esa transacción:
  `ServicioConfiguracion.actualizar_directiva(..., commit=False)` hace `flush`,
  no `commit` ni `rollback`; confirma el endpoint. Si el LLM falla después, la
  directiva y el turno se revierten juntos. `actualizar` conserva su
  `commit=True` por defecto para el flujo de configuración.
- El turno `user` se inserta con `on conflict (empresa_id, clave_idempotencia) do
  nothing`; una carrera con la misma clave devuelve el turno ya persistido.
- La conversación activa se crea con `on conflict ... where activa do nothing` y
  se relee: dos requests simultáneos no crean dos conversaciones activas
  (garantía de `uq_agente_chat_conv_activa`, `0031`).
- Los mensajes se insertan con `clock_timestamp()`, no con `now()`: dentro de una
  misma transacción `now()` es constante y el orden `user`/`assistant` se perdía.
- El buzón de aprobación reutiliza la transacción del endpoint
  (`agente/api_solicitudes.py:160-174`): `crear_viaje(commit=False)` y
  `anular(commit=False)` hacen `flush`, no `commit` ni `rollback` propios. Si el
  efecto falla, la solicitud queda `pendiente`.

### 5.1 Concurrencia (SEC-053)

La transacción permanece abierta durante las llamadas al LLM (hasta
`AGENTE_LLM_MAX_ITERACIONES × AGENTE_LLM_TIMEOUT_S`). Como mitigación acotada,
el POST usa un `threading.BoundedSemaphore` por proceso inicializado con
`AGENTE_CHAT_MAX_CONCURRENT` (default 4), en `api.py:46-65`:

- el cupo se adquiere con `acquire(blocking=False)` en una dependencia declarada
  **antes** de la autenticación; si no hay cupo, responde **429**
  `AGENTE_OCUPADO` ("El agente está atendiendo otros turnos; reintenta en unos
  segundos.") sin crear conversación ni mensajes;
- se libera en `finally` al terminar el turno (también si el endpoint falla);
- **no** es un rate limit distribuido: cada worker tiene su propio semáforo. El
  riesgo residual (transacción larga + N workers × tope) está declarado en §8.

---

## 6. Amenazas mitigadas

| Amenaza | Mitigación | Evidencia |
|---|---|---|
| Tenant desde el body | No existe `empresa_id`; `extra="forbid"`; empresa desde `X-Empresa-ID` + membresía | `api.py:74-80`, `deps.py:50-102` |
| Conversación de otra empresa/usuario | `where empresa_id` + `usuario_empresa_id` + `agente`; 404 sin revelar existencia | `runtime.py:117-160`, test 8 |
| Tool inventada o de otro agente | Allowlist por persona + `herramienta.agente` | `runtime.py:635-651` |
| Claves reservadas escritas por el Gerente | `directiva_*` por su propia tool; el catálogo cerrado solo por `gerente_actualizar_catalogo`, con capacidad **apagada por defecto** y opt-in del admin | `herramientas.py:95-112,1974`, `capacidades.py:176-186`, SEC-051/063 |
| Módulo premium sin pagar | `modulos_empresa` **y** suscripción activa, interceptado antes de la tool; el tenant no puede encender el flag por HTTP | `servicio_modulos.py:38-112`, `runtime.py:727-736`, SEC-052/066 |
| Historial del chat editable | `tei_app` solo INSERT/SELECT; UPDATE/DELETE revocados en `0033` | `0033_privilegios_tei_app.sql`, SEC-056 |
| Auto-concesión de plan | `tei_app` sin INSERT/UPDATE en `tenant_suscripciones`; solo SELECT | `0033_privilegios_tei_app.sql`, SEC-068 |
| Acción crítica ejecutada por el chat | La secretaria solo inserta en `solicitudes`; el efecto ocurre al aprobar | `herramientas.py:552`, test 5 |
| Doble clic / reintento | Clave de idempotencia del turno (obligatoria, SEC-062); la solicitud usa clave única por invocación (SEC-057) | `runtime.py:484-533`, `api.py:74-80`, tests 2 y SEC-057 |
| Dos `tool_call` idénticas en el mismo turno | Deduplicación por firma `(nombre, argumentos)`; una ejecución y un turno `tool` por id | `runtime.py:552, 578-592`, SEC-062 |
| POST sin `clave_idempotencia` | 422 por `ChatIn`; no crea conversación ni mensajes | `api.py:74-80`, test SEC-062 |
| Agotamiento del pool por turnos largos | Semáforo por proceso + 429 `AGENTE_OCUPADO` antes de la BD | `api.py:46-65`, SEC-053 |
| API key filtrada | Solo viaja en `Authorization`; errores y respuestas con mensajes fijos; `/agentes` devuelve `configurado` | `llm.py:94-166`, tests 10 y `test_agente_chat_llm.py` |
| Prompt injection desde datos | Instrucción explícita de tratar documentos/usuarios como datos | `personas.py:33-49` |
| Folio/estado inconsistentes | `crear_viaje`/`anular` dentro de la transacción del buzón | `servicio_disponibilidad.py:869`, `servicio_transiciones.py:282` |
| Edición de historial de reglas | Solo cierra vigencias abiertas; no toca filas cerradas | `herramientas.py:315-360`, `0030` |

---

## 7. Pruebas

### Unitarias (sin red ni base)

```bash
cd backend && ../.venv/bin/python -m pytest tests/test_agente_chat_llm.py -q
# 21 passed
```

Cubre: Settings/claves/planes, prompts sin claves, parseo de contenido y
`tool_calls`, JSON inválido → 502, 401 → 503, timeout → 504, 5xx → 502, error sin
clave, validadores de acción/entidad/clave (incluido el rechazo del catálogo por
SEC-051), allowlist de la tool premium (SEC-052), 429 de cupo agotado (SEC-053) y
el predicado endurecido de SEC-061 (`tipo='otra'` + acción crítica).

### Integración HTTP (`tei_test`, LLM falso)

```bash
cd backend && \
NUCLEO_TEST_DATABASE_URL="postgresql+psycopg://postgres:postgres@127.0.0.1:54322/tei_test" \
NUCLEO_DATABASE_URL="postgresql+psycopg://tei_app:tei_app@127.0.0.1:54322/tei_test" \
TEST_ADMIN_EMAIL="admin@tei.local" TEST_ADMIN_PASSWORD="TEI2026!" \
../.venv/bin/python -m pytest tests/test_agente_chat_http.py -q
# 24 passed
```

Todo el escenario se crea en una transacción externa que se revierte al final
(`Session(..., join_transaction_mode="create_savepoint")`); al terminar,
`agente_chat_conversaciones`, `agente_chat_mensajes`, empresas `CHAT%`,
directivas y solicitudes de prueba quedan en 0.

Cubre: turno básico, idempotencia, rechazo de POST sin `clave_idempotencia`
(SEC-062), deduplicación de dos `tool_call` idénticas en el mismo turno con dos
turnos `tool` persistidos y una sola solicitud (SEC-062), directiva (ok + no-op),
rechazo de `iva_porcentaje` sin crear fila, regla por entidad (ok + no-op +
entidad de otra empresa), solicitud de anulación + aprobación por el mismo
`admin` (SEC-055), rechazo de autoaprobación sin `origen=chat_inapp`, rechazo de
autoaprobación con acción desconocida o `tipo != 'otra'` (SEC-061), rechazo de un
rol sin `agente:aprobar`, repetición de la misma acción con una solicitud nueva
(SEC-057), creación de viaje + aprobación atómica, paywall del meta-tool y de la
tool premium de WhatsApp (upsell sin ejecutar y `preparado` con suscripción), 404
por empresa y por usuario, 503 sin clave, respuesta sin clave y 429 con el
semáforo agotado sin crear conversación.

### Regresión

```bash
make unit     # 135 passed (la unitaria nueva corre en `make test`)
make test     # 468 passed, 0 skipped
```

---

## 8. Deuda y no verificado

- 🟡 **SEC-057(a) (abierto):** la unicidad de `clave_idempotencia` es por
  **empresa**, no por usuario (`uq_agente_chat_msg_idempotencia` sobre
  `(empresa_id, clave_idempotencia)`). La UI usa UUIDs y el runtime filtra por
  `usuario_empresa_id`, así que una colisión entre usuarios es improbable y falla
  cerrada (502 al no encontrar el turno previo de ese usuario), pero el índice no
  separa por usuario. Cambiarlo exige DDL.
- 🟡 **Riesgo residual SEC-053 (parcial):** la transacción sigue abierta durante
  las llamadas al LLM. El semáforo acota a `AGENTE_CHAT_MAX_CONCURRENT` turnos
  por proceso, pero no protege el pool entre workers. Con varios workers, el peor
  caso es `workers × tope` transacciones largas. Mitigación posterior: bajar el
  timeout, pool dedicado o cola.
- 🟡 **SEC-054 (abierto):** no hay rate limit distribuido por usuario/empresa. El
  semáforo es por proceso y solo evita saturar ese worker; un cliente puede
  repartir carga entre workers. Mitigación posterior: límite en el gateway o en
  Redis.
- 🟡 **SEC-056 (abierto):** el historial de `nucleo.agente_chat_mensajes` es
  append-only **por diseño**, pero `0031` no impone un trigger de inmutabilidad;
  un rol con UPDATE puede editar un turno. No se agregó DDL en esta entrega.
- 🟡 **Riesgo residual SEC-055:** para propuestas del chat aprobadas por el mismo
  `admin` se pierde la segregación de funciones. Se acepta porque el `admin` ya
  puede ejecutar esas acciones directamente; fuera de `origen=chat_inapp` el 403
  por autoaprobación sigue vigente.
- 🟡 No hay presupuesto de tokens ni truncado de la respuesta del modelo; el
  límite es el timeout y `AGENTE_LLM_MAX_ITERACIONES`.
- 🟡 No se probó contra DeepSeek real (prohibido en tests). El cliente se validó
  con `httpx.MockTransport`; una prueba de humo manual requiere una clave en
  `backend/.env`.
- 🟡 `crear_viajes_masivo` y `cambiar_tarifa` se registran en el buzón pero no
  tienen ejecutor: al confirmar responden **501** `TIPO_SIN_EJECUTOR`
  (deliberado; no se deja la solicitud aprobada sin efecto).
- 🟡 El resumen (`nucleo.agente_chat_conversaciones.resumen`) no se compacta
  todavía: la memoria usa los últimos `AGENTE_LLM_MAX_MENSAJES_CONTEXTO`
  mensajes. Compactar es una tarea posterior.
- 🟡 No se auditó fila a fila el chat a propósito (`0031`): el log es append-only
  de diseño. Las escrituras de negocio sí pasan por sus tablas y triggers.
- 🟢 La UI existe en `frontend/src/app/(app)/agente/chat/`; este documento es el
  contrato que consume. No se modificó `frontend/**` en esta entrega.
- 🟡 El `GET /agentes` construye un `ClienteOpenAICompatible` por dependencia, sin
  red; no verifica disponibilidad real del proveedor.
