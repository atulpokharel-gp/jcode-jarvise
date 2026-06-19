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
- The console creates a small plan and decides how many worker scopes to use.
- The plan cards are editable before launch, so the master can change roles or
  scope text before workers start.
- Worker launch requires a clean root worktree so every branch has a clear base.
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

## Voice

Voice input uses the browser Web Speech API when available. Useful phrases:

- `plan agents`
- `start workers`
- `deploy agents`
- `merge finished`

Spoken text that is not a command is appended to the mission box.

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
