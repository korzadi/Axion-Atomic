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
  let history = [];
  let busy = false;

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
  async function loadHistory() {
    if (!currentProject) return;
    const data = await request("/workspace/chat/history?project_id=" + encodeURIComponent(currentProject));
    history = Array.isArray(data.messages) ? data.messages : [];
    renderHistory(history);
  }
  async function loadProjects() {
    const data = await request("/auth/projects");
    const items = Array.isArray(data.items) ? data.items : [];
    projectSelect.replaceChildren();
    items.forEach((project) => {
      const option = document.createElement("option");
      option.value = project.id;
      option.textContent = project.name || "Proyecto";
      projectSelect.appendChild(option);
    });
    if (!items.length) {
      currentProject = null;
      setStatus("Crea tu primer proyecto para comenzar.");
      messages.replaceChildren();
      return;
    }
    currentProject = String(items[0].id);
    projectSelect.value = currentProject;
    await loadHistory();
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
    try { await loadHistory(); setStatus("Historial del proyecto cargado."); }
    catch (error) { setStatus(error.message); }
  });
  $("ws-create-project").addEventListener("click", async () => {
    if (!currentUser) return;
    const name = $("ws-new-project").value.trim();
    if (name.length < 2) { setStatus("Escribe un nombre de al menos 2 caracteres."); return; }
    try {
      await request("/auth/projects", { method: "POST", body: JSON.stringify({ name }) });
      $("ws-new-project").value = "";
      await loadProjects();
      setStatus("Proyecto creado correctamente.");
    } catch (error) { setStatus(error.message); }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const content = prompt.value.trim();
    if (!currentUser || !currentProject || !content || busy) return;
    busy = true; send.disabled = true;
    const nextHistory = history.concat([{ role: "user", content }]);
    say(content, "user"); prompt.value = "";
    setStatus("Axyron está consultando Atomic Code…");
    try {
      const data = await request("/workspace/chat/completions", {
        method: "POST",
        body: JSON.stringify({ model: "atomic-code", project_id: currentProject, messages: nextHistory, temperature: 0.2, max_tokens: 2048, stream: false })
      });
      const answer = data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content;
      if (typeof answer !== "string" || !answer.trim()) throw new Error("El servidor devolvió una respuesta vacía.");
      history = nextHistory.concat([{ role: "assistant", content: answer }]);
      say(answer, "assistant");
      setStatus(data.history_saved === false ? "Respuesta recibida; el historial no pudo guardarse." : "Respuesta recibida y guardada.");
    } catch (error) {
      // Keep the typed user turn visible but don't add it to the saved client history on failure.
      setStatus(error.message);
    } finally { busy = false; send.disabled = false; }
  });
})();