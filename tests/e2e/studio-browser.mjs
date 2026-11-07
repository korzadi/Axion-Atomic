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
  process.stdout.write("Axyron Atomic landing and admin MFA browser E2E: passed\\n");
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
