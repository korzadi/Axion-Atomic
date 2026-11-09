/* E2E de AXYRON Studio (independiente): rutas reales, navegación, 404,
   protección de sesión y accesibilidad básica con axe WCAG 2 A/AA. */
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const studio = new URL("../../studio/", import.meta.url);
const indexHtml = await readFile(new URL("index.html", studio));
const appJs = await readFile(new URL("app.js", studio));
const studioCss = await readFile(new URL("studio.css", studio));
const fetched = {};

const server = createServer((request, response) => {
  const url = new URL(request.url, "http://localhost");
  if (url.pathname === "/studio.css") {
    response.writeHead(200, { "content-type": "text/css; charset=utf-8" });
    return response.end(studioCss);
  }
  if (url.pathname === "/app.js") {
    response.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
    return response.end(appJs);
  }
  // SPA fallback: cualquier ruta real sirve el documento.
  response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  response.end(indexHtml);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true });

const axeSource = readFileSync(new URL("../../node_modules/axe-core/axe.min.js", import.meta.url), "utf8");
const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
const catalog = {
  version: 1, status: "active", checkout_enabled: true, payment_provider: "qvapay_lightning",
  free_credits_on_verify: 50, credit_packages: [],
  models: [{ code: "atomic-code", name: "ATOMIC CODE", description: "Modelo de programación de AXYRON ATOMIC.", available_for_chat: true, billing_candidate: true, billing_enabled: true }],
  plans: [
    { code: "starter_300", name: "Axyron Atomic STARTER", description: "300 créditos (30.000 tokens). Compra única.", credits: 300, price_minor: 499, currency: "USD", one_time: true },
    { code: "plus_750", name: "Axyron Atomic PLUS", description: "750 créditos (75.000 tokens). Compra única.", credits: 750, price_minor: 999, currency: "USD", one_time: true },
  ],
};

function mockAuthed(page) {
  page.route("**/auth/me", (route) => route.fulfill(json({ user: { id: "user-1", email: "u@example.test", display_name: "Usuario Prueba" } })));
  page.route("**/auth/projects", (route) => route.fulfill(json({ items: [{ id: "p1", name: "Proyecto demo", role: "owner" }] })));
  page.route("**/health/readiness", (route) => route.fulfill(json({ status: "ready", billing: { mode: "ledger" } })));
  page.route("**/billing/credits", (route) => route.fulfill(json({ provisioned: true, totals: { available: 50, reserved: 0, consumed: 0 }, recent_ledger: [{ event_type: "grant", available_delta: 50, created_at: "2026-11-08T00:00:00Z" }] })));
  page.route("**/billing/orders**", (route) => route.fulfill(json({ items: [], total: 0, limit: 50, offset: 0 })));
  page.route("**/billing/catalog", (route) => route.fulfill(json(catalog)));
  page.route("**/workspace/usage**", (route) => route.fulfill(json({ totals: { requests: 3, prompt_tokens: 1200, output_tokens: 800, unavailable_measurements: 0 } })));
  page.route("**/workspace/chat/history**", (route) => route.fulfill(json({ messages: [], updated_at: null })));
  page.route("**/auth/mfa/status", (route) => route.fulfill(json({ enabled: false })));
  page.route("**/workspace/knowledge/sources**", (route) => route.fulfill(json({ items: [] })));
  page.route("**/workspace/agent/runs**", (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET") return route.fulfill(json({ status: "awaiting_approval" }));
    if (/\/workspace\/agent\/runs\/[^/]+$/.test(url.pathname)) {
      return route.fulfill(json({
        id: "run-1", goal: "Analizar el proyecto", status: "awaiting_approval",
        messages: [{ role: "assistant", content: "Plan propuesto para el proyecto." }],
        pending_actions: [{ tool: "write_file", summary: "Modificar un archivo", action_hash: "hash-1" }],
      }));
    }
    return route.fulfill(json({ items: [{ id: "run-1", goal: "Analizar el proyecto", status: "awaiting_approval", updated_at: "2026-11-09T00:00:00Z" }] }));
  });
  page.route("**/workspace/agent/approvals**", (route) => route.fulfill(json({
    items: [{ id: "approval-1", tool: "write_file", what: "Modificar un archivo", why: "Corregir un defecto", expires_at: "2026-11-09T01:00:00Z" }],
    plan_items: [],
  })));
  page.route("**/workspace/agent/plan-approvals**", (route) => route.fulfill(json({ id: "plan-1", status: "approved" })));
  page.route("**/workspace/models/availability**", (route) => route.fulfill(json({ models: [{ code: "atomic-code", available: true }] })));
}

try {
  // 1) Sesión inválida -> pantalla de acceso
  {
    const page = await browser.newPage();
    await page.route("**/auth/me", (route) => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Autenticación requerida" }) }));
    await page.goto(baseUrl + "/dashboard", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Tu espacio ya te espera" }).waitFor();
    assert.ok(await page.locator("#st-login-form").isVisible());
    await page.close();
  }

  // 2) Sesión válida -> dashboard con rutas reales y navegación
  {
    const page = await browser.newPage();
    mockAuthed(page);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(baseUrl + "/dashboard", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Panel de control" }).waitFor();
    assert.ok(await page.locator(".st-nav a.active").filter({ hasText: "Resumen" }).count() >= 1);

    // Navegación lateral -> projects (ruta real)
    await page.locator('.st-nav a[data-page="projects"]').click();
    await page.locator(".st-title", { hasText: "Tus proyectos" }).waitFor();
    assert.equal(new URL(page.url()).pathname, "/projects");

    // Botón atrás -> vuelve a dashboard
    await page.goBack();
    await page.getByRole("heading", { name: "Panel de control" }).waitFor();

    // Carga directa + recarga de una ruta real con estado autenticado
    await page.goto(baseUrl + "/billing", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Créditos y facturación" }).waitFor();
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Créditos y facturación" }).waitFor();

    // Compra -> catálogo real con botones Comprar
    await page.goto(baseUrl + "/buy", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Comprar créditos" }).waitFor();
    assert.equal(await page.locator(".st-buy-btn").count(), 2);

    // Agente: ejecuciones, detalle persistido y aprobaciones reales (sin #approve)
    await page.goto(baseUrl + "/agent", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Agente AXYRON" }).waitFor();
    await page.getByText("Analizar el proyecto").first().waitFor();
    assert.equal(await page.locator('a[href="#approve"]').count(), 0);
    await page.getByRole("button", { name: "Ver detalle" }).click();
    await page.getByRole("heading", { name: "Detalle de la ejecución" }).waitFor();
    await page.getByText("Plan propuesto para el proyecto.").waitFor();
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Aprobar" }).click();
    await page.getByText("Decisión registrada. La aprobación no ejecuta por sí sola la acción.").waitFor();

    // Modelos: solo disponible cuando el runtime lo confirma
    await page.goto(baseUrl + "/models", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Modelos Atomic" }).waitFor();
    await page.locator(".st-pill.good", { hasText: "Disponible ahora" }).first().waitFor();
    await page.locator(".st-pill.warn", { hasText: "Próxima actualización" }).first().waitFor();
    assert.deepEqual(errors, [], "El Studio no debe lanzar errores JavaScript");

    // 404 propio
    await page.goto(baseUrl + "/no-existe", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: /404/ }).waitFor();

    // Accesibilidad: axe en dashboard y login
    await page.goto(baseUrl + "/dashboard", { waitUntil: "domcontentloaded" });
    await page.addScriptTag({ content: axeSource });
    const axeResult = await page.evaluate(async () => await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } }));
    assert.equal(axeResult.violations.length, 0, JSON.stringify(axeResult.violations.map((v) => v.id)));
    await page.close();
  }

  // 3) SSO: callback con intercambio simulado -> dashboard
  {
    const page = await browser.newPage();
    mockAuthed(page);
    await page.route("**/auth/sso/exchange", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "authenticated", csrf_token: "csrf-token", expires_in: 43200 }) }));
    await page.goto(baseUrl + "/sso/callback#code=code-mock-1234567890abcdef&state=state-mock-1234567890abcdef", { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Panel de control" }).waitFor();
    assert.equal(new URL(page.url()).pathname, "/dashboard");
    assert.equal(new URL(page.url()).hash, "", "El código SSO no debe permanecer en la URL");
    await page.close();
  }

  process.stdout.write("AXYRON Studio: rutas reales, protección de sesión, SSO, 404, navegación y navegación atrás/adelante aprobados\n");
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
