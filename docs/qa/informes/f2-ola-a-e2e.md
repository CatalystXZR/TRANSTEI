# Fase 2 — Ola A del retiro legacy: actualización de E2E

> **Dueño:** `qa` · **Fecha:** 2026-10-31 12:59 (-03) · **Alcance:** `frontend/e2e/tei.spec.ts`
> **Método:** lectura de código real + ejecución de `make e2e`, `make unit` y `make test`
> contra el entorno local. Sin cambios en código de producción.
> **Nivel de evidencia:** 🟢 todo lo de este informe se ejecutó en esta sesión; los
> puntos no verificables se marcan explícitamente.

---

## 1. Entorno

| Elemento | Valor |
|---|---|
| Repo / rama | `/Users/pc/Desktop/Informatica/TRANSTEI/TRANSTEI` · `main` |
| Frontend | `http://localhost:3000` arriba (Next 16.4.3, `npm run dev`) |
| Backend | `http://localhost:8000` arriba (`/docs` → 200) |
| Base de datos | Supabase local arriba (`make test` ejecutó `db-up` y la suite de integración) |
| Node / Python | v22.23.3 · 3.13.16 |
| Playwright | 1.56.1 · Chromium ya instalado (`chromium-1194`) |
| `NUCLEO_TEST_DATABASE_URL` | no definida en el entorno; `make test` usa el default `tei_test` del Makefile y funcionó |
| Secretos | no se leyó ningún `.env` ni valor de credenciales |

`frontend/playwright.config.ts` no se modificó (webServer con `reuseExistingServer`).

---

## 2. Escenario

Tras la Ola A, nueve pantallas legacy dejaron de existir como páginas y pasaron a ser
redirecciones permanentes **308** al equivalente del núcleo (route group
`frontend/src/app/(retiradas)/`); `/` responde **307** a `/tablero` y el login aterriza
en `/tablero`. La suite E2E seguía esperando `/dashboard` y no cubría el retiro.

**Esperado:** login → `/tablero`; las 9 rutas → 308 con `Location` correcto; menú TEI
con 17 ítems; tenant TES con 13 ítems sin legacy y sin montar pantallas legacy.
**Actual (línea base):** 1 failed / 8 passed — la única falla era la expectativa
obsoleta `/dashboard` (la app ya respondía `/tablero`). No era un defecto de producto.

Fuente: `frontend/src/app/(retiradas)/*/page.tsx`, `frontend/src/app/page.tsx`,
`frontend/src/app/login/page.tsx:30`, `frontend/src/lib/navigation.ts`,
`docs/frontend/f2-ola-a-retiro.md`.

---

## 3. Reproducción

```bash
cd /Users/pc/Desktop/Informatica/TRANSTEI/TRANSTEI
make e2e     # requiere frontend :3000, backend :8000, base y seed
make unit
make test
```

---

## 4. Pruebas creadas/ajustadas

`frontend/e2e/tei.spec.ts` (15 tests, 3 bloques):

| Línea | Prueba | Qué cubre |
|---|---|---|
| 41 | login cae en tablero del dueño y briefing | `toHaveURL(/\/tablero$/)`; headings Tablero/Briefing; panel de alertas (selector por rol, antes `getByText` ambiguo) |
| 49 | comercial | Tarifas/OC (sin cambios) |
| 60 | despacho | Mesa de despacho + disponibilidad (destino de `/viajes`) |
| 68 | expediente | Lista → detalle UUID + QR (destino de `/viajes/[id]`); se **retiró el `if (await abrir.count())`** que permitía pasar sin abrir el detalle |
| 82 | maestros | `Maestros del núcleo` (destino de `/flota`, `/clientes`, `/choferes`) |
| 88 | rentabilidad | `Margen, tarifa piso y Freight Score` (destino de `/kpis`) |
| 96 | cobranza | Factura del seed + aging (destino de `/facturacion`, `/cobranzas`) |
| 106 | auditoría | Sin cambios |
| 114 | permisos | Sin cambios |
| 123 | PWA conductor | Sin cambios (login con `next=/conductor`) |
| 134 | cutover | Sin cambios |
| 150 | 9 rutas retiradas → 308 | `request.get(ruta, { maxRedirects: 0 })`: status **308** y header `Location` contiene el destino, para las 9 rutas |
| 163 | raíz → 307 | `/` responde 307 → `/tablero` |
| 169 | menú TEI 17 ítems | `nav[aria-label="Navegación principal"] a` = 17; contiene `/mantenimiento`, `/iva`, `/liquidaciones`, `/configuracion`; no contiene las 9 rutas retiradas |
| 186 | tenant TES | login `admin2@tei.local` → `/tablero`; menú = 13 sin ítems legacy; `/dashboard` → 308; `/mantenimiento` no monta pantalla y redirige a `/despacho?aviso=sin-acceso-legacy` |

---

## 5. Resultado

### 5.1 Línea base (antes del ajuste) — 🟢

```text
$ cd frontend && npx playwright test --reporter=list
  1 failed
    [chromium] › e2e/tei.spec.ts:14:7 › TEI — flujo del piloto › login, tablero del dueño y briefing
    Expected pattern: /\/dashboard/
    Received string:  "http://localhost:3000/tablero"
  8 passed (23.7s)
```

Falla por la razón correcta: la app ya no aterriza en `/dashboard`.

### 5.2 Suite final — 🟢 `make e2e`

```text
$ make e2e
> frontend@0.1.0 test:e2e
> playwright test

Running 15 tests using 1 worker

  ✓   1 ... login cae en tablero del dueño y briefing (1.1s)
  ✓   2 ... comercial: tarifas, OC y centros de costo (1.6s)
  ✓   3 ... despacho: mesa y disponibilidad (1.3s)
  ✓   4 ... expediente: lista y detalle con QR (1.9s)
  ✓   5 ... maestros: reemplaza flota, clientes y choferes retirados (1.3s)
  ✓   6 ... rentabilidad: reemplaza los KPIs retirados (1.3s)
  ✓   7 ... cobranza: factura del seed y aging (1.7s)
  ✓   8 ... auditoría: filtros y registros (1.7s)
  ✓   9 ... permisos: matriz de 8 roles (1.4s)
  ✓  10 ... PWA del conductor: login y mi viaje (1.0s)
  ✓  11 ... cutover: estado actual y runbook (1.3s)
  ✓  12 ... las 9 rutas retiradas responden 308 hacia su equivalente del núcleo (244ms)
  ✓  13 ... la raíz redirige 307 al tablero (22ms)
  ✓  14 ... TEI: menú con 17 ítems, sin las rutas retiradas y con las 4 legacy restantes (1.1s)
  ✓  15 ... Tenant 2 (TES): login cae en tablero, menú solo núcleo y pantalla legacy no se ofrece (1.4s)

  15 passed (19.0s)
```

**0 failed · 0 skipped · 0 errores.**

### 5.3 Regresión backend — 🟢

```text
$ make unit
135 passed, 2 warnings in 0.80s

$ make test
388 passed, 2 warnings in 7.75s
```

Sin cambios respecto del comportamiento esperado; no hay skips. `make test` incluye
`test_f2_tenant2_gate_legacy.py`, que verifica el 403 `LEGACY_SOLO_TEI` de la API para
el tenant TES (el gate real, que el E2E de UI no duplica).

---

## 6. Cobertura por pantalla retirada

| Pantalla retirada | URL | Redirección verificada | Equivalente del núcleo probado | Estado |
|---|---|---|---|---|
| Dashboard legacy | `/dashboard` | 308 → `/tablero` | tablero (E2E:41) | 🟢 |
| Viajes | `/viajes` | 308 → `/despacho` | despacho (E2E:60) | 🟢 |
| Detalle de viaje | `/viajes/123` | 308 → `/expediente` | expediente + detalle/QR (E2E:68) | 🟢 |
| Flota | `/flota` | 308 → `/maestros` | maestros (E2E:82) | 🟢 |
| Clientes | `/clientes` | 308 → `/maestros` | maestros (E2E:82) | 🟢 |
| Choferes | `/choferes` | 308 → `/maestros` | maestros (E2E:82) | 🟢 |
| Facturación | `/facturacion` | 308 → `/cobranza` | cobranza (E2E:96) | 🟢 |
| Cobranzas | `/cobranzas` | 308 → `/cobranza` | cobranza (E2E:96) | 🟢 |
| KPIs | `/kpis` | 308 → `/rentabilidad` | rentabilidad (E2E:88) | 🟢 |
| Raíz | `/` | 307 → `/tablero` | tablero (E2E:41) | 🟢 |

Menú y tenant: TEI 17 ítems (E2E:169); TES 13 ítems sin legacy, login en `/tablero`,
`/dashboard` 308 y `/mantenimiento` redirigido a despacho con aviso (E2E:186).

---

## 7. Sanidad

**No se hizo mutación real.** Mutar exigía retirar `permanentRedirect` de
`frontend/src/app/(retiradas)/…`, que es código de producción y este rol no puede
editar; hacerlo en una copia desechable requería levantar un segundo Next con
dependencias, fuera del alcance de esta tarea. Se declara como limitación, no como
hecho.

**Control negativo ejecutado** con las mismas aserciones aplicadas a donde la garantía
no existe (spec temporal `frontend/e2e/_sanity.spec.ts`, borrado después):

```text
✘ control negativo: ruta viva no responde 308
   Expected: 308 · Received: 200            (/comercial, ruta viva)
✘ control negativo: TES no tiene 17 ítems
   Expected: 17 · Received: 13              (menú real del tenant TES)
2 failed
```

Demuestra que ambas aserciones (código 308 y conteo del menú) **pueden fallar** y no
son vacuas. El spec temporal se eliminó: `frontend/e2e/` contiene solo `tei.spec.ts`.

Otro refuerzo dentro de la suite: el test de expediente ya no está envuelto en
`if (await abrir.count())`; si el seed no trae viajes, el test falla en vez de pasar
sin verificar el detalle ni el QR.

---

## 8. Cobertura faltante / límites

| Punto | Estado |
|---|---|
| 403 `LEGACY_SOLO_TEI` desde la UI | 🔴 no en E2E (requeriría extraer el JWT de Supabase y llamar a `:8000`; el gate lo cubre `test_f2_tenant2_gate_legacy.py`, ejecutado en `make test`) |
| Respuesta API legacy 200 para TEI en E2E | 🔴 fuera del alcance (cubierto por backend) |
| Mutación del mecanismo 308 | 🔴 no ejecutada (no se toca código de producción) |
| Otros roles del tenant 2 (`despacho2@tei.local`, 10 ítems) | 🔴 no cubierto en E2E; el conteo por rol está documentado en `docs/frontend/f2-tenant2-navegacion.md` pero no ejecutado aquí |
| Móvil / drawer | 🔴 no cubierto (viewport 1440 desktop) |

---

## 9. Defectos detectados

Ninguno atribuible al código de producción en este alcance: el único rojo de la línea
base era la expectativa obsoleta del propio test.

Defecto de prueba corregido (no de producto):

| ID | Descripción | Evidencia | Impacto |
|---|---|---|---|
| Q-01 | La suite esperaba `/dashboard` después del login y tenía un `if (await abrir.count())` que podía omitir el detalle del expediente (SEC-011 de la matriz) | línea base E2E:41; `tei.spec.ts` previo:47-53 | bajo (cobertura, no producto) — corregido en esta tarea |

El `getByText("Centro de alertas")` también era ambiguo (2 coincidencias) al ejecutar
por primera vez el test de login ya corregido; se reemplazó por
`getByRole("heading", { name: /Centro de alertas/ })`.

---

## 10. Artefactos

- `frontend/e2e/tei.spec.ts` — suite actualizada (15 tests).
- `docs/qa/matriz-trazabilidad.md` §9 — estado E2E y filas de la Ola A actualizadas a
  "ejecutada 2026-10-31".
- Este informe.
