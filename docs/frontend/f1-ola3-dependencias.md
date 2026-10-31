# Dependencias del frontend — Fase 1, Ola 3

**Fecha:** 2026-10-30 · **Rol:** frontend · **Riesgo:** Medio (dependencias)
**Alcance:** `frontend/package.json`, `frontend/package-lock.json` (escritos solo por
npm). No se modificó `frontend/src`.
**Método:** comandos ejecutados en el entorno local (Node 22.23.3, npm 10.9.9,
Next 16). Cada cifra de este informe proviene de una salida pegada abajo; no se cita
de memoria.

---

## Resumen

| Momento | Total | Critical | High | Moderate | Low |
|---|---|---|---|---|---|
| Inicial (`npm audit --omit=dev`) | **12** | 1 | 7 | 3 | 1 |
| Tras `npm audit fix` (sin `--force`) | **4** | 1 | 0 | 0 | 3 |
| Tras subir `next`/`eslint-config-next` 16.3.7 → 16.4.3 | **3** | 0 | 0 | 0 | 3 |

`npm audit` completo (con devDependencies) da exactamente los mismos totales que
`--omit=dev` en los tres momentos, porque los paquetes vulnerables restantes cuelgan de
`shadcn`, que está declarado en `dependencies` (ver §3).

**Lo que queda no se ejecuta en el bundle del ERP.** Los 3 `low` restantes son
`deepmerge` y sus dos ancestros `@shadcn/registry` → `shadcn`: la CLI de generación de
componentes, sin ningún `import` desde `frontend/src` (§3).

**Corrección al contexto de F0:** el reporte de F0 describía "7 high en `undici`, 1
critical + moderate en `zod`". El árbol real tenía la **critical en `next@16.3.7`** y
`zod` como **high** (no critical); `undici` high sí existía, pero solo bajo la CLI
`shadcn`. El detalle real está en §1.

---

## 1. Estado inicial (🟢 verificado)

Comando: `npm audit --omit=dev` en `frontend/`.
Salida (extracto de encabezados; total al pie):

```text
@modelcontextprotocol/sdk  <=1.31.0   high      fix available via `npm audit fix`
body-parser  2.0.0 - 2.3.0            high      fix available via `npm audit fix`
deepmerge  >=4.2.0                    low       fix available via `npm audit fix --force` (shadcn@1.0.0)
fast-uri  3.0.0 - 3.1.8               moderate  fix available via `npm audit fix`
ip-address  <=10.7.3                  moderate  fix available via `npm audit fix`
next  16.0.0 - 16.4.0                 critical  fix available via `npm audit fix --force` (next@16.4.3)
qs  6.7.0 - 6.16.0                    moderate  fix available via `npm audit fix`
source-map-js  1.0.0 - 1.2.1          high      fix available via `npm audit fix`
systeminformation  <5.33.16           high      fix available via `npm audit fix`
undici  7.0.0 - 7.30.0                high      fix available via `npm audit fix`
zod  <4.6.6                           high      fix available via `npm audit fix --force` (shadcn@1.0.0)

12 vulnerabilities (1 low, 3 moderate, 7 high, 1 critical)
```

Ruta real de cada paquete verificada con `npm ls`:

| Paquete | Ruta | ¿Runtime del ERP? |
|---|---|---|
| `next@16.3.7` | dependencia directa | **Sí** (servidor/render) |
| `undici@7.30.0` | `shadcn → @dotenvx/dotenvx`, `shadcn` | No (CLI) |
| `zod@4.6.5` | `shadcn` (hoisted) y `eslint-config-next → eslint-plugin-react-hooks` | No (CLI/lint) |
| `deepmerge` | `shadcn → @shadcn/registry` | No (CLI) |
| `@modelcontextprotocol/sdk`, `body-parser`, `express`, `hono`… | `shadcn` | No (CLI) |
| `source-map-js` | `postcss`/`@tailwindcss/postcss`/`next` | Sí (build), no bundle de cliente |
| `systeminformation`, `fast-uri`, `ip-address`, `qs` | `shadcn`/tooling | No (CLI) |

Evidencia de que `shadcn` no es runtime (🟢): `grep -rn "shadcn"` en `frontend/src`
no devuelve ninguna importación; solo aparece en `frontend/package.json:22` y en
`frontend/components.json:2` (schema de configuración). Los componentes de
`frontend/src/components/ui/**` son archivos locales que no importan el paquete.

---

## 2. Acciones aplicadas

### 2.1 `npm audit fix` (sin `--force`) — 12 → 4

```text
added 9 packages, removed 71 packages, changed 8 packages, and audited 557 packages in 6s
...
4 vulnerabilities (3 low, 1 critical)
```

`package.json` **no cambió** (los rangos `^` ya permitían los parches). Cambios
relevantes del lock:

| Paquete | Antes | Después |
|---|---|---|
| `shadcn` | 4.21.0 | 4.23.0 |
| `undici` | 7.30.0 | 7.30.1 |
| `zod` (top-level) | 4.6.5 | 4.6.7 |
| `source-map-js` | 1.2.1 | 1.2.2 |
| `systeminformation` | 5.33.14 | 5.33.18 |
| `ip-address` | 10.7.2 | 10.7.5 |
| `fast-uri` | 3.1.8 | 3.1.9 |
| `@modelcontextprotocol/sdk` 1.31.0, `body-parser` 2.3.0, `express` 5.2.1, `hono`… | presentes | **eliminados** (la CLI 4.23.0 ya no los arrastra) |

Total: 86 entradas de `package-lock.json` con versión distinta (9 altas, 71 bajas,
6 cambios). Verificación de ese paso: `tsc`/`lint`/`build` en verde (§4).

> Nota: en este punto `zod` quedó resuelto (4.6.5 → 4.6.7, fuera del rango `<4.6.6`)
> sin tocar `shadcn` a la fuerza. El único `zod` vulnerable que npm seguía listando era
> el árbol previo; tras el fix ya no aparece en `npm audit`.

### 2.2 `next` 16.3.7 → 16.4.3 (+ `eslint-config-next`) — 4 → 3

La única `critical` restante era `next@16.3.7` (10 advisories: RCE no autenticado en
Image Optimization con SVG, SSRF en Image Optimization, cache poisoning SSG/ISR, DoS
en Server Actions, fugas de `use cache`, etc.). `npm audit fix` no la aplicaba porque
`package.json` **fija la versión exacta** (`"next": "16.3.7"`), y la corrección
(`16.4.3`) es el `latest` estable, **mismo major** (`isSemVerMajor: false`).

Comando ejecutado (preservando el estilo de pin exacto):

```bash
npm install --save-exact next@16.4.3 eslint-config-next@16.4.3
# changed 5 packages, and audited 557 packages in 7s
# 3 low severity vulnerabilities
```

Se actualizó `eslint-config-next` junto con `next` para evitar el desfase
config/compilador (ambos estaban pinneados a 16.3.7). Cambios en el lock:
`next`, `@next/env`, `@next/eslint-plugin-next`, `eslint-config-next` y el binario
`@next/swc-darwin-arm64`, todos 16.3.7 → 16.4.3.

Rollback si hiciera falta: `npm install --save-exact next@16.3.7 eslint-config-next@16.3.7`
(la copia previa de `package.json`/`package-lock.json` de esta sesión está en
`/tmp/f1ola3/*.before`, fuera del repo).

---

## 3. `zod` y `shadcn`: por qué no se fuerza el cambio

- **`zod` ya está corregido** por la vía segura (4.6.7). La ruta `shadcn` que npm
  proponía (`--force` → `shadcn@1.0.0`) es un **downgrade con cambio de major** de una
  herramienta de generación, no una corrección de runtime.
- **`shadcn` es herramienta de generación, no runtime** 🟢:
  - `grep -rn "from ['\"]shadcn\|require(['\"]shadcn\|shadcn/" frontend/src` → sin
    resultados.
  - `components.json` solo declara el schema/aliases; no importa el paquete.
  - El build de producción (`npm run build`) no lo necesita: la app compila y sirve
    con los componentes ya versionados en `src/components/ui/`.
  - Solo se usa manualmente (`npx shadcn add ...`) para añadir componentes.
- **Hallazgo de clasificación** (🟡, no corregido por alcance): `shadcn` está en
  `dependencies` (`frontend/package.json:22`) cuando es una CLI de desarrollo. Eso
  hace que (a) se instale en despliegues con `npm ci` completo (CI lo hace,
  `.github/workflows/ci.yml:102`) y (b) `npm audit --omit=dev` siga contando su árbol
  como si fuera producción.
  **Propuesta para una tarea aparte** (no aplicada aquí): moverlo a
  `devDependencies` y verificar `npm ci && npm run build`. Con eso el árbol de
  producción quedaría sin `shadcn`, `@shadcn/registry` ni `deepmerge`, y
  `npm audit --omit=dev` debería bajar a 0. No se aplicó porque cambia el contrato de
  instalación/despliegue y la instrucción de esta ola era no forzar la ruta shadcn.
- El `low` de `deepmerge` (prototype poisoning en `mergeObject`) vive solo en la CLI;
  no hay entrada de usuario del ERP que llegue a esa función.

---

## 4. Verificación (🟢 comandos ejecutados)

| Momento | `npx tsc --noEmit` | `npm run lint` | `npm run build` |
|---|---|---|---|
| Línea base (antes de tocar nada) | 0 | 0 | no ejecutado antes |
| Tras `npm audit fix` | 0 | 0 | 0 (29 rutas) |
| Tras subir `next` a 16.4.3 | 0 | 0 | 0 (29 rutas, "Finished TypeScript in 3.7s") |

Salidas:

```text
TSC_EXIT=0
LINT_EXIT=0   (eslint sin hallazgos)
BUILD_EXIT=0
✓ Generating static pages using 7 workers (29/29) in 249ms
Route (app) … /, /login, /dashboard, /despacho, /viajes, /maestros, /facturacion …
```

Consistencia del lock para CI (`npm ci`):

```text
$ npm ci --dry-run
added 73 packages in 268ms
EXIT=0
```

Prueba de ejecución real (no solo compilación):

- Servidor de producción del build nuevo: `npx next start -p 3100` (Next 16.4.3) →
  `/, 307` (redirect a login) · `/login 200` · `/dashboard 200` · `/despacho 200` ·
  `/viajes 200` · `/maestros 200`. Proceso detenido al terminar.
- Servidor de desarrollo en `:3000`: el proceso previo corría `next-server (v16.3.7)`
  en memoria y quedó en `500` al reemplazarse `node_modules` (log:
  `Module not found: Can't resolve 'source-map-js'` y luego
  `routeModule.ensureInstrumentation is not a function`). Se reinició `npm run dev`
  con 16.4.3; verificado `/ 307`, `/login 200`, `/dashboard 200`, `/despacho 200`,
  `/viajes 200`, `/maestros 200`, `/facturacion 200`.

**Limitación:** no se probó un flujo autenticado end-to-end (login real + carga de
datos contra el backend). Las rutas devuelven 200/307 y el shell renderiza, pero la
verificación funcional con datos corresponde a `qa` (§6).

---

## 5. Diff aplicado

`frontend/package.json` (único cambio manual, vía npm):

```diff
-    "next": "16.3.7",
+    "next": "16.4.3",
...
-    "eslint-config-next": "16.3.7",
+    "eslint-config-next": "16.4.3",
```

`frontend/package-lock.json`: reescrito por npm en dos pasos (§2.1 y §2.2). Respecto
de la línea base, el árbol interno de `shadcn@4.23.0` cambia (9 altas, 71 bajas: se
van `express`, `body-parser`, `hono`, `@modelcontextprotocol/sdk` y compañía) y las
dependencias directas del ERP mantienen su conjunto; `next`/`@next/*` suben a
16.4.3. No se agregó ninguna dependencia directa nueva.

`frontend/AGENTS.md` aparece modificado en `git status` **porque lo regeneró
`next dev` 16.4.3** (cambia `#` por `##` en el título del bloque generado). No se
editó a mano; el archivo es generado (ver el propio bloque
`BEGIN:nextjs-agent-rules`).

---

## 6. Handoff

**A `qa`** (regresión por salto de minor de Next):

1. `E2E-1`: login → `/dashboard` → `/despacho`, rol operador, datos de seed;
   esperado: tablero con viajes del día y sin errores de consola.
2. `E2E-2`: `/viajes` → detalle `/viajes/[id]` (ruta dinámica `ƒ`), verificar que la
   ruta dinámica sigue renderizando tras el cambio de versión.
3. `E2E-3`: `/expediente/[id]` (la otra ruta dinámica) con un expediente existente.
4. `E2E-4`: build limpio en CI (`npm ci && npm run lint && npm run build`) — el job
   ya existe en `.github/workflows/ci.yml:102-110`.
5. `E2E-5` (conductor/PWA): abrir `/conductor` en viewport móvil; el salto de Next
   puede afectar caché de service worker si existiera.

**A `auditor-seguridad`:** no se tocaron permisos ni tenant. Si se aprueba mover
`shadcn` a `devDependencies`, revisar que ningún despliegue con `--omit=dev` lo
necesite.

---

## 7. Riesgos y no verificado

- 🔴 **Flujo autenticado con datos no probado** (requiere credenciales/seed y backend
  con sesión). Solo se verificó render/HTTP.
- 🟡 **Next 16.4.3 es un salto de minor** dentro de 16.x. `tsc`, lint, build y rutas
  responden, pero comportamientos de runtime (caché, Server Actions, image
  optimization) no se ejercitaron por falta de flujos que los usen. Si `qa` detecta
  una regresión, el rollback está en §2.2.
- 🟡 **`shadcn` en `dependencies`** mantiene 3 `low` en el audit. No es runtime; se
  propone moverlo a `devDependencies` en tarea autorizada.
- 🟡 El servidor `:3000` **debe reiniciarse tras cualquier cambio de dependencias**;
  un `next dev` viejo contra `node_modules` nuevo responde 500 (observado y
  corregido en esta sesión).
- 🟢 No se ejecutó `npm audit fix --force` en ningún momento; no se instaló
  `shadcn@1.0.0`.
