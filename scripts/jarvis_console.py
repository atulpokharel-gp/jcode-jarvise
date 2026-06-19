#!/usr/bin/env python3
"""Local Jarvis-style console for orchestrating multiple Jcode workers.

The console is intentionally local-only. It serves a browser UI, creates
per-worker git worktrees and branches, starts `jcode run` processes, commits
leftover worker changes when a process exits, and offers a master merge action.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
ASSET_DIR = ROOT / "assets" / "jarvis-console"
STATE_DIR = ROOT / ".jcode" / "jarvis-console"
STATE_FILE = STATE_DIR / "state.json"
WORKTREE_ROOT = STATE_DIR / "worktrees"
LOG_DIR = STATE_DIR / "logs"
PROCESSES: dict[str, subprocess.Popen[Any]] = {}
STATE_LOCK = threading.Lock()


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def run(cmd: list[str], cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def default_state() -> dict[str, Any]:
    return {"plan": [], "agents": [], "events": []}


def load_state() -> dict[str, Any]:
    ensure_dirs()
    if not STATE_FILE.exists():
        return default_state()
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_state()


def save_state(state: dict[str, Any]) -> None:
    ensure_dirs()
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def event(state: dict[str, Any], message: str) -> None:
    state.setdefault("events", []).append({"time": now(), "message": message})
    state["events"] = state["events"][-120:]


def git_status() -> str:
    result = run(["git", "status", "--short"], check=False)
    text = (result.stdout + result.stderr).strip()
    return text or "Clean"


def current_branch() -> str:
    result = run(["git", "branch", "--show-current"], check=False)
    branch = result.stdout.strip()
    return branch or "HEAD"


def last_commit(cwd: Path) -> str:
    result = run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, check=False)
    return result.stdout.strip()


def dirty(cwd: Path) -> bool:
    return bool(run(["git", "status", "--porcelain"], cwd=cwd, check=False).stdout.strip())


def commit_if_needed(agent: dict[str, Any]) -> None:
    worktree = Path(agent["worktree"])
    if not worktree.exists() or not dirty(worktree):
        agent["commit"] = last_commit(worktree) if worktree.exists() else agent.get("commit")
        return
    run(["git", "add", "-A"], cwd=worktree, check=False)
    message = f"jarvis({agent['id']}): {agent['role']}"
    commit = run(["git", "commit", "-m", message], cwd=worktree, check=False)
    agent["commit"] = last_commit(worktree)
    agent["commit_output"] = (commit.stdout + commit.stderr).strip()[-2000:]


def poll_processes(state: dict[str, Any]) -> None:
    changed = False
    for agent in state.get("agents", []):
        process = PROCESSES.get(agent["id"])
        if not process:
            continue
        code = process.poll()
        if code is None:
            agent["status"] = "running"
            continue
        PROCESSES.pop(agent["id"], None)
        agent["exit_code"] = code
        agent["ended_at"] = datetime.now().isoformat(timespec="seconds")
        if code == 0:
            commit_if_needed(agent)
            agent["status"] = "complete"
            event(state, f"{agent['id']} completed on {agent.get('branch')}")
        else:
            agent["status"] = "failed"
            event(state, f"{agent['id']} failed with exit code {code}")
        changed = True
    if changed:
        save_state(state)


def choose_plan(task: str) -> list[dict[str, str]]:
    lowered = task.lower()
    broad_markers = ["frontend", "backend", "api", "tests", "docs", "git", "merge", "ui"]
    score = sum(1 for marker in broad_markers if marker in lowered)
    if len(task) > 600:
        score += 2
    count = max(1, min(5, score or 2))
    roles = [
        ("UI Agent", "Build the user-facing console, controls, and visual states."),
        ("Orchestration Agent", "Implement worker launch, lifecycle tracking, and logs."),
        ("Git Agent", "Keep branch/worktree state clean and prepare merge notes."),
        ("Verification Agent", "Run focused checks and report failures clearly."),
        ("Polish Agent", "Tighten docs, empty states, and operator ergonomics."),
    ]
    return [
        {
            "role": roles[i][0],
            "task": f"{roles[i][1]} Scope it against this mission: {task}",
        }
        for i in range(count)
    ]


def worker_prompt(agent: dict[str, Any], mission: str) -> str:
    return f"""You are a Jcode worker agent controlled by the Jarvis master.

Mission:
{mission}

Your scoped role:
{agent['role']}

Your scoped task:
{agent['task']}

Rules:
- Work only in your current git worktree and branch.
- Keep changes focused on your assigned scope.
- Commit your completed changes before finishing when possible.
- Do not merge other worker branches.
- End with a concise report: files changed, validation run, risks, and blockers.
"""


def start_workers(task: str, plan: list[dict[str, str]]) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        if dirty(ROOT):
            raise RuntimeError("Root worktree is dirty. Commit or stash before launching workers.")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base_branch = current_branch()
        jcode = os.environ.get("JARVIS_JCODE", shutil.which("jcode") or "jcode")
        extra_args = shlex.split(os.environ.get("JARVIS_JCODE_ARGS", ""))
        new_agents: list[dict[str, Any]] = []
        for index, item in enumerate(plan, start=1):
            agent_id = f"agent-{stamp}-{index}"
            branch = f"jarvis/{stamp}/{index}"
            worktree = WORKTREE_ROOT / stamp / f"agent-{index}"
            run(["git", "worktree", "add", "-B", branch, str(worktree), "HEAD"])
            log_path = LOG_DIR / f"{agent_id}.log"
            agent = {
                "id": agent_id,
                "role": item["role"],
                "task": item["task"],
                "status": "starting",
                "branch": branch,
                "base_branch": base_branch,
                "worktree": str(worktree),
                "log": str(log_path),
                "started_at": datetime.now().isoformat(timespec="seconds"),
            }
            prompt = worker_prompt(agent, task)
            log_file = log_path.open("w", encoding="utf-8")
            process = subprocess.Popen(
                [jcode, *extra_args, "run", prompt],
                cwd=str(worktree),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            PROCESSES[agent_id] = process
            agent["pid"] = process.pid
            agent["status"] = "running"
            new_agents.append(agent)
            event(state, f"{agent_id} launched on {branch}")
        state["plan"] = plan
        state.setdefault("agents", []).extend(new_agents)
        save_state(state)
        return state


def merge_finished() -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        if dirty(ROOT):
            raise RuntimeError("Root worktree is dirty. Commit or stash before master merge.")
        merged = []
        for agent in state.get("agents", []):
            if agent.get("status") != "complete" or agent.get("merged"):
                continue
            branch = agent.get("branch")
            result = run(["git", "merge", "--no-ff", branch, "-m", f"merge {branch}"], check=False)
            if result.returncode != 0:
                agent["status"] = "conflict"
                agent["merge_output"] = (result.stdout + result.stderr).strip()[-4000:]
                conflicts = run(["git", "diff", "--name-only", "--diff-filter=U"], check=False)
                agent["conflicts"] = conflicts.stdout.splitlines()
                event(state, f"Conflict while merging {branch}. Master intervention required.")
                save_state(state)
                raise RuntimeError(f"Conflict while merging {branch}. Resolve in root worktree.")
            agent["merged"] = True
            merged.append(branch)
            event(state, f"Merged {branch}")
        if not merged:
            event(state, "No completed worker branches were ready to merge.")
        save_state(state)
        return state


class Handler(BaseHTTPRequestHandler):
    def send_json(self, body: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/status":
            with STATE_LOCK:
                state = load_state()
                poll_processes(state)
                state["git_status"] = git_status()
                self.send_json(state)
            return
        route = "index.html" if self.path == "/" else self.path.lstrip("/")
        path = (ASSET_DIR / route).resolve()
        if not str(path).startswith(str(ASSET_DIR.resolve())) or not path.exists():
            self.send_error(404)
            return
        content_type = "text/html"
        if path.suffix == ".css":
            content_type = "text/css"
        elif path.suffix == ".js":
            content_type = "text/javascript"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self.read_json()
            if self.path == "/api/plan":
                task = str(body.get("task", "")).strip()
                if not task:
                    raise RuntimeError("Mission is empty.")
                with STATE_LOCK:
                    state = load_state()
                    plan = choose_plan(task)
                    state["plan"] = plan
                    event(state, f"Master planned {len(plan)} worker scope(s).")
                    save_state(state)
                    state["git_status"] = git_status()
                    self.send_json(state)
                return
            if self.path == "/api/start":
                task = str(body.get("task", "")).strip()
                plan = body.get("plan") or choose_plan(task)
                if not task:
                    raise RuntimeError("Mission is empty.")
                self.send_json(start_workers(task, plan))
                return
            if self.path == "/api/merge":
                self.send_json(merge_finished())
                return
            self.send_error(404)
        except Exception as exc:  # Keep UI errors readable.
            self.send_json({"error": str(exc)}, status=400)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[jarvis] {self.address_string()} {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Jcode Jarvis console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    ensure_dirs()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Jarvis console: http://{args.host}:{args.port}")
    print("Set JARVIS_JCODE_ARGS to add provider/model flags for workers.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Jarvis console.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
