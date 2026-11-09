import { expect, test, type Page } from "@playwright/test";

type Cuenta = { email: string; password: string };

const ADMIN: Cuenta = { email: "admin@tei.local", password: "TEI2026!" };
const TENANT2: Cuenta = { email: "admin2@tei.local", password: "TEI2026!" };

/** Ola A del retiro legacy (2026-10-31): URL retirada → equivalente del núcleo. */
const RUTAS_RETIRADAS: Array<{ desde: string; hacia: string }> = [
  { desde: "/dashboard", hacia: "/tablero" },
  { desde: "/viajes", hacia: "/despacho" },
  { desde: "/viajes/123", hacia: "/expediente" },
  { desde: "/flota", hacia: "/maestros" },
  { desde: "/clientes", hacia: "/maestros" },
  { desde: "/choferes", hacia: "/maestros" },
  { desde: "/facturacion", hacia: "/cobranza" },
  { desde: "/cobranzas", hacia: "/cobranza" },
  { desde: "/kpis", hacia: "/rentabilidad" },
];

/**
 * Olas B/C (2026-10-31): estas cuatro pantallas dejaron de ser legacy y se
 * reimplementaron contra `/api/v1/nucleo`. Mantienen la misma URL de UI, así que
 * ya no hay grupo legacy en el menú: son ítems del núcleo para cualquier tenant.
 */
const PANTALLAS_NUCLEO = ["/mantenimiento", "/iva", "/liquidaciones", "/configuracion"];

const NAV = 'nav[aria-label="Navegación principal"] a';

/** Base de la API del backend (nunca se usa para autenticar). */
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

/**
 * Ruido de consola que no es un defecto de la pantalla:
 * - favicon: el proyecto no publica uno y el 404 no afecta la vista.
 * - React DevTools: aviso del modo desarrollo.
 */
const CONSOLA_IGNORADA: RegExp[] = [
  /favicon/i,
  /Download the React DevTools/i,
  /\[Fast Refresh\]/i,
];

/** Recolecta errores de consola y excepciones no capturadas de la página. */
function vigilarConsola(page: Page): string[] {
  const errores: string[] = [];
  page.on("console", (mensaje) => {
    if (mensaje.type() !== "error") return;
    const texto = mensaje.text();
    if (CONSOLA_IGNORADA.some((patron) => patron.test(texto))) return;
    errores.push(`console.error: ${texto}`);
  });
  page.on("pageerror", (error) => {
    errores.push(`pageerror: ${error.message}`);
  });
  return errores;
}

/**
 * `ErrorNucleo` (403/500/404 de la API) se renderiza con `role="alert"`.
 * Next.js agrega siempre `#__next-route-announcer__`, que también es
 * `role="alert"` y va vacío: se excluye por id, no por texto.
 */
const ALERTAS_DE_ERROR = 'div[role="alert"]:not(#__next-route-announcer__)';

async function login(page: Page, cuenta: Cuenta = ADMIN, next?: string) {
  await page.goto(next ? `/login?next=${encodeURIComponent(next)}` : "/login");
  await page.getByLabel("Correo electrónico").fill(cuenta.email);
  await page.getByLabel("Contraseña").fill(cuenta.password);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await page.waitForLoadState("networkidle");
}

async function hrefsDelMenu(page: Page): Promise<string[]> {
  return page.locator(NAV).evaluateAll((enlaces) =>
    enlaces.map((e) => e.getAttribute("href") ?? ""),
  );
}

test.describe("TEI — flujo del piloto", () => {
  test("login cae en tablero del dueño y briefing", async ({ page }) => {
    await login(page);
    await expect(page).toHaveURL(/\/tablero$/);
    await expect(page.getByRole("heading", { name: "Tablero del dueño" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Briefing diario" })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Centro de alertas/ })).toBeVisible();
  });

  test("comercial: tarifas, OC y centros de costo", async ({ page }) => {
    await login(page);
    await page.goto("/comercial");
    await expect(
      page.getByRole("heading", { name: "Tarifas, OC y centros de costo" }),
    ).toBeVisible();
    await expect(page.getByRole("tab", { name: /Tarifas/ })).toBeVisible();
    await page.getByRole("tab", { name: /Órdenes de compra/ }).click();
    await expect(page.getByText("OC-0001").first()).toBeVisible();
  });

  test("despacho: mesa y disponibilidad", async ({ page }) => {
    await login(page);
    await page.goto("/despacho");
    await expect(page.getByRole("heading", { name: "Mesa de despacho" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Nuevo viaje/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Disponibilidad" })).toBeVisible();
  });

  test("expediente: lista y detalle con QR", async ({ page }) => {
    await login(page);
    await page.goto("/expediente");
    await expect(
      page.getByRole("heading", { name: "Expediente del viaje" }),
    ).toBeVisible();
    const abrir = page.getByRole("link", { name: "Abrir" }).first();
    await expect(abrir).toBeVisible();
    await abrir.click();
    await expect(page).toHaveURL(/\/expediente\/[0-9a-f-]+/);
    await expect(page.getByText("Resumen", { exact: true }).first()).toBeVisible();
    await expect(page.getByAltText(/QR/)).toBeVisible();
  });

  test("maestros: reemplaza flota, clientes y choferes retirados", async ({ page }) => {
    await login(page);
    await page.goto("/maestros");
    await expect(page.getByRole("heading", { name: "Maestros del núcleo" })).toBeVisible();
  });

  test("rentabilidad: reemplaza los KPIs retirados", async ({ page }) => {
    await login(page);
    await page.goto("/rentabilidad");
    await expect(
      page.getByRole("heading", { name: "Margen, tarifa piso y Freight Score" }),
    ).toBeVisible();
  });

  test("cobranza: factura del seed y aging", async ({ page }) => {
    await login(page);
    await page.goto("/cobranza");
    await expect(
      page.getByRole("heading", { name: "Facturación y cobranza" }),
    ).toBeVisible();
    await expect(page.getByText("Aging de cartera")).toBeVisible();
    await expect(page.getByText("FAC-2026-900001").first()).toBeVisible();
  });

  test("auditoría: filtros y registros", async ({ page }) => {
    await login(page);
    await page.goto("/auditoria");
    await expect(page.getByRole("heading", { name: "Auditoría" })).toBeVisible();
    await expect(page.getByText("Cambios ·")).toBeVisible();
    await expect(page.getByRole("button", { name: "Ver" }).first()).toBeVisible();
  });

  test("permisos: matriz de 8 roles", async ({ page }) => {
    await login(page);
    await page.goto("/permisos");
    await expect(page.getByRole("heading", { name: "Roles y permisos" })).toBeVisible();
    await expect(page.getByText("Administración", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Gerencia", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Auditoría", { exact: true }).first()).toBeVisible();
  });

  test("PWA del conductor: login y mi viaje", async ({ page }) => {
    await login(
      page,
      { email: "conductor@tei.local", password: ADMIN.password },
      "/conductor",
    );
    await expect(page).toHaveURL(/\/conductor/);
    await expect(page.getByText("Conductor", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/VJ-2026-|Sin viaje activo/).first()).toBeVisible();
  });

  test("cutover: estado actual y runbook", async ({ page }) => {
    await login(page);
    await page.goto("/cutover");
    await expect(
      page.getByRole("heading", { name: "Cutover legacy → núcleo" }),
    ).toBeVisible();
    // El congelamiento es un estado GLOBAL y mutable por operación. La prueba
    // verifica que la pantalla refleje un estado válido, no un estado concreto:
    // fijar "Congelada" la hacía pasar solo con el sistema congelado, y dejó de
    // ser cierta al descongelarlo (hallazgo H-1 del registro de orquestación).
    await expect(page.getByText(/^(Congelada|Abierta)$/).first()).toBeVisible();
    await expect(page.getByText("Runbook rápido")).toBeVisible();
  });
});

test.describe("Ola A — rutas legacy retiradas", () => {
  test("las 9 rutas retiradas responden 308 hacia su equivalente del núcleo", async ({
    request,
  }) => {
    for (const { desde, hacia } of RUTAS_RETIRADAS) {
      const respuesta = await request.get(desde, { maxRedirects: 0 });
      expect(respuesta.status(), `${desde} debe ser una redirección permanente`).toBe(308);
      expect(
        respuesta.headers()["location"],
        `${desde} debe apuntar a ${hacia}`,
      ).toContain(hacia);
    }
  });

  test("la raíz redirige 307 al tablero", async ({ request }) => {
    const respuesta = await request.get("/", { maxRedirects: 0 });
    expect(respuesta.status()).toBe(307);
    expect(respuesta.headers()["location"]).toContain("/tablero");
  });

  test("TEI: menú con 17 ítems del núcleo, sin las rutas retiradas", async ({ page }) => {
    await login(page);
    const enlaces = page.locator(NAV);
    await expect(enlaces).toHaveCount(17);

    const hrefs = await hrefsDelMenu(page);
    for (const item of PANTALLAS_NUCLEO) expect(hrefs).toContain(item);
    for (const { desde } of RUTAS_RETIRADAS) {
      if (desde === "/viajes/123") continue;
      expect(hrefs, `${desde} no debe ofrecerse en el menú`).not.toContain(desde);
    }
  });
});

test.describe("Tenant 2 (TES) — menú del núcleo", () => {
  test("login cae en tablero y el menú es el mismo núcleo (17 ítems, sin grupo legacy)", async ({
    page,
    request,
  }) => {
    await login(page, TENANT2);
    await expect(page).toHaveURL(/\/tablero$/);
    await expect(page.getByRole("heading", { name: "Tablero del dueño" })).toBeVisible();

    // Ola B/C: /mantenimiento, /iva, /liquidaciones y /configuracion ya son
    // pantallas del núcleo; el menú se filtra por rol, no por tenant.
    const enlaces = page.locator(NAV);
    await expect(enlaces).toHaveCount(17);
    const hrefs = await hrefsDelMenu(page);
    for (const item of PANTALLAS_NUCLEO) {
      expect(hrefs, `${item} debe ofrecerse en el menú del núcleo`).toContain(item);
    }

    // El retiro es del servidor: /dashboard responde 308 para cualquier tenant.
    const redirigida = await request.get("/dashboard", { maxRedirects: 0 });
    expect(redirigida.status()).toBe(308);
    expect(redirigida.headers()["location"]).toContain("/tablero");

    // Y la pantalla ya no es legacy: monta el núcleo en vez de rebotar a despacho.
    await page.goto("/mantenimiento");
    await expect(page).toHaveURL(/\/mantenimiento$/);
    await expect(page.getByRole("heading", { name: "Mantenimiento" })).toBeVisible();
  });
});

test.describe("Olas B/C — las 4 pantallas reimplementadas contra el núcleo", () => {
  test("mantenimiento: carga 200 y lee el estado y la pauta del servidor", async ({
    page,
  }) => {
    const errores = vigilarConsola(page);
    await login(page);

    const respuesta = await page.goto("/mantenimiento");
    expect(respuesta?.status()).toBe(200);
    await expect(
      page.getByRole("heading", { name: "Mantenimiento" }),
    ).toBeVisible();
    // La empresa sale de /nucleo/mis-empresas: si la sesión del núcleo falla,
    // esta línea no aparece.
    await expect(page.getByText(/^Empresa:/)).toBeVisible();

    // Lectura real: el contador de la pestaña sale de
    // GET /nucleo/mantenimiento/pautas.
    const pestanaPauta = page.getByRole("tab", { name: /^Pauta/ });
    await expect(pestanaPauta).toBeVisible();
    await pestanaPauta.click();
    await expect(
      page.getByRole("heading", { name: "Pautas de mantenimiento" }),
    ).toBeVisible();
    // ErrorNucleo (403/500) se renderiza con role=alert; un 404 de API legacy
    // también caería aquí.
    await expect(page.locator(ALERTAS_DE_ERROR)).toHaveCount(0);

    expect(errores).toEqual([]);
  });

  test("iva: carga 200 y muestra el resumen de IVA débito del mes", async ({ page }) => {
    const errores = vigilarConsola(page);
    await login(page);

    const respuesta = await page.goto("/iva");
    expect(respuesta?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: "IVA mensual" })).toBeVisible();

    // Lectura real: GET /nucleo/iva/resumen con el mes en curso.
    await expect(page.getByText(/Período consultado/)).toBeVisible();
    await expect(page.getByText("IVA débito", { exact: true })).toBeVisible();
    await expect(page.getByText("Base neta", { exact: true })).toBeVisible();
    await expect(page.locator(ALERTAS_DE_ERROR)).toHaveCount(0);

    expect(errores).toEqual([]);
  });

  test("liquidaciones: carga 200 y lista el mes en curso desde el núcleo", async ({
    page,
  }) => {
    const errores = vigilarConsola(page);
    await login(page);

    const respuesta = await page.goto("/liquidaciones");
    expect(respuesta?.status()).toBe(200);
    await expect(
      page.getByRole("heading", { name: "Liquidaciones de sueldo" }),
    ).toBeVisible();

    // Lectura real: GET /nucleo/liquidaciones?mes=AAAA-MM. El mes se fija al
    // montar y el panel muestra el conteo devuelto (0 en el seed).
    const mes = page.getByLabel("Mes de liquidación");
    await expect(mes).not.toHaveValue("");
    await expect(page.getByRole("heading", { name: /^Liquidaciones · \d+$/ })).toBeVisible();
    await expect(page.locator(ALERTAS_DE_ERROR)).toHaveCount(0);

    expect(errores).toEqual([]);
  });

  test("configuración: carga 200 y muestra los valores vigentes del servidor", async ({
    page,
  }) => {
    const errores = vigilarConsola(page);
    await login(page);

    const respuesta = await page.goto("/configuracion");
    expect(respuesta?.status()).toBe(200);
    await expect(
      page.getByRole("heading", { name: "Configuración por empresa" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Valores vigentes" })).toBeVisible();

    // Lectura real: GET /nucleo/configuracion. La migración 0026 siembra
    // iva_porcentaje=19 para las empresas existentes; el campo se llena con la
    // fila vigente, no con un valor por defecto de la UI.
    await expect(page.locator("#cfg-iva_porcentaje")).toHaveValue("19");
    await expect(page.locator(ALERTAS_DE_ERROR)).toHaveCount(0);

    expect(errores).toEqual([]);
  });
});

test.describe("Ola C — API legacy retirada", () => {
  test("los 11 routers legacy responden 404 y el núcleo sigue montado", async ({
    request,
  }) => {
    const retirados = [
      "catalogos",
      "configuracion",
      "dashboard",
      "export",
      "facturas",
      "finanzas",
      "gastos",
      "kpis",
      "liquidaciones",
      "mantenimiento",
      "viajes",
    ];

    for (const ruta of retirados) {
      const respuesta = await request.get(`${API_BASE}/${ruta}`);
      expect(respuesta.status(), `${ruta} debe estar retirado (404)`).toBe(404);
    }

    // La documentación OpenAPI está desactivada por defecto (menos superficie
    // de ataque): el esquema no se publica. En local se puede habilitar con
    // ENABLE_DOCS=true; si se hace, este test debe adaptarse, no el backend.
    const openapi = await request.get(`${API_BASE.replace(/\/api\/v1$/, "")}/openapi.json`);
    expect(openapi.status()).toBe(404);

    // El núcleo sigue publicado: sin token responde 401, no 404.
    const nucleo = await request.get(`${API_BASE}/nucleo/mis-empresas`);
    expect(nucleo.status()).toBe(401);
  });
});
