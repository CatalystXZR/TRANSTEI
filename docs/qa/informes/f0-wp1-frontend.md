# F0-WP1 — Due Diligence Frontend (solo lectura)

> Depositado por el orquestador (2026-10-29): el agente `frontend` no tiene permiso de escritura en `docs/qa/informes/`; el contenido es íntegro de su respuesta. F0 es solo lectura.

**Fecha:** 2026-10-29 · **Agente:** frontend (subagente F0) · **Método:** inventario por grep/lectura, sin modificar archivos (solo se crea este informe).
**Alcance:** `frontend/src/app/**/page.tsx`, clientes HTTP, tipos, estado/UX, auth en cliente.
**Convención de certeza:** 🟢 verificado (comando pegado + archivo:línea) · 🟡 inferido · 🔴 no determinable.

---

## 1. Inventario de pantallas (28 `page.tsx`)

Verificación: `find frontend/src/app -name "page.tsx" | sort` → **28 archivos** (coincide con `docs/estado.md`). Cliente HTTP según import en cada página (🟢):

| # | Ruta | Cliente HTTP | Evidencia (import) |
|---|---|---|---|
| 1 | `/` | — (redirect a `/dashboard`) | `app/page.tsx:4` `redirect("/dashboard")` |
| 2 | `/login` | supabase vía `useAuth` (sin cliente HTTP directo) | `app/login/page.tsx:6` |
| 3 | `/conductor` | nucleo + nucleoFetch + nucleoUpload | `app/conductor/page.tsx:26` |
| 4 | `/dashboard` | **legacy** `api` | `(app)/dashboard/page.tsx:16` |
| 5 | `/tablero` | **núcleo** `nucleo` | `(app)/tablero/page.tsx:19` |
| 6 | `/despacho` | núcleo | `(app)/despacho/page.tsx:21` |
| 7 | `/agenda` | núcleo | `(app)/agenda/page.tsx:15` |
| 8 | `/expediente` | núcleo | `(app)/expediente/page.tsx:14` |
| 9 | `/expediente/[id]` | núcleo + nucleoUpload | `(app)/expediente/[id]/page.tsx:23` |
| 10 | `/viajes` | **legacy** `api` | `(app)/viajes/page.tsx:9` |
| 11 | `/viajes/[id]` | legacy `api` + apiUpload | `(app)/viajes/[id]/page.tsx:20` |
| 12 | `/flota` | legacy | `(app)/flota/page.tsx:6` |
| 13 | `/mantenimiento` | legacy | `(app)/mantenimiento/page.tsx:7` |
| 14 | `/comercial` | núcleo | `(app)/comercial/page.tsx:14` |
| 15 | `/rentabilidad` | núcleo | `(app)/rentabilidad/page.tsx:6` |
| 16 | `/facturacion` | **legacy** | `(app)/facturacion/page.tsx:8` |
| 17 | `/cobranza` | **núcleo** | `(app)/cobranza/page.tsx:13` |
| 18 | `/cobranzas` | **legacy** | `(app)/cobranzas/page.tsx:7` |
| 19 | `/iva` | legacy | `(app)/iva/page.tsx:6` |
| 20 | `/liquidaciones` | legacy | `(app)/liquidaciones/page.tsx:7` |
| 21 | `/maestros` | **núcleo** (`/nucleo/<tab>`) | `(app)/maestros/page.tsx:6` |
| 22 | `/clientes` | **legacy** | `(app)/clientes/page.tsx:6` |
| 23 | `/choferes` | **legacy** | `(app)/choferes/page.tsx:6` |
| 24 | `/kpis` | legacy | `(app)/kpis/page.tsx:7` |
| 25 | `/auditoria` | núcleo | `(app)/auditoria/page.tsx:10` |
| 26 | `/permisos` | núcleo | `(app)/permisos/page.tsx:5` |
| 27 | `/cutover` | núcleo | `(app)/cutover/page.tsx:13` |
| 28 | `/configuracion` | legacy | `(app)/configuracion/page.tsx:7` |

**Totales:** legacy `api` = 13 páginas · núcleo `nucleo` = 13 · sin cliente (login/redirect) = 2. 🟢
No hay `fetch(` directo en ninguna página (grep `fetch\(` sobre `**/page.tsx` → 0 resultados) 🟢; `conductor` usa `nucleoFetch` (`app/conductor/page.tsx:222,286`).

---

## 2. Pantallas duplicadas / solapadas

Todas las listadas conviven **simultáneamente en el menú** (`lib/navigation.ts:44-99`, `NAV_GRUPOS`) con etiquetas explícitas "núcleo"/"legacy" 🟢. No hay una sola "canónica": el layout (`(app)/layout.tsx:32`) renderiza el menú por rol con `gruposParaRol` (`app-shell.tsx:37`).

| Par | Qué hace cada una | Canónica en la práctica | Evidencia |
|---|---|---|---|
| `dashboard` vs `tablero` | `dashboard` (legacy): resumen + alertas + KPIs vía `api` (`/dashboard/resumen`, `/dashboard/alertas`, `/kpis/valores`) — `dashboard/page.tsx:52-54`. `tablero` (núcleo): "Tablero del dueño" vía `nucleo.get<TableroNucleo>` (`tablero/page.tsx:108`). | Ambas en menú; roles distintos (tablero solo admin/contabilidad). **Puerta de entrada es legacy**: `/` → `/dashboard` (`page.tsx:4`). | `navigation.ts:48-49` |
| `cobranza` vs `cobranzas` | `cobranza` (núcleo): resumen+aging (`/nucleo/cobranza/resumen`, `/aging`) — `cobranza/page.tsx:118,122`. `cobranzas` (legacy): solo marcar factura pagada (`api.patch("/facturas/:id/estado",{estado:"pagada"})`) — `cobranzas/page.tsx:96`. | Ambas en menú ("Cobranza núcleo" / "Cobranzas legacy"). | `navigation.ts:75-76` |
| `maestros` vs `clientes`+`choferes`+`flota` | `maestros` (núcleo): tabs `["clientes","tractos","ramplas","choferes"]` → `nucleo.get<Registro[]>("/nucleo/<tab>")` — `maestros/page.tsx:43,100`. `clientes`/`choferes`/`flota` (legacy): CRUD sobre `/clientes`, `/choferes`, `/tractos`, `/ramplas`. | Ambas en menú ("Maestros núcleo" vs "Clientes"/"Choferes"). **Mismo maestro con dos fuentes de verdad simultáneas** (public vs nucleo). | `navigation.ts:84-86` |
| `facturacion` + `cobranzas` | Ambas mutan el **mismo endpoint legacy** `/facturas/:id/estado`: `facturacion/page.tsx:169` (pagada) y `:180` (anulada); `cobranzas/page.tsx:96` (pagada). Solape funcional de una misma acción en dos pantallas. | Ambas en menú. | archivo:línea citadas |
| `viajes` vs `expediente` | `viajes` (legacy): CRUD completo de viajes/gastos (`/viajes`, `/gastos`). `expediente` (núcleo): lista de viajes del núcleo + detalle operativo (`/nucleo/expediente/...`). No es CRUD duplicado; sí son dos vistas de "el viaje" sobre esquemas distintos. | Ambas en menú; `despacho` crea viajes del núcleo (`despacho/page.tsx:299`), `viajes` crea legacy (`viajes/page.tsx:165`). | `navigation.ts:57,59` |

**Conclusión de duplicidad:** la coexistencia es **intencional y visible** (etiquetas en el menú), pero no hay pantalla marcada como deprecada ni indicador de "preferir esta". Riesgo: un operador puede cargar el mismo cliente/chofer en `public` (legacy) y `nucleo` sin advertencia.

---

## 3. Contratos tipados

**Ubicación de tipos compartidos:** `frontend/src/types/index.ts` (225 líneas, 23 interfaces/types) y `frontend/src/types/nucleo.ts` (1.084 líneas, 77 interfaces/types) = **100 tipos declarados** 🟢. Los clientes usan genéricos: `apiFetch<T = unknown>` (`lib/api.ts:5`) y `nucleoFetch<T>` (`lib/nucleo.ts:37`).

**Cero `any` en todo `src`** 🟢: `grep -rn "any" frontend/src --include="*.ts" --include="*.tsx"` → 0 resultados.

**Llamadas tipadas vs sin tipo (genérico cae a `unknown`)** 🟢 (contadores re-ejecutados):

| Cliente | Con `<T>` explícito | Sin tipo explícito (→ `unknown` implícito) |
|---|---|---|
| `api.*` | 31 | 25 |
| `nucleo.*` | 28 | 13 |
| uploads (`apiUpload`/`nucleoUpload`) | 0 | 3 |

Ejemplos sin tipo: `maestros/page.tsx:128` (`nucleo.del`), `expediente/[id]/page.tsx:222,244,273,301,313,330,364` (put/post de paradas, eventos, incidentes, cerrar), `comercial/page.tsx:203,216,227`, `despacho/page.tsx:321`, `agenda/page.tsx:161`, `viajes/[id]/page.tsx:181` (`apiUpload`), `conductor/page.tsx:439`.

---

## 4. Estado y UX

- **Carga:** todas las páginas de datos manejan estado `cargando` + skeleton/spinner (verificado en `despacho/page.tsx:136`, `dashboard/page.tsx:45`; layout con `role="status"` y `sr-only` en `(app)/layout.tsx:21-26`). 🟢
- **Errores:** 21 páginas usan `sonner` (toast). El patrón es `toast.error(e.message)` (`iva/page.tsx:58`, `dashboard/page.tsx:63`). Los mensajes de error de red/dominio no pierden lo digitado en formularios con estado (formularios controlados). 🟢
- **401:** solo se detecta "sin token" en el cliente núcleo: `lib/nucleo.ts:29`. El layout redirige a `/login` cuando `!session` (`(app)/layout.tsx:14-17`), pero **no** hay redirección automática ante un 401 devuelto por la API. 🟢/🟡
- **403:** **no hay manejo diferenciado en ninguna página** 🟢: `grep -rn "403" frontend/src` → solo `nucleo.ts:29` es 401. `NucleoError` lleva `status`/`codigo`/`errores` (`lib/nucleo.ts:5-21`), pero solo 2 páginas consumen `e.errores` (`despacho/page.tsx:308,332`; `expediente/[id]/page.tsx:210`); **ninguna** lee `e.status` ni `e.codigo`. Un 403 del núcleo se muestra como mensaje genérico del backend, indistinguible de un error de red.
- **Doble envío:** despacho y expediente/[id] envuelven mutaciones en helper `ejecutar` que activa `setProcesando(true)` (`expediente/[id]/page.tsx:200-202`). Otros formularios (viajes, facturacion, flota) no muestran un patrón de bloqueo equivalente verificado (🟡 no auditado botón a botón).
- **Idempotencia en cliente:** no se envía `Idempotency-Key` desde el frontend (grep → 0 coincidencias). La garantía queda del lado backend (fuera de alcance F0-frontend). 🟢
- **Accesibilidad básica:** 21/28 páginas usan `<label>`/`htmlFor`; login con `required` + `autoComplete` (`login/page.tsx:42-44,59-61`); componente compartido `formulario.tsx:33` asocia label. 4 componentes con `aria-label` (app-shell, sistema, formulario, pod-panel). **0** `dangerouslySetInnerHTML` 🟢. Dialogs envuelven `@base-ui/react` (`ui/dialog.tsx:4`) — trampa de foco/Esc delegada a Base UI (🟡 no probado en runtime).

---

## 5. Auth en el cliente (solo ubicaciones, sin valores)

- **Clave anon / URL de Supabase:** únicamente en `frontend/src/lib/supabase/client.ts:7-8` (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`) — son públicas por diseño (prefijo `NEXT_PUBLIC_`). **No hay** referencias a `service_role`/`secret` en `frontend/src` (grep → 0) 🟢.
- **Dónde vive el token:** el cliente Supabase se crea **sin** opción `storage`/`persistSession` (`lib/supabase/client.ts:17` `createSupabaseClient(supabaseUrl, supabaseAnonKey)`), por lo que usa el **default de supabase-js: `localStorage`** (🟡 inferido del default de la librería, no hay override explícito).
- **Dónde se usa el token:** `lib/api.ts:10-11,53-54` y `lib/nucleo.ts:27-28` (`supabase.auth.getSession()` por request) → header `Authorization: Bearer` (`api.ts:17`, `nucleo.ts:32`); `auth-context.tsx:38-44` (getSession + onAuthStateChange), `:61` (`/auth/me`), `:80` (signInWithPassword), `:91` (signOut).
- **Multiempresa:** header `X-Empresa-ID` solo en el cliente núcleo (`lib/nucleo.ts:33`), desde la empresa seleccionada, nunca desde el body 🟢. El cliente legacy **no** envía el header (`api.ts:8-20` sin `X-Empresa-ID`) 🟢.
- **Cola PWA conductor:** `localStorage` claves `tei_conductor_cola_v1` y `tei_conductor_ultimo_viaje_v1` (`lib/offline-queue.ts:6-7,20,30`) — datos de viaje, no credenciales. 🟢

---

## 6. Hallazgos

| ID | Severidad preliminar | Hallazgo | Evidencia | Impacto |
|---|---|---|---|---|
| F0F-01 | Media | 5 pares de pantallas solapadas conviven en el menú sin indicador de deprecación ni pantalla canónica marcada; `facturacion` y `cobranzas` mutan el mismo endpoint con la misma acción. | `navigation.ts:44-99`; `facturacion/page.tsx:169` vs `cobranzas/page.tsx:96`; `maestros/page.tsx:43` vs `clientes/page.tsx:6` | Doble fuente de verdad de UI sobre esquemas distintos (public/nucleo); riesgo de operar el maestro equivocado sin advertencia. |
| F0F-02 | Media | El 403 no se distingue de otros errores: ninguna página lee `NucleoError.status`/`codigo`; solo 2 leen `errores`. | grep `403` → 0 en páginas; `lib/nucleo.ts:5-21`; `despacho/page.tsx:308` | Un usuario sin permiso no puede distinguir "no autorizado" de un fallo transitorio; problemas de soporte y auditoría de accesos. |
| F0F-03 | Media | 38 llamadas HTTP (25 api + 13 nucleo) + 3 uploads sin tipo explícito: el genérico cae a `unknown` silenciosamente. Sin `any`, pero el contrato de esas respuestas no se verifica en tiempo de compilación. | contadores §3; `maestros/page.tsx:128`; `expediente/[id]/page.tsx:222-364`; `viajes/[id]/page.tsx:181` | Derivas silenciosas de contrato entre backend y UI en las mutaciones más sensibles (cierre de viaje, gastos, incidentes). |
| F0F-04 | Baja | Fallback `API_URL = http://localhost:8000/api/v1` hardcodeado en ambos clientes si falta `NEXT_PUBLIC_API_URL`. | `lib/api.ts:4`; `lib/nucleo.ts:4` | En un build sin la variable, todo el tráfico apuntaría a localhost. |
| F0F-05 | Baja | Token en `localStorage` (default supabase-js sin override) + `getSession()` por cada request. | `lib/supabase/client.ts:17`; `api.ts:10`; `nucleo.ts:27` | Superficie XSS mayor que httpOnly cookie; latencia extra por request (sin caché de sesión). |
| F0F-06 | Baja | Sin `Idempotency-Key` en el cliente para mutaciones de dinero/estado (facturas, cierres). | grep `idempotency` → 0 | La idempotencia queda solo en backend; un reintento manual/cola offline depende de claves naturales del servidor. |
| F0F-07 | Baja | `/` redirige a `/dashboard` (legacy) como puerta de entrada, mientras el destino estratégico es el núcleo. | `app/page.tsx:4` | Primer pantalla del usuario es el esquema legacy. |
| F0F-08 | Info | Sin pantalla "canónica" declarada para maestro clientes/choferes/flota; documentación de cutover es la única referencia de transición. | `navigation.ts:84-86` | Influye en plan de cutover de pantallas. |

**Positivo verificado 🟢:** 0 `any` en `src` · 100 tipos declarados · `tsc --noEmit` limpio · 0 `dangerouslySetInnerHTML` · anon key solo en `client.ts` (pública) · sin claves de servicio · labels en 21/28 páginas · PWA conductor con cola offline explícita.

---

## 7. Verificación ejecutada

| Comando | Resultado |
|---|---|
| `find frontend/src/app -name "page.tsx" \| wc -l` | 28 |
| `grep -rn "any" frontend/src --include="*.ts" --include="*.tsx" \| wc -l` | 0 |
| `grep -rn "fetch(" frontend/src/app --include="page.tsx"` | 0 |
| `grep -rn "403" frontend/src` | 0 (solo `nucleo.ts:29` con 401) |
| `grep -rni "service_role\|secret" frontend/src` | 0 |
| `grep -rni "idempotency" frontend/src` | 0 |
| `cd frontend && npx tsc --noEmit` | **exit 0**, sin errores 🟢 |
| `npm run lint` | **NO ejecutado** (eslint puede escribir `.eslintcache`; F0 prohíbe artefactos) |
| `npm run build` | **NO ejecutado** (escribe `.next/`) |

---

## 8. No verificado / límites

- 🔴 Comportamiento runtime de auth (redirección 401, renovación de token) y focus-trap de dialogs: requiere sesión + backend real, fuera de alcance solo-lectura.
- 🟡 Persistencia exacta del token en `localStorage`: inferida del default de supabase-js; no se leyó runtime.
- 🔴 Canonicidad funcional de pantallas (cuál usan los usuarios en la práctica): requiere E2E/analítica; solo se acredita lo navegable desde el menú.
- No se leyeron valores de `.env`/`.env.local` (solo ubicaciones). Sin secretos expuestos detectados.
