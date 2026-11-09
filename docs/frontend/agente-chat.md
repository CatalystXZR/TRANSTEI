# Chat in-app del agente — contrato de UI

**Fecha:** 2026-11-02 · **Rol:** `frontend` · **Riesgo:** Medio (pantalla nueva sobre endpoints existentes)
**Alcance:** `frontend/src/app/(app)/agente/chat/page.tsx`,
`frontend/src/components/agente/chat-panel.tsx`,
`frontend/src/types/agente-chat.ts`, `frontend/src/lib/navigation.ts` y este
documento. No se modificó `frontend/src/lib/nucleo.ts`, backend, migraciones ni E2E.
**Método:** lectura del contrato en `backend/app/nucleo/agente/chat/api.py:37-143`
y `docs/backend/agente-chat-inapp.md`; verificación con `tsc --noEmit` y
`npm run lint` (salidas en §9). No hubo backend con claves ni datos para probar el
flujo real (§10).

---

## 1. Ruta, clientes y composición

| Elemento | Valor |
|---|---|
| Ruta | `/agente/chat` (`frontend/src/app/(app)/agente/chat/page.tsx`) |
| Tipo | Client Component (`"use client"`), App Router |
| Cliente HTTP | `@/lib/nucleo` → `nucleo.get` / `nucleo.post` (`X-Empresa-ID` + JWT) |
| Empresa/permisos | `useNucleoEmpresa()` (`/nucleo/mis-empresas`, `/nucleo/permisos/mios`) |
| Lógica de chat | `frontend/src/components/agente/chat-panel.tsx` |
| Tipos del contrato | `frontend/src/types/agente-chat.ts` |
| Navegación | Grupo **General**, ítem `Chat con agentes`, `roles: ["admin"]` |

La página resuelve empresa y permisos. El panel de chat solo se monta con
`empresaId`. Si el usuario no tiene empresa, se muestra el aviso existente
(`ErrorNucleo` con el error del hook o el texto "El usuario no tiene una empresa
activa asignada."). Si los permisos cargaron y no incluyen `agente:chat`, se
muestra un aviso explícito de falta de permiso; el backend sigue siendo la
autoridad.

> Nota de navegación: el contrato de tarea pedía el ítem en **General**, "junto a
> Buzón del agente". En `navigation.ts` el buzón vive en **Operación**
> (`frontend/src/lib/navigation.ts:52`). Se agregó el chat a **General**
> (`navigation.ts:43`) sin mover el buzón, para no alterar una agrupación
> existente fuera del alcance.

---

## 2. Endpoints y contrato usado

### 2.1 `GET /nucleo/agente/chat/agentes`

Response 200 (`AgenteChatNucleo[]`):

```ts
{ clave: "gerente" | "secretaria"; nombre: string; configurado: boolean; herramientas: string[] }
```

`configurado` es la única señal de disponibilidad de clave. La UI **nunca**
muestra ni solicita la API key. Si es `false`: badge "Sin API key", aviso
"El agente no tiene API key configurada en el servidor" y composer/enviar
deshabilitados para ese agente.

### 2.2 `POST /nucleo/agente/chat`

Request (`ChatEnvioNucleo`):

```ts
{
  agente: "gerente" | "secretaria";
  mensaje: string;                    // 1..4000
  conversacion_id?: string | null;
  clave_idempotencia?: string | null; // 1..120
}
```

Response 200 (`ChatRespuestaNucleo`):

```ts
{
  conversacion_id: string;
  mensaje_id: string;
  agente: string;
  respuesta: string;
  herramientas: { nombre: string; estado: string; resumen: string }[];
  upsell: { modulo: string; mensaje: string } | null;
}
```

No se envía `empresa_id` en el body: el tenant sale de `X-Empresa-ID`.

### 2.3 `GET /nucleo/agente/chat/{conversacion_id}`

Response 200 (`HistorialChatNucleo`): `{ conversacion, mensajes }` con hasta 100
turnos. La UI usa este endpoint en el botón **Actualizar** cuando ya existe una
conversación. `ConversacionChatNucleo` replica `id, agente, activa, abierta_en,
cerrada_en, resumen, resumen_en, version`.

**Discrepancia de contrato detectada (reportada, no silenciada):** el contrato de
la tarea indicaba `created_at` para los mensajes, pero el backend devuelve
`creado_en` (`backend/app/nucleo/agente/chat/api.py:73-81`, mapeado desde
`created_at` en `runtime.py:250-260`). También devuelve `metadata`, que no estaba
en el brief. Los tipos y la UI usan los nombres reales:

```ts
interface MensajeChatNucleo {
  id: string;
  rol: string;
  contenido: string | null;
  tool_calls: unknown;              // no se interpreta ni se muestra
  tool_call_id: string | null;
  nombre_herramienta: string | null;
  metadata: Record<string, unknown>; // herramientas/upsell/usage
  creado_en: string | null;
}
```

Si el dueño del contrato prefiere `created_at`, debe cambiarlo el backend; el
frontend no inventa el campo.

### 2.4 Fechas

`creado_en` es `timestamptz` serializado. Se muestra con
`formatFechaHora` de `@/lib/format`, que fija `America/Santiago`. No se
reinterpreta la hora.

---

## 3. Mapa de errores de dominio → UI

`NucleoError` entrega `status` y `codigo`; la UI no muestra el texto crudo del
proveedor. Todos los errores de envío se anuncian con `role="alert"`.

| HTTP / `codigo` | Título UI | Mensaje UI | Acción ofrecida |
|---|---|---|---|
| 401 | Sesión expirada | "Su sesión expiró. Vuelva a iniciar sesión para continuar." | Iniciar sesión (`/login?next=/agente/chat`) |
| 403 `ACCESO_DENEGADO` | Sin permiso | **"Tu rol no permite usar el chat."** | Ninguna |
| 503 `AGENTE_NO_CONFIGURADO` | Agente sin configurar | **"Falta configurar la API key del agente en el servidor."** | Reintentar |
| 504 `AGENTE_TIMEOUT` | El agente tardó demasiado | **"El agente tardó demasiado; reintenta."** | Reintentar |
| 502 `AGENTE_LLM_ERROR` | Falla del proveedor | **"El proveedor del agente falló."** | Reintentar |
| 404 `RECURSO_NO_ENCONTRADO` | Conversación no disponible | "La conversación ya no está disponible para esta empresa. Inicia una conversación nueva." | Nueva conversación |
| 422 `DATOS_INVALIDOS` | Mensaje no procesado | "El mensaje no se pudo procesar. Revisa el texto e inténtalo de nuevo." | Ninguna |
| Otro 5xx | No se pudo completar la operación | "El servidor devolvió un error. Reintenta en unos momentos." | Reintentar |
| Error de red (no `NucleoError`) | Sin conexión | "No se pudo conectar con el servidor. Revise su conexión y reintente; si el mensaje falló, se reutiliza la misma clave de idempotencia." | Reintentar |

Un 403 se muestra como falta de permiso, nunca como "sin datos". El estado de
carga de agentes con 403 reemplaza el panel completo; el 403 de envío se muestra
sobre el composer.

---

## 4. Matriz de estados

| Estado | Qué muestra la UI |
|---|---|
| Carga inicial (empresa/permisos) | Skeleton en `Panel` con `aria-busy="true"` y texto `sr-only` |
| Carga de agentes | Skeleton con `aria-busy="true"` |
| Error de carga de agentes | Aviso (crítico/atención) + Reintentar/Iniciar sesión según el error |
| Sin agentes | `EstadoVacio` "No hay agentes disponibles" + Reintentar |
| Agent select | Radio cards `gerente`/`secretaria`, descripción corta y badge Configurado/Sin API key |
| Agente sin `configurado` | Aviso "El agente no tiene API key configurada en el servidor"; composer y botón deshabilitados |
| Conversación vacía | `EstadoVacio` "Sin mensajes todavía" + invitación a escribir |
| Esperando respuesta | Burbuja del usuario "Enviando…" + "El agente está respondiendo…" (`role="status"`); `aria-busy` en el log |
| Éxito | Se agrega el turno usuario (derecha) + respuesta (izquierda); se limpia el composer y el estado `pendiente` |
| Respuesta con herramientas | `<details>` "Herramientas del turno (N)" con un chip por herramienta: nombre, estado y resumen |
| Respuesta con upsell | Tarjeta destacada (marca) "Módulo {modulo}" + mensaje; no se muestra como error |
| Error de envío | Aviso sobre el composer, texto conservado; acción según la tabla §3 |
| Selección de agente durante envío | Radios deshabilitados para no mezclar el turno con otro agente |
| Cambio de agente | Hilo independiente por agente; el `conversacion_id` de un agente no se envía al otro |
| Historial | Botón **Actualizar** llama `GET /{conversacion_id}` y reemplaza los mensajes del hilo actual |
| Conversación nueva | Botón limpia el hilo del agente actual, la clave pendiente y los errores; conserva el borrador |

---

## 5. Idempotencia

- Cada envío genera `crypto.randomUUID()` en `clave_idempotencia`.
- Al fallar (red, 502/503/504, etc.) se guarda `{ agente, mensaje, clave }` en
  `pendiente`. Un reintento con **el mismo texto y el mismo agente** reutiliza la
  clave; un texto distinto genera una clave nueva.
- `onChange` del textarea invalida `pendiente` cuando cambia el contenido que
  se envía (comparación con `trim()`, igual que el body). Cambiar de agente no
  reutiliza una clave de otro agente (`pendiente.agente` se compara).
- El doble envío se bloquea con `enviando`, el botón deshabilitado y el textarea
  deshabilitado. La garantía real es del backend
  (`(empresa_id, clave_idempotencia)` único); la UI solo evita el doble clic.
- Un 404 no se reintenta automáticamente: se ofrece **Nueva conversación**.

---

## 6. Permisos y multiempresa

- El ítem de navegación solo se muestra a `admin`; ocultarlo no autoriza.
- La página usa `useNucleoEmpresa()`: envía `X-Empresa-ID` a través de
  `nucleo.get/post`, nunca a mano por pantalla.
- La UI guía con `permisos.includes("agente:chat")`, pero cada endpoint vuelve a
  validar y un 403 se muestra explícito.
- No se muestran ni piden claves de API. No hay `dangerouslySetInnerHTML`; el
  contenido del agente se renderiza como texto de React (escapado).

---

## 7. Accesibilidad

- Selector: `fieldset` + `legend` "Agente"; radios nativos (teclado), con
  `focus-within` visible en la tarjeta.
- Composer: `label htmlFor="chat-mensaje"`, `aria-describedby` a ayuda y contador,
  `maxLength=4000`, contador visible.
- Teclado: `Enter` envía, `Shift+Enter` inserta salto de línea; se ignora
  `Enter` durante composición IME.
- Log de mensajes: `role="log"`, `aria-live="polite"`,
  `aria-relevant="additions text"`, `aria-label` con el agente.
- Errores: `role="alert"`; estado de espera con `role="status"`.
- Botones con texto visible; iconos decorativos con `aria-hidden`.
- Scroll al final tras cada cambio de mensajes/estado (`scrollIntoView`).
- No se usa color como único indicador: los estados llevan texto y badge.

---

## 8. Captura textual de estados implementados

```text
Agente
  ( ) Gerente        [Sin API key]
      Revisa el contexto del negocio y ajusta directivas o reglas por entidad.
  (•) Secretaria     [Configurado]
      Consulta viajes y solicitudes, y prepara acciones para tu aprobación.

  [El agente no tiene API key configurada en el servidor]
  Un administrador debe configurar la clave en el servidor. Esta pantalla
  nunca muestra ni solicita API keys.

Conversación con Gerente                     [Sin API key] [Nueva conversación]
  Sin mensajes todavía
  Escribe el primer mensaje para Gerente.

  Tú (derecha): "¿Cómo van los viajes de la semana?"
  Gerente (izquierda): "Hay 12 viajes en ruta…"
    > Herramientas del turno (1)
      gerente_leer_contexto   [OK]
      Viajes de los últimos 30 días por estado.

  [Módulo whatsapp]
  El módulo WhatsApp no está activo en tu plan…

  [Error] Falta configurar la API key del agente en el servidor. [Reintentar]
  Mensaje para Gerente
  [textarea deshabilitado]
  0 / 4000
  [Enviar deshabilitado]
```

---

## 9. Verificación ejecutada

```bash
cd frontend
PATH="/opt/homebrew/opt/node@22/bin:$PATH" node_modules/.bin/tsc --noEmit
# salida vacía · EXIT:0

PATH="/opt/homebrew/opt/node@22/bin:$PATH" npm run lint
# > frontend@0.1.0 lint
# > eslint
# salida vacía · EXIT:0

PATH="/opt/homebrew/opt/node@22/bin:$PATH" npm run build
# ▲ Next.js 16.4.3 (Turbopack)
# ✓ Compiled successfully in 1203ms
# ✓ Generating static pages using 7 workers (31/31)
# Route (app) incluye: ○ /agente/chat
# BUILD_EXIT:0
```

No se ejecutó E2E ni una prueba manual del flujo real: requiere backend levantado
y claves de agente (§10).

---

## 10. Handoff y no verificado

**Para `qa` (E2E, cuando haya backend con claves):**

1. Admin entra a `/agente/chat`; ve dos agentes. Si falta la clave de uno, el
   badge dice "Sin API key" y el envío está deshabilitado.
2. Enviar "hola" con Enter: aparece burbuja del usuario y respuesta del agente;
   el composer queda vacío y el contador en 0.
3. `Shift+Enter` agrega línea y no envía.
4. Respuesta con tool: abrir "Herramientas del turno" y ver nombre/estado/resumen.
5. Forzar upsell (módulo inactivo) y verificar tarjeta destacada, no error.
6. Simular 503/504/502 (sin clave, timeout, proveedor caído) y comparar el texto
   con §3.
7. Reintentar el mismo texto tras error de red: no debe duplicar el turno en
   `nucleo.agente_chat_mensajes` (misma `clave_idempotencia`).
8. Cambiar texto tras un error: debe generarse otra clave y no reutilizar la
   anterior.
9. Usuario no admin: el ítem no aparece en el nav; por URL directa recibe aviso de
   permiso/403, no "sin datos".
10. Cambiar de agente y volver: cada hilo conserva su `conversacion_id`; no se
    cruzan mensajes entre agentes.
11. `GET /{conversacion_id}` con "Actualizar": los mensajes se recargan y los
    chips de herramientas se reconstruyen desde `metadata.herramientas`.

**No verificado 🔴:**

- Flujo real contra el backend y un proveedor LLM: no hay entorno con claves en
  esta sesión; no se ejecutó E2E ni prueba manual.
- Persistencia del hilo al recargar la página: el backend no expone un listado de
  conversaciones; la UI solo conserva el hilo en memoria y puede recargarlo
  mientras tenga `conversacion_id`. Al recargar el navegador se empieza una
  conversación nueva (el servidor creará/retomará la activa al enviar).
- La discrepancia `created_at` vs `creado_en` requiere confirmación del dueño del
  contrato de backend.
