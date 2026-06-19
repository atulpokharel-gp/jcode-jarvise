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
from urllib.parse import parse_qs, urlparse


ROOT = Path.cwd()
ASSET_DIR = ROOT / "assets" / "jarvis-console"
STATE_DIR = ROOT / ".jcode" / "jarvis-console"
STATE_FILE = STATE_DIR / "state.json"
SETTINGS_FILE = STATE_DIR / "settings.json"
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


def default_settings() -> dict[str, Any]:
    return {
        "strategy": "balanced",
        "providers": {
            "openai": {
                "label": "OpenAI",
                "enabled": True,
                "launch": {"provider": "openai-api"},
                "api_key_env": "OPENAI_API_KEY",
                "api_key": "",
                "models": [
                    {"id": "gpt-5.4-mini", "tier": "economy", "cost": 1},
                    {"id": "gpt-5.4", "tier": "balanced", "cost": 3},
                    {"id": "gpt-5.5", "tier": "premium", "cost": 6},
                ],
            },
            "claude": {
                "label": "Claude",
                "enabled": True,
                "launch": {"provider": "claude-api"},
                "api_key_env": "ANTHROPIC_API_KEY",
                "api_key": "",
                "models": [
                    {"id": "claude-haiku-4.5", "tier": "economy", "cost": 1},
                    {"id": "claude-sonnet-4-6", "tier": "balanced", "cost": 4},
                    {"id": "claude-opus-4-8", "tier": "premium", "cost": 8},
                ],
            },
            "nvidia": {
                "label": "NVIDIA",
                "enabled": True,
                "launch": {"provider_profile": "nvidia-rotation"},
                "api_key_env": "NVIDIA_API_KEY",
                "api_key": "",
                "models": [
                    {"id": "moonshotai/kimi-k2.6", "tier": "economy", "cost": 1},
                    {"id": "minimaxai/minimax-m3", "tier": "balanced", "cost": 2},
                    {"id": "deepseek-ai/deepseek-v4-pro", "tier": "premium", "cost": 4},
                ],
            },
        },
    }


def load_state() -> dict[str, Any]:
    ensure_dirs()
    if not STATE_FILE.exists():
        return default_state()
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default_state()


def merge_defaults(default: Any, current: Any) -> Any:
    if isinstance(default, dict) and isinstance(current, dict):
        merged = dict(default)
        for key, value in current.items():
            merged[key] = merge_defaults(default.get(key), value)
        return merged
    return current if current is not None else default


def load_settings(include_secrets: bool = False) -> dict[str, Any]:
    ensure_dirs()
    settings = default_settings()
    if SETTINGS_FILE.exists():
        try:
            settings = merge_defaults(settings, json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            settings = default_settings()
    if include_secrets:
        return settings
    public = json.loads(json.dumps(settings))
    for provider in public.get("providers", {}).values():
        api_key = str(provider.get("api_key") or "")
        provider["has_api_key"] = bool(api_key) or credential_file_has_key(provider)
        provider["api_key"] = ""
    return public


def credential_file_has_key(provider: dict[str, Any]) -> bool:
    env_name = provider.get("api_key_env")
    if env_name and os.environ.get(str(env_name)):
        return True
    appdata = os.environ.get("APPDATA")
    if not appdata or not env_name:
        return False
    likely_files = {
        "OPENAI_API_KEY": ["openai.env"],
        "ANTHROPIC_API_KEY": ["anthropic.env", "claude.env"],
        "NVIDIA_API_KEY": [
            "provider-nvidia-rotation.env",
            "provider-nvidia-deepseek-v4-pro.env",
            "nvidia-nim.env",
        ],
    }.get(str(env_name), [])
    for name in likely_files:
        path = Path(appdata) / "jcode" / name
        if path.exists() and f"{env_name}=" in path.read_text(encoding="utf-8", errors="ignore"):
            return True
    return False


def save_settings(incoming: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings(include_secrets=True)
    if "strategy" in incoming:
        strategy = str(incoming["strategy"]).strip()
        if strategy in {"cost_saver", "balanced", "quality"}:
            settings["strategy"] = strategy
    incoming_providers = incoming.get("providers")
    if isinstance(incoming_providers, dict):
        for provider_id, provider_update in incoming_providers.items():
            if provider_id not in settings["providers"] or not isinstance(provider_update, dict):
                continue
            current = settings["providers"][provider_id]
            if "enabled" in provider_update:
                current["enabled"] = bool(provider_update["enabled"])
            api_key = str(provider_update.get("api_key") or "")
            if api_key:
                current["api_key"] = "" if api_key == "__CLEAR__" else api_key
            models = provider_update.get("models")
            if isinstance(models, list):
                cleaned_models = []
                for model in models:
                    if not isinstance(model, dict):
                        continue
                    model_id = str(model.get("id") or "").strip()
                    tier = str(model.get("tier") or "balanced").strip()
                    if tier not in {"economy", "balanced", "premium"}:
                        tier = "balanced"
                    if not model_id:
                        continue
                    try:
                        cost = int(model.get("cost") or 3)
                    except (TypeError, ValueError):
                        cost = 3
                    cleaned_models.append({"id": model_id[:160], "tier": tier, "cost": max(1, cost)})
                if cleaned_models:
                    current["models"] = cleaned_models[:12]
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return load_settings(include_secrets=False)


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


def state_summary(state: dict[str, Any]) -> dict[str, int]:
    summary = {
        "planned": 0,
        "starting": 0,
        "running": 0,
        "complete": 0,
        "failed": 0,
        "conflict": 0,
        "stopped": 0,
    }
    for agent in state.get("agents", []):
        status = str(agent.get("status") or "planned")
        summary[status] = summary.get(status, 0) + 1
    return summary


def hydrate_state(state: dict[str, Any]) -> dict[str, Any]:
    state["git_status"] = git_status()
    state["root_dirty"] = dirty(ROOT)
    state["current_branch"] = current_branch()
    state["summary"] = state_summary(state)
    try:
        state["jcode_path"] = resolve_jcode_binary()
        state["jcode_available"] = True
    except RuntimeError as exc:
        state["jcode_path"] = str(exc)
        state["jcode_available"] = False
    state["settings"] = settings_summary()
    return state


def settings_summary() -> dict[str, Any]:
    settings = load_settings(include_secrets=False)
    providers = settings.get("providers", {})
    return {
        "strategy": settings.get("strategy"),
        "providers": {
            provider_id: {
                "label": provider.get("label", provider_id),
                "enabled": provider.get("enabled", False),
                "has_api_key": provider.get("has_api_key", False),
                "models": len(provider.get("models", [])),
            }
            for provider_id, provider in providers.items()
        },
    }


def current_branch() -> str:
    result = run(["git", "branch", "--show-current"], check=False)
    branch = result.stdout.strip()
    return branch or "HEAD"


def resolve_jcode_binary() -> str:
    configured = os.environ.get("JARVIS_JCODE")
    if configured:
        expanded = os.path.expandvars(os.path.expanduser(configured))
        if Path(expanded).exists() or shutil.which(expanded):
            return expanded
        raise RuntimeError(f"JARVIS_JCODE points to a missing executable: {configured}")

    discovered = shutil.which("jcode")
    if discovered:
        return discovered

    candidates: list[Path] = []
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            root = Path(local_app_data) / "jcode"
            candidates.extend(
                [
                    root / "bin" / "jcode.exe",
                    root / "builds" / "current" / "jcode.exe",
                    root / "builds" / "stable" / "jcode.exe",
                ]
            )
    else:
        home = Path.home()
        candidates.extend(
            [
                home / ".local" / "bin" / "jcode",
                home / ".jcode" / "builds" / "current" / "jcode",
                home / ".jcode" / "builds" / "stable" / "jcode",
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "Could not find jcode executable. Set JARVIS_JCODE to the full path of jcode.exe."
    )


def last_commit(cwd: Path) -> str:
    result = run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, check=False)
    return result.stdout.strip()


def dirty(cwd: Path) -> bool:
    return bool(run(["git", "status", "--porcelain"], cwd=cwd, check=False).stdout.strip())


def clean_plan(plan: Any, max_agents: int = 5) -> list[dict[str, str]]:
    if not isinstance(plan, list):
        return []
    cleaned: list[dict[str, str]] = []
    for index, item in enumerate(plan[:max_agents], start=1):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or f"Worker Agent {index}").strip()
        task = str(item.get("task") or "").strip()
        if not task:
            continue
        cleaned_item = {"role": role[:120], "task": task[:4000]}
        if item.get("provider"):
            cleaned_item["provider"] = str(item.get("provider"))[:60]
        if item.get("model"):
            cleaned_item["model"] = str(item.get("model"))[:160]
        cleaned.append(cleaned_item)
    return cleaned


def provider_ready(provider: dict[str, Any]) -> bool:
    return bool(provider.get("enabled")) and (
        bool(provider.get("api_key")) or credential_file_has_key(provider)
    )


def tier_for_role(role: str, strategy: str) -> str:
    lowered = role.lower()
    if strategy == "cost_saver":
        return "balanced" if any(word in lowered for word in ["orchestration", "git"]) else "economy"
    if strategy == "quality":
        return "premium" if any(word in lowered for word in ["orchestration", "git", "verification"]) else "balanced"
    if any(word in lowered for word in ["orchestration", "git"]):
        return "premium"
    if "verification" in lowered:
        return "balanced"
    return "economy"


def model_candidates(settings: dict[str, Any], tier: str) -> list[dict[str, Any]]:
    tier_rank = {"economy": 0, "balanced": 1, "premium": 2}
    wanted = tier_rank.get(tier, 1)
    candidates = []
    for provider_id, provider in settings.get("providers", {}).items():
        if not provider_ready(provider):
            continue
        for model in provider.get("models", []):
            model_tier = str(model.get("tier") or "balanced")
            rank = tier_rank.get(model_tier, 1)
            if rank >= wanted or tier == "economy":
                candidates.append(
                    {
                        "provider_id": provider_id,
                        "provider": provider,
                        "model": model,
                        "rank": rank,
                        "cost": int(model.get("cost") or 3),
                    }
                )
    return sorted(candidates, key=lambda item: (item["cost"], item["rank"]))


def select_agent_model(agent: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
    providers = settings.get("providers", {})
    requested_provider = agent.get("provider")
    requested_model = agent.get("model")
    if requested_provider and requested_provider in providers:
        provider = providers[requested_provider]
        models = provider.get("models", [])
        selected_model = next((m for m in models if m.get("id") == requested_model), None)
        selected_model = selected_model or (models[0] if models else None)
        if selected_model and provider_ready(provider):
            return {"provider_id": requested_provider, "provider": provider, "model": selected_model}

    tier = tier_for_role(agent.get("role", ""), str(settings.get("strategy") or "balanced"))
    candidates = model_candidates(settings, tier)
    if not candidates:
        return None
    best = candidates[0]
    return {"provider_id": best["provider_id"], "provider": best["provider"], "model": best["model"]}


def launch_args_for(selection: dict[str, Any] | None) -> tuple[list[str], dict[str, str], str, str]:
    if not selection:
        return [], {}, "active-config", "active-config"
    provider = selection["provider"]
    model = selection["model"]
    launch = provider.get("launch", {})
    args: list[str] = []
    if launch.get("provider_profile"):
        args.extend(["--provider-profile", str(launch["provider_profile"])])
    elif launch.get("provider"):
        args.extend(["--provider", str(launch["provider"])])
    args.extend(["--model", str(model["id"])])
    env = {}
    api_key = str(provider.get("api_key") or "")
    api_key_env = str(provider.get("api_key_env") or "")
    if api_key and api_key_env:
        env[api_key_env] = api_key
    return args, env, str(selection["provider_id"]), str(model["id"])


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


def choose_plan(task: str, max_agents: int = 5) -> list[dict[str, str]]:
    lowered = task.lower()
    broad_markers = ["frontend", "backend", "api", "tests", "docs", "git", "merge", "ui"]
    score = sum(1 for marker in broad_markers if marker in lowered)
    if len(task) > 600:
        score += 2
    count = max(1, min(max_agents, score or 2))
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
        jcode = resolve_jcode_binary()
        extra_args = shlex.split(os.environ.get("JARVIS_JCODE_ARGS", ""), posix=os.name != "nt")
        settings = load_settings(include_secrets=True)
        plan = clean_plan(plan)
        if not plan:
            raise RuntimeError("Plan is empty.")
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
            selection = select_agent_model(item, settings)
            model_args, model_env, provider_label, model_label = launch_args_for(selection)
            agent["provider"] = provider_label
            agent["model"] = model_label
            prompt = worker_prompt(agent, task)
            log_file = log_path.open("w", encoding="utf-8")
            child_env = os.environ.copy()
            child_env.update(model_env)
            process = subprocess.Popen(
                [jcode, *extra_args, *model_args, "run", prompt],
                cwd=str(worktree),
                env=child_env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
            )
            PROCESSES[agent_id] = process
            agent["pid"] = process.pid
            agent["status"] = "running"
            new_agents.append(agent)
            event(state, f"{agent_id} launched on {branch} with {provider_label}/{model_label}")
        state["plan"] = plan
        state.setdefault("agents", []).extend(new_agents)
        save_state(state)
        return hydrate_state(state)


def agent_by_id(state: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    for agent in state.get("agents", []):
        if agent.get("id") == agent_id:
            return agent
    return None


def read_agent_log(agent_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        agent = agent_by_id(state, agent_id)
        if not agent:
            raise RuntimeError(f"Unknown agent: {agent_id}")
        raw_log_path = str(agent.get("log") or "").strip()
        if not raw_log_path:
            return {"id": agent_id, "log": ""}
        log_path = Path(raw_log_path)
        if not log_path.exists() or not log_path.is_file():
            return {"id": agent_id, "log": ""}
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return {"id": agent_id, "log": text[-24000:]}


def stop_agent(agent_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        agent = agent_by_id(state, agent_id)
        if not agent:
            raise RuntimeError(f"Unknown agent: {agent_id}")
        process = PROCESSES.pop(agent_id, None)
        if process and process.poll() is None:
            process.terminate()
        elif agent.get("pid"):
            pid = str(agent["pid"])
            if os.name == "nt":
                run(["taskkill", "/PID", pid, "/T", "/F"], check=False)
            else:
                run(["kill", "-TERM", pid], check=False)
        agent["status"] = "stopped"
        agent["ended_at"] = datetime.now().isoformat(timespec="seconds")
        event(state, f"{agent_id} stopped by master.")
        save_state(state)
        return hydrate_state(state)


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
        return hydrate_state(state)


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
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/status":
                with STATE_LOCK:
                    state = load_state()
                    poll_processes(state)
                    self.send_json(hydrate_state(state))
                return
            if parsed.path == "/api/agent/log":
                agent_id = parse_qs(parsed.query).get("id", [""])[0]
                self.send_json(read_agent_log(agent_id))
                return
            if parsed.path == "/api/settings":
                self.send_json(load_settings(include_secrets=False))
                return
            route = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
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
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)
            return

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self.read_json()
            if self.path == "/api/plan":
                task = str(body.get("task", "")).strip()
                if not task:
                    raise RuntimeError("Mission is empty.")
                max_agents = int(body.get("max_agents") or 5)
                max_agents = max(1, min(5, max_agents))
                with STATE_LOCK:
                    state = load_state()
                    plan = choose_plan(task, max_agents=max_agents)
                    state["plan"] = plan
                    event(state, f"Master planned {len(plan)} worker scope(s).")
                    save_state(state)
                    self.send_json(hydrate_state(state))
                return
            if self.path == "/api/start":
                task = str(body.get("task", "")).strip()
                plan = clean_plan(body.get("plan")) or choose_plan(task)
                if not task:
                    raise RuntimeError("Mission is empty.")
                self.send_json(start_workers(task, plan))
                return
            if self.path == "/api/merge":
                self.send_json(merge_finished())
                return
            if self.path == "/api/agent/stop":
                agent_id = str(body.get("id") or "").strip()
                if not agent_id:
                    raise RuntimeError("Missing agent id.")
                self.send_json(stop_agent(agent_id))
                return
            if self.path == "/api/settings":
                self.send_json(save_settings(body))
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
