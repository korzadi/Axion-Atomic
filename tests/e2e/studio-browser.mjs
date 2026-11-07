import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

const html = await readFile(new URL("../../frontend/Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html", import.meta.url));
const server = createServer((request, response) => {
  response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  response.end(html);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.goto(baseUrl);
  await page.getByRole("heading", { name: /Tu asistente de IA/ }).waitFor();
  await page.locator('[data-open="reg"]').first().click();
  await page.locator("#e").waitFor();
  await page.locator("#terms").waitFor();
  assert.equal(await page.locator("#terms").isVisible(), true);
  assert.equal(await page.locator("#mfaRow").isVisible(), false);
  const hasFakeSession = await page.evaluate(() => localStorage.getItem("axyron-user"));
  assert.equal(hasFakeSession, null);
  await page.locator("#cl").click();
  await page.locator('[data-open="login"]').first().click();
  await page.locator("#e").waitFor();
  assert.equal(await page.locator("#termsRow").isVisible(), false);
  process.stdout.write("Axyron Atomic landing browser E2E: passed\\n");
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
