(() => {
  "use strict";
  const root = document.getElementById("workspace-app");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const projectSelect = $("ws-project");
  const messages = $("ws-messages");
  const status = $("ws-status");
  const form = $("ws-chat-form");
  const prompt = $("ws-prompt");
  const send = $("ws-send");
  let currentUser = null;
  let currentProject = null;
  let currentProjectRole = null;
  let history = [];
  let busy = false;
  let agentBusy = false;
  let activeAgentRun = null;

  // Panel nativo del agente: usa las rutas persistentes ya existentes y nunca
  // ejecuta una modificación sin una decisión explícita del propietario/admin.
  const agentPanel = document.createElement("section");
  agentPanel.className = "ws-agent-panel";
  agentPanel.setAttribute("aria-labelledby", "ws-agent-title");
  agentPanel.style.cssText = "margin-top:1.25rem;padding:1rem;border:1px solid var(--border-color, #8886);border-radius:12px;display:grid;gap:.75rem";
  const agentTitle = document.createElement("h3");
  agentTitle.id = "ws-agent-title";
  agentTitle.textContent = "Agente AXYRON";
  const agentDescription = document.createElement("p");
  agentDescription.textContent = "Describe una tarea para que el agente analice el proyecto, proponga cambios y espere tu aprobación.";
  const agentGoal = document.createElement("textarea");
  agentGoal.rows = 3;
  agentGoal.maxLength = 10000;
  agentGoal.placeholder = "Ej.: Analiza el módulo de autenticación y propone una corrección concreta.";
  agentGoal.setAttribute("aria-label", "Objetivo del agente AXYRON");
  agentGoal.style.cssText = "width:100%;min-height:5rem;resize:vertical";
  const agentStart = document.createElement("button");
  agentStart.type = "button";
  agentStart.textContent = "Iniciar tarea";
  agentStart.disabled = true;
  const agentStatus = document.createElement("p");
  agentStatus.setAttribute("role", "status");
  agentStatus.setAttribute("aria-live", "polite");
  agentStatus.textContent = "Agente listo.";
  const agentOutput = document.createElement("pre");
  agentOutput.style.cssText = "white-space:pre-wrap;overflow-wrap:anywhere;max-height:22rem;overflow:auto";
  const agentHistoryButton = document.createElement("button");
  agentHistoryButton.type = "button";
  agentHistoryButton.textContent = "Actualizar historial";
  const agentHistory = document.createElement("div");
  agentHistory.style.cssText = "display:grid;gap:.4rem";
  const agentActions = document.createElement("div");
  agentActions.style.cssText = "display:flex;gap:.5rem;flex-wrap:wrap";
  agentPanel.append(agentTitle, agentDescription, agentGoal, agentStart, agentStatus, agentOutput, agentActions, agentHistoryButton, agentHistory);
  root.appendChild(agentPanel);

  function setAgentBusy(value) {
    agentBusy = Boolean(value);
    const canStart = ["owner", "admin", "editor"].includes(currentProjectRole);
    agentStart.disabled = agentBusy || !currentProject || !canStart;
    agentGoal.disabled = agentBusy || !currentProject || !canStart;
    agentHistoryButton.disabled = agentBusy || !currentProject;
  }
  function showAgentRun(run) {
    activeAgentRun = run && run.run_id ? run : activeAgentRun;
    agentOutput.textContent = "";
    if (!run) return;
    const lines = [
      "Estado: " + (run.status || "desconocido"),
      "Ejecución: " + (run.run_id || activeAgentRun && activeAgentRun.run_id || "—"),
      "Pasos: " + (Number.isSafeInteger(run.steps) ? run.steps : 0)
    ];
    if (run.final) lines.push("", run.final);
    if (run.error) lines.push("", "Error: " + run.error);
    const pending = Array.isArray(run.pending_actions) ? run.pending_actions : [];
    if (pending.length) lines.push("", "Acciones que requieren aprobación:");
    agentOutput.textContent = lines.join("\n");
    agentActions.replaceChildren();
    if (pending.length && !["owner", "admin"].includes(currentProjectRole)) {
      const notice = document.createElement("p");
      notice.textContent = "La propuesta está pendiente. Solo el propietario o un administrador del proyecto puede aprobarla o rechazarla.";
      agentActions.appendChild(notice);
    }
    pending.forEach((action) => {
      if (!["owner", "admin"].includes(currentProjectRole)) return;
      const row = document.createElement("div");
      row.style.cssText = "display:grid;gap:.35rem;padding:.65rem;border:1px solid var(--border-color, #8886);border-radius:8px";
      const label = document.createElement("p");
      label.textContent = action.tool + ": " + action.summary;
      const approve = document.createElement("button");
      approve.type = "button";
      approve.textContent = "Aprobar y continuar";
      const reject = document.createElement("button");
      reject.type = "button";
      reject.textContent = "Rechazar";
      approve.addEventListener("click", () => decideAgentAction(action.proposal_id, true));
      reject.addEventListener("click", () => decideAgentAction(action.proposal_id, false));
      row.append(label, approve, reject);
      agentActions.appendChild(row);
    });
    if (!pending.length && run.status === "done") agentStatus.textContent = "Tarea terminada.";
    else if (!pending.length) agentStatus.textContent = "Agente: " + (run.status || "en proceso") + ".";
  }
  async function decideAgentAction(proposalId, approved) {
    if (!activeAgentRun || !currentProject || !["owner", "admin"].includes(currentProjectRole) || agentBusy) return;
    setAgentBusy(true);
    agentStatus.textContent = approved ? "Registrando aprobación…" : "Registrando rechazo…";
    try {
      const query = "?project_id=" + encodeURIComponent(currentProject);
      await request("/workspace/agent/approvals/" + encodeURIComponent(proposalId) + query, {
        method: "POST",
        body: JSON.stringify({ approved, note: approved ? "Aprobado desde AXYRON Studio" : "Rechazado desde AXYRON Studio" })
      });
      agentStatus.textContent = "Decisión guardada. Continuando ejecución…";
      const run = await request("/workspace/agent/runs/" + encodeURIComponent(activeAgentRun.run_id) + "/resume" + query, {
        method: "POST",
        body: JSON.stringify({})
      });
      showAgentRun(run);
    } catch (error) {
      agentStatus.textContent = error.message;
    } finally { setAgentBusy(false); await loadAgentHistory(); }
  }
  agentStart.addEventListener("click", async () => {
    const goal = agentGoal.value.trim();
    if (!currentProject || goal.length < 5 || agentBusy) {
      if (goal.length < 5) agentStatus.textContent = "Describe una tarea de al menos 5 caracteres.";
      return;
    }
    setAgentBusy(true);
    agentStatus.textContent = "AXYRON está analizando el proyecto…";
    agentActions.replaceChildren();
    agentOutput.textContent = "";
    try {
      const run = await request("/workspace/agent/runs", {
        method: "POST",
        body: JSON.stringify({ project_id: currentProject, goal })
      });
      showAgentRun(run);
      if (run.status === "awaiting_approval") {
        agentStatus.textContent = "Propuesta preparada. Revisa cada cambio antes de aprobarlo.";
      } else if (run.status === "done") {
        agentStatus.textContent = "Tarea terminada.";
      } else {
        agentStatus.textContent = "Ejecución: " + run.status + ".";
      }
    } catch (error) {
      agentStatus.textContent = error.message;
    } finally { setAgentBusy(false); await loadAgentHistory(); }
  });

  async function loadAgentHistory() {
    if (!currentProject || agentBusy) return;
    agentHistoryButton.disabled = true;
    agentHistory.replaceChildren();
    const query = "?project_id=" + encodeURIComponent(currentProject) + "&limit=10";
    try {
      const data = await request("/workspace/agent/runs" + query);
      const items = Array.isArray(data.items) ? data.items : [];
      if (!items.length) {
        const empty = document.createElement("p");
        empty.textContent = "Todavía no hay ejecuciones guardadas en este proyecto.";
        agentHistory.appendChild(empty);
      }
      items.forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = (item.status || "sin estado") + " · " + (item.goal || "Tarea") + " · " + String(item.id || "").slice(0, 8);
        button.addEventListener("click", async () => {
          if (agentBusy || !item.id) return;
          setAgentBusy(true);
          agentStatus.textContent = "Recuperando ejecución guardada…";
          try {
            const detail = await request("/workspace/agent/runs/" + encodeURIComponent(item.id) + "?project_id=" + encodeURIComponent(currentProject));
            showAgentRun({ ...detail, run_id: detail.id, pending_actions: Array.isArray(detail.pending_actions) ? detail.pending_actions : [] });
            agentStatus.textContent = "Ejecución recuperada del historial.";
          } catch (error) {
            agentStatus.textContent = error.message;
          } finally { setAgentBusy(false); }
        });
        agentHistory.appendChild(button);
      });
    } catch (error) {
      const message = document.createElement("p");
      message.textContent = "No se pudo cargar el historial: " + error.message;
      agentHistory.appendChild(message);
    } finally { agentHistoryButton.disabled = !currentProject || agentBusy; }
  }
  agentHistoryButton.addEventListener("click", loadAgentHistory);
  function csrfToken() {
    const match = document.cookie.match(/(?:^|; )axion_csrf=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }
  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.method && options.method !== "GET") {
      headers.set("Content-Type", "application/json");
      headers.set("X-CSRF-Token", csrfToken());
    }
    const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || payload.message || ("HTTP " + response.status));
    return payload;
  }
  function say(text, role) {
    const item = document.createElement("div");
    item.className = "b " + (role === "user" ? "u" : "a");
    item.textContent = text;
    messages.appendChild(item);
    messages.scrollTop = messages.scrollHeight;
  }
  function renderHistory(items) {
    messages.replaceChildren();
    (items || []).forEach((item) => say(item.content, item.role));
  }
  function setStatus(text) { status.textContent = text; }
  function createIdempotencyKey() {
    const cryptoApi = window.crypto;
    if (cryptoApi && typeof cryptoApi.randomUUID === "function") return cryptoApi.randomUUID();
    if (!cryptoApi || typeof cryptoApi.getRandomValues !== "function") {
      throw new Error("Este navegador no permite generar una clave segura para reintentos.");
    }
    const bytes = new Uint8Array(16);
    cryptoApi.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
    return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16)
      + "-" + hex.slice(16, 20) + "-" + hex.slice(20);
  }
  let pendingIdempotencyKey = null;
  let pendingRequestFingerprint = null;
  function setBusy(value) {
    busy = Boolean(value);
    send.disabled = busy;
    projectSelect.disabled = busy;
    $("ws-create-project").disabled = busy;
    $("ws-new-project").disabled = busy;
    form.setAttribute("aria-busy", busy ? "true" : "false");
  }
  async function loadHistory() {
    if (!currentProject) return;
    const data = await request("/workspace/chat/history?project_id=" + encodeURIComponent(currentProject));
    history = Array.isArray(data.messages) ? data.messages : [];
    renderHistory(history);
  }
  async function loadProjects(preferredProjectId = null) {
    const data = await request("/auth/projects");
    const items = Array.isArray(data.items) ? data.items : [];
    projectSelect.replaceChildren();
    items.forEach((project) => {
      const option = document.createElement("option");
      option.value = project.id;
      option.dataset.role = project.role || "";
      option.textContent = project.name || "Proyecto";
      projectSelect.appendChild(option);
    });
    if (!items.length) {
      currentProject = null;
      currentProjectRole = null;
      activeAgentRun = null;
      agentOutput.textContent = "";
      agentActions.replaceChildren();
      setAgentBusy(false);
      setStatus("Crea tu primer proyecto para comenzar.");
      messages.replaceChildren();
      return;
    }
    const preferred = preferredProjectId == null ? null : String(preferredProjectId);
    currentProject = items.some((item) => String(item.id) === preferred) ? preferred : String(items[0].id);
    projectSelect.value = currentProject;
    currentProjectRole = items.find((item) => String(item.id) === currentProject)?.role || null;
    activeAgentRun = null;
    agentOutput.textContent = "";
    agentActions.replaceChildren();
    agentHistory.replaceChildren();
    setAgentBusy(false);
    await loadHistory();
    await loadAgentHistory();
    setStatus("Proyecto listo. Atomic Code está conectado al backend.");
  }
  async function activate(user) {
    currentUser = user || null;
    root.hidden = !currentUser;
    if (!currentUser) {
      currentProject = null;
      history = [];
      messages.replaceChildren();
      return;
    }
    try { await loadProjects(); }
    catch (error) { setStatus(error.message); }
  }
  window.addEventListener("axyron:user", (event) => activate(event.detail && event.detail.user));
  request("/auth/me").then((data) => activate(data.user)).catch(() => activate(null));

  projectSelect.addEventListener("change", async () => {
    currentProject = projectSelect.value || null;
    currentProjectRole = projectSelect.selectedOptions[0]?.dataset.role || null;
    activeAgentRun = null;
    agentOutput.textContent = "";
    agentActions.replaceChildren();
    agentHistory.replaceChildren();
    setAgentBusy(false);
    try { await loadHistory(); await loadAgentHistory(); setStatus("Historial del proyecto cargado."); }
    catch (error) { setStatus(error.message); }
  });
  $("ws-create-project").addEventListener("click", async () => {
    if (!currentUser) return;
    const name = $("ws-new-project").value.trim();
    if (name.length < 2) { setStatus("Escribe un nombre de al menos 2 caracteres."); return; }
    try {
      const created = await request("/auth/projects", { method: "POST", body: JSON.stringify({ name }) });
      $("ws-new-project").value = "";
      await loadProjects(created.project && created.project.id);
      setStatus("Proyecto creado correctamente.");
    } catch (error) { setStatus(error.message); }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const content = prompt.value.trim();
    if (!currentUser || !currentProject || !content || busy) return;
    setBusy(true);
    const nextHistory = history.concat([{ role: "user", content }]);
    say(content, "user"); prompt.value = "";
    setStatus("Axyron está consultando Atomic Code…");
    try {
      const chatPayload = {
        model: "atomic-code",
        project_id: currentProject,
        messages: nextHistory,
        temperature: Number($("ws-temperature").value),
        max_tokens: Number.parseInt($("ws-max-tokens").value, 10),
        stream: true
      };
      const requestFingerprint = JSON.stringify(chatPayload);
      if (!pendingIdempotencyKey || pendingRequestFingerprint !== requestFingerprint) {
        pendingIdempotencyKey = createIdempotencyKey();
        pendingRequestFingerprint = requestFingerprint;
      }
      const data = await request("/workspace/chat/completions", {
        method: "POST",
        headers: { "Idempotency-Key": pendingIdempotencyKey },
        body: JSON.stringify(chatPayload)
      });
      const answer = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
      if (typeof answer !== "string" || !answer.trim()) throw new Error("El servidor devolvió una respuesta vacía.");
      history = nextHistory.concat([{ role: "assistant", content: answer }]);
      say(answer, "assistant");
      pendingIdempotencyKey = null;
      pendingRequestFingerprint = null;
      const historyStatus = data.history_saved === false
        ? "Respuesta recibida; el historial no pudo guardarse."
        : "Respuesta recibida y guardada.";
      const billing = data.usage_billing;
      const billingStatus = billing && billing.mode === "shadow" && billing.charged === false && billing.credits_reserved === false
        ? " Facturación: modo de medición; no se cobraron ni reservaron créditos."
        : billing && billing.mode === "ledger" && billing.charged === true
          && Number.isSafeInteger(billing.credits_charged) && billing.credits_charged >= 0
          ? " Facturación: se descontaron " + billing.credits_charged + " créditos según el consumo medido de Ollama."
          : " Estado de facturación no confirmado.";
      setStatus(historyStatus + billingStatus);
    } catch (error) {
      // Mantiene intactos history, payload y clave idempotente: si el servidor
      // completó la inferencia pero se perdió la respuesta HTTP, el reintento
      // debe recuperar esa misma ejecución y nunca crear una nueva.
      prompt.value = content;
      renderHistory(history);
      setStatus(error.message);
    } finally { setBusy(false); }
  });
})();