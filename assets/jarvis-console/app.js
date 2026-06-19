const taskInput = document.querySelector("#task");
const planButton = document.querySelector("#planButton");
const startButton = document.querySelector("#startButton");
const mergeButton = document.querySelector("#mergeButton");
const settingsButton = document.querySelector("#settingsButton");
const refreshButton = document.querySelector("#refreshButton");
const voiceButton = document.querySelector("#voiceButton");
const voiceRing = document.querySelector("#voiceRing");
const voiceStatus = document.querySelector("#voiceStatus");
const gitStatus = document.querySelector("#gitStatus");
const planEl = document.querySelector("#plan");
const agentsEl = document.querySelector("#agents");
const eventsEl = document.querySelector("#events");
const agentCount = document.querySelector("#agentCount");
const agentLimit = document.querySelector("#agentLimit");
const agentLimitValue = document.querySelector("#agentLimitValue");
const launchGate = document.querySelector("#launchGate");
const metricBranch = document.querySelector("#metricBranch");
const metricWorkspace = document.querySelector("#metricWorkspace");
const metricRunning = document.querySelector("#metricRunning");
const metricComplete = document.querySelector("#metricComplete");
const metricConflict = document.querySelector("#metricConflict");
const selectedAgent = document.querySelector("#selectedAgent");
const agentDetails = document.querySelector("#agentDetails");
const agentLog = document.querySelector("#agentLog");
const settingsModal = document.querySelector("#settingsModal");
const closeSettings = document.querySelector("#closeSettings");
const providerSettings = document.querySelector("#providerSettings");
const strategySelect = document.querySelector("#strategySelect");
const saveSettings = document.querySelector("#saveSettings");
const reloadSettings = document.querySelector("#reloadSettings");
const backendStatus = document.querySelector("#backendStatus");
const backendJcode = document.querySelector("#backendJcode");
const backendWorkspace = document.querySelector("#backendWorkspace");
const backendGit = document.querySelector("#backendGit");
const workspacePath = document.querySelector("#workspacePath");
const openWorkspaceButton = document.querySelector("#openWorkspaceButton");
const setWorkspaceButton = document.querySelector("#setWorkspaceButton");
const newProjectParent = document.querySelector("#newProjectParent");
const newProjectName = document.querySelector("#newProjectName");
const createProjectButton = document.querySelector("#createProjectButton");
const folderList = document.querySelector("#folderList");

let currentPlan = [];
let latestAgents = [];
let selectedAgentId = "";
let currentSettings;
let currentWorkspacePath = "";
let recognition;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || `Request failed: ${response.status}`);
  }
  return body;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusClass(status) {
  return `status-${String(status || "planned").toLowerCase()}`;
}

function gatherPlanFromDom() {
  const rows = [...planEl.querySelectorAll(".plan-item")];
  const plan = rows
    .map((row) => ({
      role: row.querySelector("[data-role]")?.value.trim() || "Worker Agent",
      task: row.querySelector("[data-task]")?.value.trim() || "",
      provider: row.querySelector("[data-provider]")?.value.trim() || "",
      model: row.querySelector("[data-model]")?.value.trim() || "",
    }))
    .filter((item) => item.task.length > 0);
  currentPlan = plan;
  return plan;
}

function renderMetrics(state) {
  const summary = state.summary || {};
  const workspace = state.workspace || {};
  currentWorkspacePath = workspace.path || "";
  metricWorkspace.textContent = currentWorkspacePath ? currentWorkspacePath.split(/[\\/]/).pop() : "-";
  metricBranch.textContent = state.current_branch || "-";
  metricRunning.textContent = summary.running || 0;
  metricComplete.textContent = summary.complete || 0;
  metricConflict.textContent = summary.conflict || 0;
  const dirty = Boolean(state.root_dirty);
  const missingJcode = state.jcode_available === false;
  const providers = state.settings?.providers || {};
  const availableProviders = Object.values(providers).filter((provider) => provider.enabled && provider.has_api_key);
  if (missingJcode) {
    launchGate.textContent = state.jcode_path || "Jcode executable not found";
  } else if (!availableProviders.length) {
    launchGate.textContent = "Add an API key in Settings before launch";
  } else {
    launchGate.textContent = dirty ? "Commit or stash before launch" : `Ready: ${state.jcode_path}`;
  }
  launchGate.className = `gate ${dirty || missingJcode || !availableProviders.length ? "blocked" : "ready"}`;
  startButton.disabled = dirty || missingJcode || !availableProviders.length;
  backendStatus.textContent = state.jcode_available ? "online" : "blocked";
  backendStatus.className = `badge ${state.jcode_available ? "status-complete" : "status-failed"}`;
  backendJcode.textContent = state.jcode_path || "-";
  backendWorkspace.textContent = workspace.path || "-";
  backendGit.textContent = workspace.is_git_repo ? `${workspace.branch} / ${workspace.dirty ? "dirty" : "clean"}` : "not a git repo";
  if (document.activeElement !== workspacePath) {
    workspacePath.value = workspace.path || "";
  }
  if (document.activeElement !== newProjectParent) {
    newProjectParent.value = workspace.path || "";
  }
}

function renderPlan(plan) {
  currentPlan = plan || [];
  planEl.innerHTML = "";
  if (!currentPlan.length) {
    planEl.innerHTML = '<div class="plan-item subtle">No plan yet.</div>';
    return;
  }
  currentPlan.forEach((item, index) => {
    const node = document.createElement("div");
    node.className = "plan-item";
    node.innerHTML = `
      <label>Worker ${index + 1}</label>
      <input data-role value="${escapeHtml(item.role)}" />
      <textarea data-task rows="3">${escapeHtml(item.task)}</textarea>
      <div class="route-row">
        <input data-provider value="${escapeHtml(item.provider || "")}" placeholder="provider override: openai, claude, nvidia" />
        <input data-model value="${escapeHtml(item.model || "")}" placeholder="model override, blank = smart" />
      </div>
    `;
    planEl.appendChild(node);
  });
}

function renderAgents(agents) {
  latestAgents = agents || [];
  agentsEl.innerHTML = "";
  const active = latestAgents.filter((agent) => ["starting", "running"].includes(agent.status)).length;
  agentCount.textContent = `${active} active`;
  if (!latestAgents.length) {
    agentsEl.innerHTML = '<div class="agent subtle">No workers launched.</div>';
    renderSelectedAgent();
    return;
  }
  latestAgents.forEach((agent) => {
    const node = document.createElement("article");
    node.className = "agent";
    node.innerHTML = `
      <header>
        <strong>${escapeHtml(agent.id)}</strong>
        <span class="${statusClass(agent.status)}">${escapeHtml(agent.status)}</span>
      </header>
      <p>${escapeHtml(agent.role)}</p>
      <small>${escapeHtml(agent.task)}</small>
      <small>branch: ${escapeHtml(agent.branch || "pending")}</small>
      <small class="model-route">model: ${escapeHtml(agent.provider || "pending")}/${escapeHtml(agent.model || "pending")}</small>
      <small>commit: ${escapeHtml(agent.commit || "not committed yet")}</small>
      <small>pid: ${escapeHtml(agent.pid || "-")}</small>
      <button data-inspect="${escapeHtml(agent.id)}">Inspect</button>
    `;
    agentsEl.appendChild(node);
  });
  agentsEl.querySelectorAll("[data-inspect]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedAgentId = button.dataset.inspect;
      renderSelectedAgent();
      refreshAgentLog();
    });
  });
  if (!latestAgents.some((agent) => agent.id === selectedAgentId)) {
    selectedAgentId = latestAgents[0]?.id || "";
  }
  renderSelectedAgent();
}

function renderSelectedAgent() {
  const agent = latestAgents.find((item) => item.id === selectedAgentId);
  if (!agent) {
    selectedAgent.textContent = "none selected";
    agentDetails.textContent = "Select a worker to inspect its live log.";
    agentLog.textContent = "No log selected.";
    return;
  }
  selectedAgent.textContent = agent.id;
  const canStop = ["starting", "running"].includes(agent.status);
  agentDetails.innerHTML = `
    <strong>${escapeHtml(agent.role)}</strong>
    <span class="${statusClass(agent.status)}">${escapeHtml(agent.status)}</span>
    <small>${escapeHtml(agent.task)}</small>
    <small class="model-route">provider/model: ${escapeHtml(agent.provider || "-")}/${escapeHtml(agent.model || "-")}</small>
    <small>branch: ${escapeHtml(agent.branch)}</small>
    <small>worktree: ${escapeHtml(agent.worktree)}</small>
    <small>log: ${escapeHtml(agent.log)}</small>
    ${agent.conflicts?.length ? `<small>conflicts: ${escapeHtml(agent.conflicts.join(", "))}</small>` : ""}
    <button id="stopSelected" ${canStop ? "" : "disabled"}>Stop Worker</button>
  `;
  agentDetails.querySelector("#stopSelected")?.addEventListener("click", () => stopAgent(agent.id));
}

function renderEvents(events) {
  eventsEl.innerHTML = "";
  if (!events.length) {
    eventsEl.innerHTML = '<div class="event">Waiting for console activity.</div>';
    return;
  }
  events.slice().reverse().forEach((event) => {
    const node = document.createElement("div");
    node.className = "event";
    node.textContent = `[${event.time}] ${event.message}`;
    eventsEl.appendChild(node);
  });
}

async function refreshAgentLog() {
  if (!selectedAgentId) return;
  try {
    const response = await api(`/api/agent/log?id=${encodeURIComponent(selectedAgentId)}`);
    agentLog.textContent = response.log || "Log is empty.";
    agentLog.scrollTop = agentLog.scrollHeight;
  } catch (error) {
    agentLog.textContent = error.message;
  }
}

async function refresh() {
  const state = await api("/api/status");
  gitStatus.textContent = state.git_status || "Clean";
  renderMetrics(state);
  if (document.activeElement?.closest?.("#plan") !== planEl) {
    renderPlan(state.plan);
  }
  renderAgents(state.agents || []);
  renderEvents(state.events || []);
  await refreshAgentLog();
}

async function browseWorkspace(path = workspacePath.value || currentWorkspacePath) {
  const response = await api(`/api/workspace/list?path=${encodeURIComponent(path || "")}`);
  workspacePath.value = response.path;
  newProjectParent.value = response.path;
  folderList.innerHTML = "";
  if (response.parent) {
    const parentNode = document.createElement("div");
    parentNode.className = "folder-item";
    parentNode.innerHTML = `<small>..</small><button data-browse="${escapeHtml(response.parent)}">Open</button>`;
    folderList.appendChild(parentNode);
  }
  response.entries.forEach((entry) => {
    const node = document.createElement("div");
    node.className = "folder-item";
    const label = entry.is_dir ? `[folder] ${entry.name}` : entry.name;
    node.innerHTML = `
      <small>${escapeHtml(label)}${entry.is_git_repo ? " / git" : ""}</small>
      ${
        entry.is_dir
          ? `<span><button data-browse="${escapeHtml(entry.path)}">Open</button> <button data-use="${escapeHtml(entry.path)}">Use</button></span>`
          : "<span></span>"
      }
    `;
    folderList.appendChild(node);
  });
  folderList.querySelectorAll("[data-browse]").forEach((button) => {
    button.addEventListener("click", () => browseWorkspace(button.dataset.browse).catch((error) => alert(error.message)));
  });
  folderList.querySelectorAll("[data-use]").forEach((button) => {
    button.addEventListener("click", () => setWorkspace(button.dataset.use).catch((error) => alert(error.message)));
  });
}

async function setWorkspace(path = workspacePath.value) {
  await api("/api/workspace/set", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
  await refresh();
  await browseWorkspace(path);
}

async function createProject() {
  const parent = newProjectParent.value.trim() || currentWorkspacePath;
  const name = newProjectName.value.trim();
  if (!name) {
    alert("Project name is required.");
    return;
  }
  await api("/api/workspace/create", {
    method: "POST",
    body: JSON.stringify({ parent, name, init_git: true }),
  });
  newProjectName.value = "";
  await refresh();
  await browseWorkspace(`${parent}\\${name}`);
}

function modelsToText(models) {
  return (models || []).map((model) => `${model.id}|${model.tier}|${model.cost}`).join("\n");
}

function textToModels(value) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [id, tier = "balanced", cost = "3"] = line.split("|").map((part) => part.trim());
      return { id, tier, cost: Number(cost) || 3 };
    })
    .filter((model) => model.id);
}

function renderSettings(settings) {
  currentSettings = settings;
  strategySelect.value = settings.strategy || "balanced";
  providerSettings.innerHTML = "";
  Object.entries(settings.providers || {}).forEach(([providerId, provider]) => {
    const card = document.createElement("article");
    card.className = "provider-card";
    card.dataset.provider = providerId;
    card.innerHTML = `
      <div class="check-row">
        <input id="provider-${providerId}" type="checkbox" data-enabled ${provider.enabled ? "checked" : ""} />
        <label for="provider-${providerId}">${escapeHtml(provider.label || providerId)}</label>
      </div>
      <small class="${provider.has_api_key ? "status-complete" : "status-failed"}">
        ${provider.has_api_key ? "API key saved/found" : "No API key found"}
      </small>
      <label>API key</label>
      <input data-api-key type="password" placeholder="Leave blank to keep existing key" autocomplete="off" />
      <label>Models: id|tier|cost</label>
      <textarea data-models>${escapeHtml(modelsToText(provider.models))}</textarea>
      <small class="subtle">tier is economy, balanced, or premium. Lower cost wins inside a tier.</small>
    `;
    providerSettings.appendChild(card);
  });
}

async function openSettings() {
  const settings = await api("/api/settings");
  renderSettings(settings);
  settingsModal.hidden = false;
}

function collectSettings() {
  const providers = {};
  providerSettings.querySelectorAll(".provider-card").forEach((card) => {
    providers[card.dataset.provider] = {
      enabled: card.querySelector("[data-enabled]").checked,
      api_key: card.querySelector("[data-api-key]").value.trim(),
      models: textToModels(card.querySelector("[data-models]").value),
    };
  });
  return { strategy: strategySelect.value, providers };
}

async function persistSettings() {
  const saved = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify(collectSettings()),
  });
  renderSettings(saved);
  await refresh();
}

async function planAgents() {
  const task = taskInput.value.trim();
  if (!task) return;
  const response = await api("/api/plan", {
    method: "POST",
    body: JSON.stringify({ task, max_agents: Number(agentLimit.value) }),
  });
  renderPlan(response.plan);
  renderEvents(response.events || []);
  renderMetrics(response);
}

async function startWorkers() {
  const task = taskInput.value.trim();
  if (!task) return;
  const plan = gatherPlanFromDom();
  if (!plan.length) {
    await planAgents();
  }
  await api("/api/start", {
    method: "POST",
    body: JSON.stringify({ task, plan: currentPlan }),
  });
  await refresh();
}

async function mergeFinished() {
  if (!confirm("Merge completed agent branches into the current branch?")) return;
  await api("/api/merge", { method: "POST", body: "{}" });
  await refresh();
}

async function stopAgent(id) {
  if (!confirm(`Stop ${id}?`)) return;
  await api("/api/agent/stop", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
  await refresh();
}

function setupVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceButton.disabled = true;
    voiceStatus.textContent = "Speech recognition is not available in this browser.";
    return;
  }
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";
  recognition.onstart = () => {
    voiceRing.classList.add("listening");
    voiceButton.textContent = "Stop Voice";
    voiceStatus.textContent = "Listening. Say a task, then say start workers or merge finished.";
  };
  recognition.onend = () => {
    voiceRing.classList.remove("listening");
    voiceButton.textContent = "Start Voice";
  };
  recognition.onresult = (event) => {
    let text = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      text += event.results[i][0].transcript;
    }
    const lower = text.toLowerCase();
    if (lower.includes("start workers") || lower.includes("deploy agents")) {
      startWorkers().catch((error) => alert(error.message));
      return;
    }
    if (lower.includes("plan agents")) {
      planAgents().catch((error) => alert(error.message));
      return;
    }
    if (lower.includes("merge finished")) {
      mergeFinished().catch((error) => alert(error.message));
      return;
    }
    taskInput.value = `${taskInput.value} ${text}`.trim();
  };
}

agentLimit.addEventListener("input", () => {
  agentLimitValue.textContent = agentLimit.value;
});
planButton.addEventListener("click", () => planAgents().catch((error) => alert(error.message)));
startButton.addEventListener("click", () => startWorkers().catch((error) => alert(error.message)));
mergeButton.addEventListener("click", () => mergeFinished().catch((error) => alert(error.message)));
refreshButton.addEventListener("click", () => refresh().catch((error) => alert(error.message)));
openWorkspaceButton.addEventListener("click", () => browseWorkspace().catch((error) => alert(error.message)));
setWorkspaceButton.addEventListener("click", () => setWorkspace().catch((error) => alert(error.message)));
createProjectButton.addEventListener("click", () => createProject().catch((error) => alert(error.message)));
settingsButton.addEventListener("click", () => openSettings().catch((error) => alert(error.message)));
closeSettings.addEventListener("click", () => {
  settingsModal.hidden = true;
});
reloadSettings.addEventListener("click", () => openSettings().catch((error) => alert(error.message)));
saveSettings.addEventListener("click", () => persistSettings().catch((error) => alert(error.message)));
settingsModal.addEventListener("click", (event) => {
  if (event.target === settingsModal) {
    settingsModal.hidden = true;
  }
});
voiceButton.addEventListener("click", () => {
  if (!recognition) return;
  if (voiceRing.classList.contains("listening")) {
    recognition.stop();
  } else {
    recognition.start();
  }
});

document.querySelectorAll("[data-template]").forEach((button) => {
  button.addEventListener("click", () => {
    taskInput.value = `${button.dataset.template}${taskInput.value}`.trim();
    taskInput.focus();
  });
});

setupVoice();
refresh().catch((error) => {
  gitStatus.textContent = error.message;
});
browseWorkspace().catch(() => {});
setInterval(() => refresh().catch(() => {}), 1500);
