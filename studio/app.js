"use strict";
/* Axyron Studio — aplicación independiente con rutas reales.
   Llama al mismo backend core que la web principal (sesión host-only por cookie,
   CSRF por cookie+encabezado, mismas rutas /workspace, /billing, /auth, /health).
   Sin frameworks ni paso de build: ES2020 puro. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const outlet = $("#st-outlet");
const landingBase = (() => {
  const meta = document.querySelector('meta[name="landing-origin"]');
  return meta ? meta.content.replace(/\/$/, "") : "https://axyronatomic.com";
})();

function csrf() {
  const m = document.cookie.match(/(?:^|; )axion_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const method = (options.method || "GET").toUpperCase();
  if (method !== "GET" && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (method !== "GET") headers.set("X-CSRF-Token", csrf());
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(data.detail || data.message || `HTTP ${response.status}`, response.status);
  return data;
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function usd(minor) { return `$${(Number(minor) / 100).toFixed(2)}`; }
function num(n) { return Number(n || 0).toLocaleString("es"); }
function notice(kind, text) {
  const el = document.createElement("div");
  el.className = `st-notice ${kind === "error" ? "st-error" : kind === "good" ? "st-good-notice" : ""}`;
  el.setAttribute("role", "status");
  el.textContent = text;
  return el;
}

/* ---------- Router: rutas reales con history API ---------- */

const routes = {
  dashboard: renderDashboard,
  projects: renderProjects,
  code: renderCode,
  knowledge: renderKnowledge,
  agent: renderAgent,
  models: renderModels,
  usage: renderUsage,
  billing: renderBilling,
  buy: renderBuy,
  account: renderAccount,
  security: renderSecurity,
  privacy: renderPrivacy,
  integrations: renderIntegrations,
  tools: renderTools,
};

const state = { user: null, projectId: null, projects: [] };

function route() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path.startsWith("/sso/callback")) return "sso-callback";
  const name = path === "/" || path === "/dashboard" ? "dashboard" : path.slice(1);
  return Object.prototype.hasOwnProperty.call(routes, name) ? name : "404";
}

async function navigate(path) {
  if (window.location.pathname + window.location.search !== path) {
    window.history.pushState({}, "", path);
  }
  await render();
}

async function render() {
  const name = route();
  updateNav(name);
  if (name === "404") return renderNotFound();
  if (name === "sso-callback") return renderSsoCallback();
  if (!state.user) return renderLogin();
  const renderer = routes[name] ?? renderNotFound;
  outlet.innerHTML = "";
  await renderer();
  $("#st-main", document).focus({ preventScroll: true });
}

function updateNav(name) {
  $$(".st-nav a").forEach((link) => {
    const active = link.dataset.page === name;
    link.classList.toggle("active", active);
    link.setAttribute("aria-current", active ? "page" : "false");
  });
}

window.addEventListener("popstate", render);

document.addEventListener("click", (event) => {
  const anchor = event.target.closest("a[href^='/']");
  if (!anchor) return;
  const href = anchor.getAttribute("href");
  if (href.startsWith("/api") || href.startsWith("/sso/callback")) return;
  if (anchor.target === "_blank" || anchor.hasAttribute("download")) return;
  event.preventDefault();
  navigate(href);
});

/* ---------- Autenticación compartida (SSO con la web principal) ---------- */

function landingSsoUrl() {
  return `${landingBase}/sso-start`;
}

async function renderLogin() {
  outlet.innerHTML = `
    <div class="st-view login-page">
      <div class="st-card">
        <p class="st-eyebrow">Acceso a Axyron Studio</p>
        <h1 class="st-title">Tu espacio ya te espera</h1>
        <p class="st-subtitle">Inicia sesión o entra con tu cuenta de Axyron Atomic.</p>
        <div id="st-login-status" aria-live="polite"></div>
        <form id="st-login-form" class="st-grid-form" novalidate style="margin-top:16px">
          <div class="st-field"><label for="st-email">Correo</label><input id="st-email" name="email" type="email" autocomplete="email" required></div>
          <div class="st-field"><label for="st-password">Contraseña</label><input id="st-password" name="password" type="password" autocomplete="current-password" required minlength="12"></div>
          <div class="st-field" id="st-mfa-field" style="display:none"><label for="st-mfa-code">Código MFA</label><input id="st-mfa-code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="10"></div>
          <button class="st-btn primary" type="submit" id="st-login-submit">Entrar</button>
        </form>
        <div style="display:grid;gap:10px;margin-top:16px">
          <a class="st-btn" href="${landingSsoUrl()}" style="justify-content:center">Entrar con AXYRON ATOMIC SSO</a>
          <a class="st-muted" href="${landingBase}/" style="text-align:center;font-size:.85rem">¿Sin cuenta? Regístrate en la web principal →</a>
        </div>
      </div>
    </div>`;
  const form = $("#st-login-form");
  const status = $("#st-login-status");
  let challengeToken = null;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = $("#st-login-submit");
    submit.disabled = true;
    status.innerHTML = "";
    const email = $("#st-email").value.trim();
    const password = $("#st-password").value;
    try {
      const mfaCode = $("#st-mfa-code").value.trim();
      if (challengeToken) {
        await api("/auth/mfa/challenge/verify", { method: "POST", body: JSON.stringify({ challenge_token: challengeToken, code: mfaCode }) });
        state.user = (await api("/auth/me")).user;
        await bootProjects();
        return navigate("/dashboard");
      }
      const response = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      if (response.mfa_required) {
        challengeToken = response.challenge_token;
        $("#st-mfa-field").style.display = "grid";
        $("#st-mfa-code").focus();
        status.appendChild(notice("", "Introduce el código MFA para terminar de entrar."));
      } else {
        state.user = response.user ?? (await api("/auth/me")).user;
        await bootProjects();
        await navigate("/dashboard");
      }
    } catch (error) {
      status.appendChild(notice("error", error.message || "No se pudo iniciar sesión"));
    } finally {
      submit.disabled = false;
    }
  });
}

async function renderSsoCallback() {
  outlet.innerHTML = `<div class="st-view login-page"><div class="st-card"><h1 class="st-title">Conectando con tu cuenta…</h1><div id="st-sso-status" aria-live="polite"><span class="st-spinner"></span></div></div></div>`;
  const status = $("#st-sso-status");
  try {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code") || "";
    const stateParam = params.get("state") || "";
    if (!code || !stateParam) throw new Error("Enlace de acceso incompleto");
    await api("/auth/sso/exchange", { method: "POST", body: JSON.stringify({ code, state: stateParam }) });
    state.user = (await api("/auth/me")).user;
    await bootProjects();
    history.replaceState({}, "", "/dashboard");
    return navigate("/dashboard");
  } catch (error) {
    status.innerHTML = `<div class="st-notice st-error" role="alert">No se pudo completar el acceso SSO. Vuelve a intentarlo desde la web principal.</div><p style="margin-top:14px"><a class="st-btn primary" href="${landingSsoUrl()}">Reintentar con SSO</a></p>`;
  }
}

async function bootProjects() {
  try {
    const data = await api("/auth/projects");
    state.projects = data.items || [];
    state.projectId = state.projects[0]?.id ?? null;
  } catch {
    state.projects = [];
    state.projectId = null;
  }
}

async function renderNotFound() {
  outlet.innerHTML = `<div class="st-view"><h1 class="st-title">404 — Página no encontrada</h1><p class="st-subtitle">Esa página no existe en Axyron Studio.</p><p style="margin-top:14px"><a class="st-btn primary" href="/dashboard">Volver al panel</a></p></div>`;
}

/* ---------- Utilidades compartidas por vistas ---------- */

function viewHead(eyebrow, title, subtitle) {
  return `<div class="st-head"><p class="st-eyebrow">${esc(eyebrow)}</p><h1 class="st-title">${esc(title)}</h1><p class="st-subtitle">${esc(subtitle)}</p></div>`;
}

function setOutlet(html) {
  outlet.innerHTML = html;
}

async function withError(promiseFactory, container) {
  try {
    await promiseFactory();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      state.user = null;
      return navigate(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
    const el = notice("error", error.message || "No se pudo completar la operación");
    (container ?? outlet).prepend(el);
  }
}

function projectSelectorHtml() {
  if (!state.projects.length) {
    return `<div class="st-empty">Aún no tienes proyectos. Crea uno desde <a href="/projects">Proyectos</a>.</div>`;
  }
  const options = state.projects.map((p) => `<option value="${esc(p.id)}" ${String(p.id) === String(state.projectId) ? "selected" : ""}>${esc(p.name)}</option>`).join("");
  return `<label class="st-muted" for="st-project" style="font-size:.82rem">Proyecto</label><select id="st-project" class="st-field" style="width:100%;border:1px solid var(--st-border);background:#080f20;color:var(--st-text);border-radius:10px;padding:10px">${options}</select>`;
}

function bindProjectSelector(onChange) {
  const select = $("#st-project");
  if (select) select.addEventListener("change", () => { state.projectId = select.value; onChange?.(select.value); });
}

/* ---------- Vistas ---------- */

async function renderDashboard() {
  setOutlet(`<div class="st-view">${viewHead("Resumen", "Panel de control", "Estado real de tu espacio y tu cuenta.")}
    <div class="st-grid">
      <div class="st-card third"><h3>Servicios</h3><div id="st-health" class="st-kpi">…</div><p class="st-muted" id="st-health-detail">Comprobando…</p></div>
      <div class="st-card third"><h3>Proyectos</h3><div class="st-kpi st-grad" id="st-project-count">—</div><p class="st-muted">con tu cuenta</p></div>
      <div class="st-card third"><h3>Facturación</h3><div class="st-kpi st-grad" id="st-billing-mode">—</div><p class="st-muted">modo actual del servidor</p></div>
      <div class="st-card"><h3>Accesos rápidos</h3><div class="st-row" style="justify-content:flex-start;gap:10px">
        <a class="st-btn" href="/code">Atomic Code</a>
        <a class="st-btn" href="/agent">Agente AXYRON</a>
        <a class="st-btn" href="/knowledge">Conocimiento</a>
        <a class="st-btn" href="/billing">Créditos y facturación</a>
        <a class="st-btn" href="/buy">Comprar créditos</a>
      </div></div>
    </div>
  </div>`);
  $("#st-project-count").textContent = num(state.projects.length);
  withError(async () => {
    const readiness = await api("/health/readiness");
    const ok = readiness.status === "ready";
    $("#st-health").textContent = ok ? "Operativo" : "Degradado";
    $("#st-health-detail").textContent = ok ? "Todos los servicios responden." : "Hay dependencias no disponibles.";
    $("#st-billing-mode").textContent = readiness.billing?.mode === "ledger" ? "Ledger real" : "Shadow (sombra)";
  }, outlet);
}

async function renderProjects() {
  setOutlet(`<div class="st-view">${viewHead("Proyectos", "Tus proyectos", "Crea, abre y usa tu entorno de trabajo.")}
    <div class="st-grid">
      <div class="st-card half"><h3>Crear proyecto</h3>
        <form id="st-project-form" class="st-grid-form">
          <div class="st-field"><label for="st-project-name">Nombre</label><input id="st-project-name" required minlength="2" maxlength="120" placeholder="Mi proyecto"></div>
          <button class="st-btn primary" type="submit">Crear</button>
        </form>
      </div>
      <div class="st-card half"><h3>Tus proyectos</h3><div id="st-project-list" class="st-list"><div class="st-empty">Cargando…</div></div></div>
    </div>
  </div>`);
  const list = $("#st-project-list");
  const render = async () => {
    list.innerHTML = state.projects.length
      ? state.projects.map((p) => `<div class="st-item"><div class="st-item-main"><div class="st-item-title">${esc(p.name)}</div><div class="st-item-meta">Rol: ${esc(p.role ?? "miembro")}</div></div><a class="st-btn" href="/code">Abrir</a></div>`).join("")
      : `<div class="st-empty">Todavía no hay proyectos.</div>`;
  };
  await render();
  $("#st-project-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("#st-project-name");
    try {
      const result = await api("/auth/projects", { method: "POST", body: JSON.stringify({ name: input.value.trim() }) });
      input.value = "";
      await bootProjects();
      await render();
      outlet.prepend(notice("good", "Proyecto creado."));
    } catch (error) {
      outlet.prepend(notice("error", error.message));
    }
  });
}

async function renderCode() {
  if (!state.projects.length) {
    setOutlet(`<div class="st-view">${viewHead("Atomic Code", "Atomic Code 1.1", "Tu agente de programación.")}<div class="st-empty">Primero crea un proyecto desde <a href="/projects">Proyectos</a>.</div></div>`);
    return;
  }
  const idempotencyKey = (() => {
    try { return (crypto.randomUUID && crypto.randomUUID()) || `axy-${Date.now()}`; } catch { return `axy-${Date.now()}`; }
  })();
  setOutlet(`<div class="st-view">${viewHead("Atomic Code", "Atomic Code 1.1", "Respuestas reales del modelo; nada se simula.")}
    <div class="st-grid">
      <div class="st-card">${projectSelectorHtml()}</div>
      <div class="st-card"><h3>Conversación</h3><div id="st-chat" class="st-chat" aria-live="polite"></div>
        <form id="st-chat-form" class="st-grid-form" style="margin-top:12px">
          <div class="st-field"><label for="st-chat-input">Mensaje</label><textarea id="st-chat-input" maxlength="8000" required placeholder="Describe lo que necesitas…"></textarea></div>
          <button class="st-btn primary" type="submit" id="st-chat-send">Enviar</button>
        </form>
        <p class="st-muted" id="st-chat-billing" style="margin-top:8px"></p>
      </div>
    </div>
  </div>`);
  const chat = $("#st-chat");
  const form = $("#st-chat-form");
  const input = $("#st-chat-input");
  const billingNote = $("#st-chat-billing");
  const loadHistory = async () => {
    chat.innerHTML = "";
    try {
      const data = await api(`/workspace/chat/history?project_id=${encodeURIComponent(state.projectId)}`);
      const messages = data.messages || [];
      if (!messages.length) chat.innerHTML = '<div class="st-empty">Aún no hay conversación.</div>';
      for (const message of messages.slice(-20)) {
        const bubble = document.createElement("div");
        bubble.className = `st-bubble ${message.role === "assistant" ? "assistant" : "user"}`;
        bubble.textContent = message.content;
        chat.appendChild(bubble);
      }
      chat.scrollTop = chat.scrollHeight;
    } catch (error) {
      chat.innerHTML = `<div class="st-empty">No se pudo cargar el historial.</div>`;
    }
  };
  bindProjectSelector(loadHistory);
  await loadHistory();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const content = input.value.trim();
    if (!content) return;
    const send = $("#st-chat-send");
    send.disabled = true;
    const userBubble = document.createElement("div");
    userBubble.className = "st-bubble user";
    userBubble.textContent = content;
    chat.appendChild(userBubble);
    input.value = "";
    try {
      const result = await api("/workspace/chat/completions", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({
          project_id: state.projectId,
          messages: [{ role: "user", content }],
          max_tokens: 1024,
          temperature: 0.2,
        }),
      });
      const answer = result.choices?.[0]?.message?.content ?? "(sin respuesta)";
      const bubble = document.createElement("div");
      bubble.className = "st-bubble assistant";
      bubble.textContent = answer;
      chat.appendChild(bubble);
      chat.scrollTop = chat.scrollHeight;
      const billing = result.usage_billing;
      if (billing?.mode === "ledger" && billing.charged) {
        billingNote.textContent = `${billing.credits_charged ?? "?"} créditos liquidados según el consumo medido.`;
      } else if (billing?.mode === "shadow") {
        billingNote.textContent = "Medición en modo sombra: no se cobraron créditos.";
      }
    } catch (error) {
      outlet.prepend(notice("error", error.message));
    } finally {
      send.disabled = false;
    }
  });
}

async function renderKnowledge() {
  if (!state.projects.length) {
    setOutlet(`<div class="st-view">${viewHead("Conocimiento", "Conocimiento del proyecto", "Indexa documentos con RAG aislado por proyecto.")}<div class="st-empty">Crea un proyecto primero desde <a href="/projects">Proyectos</a>.</div></div>`);
    return;
  }
  setOutlet(`<div class="st-view">${viewHead("Conocimiento", "Conocimiento del proyecto", "Texto y archivos, con aislamiento por proyecto.")}
    <div class="st-grid">
      <div class="st-card">${projectSelectorHtml()}</div>
      <div class="st-card half"><h3>Indexar texto</h3>
        <form id="st-ingest-form" class="st-grid-form">
          <div class="st-field"><label for="st-ingest-source">Nombre de la fuente</label><input id="st-ingest-source" maxlength="200" value="Nota"></div>
          <div class="st-field"><label for="st-ingest-body">Contenido</label><textarea id="st-ingest-body" maxlength="100000" required></textarea></div>
          <button class="st-btn primary" type="submit">Indexar</button>
        </form>
      </div>
      <div class="st-card half"><h3>Subir archivo</h3>
        <form id="st-upload-form" class="st-grid-form">
          <div class="st-field"><label for="st-upload-file">Archivo (.pdf, .docx, .txt, .md)</label><input id="st-upload-file" type="file" accept=".pdf,.docx,.txt,.md" required></div>
          <button class="st-btn" type="submit">Subir e indexar</button>
        </form>
        <p class="st-muted" style="margin-top:8px">El contenido se indexa aislado por proyecto.</p>
      </div>
      <div class="st-card"><h3>Fuentes del proyecto</h3><div id="st-sources" class="st-list"><div class="st-empty">Cargando…</div></div></div>
    </div>
  </div>`);
  const sourcesBox = $("#st-sources");
  const refresh = async () => {
    try {
      const data = await api(`/workspace/knowledge/sources?project_id=${encodeURIComponent(state.projectId)}`);
      const items = data.items || data.sources || [];
      sourcesBox.innerHTML = items.length
        ? items.map((s) => `<div class="st-item"><div class="st-item-main"><div class="st-item-title">${esc(s.source ?? s.name ?? "Fuente")}</div><div class="st-item-meta">${esc(s.source_id ?? s.id ?? "")} · ${num(s.chunks)} fragmentos</div></div><button class="st-btn danger" data-delete="${esc(s.source_id ?? s.id)}">Eliminar</button></div>`).join("")
        : `<div class="st-empty">Sin fuentes indexadas.</div>`;
      sourcesBox.querySelectorAll("[data-delete]").forEach((button) => button.addEventListener("click", async () => {
        if (!confirm("¿Eliminar esta fuente del proyecto?")) return;
        try {
          await api(`/workspace/knowledge/sources/${encodeURIComponent(button.dataset.delete)}?project_id=${encodeURIComponent(state.projectId)}`, { method: "DELETE" });
          await refresh();
        } catch (error) { outlet.prepend(notice("error", error.message)); }
      }));
    } catch {
      sourcesBox.innerHTML = `<div class="st-empty">No se pudieron cargar las fuentes.</div>`;
    }
  };
  bindProjectSelector(refresh);
  await refresh();
  $("#st-ingest-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = $("#st-ingest-body").value.trim();
    const source = $("#st-ingest-source").value.trim() || "Nota";
    try {
      const result = await api("/workspace/knowledge/ingest", { method: "POST", body: JSON.stringify({ project_id: state.projectId, source, text: body }) });
      outlet.prepend(notice("good", `Texto indexado: ${result.chunks ?? 0} fragmentos.`));
      $("#st-ingest-body").value = "";
      await refresh();
    } catch (error) { outlet.prepend(notice("error", error.message)); }
  });
  $("#st-upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const fileInput = $("#st-upload-file");
    const file = fileInput.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const result = await api(`/workspace/knowledge/upload?project_id=${encodeURIComponent(state.projectId)}`, { method: "POST", body: formData });
      outlet.prepend(notice("good", `Archivo indexado: ${result.chunks ?? 0} fragmentos.`));
      fileInput.value = "";
      await refresh();
    } catch (error) { outlet.prepend(notice("error", error.message)); }
  });
}

async function renderAgent() {
  if (!state.projects.length) {
    setOutlet(`<div class="st-view">${viewHead("Agente", "Agente AXYRON", "Ejecuciones supervisadas con aprobación humana.")}<div class="st-empty">Crea un proyecto primero desde <a href="/projects">Proyectos</a>.</div></div>`);
    return;
  }
  setOutlet(`<div class="st-view">${viewHead("Agente", "Agente AXYRON", "Planifica, propone y ejecuta con tu aprobación explícita.")}
    <div class="st-grid">
      <div class="st-card">${projectSelectorHtml()}</div>
      <div class="st-card half"><h3>Iniciar tarea</h3>
        <form id="st-agent-form" class="st-grid-form">
          <div class="st-field"><label for="st-goal">Objetivo</label><textarea id="st-goal" maxlength="10000" minlength="5" required placeholder="Describe qué debe hacer Axyron…"></textarea></div>
          <button class="st-btn primary" type="submit">Iniciar tarea</button>
        </form>
      </div>
      <div class="st-card half"><h3>Ejecuciones recientes</h3><div id="st-runs" class="st-list"><div class="st-empty">Cargando…</div></div></div>
    </div>
  </div>`);
  const runsBox = $("#st-runs");
  const refresh = async () => {
    try {
      const data = await api(`/workspace/agent/runs?project_id=${encodeURIComponent(state.projectId)}`);
      const runs = data.items || [];
      runsBox.innerHTML = runs.length
        ? runs.map((run) => `<div class="st-item"><div class="st-item-main"><div class="st-item-title">${esc(run.goal)}</div><div class="st-item-meta">${esc(run.status)} · ${esc(run.updated_at ?? "")}</div></div>${run.status === "awaiting_approval" ? '<a class="st-btn" href="#approve">Revisar</a>' : ""}</div>`).join("")
        : `<div class="st-empty">Sin ejecuciones aún.</div>`;
    } catch { runsBox.innerHTML = `<div class="st-empty">No se pudieron cargar las ejecuciones.</div>`; }
  };
  bindProjectSelector(refresh);
  await refresh();
  $("#st-agent-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const goal = $("#st-goal").value.trim();
    if (goal.length < 5) return;
    try {
      const run = await api("/workspace/agent/runs", { method: "POST", body: JSON.stringify({ project_id: state.projectId, goal }) });
      outlet.prepend(notice("good", `Tarea creada: ${run.status}`));
      $("#st-goal").value = "";
      await refresh();
    } catch (error) { outlet.prepend(notice("error", error.message)); }
  });
}

async function renderModels() {
  setOutlet(`<div class="st-view">${viewHead("Modelos", "Modelos Atomic", "Catálogo del servidor y disponibilidad en tiempo real.")}
    <div class="st-grid"><div id="st-models" class="st-grid" style="grid-column:span 12"><div class="st-empty">Cargando catálogo…</div></div></div>
  </div>`);
  try {
    const catalog = await api("/billing/catalog");
    const box = $("#st-models");
    box.innerHTML = catalog.models.map((model) => `<div class="st-card third"><div class="st-ico" style="font-size:1.5rem">⌘</div><h3>${esc(model.name)}</h3><p class="st-muted">${esc(model.description)}</p><p style="margin-top:10px"><span class="st-pill ${model.available_for_chat ? "good" : "warn"}">${model.available_for_chat ? "Disponible" : "Próxima actualización"}</span></p></div>`).join("")
      + `<div class="st-card"><h3>Disponibilidad del runtime</h3><p class="st-muted">Comprueba contra Ollama si el chat está listo ahora mismo.</p><button class="st-btn primary" id="st-models-check">Comprobar disponibilidad</button><div id="st-models-result" class="st-muted" aria-live="polite" style="margin-top:10px"></div></div>`;
    $("#st-models-check").addEventListener("click", async () => {
      const out = $("#st-models-result");
      out.textContent = "Comprobando…";
      try {
        const data = await api(`/workspace/models/availability?project_id=${encodeURIComponent(state.projectId ?? "")}`);
        out.textContent = (data.models ?? []).map((m) => `${m.code}: ${m.available === true ? "disponible" : "no disponible"}`).join(" · ") || "Sin datos.";
      } catch (error) { out.textContent = error.message; }
    });
  } catch (error) { outlet.prepend(notice("error", error.message)); }
}

async function renderUsage() {
  if (!state.projects.length) {
    setOutlet(`<div class="st-view">${viewHead("Consumo", "Consumo del proyecto", "Medición real de tokens.")}<div class="st-empty">Crea un proyecto primero desde <a href="/projects">Proyectos</a>.</div></div>`);
    return;
  }
  setOutlet(`<div class="st-view">${viewHead("Consumo", "Consumo del proyecto", "Datos medidos desde PostgreSQL.")}
    <div class="st-grid">
      <div class="st-card">${projectSelectorHtml()}</div>
      <div class="st-card"><h3>Indicadores</h3><div class="st-grid" id="st-usage-kpi"><div class="st-empty">Cargando…</div></div></div>
    </div>
  </div>`);
  const load = async () => {
    try {
      const data = await api(`/workspace/usage?project_id=${encodeURIComponent(state.projectId)}&limit=50`);
      const totals = data.totals ?? {};
      $("#st-usage-kpi").innerHTML = [
        ["Peticiones", totals.requests ?? 0],
        ["Tokens de entrada", totals.prompt_tokens ?? "No medido"],
        ["Tokens de salida", totals.output_tokens ?? "No medido"],
        ["Sin disponibilidad", totals.unavailable_measurements ?? 0],
      ].map(([k, v]) => `<div class="st-card third"><div class="st-muted">${esc(k)}</div><div class="st-kpi">${esc(v)}</div></div>`).join("");
    } catch (error) { $("#st-usage-kpi").innerHTML = `<div class="st-empty">${esc(error.message)}</div>`; }
  };
  bindProjectSelector(load);
  await load();
}

async function renderBilling() {
  setOutlet(`<div class="st-view">${viewHead("Créditos y facturación", "Créditos y facturación", "Saldo real, movimientos y órdenes — todo desde PostgreSQL.")}
    <div class="st-grid">
      <div class="st-card third"><h3>Saldo</h3><div class="st-kpi st-grad" id="st-credits">—</div><p class="st-muted" id="st-credits-detail"></p></div>
      <div class="st-card half"><h3>Movimientos del ledger</h3><div id="st-ledger" class="st-table-wrap"><div class="st-empty">Cargando…</div></div></div>
      <div class="st-card half"><h3>Historial de órdenes</h3><div id="st-orders" class="st-table-wrap"><div class="st-empty">Cargando…</div></div></div>
    </div>
  </div>`);
  const render = async () => {
    try {
      const credits = await api("/billing/credits");
      $("#st-credits").textContent = num(credits.totals?.available ?? 0);
      $("#st-credits-detail").textContent = credits.provisioned ? `Reservados: ${num(credits.totals?.reserved)} · Consumidos: ${num(credits.totals?.consumed)}` : "Sin provisión; verifica tu correo para la concesión FREE.";
      $("#st-ledger").innerHTML = (credits.recent_ledger ?? []).length
        ? `<table class="st-table"><thead><tr><th>Fecha</th><th>Tipo</th><th>Δ Disponible</th></tr></thead><tbody>${credits.recent_ledger.map((e) => `<tr><td>${esc(e.created_at ?? "")}</td><td>${esc(e.event_type)}</td><td>${esc(e.available_delta)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="st-empty">Sin movimientos aún.</div>`;
    } catch (error) { $("#st-ledger").innerHTML = `<div class="st-empty">${esc(error.message)}</div>`; }
    try {
      const orders = await api("/billing/orders?limit=50");
      $("#st-orders").innerHTML = (orders.items ?? []).length
        ? `<table class="st-table"><thead><tr><th>Producto</th><th>Importe</th><th>Créditos</th><th>Estado</th></tr></thead><tbody>${orders.items.map((o) => `<tr><td>${esc(o.product_code)}</td><td>${usd(o.amount_minor)} ${esc(o.currency)}</td><td>${esc(o.credits)}</td><td>${esc(o.status)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="st-empty">Aún no hay órdenes.</div>`;
    } catch (error) { $("#st-orders").innerHTML = `<div class="st-empty">${esc(error.message)}</div>`; }
  };
  await render();
}

async function renderBuy() {
  setOutlet(`<div class="st-view">${viewHead("Comprar", "Comprar créditos", "Compra única vía Lightning; acreditación tras confirmación.")}
    <div class="st-buy-grid" id="st-plans"><div class="st-empty">Cargando catálogo…</div></div>
    <div id="st-buy-status" aria-live="polite" style="margin-top:14px"></div>
    <div id="st-checkout-invoice" hidden style="margin-top:14px"></div>
  </div>`);
  const params = new URLSearchParams(window.location.search);
  const selected = params.get("plan");
  const statusBox = $("#st-buy-status");
  const showInvoice = (order) => {
    const box = $("#st-checkout-invoice");
    box.innerHTML = `<div class="st-card"><h3>Factura Lightning</h3><p class="st-muted">Copia la factura y paga desde tu monedero Lightning.</p><label class="st-muted" for="st-pr">Factura (bolt11)</label><textarea id="st-pr" class="st-mono" readonly style="width:100%;min-height:110px;border:1px solid var(--st-border);background:#080f20;color:var(--st-text);border-radius:10px;padding:10px">${esc(order.bolt11)}</textarea><p class="st-muted">Referencia: <code>${esc(order.reference)}</code> · ${num(order.amount_sats)} sats · Caduca: ${esc(order.expires_at)}</p><div class="st-row" style="justify-content:flex-start;gap:10px"><button class="st-btn primary" id="st-copy-pr">Copiar factura</button><a class="st-btn" href="lightning:${esc(order.bolt11)}">Abrir en monedero</a><button class="st-btn" id="st-verify-payment">Confirmar pago</button></div></div>`;
    box.hidden = false;
    $("#st-copy-pr").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      try {
        await navigator.clipboard.writeText(order.bolt11);
        button.textContent = "Factura copiada";
      } catch {
        $("#st-pr").focus(); $("#st-pr").select(); button.textContent = "Selecciona y copia";
      }
      setTimeout(() => { button.textContent = "Copiar factura"; }, 2200);
    });
    $("#st-verify-payment").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      statusBox.innerHTML = notice("", "Confirmando el pago con QvaPay…").outerHTML;
      try {
        const result = await api(`/billing/checkout/orders/${encodeURIComponent(order.order_id)}/verify`, { method: "POST" });
        statusBox.innerHTML = result.paid
          ? notice("good", "Pago confirmado. Los créditos quedaron acreditados en tu saldo.").outerHTML
          : notice("", "Aún no detectamos el pago; si ya pagaste, espera unos segundos y confirma de nuevo.").outerHTML;
        if (result.paid) setTimeout(() => navigate("/billing"), 1500);
      } catch (error) {
        statusBox.innerHTML = notice("error", error.message).outerHTML;
        button.disabled = false;
      }
    });
  };
  try {
    const catalog = await api("/billing/catalog");
    const box = $("#st-plans");
    box.innerHTML = catalog.plans.map((p) => `<div class="st-plan"><h3>${esc(p.name)}</h3><div class="st-kpi st-grad">${esc(num(p.credits))}</div><p class="st-muted">créditos · ${usd(p.price_minor)} USD · ${esc(p.description ?? "")}</p><button class="st-btn primary st-buy-btn" data-code="${esc(p.code)}">Comprar</button></div>`).join("");
    box.querySelectorAll(".st-buy-btn").forEach((button) => button.addEventListener("click", async () => {
      statusBox.innerHTML = notice("", "Creando la orden y la factura…").outerHTML;
      try {
        const order = await api("/billing/checkout/orders", { method: "POST", body: JSON.stringify({ product_code: button.dataset.code }) });
        statusBox.innerHTML = notice("", "Factura creada. Págala desde tu monedero Lightning.").outerHTML;
        showInvoice(order);
      } catch (error) { statusBox.innerHTML = notice("error", error.message).outerHTML; }
    }));
    if (selected) {
      const plan = catalog.plans.find((p) => p.code === selected);
      if (plan) $("#st-plans").querySelector(`[data-code="${CSS.escape(plan.code)}"]`)?.click();
    }
  } catch (error) { $("#st-plans").innerHTML = `<div class="st-empty">${esc(error.message)}</div>`; }
}

async function renderAccount() {
  setOutlet(`<div class="st-view">${viewHead("Cuenta", "Cuenta y seguridad", "Tu identidad, tu sesión y tu segundo factor.")}
    <div class="st-grid">
      <div class="st-card half"><h3>Tu cuenta</h3><div id="st-account" class="st-list"><div class="st-empty">Cargando…</div></div></div>
      <div class="st-card half"><h3>Autenticación multifactor</h3><div id="st-mfa" class="st-list"><div class="st-empty">Cargando…</div></div></div>
    </div>
  </div>`);
  try {
    const me = await api("/auth/me");
    $("#st-account").innerHTML = `<div class="st-item"><div class="st-item-main"><div class="st-item-title">${esc(me.user.display_name ?? me.user.email)}</div><div class="st-item-meta">${esc(me.user.email)}</div></div><span class="st-pill good">Sesión activa</span></div>`;
  } catch { $("#st-account").innerHTML = `<div class="st-empty">No se pudo cargar tu perfil.</div>`; }
  try {
    const mfa = await api("/auth/mfa/status");
    const box = $("#st-mfa");
    if (mfa.enabled) {
      box.innerHTML = `<div class="st-item"><div class="st-item-main"><div class="st-item-title">MFA activo</div><div class="st-item-meta">Tu cuenta usa autenticador TOTP.</div></div><span class="st-pill good">Activado</span></div>`;
      return;
    }
    box.innerHTML = `
      <div class="st-item"><div class="st-item-main"><div class="st-item-title">MFA sin configurar</div><div class="st-item-meta">Protege tu cuenta con un autenticador.</div></div><span class="st-pill warn">No activado</span></div>
      <button class="st-btn primary" id="st-mfa-start">Configurar MFA</button>
      <div id="st-mfa-setup" aria-live="polite"></div>`;
    $("#st-mfa-start").addEventListener("click", async () => {
      try {
        const enroll = await api("/auth/mfa/enroll", { method: "POST", body: "{}" });
        $("#st-mfa-setup").innerHTML = `
          <div class="st-notice">Añade esta clave en tu autenticador (Google Authenticator, Aegis…):<br><code class="st-mono" style="word-break:break-all">${esc(enroll.secret)}</code></div>
          <form id="st-mfa-confirm" class="st-grid-form" style="margin-top:10px">
            <div class="st-field"><label for="st-mfa-code">Código de 6 dígitos</label><input id="st-mfa-code" inputmode="numeric" maxlength="6" required pattern="[0-9]{6}"></div>
            <button class="st-btn primary" type="submit">Activar MFA</button>
          </form>`;
        $("#st-mfa-confirm").addEventListener("submit", async (event) => {
          event.preventDefault();
          try {
            const confirmed = await api("/auth/mfa/confirm", { method: "POST", body: JSON.stringify({ code: $("#st-mfa-code").value.trim() }) });
            $("#st-mfa-setup").innerHTML = `<div class="st-notice st-good-notice"><strong>MFA activado.</strong> Códigos de recuperación (guárdalos, se muestran una sola vez):<br><code class="st-mono">${(confirmed.recovery_codes ?? []).map(esc).join("<br>")}</code></div>`;
          } catch (error) { outlet.prepend(notice("error", error.message)); }
        });
      } catch (error) { outlet.prepend(notice("error", error.message)); }
    });
  } catch { $("#st-mfa").innerHTML = `<div class="st-empty">No se pudo consultar el estado MFA.</div>`; }
}

async function renderSecurity() {
  setOutlet(`<div class="st-view">${viewHead("Seguridad", "Seguridad de la cuenta", "Qué está protegido hoy y por qué.")}
    <div class="st-grid">
      <div class="st-card half"><h3>MFA</h3><div id="st-sec-mfa" class="st-muted">Consultando…</div></div>
      <div class="st-card half"><h3>Sesiones</h3><p class="st-muted">Tus sesiones usan cookies HttpOnly y Secure, con rotación al entrar y CSRF en cada mutación. Cerrar sesión aquí revoca esta sesión.</p><button class="st-btn" id="st-logout">Cerrar sesión</button></div>
      <div class="st-card"><h3>Controles del servidor</h3><ul class="st-muted">
        <li>Sesiones con expiración y revocación.</li>
        <li>CSRF obligatorio en operaciones de escritura.</li>
        <li>Aislamiento por proyecto y autorización por rol.</li>
        <li>Sandbox Docker aislado con red deshabilitada (AGT-04 verificado).</li>
        <li>Aprobación humana para acciones sensibles del agente.</li>
      </ul></div>
    </div>
  </div>`);
  try {
    const mfa = await api("/auth/mfa/status");
    $("#st-sec-mfa").textContent = mfa.enabled ? "MFA activado: tu cuenta exige segundo factor al entrar." : "MFA sin configurar: actívalo desde Cuenta.";
  } catch { $("#st-sec-mfa").textContent = "No se pudo consultar MFA."; }
  $("#st-logout").addEventListener("click", async () => {
    try { await api("/auth/logout", { method: "POST", body: "{}" }); } catch {}
    state.user = null;
    await navigate("/login");
  });
}

async function renderPrivacy() {
  setOutlet(`<div class="st-view">${viewHead("Privacidad", "Privacidad y datos", "Qué hace Axyron con tu información.")}
    <div class="st-grid">
      <div class="st-card"><h3>Datos medidos</h3><ul class="st-muted">
        <li>Los contadores de tokens se guardan asociados a tu usuario y proyecto (tabla <code>inference_usage_events</code>), sin prompts ni respuestas.</li>
        <li>El historial de chat se guarda cifrado en reposo por proyecto y puede borrarse con el proyecto.</li>
        <li>RAG aísla documentos y fragmentos por proyecto.</li>
      </ul></div>
      <div class="st-card"><h3>Disponibilidad de derechos</h3><p class="st-muted">Exportación y eliminación completa de datos personales están en desarrollo; no hay autoservicio aún. Para solicitudes de privacidad, escribe a la dirección de contacto publicada por el operador de la instancia.</p><span class="st-pill warn">Parcial</span></div>
      <div class="st-card"><h3>Legal</h3><p class="st-muted">Los términos y la política de privacidad se publicarán en la web principal antes del lanzamiento comercial. Consulta con el operador de la instancia.</p></div>
    </div>
  </div>`);
}

async function renderIntegrations() {
  setOutlet(`<div class="st-view">${viewHead("API e integraciones", "API e integraciones", "Qué hay disponible hoy.")}
    <div class="st-grid">
      <div class="st-card"><h3>API propia (compatible con OpenAI)</h3><p class="st-muted">Endpoints bajo <code>/workspace</code> e <code>/auth</code>, autenticados por cookie de sesión o herencia del proveedor; el uso heredado <code>/v1/*</code> está desactivado por defecto.</p><span class="st-pill good">Disponible</span></div>
      <div class="st-card"><h3>Atomic Video / Vision / Reasoning</h3><p class="st-muted">Modelos de generación y visión en desarrollo. No están disponibles ni se ofrecen hoy.</p><span class="st-pill warn">Próxima actualización</span></div>
      <div class="st-card"><h3>AXYRON CONNECT · Plugin Hub · Tool Registry</h3><p class="st-muted">Conectores, plugins y herramientas de terceros requieren permisos, verificación y pruebas. Aún no están activados.</p><span class="st-pill warn">Próxima actualización</span></div>
    </div>
  </div>`);
}

async function renderTools() {
  setOutlet(`<div class="st-view">${viewHead("Herramientas", "Herramientas del agente", "Qué puede hacer Axyron hoy por ti.")}
    <div class="st-grid">
      <div class="st-card"><h3>Ejecuciones supervisadas</h3><ul class="st-muted">
        <li>Plan y aprobación humana por cada acción sensible.</li>
        <li>Ejecuciones persistentes y recuperables con reconciliación manual.</li>
        <li>Cancelación con motivo auditado.</li>
      </ul></div>
      <div class="st-card"><h3>Sandbox Docker (AGT-04)</h3><ul class="st-muted">
        <li>Daemon dedicado userns-remapped con TLS; imagen fijada por digest.</li>
        <li>Sin red saliente, rootfs de solo lectura, uid/GID no root, sin sockets Docker.</li>
      </ul><span class="st-pill good">Verificado</span></div>
      <div class="st-card"><h3>Terminal desde el navegador</h3><p class="st-muted">No disponible. La ejecución real ocurre solo tras aprobación humana vía el agente con sandbox habilitado.</p><span class="st-pill warn">Ausente</span></div>
    </div>
  </div>`);
}

/* ---------- Arranque ---------- */

document.querySelectorAll('a[href^="/"]').forEach((link) => {
  const href = link.getAttribute("href");
  if (href && href.startsWith("/") && !href.startsWith("/api") && !href.startsWith("/sso")) {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(href);
    });
  }
});

(async function boot() {
  try {
    const me = await api("/auth/me");
    state.user = me.user;
    await bootProjects();
  } catch {
    state.user = null;
  }
  await render();
})();
