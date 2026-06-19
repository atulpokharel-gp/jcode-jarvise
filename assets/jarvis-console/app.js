const taskInput = document.querySelector("#task");
const planButton = document.querySelector("#planButton");
const startButton = document.querySelector("#startButton");
const mergeButton = document.querySelector("#mergeButton");
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
const metricRunning = document.querySelector("#metricRunning");
const metricComplete = document.querySelector("#metricComplete");
const metricConflict = document.querySelector("#metricConflict");
const selectedAgent = document.querySelector("#selectedAgent");
const agentDetails = document.querySelector("#agentDetails");
const agentLog = document.querySelector("#agentLog");

let currentPlan = [];
let latestAgents = [];
let selectedAgentId = "";
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
    }))
    .filter((item) => item.task.length > 0);
  currentPlan = plan;
  return plan;
}

function renderMetrics(state) {
  const summary = state.summary || {};
  metricBranch.textContent = state.current_branch || "-";
  metricRunning.textContent = summary.running || 0;
  metricComplete.textContent = summary.complete || 0;
  metricConflict.textContent = summary.conflict || 0;
  const dirty = Boolean(state.root_dirty);
  launchGate.textContent = dirty ? "Commit or stash before launch" : "Ready to launch";
  launchGate.className = `gate ${dirty ? "blocked" : "ready"}`;
  startButton.disabled = dirty;
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
setInterval(() => refresh().catch(() => {}), 1500);
