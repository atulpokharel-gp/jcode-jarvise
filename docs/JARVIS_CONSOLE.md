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
- The console creates a small plan and decides how many worker scopes to use.
- The agent limit can scale up to 12 workers for a fuller company-style team:
  mission architect, UX, frontend, orchestration, security, database,
  customer advocates, QA, git integration, docs, and polish.
- The Agent Army map shows the master controller plus every planned or running
  worker, including stage, model route, branch, and status.
- The plan cards are editable before launch, so the master can change roles or
  scope text before workers start.
- Worker launch requires a clean active workspace so every branch has a clear base.
- Each worker gets its own branch and worktree under `.jcode/jarvis-console/`.
- Each worker runs `jcode run` with scoped instructions.
- When a worker exits, the console commits any remaining dirty changes in that
  worker worktree.
- The worker dashboard refreshes live and shows running, complete, failed, and
  conflict counts.
- Selecting a worker opens an inspector with branch, worktree, log path, stop
  control, and live log tail.
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

Clicking **Plan Agents** pops up a shared whiteboard. The master's single
"thought" (the mission) is rerouted into one lane per agent so the whole swarm
plans together before any branch is touched. Each lane shows the role, focus,
its dependencies (workers depend on the Mission Architect; integration/QA/merge
lanes depend on everyone), and the branch it will claim. Operators can post
planning notes, then **Deploy From Whiteboard** launches the workers. Lanes are
combined back into the base branch at merge time, and the board status moves
`planning -> executing -> merged`.

## Self-Healing Agent

One agent keeps watch over the whole swarm. When a worker exits with a failure,
the console signals the self-healing agent over `apcall://heal`, which
automatically dispatches a real healing worker into the **same worktree and
branch** as the failed agent. The healing worker runs with the strongest
available model, is given the failed worker's log tail, and is told to diagnose
and repair the scope. Success marks the original agent `complete` (healed);
failure retries up to `HEAL_MAX_ATTEMPTS` (2) before escalating to master.
Auto-repair can be armed/muted from the **Repair Agent** panel, and a manual
**Dispatch Healer** button is available in the agent inspector for any failed or
conflicted worker.

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
