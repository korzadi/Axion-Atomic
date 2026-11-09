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
  if (!response.ok) {
    const error = new ApiError(data.detail || data.message || `HTTP ${response.status}`, response.status);
    error.data = data;
    throw error;
  }
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
  if (path === "/login" || path === "/sso/callback") return path.slice(1);
  const name = path === "/" || path === "/dashboard" ? "dashboard" : path.slice(1);
  return Object.prototype.hasOwnProperty.call(routes, name) ? name : "404";
}

async function navigate(path) {
  const url = new URL(path, window.location.origin);
  if (window.location.pathname + window.location.search !== url.pathname + url.search) {
    window.history.pushState({}, "", url.pathname + url.search);
  }
  await render();
}

async function render() {
  const name = route();
  updateNav(name);
  if (name === "404") return renderNotFound();
  if (name === "sso-callback" || name === "sso/callback") return renderSsoCallback();
  if (!state.user) {
    if (name !== "login" && name !== "sso-callback") history.replaceState({}, "", "/login?next=" + encodeURIComponent(window.location.pathname + window.location.search));
    return renderLogin();
  }
  if (name === "login") return navigate("/dashboard");
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
  return `${landingBase}/sso-start.html`;
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
        <div id="st-oauth-row" style="display:none;gap:10px;margin-top:16px">
          <div style="display:flex;align-items:center;gap:10px;color:var(--st-muted);font-size:.84rem"><span style="flex:1;height:1px;background:var(--st-border)"></span><span>o continúa con</span><span style="flex:1;height:1px;background:var(--st-border)"></span></div>
          <a id="st-oauth-google" class="st-btn" href="/auth/oauth/google/start" style="justify-content:center" rel="nofollow">Continuar con Google</a>
          <a id="st-oauth-github" class="st-btn" href="/auth/oauth/github/start" style="justify-content:center" rel="nofollow">Continuar con GitHub</a>
        </div>
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

  try {
    const p = await api("/auth/oauth/providers");
    const row = $("#st-oauth-row"), g = $("#st-oauth-google"), gh = $("#st-oauth-github");
    if (row && g && gh && p) {
      g.style.display = p.google ? "" : "none";
      gh.style.display = p.github ? "" : "none";
      row.style.display = (p.google || p.github) ? "grid" : "none";
    }
  } catch {}
}

async function renderSsoCallback() {
  outlet.innerHTML = `<div class="st-view login-page"><div class="st-card"><h1 class="st-title">Conectando con tu cuenta…</h1><div id="st-sso-status" aria-live="polite"><span class="st-spinner"></span></div></div></div>`;
  const status = $("#st-sso-status");
  try {
    const params = new URLSearchParams(window.location.search);
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const code = params.get("code") || fragment.get("code") || "";
    const stateParam = params.get("state") || fragment.get("state") || "";
    if (!code || !stateParam) throw new Error("Enlace de acceso incompleto");
    // El código es de un solo uso: se retira de la URL antes de cualquier
    // petición para no dejarlo en el historial, capturas ni referencias.
    history.replaceState({}, "", "/sso/callback");
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

function currentProject() {
  return state.projects.find((project) => String(project.id) === String(state.projectId)) ?? null;
}

function currentRole() {
  return currentProject()?.role ?? null;
}

function canDecide() {
  return ["owner", "admin"].includes(currentRole());
}

function canEdit() {
  return ["owner", "admin", "editor"].includes(currentRole());
}

/* ---------- Vistas ---------- */

async function renderDashboard() {
  setOutlet(`<div class="st-view">${viewHead("Resumen", "Panel de control", "Estado real de tu espacio y tu cuenta.")}
    <div class="st-grid">
      <div class="st-card third"><h3>Servicios</h3><div id="st-health" class="st-kpi">…</div><p class="st-muted" id="st-health-detail">Comprobando…</p></div>
      <div class="st-card third"><h3>Proyectos</h3><div class="st-kpi st-grad" id="st-project-count">—</div><p class="st-muted">con tu cuenta</p></div>
      <div class="st-card third"><h3>Facturación</h3><div class="st-kpi st-grad" id="st-billing-mode">—</div><p class="st-muted">modo actual del servidor</p></div>
      <div class="st-card third"><h3>Agente</h3><div class="st-kpi" id="st-agent-state">—</div><p class="st-muted" id="st-agent-detail">Sin proyecto activo</p></div>
      <div class="st-card third"><h3>Modelo</h3><div class="st-kpi" id="st-model-state">—</div><p class="st-muted" id="st-model-detail">Sin verificar</p></div>
      <div class="st-card third"><h3>Accesos rápidos</h3><div class="st-row" style="justify-content:flex-start;gap:10px">
        <a class="st-btn" href="/code">Atomic Code</a>
        <a class="st-btn" href="/agent">Agente AXYRON</a>
        <a class="st-btn" href="/knowledge">Conocimiento</a>
        <a class="st-btn" href="/billing">Créditos y facturación</a>
        <a class="st-btn" href="/buy">Comprar créditos</a>
      </div></div>
    </div>
  </div>`);
  $("#st-project-count").textContent = num(state.projects.length);
  try {
    const readiness = await api("/health/readiness");
    const ok = readiness.status === "ready";
    $("#st-health").textContent = ok ? "Operativo" : "Degradado";
    $("#st-health-detail").textContent = ok ? "Todos los servicios responden." : "Hay dependencias no disponibles.";
    $("#st-billing-mode").textContent = readiness.billing?.mode === "ledger" ? "Ledger real" : "Shadow (sombra)";
  } catch (error) {
    const report = error?.data ?? null;
    if (report && report.status) {
      $("#st-health").textContent = report.status === "ready" ? "Operativo" : "Degradado";
      const failing = Object.entries(report.dependencies ?? {}).filter(([, value]) => value !== "ok").map(([name]) => name);
      $("#st-health-detail").textContent = failing.length ? `Dependencias no disponibles: ${failing.join(", ")}.` : "El servidor reportó estado degradado.";
      $("#st-billing-mode").textContent = report.billing?.mode === "ledger" ? "Ledger real" : "Shadow (sombra)";
    } else {
      $("#st-health").textContent = "No disponible";
      $("#st-health-detail").textContent = error.message || "No se pudo consultar el estado del servidor.";
      $("#st-billing-mode").textContent = "No verificado";
    }
  }

  if (!state.projectId) {
    $("#st-agent-detail").textContent = "Crea o selecciona un proyecto para ver ejecuciones.";
    $("#st-model-detail").textContent = "Crea o selecciona un proyecto para verificar el runtime.";
    return;
  }
  try {
    const runs = await api(`/workspace/agent/runs?project_id=${encodeURIComponent(state.projectId)}&limit=1`);
    const last = (runs.items || [])[0];
    $("#st-agent-state").textContent = last ? last.status : "Sin ejecuciones";
    $("#st-agent-detail").textContent = last ? last.goal : "El agente todavía no ha ejecutado tareas en este proyecto.";
  } catch {
    $("#st-agent-state").textContent = "No disponible";
    $("#st-agent-detail").textContent = "No se pudo consultar el estado del agente.";
  }
  try {
    const availability = await api(`/workspace/models/availability?project_id=${encodeURIComponent(state.projectId)}`);
    const model = (availability.models || []).find((item) => item.code === "atomic-code");
    const available = model?.available === true;
    $("#st-model-state").textContent = available ? "Disponible" : "No disponible";
    $("#st-model-detail").textContent = available
      ? "El runtime confirmó el modelo configurado."
      : "Ollama no confirmó el modelo configurado.";
  } catch {
    $("#st-model-state").textContent = "No verificado";
    $("#st-model-detail").textContent = "No se pudo comprobar la disponibilidad del modelo.";
  }
}

async function renderProjects() {
  setOutlet(`<div class="st-view">${viewHead("Proyectos", "Tus proyectos", "Crea, abre y usa tu entorno de trabajo.")}
    <div class="st-grid">
      <div class="st-card half"><h3>Crear proyecto</h3>
        <form id="st-project-form" class="st-grid-form">
          <div class="st-field"><label for="st-project-name">Nombre</label><input id="st-project-name" required minlength="2" maxlength="120" placeholder="Mi proyecto"></div>
          <button class="st-btn primary" type="submit">Crear</button>
        </form>
        <p class="st-muted" style="margin-top:10px">El backend crea la propiedad y un workspace aislado. Si el almacenamiento falla, la operación falla de forma segura.</p>
      </div>
      <div class="st-card half"><h3>Tus proyectos</h3><div id="st-project-list" class="st-list"><div class="st-empty">Cargando…</div></div></div>
      <div class="st-card"><h3>Gestión disponible</h3><p class="st-muted">Puedes crear, listar, seleccionar y abrir proyectos. El backend actual no expone un endpoint de borrado de proyectos, por lo que esta aplicación no muestra un botón de eliminación que no haría nada.</p></div>
    </div>
  </div>`);
  const list = $("#st-project-list");
  const render = async () => {
    list.innerHTML = state.projects.length
      ? state.projects.map((project) => {
        const active = String(project.id) === String(state.projectId);
        return `<div class="st-item"><div class="st-item-main"><div class="st-item-title">${esc(project.name)} ${active ? '<span class="st-pill good">Activo</span>' : ""}</div><div class="st-item-meta">Rol: ${esc(project.role ?? "miembro")} · ${esc(project.created_at ?? "")}</div></div><div class="st-row"><button class="st-btn" data-select-project="${esc(project.id)}" ${active ? "disabled" : ""}>${active ? "Seleccionado" : "Seleccionar"}</button><button class="st-btn primary" data-open-project="${esc(project.id)}">Abrir</button></div></div>`;
      }).join("")
      : `<div class="st-empty">Todavía no hay proyectos.</div>`;
    list.querySelectorAll("[data-select-project]").forEach((button) => button.addEventListener("click", async () => {
      state.projectId = button.dataset.selectProject;
      await render();
      outlet.prepend(notice("good", "Proyecto seleccionado para el resto de módulos."));
    }));
    list.querySelectorAll("[data-open-project]").forEach((button) => button.addEventListener("click", async () => {
      state.projectId = button.dataset.openProject;
      await navigate("/code");
    }));
  };
  await render();
  $("#st-project-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("#st-project-name");
    try {
      const created = await api("/auth/projects", { method: "POST", body: JSON.stringify({ name: input.value.trim() }) });
      input.value = "";
      await bootProjects();
      if (created.project?.id) state.projectId = created.project.id;
      await render();
      outlet.prepend(notice("good", "Proyecto creado y seleccionado."));
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
  let history = [];
  let pendingKey = null;
  let pendingFingerprint = "";
  const newKey = () => {
    try { return (crypto.randomUUID && crypto.randomUUID()) || `axy-${Date.now()}`; } catch { return `axy-${Date.now()}`; }
  };
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
    billingNote.textContent = "";
    try {
      const data = await api(`/workspace/chat/history?project_id=${encodeURIComponent(state.projectId)}`);
      const messages = data.messages || [];
      history = messages;
      pendingKey = null;
      pendingFingerprint = "";
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
      const payload = {
        model: "atomic-code",
        project_id: state.projectId,
        messages: history.concat([{ role: "user", content }]),
        max_tokens: 1024,
        temperature: 0.2,
        stream: true,
      };
      const fingerprint = JSON.stringify({ ...payload, stream: false });
      if (!pendingKey || pendingFingerprint !== fingerprint) {
        pendingKey = newKey();
        pendingFingerprint = fingerprint;
      }
      const assistantBubble = document.createElement("div");
      assistantBubble.className = "st-bubble assistant";
      assistantBubble.textContent = "…";
      chat.appendChild(assistantBubble);
      chat.scrollTop = chat.scrollHeight;
      const applyBilling = (result) => {
        const billing = result && result.usage_billing;
        if (billing?.mode === "ledger" && billing.charged) {
          billingNote.textContent = `${billing.credits_charged ?? "?"} créditos liquidados según el consumo medido.`;
        } else if (billing?.mode === "shadow") {
          billingNote.textContent = "Medición en modo sombra: no se cobraron créditos.";
        }
      };
      let answer = "";
      let doneResult = null;
      try {
        const response = await fetch("/workspace/chat/completions", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf(),
            "Idempotency-Key": pendingKey,
            "Accept": "text/event-stream",
          },
          body: JSON.stringify(payload),
        });
        if (!response.ok || !response.headers.get("content-type")?.includes("text/event-stream")) {
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new ApiError(data.detail || data.message || `HTTP ${response.status}`, response.status);
          doneResult = data;
          answer = data.choices?.[0]?.message?.content ?? "(sin respuesta)";
        } else {
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const frames = buffer.split("\n\n");
            buffer = frames.pop() || "";
            for (const frame of frames) {
              const lines = frame.split("\n");
              let event = "message";
              const dataLines = [];
              for (const line of lines) {
                if (line.startsWith("event:")) event = line.slice(6).trim();
                else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
              }
              if (!dataLines.length) continue;
              let data;
              try { data = JSON.parse(dataLines.join("\n")); } catch { continue; }
              if (event === "message" && typeof data.delta === "string") {
                answer += data.delta;
                assistantBubble.textContent = answer;
                chat.scrollTop = chat.scrollHeight;
              } else if (event === "done") {
                doneResult = data;
                if (!answer) answer = data.choices?.[0]?.message?.content ?? "";
              } else if (event === "error") {
                throw new ApiError(data.detail || "Error de streaming", data.status_code || 503);
              }
            }
          }
        }
      } catch (streamError) {
        if (!(streamError instanceof ApiError) || streamError.status === 0) throw streamError;
        if (answer) { applyBilling(doneResult || {}); history = payload.messages.concat([{ role: "assistant", content: answer }]); pendingKey = null; pendingFingerprint = ""; throw streamError; }
        // fallback no-stream (compatibilidad)
        const fallback = await api("/workspace/chat/completions", {
          method: "POST",
          headers: { "Idempotency-Key": pendingKey },
          body: JSON.stringify({ ...payload, stream: false }),
        });
        doneResult = fallback;
        answer = fallback.choices?.[0]?.message?.content ?? "(sin respuesta)";
      }
      if (!answer) answer = "(sin respuesta)";
      assistantBubble.textContent = answer;
      history = payload.messages.concat([{ role: "assistant", content: answer }]);
      pendingKey = null;
      pendingFingerprint = "";
      chat.scrollTop = chat.scrollHeight;
      applyBilling(doneResult || {});
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
        <p class="st-muted" style="margin-top:10px">El runtime crea una ejecución persistente. Las acciones que modifican recursos requieren aprobación humana; no se ejecutan de forma silenciosa.</p>
      </div>
      <div class="st-card half"><h3>Ejecuciones</h3><div id="st-runs" class="st-list"><div class="st-empty">Cargando…</div></div></div>
      <div class="st-card"><h3>Aprobaciones pendientes</h3><div id="st-approvals" class="st-list"><div class="st-empty">Cargando…</div></div></div>
      <div class="st-card" id="st-run-detail" hidden></div>
    </div>
  </div>`);
  const runsBox = $("#st-runs");
  const approvalsBox = $("#st-approvals");
  const detailBox = $("#st-run-detail");

  const showDetail = async (runId) => {
    detailBox.hidden = false;
    detailBox.innerHTML = `<h3>Detalle de la ejecución</h3><div class="st-empty">Cargando…</div>`;
    try {
      const detail = await api(`/workspace/agent/runs/${encodeURIComponent(runId)}?project_id=${encodeURIComponent(state.projectId)}`);
      const messages = (detail.messages || []).map((message) => {
        const content = typeof message?.content === "string" ? message.content : JSON.stringify(message?.content ?? "");
        return `<div class="st-item"><div class="st-item-main"><div class="st-item-meta">${esc(message?.role ?? "mensaje")}</div><div>${esc(content)}</div></div></div>`;
      }).join("");
      const pending = (detail.pending_actions || []).map((action) => `<div class="st-item"><div class="st-item-main"><div class="st-item-title">${esc(action.tool ?? "Acción")}</div><div class="st-item-meta">${esc(action.summary ?? "")} · hash ${esc(action.action_hash ?? "")}</div></div><span class="st-pill warn">Pendiente</span></div>`).join("");
      detailBox.innerHTML = `<div class="st-row"><h3 style="margin:0">Detalle de la ejecución</h3><button class="st-btn" id="st-run-detail-close">Cerrar</button></div>
        <p class="st-muted">${esc(detail.goal ?? "")} · Estado: <strong>${esc(detail.status ?? "")}</strong></p>
        ${detail.error ? `<div class="st-notice st-error" role="alert">${esc(detail.error)}</div>` : ""}
        <h4>Mensajes</h4><div class="st-list">${messages || '<div class="st-empty">Sin mensajes persistidos.</div>'}</div>
        <h4>Acciones pendientes</h4><div class="st-list">${pending || '<div class="st-empty">Sin acciones pendientes.</div>'}</div>`;
      $("#st-run-detail-close", detailBox).addEventListener("click", () => { detailBox.hidden = true; detailBox.innerHTML = ""; });
    } catch (error) {
      detailBox.innerHTML = `<div class="st-row"><h3 style="margin:0">Detalle de la ejecución</h3><button class="st-btn" id="st-run-detail-close">Cerrar</button></div><div class="st-notice st-error" role="alert">${esc(error.message)}</div>`;
      $("#st-run-detail-close", detailBox).addEventListener("click", () => { detailBox.hidden = true; detailBox.innerHTML = ""; });
    }
  };

  const load = async () => {
    const decide = canDecide();
    const edit = canEdit();
    try {
      const [runs, approvals] = await Promise.all([
        api(`/workspace/agent/runs?project_id=${encodeURIComponent(state.projectId)}`),
        api(`/workspace/agent/approvals?project_id=${encodeURIComponent(state.projectId)}`),
      ]);
      const items = runs.items || [];
      runsBox.innerHTML = items.length
        ? items.map((run) => `<div class="st-item"><div class="st-item-main"><div class="st-item-title">${esc(run.goal)}</div><div class="st-item-meta">${esc(run.status)} · ${esc(run.updated_at ?? "")}</div></div><div class="st-row">
            <button class="st-btn" data-run-detail="${esc(run.id)}">Ver detalle</button>
            ${run.status === "awaiting_approval" && edit ? `<button class="st-btn primary" data-resume-run="${esc(run.id)}">Continuar ejecución</button>` : ""}
            ${run.status === "awaiting_approval" && decide ? `<button class="st-btn danger" data-cancel-run="${esc(run.id)}">Cancelar ejecución</button>` : ""}
            ${run.status === "needs_reconciliation" && decide ? `<button class="st-btn" data-reconcile-run="${esc(run.id)}" data-resolution="applied">Marcar aplicada</button><button class="st-btn danger" data-reconcile-run="${esc(run.id)}" data-resolution="failed">Marcar no aplicada</button>` : ""}
          </div></div>`).join("")
        : `<div class="st-empty">Sin ejecuciones aún.</div>`;

      runsBox.querySelectorAll("[data-run-detail]").forEach((button) => button.addEventListener("click", () => showDetail(button.dataset.runDetail)));

      runsBox.querySelectorAll("[data-resume-run]").forEach((button) => button.addEventListener("click", async () => {
        if (!confirm("Continuar esta ejecución aplicará únicamente las acciones que ya hayan sido aprobadas. ¿Deseas continuar?")) return;
        button.disabled = true;
        try {
          const result = await api(`/workspace/agent/runs/${encodeURIComponent(button.dataset.resumeRun)}/resume?project_id=${encodeURIComponent(state.projectId)}`, { method: "POST" });
          outlet.prepend(notice("good", result.status === "awaiting_approval" ? "La ejecución sigue esperando aprobación." : result.status === "needs_reconciliation" ? "La acción requiere reconciliación humana." : `Ejecución actualizada: ${result.status}`));
          await load();
        } catch (error) { outlet.prepend(notice("error", error.message)); }
        finally { button.disabled = false; }
      }));

      runsBox.querySelectorAll("[data-cancel-run]").forEach((button) => button.addEventListener("click", async () => {
        const note = prompt("Indica el motivo de la cancelación (mínimo 8 caracteres). No se aplicará ninguna acción pendiente:");
        if (!note || note.trim().length < 8) { outlet.prepend(notice("error", "El motivo debe tener al menos 8 caracteres.")); return; }
        if (!confirm("Se cancelará la ejecución y se invalidarán sus aprobaciones pendientes. ¿Continuar?")) return;
        button.disabled = true;
        try {
          await api(`/workspace/agent/runs/${encodeURIComponent(button.dataset.cancelRun)}/cancel?project_id=${encodeURIComponent(state.projectId)}`, { method: "POST", body: JSON.stringify({ note: note.trim() }) });
          outlet.prepend(notice("good", "Ejecución cancelada. No se aplicaron acciones pendientes."));
          await load();
        } catch (error) { outlet.prepend(notice("error", error.message)); }
        finally { button.disabled = false; }
      }));

      runsBox.querySelectorAll("[data-reconcile-run]").forEach((button) => button.addEventListener("click", async () => {
        const resolution = button.dataset.resolution;
        const note = prompt("Describe la verificación manual de la acción interrumpida (mínimo 8 caracteres). No se ejecutará nada automáticamente:");
        if (!note || note.trim().length < 8) { outlet.prepend(notice("error", "El motivo debe tener al menos 8 caracteres.")); return; }
        if (!confirm(`Se registrará la acción como ${resolution === "applied" ? "aplicada" : "no aplicada"} sin ejecutarla. ¿Continuar?`)) return;
        button.disabled = true;
        try {
          const detail = await api(`/workspace/agent/runs/${encodeURIComponent(button.dataset.reconcileRun)}?project_id=${encodeURIComponent(state.projectId)}`);
          const pending = detail.pending_actions || [];
          if (pending.length !== 1) { outlet.prepend(notice("error", "La ejecución debe tener exactamente una acción pendiente para reconciliar.")); return; }
          await api(`/workspace/agent/runs/${encodeURIComponent(button.dataset.reconcileRun)}/reconcile?project_id=${encodeURIComponent(state.projectId)}`, { method: "POST", body: JSON.stringify({ action_hash: pending[0].action_hash, resolution, note: note.trim() }) });
          outlet.prepend(notice("good", "Reconciliación registrada. Pulsa Continuar ejecución para reanudar."));
          await load();
        } catch (error) { outlet.prepend(notice("error", error.message)); }
        finally { button.disabled = false; }
      }));

      const approvalItems = approvals.items || [];
      const planItems = approvals.plan_items || [];
      approvalsBox.innerHTML = (approvalItems.length || planItems.length)
        ? approvalItems.map((item) => `<div class="st-item"><div class="st-item-main"><div class="st-item-title">${esc(item.what ?? item.tool ?? "Acción propuesta")}</div><div class="st-item-meta">${esc(item.why ?? "Requiere revisión")} · caduca ${esc(item.expires_at ?? "")}</div></div>${decide ? `<div class="st-row"><button class="st-btn" data-approval="${esc(item.id)}" data-approve="true">Aprobar</button><button class="st-btn danger" data-approval="${esc(item.id)}" data-approve="false">Rechazar</button></div>` : '<span class="st-pill warn">Solo propietario o administrador</span>'}</div>`).join("")
          + planItems.map((item) => `<div class="st-item"><div class="st-item-main"><div class="st-item-title">Plan: ${esc(item.goal)}</div><div class="st-item-meta">Aprobación de plan · no ejecuta herramientas</div></div>${decide ? `<div class="st-row"><button class="st-btn" data-plan-approval="${esc(item.id)}" data-approve="true">Aprobar</button><button class="st-btn danger" data-plan-approval="${esc(item.id)}" data-approve="false">Rechazar</button></div>` : '<span class="st-pill warn">Solo propietario o administrador</span>'}</div>`).join("")
        : `<div class="st-empty">No hay aprobaciones pendientes.</div>`;

      approvalsBox.querySelectorAll("[data-approval]").forEach((button) => button.addEventListener("click", async () => {
        const approved = button.dataset.approve === "true";
        if (!confirm(`${approved ? "¿Aprobar" : "¿Rechazar"} esta acción propuesta? La decisión no ejecuta la acción por sí sola.`)) return;
        button.disabled = true;
        try {
          await api(`/workspace/agent/approvals/${encodeURIComponent(button.dataset.approval)}?project_id=${encodeURIComponent(state.projectId)}`, { method: "POST", body: JSON.stringify({ approved, note: "Decisión desde Axyron Studio" }) });
          outlet.prepend(notice("good", "Decisión registrada. La aprobación no ejecuta por sí sola la acción."));
          await load();
        } catch (error) { outlet.prepend(notice("error", error.message)); }
        finally { button.disabled = false; }
      }));

      approvalsBox.querySelectorAll("[data-plan-approval]").forEach((button) => button.addEventListener("click", async () => {
        const approved = button.dataset.approve === "true";
        if (!confirm(`${approved ? "¿Aprobar" : "¿Rechazar"} este plan? La decisión no ejecutará herramientas.`)) return;
        button.disabled = true;
        try {
          await api(`/workspace/agent/plan-approvals/${encodeURIComponent(button.dataset.planApproval)}?project_id=${encodeURIComponent(state.projectId)}`, { method: "POST", body: JSON.stringify({ approved, note: "Decisión desde Axyron Studio" }) });
          outlet.prepend(notice("good", "Decisión del plan registrada; no se ejecutaron herramientas."));
          await load();
        } catch (error) { outlet.prepend(notice("error", error.message)); }
        finally { button.disabled = false; }
      }));
    } catch (error) {
      runsBox.innerHTML = `<div class="st-empty">No se pudieron cargar las ejecuciones.</div>`;
      approvalsBox.innerHTML = `<div class="st-empty">No se pudieron cargar las aprobaciones.</div>`;
      outlet.prepend(notice("error", error.message));
    }
  };
  bindProjectSelector(load);
  await load();
  $("#st-agent-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const goal = $("#st-goal").value.trim();
    if (goal.length < 5) return;
    try {
      const run = await api("/workspace/agent/runs", { method: "POST", body: JSON.stringify({ project_id: state.projectId, goal }) });
      outlet.prepend(notice("good", `Tarea creada: ${run.status}`));
      $("#st-goal").value = "";
      await load();
    } catch (error) { outlet.prepend(notice("error", error.message)); }
  });
}

async function renderModels() {
  setOutlet(`<div class="st-view">${viewHead("Modelos", "Modelos Atomic", "Catálogo del servidor y disponibilidad en tiempo real.")}
    <div class="st-grid">
      <div class="st-card"><h3>Modelos publicados</h3><div id="st-models" class="st-grid"><div class="st-empty">Cargando catálogo…</div></div></div>
      <div class="st-card"><h3>Disponibilidad del runtime</h3><p class="st-muted">Solo se marca «Disponible ahora» cuando Ollama confirma el modelo configurado para el proyecto activo.</p><button class="st-btn primary" id="st-models-check">Volver a comprobar</button><div id="st-models-result" class="st-muted" aria-live="polite" style="margin-top:10px"></div></div>
      <div class="st-card"><h3>Próximas capacidades</h3><p class="st-muted">Atomic Reasoning, Atomic Vision y Atomic Video no forman parte del catálogo operativo actual. No se presentan como modelos disponibles.</p><span class="st-pill warn">Próxima actualización</span></div>
    </div>
  </div>`);
  const box = $("#st-models");
  let catalog;
  try {
    catalog = await api("/billing/catalog");
  } catch (error) {
    box.innerHTML = `<div class="st-empty">${esc(error.message)}</div>`;
    return;
  }
  const models = catalog.models || [];

  const loadAvailability = async () => {
    const result = $("#st-models-result");
    if (!state.projectId) {
      box.innerHTML = models.map((model) => `<div class="st-card third"><h3>${esc(model.name)}</h3><p class="st-muted">${esc(model.description)}</p><span class="st-pill warn">Sin verificar</span><p class="st-muted">Selecciona un proyecto para comprobar el runtime.</p></div>`).join("");
      result.textContent = "Crea o selecciona un proyecto para verificar Ollama.";
      return;
    }
    result.textContent = "Comprobando contra Ollama…";
    let live = new Map();
    try {
      const data = await api(`/workspace/models/availability?project_id=${encodeURIComponent(state.projectId)}`);
      live = new Map((data.models || []).map((model) => [model.code, model.available === true]));
    } catch (error) {
      result.textContent = `No se pudo verificar Ollama: ${error.message}`;
    }
    box.innerHTML = models.map((model) => {
      const verified = live.get(model.code);
      const available = verified === true;
      const label = verified === undefined ? "Sin verificar" : available ? "Disponible ahora" : "No disponible";
      const detail = verified === undefined
        ? "El runtime no respondió a la comprobación."
        : available
          ? "Ollama confirmó este modelo para el proyecto activo."
          : "El catálogo lo publica, pero el runtime no lo confirmó; no se puede iniciar inferencia.";
      return `<div class="st-card third"><h3>${esc(model.name)}</h3><p class="st-muted">${esc(model.description)}</p><span class="st-pill ${available ? "good" : "warn"}">${label}</span><p class="st-muted">${detail}</p>${available ? '<p><a class="st-btn" href="/code">Abrir Atomic Code</a></p>' : ""}</div>`;
    }).join("") || `<div class="st-empty">No hay modelos publicados.</div>`;
    if (result.textContent.startsWith("Comprobando")) {
      result.textContent = live.size ? "Comprobación completada." : "El runtime no devolvió modelos.";
    }
  };
  $("#st-models-check").addEventListener("click", loadAvailability);
  await loadAvailability();
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
      <div class="st-card half"><h3>Tu cuenta</h3><div id="st-account" class="st-list"><div class="st-empty">Cargando…</div></div>
        <form id="st-password-form" class="st-grid-form" style="margin-top:12px">
          <div class="st-field"><label for="st-current-password">Contraseña actual</label><input id="st-current-password" type="password" autocomplete="current-password" maxlength="1024" required></div>
          <div class="st-field"><label for="st-new-password">Nueva contraseña (mínimo 12 caracteres)</label><input id="st-new-password" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required></div>
          <div class="st-field"><label for="st-confirm-password">Repite la nueva contraseña</label><input id="st-confirm-password" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required></div>
          <button class="st-btn primary" type="submit">Cambiar contraseña</button>
        </form>
        <p class="st-muted" style="margin-top:10px">Al cambiarla se revocan todas tus sesiones, incluida esta; tendrás que iniciar sesión de nuevo con la nueva contraseña.</p>
      </div>
      <div class="st-card half"><h3>Autenticación multifactor</h3><div id="st-mfa" class="st-list"><div class="st-empty">Cargando…</div></div></div>
      <div class="st-card"><h3>Sesión</h3><p class="st-muted">Cerrar sesión aquí revoca la sesión de este host (Studio). No revoca la sesión de la web principal ni otras sesiones de tu cuenta; esta versión no ofrece cierre de sesión global.</p><button class="st-btn" id="st-account-logout">Cerrar sesión en este dominio</button></div>
    </div>
  </div>`);
  $("#st-account-logout").addEventListener("click", async () => {
    try { await api("/auth/logout", { method: "POST", body: "{}" }); } catch {}
    state.user = null;
    await navigate("/login");
  });
  $("#st-password-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const current = $("#st-current-password").value;
    const next = $("#st-new-password").value;
    if (next !== $("#st-confirm-password").value) {
      outlet.prepend(notice("error", "La nueva contraseña y su confirmación no coinciden."));
      return;
    }
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await api("/auth/password/change", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      state.user = null;
      await navigate("/login");
    } catch (error) {
      outlet.prepend(notice("error", error.message));
      button.disabled = false;
    }
  });
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
      <div class="st-card half"><h3>Sesiones</h3><p class="st-muted">Tus sesiones usan cookies HttpOnly y Secure, con rotación al entrar y CSRF en cada mutación. Cerrar sesión aquí revoca únicamente la sesión de este host (Studio); no cierra la web principal ni otras sesiones de tu cuenta. Esta versión no implementa cierre de sesión global.</p><button class="st-btn" id="st-logout">Cerrar sesión en este dominio</button></div>
      <div class="st-card"><h3>Controles del servidor</h3><ul class="st-muted">
        <li>Sesiones con expiración y revocación.</li>
        <li>CSRF obligatorio en operaciones de escritura.</li>
        <li>Aislamiento por proyecto y autorización por rol.</li>
        <li>Sandbox con backend fail-closed: Docker solo se inyecta con configuración explícita y su validación E2E sigue pendiente.</li>
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
        <li>El historial de chat se guarda por usuario y proyecto en la base de datos (cifrado de disco según el operador, no cifrado a nivel de aplicación). No hay autoservicio de borrado de proyectos; la eliminación corresponde al operador.</li>
        <li>RAG aísla documentos y fragmentos por proyecto.</li>
      </ul></div>
      <div class="st-card"><h3>Exportación de datos</h3><p class="st-muted">Descarga un JSON con los datos acotados a tu cuenta (perfil, proyectos, consumo agregado y saldo/ledger recientes). No incluye prompts, respuestas ni secretos.</p><button class="st-btn" id="st-export-data">Exportar mis datos</button><div id="st-export-status" class="st-muted" aria-live="polite" style="margin-top:10px"></div></div>
      <div class="st-card"><h3>Solicitud de eliminación</h3><p class="st-muted">Registra una solicitud auditable de eliminación de tu cuenta. La eliminación efectiva la revisa y ejecuta el operador, preservando los registros financieros y de auditoría cuando corresponda; no se borra automáticamente.</p>
        <form id="st-delete-request-form" class="st-grid-form">
          <div class="st-field"><label for="st-delete-note">Motivo (opcional)</label><textarea id="st-delete-note" maxlength="2000" placeholder="Indica el motivo si lo deseas"></textarea></div>
          <button class="st-btn danger" type="submit">Registrar solicitud de eliminación</button>
        </form>
        <div id="st-delete-status" class="st-muted" aria-live="polite" style="margin-top:10px"></div>
      </div>
      <div class="st-card"><h3>Legal</h3><p class="st-muted">Consulta los documentos legales publicados en la web principal:</p><ul class="st-muted"><li><a href="${esc(webBase())}/terminos.html" target="_blank" rel="noopener">Términos de servicio</a></li><li><a href="${esc(webBase())}/privacidad.html" target="_blank" rel="noopener">Política de privacidad</a></li><li><a href="${esc(webBase())}/reembolsos.html" target="_blank" rel="noopener">Política de reembolsos</a></li></ul></div>
    </div>
  </div>`);
  $("#st-export-data").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const status = $("#st-export-status");
    button.disabled = true;
    status.textContent = "Preparando exportación…";
    try {
      const data = await api("/auth/account/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `axyron-account-export-${(data.user?.id || "cuenta").slice(0, 12)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      status.textContent = "Exportación descargada. Revisa el archivo con cuidado: contiene metadatos de tu cuenta.";
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  $("#st-delete-request-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = $("#st-delete-status");
    if (!confirm("Se registrará una solicitud de eliminación de tu cuenta para revisión del operador. No se eliminará automáticamente. ¿Continuar?")) return;
    try {
      const result = await api("/auth/account/deletion-request", {
        method: "POST",
        body: JSON.stringify({ note: $("#st-delete-note").value }),
      });
      status.textContent = result.message || "Solicitud registrada.";
      $("#st-delete-note").value = "";
    } catch (error) {
      status.textContent = error.message;
    }
  });
}

async function renderIntegrations() {
  setOutlet(`<div class="st-view">${viewHead("API e integraciones", "API e integraciones", "Qué hay disponible hoy.")}
    <div class="st-grid">
      <div class="st-card"><h3>API propia (compatible con OpenAI)</h3><p class="st-muted">La API multiusuario usa <code>/workspace</code> y <code>/auth</code> con sesión de host, CSRF y membresía de proyecto. La API heredada <code>/v1/*</code> con clave de servicio está desactivada por defecto y no identifica usuario ni proyecto.</p><span class="st-pill good">Disponible</span></div>
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
        <li>El backend Docker es fail-closed y solo se inyecta con configuración explícita; está desactivado por defecto.</li>
        <li>El diseño prevé daemon dedicado, imagen por digest, sin red saliente, rootfs de solo lectura y sin sockets Docker; la activación y validación E2E siguen pendientes.</li>
      </ul><span class="st-pill warn">Parcial</span></div>
      <div class="st-card"><h3>Terminal desde el navegador</h3><p class="st-muted">No disponible. El agente puede proponer acciones y requiere aprobación humana, pero el sandbox Docker no está validado E2E; no se anuncia ejecución autónoma.</p><span class="st-pill warn">Ausente</span></div>
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
