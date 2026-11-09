> ⚠️ **Aviso de vigencia (2026-11-01):** cita archivos/cifras anteriores al retiro del legacy (`public`, `lib/api.ts`, `backend/app/api/routes/*`, `kpi_engine.py`). No citar como estado actual; ver `docs/estado.md` §2–§6 y `docs/PLAN_DESARROLLO.md`.

# Fase 2 — Onboarding del segundo tenant: navegación sin legacy

**Fecha:** 2026-10-31 · **Agente:** `frontend` · **Riesgo:** Medio
**Método:** lectura de código (`archivo:línea`), `tsc`, `eslint`, `next build` y smoke HTTP
contra el entorno local. La prueba manual del flujo con usuario del tenant 2 **no** se
ejecutó (ver §8).

---

## 1. Contrato usado

| Elemento | Fuente verificada |
|---|---|
| `GET /api/v1/auth/me` → `{ id, nombre, email, rol, es_legacy }` | `backend/app/api/routes/auth.py:12-28`, `backend/app/schemas/__init__.py:8-14` 🟢 |
| `es_legacy` = membresía activa en `LEGACY_EMPRESA_ID` | `backend/app/api/routes/auth.py:25-27`, `backend/app/core/security.py:70-94`, `backend/app/core/config.py:31` 🟢 |
| Sin membresía TEI: `/api/v1/<legacy>` → **403** `{"codigo":"LEGACY_SOLO_TEI","detail":…}` | `backend/app/main.py:160-175` (ruta legacy), `:191-200` (cuerpo), `:233-265` (`GateLegacyMiddleware`) 🟢 |
| `/api/v1/nucleo/*` y `/api/v1/auth/*` exentos del gate | `backend/app/main.py:157,172-174` 🟢 |

Cliente HTTP: **legacy** `frontend/src/lib/api.ts` (pantallas legacy) y **núcleo**
`frontend/src/lib/nucleo.ts` (pantallas del núcleo). Este cambio no crea clientes nuevos.

### Tipos (frontend)

```ts
// frontend/src/types/index.ts:3-19
interface Usuario {
  id: string; nombre: string; email: string | null;
  rol: "admin" | "operacion" | "contabilidad";
  es_legacy: boolean; // true = puede operar el legacy monoempresa
}
```

El borde de red tolera un backend sin el flag: `PerfilApi` lo declara opcional y
`normalizarPerfil` convierte `undefined → true` (`frontend/src/context/auth-context.tsx:14,29-41`).
Regla: **la ausencia de dato nunca habilita legacy**.

## 2. Cambio implementado

| Archivo | Qué hace |
|---|---|
| `frontend/src/types/index.ts:3-19` | `Usuario.es_legacy: boolean` documentado con su semántica. |
| `frontend/src/context/auth-context.tsx:14,33-41` | Tipo de borde + normalización `undefined → true`. |
| `frontend/src/context/auth-context.tsx:66-102` | `/auth/me` sigue siendo la fuente; guarda `{ userId, usuario }`. |
| `frontend/src/context/auth-context.tsx:104-105` | `usuario` y `perfilCargando` **derivados** de la sesión (descarta perfil de otra sesión, sin `setState` en efectos). |
| `frontend/src/lib/navigation.ts:35-44` | `NavItem.legacy: boolean`; los 12 ítems legacy quedan marcados (`:54,66-68,81,83-85,92-93,99,103`). |
| `frontend/src/lib/navigation.ts:110-120` | `RUTAS_LEGACY` derivada de la navegación + `esRutaLegacy(pathname)` (coincidencia por segmento). |
| `frontend/src/lib/navigation.ts:122-133` | `gruposParaRol(rol, esLegacy = true)` filtra por rol **y** por legacy; grupos vacíos se omiten. |
| `frontend/src/components/app-shell.tsx:37-38` | El menú usa `gruposParaRol(usuario.rol, usuario.es_legacy)`; el logo enlaza a `/despacho` si no hay legacy (evita un enlace muerto a `/dashboard`). |
| `frontend/src/app/(app)/layout.tsx:11-18` | `sinLegacy` + `rutaBloqueada` (`es_legacy === false` & ruta legacy). |
| `frontend/src/app/(app)/layout.tsx:26-33` | Redirección a `/despacho?aviso=sin-acceso-legacy&ruta=<ruta>`. |
| `frontend/src/app/(app)/layout.tsx:36-48` | No monta la pantalla mientras `/auth/me` está en vuelo (`role="status"`). |
| `frontend/src/app/(app)/layout.tsx:50-67` | Estado explícito **sin permiso** (403) mientras redirige; los `children` legacy **nunca** se montan. |
| `frontend/src/components/aviso-sin-legacy.tsx:15-34` | Aviso en la mesa de despacho (`role="alert"`), nombra la pantalla solicitada vía `tituloDeRuta`. |
| `frontend/src/app/(app)/despacho/page.tsx:3,35,347-349` | Render del aviso dentro de `<Suspense>` (requisito de `useSearchParams` en Next 16). |

## 3. Pantallas por tenant

Clasificación: 12 pantallas legacy (consumen `lib/api.ts` → `/api/v1/...`) y 13 del
núcleo (`lib/nucleo.ts` → `/api/v1/nucleo/...`). Verificación mecánica: la lista de
páginas que importa `@/lib/api` coincide 1:1 con `legacy: true` en `navigation.ts`
(salvo `/viajes/[id]`, cubierta por prefijo `/viajes`).

### Legacy (ocultas si `es_legacy === false`)
`/dashboard` · `/viajes` (+ `/viajes/[id]`) · `/flota` · `/mantenimiento` ·
`/facturacion` · `/cobranzas` · `/iva` · `/liquidaciones` · `/clientes` ·
`/choferes` · `/kpis` · `/configuracion`

### Núcleo (visibles según rol, siempre)
`/despacho` · `/agenda` · `/expediente` · `/agente/buzon` · `/conductor` · `/comercial` ·
`/rentabilidad` · `/cobranza` · `/maestros` · `/tablero` · `/auditoria` · `/permisos` ·
`/cutover`

### Resultado por caso

| Usuario | Menú resultante |
|---|---|
| TEI (`es_legacy = true`) | Sin cambios: 25 ítems (12 legacy + 13 núcleo), `legacy` sigue el filtro de rol de siempre. |
| Tenant 2 admin (`admin2@tei.local`) | 13 ítems: tablero, despacho, agenda, expediente, agente/buzon, conductor, comercial, rentabilidad, cobranza, maestros, auditoria, permisos, cutover. |
| Tenant 2 operación (`despacho2@tei.local`) | 10 ítems en 5 grupos (General queda vacío y se omite: solo tenía Panel de control): despacho, agenda, expediente, conductor, comercial, rentabilidad, cobranza, maestros, auditoria, permisos. |
| Sin sesión | `useAuth` sin usuario → menú vacío y layout redirige a `/login?next=…` (comportamiento previo intacto). |
| `es_legacy` ausente (backend viejo) | Se trata como `true` (TEI): no se oculta nada y el backend sigue bloqueando con 403. |

## 4. Estados cubiertos

| Estado | Comportamiento |
|---|---|
| Cargando sesión | Loader `role="status"` (preexistente). |
| Perfil en vuelo | Loader; **no** se montan children legacy (`layout.tsx:36-48`). |
| Sin sesión | `router.replace('/login?next=…')` (`layout.tsx:20-24`). |
| 403 pantalla legacy | Estado "Sin permiso para esta pantalla" con `role="alert"` + redirección a `/despacho` con aviso (`layout.tsx:26-33,50-67`). |
| Error de red al pedir `/auth/me` | `usuario = null`, no se bloquea (no se puede afirmar el tenant); el backend responde 403 y la página legacy muestra el `detail` del servidor. Limitación declarada en §8. |
| Éxito | Menú coherente con el flag; sin parpadeo del menú legacy (el perfil se espera antes de renderizar `AppShell`). |
| Vacío | Un grupo sin ítems visibles no se pinta (`navigation.ts:127-133`). |

## 5. Permisos y multiempresa

- El ocultamiento es **guía de UI**; la autorización real es `GateLegacyMiddleware`
  (`backend/app/main.py:233-265`) → 403 `LEGACY_SOLO_TEI`.
- No se usa ni se envía `X-Empresa-ID` en este cambio; los clientes siguen siendo
  `lib/api.ts` (legacy) y `lib/nucleo.ts` (núcleo).
- No se agregaron dependencias, ni cambios de contrato, ni terceras fuentes de datos.

## 6. Accesibilidad

- Aviso con `role="alert"` (anuncio al montar) y texto explícito "Sin permiso".
- Pantalla bloqueada: `role="alert"`, `h1`, spinner `aria-hidden`, mensaje de redirección.
- Loader: `role="status"` + texto `sr-only` (preexistente).
- Navegación: se conservan `aria-current="page"`, `aria-label="Navegación principal"`,
  foco visible de los `Link` y el drawer móvil con trampa de foco/`Esc` del diálogo previo.
- La información no depende solo del color (icono `ShieldAlert` + texto).
- El estado no se deriva de HTML del query string: `ruta` solo se usa para buscar una
  etiqueta en la navegación (sin `dangerouslySetInnerHTML`).

## 7. Verificación ejecutada

```text
$ cd frontend && npx tsc --noEmit
(sin salida → 0 errores)

$ npm run lint
> eslint
(sin salida → 0 errores)

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Compiled successfully in 918ms
✓ Generating static pages using 7 workers (30/30)
(las 30 rutas se generan; /expediente/[id] y /viajes/[id] dinámicas)

$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/despacho   → 200
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/dashboard  → 200
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/login      → 200
```

Cobertura legacy vs navegación (⚠️ diferencia esperada por la ruta dinámica):

```text
páginas con lib/api: /choferes /clientes /cobranzas /configuracion /dashboard
  /facturacion /flota /iva /kpis /liquidaciones /mantenimiento /viajes /viajes/[id]
ítems legacy:        (las 12 anteriores)
diff → solo "/viajes/[id]" (cubierta por prefijo /viajes)
```

## 8. Riesgos y no verificado

| Nivel | Punto |
|---|---|
| 🔴 | **Flujo real con usuario del tenant 2 no ejecutado**: no se corrió `scripts/seed_segundo_tenant.py` (requiere autorización de seed) ni se dispone de credenciales de sesión; no se afirma funcionamiento de extremo a extremo. Lo cubre `qa` (§9). |
| 🟡 | Si `/auth/me` falla (red/500), no hay bloqueo de UI porque el tenant es desconocido; la garantía queda en el backend (403). Se prefirió no romper la app de TEI por un fallo de perfil. |
| 🟡 | `/` (`app/page.tsx:3-5`) y el login (`app/login/page.tsx:30-31`) siguen apuntando a `/dashboard` por defecto: un usuario sin legacy hace una redirección extra a `/despacho?aviso=…`. Es intencional para no cambiar el inicio de TEI. |
| 🟡 | `lib/api.ts:23-33` no expone `codigo` (solo `detail`). Si una pantalla legacy se montara igual, el mensaje sería el `detail` del backend, no un mapeo por código. Deuda del cliente legacy, fuera de alcance. |
| 🟡 | El flag `rol` del `/auth/me` sigue siendo el rol legacy (`public.usuarios`); los roles del núcleo (`despacho`, etc.) no se usan para filtrar el menú. Sin cambios en esta fase. |
| 🟡 | `RUTAS_LEGACY` se deriva de `NAV_GRUPOS`: una pantalla legacy nueva sin entrada de navegación no quedaría bloqueada en cliente (el backend sí la bloquea). |

## 9. Handoff

### A `qa` (E2E)

1. **Tenant 2 admin**: login `admin2@tei.local` → `/dashboard` → URL final
   `/despacho?aviso=sin-acceso-legacy&ruta=%2Fdashboard`; aviso "Sin permiso para el
   sistema legacy" visible y anunciado; menú con 13 ítems; **ningún** enlace legacy.
2. **Tenant 2 operación**: login `despacho2@tei.local` → menú sin "General" y sin
   legacy (10 ítems); `/tablero` por URL directa → 403 de backend (`/api/v1/...`) o
   pantalla de permiso del núcleo según rol.
3. **URL directa**: con sesión tenant 2, entrar a `/viajes`, `/dashboard`, `/facturacion`:
   la pantalla legacy no monta, se redirige a despacho y el aviso nombra la pantalla.
4. **TEI**: login usuario TEI → `/dashboard` normal, 25 ítems, sin aviso ni redirección.
5. **Sin sesión**: `/viajes` → `/login?next=%2Fviajes`; tras login TEI vuelve a `/viajes`.
6. **Backend**: `GET /api/v1/viajes` con token tenant 2 → 403 `LEGACY_SOLO_TEI`
   (aunque la UI ya no lo permita).
7. Regresión: menú por rol de TEI (admin/operación/contabilidad) sin cambios.

### A `auditor-seguridad`

- El ocultamiento es solo UX; validar que `GateLegacyMiddleware` cubre **todos** los
  verbos y rutas legacy (`backend/app/main.py:160-175`) y que `/nucleo` + `/auth`
  quedan exentos a propósito.
- Confirmar que `es_legacy` no habilita nada por sí mismo (solo informa).
