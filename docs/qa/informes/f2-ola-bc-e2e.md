# Fase 2 — Olas B/C del retiro legacy: E2E de las 4 pantallas del núcleo

> **Dueño:** `qa` · **Fecha:** 2026-10-31 · **Alcance:** `frontend/e2e/tei.spec.ts`
> y `docs/qa/`.
> **Método:** lectura del código real (páginas, router del núcleo, navegación) +
> ejecución de `make e2e`, `make unit` y `make test` contra el entorno local.
> **Nivel de evidencia:** 🟢 salvo lo marcado 🔴/🟡.

---

## 1. Entorno

| Elemento | Valor | Cómo se verificó |
|---|---|---|
| Repo / rama | `/Users/pc/Desktop/Informatica/TRANSTEI/TRANSTEI` · `main` | `git status --short` |
| Frontend | `http://localhost:3000` arriba | `curl /login` → 200 |
| Backend | `http://localhost:8000` arriba | `curl /docs` → 200 · `/openapi.json` → 200 |
| API legacy | retirada | `GET /api/v1/clientes` → **404** |
| Base de datos | local arriba (`127.0.0.1:54322`) | `make test` ejecutó `db-up` y la suite de integración contra `tei_test` |
| Node / Python | v22.23.3 · 3.13.16 | `node --version`, `.venv/bin/python --version` |
| Playwright | 1.56.1 · Chromium | `npx playwright --version` |
| `NUCLEO_TEST_DATABASE_URL` | no definida en el entorno | `make test` usó el default `tei_test` del Makefile |
| Secretos | no se leyó `.env` ni credenciales reales | — |

`frontend/playwright.config.ts` **no** se modificó (`webServer` con
`reuseExistingServer`, 1 worker, `trace`/`screenshot` al fallar).

---

## 2. Escenario

Tras las Olas B/C los 11 routers legacy de negocio ya no están publicados
(`GET /api/v1/<legacy>` → 404) y las 4 pantallas restantes (`/mantenimiento`,
`/iva`, `/liquidaciones`, `/configuracion`) se reimplementaron contra
`/api/v1/nucleo`. El menú ya no tiene grupo legacy: TEI y TES ven **17 ítems**.

**Esperado:** login → `/tablero`; 9 rutas retiradas → 308; API legacy → 404; menú
17 ítems para TEI y TES; las 4 pantallas cargan desde el núcleo sin errores de
consola y con al menos una lectura real.

**Línea base (antes del ajuste):** `14 passed · 1 failed`. La única falla era la
expectativa obsoleta del propio test: el bloque de TES todavía exigía **13** ítems
y la redirección de UI `aviso=sin-acceso-legacy`, ambas cosas eliminadas por la
Ola B/C. No era defecto de producto.

Fuente: `frontend/src/lib/navigation.ts:37-97`,
`frontend/src/app/(app)/{mantenimiento,iva,liquidaciones,configuracion}/page.tsx`,
`backend/app/api/router.py`, `backend/app/nucleo/router.py`.

---

## 3. Reproducción

```bash
cd /Users/pc/Desktop/Informatica/TRANSTEI/TRANSTEI
make e2e     # requiere frontend :3000, backend :8000, base y seed
make unit
make test
```

---

## 4. Pruebas creadas/ajustadas (`frontend/e2e/tei.spec.ts`, 20 tests)

| Línea | Prueba | Qué cubre |
|---|---|---|
| 81-174 | 11 escenarios del piloto | sin cambios respecto de la Ola A |
| 190 | 9 rutas retiradas → 308 | **se mantiene**: status 308 + `Location` al equivalente del núcleo |
| 203 | `/` → 307 → `/tablero` | **se mantiene** |
| 209 | TEI: menú 17 ítems del núcleo | 17 enlaces; contiene las 4 pantallas reimplementadas; no contiene las 9 rutas retiradas |
| 224 | TES: menú 17 ítems y `/mantenimiento` monta el núcleo | **reescrito**: ya no exige 13 ítems ni el rebote `aviso=sin-acceso-legacy`; verifica 17 ítems con las 4 pantallas, que `/mantenimiento` quede en su URL y que `/dashboard` siga en 308 |
| 254 | `/mantenimiento` | 200, `h1` "Mantenimiento", línea `Empresa:` (sesión del núcleo), pestaña **Pauta** con contador y panel "Pautas de mantenimiento" (lectura de `GET /nucleo/mantenimiento/pautas`) |
| 284 | `/iva` | 200, `h1` "IVA mensual", aviso "Período consultado" y tiles "IVA débito" / "Base neta" (lectura de `GET /nucleo/iva/resumen`) |
| 301 | `/liquidaciones` | 200, `h1` "Liquidaciones de sueldo", input "Mes de liquidación" con valor, panel `Liquidaciones · N` (lectura de `GET /nucleo/liquidaciones?mes=…`) |
| 323 | `/configuración` | 200, `h1` "Configuración por empresa", panel "Valores vigentes" y `#cfg-iva_porcentaje` = `19` (lectura de `GET /nucleo/configuracion`; el 19 lo siembra `0026`) |
| 347 | API legacy retirada | los 11 routers (`catalogos, configuracion, dashboard, export, facturas, finanzas, gastos, kpis, liquidaciones, mantenimiento, viajes`) → **404**; `openapi.json` no publica ninguna ruta `/api/v1/*` fuera de `/auth` y `/nucleo`; `/api/v1/nucleo/mis-empresas` sin token → **401** (el núcleo sigue montado) |

Las 4 pruebas de pantalla comparten dos detectores:

- `vigilarConsola(page)` recolecta `console.error` y `pageerror`; se descarta solo
  ruido declarado (`favicon`, aviso de React DevTools, Fast Refresh).
- `ALERTAS_DE_ERROR = 'div[role="alert"]:not(#__next-route-announcer__)'` detecta el
  `ErrorNucleo` (403/404/500 de la API). Se excluye por **id** el route announcer de
  Next, que también es `role="alert"` y va vacío (ver Q-02).

---

## 5. Resultado

### 5.1 Línea base — 🟢 (rojo por la razón correcta)

```text
$ make e2e
Running 15 tests using 1 worker
...
  Locator:  locator('nav[aria-label="Navegación principal"] a')
  Expected: 13
  Received: 17
  1 failed
    [chromium] › e2e/tei.spec.ts:186:7 › Tenant 2 (TES) — sin legacy › ...
  14 passed (28.9s)
make: *** [e2e] Error 1
```

### 5.2 Suite final — 🟢 `make e2e`

```text
$ make e2e
> frontend@0.1.0 test:e2e
> playwright test

Running 20 tests using 1 worker

  ✓  1 ... login cae en tablero del dueño y briefing (1.1s)
  ✓  2 ... comercial: tarifas, OC y centros de costo (1.3s)
  ✓  3 ... despacho: mesa y disponibilidad (1.3s)
  ✓  4 ... expediente: lista y detalle con QR (1.8s)
  ✓  5 ... maestros: reemplaza flota, clientes y choferes retirados (1.2s)
  ✓  6 ... rentabilidad: reemplaza los KPIs retirados (1.3s)
  ✓  7 ... cobranza: factura del seed y aging (1.6s)
  ✓  8 ... auditoría: filtros y registros (1.6s)
  ✓  9 ... permisos: matriz de 8 roles (1.3s)
  ✓ 10 ... PWA del conductor: login y mi viaje (970ms)
  ✓ 11 ... cutover: estado actual y runbook (1.3s)
  ✓ 12 ... las 9 rutas retiradas responden 308 hacia su equivalente del núcleo (222ms)
  ✓ 13 ... la raíz redirige 307 al tablero (20ms)
  ✓ 14 ... TEI: menú con 17 ítems del núcleo, sin las rutas retiradas (1.1s)
  ✓ 15 ... Tenant 2 (TES): login cae en tablero y el menú es el mismo núcleo (17 ítems, sin grupo legacy) (1.3s)
  ✓ 16 ... mantenimiento: carga 200 y lee el estado y la pauta del servidor (1.3s)
  ✓ 17 ... iva: carga 200 y muestra el resumen de IVA débito del mes (1.6s)
  ✓ 18 ... liquidaciones: carga 200 y lista el mes en curso desde el núcleo (1.3s)
  ✓ 19 ... configuración: carga 200 y muestra los valores vigentes del servidor (1.3s)
  ✓ 20 ... los 11 routers legacy responden 404 y el núcleo sigue montado (356ms)

  20 passed (24.2s)
```

**20 passed · 0 failed · 0 skipped · 0 flaky.**

### 5.3 Regresión backend — 🟢

```text
$ make unit
128 passed, 2 warnings in 0.79s

$ make test
405 passed, 2 warnings in 7.49s
```

Coincide con lo esperado (128 y 405). Sin `skipped` en la salida; sin cambios en
`backend/tests/` por parte de este rol.

---

## 6. Cobertura por pantalla

| Pantalla | URL | Carga | Lectura verificada | Consola / errores | Estado |
|---|---|---|---|---|---|
| Mantenimiento | `/mantenimiento` | 200, `h1` y línea Empresa | pestaña Pauta + panel (contador del servidor) | sin `console.error`, sin `ErrorNucleo` | 🟢 |
| IVA mensual | `/iva` | 200, `h1` | resumen del mes: IVA débito y base neta | sin `console.error`, sin `ErrorNucleo` | 🟢 |
| Liquidaciones | `/liquidaciones` | 200, `h1` | mes fijado y panel `Liquidaciones · N` | sin `console.error`, sin `ErrorNucleo` | 🟢 |
| Configuración | `/configuracion` | 200, `h1` | valores vigentes con `iva_porcentaje = 19` | sin `console.error`, sin `ErrorNucleo` | 🟢 |
| Menú TEI/TES | `nav[…]` | 17 ítems ambos | las 4 URLs presentes | — | 🟢 |
| API legacy | `/api/v1/<11 routers>` | 404 | no publicadas en OpenAPI | — | 🟢 |
| API núcleo | `/api/v1/nucleo/mis-empresas` | 401 sin token | sigue montado | — | 🟢 |
| Rutas retiradas de UI | 9 URLs | 308 + `Location` | — | — | 🟢 |

Nota de datos: el seed no crea pautas, liquidaciones ni facturas del mes en curso
para TEI, así que las pantallas muestran estados vacíos/cero. La prueba verifica
que el **servidor** respondió (contadores, panel, valor `19` de configuración) y
que no hay alerta de error; no inventa filas.

---

## 7. Sanidad (control negativo)

No se puede mutar el código de producción desde este rol y no se hizo copia
desechable del frontend. Se ejecutaron **tres controles negativos** con las mismas
aserciones de la suite en un spec temporal (`frontend/e2e/_sanity.spec.ts`,
**borrado** después; `frontend/e2e/` contiene solo `tei.spec.ts`).

```text
$ npx playwright test e2e/_sanity.spec.ts --reporter=list
  ✘ 1 control negativo: la API del núcleo caída produce alerta visible
      expect(locator).toHaveCount(0)
      Expected: 0 · Received: 1          # con /nucleo/configuracion forzado a 500
  ✘ 2 control negativo: console.error se recolecta
      - Array []
      + Array [ "fallo inyectado de sanidad" ]
  ✘ 3 control negativo: 404 de API legacy no es vacuo
      Expected: 404 · Received: 401      # ruta viva del núcleo
  3 failed
```

Lectura: (1) el detector `ALERTAS_DE_ERROR` **sí** ve un fallo de API en estas
pantallas — si la pantalla dejara de cargar del núcleo, el test de la Ola B/C
fallaría; (2) `vigilarConsola` recoge un `console.error` inyectado; (3) la
aserción de 404 distingue una ruta retirada de una ruta viva. Además, la línea
base (5.1) es evidencia de que el conteo del menú puede fallar: con 13 esperados
el rojo apareció solo.

No se usó `xfail`, `skip` ni se borraron pruebas; los dos `test` de la suite que
se reescribieron siguen existiendo (TES) o se mantuvieron (308, raíz, menú TEI).

---

## 8. Cobertura faltante / límites

| Punto | Estado |
|---|---|
| Acción de **escritura** en las 4 pantallas (crear pauta, registrar mantención, emitir liquidación, guardar configuración) | 🔴 fuera de alcance: exigiría mutar el seed/datos y el objetivo era carga + lectura |
| Datos no vacíos en las 4 pantallas (el seed no trae pautas/liquidaciones/facturas del mes) | 🔴 no cubierto; se validan contadores y estados vacíos |
| Roles distintos de `admin` en el menú (despacho, contador, tesorería…) | 🔴 no cubierto en E2E (`gruposParaRol` filtra por rol, verificado solo por lectura) |
| 403/401 de la API desde un JWT real del navegador | 🔴 no cubierto aquí; los permisos por endpoint los cubre `make test` |
| Viewport móvil / drawer | 🔴 no cubierto (1440×900) |
| Mutación del `permanentRedirect` de las 9 rutas | 🔴 no ejecutada (código de producción, fuera del rol) |
| `console.warn` / warnings de React | 🟡 no se aseveran; solo `error` y `pageerror` |

---

## 9. Defectos detectados

Ningún defecto de producto en este alcance: las 4 pantallas cargan del núcleo,
los 11 routers legacy dan 404 y el núcleo responde 401 sin token.

| ID | Descripción | Evidencia | Impacto | Estado |
|---|---|---|---|---|
| Q-02 | La primera versión de las pruebas nuevas usaba `getByRole("alert")` para detectar `ErrorNucleo`; Next.js monta siempre `#__next-route-announcer__` con `role="alert"` vacío → falso positivo en las 4 pantallas | 4 tests rojos con `Expected 0 · Received 1`; el snapshot de error mostraba `alert [ref=e265]` | bajo (defecto de la prueba, no del producto) | corregido: se excluye por id y se validó con el control negativo (1) |
| Q-03 | `docs/qa/matriz-trazabilidad.md` §10 declaraba 13/16/4/31/64 filas, cifras que no se reproducían con el propio comando `awk` del documento (36/19/3/32/90 antes de esta tarea) | comando de §10 ejecutado en esta sesión | documental | corregido: §10/§11 recalculados a `40/20/3/32/95`; §9 actualizado a las Olas B/C |

---

## 10. Artefactos modificados

- `frontend/e2e/tei.spec.ts` — 15 → 20 tests; Olas B/C cubiertas.
- `docs/qa/matriz-trazabilidad.md` §9 (filas de menú/TES + 5 filas de la Ola B/C),
  §10 y §11 (cifras recalculadas).
- Este informe.
