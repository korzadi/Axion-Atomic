import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";

const html = await readFile(new URL("../../frontend/index.html", import.meta.url));
const server = createServer((request, response) => {
  if (request.url !== "/") {
    response.writeHead(404).end("Not found");
    return;
  }
  response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  response.end(html);
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const baseUrl = `http://127.0.0.1:${address.port}`;
const browser = await chromium.launch({ headless: true });

async function newPage(role = "owner") {
  const context = await browser.newContext();
  await context.addCookies([{ name: "axion_csrf", value: "csrf-browser-test", url: baseUrl }]);
  const page = await context.newPage();
  const user = { id: "browser-user", email: "browser@example.test", display_name: "Prueba AXION" };
  const projects = [{ id: "project-browser", name: "Proyecto navegador", role }];
  await page.route("**/auth/login", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ user })
  }));
  await page.route("**/auth/me", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ user })
  }));
  await page.route("**/auth/projects", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ items: projects })
  }));
  await page.route("**/billing/catalog", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ models: [], checkout_enabled: false })
  }));
  await page.route("**/auth/oauth/providers", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ google: true, github: false })
  }));
  await page.goto(baseUrl);
  await page.locator('[data-open="login"]').first().click();
  await page.locator("#email").fill(user.email);
  await page.locator("#password").fill("correct-horse-battery-1");
  await page.locator("#submitAuth").click();
  await page.locator("#workspace.show").waitFor();
  await page.getByRole("heading", { name: /Hola, Prueba AXION/ }).waitFor();
  return { context, page };
}

async function ownerCanUploadAndRefreshKnowledge() {
  const { context, page } = await newPage("owner");
  let uploadRequest;
  let sourceReads = 0;
  await page.route("**/workspace/knowledge/sources?*", route => {
    sourceReads += 1;
    const sources = sourceReads > 1
      ? [{ source_id: "source-browser", source: "manual.txt", chunks: 1 }]
      : [];
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({ sources, truncated: false })
    });
  });
  await page.route("**/workspace/knowledge/upload?*", async route => {
    uploadRequest = route.request();
    return route.fulfill({
      status: 200, contentType: "application/json",
      body: JSON.stringify({
        status: "indexed", project_id: "project-browser",
        source_id: "source-browser", source: "manual.txt", chunks: 1
      })
    });
  });
  await page.locator('[data-view="knowledge"]').click();
  await page.locator('#knowledgeProject option[value="project-browser"]').waitFor({ state: "attached" });
  await page.locator("#knowledgeFile").setInputFiles({
    name: "manual.txt", mimeType: "text/plain", buffer: Buffer.from("Contenido de prueba para AXION.")
  });
  assert.equal(await page.locator("#knowledgeUpload").isEnabled(), true);
  await page.locator("#knowledgeUpload").click();
  await page.locator("#knowledgeUploadNotice").getByText(/Documento indexado:/).waitFor();
  assert.ok(uploadRequest, "La interfaz no envió la solicitud HTTP de carga");
  assert.equal(uploadRequest.method(), "POST");
  assert.equal(uploadRequest.headers()["x-csrf-token"], "csrf-browser-test");
  assert.match(uploadRequest.headers()["content-type"], /^multipart\/form-data; boundary=/);
  assert.ok(sourceReads >= 2, "La lista de fuentes no se actualizó tras la carga");
  await context.close();
}

async function viewerCannotUpload() {
  const { context, page } = await newPage("viewer");
  await page.route("**/workspace/knowledge/sources?*", route => route.fulfill({
    status: 200, contentType: "application/json",
    body: JSON.stringify({ sources: [], truncated: false })
  }));
  await page.locator('[data-view="knowledge"]').click();
  await page.locator('#knowledgeProject option[value="project-browser"]').waitFor({ state: "attached" });
  await page.locator("#knowledgeFile").setInputFiles({
    name: "manual.txt", mimeType: "text/plain", buffer: Buffer.from("Solo lectura.")
  });
  assert.equal(await page.locator("#knowledgeUpload").isDisabled(), true);
  await context.close();
}

async function oauthRequiresTermsAcceptance() {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.route("**/auth/oauth/providers", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({ google: true, github: false })
  }));
  await page.goto(baseUrl);
  await page.locator('[data-open="login"]').first().click();
  await page.locator('[data-oauth="google"]').click();
  await page.getByText("Debes aceptar los términos", { exact: false }).waitFor();
  assert.equal(new URL(page.url()).pathname, "/");
  await context.close();
}

try {
  await ownerCanUploadAndRefreshKnowledge();
  await viewerCannotUpload();
  await oauthRequiresTermsAcceptance();
  process.stdout.write("AXION STUDIO browser E2E: 3 scenarios passed\\n");
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
