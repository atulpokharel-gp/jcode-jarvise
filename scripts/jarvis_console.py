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
import re
import shlex
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
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
SESSIONS_DIR = STATE_DIR / "sessions"
PROCESSES: dict[str, subprocess.Popen[Any]] = {}
STATE_LOCK = threading.Lock()
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
APCALL_CAP = 200
HEAL_MAX_ATTEMPTS = 2
# apcall is the Jarvis inter-agent protocol. Every agent lifecycle transition,
# planning broadcast, and self-heal handshake is published as an apcall message
# so the console can show agents coordinating with each other in real time.
APCALL_HEAL_BUS = "apcall://heal"
# apcall-net: the on-disk, network-capable form of the bus. Every published
# message is also written to an append-only NDJSON session log and exposed over
# the /apcall/v1 HTTP transport described in docs/APCALL_NETWORK_PROTOCOL.md.
APC_VERSION = "apcall/1.0"
APCALL_BUSES = {
    "apcall://master",
    "apcall://workers",
    "apcall://heal",
    "apcall://whiteboard",
    "apcall://observers",
    "apcall://all",
}


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ensure_session(state: dict[str, Any]) -> str:
    """Every apcall message belongs to a session; create one lazily."""
    if not state.get("session_id"):
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        state["session_id"] = f"ses_{stamp}"
    return str(state["session_id"])


def start_session(state: dict[str, Any]) -> str:
    """Open a fresh apcall session + mission for a new run (new NDJSON log)."""
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    state["session_id"] = f"ses_{stamp}"
    state["mission_id"] = f"mis_{stamp}"
    state["apcall_seq"] = 0
    return str(state["session_id"])


def to_envelope(state: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    """Project a local bus message into the apcall network envelope."""
    receiver = str(message.get("to") or "")
    if receiver.startswith("apcall://") or receiver in APCALL_BUSES:
        to_field: dict[str, Any] = {"bus": receiver}
    elif receiver in {"all", "workers", "whiteboard", "observers"}:
        # Broadcast-style short names map onto the reserved apcall buses.
        to_field = {"bus": f"apcall://{receiver}"}
    else:
        to_field = {"node_id": receiver}
    return {
        "apc_version": APC_VERSION,
        "id": message["id"],
        "session_id": state.get("session_id"),
        "mission_id": state.get("mission_id"),
        "seq": message.get("seq"),
        "from": {"node_id": str(message.get("from") or "")},
        "to": to_field,
        "type": message.get("type"),
        "ts": iso_now(),
        "payload": message.get("payload", {}),
    }


def append_session_log(session_id: str | None, envelope: dict[str, Any]) -> None:
    """Append one message to the append-only NDJSON session log (source of truth)."""
    if not session_id:
        return
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    with (session_dir / "apcall.ndjson").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(envelope) + "\n")


def read_session_messages(session_id: str, after: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Replay messages from a session log, optionally after a given message id."""
    path = SESSIONS_DIR / session_id / "apcall.ndjson"
    if not path.exists():
        return {"session_id": session_id, "messages": [], "count": 0}
    messages: list[dict[str, Any]] = []
    started = after is None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not started:
            if envelope.get("id") == after:
                started = True
            continue
        messages.append(envelope)
    return {"session_id": session_id, "messages": messages[-limit:], "count": len(messages)}


def list_sessions() -> dict[str, Any]:
    if not SESSIONS_DIR.exists():
        return {"sessions": []}
    sessions = [
        directory.name
        for directory in sorted(SESSIONS_DIR.iterdir())
        if directory.is_dir() and (directory / "apcall.ndjson").exists()
    ]
    return {"sessions": sessions}


def ingest_message(session_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Accept an apcall message from an external node over the HTTP transport."""
    message_type = str(body.get("type") or "").strip()
    if not message_type:
        raise RuntimeError("Missing message type.")
    sender = body.get("from")
    receiver = body.get("to")
    sender_id = sender.get("node_id") if isinstance(sender, dict) else (sender or "external")
    receiver_id = (
        (receiver.get("node_id") or receiver.get("bus"))
        if isinstance(receiver, dict)
        else (receiver or "master")
    )
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    with STATE_LOCK:
        state = load_state()
        ensure_session(state)
        seq = int(state.get("apcall_seq", 0)) + 1
        state["apcall_seq"] = seq
        stamp = datetime.now().strftime("%H%M%S%f")
        message = {
            "id": f"apc-ext-{stamp}-{seq}",
            "time": now(),
            "from": str(sender_id),
            "to": str(receiver_id),
            "type": message_type,
            "payload": payload,
            "seq": seq,
        }
        bus = state.setdefault("apcall", [])
        bus.append(message)
        state["apcall"] = bus[-APCALL_CAP:]
        envelope = to_envelope(state, message)
        envelope["session_id"] = session_id
        append_session_log(session_id, envelope)
        event(state, f"apcall ingest from {sender_id}: {message_type}")
        save_state(state)
    return {"accepted": True, "id": message["id"], "seq": seq}


def apcall(
    state: dict[str, Any],
    sender: str,
    receiver: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Publish one message on the apcall inter-agent bus.

    apcall (Agent Protocol Call) is how every node in the swarm talks to the
    others: the master broadcasts the mission, workers report status, and the
    self-healing agent negotiates repairs. Messages are persisted on the state
    so the browser can render the live mesh.
    """
    bus = state.setdefault("apcall", [])
    ensure_session(state)
    seq = int(state.get("apcall_seq", 0)) + 1
    state["apcall_seq"] = seq
    stamp = datetime.now().strftime("%H%M%S%f")
    message = {
        "id": f"apcall-{stamp}-{seq}",
        "time": now(),
        "from": sender,
        "to": receiver,
        "type": kind,
        "payload": payload or {},
        "seq": seq,
    }
    bus.append(message)
    state["apcall"] = bus[-APCALL_CAP:]
    # Mirror onto the append-only session log (apcall-net source of truth).
    try:
        append_session_log(state.get("session_id"), to_envelope(state, message))
    except OSError:
        pass
    if summary:
        event(state, summary)
    return message


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
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def default_state() -> dict[str, Any]:
    return {
        "plan": [],
        "plan_preview": False,
        "agents": [],
        "events": [],
        "apcall": [],
        "whiteboard": None,
        "healing": {"enabled": True, "attempts": {}},
    }


def default_settings() -> dict[str, Any]:
    return {
        "strategy": "balanced",
        "workspace": {"path": str(ROOT)},
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
    if isinstance(incoming.get("workspace"), dict):
        workspace_path = str(incoming["workspace"].get("path") or "").strip()
        if workspace_path:
            settings["workspace"] = {"path": str(Path(workspace_path).expanduser().resolve())}
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
    result = run(["git", "status", "--short"], cwd=active_workspace(), check=False)
    text = (result.stdout + result.stderr).strip()
    return text or "Clean"


def active_workspace() -> Path:
    settings = load_settings(include_secrets=True)
    raw_path = str(settings.get("workspace", {}).get("path") or str(ROOT))
    return Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()


def is_git_repo(path: Path) -> bool:
    result = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def workspace_info(path: Path | None = None) -> dict[str, Any]:
    workspace = (path or active_workspace()).resolve()
    exists = workspace.exists() and workspace.is_dir()
    git_repo = exists and is_git_repo(workspace)
    info = {
        "path": str(workspace),
        "exists": exists,
        "is_git_repo": git_repo,
        "branch": "not a git repo",
        "dirty": False,
        "git_status": "Not a git repo",
    }
    if git_repo:
        info["branch"] = current_branch(workspace)
        info["dirty"] = dirty(workspace)
        info["git_status"] = git_status_for(workspace)
    return info


def git_status_for(path: Path) -> str:
    result = run(["git", "status", "--short"], cwd=path, check=False)
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
    workspace = workspace_info()
    state["workspace"] = workspace
    state["git_status"] = workspace["git_status"]
    state["root_dirty"] = workspace["dirty"] or not workspace["is_git_repo"]
    state["current_branch"] = workspace["branch"]
    state["summary"] = state_summary(state)
    state.setdefault("apcall", [])
    state.setdefault("whiteboard", None)
    state.setdefault("healing", {"enabled": True, "attempts": {}})
    try:
        state["jcode_path"] = resolve_jcode_binary()
        state["jcode_available"] = True
    except RuntimeError as exc:
        state["jcode_path"] = str(exc)
        state["jcode_available"] = False
    state["settings"] = settings_summary()
    state["service"] = service_status()
    return state


def service_target_path() -> Path:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA is not set, so Windows startup cannot be configured.")
        return (
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / "jcode-jarvis-console.cmd"
        )
    return Path.home() / ".config" / "autostart" / "jcode-jarvis-console.desktop"


def service_command_preview() -> str:
    script = ROOT / "scripts" / "jarvis_console.py"
    return f"{sys.executable} {script} --host {DEFAULT_HOST} --port {DEFAULT_PORT}"


def service_file_contents() -> str:
    script = ROOT / "scripts" / "jarvis_console.py"
    if os.name == "nt":
        return (
            "@echo off\n"
            f'cd /d "{ROOT}"\n'
            f'start "Jcode Jarvis Console" /min "{sys.executable}" "{script}" '
            f"--host {DEFAULT_HOST} --port {DEFAULT_PORT}\n"
        )
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Jcode Jarvis Console\n"
        f"Exec={shlex.quote(sys.executable)} {shlex.quote(str(script))} "
        f"--host {DEFAULT_HOST} --port {DEFAULT_PORT}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def service_status() -> dict[str, Any]:
    try:
        path = service_target_path()
        return {
            "supported": True,
            "installed": path.exists(),
            "path": str(path),
            "command": service_command_preview(),
        }
    except RuntimeError as exc:
        return {"supported": False, "installed": False, "path": "", "command": "", "error": str(exc)}


def install_service() -> dict[str, Any]:
    path = service_target_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(service_file_contents(), encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)
    state = load_state()
    event(state, f"Auto-run service installed at {path}")
    save_state(state)
    return hydrate_state(state)


def remove_service() -> dict[str, Any]:
    path = service_target_path()
    if path.exists():
        path.unlink()
    state = load_state()
    event(state, "Auto-run service removed.")
    save_state(state)
    return hydrate_state(state)


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


def current_branch(cwd: Path | None = None) -> str:
    result = run(["git", "branch", "--show-current"], cwd=cwd or active_workspace(), check=False)
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


def list_workspace_path(raw_path: str | None) -> dict[str, Any]:
    base = Path(os.path.expandvars(os.path.expanduser(raw_path or str(active_workspace())))).resolve()
    if not base.exists() or not base.is_dir():
        raise RuntimeError(f"Directory does not exist: {base}")
    entries = []
    try:
        children = sorted(base.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except PermissionError as exc:
        raise RuntimeError(f"Permission denied: {base}") from exc
    for child in children[:300]:
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "is_dir": child.is_dir(),
                "is_git_repo": child.is_dir() and (child / ".git").exists(),
            }
        )
    parent = str(base.parent) if base.parent != base else ""
    return {"path": str(base), "parent": parent, "entries": entries}


def set_workspace(raw_path: str) -> dict[str, Any]:
    workspace = Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise RuntimeError(f"Workspace directory does not exist: {workspace}")
    settings = load_settings(include_secrets=True)
    settings["workspace"] = {"path": str(workspace)}
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    state = load_state()
    event(state, f"Workspace set to {workspace}")
    save_state(state)
    return hydrate_state(state)


def create_workspace(parent_raw: str, name: str, init_git: bool = True) -> dict[str, Any]:
    parent = Path(os.path.expandvars(os.path.expanduser(parent_raw or str(ROOT)))).resolve()
    clean_name = name.strip().replace("\\", "-").replace("/", "-")
    if not clean_name:
        raise RuntimeError("Project name is empty.")
    if not parent.exists() or not parent.is_dir():
        raise RuntimeError(f"Parent directory does not exist: {parent}")
    target = (parent / clean_name).resolve()
    if target.exists() and any(target.iterdir()):
        raise RuntimeError(f"Project already exists and is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(f"# {clean_name}\n", encoding="utf-8")
    if init_git and not is_git_repo(target):
        run(["git", "init"], cwd=target)
        run(["git", "add", "README.md"], cwd=target, check=False)
        run(["git", "commit", "-m", "Initial project"], cwd=target, check=False)
    return set_workspace(str(target))


def clean_plan(plan: Any, max_agents: int = 12) -> list[dict[str, str]]:
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
    premium_words = ["orchestration", "git", "master", "architecture", "security"]
    balanced_words = ["verification", "database", "backend", "qa", "runner", "integration"]
    if strategy == "cost_saver":
        return "balanced" if any(word in lowered for word in premium_words) else "economy"
    if strategy == "quality":
        return "premium" if any(word in lowered for word in [*premium_words, "verification"]) else "balanced"
    if any(word in lowered for word in premium_words):
        return "premium"
    if any(word in lowered for word in balanced_words):
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


def log_tail(raw_path: str | None, limit: int = 6000) -> str:
    if not raw_path:
        return ""
    path = Path(raw_path)
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-limit:]


def dispatch_healer(state: dict[str, Any], target: dict[str, Any], attempt: int) -> None:
    """Launch a real self-healing worker on the failed agent's own branch."""
    worktree = Path(target.get("worktree") or "")
    if not worktree.exists():
        target["status"] = "failed"
        apcall(
            state,
            APCALL_HEAL_BUS,
            target["id"],
            "heal.abort",
            {"reason": "worktree missing"},
            f"Self-Healing Agent could not reach {target['id']}: worktree is gone.",
        )
        return
    try:
        jcode = resolve_jcode_binary()
    except RuntimeError as exc:
        target["status"] = "failed"
        apcall(state, APCALL_HEAL_BUS, target["id"], "heal.abort", {"reason": str(exc)})
        return
    extra_args = shlex.split(os.environ.get("JARVIS_JCODE_ARGS", ""), posix=os.name != "nt")
    settings = load_settings(include_secrets=True)
    selection = select_healer_model(settings)
    model_args, model_env, provider_label, model_label = launch_args_for(selection)
    healer_id = f"healer-{target['id']}-{attempt}"
    healer_log = LOG_DIR / f"{healer_id}.log"
    whiteboard = state.get("whiteboard") or {}
    headline = mission_headline(str(whiteboard.get("mission") or target.get("task") or ""))
    prompt = healer_prompt(target, headline, log_tail(target.get("log")), attempt)
    log_file = healer_log.open("w", encoding="utf-8")
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
    PROCESSES[healer_id] = process
    healer = {
        "id": healer_id,
        "role": "Self-Healing Agent",
        "kind": "healer",
        "heals": target["id"],
        "attempt": attempt,
        "task": f"Diagnose and repair {target['id']} ({target.get('role')}) so its scope works.",
        "status": "running",
        "branch": target.get("branch"),
        "base_branch": target.get("base_branch"),
        "worktree": str(worktree),
        "log": str(healer_log),
        "provider": provider_label,
        "model": model_label,
        "pid": process.pid,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    state.setdefault("agents", []).append(healer)
    target["status"] = "healing"
    target["healed_by"] = healer_id
    apcall(
        state,
        APCALL_HEAL_BUS,
        target["id"],
        "heal.dispatch",
        {"healer": healer_id, "attempt": attempt, "model": f"{provider_label}/{model_label}"},
        f"Self-Healing Agent dispatched to repair {target['id']} (attempt {attempt}/{HEAL_MAX_ATTEMPTS}).",
    )


def recreate_task_for(state: dict[str, Any], agent_id: str) -> None:
    """Send a failed task back to the board so another agent can claim it."""
    whiteboard = state.get("whiteboard")
    if not isinstance(whiteboard, dict):
        return
    for task in whiteboard.get("tasks", []):
        if task.get("assignee") == agent_id:
            task["status"] = "todo"
            task["recreated"] = True


def maybe_dispatch_healer(state: dict[str, Any], target: dict[str, Any]) -> None:
    """The healing agent keeps watch and steps in when a worker cannot succeed."""
    if target.get("kind") == "healer":
        return
    healing = state.setdefault("healing", {"enabled": True, "attempts": {}})
    if not healing.get("enabled", True):
        apcall(state, APCALL_HEAL_BUS, target["id"], "heal.muted", {}, None)
        return
    attempts = healing.setdefault("attempts", {})
    done = int(attempts.get(target["id"], 0))
    if done >= HEAL_MAX_ATTEMPTS:
        recreate_task_for(state, target["id"])
        apcall(
            state,
            APCALL_HEAL_BUS,
            target["id"],
            "heal.giveup",
            {"attempts": done},
            f"Self-Healing Agent exhausted {done} repair attempts on {target['id']}; task recreated for pickup.",
        )
        return
    for other in state.get("agents", []):
        if other.get("kind") == "healer" and other.get("heals") == target["id"] and other.get("status") in ("starting", "running"):
            return
    attempt = done + 1
    attempts[target["id"]] = attempt
    dispatch_healer(state, target, attempt)


def handle_healer_exit(state: dict[str, Any], healer: dict[str, Any], code: int) -> None:
    target = agent_by_id(state, str(healer.get("heals") or ""))
    if code == 0:
        healer["status"] = "complete"
        if target:
            commit_if_needed(target)
            target["status"] = "complete"
            target["healed"] = True
            apcall(
                state,
                healer["id"],
                target["id"],
                "heal.result",
                {"ok": True, "branch": target.get("branch")},
                f"Self-Healing Agent repaired {target['id']}. Branch {target.get('branch')} is healthy again.",
            )
        return
    healer["status"] = "failed"
    if target:
        apcall(
            state,
            healer["id"],
            APCALL_HEAL_BUS,
            "heal.result",
            {"ok": False, "exit_code": code, "attempt": healer.get("attempt")},
            f"Repair attempt {healer.get('attempt')} for {target['id']} failed (exit {code}).",
        )
        maybe_dispatch_healer(state, target)


def poll_processes(state: dict[str, Any]) -> None:
    changed = False
    for agent in list(state.get("agents", [])):
        process = PROCESSES.get(agent["id"])
        if not process:
            continue
        code = process.poll()
        if code is None:
            if agent.get("status") != "healing":
                agent["status"] = "running"
            continue
        PROCESSES.pop(agent["id"], None)
        agent["exit_code"] = code
        agent["ended_at"] = datetime.now().isoformat(timespec="seconds")
        if agent.get("kind") == "healer":
            handle_healer_exit(state, agent, code)
        elif code == 0:
            commit_if_needed(agent)
            agent["status"] = "complete"
            apcall(
                state,
                agent["id"],
                "master",
                "status.complete",
                {"branch": agent.get("branch")},
                f"{agent['id']} completed on {agent.get('branch')}",
            )
        else:
            agent["status"] = "failed"
            apcall(
                state,
                agent["id"],
                APCALL_HEAL_BUS,
                "status.failed",
                {"exit_code": code},
                f"{agent['id']} failed with exit code {code}; signalling the self-healing agent.",
            )
            maybe_dispatch_healer(state, agent)
        changed = True
    if changed:
        sync_tasks(state)
        save_state(state)


def choose_plan(task: str, max_agents: int = 12) -> list[dict[str, str]]:
    lowered = task.lower()
    requested = re.search(r"\b(\d{1,2})\s+(?:agents|workers|engineers)\b", lowered)
    broad_markers = [
        "frontend",
        "backend",
        "api",
        "tests",
        "docs",
        "git",
        "merge",
        "ui",
        "database",
        "security",
        "customer",
        "architecture",
    ]
    score = sum(1 for marker in broad_markers if marker in lowered)
    if len(task) > 600:
        score += 2
    if requested:
        count = int(requested.group(1))
    elif any(word in lowered for word in ["army", "company", "full team", "whole team", "jarvis"]):
        count = 10
    else:
        count = max(3, score or 4)
    count = max(1, min(max_agents, count))
    roles = [
        ("Mission Architect", "Break the mission into rules, acceptance criteria, and safe worker boundaries."),
        ("UX Systems Agent", "Design the screen flow, visual hierarchy, controls, and empty/loading/error states."),
        ("Frontend Engineer", "Build the user-facing UI, dashboard states, and responsive interactions."),
        ("Backend Orchestration Agent", "Implement worker launch, lifecycle tracking, service controls, and logs."),
        ("Security Review Agent", "Threat-model secrets, command execution, file access, and unsafe workflows."),
        ("Database Schema Agent", "Plan data models, persistence, migrations, and rollback notes when storage is needed."),
        ("Customer Advocate A", "Review the feature as a first-time user and list missing workflow expectations."),
        ("Customer Advocate B", "Review the feature as a power user and list speed, control, and visibility gaps."),
        ("QA Runner Agent", "Run focused checks, reproduce failures, and report exact commands and errors."),
        ("Git Integration Agent", "Keep branch/worktree state clean, verify commits, and prepare merge notes."),
        ("Docs Navigator Agent", "Document what was built, how to navigate it, and remaining risks."),
        ("Polish Agent", "Tighten microcopy, accessibility, spacing, and operator ergonomics."),
    ]
    # The task is the worker's compact, scoped objective only. The full mission
    # is held by the master; each worker receives just a short headline plus this
    # objective at launch (see worker_prompt) so we do not pay to send the whole
    # project concept to every slave agent.
    return [
        {
            "role": roles[i][0],
            "task": roles[i][1],
        }
        for i in range(count)
    ]


def build_whiteboard(task: str, plan: list[dict[str, str]]) -> dict[str, Any]:
    """Turn the mission into a live checklist the swarm works off of.

    The whiteboard is a shared task board: one checklist item per scope. Items
    start as ``todo`` and move through ``in_progress`` -> ``done`` driven by the
    real agent assigned to them. If an item ``fail``s it is recreated so another
    agent (the self-healing agent) can pick it up and finish the work.
    """
    roles = [str(item.get("role") or f"Worker {i}") for i, item in enumerate(plan, start=1)]
    architect = next((role for role in roles if "architect" in role.lower()), "")
    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(plan, start=1):
        role = str(item.get("role") or f"Worker {index}")
        lower = role.lower()
        if architect and role == architect:
            depends_on: list[str] = []
        elif any(word in lower for word in ["git", "integration", "merge", "qa", "polish", "docs"]):
            depends_on = [r for r in roles if r != role]
        elif architect:
            depends_on = [architect]
        else:
            depends_on = []
        tasks.append(
            {
                "id": f"task-{index}",
                "index": index,
                "title": role,
                "detail": str(item.get("task") or ""),
                "status": "todo",
                "assignee": "",
                "picked_by": "",
                "branch": "",
                "depends_on": depends_on,
                "provider": str(item.get("provider") or ""),
                "model": str(item.get("model") or ""),
            }
        )
    return {
        "mission": task,
        "created": now(),
        "status": "planning",
        "tasks": tasks,
        "notes": [],
        "done_count": 0,
        "total_count": len(tasks),
        "merge_target": "combined into the base branch under master review",
    }


def sync_tasks(state: dict[str, Any]) -> None:
    """Drive the checklist from the real status of each assigned agent."""
    whiteboard = state.get("whiteboard")
    if not isinstance(whiteboard, dict):
        return
    tasks = whiteboard.get("tasks") or []
    workers = {
        agent.get("id"): agent
        for agent in state.get("agents", [])
        if agent.get("kind") != "healer"
    }
    status_map = {
        "starting": "in_progress",
        "running": "in_progress",
        "healing": "healing",
        "complete": "done",
        "failed": "failed",
        "conflict": "failed",
        "stopped": "todo",
    }
    done = 0
    active = 0
    for task in tasks:
        agent = workers.get(task.get("assignee"))
        if agent:
            mapped = status_map.get(str(agent.get("status")), task.get("status", "todo"))
            if mapped == "failed" and task.get("recreated"):
                mapped = "todo"
            elif mapped in ("in_progress", "healing", "done"):
                task["recreated"] = False
            task["status"] = mapped
            task["branch"] = agent.get("branch") or task.get("branch", "")
            if agent.get("healed_by"):
                task["picked_by"] = agent["healed_by"]
        if task.get("status") == "done":
            done += 1
        elif task.get("status") in ("in_progress", "healing"):
            active += 1
    whiteboard["done_count"] = done
    whiteboard["total_count"] = len(tasks)
    if not tasks:
        whiteboard["status"] = whiteboard.get("status", "planning")
    elif done == len(tasks):
        whiteboard["status"] = "complete"
    elif active:
        whiteboard["status"] = "executing"


def select_healer_model(settings: dict[str, Any]) -> dict[str, Any] | None:
    """The self-healing agent always reaches for the strongest available model."""
    for tier in ("premium", "balanced", "economy"):
        candidates = model_candidates(settings, tier)
        if candidates:
            best = candidates[-1] if tier == "premium" else candidates[0]
            return {"provider_id": best["provider_id"], "provider": best["provider"], "model": best["model"]}
    return None


def mission_headline(task: str, limit: int = 320) -> str:
    """Compact the full mission into the short headline a slave actually needs.

    The master keeps the whole concept; workers only receive this headline plus
    their own scoped objective, which is the token-saving core of the design.
    """
    text = " ".join(str(task or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if boundary >= limit * 0.5:
        return cut[: boundary + 1]
    return cut.rsplit(" ", 1)[0] + " ..."


def team_boundaries(agent: dict[str, Any], team_roles: list[str]) -> str:
    others = [role for role in team_roles if role != agent.get("role")]
    if not others:
        return "- (you are the only agent on this run)"
    return "\n".join(f"- {role}" for role in others)


def worker_prompt(agent: dict[str, Any], headline: str, team_roles: list[str]) -> str:
    return f"""You are {agent['role']}, a worker on a team run by the Jarvis master.

The master holds the full project context. You are given only the compact work
order you need for your task -- work to it precisely and do not try to rebuild
the whole project or another agent's scope.

Project (headline only):
{headline}

Your assignment:
{agent['task']}

Other agents own these scopes -- stay out of them and assume a clean interface
where you need their work:
{team_boundaries(agent, team_roles)}

Rules:
- Work only in your current git worktree and branch.
- Keep changes tight to your assignment; do not expand scope.
- If you are blocked on something another agent owns, note it and stub a clean
  interface rather than building it yourself.
- Commit your completed changes before finishing.
- End with a concise report: files changed, validation run, risks, and blockers.
"""


def healer_prompt(target: dict[str, Any], headline: str, log_tail: str, attempt: int) -> str:
    return f"""You are {target.get('role')}. The master is sending your own task
back to you because it failed -- fix it like a developer correcting their own
work. You are inside your original git worktree and branch.

Project (headline only):
{headline}

Your assignment (the one that failed):
{target.get('task')}

This is repair attempt {attempt} of {HEAL_MAX_ATTEMPTS}.

What went wrong (tail of your log):
---
{log_tail or '(no log captured)'}
---

Rules:
- Diagnose the root cause from the log and the working tree, then fix it.
- Stay inside this worktree and branch only; do not touch other agents' work.
- Make your assignment actually work: build, run, and verify what you can.
- Commit your repair before finishing.
- End with a concise report: root cause, the fix, and how you verified it.
"""


def start_workers(task: str, plan: list[dict[str, str]]) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        workspace = active_workspace()
        if not workspace.exists() or not workspace.is_dir():
            raise RuntimeError(f"Workspace does not exist: {workspace}")
        if not is_git_repo(workspace):
            raise RuntimeError("Selected workspace is not a git repo. Create a project or run git init.")
        if dirty(workspace):
            raise RuntimeError("Workspace is dirty. Commit or stash before launching workers.")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base_branch = current_branch(workspace)
        jcode = resolve_jcode_binary()
        extra_args = shlex.split(os.environ.get("JARVIS_JCODE_ARGS", ""), posix=os.name != "nt")
        settings = load_settings(include_secrets=True)
        plan = clean_plan(plan)
        if not plan:
            raise RuntimeError("Plan is empty.")
        # The master compacts the mission into one shared headline; each worker
        # gets the headline + its own objective instead of the full concept.
        headline = mission_headline(task)
        team_roles = [item["role"] for item in plan]
        new_agents: list[dict[str, Any]] = []
        for index, item in enumerate(plan, start=1):
            agent_id = f"agent-{stamp}-{index}"
            branch = f"jarvis/{stamp}/{index}"
            worktree = WORKTREE_ROOT / stamp / f"agent-{index}"
            run(["git", "worktree", "add", "-B", branch, str(worktree), "HEAD"], cwd=workspace)
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
            prompt = worker_prompt(agent, headline, team_roles)
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
            apcall(
                state,
                "master",
                agent_id,
                "task.dispatch",
                {"branch": branch, "model": f"{provider_label}/{model_label}"},
                f"{agent_id} launched on {branch} with {provider_label}/{model_label}",
            )
        state["plan"] = plan
        state["plan_preview"] = False
        whiteboard = state.get("whiteboard")
        if not isinstance(whiteboard, dict) or not whiteboard.get("tasks"):
            whiteboard = build_whiteboard(task, plan)
            state["whiteboard"] = whiteboard
        whiteboard["status"] = "executing"
        for task_item, agent in zip(whiteboard["tasks"], new_agents):
            task_item["assignee"] = agent["id"]
            task_item["branch"] = agent["branch"]
            task_item["status"] = "in_progress"
        state.setdefault("agents", []).extend(new_agents)
        sync_tasks(state)
        apcall(state, "master", "all", "swarm.deploy", {"count": len(new_agents)})
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


def trigger_heal(agent_id: str) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        agent = agent_by_id(state, agent_id)
        if not agent:
            raise RuntimeError(f"Unknown agent: {agent_id}")
        if agent.get("kind") == "healer":
            raise RuntimeError("Healing agents do not heal themselves.")
        if agent.get("status") in ("starting", "running"):
            raise RuntimeError("Agent is still working; stop it before requesting a heal.")
        healing = state.setdefault("healing", {"enabled": True, "attempts": {}})
        healing["enabled"] = True
        healing.setdefault("attempts", {})[agent_id] = 0
        apcall(state, "master", APCALL_HEAL_BUS, "heal.request", {"target": agent_id}, f"Master requested a manual heal for {agent_id}.")
        maybe_dispatch_healer(state, agent)
        sync_tasks(state)
        save_state(state)
        return hydrate_state(state)


def set_healing(enabled: bool) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        healing = state.setdefault("healing", {"enabled": True, "attempts": {}})
        healing["enabled"] = bool(enabled)
        apcall(
            state,
            "master",
            APCALL_HEAL_BUS,
            "heal.toggle",
            {"enabled": bool(enabled)},
            f"Self-healing auto-repair {'armed' if enabled else 'muted'} by master.",
        )
        save_state(state)
        return hydrate_state(state)


def add_whiteboard_note(text: str, author: str = "master") -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        whiteboard = state.get("whiteboard")
        if not isinstance(whiteboard, dict):
            raise RuntimeError("No whiteboard yet. Plan a mission first.")
        note = {"time": now(), "author": author[:60] or "master", "text": text[:500]}
        whiteboard.setdefault("notes", []).append(note)
        whiteboard["notes"] = whiteboard["notes"][-40:]
        apcall(state, author or "master", "whiteboard", "plan.note", {"text": text[:200]})
        save_state(state)
        return hydrate_state(state)


def merge_finished() -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        workspace = active_workspace()
        if not is_git_repo(workspace):
            raise RuntimeError("Selected workspace is not a git repo.")
        if dirty(workspace):
            raise RuntimeError("Workspace is dirty. Commit or stash before master merge.")
        merged = []
        for agent in state.get("agents", []):
            if agent.get("status") != "complete" or agent.get("merged"):
                continue
            branch = agent.get("branch")
            result = run(["git", "merge", "--no-ff", branch, "-m", f"merge {branch}"], cwd=workspace, check=False)
            if result.returncode != 0:
                agent["status"] = "conflict"
                agent["merge_output"] = (result.stdout + result.stderr).strip()[-4000:]
                conflicts = run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=workspace, check=False)
                agent["conflicts"] = conflicts.stdout.splitlines()
                event(state, f"Conflict while merging {branch}. Master intervention required.")
                save_state(state)
                raise RuntimeError(f"Conflict while merging {branch}. Resolve in root worktree.")
            agent["merged"] = True
            merged.append(branch)
            apcall(state, agent["id"], "master", "branch.merged", {"branch": branch}, f"Merged {branch}")
        if not merged:
            event(state, "No completed worker branches were ready to merge.")
        else:
            whiteboard = state.get("whiteboard")
            if isinstance(whiteboard, dict):
                whiteboard["status"] = "merged"
            apcall(state, "master", "all", "swarm.combined", {"branches": merged})
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

    def handle_apcall_get(self, parsed: Any) -> None:
        """apcall-net HTTP read transport: sessions list, current, and replay."""
        if parsed.path == "/apcall/v1/sessions":
            self.send_json(list_sessions())
            return
        if parsed.path == "/apcall/v1/session":
            with STATE_LOCK:
                state = load_state()
            self.send_json(
                {
                    "apc_version": APC_VERSION,
                    "session_id": state.get("session_id"),
                    "mission_id": state.get("mission_id"),
                }
            )
            return
        match = re.match(r"^/apcall/v1/sessions/([^/]+)/messages$", parsed.path)
        if match:
            query = parse_qs(parsed.query)
            after = query.get("after", [None])[0]
            try:
                limit = int(query.get("limit", ["200"])[0] or 200)
            except ValueError:
                limit = 200
            limit = max(1, min(1000, limit))
            self.send_json(read_session_messages(match.group(1), after=after, limit=limit))
            return
        self.send_json({"error": "Unknown apcall route"}, status=404)

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
            if parsed.path == "/api/service/status":
                self.send_json(service_status())
                return
            if parsed.path == "/api/workspace/list":
                raw_path = parse_qs(parsed.query).get("path", [""])[0]
                self.send_json(list_workspace_path(raw_path or None))
                return
            if parsed.path.startswith("/apcall/v1"):
                self.handle_apcall_get(parsed)
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
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
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
                max_agents = max(1, min(12, max_agents))
                with STATE_LOCK:
                    state = load_state()
                    start_session(state)
                    plan = choose_plan(task, max_agents=max_agents)
                    state["plan"] = plan
                    state["plan_preview"] = True
                    state["whiteboard"] = build_whiteboard(task, plan)
                    apcall(
                        state,
                        "master",
                        "all",
                        "plan.broadcast",
                        {"mission": task[:400], "tasks": len(plan)},
                        f"Master broke the mission into {len(plan)} checklist tasks.",
                    )
                    for task_item in state["whiteboard"]["tasks"]:
                        apcall(state, task_item["title"], "whiteboard", "plan.contribute", {"focus": task_item["detail"][:200]})
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
            if self.path == "/api/launch":
                task = str(body.get("task", "")).strip()
                if not task:
                    raise RuntimeError("Mission is empty.")
                max_agents = max(1, min(12, int(body.get("max_agents") or 6)))
                plan = clean_plan(body.get("plan")) or choose_plan(task, max_agents=max_agents)
                with STATE_LOCK:
                    state = load_state()
                    start_session(state)
                    state["plan"] = plan
                    state["plan_preview"] = True
                    state["whiteboard"] = build_whiteboard(task, plan)
                    apcall(
                        state,
                        "master",
                        "all",
                        "plan.broadcast",
                        {"mission": task[:400], "tasks": len(plan)},
                        f"Master broke the mission into {len(plan)} checklist tasks.",
                    )
                    for task_item in state["whiteboard"]["tasks"]:
                        apcall(state, task_item["title"], "whiteboard", "plan.contribute", {"focus": task_item["detail"][:200]})
                    save_state(state)
                self.send_json(start_workers(task, plan))
                return
            if self.path == "/api/merge":
                self.send_json(merge_finished())
                return
            if self.path == "/api/heal":
                agent_id = str(body.get("id") or "").strip()
                if not agent_id:
                    raise RuntimeError("Missing agent id.")
                self.send_json(trigger_heal(agent_id))
                return
            if self.path == "/api/healing/toggle":
                self.send_json(set_healing(bool(body.get("enabled", True))))
                return
            if self.path == "/api/whiteboard/note":
                text = str(body.get("text") or "").strip()
                if not text:
                    raise RuntimeError("Note text is empty.")
                self.send_json(add_whiteboard_note(text, str(body.get("author") or "master")))
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
            if self.path == "/api/workspace/set":
                path = str(body.get("path") or "").strip()
                if not path:
                    raise RuntimeError("Missing workspace path.")
                self.send_json(set_workspace(path))
                return
            if self.path == "/api/workspace/create":
                parent = str(body.get("parent") or "").strip()
                name = str(body.get("name") or "").strip()
                init_git = bool(body.get("init_git", True))
                self.send_json(create_workspace(parent, name, init_git))
                return
            if self.path == "/api/service/install":
                self.send_json(install_service())
                return
            if self.path == "/api/service/remove":
                self.send_json(remove_service())
                return
            ingest = re.match(r"^/apcall/v1/sessions/([^/]+)/messages$", urlparse(self.path).path)
            if ingest:
                self.send_json(ingest_message(ingest.group(1), body))
                return
            self.send_json({"error": "Unknown route"}, status=404)
        except Exception as exc:  # Keep UI errors readable.
            self.send_json({"error": str(exc)}, status=400)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[jarvis] {self.address_string()} {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Jcode Jarvis console.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
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
