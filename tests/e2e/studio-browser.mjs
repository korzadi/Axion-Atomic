import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

const frontend = new URL("../../frontend/", import.meta.url);
const html = await readFile(new URL("Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html", frontend));
const workspaceJs = await readFile(new URL("workspace.js", frontend));
const studioJs = await readFile(new URL("studio.js", frontend));
const studioCss = await readFile(new URL("studio.css", frontend));
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
  await page.goto(baseUrl);
  await page.waitForLoadState("networkidle");
  assert.equal(await page.locator("#workspace-app").isHidden(), true);
  assert.equal(await page.locator("#studio-shell").isHidden(), true);
  assert.equal(await page.locator("#studio-nav").isHidden(), true);
  assert.equal(await page.locator("#studio-root").count(), 1);
  assert.equal(await page.locator('link[href="/studio.css"]').count(), 1);
  assert.equal(await page.locator("#ws-chat-form").count(), 1);
  await page.getByRole("heading", { name: /Tu asistente de IA/ }).waitFor();
  await page.locator('[data-open="reg"]').first().click();
  await page.locator("#e").waitFor();
  await page.locator("#terms").waitFor();
  assert.equal(await page.locator("#terms").isVisible(), true);
  assert.equal(await page.locator("#mfaRow").isVisible(), false);
  const hasFakeSession = await page.evaluate(() => localStorage.getItem("axyron-user"));
  assert.equal(hasFakeSession, null);
  assert.equal(await page.locator("#workspace-app").isHidden(), true);
  assert.equal(await page.locator("#workspace-app").textContent().then(text => text.includes("Atomic Code")), true);
  await page.locator("#cl").click();
  await page.locator('[data-open="login"]').first().click();
  await page.locator("#e").waitFor();
  assert.equal(await page.locator("#termsRow").isVisible(), false);
  process.stdout.write("Axyron Atomic landing browser E2E: passed\\n");
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
