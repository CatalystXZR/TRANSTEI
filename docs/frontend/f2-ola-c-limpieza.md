# Fase 2 — Ola C: limpieza del cliente legacy en el frontend

**Fecha:** 2026-10-31 · **Agente:** `frontend` · **Riesgo:** Medio
**Método:** `grep` dirigido, lectura de código (`archivo:línea`), `tsc`, `eslint`,
`next build` y smoke HTTP contra el servidor local ya en ejecución
(`127.0.0.1:3000`). No se ejecutó E2E (lo cubre `qa`). Sin cambios de backend ni de
`package.json`.

---

## 1. Verificación previa: ¿había consumidores?

Comando:

```bash
grep -rn "lib/api\b\|lib/api\"\|lib/api'" frontend/src --include="*.ts" --include="*.tsx"
grep -rn "apiUpload" frontend/src --include="*.ts" --include="*.tsx"
grep -rn "ImportarCsv\|importar-csv" frontend/src --include="*.ts" --include="*.tsx"
```

Resultado (previo al borrado):

```text
frontend/src/components/importar-csv.tsx:6:import { apiUpload } from "@/lib/api";
frontend/src/components/importar-csv.tsx:29: ... await apiUpload<...>(
frontend/src/lib/api.ts:48:export async function apiUpload<T = unknown>(
frontend/src/components/importar-csv.tsx:15:export function ImportarCsv({
```

- Ninguna página ni componente importaba `lib/api.ts` (`api`/`apiFetch`) ni
  `ImportarCsv`. El único consumidor del primero era el segundo, y el segundo no
  tenía consumidores.
- `lib/download.ts` (`descargarArchivo`, base `/api/v1`, sin `X-Empresa-ID`) también
  quedó sin consumidores: `grep -rn "lib/download" frontend/src` → 0 resultados.
- Las apariciones de `lib/api.ts` en `frontend/.next/**` son artefactos de build
  (ignorados, no se editan).

Verificación de tipos de `frontend/src/types/index.ts`: se contó cada export fuera del
propio archivo. Solo tenían consumidores `Rol` (6), `Usuario` (8) y `ROL_LABEL` (2).
Los demás (`Cliente`, `Chofer`, `Tracto`, `Rampla`, `EstadoViaje`, `Viaje`,
`CategoriaGasto`, `Gasto`, dashboard, KPIs) daban 0 y sus coincidencias eran texto de
UI, no tipos.

## 2. Qué se eliminó

| Archivo | Motivo |
|---|---|
| `frontend/src/lib/api.ts` | Cliente legacy `/api/v1` sin consumidores; `apiUpload` era su única función usada, por un componente muerto. |
| `frontend/src/components/importar-csv.tsx` | Sin consumidores; dependía de `apiUpload`. |
| `frontend/src/lib/download.ts` | Utilidad de descarga legacy sin consumidores. |
| `frontend/src/components/aviso-sin-legacy.tsx` | Aviso alcanzable solo por el redirect del bloqueo legacy del layout; al quedar `RUTAS_LEGACY` vacía era código muerto. También se quitó su uso en `despacho/page.tsx` (`Suspense` incluido). |
| Exportaciones legacy de `frontend/src/types/index.ts` | Sin uso: `Cliente`, `Chofer`, `Tracto`, `Rampla`, `EstadoViaje`, `ESTADO_VIAJE_LABEL`, `ESTADO_VIAJE_TONO`, `Viaje`, `CategoriaGasto`, `CATEGORIA_GASTO_LABEL`, `Gasto`, `ResumenDashboard`, `AlertaVencimiento`, `FacturaVencida`, `AlertasDashboard`, bloque KPI (`AmbitoKpi`, `FormatoKpi`, `UsoKpi`, `ReglaColor`, `Kpi`, `KpiValor`, `CatalogoKpis`, `PreviewKpi`, `PreviewRentabilidad`, `TONO_KPI`, `formatValorKpi`). |

`types/index.ts` conserva únicamente `Rol`, `Usuario` y `ROL_LABEL`
(`frontend/src/types/index.ts:1-27`), que son los usados por
`context/auth-context.tsx`, `components/app-shell.tsx` y `lib/navigation.ts`.

## 3. Navegación sin concepto legacy

`frontend/src/lib/navigation.ts`:

- `NavItem` ya no declara `legacy: boolean` (`:23-28`) y los ítems de `NAV_GRUPOS` no
  llevan el campo.
- Se eliminaron `RUTAS_LEGACY` y `esRutaLegacy()`, que derivaban una lista vacía.
- `gruposParaRol(rol)` (`:91`) mantiene su comportamiento efectivo (filtrar por rol y
  descartar grupos vacíos); ya no recibe `esLegacy`.
- `tituloDeRuta()` y `NAV_ITEMS` se conservan sin cambios.

`frontend/src/components/app-shell.tsx:37` actualizado a `gruposParaRol(usuario.rol)`.

## 4. Layout sin bloqueo legacy

`frontend/src/app/(app)/layout.tsx`:

- Se eliminó el cálculo `sinLegacy`/`rutaBloqueada`, el `useEffect` de redirect a
  `/despacho?aviso=sin-acceso-legacy`, la pantalla `ShieldAlert` y los imports
  `esRutaLegacy`/`ShieldAlert`.
- Se conserva: redirección a `/login?next=...` sin sesión, estado de carga
  (`loading`/`perfilCargando`) y `AppShell` (`:14-34`).
- El manejo de 403 del núcleo no vive en este layout y no se tocó; sigue en
  `lib/nucleo.ts`/pantallas (`NucleoError`).

## 5. `es_legacy`: estado y pendiente Ola E

Sigue usado en la UI para elegir el inicio del `AppShell`
(`frontend/src/components/app-shell.tsx:40`:

```ts
const inicio = usuario?.es_legacy === false ? "/despacho" : "/tablero";
```

). También permanece el tipo y la normalización en
`frontend/src/types/index.ts:20` y `frontend/src/context/auth-context.tsx:39`.
**No se eliminó** porque la instrucción lo reserva para la Ola E y aún tiene un uso
de presentación. Con `/tablero` ya en el núcleo, ese uso es candidato a retiro en la
Ola E junto con el flag del backend.

## 6. Verificación

```text
$ npx tsc --noEmit
TSC_EXIT=0

$ npm run lint
> eslint
LINT_EXIT=0

$ npm run build
▲ Next.js 16.4.3 (Turbopack)
✓ Compiled successfully in 832ms
✓ Generating static pages using 7 workers (30/30) in 234ms
BUILD_EXIT=0
```

Smoke HTTP (servidor local ya en ejecución en `127.0.0.1:3000`):

| Ruta | Código |
|---|---|
| `/mantenimiento` | 200 |
| `/liquidaciones` | 200 |
| `/iva` | 200 |
| `/configuracion` | 200 |
| `/despacho` | 200 |

Grep de cierre (sin referencias en `frontend/src`):

```text
$ grep -rn "lib/api\"\|lib/download\"\|importar-csv\|aviso-sin-legacy\|AvisoSinAccesoLegacy\|esRutaLegacy\|RUTAS_LEGACY" frontend/src --include="*.ts" --include="*.tsx"
sin referencias
```

## 7. Riesgos y observaciones

- 🟢 Borrado seguro para el build actual: `tsc`, `eslint` y `next build` en verde.
- 🟡 El smoke se hizo contra el servidor de desarrollo ya levantado, no contra
  `next start` del build recién generado. El build compila las mismas rutas.
- 🟡 El build sigue listando `/dashboard`, `/viajes`, etc. porque existen como páginas
  de redirección en `frontend/src/app/(retiradas)/` (Ola A). No se tocaron.
- 🟡 `lib/utils.ts` no tiene consumidores, pero no es legacy ni entra en el alcance de
  esta ola; se deja intacto.
- 🔴 Sin E2E ejecutado en esta ola; los flujos autenticados quedan para `qa`.
- **Ola E:** evaluar el retiro de `es_legacy` (tipo, contexto, `app-shell` y contrato
  `/auth/me`) una vez que el backend deje de exponerlo.
