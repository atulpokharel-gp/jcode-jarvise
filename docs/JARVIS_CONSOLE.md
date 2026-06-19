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

By default the console runs `jcode run` using the active Jcode config. To pin a
provider or model, set `JARVIS_JCODE_ARGS` before starting the console:

```powershell
$env:JARVIS_JCODE_ARGS = "--provider-profile nvidia-rotation --model moonshotai/kimi-k2.6"
python scripts/jarvis_console.py
```

To use a specific binary:

```powershell
$env:JARVIS_JCODE = "C:\Users\atulp\AppData\Local\jcode\bin\jcode.exe"
```

## Safety Model

The user asked for multiple agents in the same directory. This prototype keeps
them in the same repository but uses per-agent worktrees so workers do not write
over each other. The master merge still happens in the root worktree, where
conflicts are visible and recoverable.
