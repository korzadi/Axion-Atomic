import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const frontend = new URL("../../frontend/", import.meta.url);
const axeSource = readFileSync(new URL("../../node_modules/axe-core/axe.min.js", import.meta.url), "utf8");
const files = {
  "/": "Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html",
  "/admin-test": "admin.html",
};
const assets = {
  "/studio.js": "studio.js",
  "/studio.css": "studio.css",
  "/workspace.js": "workspace.js",
  "/admin.js": "admin.js",
};
const server = createServer(async (request, response) => {
  const url = request.url.split("?")[0];
  if (files[url]) {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(await readFile(new URL(files[url], frontend)));
    return;
  }
  if (assets[url]) {
    const contentType = url.endsWith(".css") ? "text/css" : "text/javascript";
    response.writeHead(200, { "content-type": `${contentType}; charset=utf-8` });
    response.end(await readFile(new URL(assets[url], frontend)));
    return;
  }
  response.writeHead(404);
  response.end();
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const studioJson = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
const routeStudioMocks = (page) => {
  page.route("**/auth/me", route => route.fulfill(studioJson({ user: { id: "user-1", email: "user@example.test", display_name: "Test User" } })));
  page.route("**/auth/projects", route => route.fulfill(studioJson({ items: [{ id: "project-1", name: "Proyecto de prueba", role: "owner", created_at: "2026-11-08T00:00:00Z" }] })));
  page.route("**/billing/catalog", route => route.fulfill(studioJson({ version: 1, status: "preview_only", checkout_enabled: false, payment_provider: null, models: [{ code: "atomic-code", name: "ATOMIC CODE", description: "Modelo de programación", available_for_chat: true, billing_candidate: true, billing_enabled: false }], plans: [], credit_packages: [] })));
  page.route("**/health**", route => {
    if (route.request().url().includes("/health/readiness")) return route.fulfill(studioJson({ status: "ok" }));
    return route.fulfill(studioJson({ status: "ok" }));
  });
  page.route("**/workspace/usage**", route => route.fulfill(studioJson({ totals: { requests: 3, prompt_tokens: 900, output_tokens: 300, unavailable_measurements: 0 }, items: [] })));
  page.route("**/billing/orders**", route => route.fulfill(studioJson({ items: [] })));
  page.route("**/billing/credits", route => route.fulfill(studioJson({ provisioned: false, totals: { available: 0, reserved: 0, consumed: 0 }, recent_ledger: [] })));
};

const browser = await chromium.launch({ headless: true });

const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
const routeAdminMocks = (page) => {
  page.route("**/auth/me", route => route.fulfill(json({ user: { id: "admin-1", email: "admin@example.test", display_name: "Admin" } })));
  page.route("**/admin/**", route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    let body = {};
    if (url.pathname === "/admin/access/me") {
      body = { administration_enabled: true, mutations_enabled: true, roles: ["platform_admin"], permissions: ["admin.access.read", "billing.read", "billing.manage", "users.read", "users.manage", "audit.read"] };
    } else if (url.pathname === "/admin/audit") body = { events: [] };
    else if (url.pathname === "/admin/users") body = { users: [], pagination: { total: 0, limit: 50, offset: 0, has_more: false } };
    else if (url.pathname === "/admin/billing/overview") body = { reservations: [], ledger: [], executions: [], usage: [] };
    else if (url.pathname === "/admin/billing/executions") body = { executions: [], pagination: { total: 0, limit: 25, offset: 0, has_more: false } };
    else if (url.pathname.endsWith("/roles")) body = method === "POST" ? { user_id: "user-1", role: "billing_readonly", status: "granted" } : { user_id: "user-1", assignments: [] };
    else if (url.pathname.endsWith("/status")) body = { user_id: "user-1", status: "disabled" };
    route.fulfill(json(body));
  });
};

try {
  for (const hash of ["#app/inicio", "#app/facturacion"]) {
    const studioPage = await browser.newPage();
    routeStudioMocks(studioPage);
    await studioPage.goto(baseUrl + "/" + hash);
    await studioPage.waitForLoadState("networkidle");
    if (hash === "#app/inicio") {
      await studioPage.getByRole("heading", { name: /Axyron Atomic/ }).waitFor({ timeout: 5000 }).catch(() => {});
    }
    await studioPage.waitForTimeout(500);
    await studioPage.addScriptTag({ content: axeSource });
    const studioReport = await studioPage.evaluate(async () => {
      // eslint-disable-next-line no-undef
      const results = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } });
      return results.violations.map(v => ({ id: v.id, impact: v.impact, description: v.description, nodes: v.nodes.length, target: v.nodes.slice(0, 2).map(n => n.target.join(" ")) }));
    });
    console.log(`\n=== / (autenticado, studio ${hash}) — ${studioReport.length} violaciones ===`);
    for (const v of studioReport) {
      console.log(`- [${v.impact}] ${v.id}: ${v.description} (${v.nodes} nodos) ${v.target.join(" | ")}`);
    }
    await studioPage.close();
  }

  const managePage = await browser.newPage();
  routeAdminMocks(managePage);
  await managePage.goto(baseUrl + "/admin-test");
  await managePage.getByRole("heading", { name: "Gestión de usuarios y roles" }).waitFor();
  await managePage.waitForLoadState("networkidle");
  await managePage.addScriptTag({ content: axeSource });
  const manageReport = await managePage.evaluate(async () => {
    // eslint-disable-next-line no-undef
    const results = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } });
    return results.violations.map(v => ({ id: v.id, impact: v.impact, description: v.description, nodes: v.nodes.length, target: v.nodes.slice(0, 2).map(n => n.target.join(" ")) }));
  });
  console.log(`\n=== /admin-test (autenticado, gestión) — ${manageReport.length} violaciones ===`);
  for (const v of manageReport) {
    console.log(`- [${v.impact}] ${v.id}: ${v.description} (${v.nodes} nodos) ${v.target.join(" | ")}`);
  }
  await managePage.close();

  for (const path of ["/", "/admin-test"]) {
    const page = await browser.newPage();
    await page.goto(baseUrl + path);
    await page.waitForLoadState("networkidle");
    await page.addScriptTag({ content: axeSource });
    const report = await page.evaluate(async () => {
      // eslint-disable-next-line no-undef
      const results = await axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa"] } });
      return results.violations.map(v => ({
        id: v.id,
        impact: v.impact,
        description: v.description,
        nodes: v.nodes.length,
        target: v.nodes.slice(0, 2).map(n => n.target.join(" ")),
      }));
    });
    console.log(`\n=== ${path} — ${report.length} violaciones ===`);
    for (const v of report) {
      console.log(`- [${v.impact}] ${v.id}: ${v.description} (${v.nodes} nodos) ${v.target.join(" | ")}`);
    }
    await page.close();
  }
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
