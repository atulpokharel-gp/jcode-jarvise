# Jarvis Master Console

Status: dynamic local console.

The Jarvis console is a browser UI for launching multiple Jcode worker agents
from one master screen. It keeps workers isolated with git worktrees, tracks
their branches and logs, and gives the master a single merge button that stops
on conflicts for manual resolution.

Run it from the repository root:

```powershell
python scripts/jarvis_console.py
```

Then open:

```text
http://127.0.0.1:8765
```

## How It Works

- The master types or dictates a mission.
- The backend control panel shows the active project directory, Jcode binary,
  git branch, and git clean/dirty state.
- The folder browser can open directories, switch the active workspace, or
  create a new git-initialized project.
- A single **Launch Swarm** control drives the whole run: it breaks the mission
  into a checklist, opens the whiteboard, and starts the workers in one step.
  The same button becomes **Stop Agents** while work is running and **Merge &
  Combine** once everything is done.
- The agent limit can scale up to 12 workers for a fuller company-style team:
  mission architect, UX, frontend, orchestration, security, database,
  customer advocates, QA, git integration, docs, and polish.
- The Agent Army map shows the master controller plus every planned or running
  worker, including stage, model route, branch, and status.
- The plan cards are still editable; if you tweak them before launching, the
  edited scopes are used instead of the auto-generated ones.
- Worker launch requires a clean active workspace so every branch has a clear base.
- Each worker gets its own branch and worktree under `.jcode/jarvis-console/`.
- Each worker runs `jcode run` with scoped instructions.
- When a worker exits, the console commits any remaining dirty changes in that
  worker worktree.
- The worker dashboard refreshes live and shows running, complete, failed, and
  conflict counts.
- Each worker opens its own floating **live console** that streams the real log
  tail. Consoles pop up automatically as workers start, can be dragged,
  minimized, or closed, and offer a stop (or dispatch-healer) control inline.
- The master can merge completed worker branches from the console.
- If git reports a conflict, the merge stops and the master resolves it in the
  root worktree.

## apcall Protocol

`apcall` (Agent Protocol Call) is the inter-agent message bus. Every lifecycle
transition is published as a structured message `{from, to, type, payload}` and
rendered live in the **Inter-Agent Mesh** panel. The master broadcasts the
mission (`plan.broadcast`), each agent contributes on the whiteboard
(`plan.contribute`), workers report status (`task.dispatch`, `status.complete`,
`status.failed`), and the self-healing agent negotiates repairs over the
`apcall://heal` bus (`heal.dispatch`, `heal.result`, `heal.giveup`). The feed is
capped at the most recent 200 messages.

The network design for turning this local message bus into a remote-capable
agent protocol lives in [APCALL_NETWORK_PROTOCOL.md](APCALL_NETWORK_PROTOCOL.md).

## Agent Whiteboard

The whiteboard pops up by itself on launch and is a live **checklist**. The
master's single "thought" (the mission) is broken into one task per agent. Each
task moves through `todo -> in progress -> done`, driven entirely by the real
agent assigned to it — no mock state. A progress bar tracks `done / total`, and
each task shows its assignee, branch, and dependencies (workers depend on the
Mission Architect; integration/QA/merge tasks depend on everyone).

If an agent fails and cannot be repaired, its task is **recreated** and handed
back to the board so another agent (the self-healing agent) can pick it up and
finish the work. Branches are combined back into the base branch at merge time,
and the board status moves `planning -> executing -> complete`.

## Token-Saving Work Orders

The master holds the full mission; the workers do not. Sending the whole project
concept to every agent wastes tokens, so Jarvis delegates like a manager:

- `choose_plan` gives each task only a compact, scoped objective — never the
  full mission text.
- At launch the master compacts the mission into a single short **headline**
  (~320 chars). Each worker prompt contains only that headline, the worker's own
  objective, and the list of the other agents' scopes to stay out of.
- The cost of the mission text is therefore paid roughly once as a headline,
  instead of being re-sent in full to all N workers (the old prompt embedded the
  whole mission in every worker, and `choose_plan` embedded it again per task).

When a worker fails, the work is handed **back to the same agent** - its own
branch and worktree - to fix, like a manager returning a bug to the developer
who wrote it. The repair prompt carries the same compact headline, the original
objective, and the failure log; it never re-sends the whole concept. See
[Self-Healing Agent](#self-healing-agent).

## Mission Architect Scope: Build API and UI with tests

### Rules

- Keep the work limited to mission decomposition for the API and UI effort.
- Treat the API and UI implementations as owned by other agents.
- Only define the work boundaries, dependencies, and validation expectations.
- Do not implement product logic, UI wiring, or endpoint behavior here.
- Prefer clean handoff text that another agent can use directly.

### Acceptance Criteria

- The mission is split into clear worker-ready rules.
- The scope states what is in bounds and what is out of bounds.
- The scope includes test and validation expectations for the API and UI work.
- The scope names the dependencies on other agents without duplicating their work.
- The scope is concise enough to hand off without additional interpretation.

### Safe Worker Boundaries

- In scope: mission framing, task boundaries, success criteria, and validation gates.
- In scope: interface expectations that the API and UI workers must respect.
- Out of scope: backend endpoints, frontend components, styling, state management, and test implementation details.
- Out of scope: cross-agent integration code unless it is a thin contract or stub.
- If a dependency is missing, document the contract and stop rather than filling in the other agent's work.

## Self-Healing Agent

One agent keeps watch over the whole swarm. When a worker exits with a failure,
the console signals the self-healing agent over `apcall://heal`, which
automatically dispatches a real healing worker into the **same worktree and
branch** as the failed agent. The healing worker runs with the strongest
available model, is given the failed worker's log tail, and is told to diagnose
and repair the scope. Success marks the original agent `complete` (healed);
failure retries up to `HEAL_MAX_ATTEMPTS` (2) before the task is recreated for
pickup. Auto-repair can be armed/muted from the **Repair Agent** panel, and a
manual dispatch-healer control is available inside any failed or conflicted
worker's live console.

## Voice

Voice input uses the browser Web Speech API when available. Useful phrases:

- `plan agents`
- `start workers`
- `deploy agents`
- `merge finished`

Spoken text that is not a command is appended to the mission box.

## Auto-run Service

The backend control panel has **Create Auto-run Service** and **Remove Service**
buttons. On Windows, this writes a startup command file here:

```text
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\jcode-jarvis-console.cmd
```

That starts the local Jarvis console when the user signs in. The service button
only creates or removes the startup entry; it does not install any system-wide
daemon or store API keys outside the ignored Jarvis settings file.

## Worker Provider

Open **Settings** in the console to configure OpenAI, Claude, and NVIDIA. API
keys are saved only in the ignored local runtime file:

```text
.jcode/jarvis-console/settings.json
```

Each provider has an editable model list using this format:

```text
model-id|tier|cost
```

`tier` is `economy`, `balanced`, or `premium`; lower `cost` wins when multiple
models satisfy the same worker need.

The smart router has three strategies:

- `Cost saver` uses economy models unless the role needs coordination or git.
- `Balanced` uses stronger models for orchestration/git and cheaper models for
  UI/polish workers.
- `Quality first` prefers premium models for coordination, git, and
  verification.

Plan cards also support per-agent provider/model overrides. Leave those fields
blank to let Jarvis choose automatically.

By default the console runs `jcode run` through these provider routes:

- OpenAI: `--provider openai-api --model <model>`
- Claude: `--provider claude-api --model <model>`
- NVIDIA: `--provider-profile nvidia-rotation --model <model>`

To pin extra arguments globally, set `JARVIS_JCODE_ARGS` before starting the console:

```powershell
$env:JARVIS_JCODE_ARGS = "--provider-profile nvidia-rotation --model moonshotai/kimi-k2.6"
python scripts/jarvis_console.py
```

To use a specific binary:

```powershell
$env:JARVIS_JCODE = "C:\Users\atulp\AppData\Local\jcode\bin\jcode.exe"
```

On Windows, the console also falls back to the standard installed locations
under `%LOCALAPPDATA%\jcode\` when `jcode` is not on `PATH`.

## Safety Model

The user asked for multiple agents in the same directory. This prototype keeps
them in the same repository but uses per-agent worktrees so workers do not write
over each other. The master merge still happens in the root worktree, where
conflicts are visible and recoverable.
