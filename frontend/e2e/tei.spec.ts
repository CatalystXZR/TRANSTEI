import { expect, test, type Page } from "@playwright/test";

const ADMIN = { email: "admin@tei.local", password: "TEI2026!" };

async function login(page: Page, email = ADMIN.email, next?: string) {
  await page.goto(next ? `/login?next=${encodeURIComponent(next)}` : "/login");
  await page.getByLabel("Correo electrónico").fill(email);
  await page.getByLabel("Contraseña").fill(ADMIN.password);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await page.waitForLoadState("networkidle");
}

test.describe("TEI — flujo del piloto", () => {
  test("login, tablero del dueño y briefing", async ({ page }) => {
    await login(page);
    await expect(page).toHaveURL(/\/dashboard/);
    await page.goto("/tablero");
    await expect(page.getByRole("heading", { name: "Tablero del dueño" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Briefing diario" })).toBeVisible();
    await expect(page.getByText("Centro de alertas")).toBeVisible();
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
    if (await abrir.count()) {
      await abrir.click();
      await expect(page).toHaveURL(/\/expediente\/[0-9a-f-]+/);
      await expect(page.getByText("Resumen", { exact: true }).first()).toBeVisible();
      await expect(page.getByAltText(/QR/)).toBeVisible();
    }
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
    await login(page, "conductor@tei.local", "/conductor");
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
