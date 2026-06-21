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

// New feature refs
const templateSelect    = document.querySelector("#templateSelect");
const saveTemplateBtn   = document.querySelector("#saveTemplateBtn");
const diffPreviewBtn    = document.querySelector("#diffPreviewBtn");
const mergeBtn          = document.querySelector("#mergeBtn");
const mergePrBtn        = document.querySelector("#mergePrBtn");
const prLinkBar         = document.querySelector("#prLinkBar");
const prLink            = document.querySelector("#prLink");
const metricCost        = document.querySelector("#metricCost");
const metricTokens      = document.querySelector("#metricTokens");
const metricPending     = document.querySelector("#metricPending");
const webhookUrl        = document.querySelector("#webhookUrl");
const skipPermsToggle   = document.querySelector("#skipPermsToggle");
const notifyPermBtn     = document.querySelector("#notifyPermBtn");
const diffModal         = document.querySelector("#diffModal");
const closeDiffModal    = document.querySelector("#closeDiffModal");
const diffContent       = document.querySelector("#diffContent");
const timelineModal     = document.querySelector("#timelineModal");
const closeTimelineModal = document.querySelector("#closeTimelineModal");
const timelineContent   = document.querySelector("#timelineContent");
const timelineBtn       = document.querySelector("#timelineBtn");

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
  if (metricPending) metricPending.textContent = state.pending_workers || 0;
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
    const lastLine = agent.last_line ? `<div class="agent-last-line">${escapeHtml(agent.last_line)}</div>` : "";
    node.innerHTML = `
      <header>
        <strong>${escapeHtml(agent.id)}</strong>
        <span class="${statusClass(agent.status)}">${escapeHtml(agent.status)}</span>
      </header>
      <p>${escapeHtml(agent.role)}</p>
      <small>${escapeHtml(agent.task)}</small>
      ${lastLine}
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
          <span class="lc-line-count"></span>
          <span class="lc-actions">
            <button data-act="copy" title="Copy log">&#x2398;</button>
            <button data-act="min" title="Minimize">_</button>
            <button data-act="stop" title="Stop">&#9632;</button>
            <button data-act="close" title="Close">&times;</button>
          </span>
        </header>
        <div class="lc-log"></div>
      `;
      consoleDeck.appendChild(win);
      makeConsoleDraggable(win, win.querySelector(".lc-head"));
      win.querySelector('[data-act="min"]').addEventListener("click", () => {
        win.classList.toggle("minimized");
        if (!win.classList.contains("minimized")) pollConsoleLogs();
      });
      win.querySelector('[data-act="copy"]').addEventListener("click", () => {
        const text = [...win.querySelectorAll(".ll")].map(el => el.textContent).join("\n");
        navigator.clipboard.writeText(text).catch(() => {});
      });
      win.querySelector('[data-act="close"]').addEventListener("click", () => {
        resetLogOffset(agentId);
        closeConsole(agentId);
      });
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

// ── Log rendering helpers ────────────────────────────────────────────────────

const _ansiRe = /\x1b\[[0-9;]*[mGKHJA-Z]/g;
function stripAnsi(s) { return s.replace(_ansiRe, "").replace(/\r/g, ""); }

function logLineClass(raw) {
  const s = stripAnsi(raw).toLowerCase();
  if (/\berror\b|failed|exception|fatal|traceback|syntax error/.test(s)) return "ll-error";
  if (/\bwarn(ing)?\b/.test(s))                              return "ll-warn";
  if (/\btool:\s*(write|edit|create)|writing\b|updated?\s+file|creating file/.test(s)) return "ll-file";
  if (/git (commit|push|add)|committed\b|changes committed/.test(s))         return "ll-commit";
  if (/✓|passed|success|done|complete|all tests/.test(s))   return "ll-ok";
  if (/bash\(|running\s+`|executing\s+`|\$\s+\w/.test(s))   return "ll-cmd";
  return "";
}

function appendLogLines(logEl, lines) {
  const frag = document.createDocumentFragment();
  for (const raw of lines) {
    const el = document.createElement("div");
    el.className = "ll " + logLineClass(raw);
    el.textContent = stripAnsi(raw);
    frag.appendChild(el);
  }
  logEl.appendChild(frag);
}

// Track how many lines each console has already loaded
const _logOffsets = {}; // agentId -> number of lines displayed so far

function resetLogOffset(agentId) { delete _logOffsets[agentId]; }

async function pollConsoleLogs() {
  const ids = [...openConsoles].filter((id) => {
    const win = document.getElementById(consoleIdFor(id));
    return win && !win.classList.contains("minimized");
  });
  await Promise.all(
    ids.map(async (id) => {
      try {
        const after = _logOffsets[id] || 0;
        const res = await api(`/api/agent/log?id=${encodeURIComponent(id)}&after=${after}`);
        const win = document.getElementById(consoleIdFor(id));
        if (!win) return;
        const log = win.querySelector(".lc-log");
        if (!log) return;

        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 60;

        if (after === 0) {
          // First load: clear placeholder, show initial batch
          log.innerHTML = "";
          if (res.lines && res.lines.length) {
            appendLogLines(log, res.lines);
          } else {
            const placeholder = document.createElement("div");
            placeholder.className = "ll ll-muted";
            placeholder.textContent = "Waiting for agent output…";
            log.appendChild(placeholder);
          }
        } else if (res.lines && res.lines.length) {
          // Remove placeholder if present
          const placeholder = log.querySelector(".ll-muted");
          if (placeholder) placeholder.remove();
          appendLogLines(log, res.lines);
        }

        _logOffsets[id] = (res.start_line || 0) + (res.lines?.length || 0);

        // Update line counter
        const counter = win.querySelector(".lc-line-count");
        if (counter) counter.textContent = `${res.total_lines || 0} lines`;

        // Update running indicator
        win.classList.toggle("lc-running", !!res.running);

        if (atBottom) log.scrollTop = log.scrollHeight;
      } catch (error) {
        const win = document.getElementById(consoleIdFor(id));
        if (win) {
          const log = win.querySelector(".lc-log");
          if (log && !log.children.length) log.textContent = error.message;
        }
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
  renderCost(state);
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
  if (webhookUrl) webhookUrl.value = settings.notifications?.webhook_url || "";
  if (skipPermsToggle) skipPermsToggle.checked = settings.agents?.skip_permissions !== false;
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
  return {
    strategy: strategySelect.value,
    providers,
    notifications: { webhook_url: webhookUrl?.value?.trim() || "" },
    agents: { skip_permissions: skipPermsToggle?.checked !== false },
  };
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

// ═══════════════════════════════════════════════════════════════════════════
// CODE STUDIO  — Multi-agent Monaco editor with live worktree sync
// ═══════════════════════════════════════════════════════════════════════════

const AGENT_PALETTE = [
  '#00f0ff', // cyan
  '#00ff9d', // green
  '#bf00ff', // purple
  '#ffc400', // amber
  '#ff3ddd', // magenta
  '#2979ff', // blue
  '#ff5500', // orange
  '#a855f7', // violet
];

// Language detection from file extension
function studioLang(path) {
  const ext = (path || '').split('.').pop().toLowerCase();
  return {
    js:'javascript', mjs:'javascript', cjs:'javascript',
    ts:'typescript', tsx:'typescript', jsx:'javascript',
    py:'python', rs:'rust', go:'go', java:'java', cs:'csharp',
    css:'css', scss:'scss', less:'less',
    html:'html', htm:'html', xml:'xml',
    json:'json', jsonc:'json', json5:'json',
    md:'markdown', mdx:'markdown',
    sh:'shell', bash:'shell', zsh:'shell', fish:'shell',
    yaml:'yaml', yml:'yaml', toml:'ini',
    cpp:'cpp', cc:'cpp', cxx:'cpp', c:'c', h:'cpp',
    rb:'ruby', php:'php', kt:'kotlin', swift:'swift',
    dart:'dart', sql:'sql', r:'r', lua:'lua',
    vue:'html', svelte:'html',
  }[ext] || 'plaintext';
}

// Studio state
let studioOpen          = false;
let studioMonacoReady   = false;
let studioLayout        = 1;
let studioSelectedAgent = null;
let studioLastSnap      = [];        // last snapshot for diffing
let studioInterval      = null;
const studioEditorMap   = new Map(); // agentId → {editor, model, container, decorIds}

// DOM refs (may be null if studio section hidden)
const studioSection     = document.getElementById('studioSection');
const studioBody        = document.getElementById('studioBody');
const studioToggleBtn   = document.getElementById('studioToggleBtn');
const studioTabbar      = document.getElementById('studioTabbar');
const studioEditorsCont = document.getElementById('studioEditors');
const studioFileTree    = document.getElementById('studioFileTree');
const studioSidebar     = document.getElementById('studioSidebar');
const studioAgentBadge  = document.getElementById('studioAgentBadge');
const studioLayoutBtns  = document.getElementById('studioLayoutBtns');
const studioStatusAgent = document.getElementById('studioStatusAgent');
const studioStatusFile  = document.getElementById('studioStatusFile');
const studioStatusLines = document.getElementById('studioStatusLines');
const studioStatusLang  = document.getElementById('studioStatusLang');
const studioStatusRight = document.getElementById('studioStatusRight');

// ── Jarvis dark theme definition ────────────────────────────────────────────
const JARVIS_THEME_DEF = {
  base: 'vs-dark', inherit: true,
  rules: [
    { token: '',             foreground: 'b8e8f0', background: '000608' },
    { token: 'comment',      foreground: '2e6070', fontStyle: 'italic'  },
    { token: 'comment.doc',  foreground: '2e7080', fontStyle: 'italic'  },
    { token: 'string',       foreground: '00ff9d'  },
    { token: 'string.escape',foreground: '00e8c0'  },
    { token: 'keyword',      foreground: '00f0ff', fontStyle: 'bold'    },
    { token: 'keyword.flow', foreground: '00d8ff'  },
    { token: 'number',       foreground: 'ffc400'  },
    { token: 'type',         foreground: 'bf00ff'  },
    { token: 'type.identifier', foreground: 'c060ff' },
    { token: 'function',     foreground: '2979ff'  },
    { token: 'variable',     foreground: 'b8e8f0'  },
    { token: 'variable.parameter', foreground: 'ff8a65' },
    { token: 'constant',     foreground: 'ffc400'  },
    { token: 'operator',     foreground: '00e0e8'  },
    { token: 'delimiter',    foreground: '4a7080'  },
    { token: 'tag',          foreground: '00f0ff'  },
    { token: 'attribute.name',  foreground: 'ffc400' },
    { token: 'attribute.value', foreground: '00ff9d' },
    { token: 'metatag',      foreground: 'bf00ff'  },
    { token: 'regexp',       foreground: 'ff3ddd'  },
    { token: 'decorator',    foreground: 'a855f7'  },
  ],
  colors: {
    'editor.background':              '#000608',
    'editor.foreground':              '#b8e8f0',
    'editorLineNumber.foreground':    '#2e5060',
    'editorLineNumber.activeForeground': '#00f0ff',
    'editor.lineHighlightBackground': '#00101880',
    'editor.lineHighlightBorder':     '#00000000',
    'editor.selectionBackground':     '#00f0ff26',
    'editor.inactiveSelectionBackground': '#00f0ff14',
    'editor.findMatchBackground':     '#00ff9d33',
    'editor.findMatchHighlightBackground': '#00ff9d18',
    'editorCursor.foreground':        '#00f0ff',
    'editorCursor.background':        '#000608',
    'editorGutter.background':        '#000608',
    'editorGutter.modifiedBackground':'#00f0ff',
    'editorGutter.addedBackground':   '#00ff9d',
    'editorGutter.deletedBackground': '#ff0055',
    'editorIndentGuide.background1':  '#0a2030',
    'editorIndentGuide.activeBackground1': '#00f0ff40',
    'editorBracketMatch.background':  '#00f0ff22',
    'editorBracketMatch.border':      '#00f0ff',
    'editorOverviewRuler.border':     '#00000000',
    'scrollbar.shadow':               '#000000',
    'scrollbarSlider.background':     '#2e506050',
    'scrollbarSlider.hoverBackground':'#00f0ff40',
    'scrollbarSlider.activeBackground':'#00f0ff70',
    'minimap.background':             '#000608',
    'editor.rangeHighlightBackground':'#00f0ff0a',
    'editorWidget.background':        '#00080f',
    'editorWidget.border':            '#00f0ff30',
    'input.background':               '#00080f',
    'input.border':                   '#00f0ff30',
    'input.foreground':               '#b8e8f0',
    'focusBorder':                    '#00f0ff60',
  }
};

// ── Monaco init (lazy — only on studio open) ─────────────────────────────────
function initMonaco(cb) {
  if (studioMonacoReady) { cb(); return; }
  if (typeof require === 'undefined') {
    console.warn('[studio] Monaco loader not available');
    return;
  }
  require(['vs/editor/editor.main'], () => {
    monaco.editor.defineTheme('jarvis', JARVIS_THEME_DEF);
    studioMonacoReady = true;
    cb();
  });
}

// ── Create / get a Monaco editor pane for an agent ───────────────────────────
function ensureEditorPane(agentId, color) {
  if (studioEditorMap.has(agentId)) return studioEditorMap.get(agentId);

  // Outer pane
  const pane = document.createElement('div');
  pane.className = 'studio-pane';
  pane.dataset.agent = agentId;
  pane.style.setProperty('--agent-color', color);

  // Pane header
  const head = document.createElement('div');
  head.className = 'studio-pane-head';
  head.innerHTML = `
    <span class="studio-pane-dot" style="background:${color};box-shadow:0 0 8px ${color}"></span>
    <span class="studio-pane-role" id="pane-role-${agentId}">—</span>
    <span class="studio-pane-file" id="pane-file-${agentId}">No files yet</span>
    <span class="studio-pane-lines" id="pane-lines-${agentId}"></span>
  `;
  pane.appendChild(head);

  // Monaco container
  const monacoDiv = document.createElement('div');
  monacoDiv.className = 'studio-monaco';
  monacoDiv.id = `monaco-${agentId}`;
  pane.appendChild(monacoDiv);

  studioEditorsCont.appendChild(pane);

  // Create editor
  const model = monaco.editor.createModel('// Waiting for agent to write code…', 'plaintext');
  const editor = monaco.editor.create(monacoDiv, {
    model,
    theme:          'jarvis',
    readOnly:       true,
    automaticLayout: true,
    fontSize:        13,
    fontFamily:      "'Share Tech Mono', 'Fira Code', 'Cascadia Code', monospace",
    fontLigatures:   true,
    lineHeight:      21,
    minimap:         { enabled: studioLayout === 1, scale: 1 },
    scrollBeyondLastLine: false,
    smoothScrolling: true,
    cursorBlinking: 'smooth',
    renderLineHighlight: 'all',
    roundedSelection: false,
    padding:         { top: 12, bottom: 12 },
    scrollbar: {
      verticalScrollbarSize:   6,
      horizontalScrollbarSize: 6,
    },
    overviewRulerLanes: 3,
    glyphMargin: true,
    folding:     true,
    lineDecorationsWidth: 4,
    lineNumbersMinChars:  3,
  });

  const entry = { editor, model, pane, color, decorIds: [] };
  studioEditorMap.set(agentId, entry);
  return entry;
}

// ── Update one editor with new content, highlighting changed lines ────────────
function applyFileToEditor(agentId, filePath, content, color) {
  const entry = studioEditorMap.get(agentId);
  if (!entry) return;
  const { editor, model, decorIds } = entry;

  const lang = studioLang(filePath);
  const oldContent = model.getValue();
  const changed = oldContent !== content;

  // Update language
  monaco.editor.setModelLanguage(model, lang);

  if (changed) {
    // Find changed line numbers
    const oldLines = oldContent.split('\n');
    const newLines = content.split('\n');
    const changedNums = [];
    const maxLen = Math.max(oldLines.length, newLines.length);
    for (let i = 0; i < maxLen; i++) {
      if ((oldLines[i] || '') !== (newLines[i] || '')) changedNums.push(i + 1);
    }

    // Set content (preserves undo stack via edit operation)
    const fullRange = model.getFullModelRange();
    model.pushEditOperations([], [{
      range: fullRange,
      text: content,
    }], () => null);

    // Highlight changed lines with agent color
    if (changedNums.length > 0 && changedNums.length < 400) {
      const hex = color.replace('#', '');
      // Inject dynamic CSS class for this agent's highlight color
      let styleEl = document.getElementById(`studio-style-${agentId}`);
      if (!styleEl) {
        styleEl = document.createElement('style');
        styleEl.id = `studio-style-${agentId}`;
        document.head.appendChild(styleEl);
      }
      styleEl.textContent = `.studio-changed-${agentId} { background: ${color}18 !important; border-left: 2px solid ${color} !important; }`;

      const newDecors = changedNums.map(line => ({
        range: new monaco.Range(line, 1, line, 999),
        options: {
          isWholeLine:    true,
          className:      `studio-changed-${agentId}`,
          overviewRuler:  { color, position: monaco.editor.OverviewRulerLane.Left },
          glyphMarginClassName: 'studio-glyph-changed',
        },
      }));

      // Replace old decorations
      const ids = editor.createDecorationsCollection(
        entry.decorIds.length ? [] : newDecors
      );
      entry.decorIds = editor.deltaDecorations(entry.decorIds, newDecors);

      // Scroll to first change
      editor.revealLineInCenterIfOutsideViewport(changedNums[0], 1);

      // Remove highlights after 4 seconds
      setTimeout(() => {
        entry.decorIds = editor.deltaDecorations(entry.decorIds, []);
      }, 4000);
    } else if (newLines.length > 0) {
      // New content — scroll to bottom (agent is actively writing)
      editor.revealLine(newLines.length, 1);
    }
  }

  // Update pane header
  const roleEl = document.getElementById(`pane-role-${agentId}`);
  const fileEl = document.getElementById(`pane-file-${agentId}`);
  const linesEl = document.getElementById(`pane-lines-${agentId}`);
  if (roleEl && entry.role) roleEl.textContent = entry.role;
  if (fileEl) fileEl.textContent = filePath.split('/').pop();
  if (linesEl) linesEl.textContent = `${content.split('\n').length} lines`;
}

// ── Render agent tabs ────────────────────────────────────────────────────────
function renderStudioTabs(snap) {
  if (!studioTabbar) return;
  const sel = studioSelectedAgent || (snap[0]?.agent_id);
  studioTabbar.innerHTML = snap.map(a => {
    const color  = AGENT_PALETTE[a.color_idx] || '#00f0ff';
    const active = a.agent_id === sel ? ' active' : '';
    const file   = a.active_file?.path?.split('/').pop() || 'idle';
    return `
      <button class="studio-tab${active}" data-agent="${a.agent_id}"
              style="--tab-color:${color}" title="${escapeHtml(a.role)}">
        <span class="studio-tab-dot" style="background:${color};box-shadow:0 0 6px ${color}"></span>
        <span class="studio-tab-role">${escapeHtml((a.role||a.agent_id).split(' ').slice(0,2).join(' '))}</span>
        <span class="studio-tab-file">${escapeHtml(file)}</span>
        <span class="studio-tab-status studio-status-${a.status}"></span>
      </button>`;
  }).join('');
  studioTabbar.querySelectorAll('.studio-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      studioSelectedAgent = btn.dataset.agent;
      renderStudioTabs(studioLastSnap);
      renderStudioSidebar(studioLastSnap);
      focusStudioAgent(studioSelectedAgent);
    });
  });
}

// ── Render file tree sidebar ─────────────────────────────────────────────────
function renderStudioSidebar(snap) {
  if (!studioFileTree) return;
  const agent = snap.find(a => a.agent_id === studioSelectedAgent) || snap[0];
  if (!agent || !agent.files?.length) {
    studioFileTree.innerHTML = '<p class="studio-empty">No modified files yet.</p>';
    return;
  }
  const color = AGENT_PALETTE[agent.color_idx] || '#00f0ff';
  studioFileTree.innerHTML = agent.files.map(f => {
    const name = f.path.split('/').pop();
    const dir  = f.path.includes('/') ? f.path.split('/').slice(0, -1).join('/') : '';
    return `
      <div class="studio-file-item" data-agent="${agent.agent_id}" data-path="${escapeHtml(f.path)}"
           title="${escapeHtml(f.path)}">
        <span class="studio-file-icon">${fileIcon(f.path)}</span>
        <div class="studio-file-info">
          <span class="studio-file-name">${escapeHtml(name)}</span>
          ${dir ? `<span class="studio-file-dir">${escapeHtml(dir)}</span>` : ''}
        </div>
        <span class="studio-file-lines">${f.lines}L</span>
      </div>`;
  }).join('');

  studioFileTree.querySelectorAll('.studio-file-item').forEach(item => {
    item.addEventListener('click', () => {
      const ag  = item.dataset.agent;
      const fp  = item.dataset.path;
      const a   = snap.find(x => x.agent_id === ag);
      const fObj = a?.files?.find(x => x.path === fp);
      if (fObj && studioMonacoReady) {
        applyFileToEditor(ag, fObj.path, fObj.content, AGENT_PALETTE[a.color_idx] || '#00f0ff');
        updateStudioStatusbar(a, fObj);
      }
    });
  });
}

// ── Focus / bring an agent's editor to top in split view ────────────────────
function focusStudioAgent(agentId) {
  if (!studioEditorMap.has(agentId)) return;
  const { editor } = studioEditorMap.get(agentId);
  editor.focus();
}

// ── Update the VS Code-style status bar ─────────────────────────────────────
function updateStudioStatusbar(agent, file) {
  if (!studioStatusAgent) return;
  const color = AGENT_PALETTE[agent.color_idx] || '#00f0ff';
  studioStatusAgent.textContent = agent.role || agent.agent_id;
  studioStatusAgent.style.color = color;
  studioStatusAgent.style.textShadow = `0 0 10px ${color}`;
  if (file) {
    studioStatusFile.textContent = file.path;
    studioStatusLines.textContent = `${file.lines} lines`;
    studioStatusLang.textContent = studioLang(file.path);
  }
}

// ── File icon helper ─────────────────────────────────────────────────────────
function fileIcon(path) {
  const ext = (path||'').split('.').pop().toLowerCase();
  const icons = {
    js:'🟡', ts:'🔵', tsx:'🔵', jsx:'🟡', py:'🐍', rs:'🦀',
    go:'🔵', java:'☕', cs:'🔷', css:'🎨', scss:'🎨',
    html:'🌐', json:'📋', md:'📝', sh:'⚙️', yaml:'⚙️',
    yml:'⚙️', sql:'🗄️', cpp:'⚙️', c:'⚙️', rb:'💎',
    php:'🐘', kt:'🔵', swift:'🍎',
  };
  return icons[ext] || '📄';
}

// ── Main studio refresh ──────────────────────────────────────────────────────
async function studioRefresh() {
  if (!studioOpen || !studioMonacoReady) return;
  try {
    const snap = await api('/api/studio/snapshot');
    studioLastSnap = snap;

    // Update badge
    if (studioAgentBadge) studioAgentBadge.textContent = `${snap.length} agent${snap.length !== 1 ? 's' : ''} writing`;

    if (!snap.length) {
      studioEditorsCont.innerHTML = '<div class="studio-idle"><p>Launch a swarm to watch agents code in real-time.</p><p class="subtle">Each agent\'s worktree files will appear here as they work.</p></div>';
      if (studioTabbar) studioTabbar.innerHTML = '';
      if (studioFileTree) studioFileTree.innerHTML = '<p class="studio-empty">No active agents.</p>';
      return;
    }

    // Auto-select first agent if none selected
    if (!studioSelectedAgent || !snap.find(a => a.agent_id === studioSelectedAgent)) {
      studioSelectedAgent = snap[0].agent_id;
    }

    renderStudioTabs(snap);
    renderStudioSidebar(snap);

    // Decide which agents to show in panes (based on layout)
    const slots = Math.min(studioLayout, snap.length);
    // Primary agent always first
    const ordered = [
      ...snap.filter(a => a.agent_id === studioSelectedAgent),
      ...snap.filter(a => a.agent_id !== studioSelectedAgent),
    ].slice(0, slots);

    // Remove panes for agents no longer shown
    studioEditorMap.forEach((entry, agentId) => {
      if (!ordered.find(a => a.agent_id === agentId)) {
        entry.pane.remove();
        entry.editor.dispose();
        entry.model.dispose();
        studioEditorMap.delete(agentId);
      }
    });

    // Ensure panes exist and update content
    for (const agent of ordered) {
      const color = AGENT_PALETTE[agent.color_idx] || '#00f0ff';
      const entry = ensureEditorPane(agent.agent_id, color);
      entry.role  = agent.role;
      if (agent.active_file) {
        applyFileToEditor(agent.agent_id, agent.active_file.path, agent.active_file.content, color);
      }
    }

    // Update minimap setting based on layout
    studioEditorMap.forEach(({ editor }) => {
      editor.updateOptions({ minimap: { enabled: studioLayout === 1 } });
    });

    // Update status bar for selected agent
    const selAgent = snap.find(a => a.agent_id === studioSelectedAgent);
    if (selAgent && selAgent.active_file) updateStudioStatusbar(selAgent, selAgent.active_file);

    if (studioStatusRight) studioStatusRight.textContent = `Refreshed ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    if (studioStatusRight) studioStatusRight.textContent = `Error: ${err.message}`;
  }
}

// ── Set layout (1 / 2 / 4 columns) ──────────────────────────────────────────
function setStudioLayout(cols) {
  studioLayout = cols;
  if (studioEditorsCont) studioEditorsCont.dataset.cols = String(cols);
  studioLayoutBtns?.querySelectorAll('.studio-layout-btn').forEach(btn => {
    btn.classList.toggle('active', Number(btn.dataset.cols) === cols);
  });
  // Force Monaco to re-layout
  studioEditorMap.forEach(({ editor }) => editor.layout());
  studioRefresh().catch(() => {});
}

studioLayoutBtns?.querySelectorAll('.studio-layout-btn').forEach(btn => {
  btn.addEventListener('click', () => setStudioLayout(Number(btn.dataset.cols)));
});

// ── Toggle studio open/closed ────────────────────────────────────────────────
studioToggleBtn?.addEventListener('click', () => {
  studioOpen = !studioOpen;
  if (studioBody) studioBody.hidden = !studioOpen;
  if (studioToggleBtn) studioToggleBtn.textContent = studioOpen ? 'Close Studio' : 'Open Studio';
  if (studioOpen) {
    initMonaco(() => {
      studioEditorsCont.dataset.cols = String(studioLayout);
      studioRefresh().catch(() => {});
      if (!studioInterval) {
        studioInterval = setInterval(() => studioRefresh().catch(() => {}), 2500);
      }
    });
  } else {
    if (studioInterval) { clearInterval(studioInterval); studioInterval = null; }
  }
});

// ── Cost / token meter ────────────────────────────────────────────────────
function renderCost(state) {
  const cost = state.cost || {};
  if (metricCost)   metricCost.textContent   = `$${(cost.cost_usd || 0).toFixed(4)}`;
  if (metricTokens) metricTokens.textContent =
    `${(cost.input_tokens || 0).toLocaleString()} / ${(cost.output_tokens || 0).toLocaleString()}`;
}

// ── Mission templates ─────────────────────────────────────────────────────
async function loadTemplates() {
  const tpls = await api("/api/templates");
  if (!templateSelect) return;
  templateSelect.innerHTML = '<option value="">— Load template —</option>';
  tpls.forEach((t) => {
    const o = document.createElement("option");
    o.value = t.prompt;
    o.textContent = t.name;
    o.dataset.id = t.id;
    templateSelect.appendChild(o);
  });
}

if (templateSelect) {
  templateSelect.addEventListener("change", () => {
    if (templateSelect.value) taskInput.value = templateSelect.value;
  });
}

if (saveTemplateBtn) {
  saveTemplateBtn.addEventListener("click", async () => {
    const prompt = taskInput.value.trim();
    if (!prompt) { alert("Enter a mission prompt first."); return; }
    const name = window.prompt("Template name:");
    if (!name) return;
    await api("/api/templates", {
      method: "POST",
      body: JSON.stringify({ name, prompt }),
    });
    loadTemplates().catch(() => {});
  });
}

// ── Browser notifications ─────────────────────────────────────────────────
function tryBrowserNotify(title, body) {
  if (Notification.permission === "granted") {
    new Notification(title, { body, icon: "/favicon.ico" });
  }
}

if (notifyPermBtn) {
  notifyPermBtn.addEventListener("click", () => {
    Notification.requestPermission().then((p) => {
      notifyPermBtn.textContent = p === "granted" ? "Notifications enabled ✓" : "Permission denied";
    });
  });
}

// Patch renderAll to fire browser notify on mission complete / agent fail
const _origRenderAll = renderAll;  // eslint-disable-line no-use-before-define
// (renderAll already defined above; we hook into renderEvents & mergeFinished instead)

// ── Diff preview ──────────────────────────────────────────────────────────
async function openDiffPreview() {
  diffContent.innerHTML = '<p class="subtle">Loading diffs…</p>';
  diffModal.hidden = false;
  const diffs = await api("/api/diff");
  if (!diffs.length) {
    diffContent.innerHTML = '<p class="subtle">No completed unmerged branches to preview.</p>';
    return;
  }
  diffContent.innerHTML = diffs.map((d) => `
    <div class="diff-agent">
      <div class="diff-agent-head">
        <span class="diff-role">${escapeHtml(d.role)}</span>
        <span class="diff-branch">${escapeHtml(d.branch)}</span>
      </div>
      <pre class="diff-stat">${escapeHtml(d.stat || '(no changes)')}</pre>
      <details class="diff-details">
        <summary>Full diff</summary>
        <pre class="diff-full">${escapeHtml(d.diff || '(empty)')}</pre>
      </details>
    </div>
  `).join("");
}

if (diffPreviewBtn)  diffPreviewBtn.addEventListener("click",  () => openDiffPreview().catch((e) => alert(e.message)));
if (closeDiffModal)  closeDiffModal.addEventListener("click",  () => { diffModal.hidden = true; });
diffModal?.addEventListener("click", (e) => { if (e.target === diffModal) diffModal.hidden = true; });

// ── Merge buttons ─────────────────────────────────────────────────────────
async function doMerge(autoPr = false) {
  if (!confirm(autoPr ? "Merge all complete branches and open a GitHub PR?" : "Merge all complete branches?")) return;
  setBusy(true, "Merging");
  try {
    const state = await api("/api/merge", {
      method: "POST",
      body: JSON.stringify({ auto_pr: autoPr }),
    });
    renderAll(state);
    if (state.pr?.ok && prLink && prLinkBar) {
      prLink.href = state.pr.url;
      prLink.textContent = state.pr.url;
      prLinkBar.hidden = false;
      tryBrowserNotify("Jarvis — PR Created", state.pr.url);
    }
    tryBrowserNotify("Jarvis — Mission Merged", `${(state.agents || []).filter(a => a.merged).length} branches merged`);
  } finally {
    setBusy(false);
  }
}

if (mergeBtn)   mergeBtn.addEventListener("click",   () => doMerge(false).catch((e) => alert(e.message)));
if (mergePrBtn) mergePrBtn.addEventListener("click", () => doMerge(true).catch((e) => alert(e.message)));

// ── Timeline view ─────────────────────────────────────────────────────────
function openTimeline() {
  const agents = latestAgents.filter((a) => a.started_at);
  if (!agents.length) {
    timelineContent.innerHTML = '<p class="subtle">No agents have started yet.</p>';
    timelineModal.hidden = false;
    return;
  }
  const starts = agents.map((a) => new Date(a.started_at).getTime());
  const ends   = agents.map((a) => a.ended_at ? new Date(a.ended_at).getTime() : Date.now());
  const tMin   = Math.min(...starts);
  const tMax   = Math.max(...ends);
  const span   = Math.max(tMax - tMin, 1000);

  const statusColors = {
    running: "var(--cyan)", complete: "var(--green)", failed: "var(--red)",
    healing: "var(--heal)", testing: "var(--blue)", conflict: "var(--red)",
    killed: "var(--muted)", starting: "var(--amber)",
  };

  timelineContent.innerHTML = `
    <div class="timeline-grid">
      ${agents.map((a) => {
        const s = new Date(a.started_at).getTime();
        const e = a.ended_at ? new Date(a.ended_at).getTime() : Date.now();
        const left  = ((s - tMin) / span * 100).toFixed(1);
        const width = Math.max(((e - s) / span * 100), 1).toFixed(1);
        const color = statusColors[a.status] || "var(--muted)";
        const dur   = Math.round((e - s) / 1000);
        const cost  = a.cost_usd ? ` · $${a.cost_usd.toFixed(4)}` : "";
        return `
          <div class="tl-row">
            <div class="tl-label" title="${escapeHtml(a.role)}">${escapeHtml((a.role || a.id).slice(0, 22))}</div>
            <div class="tl-track">
              <div class="tl-bar" style="left:${left}%;width:${width}%;background:${color};box-shadow:0 0 10px ${color}">
                <span class="tl-bar-label">${dur}s${cost}</span>
              </div>
            </div>
            <span class="tl-status" style="color:${color}">${a.status}</span>
          </div>`;
      }).join("")}
    </div>
  `;
  timelineModal.hidden = false;
}

if (timelineBtn)          timelineBtn.addEventListener("click",           () => openTimeline());
if (closeTimelineModal)   closeTimelineModal.addEventListener("click",    () => { timelineModal.hidden = true; });
timelineModal?.addEventListener("click", (e) => { if (e.target === timelineModal) timelineModal.hidden = true; });

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

// ── MCP Connector Hub ─────────────────────────────────────────────────────────

const mcpFilter            = document.querySelector("#mcpFilter");
const addCustomMcpBtn      = document.querySelector("#addCustomMcpBtn");
const mcpCatalogEl         = document.querySelector("#mcpCatalog");
const mcpConnectedSection  = document.querySelector("#mcpConnectedSection");
const mcpConnectedList     = document.querySelector("#mcpConnectedList");
const mcpConfigModal       = document.querySelector("#mcpConfigModal");
const closeMcpConfig       = document.querySelector("#closeMcpConfig");
const cancelMcpConfig      = document.querySelector("#cancelMcpConfig");
const saveMcpConfigBtn     = document.querySelector("#saveMcpConfig");
const mcpConfigTitle       = document.querySelector("#mcpConfigTitle");
const mcpConfigDesc        = document.querySelector("#mcpConfigDesc");
const mcpConfigEyebrow     = document.querySelector("#mcpConfigEyebrow");
const mcpConfigEnvFields   = document.querySelector("#mcpConfigEnvFields");
const mcpConfigCustomFields= document.querySelector("#mcpConfigCustomFields");
const mcpConfigTransport   = document.querySelector("#mcpConfigTransport");
const mcpConfigStdioFields = document.querySelector("#mcpConfigStdioFields");
const mcpConfigHttpFields  = document.querySelector("#mcpConfigHttpFields");
const mcpConfigCommand     = document.querySelector("#mcpConfigCommand");
const mcpConfigArgs        = document.querySelector("#mcpConfigArgs");
const mcpConfigUrl         = document.querySelector("#mcpConfigUrl");
const mcpConfigName        = document.querySelector("#mcpConfigName");
const mcpConfigCustomEnv   = document.querySelector("#mcpConfigCustomEnv");

let mcpCatalogData   = [];
let mcpConnectors    = [];
let mcpEditingId     = null;
let mcpCurrentEntry  = null;

// MCP brand emoji map — falls back to first letter
const MCP_EMOJI = {
  github: "🐙", figma: "🎨", slack: "💬", linear: "📋",
  notion: "📝", postgres: "🐘", "brave-search": "🔍",
  stripe: "💳", sentry: "🚨", puppeteer: "🤖",
};

async function loadMcpHub() {
  try {
    const [catRes, connRes] = await Promise.all([
      fetch("/api/mcp-connectors/catalog").then(r => r.json()),
      fetch("/api/mcp-connectors").then(r => r.json()),
    ]);
    mcpCatalogData = catRes.catalog || [];
    mcpConnectors  = connRes.connectors || [];
    renderMcpHub();
  } catch (_) {}
}

function activeCatalogConn(catalogId) {
  return mcpConnectors.find(c => c.catalog_id === catalogId && c.enabled !== false);
}

function renderMcpCard(entry, conn) {
  const connected = !!conn;
  const emoji = MCP_EMOJI[entry.id] || (entry.emoji?.length <= 2 ? entry.emoji : entry.id[0].toUpperCase());
  const tags  = (entry.tags || []).map(t => `<span class="mcp-tag">${t}</span>`).join("");
  const actions = connected
    ? `<button class="mcp-btn mcp-btn-edit" data-id="${conn.id}">Edit</button>
       <button class="mcp-btn mcp-btn-remove" data-id="${conn.id}">Remove</button>`
    : `<button class="mcp-btn mcp-btn-connect" data-catalog="${entry.id}">Connect</button>`;
  return `
    <div class="mcp-card${connected ? " mcp-card--on" : ""}" style="--mcp-accent:${entry.accent || "#00f0ff"}">
      <div class="mcp-accent-bar"></div>
      <div class="mcp-card-body">
        <span class="mcp-icon">${emoji}</span>
        <div class="mcp-card-info">
          <strong class="mcp-name">${entry.name}</strong>
          <div class="mcp-tags">${tags}</div>
          <p class="mcp-desc">${entry.description}</p>
        </div>
      </div>
      <div class="mcp-card-foot">
        <span class="mcp-dot${connected ? " mcp-dot--on" : ""}">
          ${connected ? "● Connected" : "○ Not configured"}
        </span>
        <div class="mcp-actions">${actions}</div>
      </div>
    </div>`;
}

function renderMcpHub() {
  const q = (mcpFilter?.value || "").toLowerCase().trim();
  const filtered = mcpCatalogData.filter(e =>
    !q ||
    e.name.toLowerCase().includes(q) ||
    e.description.toLowerCase().includes(q) ||
    (e.tags || []).some(t => t.includes(q))
  );

  // Custom connectors (catalog_id === "custom") go in the active section
  const customConns = mcpConnectors.filter(c => c.catalog_id === "custom" && c.enabled !== false);
  if (customConns.length) {
    mcpConnectedSection.hidden = false;
    mcpConnectedList.innerHTML = customConns.map(c => renderMcpCard(
      { id: "custom", name: c.name, accent: "#00f0ff", description: c.transport === "stdio"
          ? `${c.command} ${(c.args || []).join(" ")}`.trim()
          : c.url,
        tags: ["custom"], emoji: "⚡" },
      c
    )).join("");
    attachMcpCardEvents(mcpConnectedList);
  } else {
    mcpConnectedSection.hidden = true;
  }

  mcpCatalogEl.innerHTML = filtered.map(entry => {
    const conn = activeCatalogConn(entry.id);
    return renderMcpCard(entry, conn);
  }).join("");
  attachMcpCardEvents(mcpCatalogEl);
}

function attachMcpCardEvents(container) {
  container.querySelectorAll(".mcp-btn-connect").forEach(btn => {
    btn.addEventListener("click", () => openMcpConfig(btn.dataset.catalog, null));
  });
  container.querySelectorAll(".mcp-btn-edit").forEach(btn => {
    btn.addEventListener("click", () => {
      const conn = mcpConnectors.find(c => c.id === btn.dataset.id);
      if (conn) openMcpConfig(conn.catalog_id, conn);
    });
  });
  container.querySelectorAll(".mcp-btn-remove").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm("Remove this MCP connector?")) return;
      await fetch(`/api/mcp-connectors/${btn.dataset.id}`, { method: "DELETE" });
      loadMcpHub().catch(() => {});
    });
  });
}

function openMcpConfig(catalogId, existingConn) {
  const entry = mcpCatalogData.find(c => c.id === catalogId)
    || { id: "custom", name: "Custom", accent: "#00f0ff", description: "Custom MCP server.",
         env_vars: [], transport: "stdio", command: "", args: [], tags: ["custom"] };

  mcpCurrentEntry = entry;
  mcpEditingId    = existingConn?.id || null;

  mcpConfigTitle.textContent   = entry.name;
  mcpConfigDesc.textContent    = entry.description;
  mcpConfigEyebrow.textContent = mcpEditingId ? "Edit Connector" : "Connect";

  const isCustom = entry.id === "custom";
  mcpConfigCustomFields.hidden = !isCustom;

  if (isCustom) {
    mcpConfigName.value      = existingConn?.name || "";
    mcpConfigTransport.value = existingConn?.transport || "stdio";
    mcpConfigCommand.value   = existingConn?.command || "";
    mcpConfigArgs.value      = (existingConn?.args || []).join(" ");
    mcpConfigUrl.value       = existingConn?.url || "";
    // Rebuild custom env textarea
    const env = existingConn?.env || {};
    mcpConfigCustomEnv.value = Object.entries(env).map(([k, v]) => `${k}=${v}`).join("\n");
    updateMcpTransport();
  }

  // Build catalog env var fields
  mcpConfigEnvFields.innerHTML = (entry.env_vars || []).map(ev => {
    const val = (existingConn?.env || {})[ev.key] || "";
    return `
      <label for="mcpEnv_${ev.key}">${ev.label}</label>
      <div class="mcp-secret-row">
        <input id="mcpEnv_${ev.key}" type="${ev.secret ? "password" : "text"}"
               data-key="${ev.key}" value="${val}"
               placeholder="${ev.placeholder || ""}" class="mcp-env-input" />
        ${ev.secret ? `<button type="button" class="mcp-show-btn" data-tgt="mcpEnv_${ev.key}">show</button>` : ""}
      </div>`;
  }).join("");

  mcpConfigEnvFields.querySelectorAll(".mcp-show-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const inp = document.getElementById(btn.dataset.tgt);
      if (inp.type === "password") { inp.type = "text"; btn.textContent = "hide"; }
      else                          { inp.type = "password"; btn.textContent = "show"; }
    });
  });

  mcpConfigModal.hidden = false;
}

function updateMcpTransport() {
  const isHttp = mcpConfigTransport?.value !== "stdio";
  if (mcpConfigStdioFields) mcpConfigStdioFields.hidden = isHttp;
  if (mcpConfigHttpFields)  mcpConfigHttpFields.hidden  = !isHttp;
}

async function saveMcpConnector() {
  const entry    = mcpCurrentEntry;
  const isCustom = entry.id === "custom";
  const env      = {};

  // Collect named env var inputs
  document.querySelectorAll(".mcp-env-input").forEach(inp => {
    if (inp.value.trim()) env[inp.dataset.key] = inp.value.trim();
  });

  // Collect custom env textarea
  if (isCustom && mcpConfigCustomEnv.value.trim()) {
    mcpConfigCustomEnv.value.trim().split("\n").forEach(line => {
      const idx = line.indexOf("=");
      if (idx > 0) {
        const k = line.slice(0, idx).trim();
        const v = line.slice(idx + 1).trim();
        if (k) env[k] = v;
      }
    });
  }

  const body = {
    catalog_id: entry.id,
    name:       isCustom ? (mcpConfigName.value.trim() || "Custom") : entry.name,
    env,
  };

  if (isCustom) {
    body.transport = mcpConfigTransport.value;
    if (body.transport === "stdio") {
      body.command = mcpConfigCommand.value.trim();
      body.args    = mcpConfigArgs.value.trim().split(/\s+/).filter(Boolean);
    } else {
      body.url = mcpConfigUrl.value.trim();
    }
  }

  const url    = mcpEditingId ? `/api/mcp-connectors/${mcpEditingId}` : "/api/mcp-connectors";
  await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  mcpConfigModal.hidden = true;
  loadMcpHub().catch(() => {});
}

closeMcpConfig?.addEventListener("click",    () => { mcpConfigModal.hidden = true; });
cancelMcpConfig?.addEventListener("click",   () => { mcpConfigModal.hidden = true; });
saveMcpConfigBtn?.addEventListener("click",  saveMcpConnector);
addCustomMcpBtn?.addEventListener("click",   () => openMcpConfig("custom", null));
mcpFilter?.addEventListener("input",         renderMcpHub);
mcpConfigTransport?.addEventListener("change", updateMcpTransport);

loadMcpHub().catch(() => {});

// ── Mission History ────────────────────────────────────────────────────────────

const historyList       = document.querySelector("#historyList");
const historyRefreshBtn = document.querySelector("#historyRefreshBtn");

function renderHistory(missions) {
  if (!historyList) return;
  if (!missions || !missions.length) {
    historyList.innerHTML = '<p class="subtle">No completed missions yet. Merge a swarm to record the first entry.</p>';
    return;
  }
  historyList.innerHTML = missions.map(m => {
    const date = new Date(m.merged_at).toLocaleString();
    const branches = (m.branches || []).length;
    const costColor = m.cost_usd > 1 ? "var(--amber)" : m.cost_usd > 0.1 ? "var(--cyan)" : "var(--muted)";
    const prLink = m.pr_url ? `<a class="hist-pr" href="${escapeHtml(m.pr_url)}" target="_blank" rel="noopener">PR ↗</a>` : "";
    const title = m.title ? escapeHtml(m.title.slice(0, 90)) : "<em>untitled</em>";
    return `
      <div class="hist-row">
        <span class="hist-date">${date}</span>
        <span class="hist-title">${title}</span>
        <span class="hist-stat">${m.agents_done}/${m.agents_total} agents</span>
        <span class="hist-stat">${branches} branch${branches !== 1 ? "es" : ""}</span>
        <span class="hist-cost" style="color:${costColor}">$${m.cost_usd.toFixed(4)}</span>
        <span class="hist-tokens">${((m.tokens_in + m.tokens_out) / 1000).toFixed(1)}k tok</span>
        ${prLink}
      </div>`;
  }).join("");
}

async function loadHistory() {
  try {
    const res = await fetch("/api/history").then(r => r.json());
    renderHistory(res.history || []);
  } catch (_) {}
}

historyRefreshBtn?.addEventListener("click", () => loadHistory().catch(() => {}));
loadHistory().catch(() => {});
setInterval(() => loadHistory().catch(() => {}), 30000);

// ── End MCP Connector Hub ─────────────────────────────────────────────────────

setupVoice();
updateTalkBackUi();
pollTunnel();
loadTemplates().catch(() => {});
refresh().catch((error) => {
  gitStatus.textContent = error.message;
  setBusy(false);
});
browseWorkspace().catch(() => {});
setInterval(() => refresh().catch(() => {}), 1500);
