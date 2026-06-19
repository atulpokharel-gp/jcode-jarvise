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

let currentPlan = [];
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

function statusClass(status) {
  return `status-${String(status || "planned").toLowerCase()}`;
}

function renderPlan(plan) {
  currentPlan = plan || [];
  planEl.innerHTML = "";
  if (!currentPlan.length) {
    planEl.innerHTML = '<div class="plan-item subtle">No plan yet.</div>';
    return;
  }
  currentPlan.forEach((item) => {
    const node = document.createElement("div");
    node.className = "plan-item";
    node.innerHTML = `<strong>${item.role}</strong><p class="subtle">${item.task}</p>`;
    planEl.appendChild(node);
  });
}

function renderAgents(agents) {
  agentsEl.innerHTML = "";
  const active = agents.filter((agent) => ["starting", "running"].includes(agent.status)).length;
  agentCount.textContent = `${active} active`;
  if (!agents.length) {
    agentsEl.innerHTML = '<div class="agent subtle">No workers launched.</div>';
    return;
  }
  agents.forEach((agent) => {
    const node = document.createElement("article");
    node.className = "agent";
    node.innerHTML = `
      <header>
        <strong>${agent.id}</strong>
        <span class="${statusClass(agent.status)}">${agent.status}</span>
      </header>
      <p>${agent.role}</p>
      <small>${agent.task}</small>
      <small>branch: ${agent.branch || "pending"}</small>
      <small>commit: ${agent.commit || "not committed yet"}</small>
      <small>worktree: ${agent.worktree || "pending"}</small>
    `;
    agentsEl.appendChild(node);
  });
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

async function refresh() {
  const state = await api("/api/status");
  gitStatus.textContent = state.git_status || "Clean";
  renderPlan(state.plan);
  renderAgents(state.agents || []);
  renderEvents(state.events || []);
}

async function planAgents() {
  const task = taskInput.value.trim();
  if (!task) return;
  const response = await api("/api/plan", {
    method: "POST",
    body: JSON.stringify({ task }),
  });
  renderPlan(response.plan);
  renderEvents(response.events || []);
}

async function startWorkers() {
  const task = taskInput.value.trim();
  if (!task) return;
  if (!currentPlan.length) {
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
setInterval(() => refresh().catch(() => {}), 3000);
