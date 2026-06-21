const taskInput = document.querySelector("#task");
const launchButton = document.querySelector("#launchButton");
const settingsButton = document.querySelector("#settingsButton");
const voiceButton = document.querySelector("#voiceButton");
const talkBackButton = document.querySelector("#talkBackButton");
const voiceRing = document.querySelector("#voiceRing");
const voiceStatus = document.querySelector("#voiceStatus");
const voiceReplyStatus = document.querySelector("#voiceReplyStatus");
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
const serviceStatus = document.querySelector("#serviceStatus");
const servicePath = document.querySelector("#servicePath");
const installServiceButton = document.querySelector("#installServiceButton");
const removeServiceButton = document.querySelector("#removeServiceButton");
const workspacePath = document.querySelector("#workspacePath");
const openWorkspaceButton = document.querySelector("#openWorkspaceButton");
const setWorkspaceButton = document.querySelector("#setWorkspaceButton");
const newProjectParent = document.querySelector("#newProjectParent");
const newProjectName = document.querySelector("#newProjectName");
const createProjectButton = document.querySelector("#createProjectButton");
const folderList = document.querySelector("#folderList");
const armyBoard = document.querySelector("#armyBoard");
const armySummary = document.querySelector("#armySummary");
const consoleState = document.querySelector("#consoleState");
const consoleUpdated = document.querySelector("#consoleUpdated");
const consoleGate = document.querySelector("#consoleGate");
const metricHealing = document.querySelector("#metricHealing");
const apcallFeed = document.querySelector("#apcallFeed");
const apcallSummary = document.querySelector("#apcallSummary");
const healingStatus = document.querySelector("#healingStatus");
const healToggle = document.querySelector("#healToggle");
const qaToggle = document.querySelector("#qaToggle");
const killswitchButton = document.querySelector("#killswitchButton");
const healWatch = document.querySelector("#healWatch");
const healingBoard = document.querySelector("#healingBoard");
const budgetBar = document.querySelector("#budgetBar");
const budgetLabel = document.querySelector("#budgetLabel");
const budgetFill = document.querySelector("#budgetFill");
const queueLabel = document.querySelector("#queueLabel");
const whiteboardModal = document.querySelector("#whiteboardModal");
const closeWhiteboard = document.querySelector("#closeWhiteboard");
const wbMission = document.querySelector("#wbMission");
const wbStatus = document.querySelector("#wbStatus");
const wbTasks = document.querySelector("#wbTasks");
const wbProgressBar = document.querySelector("#wbProgressBar");
const wbProgressText = document.querySelector("#wbProgressText");
const wbNotes = document.querySelector("#wbNotes");
const wbNoteInput = document.querySelector("#wbNoteInput");
const wbNoteButton = document.querySelector("#wbNoteButton");
const wbFeed = document.querySelector("#wbFeed");
const wbActionButton = document.querySelector("#wbActionButton");
const liveActivity = document.querySelector("#liveActivity");
const consoleDeck = document.querySelector("#consoleDeck");
const consolesButton = document.querySelector("#consolesButton");
const tunnelBadge = document.querySelector("#tunnelBadge");
const remoteUrl = document.querySelector("#remoteUrl");
const remotePin = document.querySelector("#remotePin");
const remoteQr = document.querySelector("#remoteQr");
const remoteQrPlaceholder = document.querySelector("#remoteQrPlaceholder");
const copyUrlBtn = document.querySelector("#copyUrlBtn");
const revealPinBtn = document.querySelector("#revealPinBtn");
const resetPinBtn = document.querySelector("#resetPinBtn");

let currentPlan = [];
let latestAgents = [];
let latestSummary = {};
let latestPlanPreview = false;
let latestApcall = [];
let latestWhiteboard = null;
let latestHealing = { enabled: true, attempts: {} };
let healingEnabled = true;
let qaEnabled = true;
let launchBlocked = false;
const openConsoles = new Set();
const userClosedConsoles = new Set();
let consoleZ = 40;
let consoleOffset = 0;
let currentSettings;
let currentWorkspacePath = "";
let recognition;
let isBusy = false;
let lastVoiceCommand = "";
let talkBackEnabled = localStorage.getItem("jarvisTalkBack") === "true";
let agentAnnouncementPrimed = false;
let summaryAnnouncementPrimed = false;
let previousRunningCount = 0;
const processedVoiceFinals = new Set();
const recentVoiceChunks = new Map();
const agentStatusMemory = new Map();
const voiceChunkDedupeMs = 30000;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    // The server returned HTML/text instead of JSON. This almost always means
    // the running console process is an older build that does not know this
    // route yet (Python does not hot-reload), so it answered with a 404 page.
    if (response.status === 404 || /^\s*</.test(text)) {
      throw new Error(
        `${path} is not available on the running server (status ${response.status}). ` +
          `Restart the console: stop it, then run \`python scripts/jarvis_console.py\` again.`,
      );
    }
    throw new Error(`${path} returned a non-JSON response (status ${response.status}).`);
  }
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

function agentStage(status) {
  const normalized = String(status || "planned").toLowerCase();
  if (["running", "starting"].includes(normalized)) return "executing";
  if (normalized === "complete") return "committed";
  if (normalized === "conflict") return "needs master";
  if (normalized === "healing") return "repairing";
  if (normalized === "testing") return "qa testing";
  if (normalized === "failed") return "failed";
  if (normalized === "stopped") return "stopped";
  return "queued";
}

function setBusy(nextBusy, message = "") {
  isBusy = nextBusy;
  document.body.classList.toggle("busy", nextBusy);
  if (!consoleState) return;
  consoleState.textContent = nextBusy ? message || "Working" : "Ready";
  consoleState.className = nextBusy ? "state-busy" : "state-ready";
}

function updateLastSeen() {
  if (!consoleUpdated) return;
  consoleUpdated.textContent = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function canTalkBack() {
  return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
}

function updateTalkBackUi() {
  if (!talkBackButton || !voiceReplyStatus) return;
  if (!canTalkBack()) {
    talkBackButton.disabled = true;
    talkBackButton.textContent = "Talk Back Unavailable";
    voiceReplyStatus.textContent = "This browser does not support spoken replies.";
    return;
  }
  talkBackButton.textContent = talkBackEnabled ? "Talk Back On" : "Talk Back Off";
  talkBackButton.classList.toggle("primary", talkBackEnabled);
  voiceReplyStatus.textContent = talkBackEnabled
    ? "Voice replies are live. Jarvis will announce progress and completions."
    : "Voice replies are muted.";
}

function speak(text, priority = false) {
  if (!talkBackEnabled || !canTalkBack()) return;
  const message = String(text || "").replace(/\s+/g, " ").trim();
  if (!message) return;
  if (priority) {
    window.speechSynthesis.cancel();
  }
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.rate = 1;
  utterance.pitch = 0.92;
  utterance.volume = 0.95;
  window.speechSynthesis.speak(utterance);
  if (voiceReplyStatus) {
    voiceReplyStatus.textContent = `Jarvis said: ${message}`;
  }
}

function setTalkBack(enabled) {
  talkBackEnabled = enabled;
  localStorage.setItem("jarvisTalkBack", enabled ? "true" : "false");
  updateTalkBackUi();
  if (enabled) {
    speak("Voice replies online. I will report mission progress and agent completion.", true);
  } else if (canTalkBack()) {
    window.speechSynthesis.cancel();
  }
}

function appendMissionText(text) {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return;
  const current = taskInput.value.trim();
  taskInput.value = current ? `${current} ${cleaned}` : cleaned;
}

function normalizeVoiceText(text) {
  return text.replace(/\s+/g, " ").trim().toLowerCase();
}

function expireVoiceChunks(nowMs) {
  recentVoiceChunks.forEach((seenAt, chunk) => {
    if (nowMs - seenAt > voiceChunkDedupeMs) {
      recentVoiceChunks.delete(chunk);
    }
  });
}

function shouldProcessVoiceChunk(text) {
  const key = normalizeVoiceText(text);
  if (!key) return false;
  const nowMs = Date.now();
  expireVoiceChunks(nowMs);
  if (recentVoiceChunks.has(key)) return false;
  recentVoiceChunks.set(key, nowMs);
  return true;
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
  latestSummary = summary;
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
  if (consoleGate) {
    consoleGate.textContent = launchGate.textContent;
    consoleGate.className = dirty || missingJcode || !availableProviders.length ? "state-error" : "state-ready";
  }
  launchGate.className = `gate ${dirty || missingJcode || !availableProviders.length ? "blocked" : "ready"}`;
  launchBlocked = dirty || missingJcode || !availableProviders.length;
  backendStatus.textContent = state.jcode_available ? "online" : "blocked";
  backendStatus.className = `badge ${state.jcode_available ? "status-complete" : "status-failed"}`;
  backendJcode.textContent = state.jcode_path || "-";
  backendWorkspace.textContent = workspace.path || "-";
  backendGit.textContent = workspace.is_git_repo ? `${workspace.branch} / ${workspace.dirty ? "dirty" : "clean"}` : "not a git repo";
  renderService(state.service || {});
  if (document.activeElement !== workspacePath) {
    workspacePath.value = workspace.path || "";
  }
  if (document.activeElement !== newProjectParent) {
    newProjectParent.value = workspace.path || "";
  }
  announceSummaryChange(summary);
}

function announceSummaryChange(summary) {
  const running = Number(summary.running || 0) + Number(summary.starting || 0);
  const complete = Number(summary.complete || 0);
  const failed = Number(summary.failed || 0);
  const conflict = Number(summary.conflict || 0);
  if (summaryAnnouncementPrimed && previousRunningCount > 0 && running === 0) {
    if (conflict > 0) {
      speak("All active workers stopped. A merge conflict needs master review.", true);
    } else if (failed > 0) {
      speak(`All active workers stopped. ${complete} completed and ${failed} failed.`, true);
    } else {
      speak(`All active workers completed. ${complete} agents finished successfully.`, true);
    }
  }
  previousRunningCount = running;
  summaryAnnouncementPrimed = true;
}

function renderService(service) {
  if (!serviceStatus || !servicePath) return;
  if (!service.supported) {
    serviceStatus.textContent = service.error || "not supported";
    serviceStatus.className = "status-failed";
    servicePath.textContent = "-";
    installServiceButton.disabled = true;
    removeServiceButton.disabled = true;
    return;
  }
  serviceStatus.textContent = service.installed ? "installed" : "not installed";
  serviceStatus.className = service.installed ? "status-complete" : "status-planned";
  servicePath.textContent = service.path || "-";
  installServiceButton.disabled = service.installed;
  removeServiceButton.disabled = !service.installed;
}

function renderArmy() {
  if (!armyBoard || !armySummary) return;
  const plannedNodes = currentPlan.map((item, index) => ({
    ...item,
    id: `planned-${index + 1}`,
    status: "planned",
  }));
  const recentAgents = latestAgents.slice(-12);
  const nodes = latestPlanPreview && plannedNodes.length ? plannedNodes : recentAgents.length ? recentAgents : plannedNodes;
  const active = nodes.filter((agent) => ["starting", "running"].includes(agent.status)).length;
  const complete = latestSummary.complete || nodes.filter((agent) => agent.status === "complete").length;
  const conflict = latestSummary.conflict || nodes.filter((agent) => agent.status === "conflict").length;
  armySummary.textContent = `${nodes.length} workers / ${active} active / ${complete} done`;
  armySummary.className = `badge ${conflict ? "status-conflict" : active ? "status-running" : complete ? "status-complete" : ""}`;
  const masterStatus = conflict ? "conflict" : active ? "running" : complete ? "complete" : "planned";
  armyBoard.innerHTML = `
    <article class="army-node master-node army-${escapeHtml(masterStatus)}">
      <span class="node-type">Master Jcode</span>
      <strong>Rules, routing, merge control</strong>
      <small>Plans the team, watches git, merges completed branches, and stops on conflicts.</small>
      <small class="${statusClass(masterStatus)}">stage: ${escapeHtml(agentStage(masterStatus))}</small>
    </article>
  `;
  if (!nodes.length) {
    armyBoard.insertAdjacentHTML(
      "beforeend",
      '<article class="army-node"><span class="node-type">Waiting</span><strong>No mission planned</strong><small>Dictate or type a task, then click Plan Agents.</small></article>',
    );
    return;
  }
  nodes.forEach((agent, index) => {
    const status = String(agent.status || "planned").toLowerCase();
    const route = agent.provider || agent.model ? `${agent.provider || "smart"}/${agent.model || "auto"}` : "smart route";
    const node = document.createElement("article");
    node.className = `army-node army-${status}`;
    node.innerHTML = `
      <span class="node-type">Unit ${index + 1}</span>
      <strong>${escapeHtml(agent.role || "Worker Agent")}</strong>
      <small>${escapeHtml(agentStage(status))}: ${escapeHtml(agent.task || "Awaiting scope.")}</small>
      <small>model: ${escapeHtml(route)}</small>
      <small>branch: ${escapeHtml(agent.branch || "pending")}</small>
      <span class="node-pulse ${statusClass(status)}">${escapeHtml(status)}</span>
    `;
    armyBoard.appendChild(node);
  });
}

function renderPlan(plan) {
  currentPlan = plan || [];
  planEl.innerHTML = "";
  if (!currentPlan.length) {
    planEl.innerHTML = '<div class="plan-item subtle">No plan yet.</div>';
    renderArmy();
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
  renderArmy();
}

function renderAgents(agents) {
  latestAgents = agents || [];
  announceAgentStatusChanges(latestAgents);
  agentsEl.innerHTML = "";
  const active = latestAgents.filter((agent) => ["starting", "running", "healing", "testing"].includes(agent.status)).length;
  agentCount.textContent = `${active} active`;
  if (!latestAgents.length) {
    agentsEl.innerHTML = '<div class="agent subtle">No workers launched.</div>';
    renderArmy();
    return;
  }
  latestAgents.forEach((agent) => {
    const node = document.createElement("article");
    node.className = `agent ${agent.kind === "healer" ? "agent-healer" : ""}`;
    if (openConsoles.has(agent.id)) node.classList.add("selected");
    node.innerHTML = `
      <header>
        <strong>${escapeHtml(agent.id)}</strong>
        <span class="${statusClass(agent.status)}">${escapeHtml(agent.status)}</span>
      </header>
      <p>${escapeHtml(agent.role)}</p>
      <small>${escapeHtml(agent.task)}</small>
      <small>branch: ${escapeHtml(agent.branch || "pending")}</small>
      <small class="model-route">model: ${escapeHtml(agent.provider || "pending")}/${escapeHtml(agent.model || "pending")}</small>
      <small>pid: ${escapeHtml(agent.pid || "-")}</small>
      <button data-inspect="${escapeHtml(agent.id)}">Open Console</button>
    `;
    agentsEl.appendChild(node);
  });
  agentsEl.querySelectorAll("[data-inspect]").forEach((button) => {
    button.addEventListener("click", () => openConsole(button.dataset.inspect, { focus: true }));
  });
  renderArmy();
}

function announceAgentStatusChanges(agents) {
  const currentIds = new Set();
  agents.forEach((agent) => {
    const id = agent.id;
    const status = String(agent.status || "planned").toLowerCase();
    currentIds.add(id);
    const previous = agentStatusMemory.get(id);
    const role = agent.role || id;
    if (agentAnnouncementPrimed && !previous && ["starting", "running"].includes(status)) {
      speak(`${role} is now running.`);
    } else if (agentAnnouncementPrimed && previous && previous !== status) {
      if (status === "complete") {
        speak(`${role} completed. Changes are committed on ${agent.branch || "its branch"}.`, true);
      } else if (status === "failed") {
        speak(`${role} failed. Check the worker terminal for the error log.`, true);
      } else if (status === "conflict") {
        speak(`${role} hit a merge conflict. Master intervention is required.`, true);
      } else if (status === "stopped") {
        speak(`${role} was stopped.`);
      } else if (status === "running") {
        speak(`${role} is running.`);
      }
    }
    agentStatusMemory.set(id, status);
  });
  [...agentStatusMemory.keys()].forEach((id) => {
    if (!currentIds.has(id)) agentStatusMemory.delete(id);
  });
  agentAnnouncementPrimed = true;
}

/* ---- floating per-agent live consoles -------------------- */
function consoleIdFor(agentId) {
  return `console-${agentId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
}

function showConsoleDeck() {
  if (consoleDeck) consoleDeck.hidden = false;
}

function openConsole(agentId, options = {}) {
  if (!agentId) return;
  userClosedConsoles.delete(agentId);
  openConsoles.add(agentId);
  showConsoleDeck();
  renderConsoleDeck(latestAgents);
  if (options.focus) focusConsole(agentId);
  pollConsoleLogs();
}

function closeConsole(agentId) {
  openConsoles.delete(agentId);
  userClosedConsoles.add(agentId);
  const win = document.getElementById(consoleIdFor(agentId));
  if (win) win.remove();
  if (!openConsoles.size && consoleDeck) consoleDeck.hidden = true;
}

function focusConsole(agentId) {
  const win = document.getElementById(consoleIdFor(agentId));
  if (!win) return;
  consoleZ += 1;
  win.style.zIndex = String(consoleZ);
  win.classList.remove("minimized");
}

function makeConsoleDraggable(win, handle) {
  let startX = 0;
  let startY = 0;
  let baseX = 0;
  let baseY = 0;
  let dragging = false;
  const onMove = (event) => {
    if (!dragging) return;
    win.style.left = `${baseX + (event.clientX - startX)}px`;
    win.style.top = `${baseY + (event.clientY - startY)}px`;
  };
  const onUp = () => {
    dragging = false;
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
  };
  handle.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button")) return;
    dragging = true;
    startX = event.clientX;
    startY = event.clientY;
    const rect = win.getBoundingClientRect();
    baseX = rect.left;
    baseY = rect.top;
    consoleZ += 1;
    win.style.zIndex = String(consoleZ);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  });
}

function renderConsoleDeck(agents) {
  if (!consoleDeck) return;
  const roster = agents || [];
  // Auto-open a console for each freshly active agent the user has not closed.
  roster.forEach((agent) => {
    if (
      ["starting", "running", "healing", "testing"].includes(agent.status) &&
      !openConsoles.has(agent.id) &&
      !userClosedConsoles.has(agent.id)
    ) {
      openConsoles.add(agent.id);
    }
  });
  if (openConsoles.size) showConsoleDeck();
  else consoleDeck.hidden = true;
  // Remove windows for agents that vanished.
  [...consoleDeck.children].forEach((win) => {
    const id = win.dataset.agent;
    if (!roster.some((agent) => agent.id === id) || !openConsoles.has(id)) {
      openConsoles.delete(id);
      win.remove();
    }
  });
  [...openConsoles].forEach((agentId) => {
    const agent = roster.find((item) => item.id === agentId);
    if (!agent) {
      openConsoles.delete(agentId);
      return;
    }
    let win = document.getElementById(consoleIdFor(agentId));
    if (!win) {
      win = document.createElement("article");
      win.className = "live-console";
      win.id = consoleIdFor(agentId);
      win.dataset.agent = agentId;
      consoleZ += 1;
      win.style.zIndex = String(consoleZ);
      win.style.left = `${40 + (consoleOffset % 5) * 38}px`;
      win.style.top = `${90 + (consoleOffset % 5) * 32}px`;
      consoleOffset += 1;
      win.innerHTML = `
        <header class="lc-head">
          <span class="lc-dot"></span>
          <strong class="lc-title"></strong>
          <span class="lc-status"></span>
          <span class="lc-actions">
            <button data-act="min" title="Minimize">_</button>
            <button data-act="stop" title="Stop">&#9632;</button>
            <button data-act="close" title="Close">&times;</button>
          </span>
        </header>
        <pre class="lc-log">Connecting to agent stream...</pre>
      `;
      consoleDeck.appendChild(win);
      makeConsoleDraggable(win, win.querySelector(".lc-head"));
      win.querySelector('[data-act="min"]').addEventListener("click", () => win.classList.toggle("minimized"));
      win.querySelector('[data-act="close"]').addEventListener("click", () => closeConsole(agentId));
      win.querySelector('[data-act="stop"]').addEventListener("click", () => {
        const a = latestAgents.find((item) => item.id === agentId);
        if (a && a.kind !== "healer" && ["failed", "conflict"].includes(String(a.status))) {
          healAgent(agentId).catch((error) => alert(error.message));
        } else {
          stopAgent(agentId).catch((error) => alert(error.message));
        }
      });
      win.querySelector(".lc-head").addEventListener("pointerdown", () => focusConsole(agentId));
    }
    const status = String(agent.status || "").toLowerCase();
    win.className = `live-console lc-${status}${agent.kind === "healer" ? " lc-healer" : ""}${win.classList.contains("minimized") ? " minimized" : ""}`;
    win.querySelector(".lc-title").textContent = `${agent.id} · ${agent.role || ""}`;
    const statusEl = win.querySelector(".lc-status");
    statusEl.textContent = status;
    statusEl.className = `lc-status ${statusClass(agent.status)}`;
    const stopBtn = win.querySelector('[data-act="stop"]');
    if (agent.kind !== "healer" && ["failed", "conflict"].includes(status)) {
      stopBtn.innerHTML = "&#10227;";
      stopBtn.title = "Dispatch healer";
    } else {
      stopBtn.innerHTML = "&#9632;";
      stopBtn.title = "Stop";
      stopBtn.disabled = !["starting", "running", "healing"].includes(status);
    }
  });
}

async function pollConsoleLogs() {
  const ids = [...openConsoles].filter((id) => {
    const win = document.getElementById(consoleIdFor(id));
    return win && !win.classList.contains("minimized");
  });
  await Promise.all(
    ids.map(async (id) => {
      try {
        const response = await api(`/api/agent/log?id=${encodeURIComponent(id)}`);
        const win = document.getElementById(consoleIdFor(id));
        if (!win) return;
        const log = win.querySelector(".lc-log");
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
        log.textContent = response.log || "Waiting for output...";
        if (atBottom) log.scrollTop = log.scrollHeight;
      } catch (error) {
        const win = document.getElementById(consoleIdFor(id));
        if (win) win.querySelector(".lc-log").textContent = error.message;
      }
    }),
  );
}

function renderLiveActivity(state) {
  if (!liveActivity) return;
  const summary = state.summary || {};
  const agents = state.agents || [];
  const running = agents.filter((agent) => ["starting", "running", "healing"].includes(agent.status));
  const recent = (state.apcall || []).slice(-4).reverse();
  if (!agents.length && !recent.length) {
    liveActivity.innerHTML = '<span class="subtle">Idle. Enter a mission and launch the swarm.</span>';
    return;
  }
  const headline = running.length
    ? `${running.length} agent${running.length === 1 ? "" : "s"} working · ${summary.complete || 0} done`
    : `${summary.complete || 0} done · ${summary.failed || 0} failed · ${summary.conflict || 0} conflict`;
  const lines = recent
    .map(
      (msg) =>
        `<span class="la-line"><b>${escapeHtml(msg.from)}</b> &rarr; ${escapeHtml(msg.to)} <i>${escapeHtml(msg.type)}</i></span>`,
    )
    .join("");
  liveActivity.innerHTML = `<span class="la-headline">${escapeHtml(headline)}</span>${lines}`;
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

function apcallTypeClass(type) {
  const value = String(type || "").toLowerCase();
  if (value.startsWith("heal") || value === "status.failed") return "ap-heal";
  if (value.includes("complete") || value.includes("merged") || value.includes("combined")) return "ap-good";
  if (value.startsWith("plan")) return "ap-plan";
  if (value.startsWith("task") || value.startsWith("swarm")) return "ap-task";
  return "ap-default";
}

function renderApcallInto(container, messages, limit) {
  if (!container) return;
  const list = (messages || []).slice(-limit);
  if (!list.length) {
    container.innerHTML = '<div class="apcall-msg subtle">No apcall traffic yet.</div>';
    return;
  }
  container.innerHTML = "";
  list
    .slice()
    .reverse()
    .forEach((msg) => {
      const node = document.createElement("div");
      node.className = `apcall-msg ${apcallTypeClass(msg.type)}`;
      node.innerHTML = `
        <span class="ap-time">${escapeHtml(msg.time || "")}</span>
        <span class="ap-route"><b>${escapeHtml(msg.from)}</b> &rarr; ${escapeHtml(msg.to)}</span>
        <span class="ap-type">${escapeHtml(msg.type)}</span>
      `;
      container.appendChild(node);
    });
  container.scrollTop = 0;
}

function renderApcall(messages) {
  latestApcall = messages || [];
  renderApcallInto(apcallFeed, latestApcall, 40);
  renderApcallInto(wbFeed, latestApcall, 20);
  if (apcallSummary) {
    const heals = latestApcall.filter((msg) => String(msg.type || "").startsWith("heal")).length;
    apcallSummary.textContent = latestApcall.length ? `${latestApcall.length} msgs / ${heals} heal` : "idle";
    apcallSummary.className = `badge ${heals ? "status-conflict" : latestApcall.length ? "status-running" : ""}`;
  }
}

function renderHealing(healing, agents) {
  latestHealing = healing || { enabled: true, attempts: {} };
  healingEnabled = latestHealing.enabled !== false;
  const roster = agents || [];
  const healers = roster.filter((agent) => agent.kind === "healer");
  const activeHealers = healers.filter((agent) => ["starting", "running"].includes(agent.status)).length;
  const healed = roster.filter((agent) => agent.healed).length;
  const watching = roster.filter(
    (agent) => agent.kind !== "healer" && ["starting", "running", "healing", "testing"].includes(agent.status),
  ).length;
  if (healToggle) {
    healToggle.textContent = healingEnabled ? "Auto-Repair: On" : "Auto-Repair: Off";
    healToggle.classList.toggle("primary", healingEnabled);
    healToggle.classList.toggle("danger", !healingEnabled);
  }
  if (healingStatus) {
    healingStatus.textContent = activeHealers ? `${activeHealers} repairing` : healingEnabled ? "armed" : "muted";
    healingStatus.className = `badge ${activeHealers ? "status-running" : healingEnabled ? "status-complete" : "status-failed"}`;
  }
  if (healWatch) {
    healWatch.textContent = `Watching ${watching} agent${watching === 1 ? "" : "s"} · ${healed} healed.`;
  }
  if (metricHealing) {
    metricHealing.textContent = activeHealers || healed || 0;
  }
  if (!healingBoard) return;
  if (!healers.length) {
    healingBoard.innerHTML = '<div class="heal-card subtle">No repairs dispatched. The healing agent is watching.</div>';
    return;
  }
  healingBoard.innerHTML = "";
  healers
    .slice(-6)
    .reverse()
    .forEach((healer) => {
      const node = document.createElement("div");
      node.className = `heal-card ${statusClass(healer.status)}`;
      node.innerHTML = `
        <strong>${escapeHtml(healer.id)}</strong>
        <small>repairing: ${escapeHtml(healer.heals || "-")}</small>
        <small>attempt ${escapeHtml(healer.attempt || 1)} · <span class="${statusClass(healer.status)}">${escapeHtml(healer.status)}</span></small>
        <small>branch: ${escapeHtml(healer.branch || "-")}</small>
      `;
      healingBoard.appendChild(node);
    });
}

let pinRevealed = false;
let lastTunnelUrl = "";

function renderRemoteAccess(t) {
  if (!t) return;
  // Badge
  if (tunnelBadge) {
    tunnelBadge.textContent = t.running ? "tunnel active" : t.url ? "tunnel ready" : "no tunnel";
    tunnelBadge.className = `badge ${t.running || t.url ? "status-complete" : "status-failed"}`;
  }
  // URL
  if (remoteUrl) {
    remoteUrl.textContent = t.url || "Tunnel not connected — install cloudflared or run manually";
    remoteUrl.style.color = t.url ? "#7cc7ff" : "rgba(200,216,240,0.4)";
  }
  // PIN
  if (remotePin) {
    remotePin.textContent = pinRevealed ? (t.pin || "------") : "••••••";
  }
  // QR
  if (remoteQr && remoteQrPlaceholder) {
    if (t.qr_url && t.url) {
      remoteQr.src = t.qr_url;
      remoteQr.hidden = false;
      remoteQrPlaceholder.hidden = true;
    } else {
      remoteQr.hidden = true;
      remoteQrPlaceholder.hidden = false;
    }
  }
  lastTunnelUrl = t.url || "";
}

async function pollTunnel() {
  try {
    const t = await api("/api/tunnel/status");
    renderRemoteAccess(t);
    // Keep polling until the tunnel is up
    if (!t.url) setTimeout(pollTunnel, 4000);
    else setTimeout(pollTunnel, 30000);
  } catch {
    setTimeout(pollTunnel, 8000);
  }
}

async function resetPin() {
  if (!confirm("Generate a new PIN? All active remote sessions will be invalidated.")) return;
  try {
    const t = await api("/api/pin/reset", { method: "POST", body: JSON.stringify({}) });
    pinRevealed = true;
    renderRemoteAccess(t);
  } catch (err) {
    alert(err.message);
  }
}

function renderBudget(state) {
  const budget = state.budget;
  const queueDepth = state.dispatch_queue_depth || 0;
  if (!budgetBar) return;
  if (!budget) { budgetBar.hidden = true; return; }
  budgetBar.hidden = false;
  const spent = budget.spent || 0;
  const total = budget.total || 1;
  const pct = Math.min(100, Math.round((spent / total) * 100));
  if (budgetLabel) budgetLabel.textContent = `Budget: ${spent} / ${total} agents used`;
  if (budgetFill) {
    budgetFill.style.width = `${pct}%`;
    budgetFill.className = `budget-fill${pct >= 90 ? " budget-danger" : pct >= 70 ? " budget-warn" : ""}`;
  }
  if (queueLabel) queueLabel.textContent = queueDepth ? `Queue: ${queueDepth} pending` : "Queue: clear";
}

function taskStatusLabel(status) {
  const map = {
    todo: "to do",
    in_progress: "in progress",
    healing: "being repaired",
    testing: "in QA",
    done: "done",
    failed: "failed",
  };
  return map[status] || status || "to do";
}

function renderWhiteboard(wb) {
  latestWhiteboard = wb || null;
  const tasks = (wb && wb.tasks) || [];
  const hasBoard = Boolean(tasks.length);
  if (!hasBoard) return;
  if (wbMission) wbMission.textContent = wb.mission || "-";
  const done = wb.done_count ?? tasks.filter((task) => task.status === "done").length;
  const total = wb.total_count ?? tasks.length;
  if (wbStatus) {
    wbStatus.textContent = wb.status || "planning";
    wbStatus.className = `badge ${wb.status === "executing" ? "status-running" : wb.status === "complete" || wb.status === "merged" ? "status-complete" : ""}`;
  }
  if (wbProgressBar) wbProgressBar.style.width = `${total ? Math.round((done / total) * 100) : 0}%`;
  if (wbProgressText) wbProgressText.textContent = `${done} / ${total} done`;
  if (wbTasks) {
    wbTasks.innerHTML = "";
    tasks.forEach((task) => {
      const status = String(task.status || "todo");
      const node = document.createElement("article");
      node.className = `wb-task wb-${status}`;
      const pickedBy = task.picked_by ? ` · picked up by ${escapeHtml(task.picked_by)}` : "";
      const assignee = task.assignee ? `${escapeHtml(task.assignee)}${pickedBy}` : task.recreated ? "recreated · awaiting pickup" : "unassigned";
      node.innerHTML = `
        <span class="wb-check ${status === "done" ? "checked" : ""}">${status === "done" ? "&#10003;" : status === "failed" ? "&#10005;" : ""}</span>
        <div class="wb-task-body">
          <strong>${escapeHtml(task.title)}</strong>
          <p>${escapeHtml(task.detail)}</p>
          <small class="${statusClass(status === "in_progress" ? "running" : status)}">${escapeHtml(taskStatusLabel(status))} · ${assignee}</small>
          <small class="wb-branch">${escapeHtml(task.branch || "branch pending")}</small>
        </div>
      `;
      wbTasks.appendChild(node);
    });
  }
  if (wbNotes) {
    const notes = wb.notes || [];
    if (!notes.length) {
      wbNotes.innerHTML = '<div class="wb-note subtle">No notes yet. Add planning context for the swarm.</div>';
    } else {
      wbNotes.innerHTML = "";
      notes
        .slice()
        .reverse()
        .forEach((note) => {
          const node = document.createElement("div");
          node.className = "wb-note";
          node.innerHTML = `<b>${escapeHtml(note.author)}</b> <span>${escapeHtml(note.text)}</span><small>${escapeHtml(note.time)}</small>`;
          wbNotes.appendChild(node);
        });
    }
  }
}

function openWhiteboard() {
  if (!latestWhiteboard || !latestWhiteboard.tasks || !latestWhiteboard.tasks.length) return;
  renderWhiteboard(latestWhiteboard);
  whiteboardModal.hidden = false;
}

function closeWhiteboardModal() {
  whiteboardModal.hidden = true;
}

async function triggerKillswitch() {
  if (!confirm("Kill ALL agents and clear the dispatch queue? This cannot be undone.")) return;
  setBusy(true, "Kill-switch engaged");
  try {
    const state = await api("/api/killswitch", { method: "POST", body: JSON.stringify({}) });
    renderAll(state);
    speak("All agents terminated.");
  } finally {
    setBusy(false);
  }
}

async function toggleHealing() {
  setBusy(true, "Updating healing");
  try {
    const next = !healingEnabled;
    const state = await api("/api/healing/toggle", {
      method: "POST",
      body: JSON.stringify({ enabled: next }),
    });
    renderHealing(state.healing, state.agents || latestAgents);
    renderApcall(state.apcall || latestApcall);
    speak(next ? "Self healing armed." : "Self healing muted.");
  } finally {
    setBusy(false);
  }
}

function renderQA(qa, agents) {
  qaEnabled = !(qa && qa.enabled === false);
  const qaAgents = (agents || []).filter((agent) => agent.kind === "qa");
  const activeQa = qaAgents.filter((agent) => ["starting", "running"].includes(agent.status)).length;
  if (qaToggle) {
    qaToggle.textContent = activeQa ? `QA Check: ${activeQa} running` : qaEnabled ? "QA Check: On" : "QA Check: Off";
    qaToggle.classList.toggle("primary", qaEnabled);
    qaToggle.classList.toggle("danger", !qaEnabled);
  }
}

async function toggleQa() {
  setBusy(true, "Updating QA");
  try {
    const next = !qaEnabled;
    const state = await api("/api/qa/toggle", {
      method: "POST",
      body: JSON.stringify({ enabled: next }),
    });
    renderQA(state.qa, state.agents || latestAgents);
    renderApcall(state.apcall || latestApcall);
    speak(next ? "QA verification on. Agents will be checked after they finish." : "QA verification off.");
  } finally {
    setBusy(false);
  }
}

async function healAgent(id) {
  setBusy(true, "Dispatching healer");
  speak(`Dispatching self healing agent to ${id}.`, true);
  try {
    await api("/api/heal", { method: "POST", body: JSON.stringify({ id }) });
    await refresh();
  } finally {
    setBusy(false);
  }
}

async function postWhiteboardNote() {
  const text = wbNoteInput.value.trim();
  if (!text) return;
  const state = await api("/api/whiteboard/note", {
    method: "POST",
    body: JSON.stringify({ text, author: "master" }),
  });
  wbNoteInput.value = "";
  renderWhiteboard(state.whiteboard);
  renderApcall(state.apcall || latestApcall);
}

function mergeableAgents() {
  return latestAgents.filter((agent) => agent.status === "complete" && agent.kind !== "healer" && !agent.merged);
}

function activeAgentCount() {
  const summary = latestSummary || {};
  return (
    Number(summary.running || 0) +
    Number(summary.starting || 0) +
    Number(summary.healing || 0) +
    Number(summary.testing || 0)
  );
}

function updateMainButtons() {
  const active = activeAgentCount();
  const conflict = Number(latestSummary.conflict || 0);
  const mergeable = mergeableAgents().length;
  let label = "Launch Swarm";
  let mode = "launch";
  let cls = "primary";
  let disabled = false;
  if (active > 0) {
    label = `Stop ${active} Agent${active === 1 ? "" : "s"}`;
    mode = "stop";
    cls = "danger";
  } else if (conflict > 0) {
    label = "Resolve Conflict in Workspace";
    mode = "conflict";
    cls = "danger";
    disabled = true;
  } else if (mergeable > 0) {
    label = "Merge & Combine";
    mode = "merge";
    cls = "primary";
  } else if (launchBlocked) {
    label = "Commit/Stash to Launch";
    mode = "blocked";
    cls = "primary";
    disabled = true;
  }
  [launchButton, wbActionButton].forEach((button) => {
    if (!button) return;
    button.textContent = label;
    button.dataset.mode = mode;
    button.disabled = disabled;
    button.classList.toggle("primary", cls === "primary");
    button.classList.toggle("danger", cls === "danger");
  });
}

async function mainAction() {
  const mode = launchButton?.dataset.mode || "launch";
  if (mode === "stop") return stopAll();
  if (mode === "merge") return mergeFinished();
  if (mode === "conflict") {
    alert("A merge conflict needs resolving in the workspace, then launch again.");
    return;
  }
  if (mode === "blocked") {
    alert(launchGate.textContent || "Workspace is not ready to launch.");
    return;
  }
  return launchSwarm();
}

async function launchSwarm() {
  const task = taskInput.value.trim();
  if (!task) {
    alert("Enter a mission first.");
    return;
  }
  setBusy(true, "Launching swarm");
  speak(`Launching the swarm for: ${task}`, true);
  try {
    const editedPlan = gatherPlanFromDom();
    const state = await api("/api/launch", {
      method: "POST",
      body: JSON.stringify({
        task,
        max_agents: Number(agentLimit.value),
        plan: editedPlan.length ? editedPlan : undefined,
      }),
    });
    renderAll(state);
    openWhiteboard();
    showConsoleDeck();
    renderConsoleDeck(state.agents || []);
    pollConsoleLogs();
  } finally {
    setBusy(false);
  }
}

async function stopAll() {
  const running = latestAgents.filter((agent) => ["starting", "running", "healing"].includes(agent.status));
  if (!running.length) return;
  if (!confirm(`Stop ${running.length} running agent(s)?`)) return;
  setBusy(true, "Stopping all agents");
  speak("Stopping all running agents.", true);
  try {
    for (const agent of running) {
      await api("/api/agent/stop", { method: "POST", body: JSON.stringify({ id: agent.id }) }).catch(() => {});
    }
    await refresh();
  } finally {
    setBusy(false);
  }
}

function renderAll(state) {
  latestPlanPreview = Boolean(state.plan_preview);
  gitStatus.textContent = state.git_status || "Clean";
  renderMetrics(state);
  if (document.activeElement?.closest?.("#plan") !== planEl) {
    renderPlan(state.plan);
  }
  renderAgents(state.agents || []);
  renderEvents(state.events || []);
  renderApcall(state.apcall || []);
  renderHealing(state.healing, state.agents || []);
  renderQA(state.qa, state.agents || []);
  renderBudget(state);
  renderWhiteboard(state.whiteboard);
  renderConsoleDeck(state.agents || []);
  renderLiveActivity(state);
  updateMainButtons();
}

async function refresh() {
  const wasBusy = isBusy;
  if (!wasBusy) setBusy(true, "Scanning");
  try {
    const state = await api("/api/status");
    updateLastSeen();
    renderAll(state);
    await pollConsoleLogs();
  } finally {
    if (!wasBusy) setBusy(false);
  }
}

async function browseWorkspace(path = workspacePath.value || currentWorkspacePath) {
  setBusy(true, "Browsing");
  speak("Browsing workspace folders.");
  try {
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
  } finally {
    setBusy(false);
  }
}

async function setWorkspace(path = workspacePath.value) {
  setBusy(true, "Setting workspace");
  speak("Switching active workspace.");
  try {
    await api("/api/workspace/set", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    await refresh();
    await browseWorkspace(path);
  } finally {
    setBusy(false);
  }
}

async function createProject() {
  setBusy(true, "Creating project");
  speak("Creating a new git ready project.");
  try {
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
    speak(`Project ${name} is ready.`, true);
  } finally {
    setBusy(false);
  }
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
  setBusy(true, "Saving settings");
  speak("Saving model router settings.");
  try {
    const saved = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify(collectSettings()),
    });
    renderSettings(saved);
    await refresh();
    speak("Settings saved.");
  } finally {
    setBusy(false);
  }
}

async function planAgents() {
  setBusy(true, "Planning");
  try {
    const task = taskInput.value.trim();
    if (!task) return;
    const response = await api("/api/plan", {
      method: "POST",
      body: JSON.stringify({ task, max_agents: Number(agentLimit.value) }),
    });
    renderAll(response);
    updateLastSeen();
    openWhiteboard();
    speak(`Plan ready. ${response.plan?.length || 0} tasks on the whiteboard.`, true);
  } finally {
    setBusy(false);
  }
}

async function mergeFinished() {
  if (!confirm("Merge completed agent branches into the current branch?")) return;
  setBusy(true, "Merging");
  speak("Starting master merge review.", true);
  try {
    await api("/api/merge", { method: "POST", body: "{}" });
    await refresh();
    speak("Master merge completed.", true);
  } finally {
    setBusy(false);
  }
}

async function installService() {
  setBusy(true, "Installing service");
  speak("Creating auto run service.");
  try {
    await api("/api/service/install", { method: "POST", body: "{}" });
    await refresh();
    speak("Auto run service is installed.");
  } finally {
    setBusy(false);
  }
}

async function removeService() {
  setBusy(true, "Removing service");
  speak("Removing auto run service.");
  try {
    await api("/api/service/remove", { method: "POST", body: "{}" });
    await refresh();
    speak("Auto run service removed.");
  } finally {
    setBusy(false);
  }
}

async function stopAgent(id) {
  if (!confirm(`Stop ${id}?`)) return;
  setBusy(true, "Stopping worker");
  speak(`Stopping ${id}.`, true);
  try {
    await api("/api/agent/stop", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
    await refresh();
  } finally {
    setBusy(false);
  }
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
    lastVoiceCommand = "";
    processedVoiceFinals.clear();
    recentVoiceChunks.clear();
  };
  recognition.onend = () => {
    voiceRing.classList.remove("listening");
    voiceButton.textContent = "Start Voice";
  };
  recognition.onresult = (event) => {
    let interimText = "";
    const finalChunks = [];
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const result = event.results[i];
      const transcript = result[0].transcript;
      const cleaned = transcript.replace(/\s+/g, " ").trim();
      if (!cleaned) continue;
      if (result.isFinal) {
        const resultKey = `${i}:${normalizeVoiceText(cleaned)}`;
        if (!processedVoiceFinals.has(resultKey) && shouldProcessVoiceChunk(cleaned)) {
          processedVoiceFinals.add(resultKey);
          finalChunks.push(cleaned);
        }
        continue;
      }
      interimText += ` ${cleaned}`;
    }
    if (interimText.trim()) {
      voiceStatus.textContent = `Listening: ${interimText.trim()}`;
    }
    finalChunks.forEach((text) => {
      const lower = text.toLowerCase();
      const commandKey = normalizeVoiceText(text);
      if (commandKey === lastVoiceCommand) return;
      if (
        lower.includes("launch swarm") ||
        lower.includes("start workers") ||
        lower.includes("deploy agents")
      ) {
        lastVoiceCommand = commandKey;
        speak("Launch command received. Deploying the swarm.", true);
        launchSwarm().catch((error) => alert(error.message));
        return;
      }
      if (lower.includes("plan agents")) {
        lastVoiceCommand = commandKey;
        speak("Plan command received. Building the checklist.", true);
        planAgents().catch((error) => alert(error.message));
        return;
      }
      if (lower.includes("merge finished")) {
        lastVoiceCommand = commandKey;
        speak("Merge command received. Preparing master merge.", true);
        mergeFinished().catch((error) => alert(error.message));
        return;
      }
      if (lower.includes("talk back on") || lower.includes("enable voice replies")) {
        lastVoiceCommand = commandKey;
        setTalkBack(true);
        return;
      }
      if (lower.includes("talk back off") || lower.includes("mute voice replies")) {
        lastVoiceCommand = commandKey;
        setTalkBack(false);
        return;
      }
      appendMissionText(text);
      voiceStatus.textContent = `Added: ${text}`;
      speak("Mission text added.");
    });
  };
}

agentLimit.addEventListener("input", () => {
  agentLimitValue.textContent = agentLimit.value;
});
launchButton.addEventListener("click", () => mainAction().catch((error) => alert(error.message)));
wbActionButton.addEventListener("click", () => mainAction().catch((error) => alert(error.message)));
consolesButton.addEventListener("click", () => {
  const running = latestAgents.filter((agent) => ["starting", "running", "healing", "testing", "failed", "conflict"].includes(agent.status));
  if (!running.length) {
    alert("No agents to show. Launch the swarm first.");
    return;
  }
  running.forEach((agent) => openConsole(agent.id));
});
openWorkspaceButton.addEventListener("click", () => browseWorkspace().catch((error) => alert(error.message)));
setWorkspaceButton.addEventListener("click", () => setWorkspace().catch((error) => alert(error.message)));
createProjectButton.addEventListener("click", () => createProject().catch((error) => alert(error.message)));
installServiceButton.addEventListener("click", () => installService().catch((error) => alert(error.message)));
removeServiceButton.addEventListener("click", () => removeService().catch((error) => alert(error.message)));
talkBackButton.addEventListener("click", () => setTalkBack(!talkBackEnabled));
settingsButton.addEventListener("click", () => openSettings().catch((error) => alert(error.message)));
healToggle.addEventListener("click", () => toggleHealing().catch((error) => alert(error.message)));
qaToggle.addEventListener("click", () => toggleQa().catch((error) => alert(error.message)));
if (killswitchButton) killswitchButton.addEventListener("click", () => triggerKillswitch().catch((error) => alert(error.message)));
if (copyUrlBtn) copyUrlBtn.addEventListener("click", () => {
  if (lastTunnelUrl) navigator.clipboard.writeText(lastTunnelUrl).then(() => {
    copyUrlBtn.textContent = "✓"; setTimeout(() => { copyUrlBtn.textContent = "⧉"; }, 1200);
  });
});
if (revealPinBtn) revealPinBtn.addEventListener("click", () => {
  pinRevealed = !pinRevealed;
  revealPinBtn.textContent = pinRevealed ? "🙈" : "👁";
  pollTunnel();
});
if (resetPinBtn) resetPinBtn.addEventListener("click", () => resetPin().catch((err) => alert(err.message)));
closeWhiteboard.addEventListener("click", () => closeWhiteboardModal());
wbNoteButton.addEventListener("click", () => postWhiteboardNote().catch((error) => alert(error.message)));
wbNoteInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") postWhiteboardNote().catch((error) => alert(error.message));
});
whiteboardModal.addEventListener("click", (event) => {
  if (event.target === whiteboardModal) closeWhiteboardModal();
});
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

// ── Central Agent Memory ──────────────────────────────────────────────────
const memoryBoard    = document.getElementById("memoryBoard");
const memoryCount    = document.getElementById("memoryCount");
const memorySearch   = document.getElementById("memorySearch");
const memorySearchBtn  = document.getElementById("memorySearchBtn");
const memoryRefreshBtn = document.getElementById("memoryRefreshBtn");
const memoryClearBtn   = document.getElementById("memoryClearBtn");

function tagColor(tags) {
  if (!tags) return "var(--muted)";
  const t = tags.toLowerCase();
  if (t.includes("error") || t.includes("fail") || t.includes("block")) return "var(--red)";
  if (t.includes("api") || t.includes("contract"))  return "var(--violet)";
  if (t.includes("decision") || t.includes("arch")) return "var(--amber)";
  if (t.includes("heal") || t.includes("repair"))   return "var(--heal)";
  if (t.includes("qa") || t.includes("test"))       return "var(--blue)";
  return "var(--cyan)";
}

function renderMemory(entries) {
  memoryCount.textContent = `${entries.length} entr${entries.length === 1 ? "y" : "ies"}`;
  if (!entries.length) {
    memoryBoard.innerHTML = `<p class="subtle mem-empty">No memories yet. Agents write here automatically during missions.</p>`;
    return;
  }
  memoryBoard.innerHTML = entries.map((m) => {
    const date  = new Date(m.ts * 1000).toLocaleTimeString();
    const color = tagColor(m.tags);
    const tags  = (m.tags || "").split(",").filter(Boolean).map(
      (t) => `<span class="mem-tag" style="border-color:${color};color:${color}">${t.trim()}</span>`
    ).join("");
    return `
      <article class="mem-card" data-key="${m.key}">
        <div class="mem-card-head">
          <span class="mem-key">${m.key}</span>
          <span class="mem-meta">${m.agent_id ? `<b>${m.agent_id}</b> · ` : ""}${date}</span>
          <button class="mem-del-btn icon-btn" data-key="${m.key}" title="Delete">✕</button>
        </div>
        <p class="mem-summary">${m.summary}</p>
        ${tags ? `<div class="mem-tags">${tags}</div>` : ""}
        ${m.payload ? `<details class="mem-payload"><summary>payload</summary><pre>${m.payload}</pre></details>` : ""}
      </article>`;
  }).join("");

  memoryBoard.querySelectorAll(".mem-del-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const key = btn.dataset.key;
      if (!confirm(`Delete memory: "${key}"?`)) return;
      await fetch(`/api/memory/${encodeURIComponent(key)}`, { method: "DELETE" });
      loadMemory().catch(() => {});
    });
  });
}

async function loadMemory(q = "") {
  const url = q ? `/api/memory?q=${encodeURIComponent(q)}` : "/api/memory";
  const res  = await fetch(url);
  const data = await res.json();
  renderMemory(Array.isArray(data) ? data : []);
}

memorySearchBtn.addEventListener("click", () => loadMemory(memorySearch.value.trim()).catch(() => {}));
memorySearch.addEventListener("keydown", (e) => { if (e.key === "Enter") loadMemory(memorySearch.value.trim()).catch(() => {}); });
memoryRefreshBtn.addEventListener("click", () => loadMemory().catch(() => {}));
memoryClearBtn.addEventListener("click", async () => {
  if (!confirm("Clear ALL agent memories? This cannot be undone.")) return;
  await fetch("/api/memory/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  loadMemory().catch(() => {});
});

setInterval(() => loadMemory(memorySearch.value.trim()).catch(() => {}), 8000);
loadMemory().catch(() => {});

setupVoice();
updateTalkBackUi();
pollTunnel();
refresh().catch((error) => {
  gitStatus.textContent = error.message;
  setBusy(false);
});
browseWorkspace().catch(() => {});
setInterval(() => refresh().catch(() => {}), 1500);
