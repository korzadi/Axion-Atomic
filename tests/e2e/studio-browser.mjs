import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

const frontend = new URL("../../frontend/", import.meta.url);
const html = await readFile(new URL("Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html", frontend));
const workspaceJs = await readFile(new URL("workspace.js", frontend));
const studioJs = await readFile(new URL("studio.js", frontend));
const studioCss = await readFile(new URL("studio.css", frontend));
const adminHtml = await readFile(new URL("admin.html", frontend));
const adminJs = await readFile(new URL("admin.js", frontend));
const server = createServer((request, response) => {
  if (request.url === "/studio.js") {
    response.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
    response.end(studioJs);
    return;
  }
  if (request.url === "/studio.css") {
    response.writeHead(200, { "content-type": "text/css; charset=utf-8" });
    response.end(studioCss);
    return;
  }
  if (request.url === "/admin.js") {
    response.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
    response.end(adminJs);
    return;
  }
  if (request.url === "/admin-test") {
    response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    response.end(adminHtml);
    return;
  }
  if (request.url === "/workspace.js") {
    response.writeHead(200, { "content-type": "text/javascript; charset=utf-8" });
    response.end(workspaceJs);
    return;
  }
  response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  response.end(html);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const landingPageErrors = [];
  page.on("pageerror", error => landingPageErrors.push(error.message));
  await page.goto(baseUrl);
  await page.waitForLoadState("networkidle");
  await page.locator("#inicio h1:visible").waitFor();
  await page.locator("#inicio .robot img:visible").waitFor();
  await page.locator("#modelos:visible").waitFor();
  assert.deepEqual(landingPageErrors, [], "La landing no debe lanzar errores JavaScript");
  assert.equal(await page.locator("#workspace-app").isHidden(), true);
  assert.equal(await page.locator("#studio-shell").isHidden(), true);
  assert.equal(await page.locator("#studio-nav").isHidden(), true);
  assert.equal(await page.locator("#studio-root").count(), 1);
  assert.equal(await page.locator('link[href="/studio.css"]').count(), 1);
  assert.equal(await page.locator("#ws-chat-form").count(), 1);
  await page.getByRole("heading", { name: /Tu asistente de IA/ }).waitFor();
  await page.locator('[data-open="reg"]:visible').first().click();
  await page.locator("#e").waitFor();
  await page.locator("#terms").waitFor();
  assert.equal(await page.locator("#terms").isVisible(), true);
  assert.equal(await page.locator("#mfaRow").isVisible(), false);
  const hasFakeSession = await page.evaluate(() => localStorage.getItem("axyron-user"));
  assert.equal(hasFakeSession, null);
  assert.equal(await page.locator("#workspace-app").isHidden(), true);
  assert.equal(await page.locator("#workspace-app").textContent().then(text => text.includes("Atomic Code")), true);
  await page.locator("#cl").click();
  await page.locator('[data-open="login"]:visible').first().click();
  await page.locator("#e").waitFor();
  assert.equal(await page.locator("#termsRow").isVisible(), false);
  const adminPage = await browser.newPage();
  await adminPage.route("**/auth/me", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ user: { id: "test-user", email: "user@example.test", display_name: "Test User" } })
  }));
  await adminPage.route("**/admin/access/me", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ administration_enabled: false, mutations_enabled: false, roles: [], permissions: [] })
  }));
  await adminPage.route("**/auth/logout", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ status: "logged_out" })
  }));
  await adminPage.route("**/auth/login", route => route.fulfill({
    status: 202, contentType: "application/json",
    body: JSON.stringify({ mfa_required: true, challenge_token: "opaque-test-challenge", expires_in: 300 })
  }));
  await adminPage.route("**/auth/mfa/challenge/verify", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ status: "authenticated", expires_in: 43200 })
  }));
  await adminPage.goto(baseUrl + "/admin-test");
  await adminPage.getByText("Acceso administrativo no autorizado").waitFor();
  assert.equal(await adminPage.locator("#logout").isVisible(), true);
  await adminPage.locator("#logout").click();
  await adminPage.locator("#login-form").waitFor({ state: "visible" });
  await adminPage.locator("#mfa-view").waitFor({ state: "hidden" });
  await adminPage.locator("#email").fill("user@example.test");
  await adminPage.locator("#password").fill("TestPassword123!");
  await adminPage.locator("#login-submit").click();
  await adminPage.locator("#login-form").waitFor({ state: "hidden" });
  await adminPage.locator("#mfa-view").waitFor({ state: "visible" });
  assert.equal(await adminPage.locator("#password").inputValue(), "");
  await adminPage.locator("#mfa-code").fill("123456");
  await adminPage.locator("#mfa-form button[type=submit]").click();
  await adminPage.getByText("Acceso administrativo no autorizado").waitFor();
  assert.equal(await adminPage.locator("#logout").isVisible(), true);
  await adminPage.close();
  const managePage = await browser.newPage();
  managePage.on("dialog", dialog => dialog.accept());
  await managePage.route("**/auth/me", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ user: { id: "admin-1", email: "admin@example.test", display_name: "Admin" } })
  }));
  await managePage.route("**/admin/**", route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    let body = {};
    if (url.pathname === "/admin/access/me") {
      body = {
        administration_enabled: true,
        mutations_enabled: true,
        roles: ["platform_admin"],
        permissions: ["admin.access.read", "billing.read", "billing.manage", "users.read", "users.manage", "audit.read"]
      };
    } else if (url.pathname === "/admin/audit") {
      body = { events: [] };
    } else if (url.pathname === "/admin/users") {
      body = { users: [], pagination: { total: 0, limit: 50, offset: 0, has_more: false } };
    } else if (url.pathname === "/admin/billing/overview") {
      body = { reservations: [], ledger: [], executions: [] };
    } else if (url.pathname === "/admin/billing/executions") {
      body = { executions: [], pagination: { total: 0, limit: 25, offset: 0, has_more: false } };
    } else if (url.pathname.endsWith("/roles")) {
      body = method === "POST"
        ? { user_id: "user-1", role: "billing_readonly", status: "granted" }
        : { user_id: "user-1", assignments: [] };
    } else if (url.pathname.endsWith("/status")) {
      body = { user_id: "user-1", status: "disabled" };
    }
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await managePage.goto(baseUrl + "/admin-test");
  await managePage.getByRole("heading", { name: "Gestión de usuarios y roles" }).waitFor();
  await managePage.locator("#um-user").fill("user-1");
  await managePage.locator("#um-reason").fill("Motivo administrativo verificado");
  await managePage.locator("#um-grant").click();
  await managePage.getByText("Rol billing_readonly concedido a user-1.").waitFor();
  await managePage.locator("#um-status").selectOption("disabled");
  await managePage.locator("#um-status-run").click();
  await managePage.getByText("Usuario user-1 ahora en estado disabled.").waitFor();
  await managePage.close();
  process.stdout.write("Axyron Atomic landing, admin MFA and user management browser E2E: passed\\n");
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
