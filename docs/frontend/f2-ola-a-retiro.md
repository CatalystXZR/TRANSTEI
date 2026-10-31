# Fase 2 — Ola A del retiro legacy: redirecciones y navegación

**Fecha:** 2026-10-31 · **Agente:** `frontend` · **Riesgo:** Medio
**Método:** lectura de código (`archivo:línea`), `next typegen`, `tsc`, `eslint`,
`next build` y smoke HTTP con `next start` en `127.0.0.1:3123`. No se ejecutó E2E
(lo cubre `qa`). Retrocompatible: las URLs legacy siguen respondiendo, ahora con 308.

---

## 1. Tabla de redirecciones (verificada por HTTP real)

| Ruta legacy retirada | Destino | Código | Equivalente en el núcleo |
|---|---|---|---|
| `/dashboard` | `/tablero` | 308 | Tablero del dueño |
| `/viajes` | `/despacho` | 308 | Mesa de despacho |
| `/viajes/[id]` | `/expediente` | 308 | Listado del expediente |
| `/flota` | `/maestros` | 308 | Maestros (recursos) |
| `/clientes` | `/maestros` | 308 | Maestros (clientes) |
| `/choferes` | `/maestros` | 308 | Maestros (personas) |
| `/facturacion` | `/cobranza` | 308 | Cobranza núcleo (emisión) |
| `/cobranzas` | `/cobranza` | 308 | Cobranza núcleo |
| `/kpis` | `/rentabilidad` | 308 | Rentabilidad y score |
| `/` (raíz) | `/tablero` | 307 | Inicio de la aplicación |

Notas de diseño:

- Se usa `permanentRedirect` (`frontend/node_modules/next/dist/docs/01-app/03-api-reference/04-functions/permanentRedirect.md:11,49`):
  308 permanente, ideal para URLs retiradas que no volverán.
- Las páginas de redirección viven en el route group **`(retiradas)`**
  (`frontend/src/app/(retiradas)/…`), **fuera** de `(app)`. Motivo: `(app)/layout.tsx`
  es cliente y sólo renderiza `children` cuando termina de cargar la sesión
  (`frontend/src/app/(app)/layout.tsx:36-48`); un redirect dentro de ese árbol no
  produciría 308 en la petición inicial sino tras hidratar. En `(retiradas)` el 308
  sale del servidor sin autenticar, que es lo que se midió con `curl`.
- `/viajes/[id]` **no** se traduce a `/expediente/<id>`: el id legacy es numérico y el
  del núcleo es UUID, por lo que se redirige al listado
  (`frontend/src/app/(retiradas)/viajes/[id]/page.tsx:4-8`).
- La raíz conserva `redirect()` (307) para no cachear en el navegador el inicio de la
  aplicación; sólo cambió el destino (`frontend/src/app/page.tsx:4`).

## 2. Qué se eliminó

Se borró el código de las 9 pantallas legacy retiradas (**3.627 líneas** de páginas
según `wc -l` previo: 258+473+463+335+336+466+218+579+499), sin tocar `lib/api.ts`:

```text
D frontend/src/app/(app)/choferes/page.tsx
D frontend/src/app/(app)/clientes/page.tsx
D frontend/src/app/(app)/cobranzas/page.tsx
D frontend/src/app/(app)/dashboard/page.tsx
D frontend/src/app/(app)/facturacion/page.tsx
D frontend/src/app/(app)/flota/page.tsx
D frontend/src/app/(app)/kpis/page.tsx
D frontend/src/app/(app)/viajes/[id]/page.tsx
D frontend/src/app/(app)/viajes/page.tsx
```

Cada URL quedó reemplazada por una página mínima de servidor (8–12 líneas) con
`permanentRedirect`, en `frontend/src/app/(retiradas)/`.

## 3. Qué quedó

### Pantallas legacy que se mantienen (Ola B)

`/mantenimiento` · `/liquidaciones` · `/iva` · `/configuracion`
(`frontend/src/app/(app)/{mantenimiento,liquidaciones,iva,configuracion}/page.tsx`),
todas siguen consumiendo `lib/api.ts` (`/api/v1/...`). **`lib/api.ts` no se modificó.**

> **Actualización Ola B (2026-10-31):** esta lista ya no está vigente. Las cuatro
> pantallas fueron reimplementadas con `lib/nucleo.ts` y sus ítems de navegación
> quedaron con `legacy: false`; `RUTAS_LEGACY` está vacía. Ver
> [`f2-ola-b-pantallas.md`](f2-ola-b-pantallas.md). El párrafo se conserva como
> registro del estado al cierre de la Ola A.

### Componentes compartidos

No se borró ningún componente. Los directorios usados por las 4 pantallas restantes y
por el núcleo se conservan:

| Componente | Usado por (verificado con `grep`) |
|---|---|
| `components/maestros/*` | `app/(app)/maestros/page.tsx:34-39` |
| `components/cobranza/*` | `app/(app)/cobranza/page.tsx:41-42` |
| `components/comercial/*` | `app/(app)/comercial/page.tsx:43-46` |
| `components/despacho/*` | `app/(app)/despacho/page.tsx:34` |
| `components/agenda/*` | `app/(app)/agenda/page.tsx:43` |
| `components/rentabilidad/*` | `app/(app)/rentabilidad/page.tsx:21`, `expediente/[id]/page.tsx:55` |
| `components/agente/*` | `app/(app)/agente/buzon/page.tsx:46` |
| `components/expediente/*` | `app/(app)/expediente/[id]/page.tsx:56-57` |
| `components/ui*`, `sistema.tsx`, `formulario.tsx` | transversal |

### Navegación — `frontend/src/lib/navigation.ts`

- Se quitaron los 9 ítems retirados. Quedan **17 ítems en 6 grupos**: 13 del núcleo y
  **4 legacy** (`mantenimiento`, `iva`, `liquidaciones`, `configuracion`)
  (`navigation.ts:42-90`).
- Se conserva el contrato de fase 2: `NavItem.legacy` (`:25-32`), `RUTAS_LEGACY`
  derivada (`:99`), `esRutaLegacy()` (`:102-104`) y el filtro
  `gruposParaRol(rol, esLegacy)` (`:106-117`). Ahora `RUTAS_LEGACY` contiene sólo las 4
  pantallas restantes, por lo que `(app)/layout.tsx:18` sigue bloqueando exactamente
  esas 4 para un usuario `es_legacy === false`.
- Se eliminaron los iconos de `lucide-react` que quedaron sin uso
  (`LayoutDashboard`, `Truck`, `Users`, `UserRound`, `Container`, `FileText`,
  `HandCoins`, `Gauge`).

### Enlaces de inicio

| Archivo | Antes | Ahora |
|---|---|---|
| `frontend/src/app/page.tsx:4` | `/dashboard` | `/tablero` |
| `frontend/src/app/login/page.tsx:30-31` | fallback `/dashboard` | fallback `/tablero` |
| `frontend/src/components/app-shell.tsx:38-40` | `es_legacy === false ? "/despacho" : "/dashboard"` | `es_legacy === false ? "/despacho" : "/tablero"` |

**Discrepancia declarada:** la instrucción pedía `/tablero` para el logo también sin
legacy ("ya se hizo en fase 2"), pero el código de fase 2 usa `/despacho` como home
del núcleo (`docs/frontend/f2-tenant2-navegacion.md:48`). Se mantuvo `/despacho` para
`es_legacy === false` (es el home que fijó la fase 2 y coincide con el aviso
`sin-acceso-legacy`) y se cambió sólo el caso TEI de `/dashboard` a `/tablero`, que es
el enlace que estaba muerto. Si se prefiere `/tablero` para ambos, es un cambio de una
línea en `app-shell.tsx:40`.

## 4. Estados cubiertos

| Estado | Comportamiento |
|---|---|
| URL legacy vigente | 308 al equivalente del núcleo en la **primera** petición (sin montar UI legacy). |
| `/viajes/<id>` | 308 a `/expediente` (no se conserva el id numérico). |
| Sin sesión | El 308 ocurre antes del gate de auth (`(retiradas)` no está bajo `(app)`); tras el redirect la ruta destino pide login si corresponde. |
| `es_legacy === false` en una de las 4 legacy restantes | Sin cambios: `(app)/layout.tsx:26-33` redirige a `/despacho?aviso=sin-acceso-legacy&ruta=…` con `role="alert"`. |
| Rutas inexistentes | Siguen usando el `not-found` de Next (no se creó catch-all). |
| 403 del backend | Sin cambios: las 4 pantallas restantes conservan su manejo previo. |
| Éxito | Las rutas destino se sirven normalmente (`/mantenimiento` → 200 medido). |

## 5. Verificación ejecutada

```text
$ cd frontend && npx tsc --noEmit
(sin salida → 0 errores; antes se ejecutó `npx next typegen` porque `.next/types`
tenía las rutas borradas y el validador generado fallaba con TS2307)
✓ Types generated successfully

$ npm run lint
> eslint
(sin salida → 0 errores)

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Compiled successfully in 1136ms
✓ Generating static pages using 7 workers (30/30)
Rutas: / /agenda /agente/buzon /auditoria /choferes /clientes /cobranza
/cobranzas /comercial /conductor /configuracion /cutover /dashboard /despacho
/expediente /expediente/[id] /facturacion /flota /iva /kpis /liquidaciones /login
/maestros /mantenimiento /permisos /rentabilidad /tablero /viajes /viajes/[id]
```

Smoke HTTP contra `next start -p 3123` (build de producción, sin sesión):

```text
/                 307 -> http://127.0.0.1:3123/tablero
/dashboard        308 -> http://127.0.0.1:3123/tablero
/viajes           308 -> http://127.0.0.1:3123/despacho
/viajes/123       308 -> http://127.0.0.1:3123/expediente
/flota            308 -> http://127.0.0.1:3123/maestros
/clientes         308 -> http://127.0.0.1:3123/maestros
/choferes         308 -> http://127.0.0.1:3123/maestros
/facturacion      308 -> http://127.0.0.1:3123/cobranza
/cobranzas        308 -> http://127.0.0.1:3123/cobranza
/kpis             308 -> http://127.0.0.1:3123/rentabilidad
/mantenimiento    200 -> (sin redirect; pantalla legacy conservada)
```

Búsqueda de enlaces/imports muertos (`frontend/src`):

```text
$ grep -rn 'href="/dashboard\|href="/viajes\|href="/flota\|href="/clientes\|href="/choferes\|href="/facturacion\|href="/cobranzas\|href="/kpis\|"/dashboard"' .
→ ninguno
$ grep -rn '`/\(dashboard\|viajes\|flota\|clientes\|choferes\|facturacion\|cobranzas\|kpis\)' .
→ sólo 2 comentarios (app-shell.tsx:39, (retiradas)/viajes/[id]/page.tsx:4), sin navegación
$ grep -n 'dashboard\|/viajes\|/flota\|/clientes\|/choferes\|/facturacion\|/cobranzas\|/kpis' lib/navigation.ts
→ ninguna
```

`git status --short`: 9 borrados (`D`), 4 modificados (`M`: `login/page.tsx`,
`app/page.tsx`, `app-shell.tsx`, `navigation.ts`) y el grupo `?? app/(retiradas)/`.

## 6. Accesibilidad

- Las páginas de redirección no renderizan UI (308 en el servidor): no introducen
  landmarks, foco ni anuncios nuevos.
- La navegación conserva `aria-label="Navegación principal"`, `aria-current="page"`,
  foco visible y drawer móvil con cierre por `Esc`
  (`frontend/src/components/app-shell.tsx:56-108,158-185`).
- No se agregó `dangerouslySetInnerHTML`, `any` ni un tercer cliente HTTP.

## 7. Handoff

### A `qa` (E2E — obligatorio actualizar)

1. `frontend/e2e/tei.spec.ts:16` espera `toHaveURL(/\/dashboard/)` tras el login:
   **ahora el login aterriza en `/tablero`**. Hay que actualizar el spec.
2. Nuevo escenario de redirecciones: sin sesión, `request.get('/dashboard')` →
   308 `location: /tablero`; `request.get('/viajes')` → 308 `/despacho`;
   `request.get('/viajes/1')` → 308 `/expediente`; `/flota|/clientes|/choferes` →
   `/maestros`; `/facturacion|/cobranzas` → `/cobranza`; `/kpis` → `/rentabilidad`.
   Nota: con `page.goto()` Playwright sigue el redirect y la URL final es el destino.
3. Menú TEI admin: 17 ítems (13 núcleo + mantenimiento, IVA, liquidaciones,
   configuración); ya **no** aparecen Panel de control, Viajes, Flota, Facturación,
   Cobranzas, Clientes, Choferes ni Indicadores.
4. Menú TEI operación: sin Tablero, IVA, liquidaciones, cutover ni configuración.
5. Tenant 2 (`es_legacy = false`): las 4 legacy restantes siguen redirigiendo a
   `/despacho?aviso=sin-acceso-legacy&ruta=…`; en cambio `/dashboard`, `/viajes`, etc.
   ya no muestran el aviso: redirigen directo al equivalente del núcleo.
6. Regresión de las 4 pantallas legacy restantes (`/mantenimiento`, `/liquidaciones`,
   `/iva`, `/configuracion`) con usuario TEI.

### A `auditor-seguridad`

- El 308 de las rutas retiradas ocurre **antes** de la autenticación (grupo
  `(retiradas)` fuera de `(app)`): confirma que sólo revela el mapeo de URLs, ya
  público, y no datos ni permisos.
- Verificar que `lib/api.ts` (legacy) sigue siendo el único cliente de las 4 pantallas
  restantes y que no quedó ninguna página legacy montable tras el retiro.

## 8. Riesgos y no verificado

| Nivel | Punto |
|---|---|
| 🟡 | **No se ejecutó E2E ni un flujo autenticado real** (sin credenciales ni Supabase local en esta sesión). La evidencia es build + smoke HTTP sin sesión con el servidor de producción. |
| 🟡 | `/` responde 307 (temporal) y no 308: intencional para no cachear el inicio; si se quiere permanente, cambiar a `permanentRedirect` en `app/page.tsx`. |
| 🟡 | Los 308 son permanentes: un navegador que los cachee no volverá a consultar la URL legacy aunque se revierta el retiro. Aceptable para rutas retiradas; documentado. |
| 🟡 | `types/index.ts` conserva tipos usados sólo por las pantallas borradas (p. ej. `ResumenDashboard`); no hay error de `tsc`/lint y se dejan para no ampliar el diff, pero son deuda de limpieza. |
| 🔴 | El helper `components/aviso-sin-legacy.tsx` sigue usando `tituloDeRuta`; para las rutas retiradas ya no habrá aviso (no pasan por `esRutaLegacy`) — comportamiento esperado, no cubierto por prueba automatizada todavía. |
