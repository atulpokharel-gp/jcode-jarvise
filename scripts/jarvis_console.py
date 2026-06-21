#!/usr/bin/env python3
"""Local Jarvis-style console for orchestrating multiple Jcode workers.

The console is intentionally local-only. It serves a browser UI, creates
per-worker git worktrees and branches, starts `jcode run` processes, commits
leftover worker changes when a process exits, and offers a master merge action.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import sqlite3
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path.cwd()
ASSET_DIR = ROOT / "assets" / "jarvis-console"
STATE_DIR = ROOT / ".jcode" / "jarvis-console"
STATE_FILE = STATE_DIR / "state.json"
SETTINGS_FILE = STATE_DIR / "settings.json"
WORKTREE_ROOT = STATE_DIR / "worktrees"
LOG_DIR = STATE_DIR / "logs"
SESSIONS_DIR = STATE_DIR / "sessions"
PROCESSES: dict[str, subprocess.Popen[Any]] = {}
DISPATCH_QUEUE: list[dict[str, Any]] = []  # pending healer/QA jobs waiting for a slot
STATE_LOCK = threading.Lock()
MEMORY_LOCK = threading.Lock()
MEMORY_DB           = STATE_DIR / "memory.db"
TEMPLATES_FILE      = STATE_DIR / "templates.json"
COST_DB             = STATE_DIR / "cost.db"
MCP_CONNECTORS_FILE = STATE_DIR / "mcp_connectors.json"
SERVER_PORT = DEFAULT_PORT  # updated in main() to reflect --port flag

MCP_CATALOG: list[dict[str, Any]] = [
    {
        "id": "github", "name": "GitHub", "emoji": "🐙", "accent": "#238636",
        "description": "Repos, PRs, issues, code search, file access and CI status.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env_vars": [{"key": "GITHUB_PERSONAL_ACCESS_TOKEN", "label": "Personal Access Token", "secret": True, "placeholder": "ghp_..."}],
        "tags": ["code", "vcs"],
    },
    {
        "id": "figma", "name": "Figma", "emoji": "F", "accent": "#f24e1e",
        "description": "Read Figma files, components, styles and design tokens for UI agents.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "figma-developer-mcp", "--stdio"],
        "env_vars": [{"key": "FIGMA_API_KEY", "label": "Figma API Key", "secret": True, "placeholder": "figd_..."}],
        "tags": ["design", "ui"],
    },
    {
        "id": "slack", "name": "Slack", "emoji": "#", "accent": "#4a154b",
        "description": "Read and post Slack messages, manage channels and workspaces.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env_vars": [
            {"key": "SLACK_BOT_TOKEN", "label": "Bot Token", "secret": True, "placeholder": "xoxb-..."},
            {"key": "SLACK_TEAM_ID", "label": "Team ID", "secret": False, "placeholder": "T0XXXXXXX"},
        ],
        "tags": ["communication"],
    },
    {
        "id": "linear", "name": "Linear", "emoji": "L", "accent": "#5e6ad2",
        "description": "Create and manage Linear issues, projects and cycles.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-linear"],
        "env_vars": [{"key": "LINEAR_API_KEY", "label": "API Key", "secret": True, "placeholder": "lin_api_..."}],
        "tags": ["pm", "issues"],
    },
    {
        "id": "notion", "name": "Notion", "emoji": "N", "accent": "#e8e8e8",
        "description": "Read and write Notion pages, databases and blocks.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "env_vars": [{"key": "NOTION_API_TOKEN", "label": "Integration Token", "secret": True, "placeholder": "secret_..."}],
        "tags": ["docs", "pm"],
    },
    {
        "id": "postgres", "name": "PostgreSQL", "emoji": "Pg", "accent": "#336791",
        "description": "Query and inspect PostgreSQL databases. Read-only by default.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env_vars": [{"key": "POSTGRES_URL", "label": "Connection URL", "secret": True, "placeholder": "postgresql://user:pass@localhost/db"}],
        "tags": ["database"],
    },
    {
        "id": "brave-search", "name": "Brave Search", "emoji": "B", "accent": "#fb542b",
        "description": "Web and local search via Brave Search API.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env_vars": [{"key": "BRAVE_API_KEY", "label": "Brave API Key", "secret": True, "placeholder": "BSA..."}],
        "tags": ["search", "web"],
    },
    {
        "id": "stripe", "name": "Stripe", "emoji": "$", "accent": "#635bff",
        "description": "Access Stripe payments, customers, subscriptions and invoices.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@stripe/mcp-server"],
        "env_vars": [{"key": "STRIPE_SECRET_KEY", "label": "Secret Key", "secret": True, "placeholder": "sk_..."}],
        "tags": ["payments"],
    },
    {
        "id": "sentry", "name": "Sentry", "emoji": "!", "accent": "#fb4226",
        "description": "Access Sentry issues, events and error tracking data.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@sentry/mcp-server"],
        "env_vars": [
            {"key": "SENTRY_AUTH_TOKEN", "label": "Auth Token", "secret": True, "placeholder": "sntrys_..."},
            {"key": "SENTRY_HOST", "label": "Sentry Host", "secret": False, "placeholder": "sentry.io"},
        ],
        "tags": ["monitoring"],
    },
    {
        "id": "puppeteer", "name": "Puppeteer", "emoji": "P", "accent": "#40b5f4",
        "description": "Browser automation: navigate URLs, take screenshots, fill forms.",
        "transport": "stdio", "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "env_vars": [],
        "tags": ["browser", "testing"],
    },
]

# Model cost table: (input $/1M tokens, output $/1M tokens)
MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-haiku-4.5":              (0.80,  4.00),
    "claude-sonnet-4-6":             (3.00, 15.00),
    "claude-opus-4-8":              (15.00, 75.00),
    "gpt-5.4-mini":                  (0.15,  0.60),
    "gpt-5.4":                       (2.50, 10.00),
    "gpt-5.5":                      (10.00, 30.00),
    "moonshotai/kimi-k2.6":          (0.40,  2.00),
    "minimaxai/minimax-m3":          (0.60,  3.00),
    "deepseek-ai/deepseek-v4-pro":   (2.00,  8.00),
}
# Remote access — PIN auth + Cloudflare Tunnel
SESSION_TOKENS: dict[str, float] = {}  # token -> expiry unix timestamp
SESSION_LOCK = threading.Lock()
SESSION_TTL = 86400  # 24 h
TUNNEL_PROC: subprocess.Popen[Any] | None = None
TUNNEL_URL: str = ""
TUNNEL_LOCK = threading.Lock()
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
APCALL_CAP = 200
HEAL_MAX_ATTEMPTS = 2       # repairs on the same branch before escalating to restart
QA_MAX_ATTEMPTS = 2         # re-verifications before giving up on a branch
RESTART_MAX_ATTEMPTS = 1    # clean-branch restarts after all heals are exhausted
MAX_CONCURRENT_AGENTS = 16  # concurrent process ceiling — excess jobs queue, not drop
MISSION_AGENT_BUDGET_MULTIPLIER = 4  # total agents per mission = workers × this
# apcall is the Jarvis inter-agent protocol. Every agent lifecycle transition,
# planning broadcast, and self-heal handshake is published as an apcall message
# so the console can show agents coordinating with each other in real time.
APCALL_HEAL_BUS = "apcall://heal"
APCALL_QA_BUS = "apcall://qa"
# apcall-net: the on-disk, network-capable form of the bus. Every published
# message is also written to an append-only NDJSON session log and exposed over
# the /apcall/v1 HTTP transport described in docs/APCALL_NETWORK_PROTOCOL.md.
APC_VERSION = "apcall/1.0"
APCALL_BUSES = {
    "apcall://master",
    "apcall://workers",
    "apcall://heal",
    "apcall://qa",
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
        "qa": {"enabled": True, "attempts": {}},
    }


def default_settings() -> dict[str, Any]:
    return {
        "strategy": "balanced",
        "workspace": {"path": str(ROOT)},
        "remote": {
            "pin": "",          # 6-digit PIN; auto-generated on first use
            "tunnel": "auto",   # "auto" = try cloudflared; "off" = disable
        },
        "notifications": {
            "webhook_url": "",  # POST on mission complete / agent fail / heal exhausted
        },
        "agents": {
            "skip_permissions": True,   # append --dangerously-skip-permissions to every spawn
        },
        "devspace": {
            "enabled": False,
            "token": "",
            "allowed_roots": [str(ROOT)],
            "allow_shell": True,
        },
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
    devspace = public.get("devspace")
    if isinstance(devspace, dict):
        devspace["has_token"] = bool(devspace.get("token"))
        devspace["token"] = ""
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
    if isinstance(incoming.get("agents"), dict):
        ag = incoming["agents"]
        if "skip_permissions" in ag:
            settings.setdefault("agents", {})["skip_permissions"] = bool(ag["skip_permissions"])
    if isinstance(incoming.get("notifications"), dict):
        url = str(incoming["notifications"].get("webhook_url") or "").strip()
        settings.setdefault("notifications", {})["webhook_url"] = url
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
    state.setdefault("qa", {"enabled": True, "attempts": {}})
    state["dispatch_queue_depth"] = len(DISPATCH_QUEUE)
    state["pending_workers"] = len(PENDING_WORKERS)
    if state.get("budget"):
        b = state["budget"]
        b["remaining"] = max(0, int(b.get("total", 0)) - int(b.get("spent", 0)))
    try:
        state["cost"] = cost_summary(state.get("mission_id", ""))
    except Exception:
        state["cost"] = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    state["last_pr_url"] = state.get("last_pr_url", "")
    try:
        state["jcode_path"] = resolve_jcode_binary()
        state["jcode_available"] = True
    except RuntimeError as exc:
        state["jcode_path"] = str(exc)
        state["jcode_available"] = False
    state["settings"] = settings_summary()
    state["service"] = service_status()
    # Inject last_line from log tail for active agents (2 KB seek, ANSI-stripped)
    _ansi_re = re.compile(r"\x1b\[[0-9;]*[mGKHJA-Z]")
    for agent in state.get("agents", []):
        if agent.get("status") not in ("running", "starting", "healing", "testing"):
            continue
        log_path_str = str(agent.get("log") or "")
        if not log_path_str:
            continue
        try:
            lp = Path(log_path_str)
            if not lp.exists():
                continue
            with lp.open("rb") as fh:
                fh.seek(0, 2)
                size = fh.tell()
                fh.seek(max(0, size - 2048))
                tail = fh.read().decode("utf-8", errors="replace")
            lines = [l.strip() for l in tail.splitlines() if l.strip()]
            last = lines[-1] if lines else ""
            agent["last_line"] = _ansi_re.sub("", last)[:120]
        except Exception:
            pass
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


# ============================================================================
# Remote access — PIN auth, session tokens, Cloudflare Tunnel
# ============================================================================

def ensure_pin() -> str:
    """Return the 6-digit remote PIN; auto-generate and persist if not set."""
    raw: dict[str, Any] = {}
    if SETTINGS_FILE.exists():
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    pin = str(raw.get("remote", {}).get("pin") or "")
    if not pin or not pin.isdigit() or len(pin) != 6:
        pin = "".join(str(secrets.randbelow(10)) for _ in range(6))
        raw.setdefault("remote", {})["pin"] = pin
        SETTINGS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return pin


def reset_pin() -> str:
    """Generate a new 6-digit PIN, persist it, and invalidate all sessions."""
    pin = "".join(str(secrets.randbelow(10)) for _ in range(6))
    raw: dict[str, Any] = {}
    if SETTINGS_FILE.exists():
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    raw.setdefault("remote", {})["pin"] = pin
    SETTINGS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    with SESSION_LOCK:
        SESSION_TOKENS.clear()
    print(f"[jarvis] Remote PIN reset: {pin}")
    return pin


def verify_pin(submitted: str) -> bool:
    return hmac.compare_digest(submitted.strip(), ensure_pin())


def create_session() -> str:
    token = secrets.token_hex(32)
    with SESSION_LOCK:
        SESSION_TOKENS[token] = time.time() + SESSION_TTL
    return token


def check_session(token: str) -> bool:
    with SESSION_LOCK:
        exp = SESSION_TOKENS.get(token)
        if not exp:
            return False
        if time.time() > exp:
            SESSION_TOKENS.pop(token, None)
            return False
        return True


def start_tunnel(port: int) -> None:
    """Spawn cloudflared in the background; parse the public URL from its output."""
    global TUNNEL_PROC, TUNNEL_URL
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except FileNotFoundError:
        print("[jarvis] cloudflared not found — remote URL unavailable.")
        print("[jarvis]   Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        print(f"[jarvis] Or run: npx cloudflared tunnel --url http://127.0.0.1:{port}")
        return
    TUNNEL_PROC = proc

    def _watch() -> None:
        global TUNNEL_URL
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                m = re.search(r"https://[a-z0-9\-]+\.trycloudflare\.com", line)
                if m:
                    url = m.group(0)
                    with TUNNEL_LOCK:
                        TUNNEL_URL = url
                    pin = ensure_pin()
                    print(f"[jarvis] +--------------------------------------+")
                    print(f"[jarvis] |  Remote access ready                 |")
                    print(f"[jarvis] |  URL: {url:<32}|")
                    print(f"[jarvis] |  PIN: {pin}                            |")
                    print(f"[jarvis] +--------------------------------------+")
                    break
        except Exception:
            pass

    threading.Thread(target=_watch, daemon=True).start()


def tunnel_status() -> dict[str, Any]:
    with TUNNEL_LOCK:
        url = TUNNEL_URL
    pin = ensure_pin()
    running = TUNNEL_PROC is not None and TUNNEL_PROC.poll() is None
    qr = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={quote(url)}" if url else ""
    return {"url": url, "pin": pin, "running": running, "qr_url": qr}


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
    settings = load_settings(include_secrets=True)
    extra_args = build_jcode_extra_args(settings)
    selection = select_healer_model(settings)
    model_args, model_env, provider_label, model_label = launch_args_for(selection)
    if not budget_ok(state):
        apcall(
            state, APCALL_HEAL_BUS, target["id"], "heal.budget_exhausted",
            {"budget": state.get("budget")},
            f"Healer for {target['id']} blocked — mission agent budget exhausted.",
        )
        return
    if live_process_count() >= MAX_CONCURRENT_AGENTS:
        DISPATCH_QUEUE.append({"kind": "healer", "target_id": target["id"], "attempt": attempt})
        apcall(
            state, APCALL_HEAL_BUS, target["id"], "heal.queued",
            {"queue_depth": len(DISPATCH_QUEUE)},
            f"Healer for {target['id']} queued (slot will open when an agent finishes).",
        )
        return
    spend_budget(state)
    healer_id = f"healer-{target['id']}-{attempt}"
    healer_log = LOG_DIR / f"{healer_id}.log"
    whiteboard = state.get("whiteboard") or {}
    headline = mission_headline(str(whiteboard.get("mission") or target.get("task") or ""))
    prompt = healer_prompt(target, headline, log_tail(target.get("log")), attempt)
    log_file = healer_log.open("w", encoding="utf-8")
    child_env = os.environ.copy()
    child_env.update(model_env)
    child_env["JARVIS_MEMORY_URL"] = f"http://127.0.0.1:{SERVER_PORT}/api/memory"
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


def dispatch_restart(state: dict[str, Any], target: dict[str, Any]) -> bool:
    """
    Escalation path: all heal attempts on the original branch are exhausted.
    Decision: RESTART — spin up a new agent on a clean branch with the same task.
    If restarts are also exhausted: ABANDON — mark the task and notify humans.

    Escalation ladder:
      worker fails -> heal (same branch, up to HEAL_MAX_ATTEMPTS)
                   -> restart (new branch, up to RESTART_MAX_ATTEMPTS)
                   -> abandon (human review required)
    """
    restarts = state.setdefault("restarts", {})
    done = int(restarts.get(target["id"], 0))
    if done >= RESTART_MAX_ATTEMPTS or not budget_ok(state):
        target["status"] = "abandoned"
        reason = "budget exhausted" if not budget_ok(state) else f"{done} restart(s) also failed"
        apcall(
            state, "master", target["id"], "task.abandon",
            {"reason": reason, "branch": target.get("branch")},
            f"Task {target['id']} abandoned after all heal + restart attempts ({reason}). Human review needed.",
        )
        recreate_task_for(state, target["id"])
        return False
    workspace = active_workspace()
    try:
        jcode = resolve_jcode_binary()
    except RuntimeError:
        return False
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    restart_index = done + 1
    new_id = f"restart-{target['id']}-{restart_index}"
    new_branch = f"jarvis/restart/{target['id']}/{restart_index}"
    new_worktree = WORKTREE_ROOT / "restarts" / new_id
    try:
        run(["git", "worktree", "add", "-B", new_branch, str(new_worktree), "HEAD"], cwd=workspace)
    except Exception:
        return False
    restarts[target["id"]] = restart_index
    spend_budget(state)
    settings = load_settings(include_secrets=True)
    extra_args = build_jcode_extra_args(settings)
    selection = select_healer_model(settings)
    model_args, model_env, provider_label, model_label = launch_args_for(selection)
    whiteboard = state.get("whiteboard") or {}
    headline = mission_headline(str(whiteboard.get("mission") or target.get("task") or ""))
    prompt = worker_prompt(
        {**target, "id": new_id, "role": target.get("role", "Worker"), "task": target.get("task", "")},
        headline,
        [],
    )
    log_path = LOG_DIR / f"{new_id}.log"
    log_file = log_path.open("w", encoding="utf-8")
    child_env = os.environ.copy()
    child_env.update(model_env)
    child_env["JARVIS_MEMORY_URL"] = f"http://127.0.0.1:{SERVER_PORT}/api/memory"
    process = subprocess.Popen(
        [jcode, *extra_args, *model_args, "run", prompt],
        cwd=str(new_worktree),
        env=child_env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    PROCESSES[new_id] = process
    restart_agent = {
        "id": new_id,
        "role": target.get("role", "Worker"),
        "kind": "restart",
        "restarts": target["id"],
        "task": target.get("task", ""),
        "status": "running",
        "branch": new_branch,
        "base_branch": target.get("base_branch"),
        "worktree": str(new_worktree),
        "log": str(log_path),
        "provider": provider_label,
        "model": model_label,
        "pid": process.pid,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    state.setdefault("agents", []).append(restart_agent)
    apcall(
        state, "master", new_id, "task.restart",
        {"original": target["id"], "new_branch": new_branch, "attempt": restart_index},
        f"Master restarted {target['id']} on a clean branch ({new_branch}) after heals exhausted.",
    )
    return True


def maybe_dispatch_healer(state: dict[str, Any], target: dict[str, Any]) -> None:
    """
    Escalation entry point. Routes failures through the repair ladder:
      1. Heal on the same branch (up to HEAL_MAX_ATTEMPTS)
      2. Restart on a clean branch (dispatch_restart, up to RESTART_MAX_ATTEMPTS)
      3. Abandon — human review required
    """
    if target.get("kind") in ("healer", "restart"):
        return
    healing = state.setdefault("healing", {"enabled": True, "attempts": {}})
    if not healing.get("enabled", True):
        apcall(state, APCALL_HEAL_BUS, target["id"], "heal.muted", {}, None)
        return
    attempts = healing.setdefault("attempts", {})
    done = int(attempts.get(target["id"], 0))
    if done >= HEAL_MAX_ATTEMPTS:
        apcall(
            state, APCALL_HEAL_BUS, target["id"], "heal.giveup",
            {"attempts": done},
            f"All {done} heal attempts on {target['id']} exhausted — escalating to restart.",
        )
        dispatch_restart(state, target)
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
            target["healed"] = True
            apcall(
                state,
                healer["id"],
                target["id"],
                "heal.result",
                {"ok": True, "branch": target.get("branch")},
                f"Self-Healing Agent repaired {target['id']}. Branch {target.get('branch')} is healthy again.",
            )
            # Re-verify the repaired work with QA before calling it done.
            if not (target.get("needs_qa") and maybe_dispatch_qa(state, target)):
                target["status"] = "complete"
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


def qa_prompt(target: dict[str, Any], headline: str, attempt: int) -> str:
    return f"""You are the QA agent for the Jarvis team. The master allocated you to
verify the work of {target.get('role')} after it finished. You are inside that
worker's git worktree and branch. The master holds the full project; you only
need this:

Project (headline only):
{headline}

Work to verify (the worker's assignment):
{target.get('task')}

This is QA attempt {attempt} of {QA_MAX_ATTEMPTS}.

Verify that the work actually functions -- do not re-implement it:
- Build/compile and run the project's tests where they exist.
- If this is a web UI or browser-facing feature, use the built-in `browser` tool
  to open the app and exercise the key flows (open, snapshot, click, type,
  screenshot) to confirm it renders and behaves correctly. Run `browser setup`
  first if the browser is not ready.
- Keep changes to verification only; do not rewrite the implementation.

Finish your report with EXACTLY ONE machine-readable verdict line:
- `QA_VERDICT: PASS` -- the work builds, runs, and the key behavior works.
- `QA_VERDICT: FAIL - <one short reason>` -- it does not.
"""


def read_qa_verdict(qa_agent: dict[str, Any], code: int) -> dict[str, Any]:
    """Decide pass/fail from the QA agent's machine-readable verdict line."""
    text = log_tail(qa_agent.get("log"), 4000)
    match = re.search(r"QA_VERDICT:\s*(PASS|FAIL)([^\n]*)", text, re.IGNORECASE)
    if match:
        passed = match.group(1).upper() == "PASS"
        reason = match.group(2).strip(" -\t").strip() or ("verified" if passed else "verification failed")
        return {"pass": passed, "reason": reason[:200]}
    return {"pass": code == 0, "reason": f"no verdict line; exit code {code}"}


def dispatch_qa(state: dict[str, Any], target: dict[str, Any], attempt: int) -> bool:
    """Launch a real QA agent in the worker's worktree to verify (and browser-test)."""
    worktree = Path(target.get("worktree") or "")
    if not worktree.exists():
        return False
    try:
        jcode = resolve_jcode_binary()
    except RuntimeError:
        return False
    settings = load_settings(include_secrets=True)
    extra_args = build_jcode_extra_args(settings)
    selection = select_healer_model(settings)
    model_args, model_env, provider_label, model_label = launch_args_for(selection)
    if not budget_ok(state):
        apcall(
            state, APCALL_QA_BUS, target["id"], "qa.budget_exhausted",
            {"budget": state.get("budget")},
            f"QA for {target['id']} blocked — mission agent budget exhausted.",
        )
        return False
    if live_process_count() >= MAX_CONCURRENT_AGENTS:
        DISPATCH_QUEUE.append({"kind": "qa", "target_id": target["id"], "attempt": attempt})
        apcall(
            state, APCALL_QA_BUS, target["id"], "qa.queued",
            {"queue_depth": len(DISPATCH_QUEUE)},
            f"QA for {target['id']} queued (slot will open when an agent finishes).",
        )
        return False
    spend_budget(state)
    qa_id = f"qa-{target['id']}-{attempt}"
    qa_log = LOG_DIR / f"{qa_id}.log"
    whiteboard = state.get("whiteboard") or {}
    headline = mission_headline(str(whiteboard.get("mission") or target.get("task") or ""))
    prompt = qa_prompt(target, headline, attempt)
    log_file = qa_log.open("w", encoding="utf-8")
    child_env = os.environ.copy()
    child_env.update(model_env)
    child_env["JARVIS_MEMORY_URL"] = f"http://127.0.0.1:{SERVER_PORT}/api/memory"
    process = subprocess.Popen(
        [jcode, *extra_args, *model_args, "run", prompt],
        cwd=str(worktree),
        env=child_env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    PROCESSES[qa_id] = process
    qa_agent = {
        "id": qa_id,
        "role": f"QA · {target.get('role')}",
        "kind": "qa",
        "qa_for": target["id"],
        "attempt": attempt,
        "task": f"Verify {target['id']} ({target.get('role')}) works; build, test, and browser-check the UI.",
        "status": "running",
        "branch": target.get("branch"),
        "base_branch": target.get("base_branch"),
        "worktree": str(worktree),
        "log": str(qa_log),
        "provider": provider_label,
        "model": model_label,
        "pid": process.pid,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    state.setdefault("agents", []).append(qa_agent)
    target["status"] = "testing"
    target["qa_by"] = qa_id
    target["needs_qa"] = False
    apcall(
        state,
        "master",
        target["id"],
        "qa.dispatch",
        {"qa": qa_id, "attempt": attempt, "model": f"{provider_label}/{model_label}"},
        f"Master allocated a QA agent to verify {target['id']} (attempt {attempt}/{QA_MAX_ATTEMPTS}).",
    )
    return True


def maybe_dispatch_qa(state: dict[str, Any], target: dict[str, Any]) -> bool:
    """After a worker finishes, the master allocates a QA agent to check it."""
    if target.get("kind") in ("qa", "healer"):
        return False
    qa = state.setdefault("qa", {"enabled": True, "attempts": {}})
    if not qa.get("enabled", True):
        return False
    attempts = qa.setdefault("attempts", {})
    done = int(attempts.get(target["id"], 0))
    if done >= QA_MAX_ATTEMPTS:
        apcall(
            state,
            "master",
            target["id"],
            "qa.giveup",
            {"attempts": done},
            f"QA could not verify {target['id']} after {done} attempts; left for master review.",
        )
        return False
    for other in state.get("agents", []):
        if other.get("kind") == "qa" and other.get("qa_for") == target["id"] and other.get("status") in ("starting", "running"):
            return False
    attempt = done + 1
    attempts[target["id"]] = attempt
    return dispatch_qa(state, target, attempt)


def handle_qa_exit(state: dict[str, Any], qa_agent: dict[str, Any], code: int) -> None:
    qa_agent["status"] = "complete"
    target = agent_by_id(state, str(qa_agent.get("qa_for") or ""))
    verdict = read_qa_verdict(qa_agent, code)
    qa_agent["verdict"] = verdict
    if not target:
        return
    if verdict["pass"]:
        target["status"] = "complete"
        target["qa_passed"] = True
        apcall(
            state,
            qa_agent["id"],
            target["id"],
            "qa.pass",
            {"reason": verdict["reason"]},
            f"QA passed for {target['id']}: {verdict['reason']}.",
        )
        return
    target["qa_passed"] = False
    target["needs_qa"] = True
    apcall(
        state,
        qa_agent["id"],
        "master",
        "qa.fail",
        {"reason": verdict["reason"]},
        f"QA failed for {target['id']}: {verdict['reason']}. Master is reassigning the agent to fix it.",
    )
    maybe_dispatch_healer(state, target)
    if target.get("status") != "healing":
        # Could not reassign (auto-repair off or exhausted); leave it flagged.
        target["status"] = "complete"
        target["needs_qa"] = False


def live_process_count() -> int:
    return sum(1 for p in PROCESSES.values() if p.poll() is None)


def budget_ok(state: dict[str, Any]) -> bool:
    """False when the mission has already spawned its maximum allowed total agents."""
    b = state.get("budget")
    return not b or int(b.get("spent", 0)) < int(b.get("total", 9999))


def spend_budget(state: dict[str, Any]) -> None:
    b = state.setdefault("budget", {"total": 9999, "spent": 0})
    b["spent"] = int(b.get("spent", 0)) + 1


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
        # Parse and record token usage from log
        log_path = agent.get("log", "")
        if log_path:
            in_tok, out_tok = parse_tokens_from_log(log_path)
            if in_tok or out_tok:
                agent["input_tokens"]  = in_tok
                agent["output_tokens"] = out_tok
                model = agent.get("model", "")
                in_r, out_r = MODEL_COSTS.get(model, (3.0, 15.0))
                agent["cost_usd"] = round((in_tok / 1_000_000) * in_r + (out_tok / 1_000_000) * out_r, 4)
                threading.Thread(
                    target=cost_record,
                    args=(agent["id"], state.get("mission_id", ""), model, in_tok, out_tok),
                    daemon=True,
                ).start()
        if agent.get("kind") == "healer":
            handle_healer_exit(state, agent, code)
        elif agent.get("kind") == "qa":
            handle_qa_exit(state, agent, code)
        elif code == 0:
            commit_if_needed(agent)
            apcall(
                state,
                agent["id"],
                "master",
                "status.complete",
                {"branch": agent.get("branch")},
                f"{agent['id']} completed on {agent.get('branch')}",
            )
            if not maybe_dispatch_qa(state, agent):
                agent["status"] = "complete"
            # Check if this completion unblocks any pending dependent workers
            try_launch_pending(state)
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
    # Drain the queue: slots freed by exiting agents may unblock pending healer/QA jobs.
    while DISPATCH_QUEUE and live_process_count() < MAX_CONCURRENT_AGENTS:
        job = DISPATCH_QUEUE.pop(0)
        t = agent_by_id(state, job["target_id"])
        if not t:
            continue
        if job["kind"] == "healer":
            dispatch_healer(state, t, job["attempt"])
        elif job["kind"] == "qa":
            dispatch_qa(state, t, job["attempt"])
        changed = True
    if changed:
        sync_tasks(state)
        save_state(state)


def killswitch() -> dict[str, Any]:
    """
    Emergency stop: terminate every running agent, clear the dispatch queue,
    and mark all in-flight agents as killed. One button — everything stops.
    """
    with STATE_LOCK:
        state = load_state()
        killed = 0
        for agent_id, process in list(PROCESSES.items()):
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
                killed += 1
        PROCESSES.clear()
        queued = len(DISPATCH_QUEUE)
        DISPATCH_QUEUE.clear()
        for agent in state.get("agents", []):
            if agent.get("status") in ("running", "starting", "healing", "testing"):
                agent["status"] = "killed"
        apcall(
            state, "master", "all", "swarm.killswitch",
            {"killed": killed, "queue_cleared": queued},
            f"Kill-switch activated: {killed} agent(s) terminated, {queued} queued job(s) cleared.",
        )
        save_state(state)
        return hydrate_state(state)


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
        "testing": "testing",
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
        elif task.get("status") in ("in_progress", "healing", "testing"):
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


# ── Central agent memory (SQLite) ──────────────────────────────────────────

def memory_init() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(MEMORY_DB) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                key       TEXT    NOT NULL,
                summary   TEXT    NOT NULL DEFAULT '',
                agent_id  TEXT    NOT NULL DEFAULT '',
                mission_id TEXT   NOT NULL DEFAULT '',
                tags      TEXT    NOT NULL DEFAULT '',
                payload   TEXT    NOT NULL DEFAULT '',
                ts        REAL    NOT NULL
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mem_key ON memories(key)")
        conn.commit()


def memory_write(
    key: str,
    summary: str,
    agent_id: str = "",
    mission_id: str = "",
    tags: str = "",
    payload: str = "",
) -> dict[str, Any]:
    key = key.strip()[:200]
    if not key:
        raise ValueError("memory key is required")
    ts = time.time()
    with MEMORY_LOCK, sqlite3.connect(MEMORY_DB) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            INSERT INTO memories (key, summary, agent_id, mission_id, tags, payload, ts)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET
                summary=excluded.summary,
                agent_id=excluded.agent_id,
                mission_id=excluded.mission_id,
                tags=excluded.tags,
                payload=excluded.payload,
                ts=excluded.ts
            """,
            (key, summary[:2000], agent_id[:80], mission_id[:80], tags[:200], payload[:4000], ts),
        )
        conn.commit()
    return {"ok": True, "key": key, "ts": ts}


def memory_read(
    q: str = "",
    mission_id: str = "",
    tag: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    with MEMORY_LOCK, sqlite3.connect(MEMORY_DB) as conn:
        conn.row_factory = sqlite3.Row
        clauses: list[str] = []
        params: list[Any] = []
        if q:
            clauses.append("(key LIKE ? OR summary LIKE ? OR tags LIKE ?)")
            like = f"%{q}%"
            params += [like, like, like]
        if mission_id:
            clauses.append("mission_id = ?")
            params.append(mission_id)
        if tag:
            clauses.append("tags LIKE ?")
            params.append(f"%{tag}%")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM memories {where} ORDER BY ts DESC LIMIT ?",
            [*params, min(limit, 500)],
        ).fetchall()
    return [dict(r) for r in rows]


def memory_delete(key: str) -> dict[str, Any]:
    with MEMORY_LOCK, sqlite3.connect(MEMORY_DB) as conn:
        conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        conn.commit()
    return {"ok": True, "key": key}


def memory_clear() -> dict[str, Any]:
    with MEMORY_LOCK, sqlite3.connect(MEMORY_DB) as conn:
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.execute("DELETE FROM memories")
        conn.commit()
    return {"ok": True, "deleted": count}


# ── Mission templates ──────────────────────────────────────────────────────

def templates_load() -> list[dict[str, Any]]:
    if not TEMPLATES_FILE.exists():
        return []
    try:
        return json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def templates_save(tpls: list[dict[str, Any]]) -> None:
    TEMPLATES_FILE.write_text(json.dumps(tpls, indent=2), encoding="utf-8")


def template_add(name: str, prompt: str, tags: str = "") -> dict[str, Any]:
    tpls = templates_load()
    tid = f"tpl-{int(time.time())}"
    tpls.insert(0, {"id": tid, "name": name[:120], "prompt": prompt[:4000], "tags": tags[:200], "ts": time.time()})
    templates_save(tpls)
    return {"ok": True, "id": tid}


def template_delete(tid: str) -> dict[str, Any]:
    tpls = [t for t in templates_load() if t.get("id") != tid]
    templates_save(tpls)
    return {"ok": True}


# ── Cost / token tracker ────────────────────────────────────────────────────

def cost_init() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(COST_DB) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT    NOT NULL,
                mission_id  TEXT    NOT NULL DEFAULT '',
                model       TEXT    NOT NULL DEFAULT '',
                input_tok   INTEGER NOT NULL DEFAULT 0,
                output_tok  INTEGER NOT NULL DEFAULT 0,
                cost_usd    REAL    NOT NULL DEFAULT 0.0,
                ts          REAL    NOT NULL
            )
        """)
        conn.commit()


def cost_record(agent_id: str, mission_id: str, model: str, input_tok: int, output_tok: int) -> None:
    in_rate, out_rate = MODEL_COSTS.get(model, (3.0, 15.0))
    cost = (input_tok / 1_000_000) * in_rate + (output_tok / 1_000_000) * out_rate
    with sqlite3.connect(COST_DB) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "INSERT INTO usage (agent_id,mission_id,model,input_tok,output_tok,cost_usd,ts) VALUES (?,?,?,?,?,?,?)",
            (agent_id, mission_id, model, input_tok, output_tok, cost, time.time()),
        )
        conn.commit()


def cost_summary(mission_id: str = "") -> dict[str, Any]:
    with sqlite3.connect(COST_DB) as conn:
        if mission_id:
            row = conn.execute(
                "SELECT SUM(input_tok),SUM(output_tok),SUM(cost_usd) FROM usage WHERE mission_id=?",
                (mission_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT SUM(input_tok),SUM(output_tok),SUM(cost_usd) FROM usage"
            ).fetchone()
    return {
        "input_tokens":  int(row[0] or 0),
        "output_tokens": int(row[1] or 0),
        "cost_usd":      round(float(row[2] or 0.0), 4),
    }


TOKEN_RE = re.compile(
    r"(?:input[_ ]tokens?[:\s]+(\d+).*?output[_ ]tokens?[:\s]+(\d+)"
    r"|tokens?[:\s]+(\d+)\s*/\s*(\d+))",
    re.IGNORECASE,
)


def parse_tokens_from_log(log_path: str) -> tuple[int, int]:
    """Scan the last 200 lines of a log for token-usage patterns."""
    try:
        lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines[-200:]):
            m = TOKEN_RE.search(line)
            if m:
                if m.group(1):
                    return int(m.group(1)), int(m.group(2))
                return int(m.group(3)), int(m.group(4))
    except OSError:
        pass
    return 0, 0


# ── Webhook notifications ────────────────────────────────────────────────────

def fire_webhook(event_type: str, payload: dict[str, Any]) -> None:
    settings = load_settings(include_secrets=False)
    url = str(settings.get("notifications", {}).get("webhook_url") or "").strip()
    if not url:
        return
    body = json.dumps({"event": event_type, **payload, "ts": time.time()}).encode()
    try:
        import urllib.request
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


# ── Diff preview ────────────────────────────────────────────────────────────

def diff_preview() -> list[dict[str, Any]]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        workspace = active_workspace()
        base = current_branch(workspace)
        results = []
        for agent in state.get("agents", []):
            if agent.get("status") not in ("complete",) or agent.get("merged"):
                continue
            branch = agent.get("branch", "")
            diff = run(
                ["git", "diff", f"{base}...{branch}", "--stat", "--no-color"],
                cwd=workspace, check=False,
            )
            diff_full = run(
                ["git", "diff", f"{base}...{branch}", "--no-color"],
                cwd=workspace, check=False,
            )
            results.append({
                "agent_id":  agent["id"],
                "role":      agent.get("role", ""),
                "branch":    branch,
                "stat":      diff.stdout.strip()[-3000:],
                "diff":      diff_full.stdout.strip()[-8000:],
            })
        return results


# ── GitHub PR creation ───────────────────────────────────────────────────────

def create_github_pr(title: str, body: str) -> dict[str, Any]:
    workspace = active_workspace()
    result = run(
        ["gh", "pr", "create", "--title", title[:200], "--body", body[:4000], "--fill-first"],
        cwd=workspace, check=False,
    )
    if result.returncode != 0:
        # gh might not be installed or not authenticated
        return {"ok": False, "error": (result.stderr or result.stdout).strip()[-800:]}
    url = result.stdout.strip().splitlines()[-1]
    return {"ok": True, "url": url}


def auto_pr_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Generate a PR title + body from the mission and agent results, then open the PR."""
    whiteboard = state.get("whiteboard") or {}
    mission = str(whiteboard.get("mission") or "Jarvis mission")
    headline = mission_headline(mission)
    agents = [a for a in state.get("agents", []) if a.get("status") == "complete" and a.get("merged")]
    roles_done = ", ".join(a.get("role", a["id"]) for a in agents)
    body = (
        f"## Summary\n"
        f"Automated multi-agent mission via Jcode Jarvis.\n\n"
        f"**Mission:** {mission[:600]}\n\n"
        f"**Agents merged:** {roles_done or 'none'}\n\n"
        f"## Agents\n"
        + "\n".join(f"- **{a.get('role',a['id'])}** — branch `{a.get('branch','')}` on {a.get('provider','')}/{a.get('model','')}" for a in agents)
        + "\n\n🤖 Generated by [jcode-jarvise](https://github.com/atulpokharel-gp/jcode-jarvise)"
    )
    return create_github_pr(f"[Jarvis] {headline}", body)


# ── RAG: keyword-based code context injection ────────────────────────────────

def rag_context(task: str, workspace: Path, max_snippets: int = 4, lines_each: int = 40) -> str:
    """Extract relevant code snippets from the workspace using keyword search."""
    keywords = [w for w in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{3,}", task) if w.lower() not in {
        "that", "this", "with", "from", "have", "will", "should", "must", "when",
        "then", "also", "into", "each", "make", "build", "create", "function",
    }][:10]
    if not keywords or not workspace.exists():
        return ""
    snippets: list[str] = []
    seen_files: set[str] = set()
    for kw in keywords:
        if len(snippets) >= max_snippets:
            break
        result = run(
            ["git", "grep", "-n", "-i", "--", kw],
            cwd=workspace, check=False,
        )
        for line in result.stdout.splitlines()[:6]:
            if len(snippets) >= max_snippets:
                break
            parts = line.split(":", 2)
            if len(parts) < 2:
                continue
            fpath = workspace / parts[0]
            key = str(fpath)
            if key in seen_files or not fpath.is_file():
                continue
            seen_files.add(key)
            try:
                lineno = max(0, int(parts[1]) - 5)
                file_lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
                excerpt = "\n".join(file_lines[lineno : lineno + lines_each])
                rel = str(fpath.relative_to(workspace))
                snippets.append(f"--- {rel} (line {lineno+1}) ---\n{excerpt}")
            except (OSError, ValueError):
                continue
    if not snippets:
        return ""
    return "\n\nRelevant codebase context (top matches for your task):\n\n" + "\n\n".join(snippets)


# ── Conflict resolver agent ──────────────────────────────────────────────────

def dispatch_conflict_resolver(state: dict[str, Any], agent: dict[str, Any], workspace: Path) -> None:
    jcode = resolve_jcode_binary()
    settings = load_settings(include_secrets=True)
    resolver_id = f"resolver-{agent['id']}-{int(time.time())}"
    log_path = LOG_DIR / f"{resolver_id}.log"
    conflicts_list = "\n".join(agent.get("conflicts", []))
    merge_out = agent.get("merge_output", "")[:2000]
    prompt = f"""You are a Git Conflict Resolver. A merge of branch `{agent.get('branch')}` into the
base branch produced conflicts. Resolve them cleanly and commit the result.

Conflicted files:
{conflicts_list or '(check git status)'}

Merge error output:
{merge_out}

Steps:
1. Run `git status` to see conflicting files.
2. For each conflicted file: open it, understand both sides, resolve the conflict markers.
3. Stage all resolved files with `git add`.
4. Commit with message: `resolve merge conflicts from {agent.get('branch')}`
5. Report what was resolved and how.
"""
    selection = select_agent_model({"task": "git merge conflict resolution"}, settings)
    _, model_env, provider_label, model_label = launch_args_for(selection)
    extra_args = build_jcode_extra_args(settings)
    _, model_args, _, _ = launch_args_for(selection)
    log_file = log_path.open("w", encoding="utf-8")
    child_env = os.environ.copy()
    child_env.update(model_env)
    child_env["JARVIS_MEMORY_URL"] = f"http://127.0.0.1:{SERVER_PORT}/api/memory"
    process = subprocess.Popen(
        [jcode, *extra_args, *model_args, "run", prompt],
        cwd=str(workspace),
        env=child_env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    resolver = {
        "id": resolver_id,
        "role": "Conflict Resolver",
        "kind": "resolver",
        "resolves": agent["id"],
        "branch": agent.get("branch"),
        "status": "running",
        "log": str(log_path),
        "provider": provider_label,
        "model": model_label,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    PROCESSES[resolver_id] = process
    state.setdefault("agents", []).append(resolver)
    apcall(state, "master", resolver_id, "task.dispatch", {"branch": agent.get("branch")}, f"Conflict resolver launched for {agent.get('branch')}")


# ── Project context detection ────────────────────────────────────────────────

def detect_project_type(workspace: Path) -> dict[str, str]:
    """Detect language, package manager, and build/test commands from workspace files."""
    w = workspace
    if (w / "package.json").exists():
        try:
            pkg = json.loads((w / "package.json").read_text("utf-8", errors="replace"))
            sc  = pkg.get("scripts", {})
            pm  = "yarn" if (w / "yarn.lock").exists() else ("pnpm" if (w / "pnpm-lock.yaml").exists() else "npm")
            return {
                "lang":  "JavaScript/TypeScript",
                "pm":    pm,
                "build": sc.get("build", f"{pm} run build") if "build" in sc else "",
                "test":  sc.get("test",  f"{pm} test")      if "test"  in sc else "",
                "lint":  sc.get("lint",  f"{pm} run lint")  if "lint"  in sc else "",
                "dev":   sc.get("dev",   "")                if "dev"   in sc else "",
            }
        except Exception:
            return {"lang": "JavaScript/TypeScript"}
    if any((w / f).exists() for f in ("pyproject.toml", "setup.py", "requirements.txt")):
        return {
            "lang":  "Python",
            "build": "",
            "test":  "pytest" if shutil.which("pytest") else "python -m pytest",
            "lint":  "ruff check ." if shutil.which("ruff") else "",
        }
    if (w / "go.mod").exists():
        return {"lang": "Go", "build": "go build ./...", "test": "go test ./..."}
    if (w / "Cargo.toml").exists():
        return {"lang": "Rust", "build": "cargo build", "test": "cargo test", "lint": "cargo clippy"}
    if (w / "pom.xml").exists():
        return {"lang": "Java/Maven", "build": "mvn package -q", "test": "mvn test -q"}
    if list(w.glob("*.sln")) or list(w.glob("*.csproj")):
        return {"lang": "C#/.NET", "build": "dotnet build", "test": "dotnet test"}
    if (w / "Gemfile").exists():
        return {"lang": "Ruby", "build": "bundle install", "test": "bundle exec rspec"}
    return {}


def write_agent_claude_md(worktree: Path, agent: dict[str, Any], project: dict[str, str]) -> None:
    """Write .claude/CLAUDE.md so jcode reads agent workflow instructions automatically."""
    lang  = project.get("lang", "")
    pm    = project.get("pm", "")
    build = project.get("build", "")
    test  = project.get("test", "")
    lint  = project.get("lint", "")

    verify_cmds = [c for c in [lint, build, test] if c]
    verify_block = ""
    if verify_cmds:
        cmds_str = "\n".join(f"- `{c}`" for c in verify_cmds)
        verify_block = f"""
## Verification — REQUIRED before every commit
Run in order; fix any failures before committing:
{cmds_str}
"""
    install_hint = f"\nIf dependencies are missing, run `{pm} install` first." if pm else ""

    content = f"""# Agent: {agent['id']} / {agent['role']}

## Assignment
{agent['task']}

## Project language
{lang or 'Detect from workspace files.'}{install_hint}

## Required workflow
1. **Explore** — run `ls`, `git log --oneline -5`, read files relevant to your task.
2. **Understand** — read existing code your changes will touch.
3. **Implement** — make changes scoped strictly to your assignment.
4. **Verify** — run build + test; fix all errors before committing.
5. **Commit** — `git add -A && git commit -m "<type>: <message>"` — never leave uncommitted work.
6. **Report** — files changed, commands that passed, risks, blockers.
{verify_block}
## Scope rules
- Stay inside this worktree and branch only.
- Do not modify files owned by other agents' roles.
- If blocked on another agent's interface, stub it cleanly and document the blocker.
- Always commit completed work — the console only sees committed changes.
"""
    claude_dir = worktree / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "CLAUDE.md").write_text(content, "utf-8")


def build_jcode_extra_args(settings: dict[str, Any] | None = None) -> list[str]:
    """Return base extra args for all jcode agent spawns (env + settings merged)."""
    args = shlex.split(os.environ.get("JARVIS_JCODE_ARGS", ""), posix=os.name != "nt")
    if settings is None:
        settings = load_settings(include_secrets=False)
    if settings.get("agents", {}).get("skip_permissions", True):
        if "--dangerously-skip-permissions" not in args:
            args.append("--dangerously-skip-permissions")
    return args


# ── MCP Connector Hub ────────────────────────────────────────────────────────

def mcp_connectors_load() -> list[dict[str, Any]]:
    try:
        return json.loads(MCP_CONNECTORS_FILE.read_text("utf-8")) if MCP_CONNECTORS_FILE.exists() else []
    except Exception:
        return []


def mcp_connectors_save(connectors: list[dict[str, Any]]) -> None:
    MCP_CONNECTORS_FILE.write_text(json.dumps(connectors, indent=2), "utf-8")


def mcp_connector_add(body: dict[str, Any]) -> dict[str, Any]:
    connectors = mcp_connectors_load()
    catalog_id = str(body.get("catalog_id") or "custom")
    entry = next((c for c in MCP_CATALOG if c["id"] == catalog_id), None)
    conn_id = f"mcp-{int(time.time() * 1000)}"
    connector: dict[str, Any] = {
        "id": conn_id,
        "catalog_id": catalog_id,
        "name": str(body.get("name") or (entry["name"] if entry else "Custom")),
        "enabled": True,
        "transport": str(body.get("transport") or (entry.get("transport", "stdio") if entry else "stdio")),
        "command": str(body.get("command") or (entry.get("command", "") if entry else "")),
        "args": list(body.get("args") or (entry.get("args", []) if entry else [])),
        "env": dict(body.get("env") or {}),
        "url": str(body.get("url") or ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    connectors.append(connector)
    mcp_connectors_save(connectors)
    return {"ok": True, "connector": connector}


def mcp_connector_update(conn_id: str, body: dict[str, Any]) -> dict[str, Any]:
    connectors = mcp_connectors_load()
    for c in connectors:
        if c["id"] == conn_id:
            for field in ("name", "command", "url"):
                if field in body:
                    c[field] = str(body[field])
            if "args" in body:
                c["args"] = list(body["args"])
            if "env" in body:
                c["env"] = dict(body["env"])
            if "enabled" in body:
                c["enabled"] = bool(body["enabled"])
            if "transport" in body:
                c["transport"] = str(body["transport"])
            mcp_connectors_save(connectors)
            return {"ok": True, "connector": c}
    raise RuntimeError(f"Connector {conn_id} not found")


def mcp_connector_delete(conn_id: str) -> dict[str, Any]:
    connectors = mcp_connectors_load()
    updated = [c for c in connectors if c["id"] != conn_id]
    if len(updated) == len(connectors):
        raise RuntimeError(f"Connector {conn_id} not found")
    mcp_connectors_save(updated)
    return {"ok": True}


def build_mcp_json() -> dict[str, Any]:
    """Build the mcpServers dict from all enabled connectors."""
    servers: dict[str, Any] = {}
    for conn in mcp_connectors_load():
        if not conn.get("enabled", True):
            continue
        key = re.sub(r"[^a-zA-Z0-9_]", "_", conn["id"])
        env = dict(conn.get("env") or {})
        transport = conn.get("transport", "stdio")
        if transport in ("sse", "streamable-http"):
            servers[key] = {"type": transport, "url": conn.get("url", "")}
        else:
            # Substitute {VAR} placeholders in args
            args = []
            for arg in (conn.get("args") or []):
                if arg.startswith("{") and arg.endswith("}"):
                    var = arg[1:-1]
                    args.append(env.get(var, os.environ.get(var, arg)))
                else:
                    args.append(arg)
            servers[key] = {
                "type": "stdio",
                "command": conn.get("command", "npx"),
                "args": args,
                "env": env,
            }
    return {"mcpServers": servers}


def write_mcp_config(worktree: Path) -> None:
    """Write .mcp.json to worktree so jcode picks up configured MCP servers."""
    mcp = build_mcp_json()
    if not mcp["mcpServers"]:
        return
    (worktree / ".mcp.json").write_text(json.dumps(mcp, indent=2), "utf-8")


# ── Dependency-aware scheduling ──────────────────────────────────────────────

PENDING_WORKERS: list[dict[str, Any]] = []  # workers held back by unmet dependencies
PENDING_LOCK = threading.Lock()


def deps_satisfied(plan_item: dict[str, Any], state: dict[str, Any]) -> bool:
    """Return True if all dependencies for this plan item are complete."""
    deps = plan_item.get("depends_on") or []
    if not deps:
        return True
    completed_roles = {
        a.get("role", "") for a in state.get("agents", [])
        if a.get("status") == "complete" and a.get("kind") not in ("healer", "qa", "resolver")
    }
    return all(dep in completed_roles for dep in deps)


def try_launch_pending(state: dict[str, Any]) -> int:
    """Attempt to launch any pending workers whose dependencies are now satisfied."""
    with PENDING_LOCK:
        if not PENDING_WORKERS:
            return 0
        launched = 0
        still_pending = []
        for pw in PENDING_WORKERS:
            if live_process_count() >= MAX_CONCURRENT_AGENTS:
                still_pending.append(pw)
                continue
            if not deps_satisfied(pw["plan_item"], state):
                still_pending.append(pw)
                continue
            _spawn_worker(state, pw["plan_item"], pw["stamp"], pw["base_branch"],
                          pw["workspace"], pw["jcode"], pw["extra_args"], pw["settings"])
            launched += 1
        PENDING_WORKERS[:] = still_pending
    return launched


# ── Agent prompts ───────────────────────────────────────────────────────────

def worker_prompt(
    agent: dict[str, Any],
    headline: str,
    team_roles: list[str],
    project: dict[str, str] | None = None,
) -> str:
    project = project or {}
    lang  = project.get("lang", "")
    pm    = project.get("pm", "")
    build = project.get("build", "")
    test  = project.get("test", "")
    lint  = project.get("lint", "")

    lang_line = f"\nProject language/stack: {lang}" if lang else ""
    install_hint = f"\nInstall deps first: `{pm} install`" if pm else ""
    verify_cmds = [c for c in [lint, build, test] if c]
    verify_section = ""
    if verify_cmds:
        steps = "\n".join(f"  {i+1}. `{c}`" for i, c in enumerate(verify_cmds))
        verify_section = f"""
Before committing, verify your code actually works:
{steps}
Fix all errors/warnings before committing.
"""

    return f"""You are {agent['role']}, a specialist worker deployed by the Jarvis master.
{lang_line}{install_hint}

Mission:
{headline}

Your assignment:
{agent['task']}

Other agents own these scopes — stay out and assume a clean interface:
{team_boundaries(agent, team_roles)}

Required workflow:
1. EXPLORE — run `ls`, `git log --oneline -5`, read files relevant to your task first.
2. IMPLEMENT — write code for your assignment only; do not expand scope.
3. VERIFY — run build and test commands below to confirm correctness.
4. COMMIT — commit all changes (`git add -A && git commit -m "..."`) before finishing.
5. REPORT — end with: files changed, commands run, risks, blockers.
{verify_section}
Additional rules:
- Work only in your current git worktree and branch.
- If blocked on another agent's work, stub a clean interface and note the blocker.
- If your work has a UI, use the built-in `browser` tool to verify it renders.
- A QA agent will verify your output — make the build and tests pass.

Central Memory (shared across all agents on this mission):
  READ:  curl "$JARVIS_MEMORY_URL"
  WRITE: curl -s -X POST "$JARVIS_MEMORY_URL" -H "Content-Type: application/json" \\
           -d '{{"key":"<key>","summary":"<what you found>","agent_id":"{agent['id']}","tags":"<tags>"}}'
Read memory before starting; write when you discover something others need to know.
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

Central Memory: check $JARVIS_MEMORY_URL for context left by other agents.
Write a memory entry describing the root cause and fix so the team learns from it.
curl -s "$JARVIS_MEMORY_URL" | python3 -c "import sys,json;[print(r['key'],':',r['summary']) for r in json.load(sys.stdin)]"
"""


def _spawn_worker(
    state: dict[str, Any],
    item: dict[str, str],
    stamp: str,
    base_branch: str,
    workspace: Path,
    jcode: str,
    extra_args: list[str],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Create a worktree, build the prompt with RAG context, and launch the agent process."""
    index = item.get("_index", 1)
    agent_id = f"agent-{stamp}-{index}"
    branch = f"jarvis/{stamp}/{index}"
    worktree = WORKTREE_ROOT / stamp / f"agent-{index}"
    run(["git", "worktree", "add", "-B", branch, str(worktree), "HEAD"], cwd=workspace)
    write_mcp_config(worktree)
    log_path = LOG_DIR / f"{agent_id}.log"
    agent: dict[str, Any] = {
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
    headline = mission_headline(str(state.get("whiteboard", {}).get("mission") or item.get("task") or ""))
    team_roles = [a.get("role", "") for a in state.get("agents", []) if a.get("kind") not in ("healer", "qa", "resolver")]
    project = detect_project_type(workspace)
    write_agent_claude_md(worktree, agent, project)
    rag = rag_context(item.get("task", ""), workspace)
    prompt = worker_prompt(agent, headline, team_roles, project) + rag
    log_file = log_path.open("w", encoding="utf-8")
    child_env = os.environ.copy()
    child_env.update(model_env)
    child_env["JARVIS_MEMORY_URL"] = f"http://127.0.0.1:{SERVER_PORT}/api/memory"
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
    state.setdefault("agents", []).append(agent)
    apcall(
        state,
        "master",
        agent_id,
        "task.dispatch",
        {"branch": branch, "model": f"{provider_label}/{model_label}", "deps": item.get("depends_on", [])},
        f"{agent_id} launched on {branch} ({provider_label}/{model_label})",
    )
    return agent


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
        if live_process_count() >= MAX_CONCURRENT_AGENTS:
            raise RuntimeError(
                f"Cannot launch: {live_process_count()} agents already running "
                f"(ceiling is {MAX_CONCURRENT_AGENTS}). Stop some agents first."
            )
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base_branch = current_branch(workspace)
        jcode = resolve_jcode_binary()
        settings = load_settings(include_secrets=True)
        extra_args = build_jcode_extra_args(settings)
        plan = clean_plan(plan)
        if not plan:
            raise RuntimeError("Plan is empty.")
        state["budget"] = {
            "total": len(plan) * MISSION_AGENT_BUDGET_MULTIPLIER,
            "spent": len(plan),
            "mission_workers": len(plan),
        }
        whiteboard = state.get("whiteboard")
        if not isinstance(whiteboard, dict) or not whiteboard.get("tasks"):
            whiteboard = build_whiteboard(task, plan)
            state["whiteboard"] = whiteboard
        whiteboard["status"] = "executing"
        # Tag each plan item with its index for _spawn_worker
        for i, item in enumerate(plan, start=1):
            item["_index"] = i
        mission_id = stamp
        state["mission_id"] = mission_id
        # Launch immediately or queue as pending based on dependency graph
        launched: list[dict[str, Any]] = []
        with PENDING_LOCK:
            PENDING_WORKERS.clear()
        for i, item in enumerate(plan, start=1):
            if deps_satisfied(item, state):
                agent = _spawn_worker(state, item, stamp, base_branch, workspace, jcode, extra_args, settings)
                launched.append(agent)
                # Assign on whiteboard
                if i - 1 < len(whiteboard.get("tasks", [])):
                    whiteboard["tasks"][i - 1]["assignee"] = agent["id"]
                    whiteboard["tasks"][i - 1]["branch"]   = agent["branch"]
                    whiteboard["tasks"][i - 1]["status"]   = "in_progress"
            else:
                with PENDING_LOCK:
                    PENDING_WORKERS.append({
                        "plan_item": item, "stamp": stamp, "base_branch": base_branch,
                        "workspace": workspace, "jcode": jcode,
                        "extra_args": extra_args, "settings": settings,
                    })
                apcall(state, "master", f"agent-{stamp}-{i}", "task.queued",
                       {"deps": item.get("depends_on", [])},
                       f"Worker {i} ({item['role']}) waiting on: {item.get('depends_on', [])}")
        state["plan"] = plan
        state["plan_preview"] = False
        sync_tasks(state)
        apcall(state, "master", "all", "swarm.deploy",
               {"launched": len(launched), "pending": len(PENDING_WORKERS)})
        save_state(state)
        return hydrate_state(state)


def agent_by_id(state: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    for agent in state.get("agents", []):
        if agent.get("id") == agent_id:
            return agent
    return None


def read_agent_log(agent_id: str, after_line: int = 0) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        agent = agent_by_id(state, agent_id)
        if not agent:
            raise RuntimeError(f"Unknown agent: {agent_id}")
        raw_log_path = str(agent.get("log") or "").strip()
        if not raw_log_path:
            return {"id": agent_id, "lines": [], "total_lines": 0, "start_line": 0, "running": False}
        log_path = Path(raw_log_path)
        if not log_path.exists() or not log_path.is_file():
            return {"id": agent_id, "lines": [], "total_lines": 0, "start_line": 0, "running": False}
        all_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(all_lines)
        running = bool(
            agent_id in PROCESSES and PROCESSES[agent_id].poll() is None
        )
        # First load: cap at last 300 lines so the UI doesn't stall on huge logs
        if after_line == 0 and total > 300:
            start = total - 300
        else:
            start = max(0, after_line)
        new_lines = all_lines[start:]
        last_line = next((l.strip() for l in reversed(all_lines) if l.strip()), "")
        return {
            "id":          agent_id,
            "lines":       new_lines,
            "total_lines": total,
            "start_line":  start,
            "running":     running,
            "last_line":   last_line,
        }


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


def set_qa(enabled: bool) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        qa = state.setdefault("qa", {"enabled": True, "attempts": {}})
        qa["enabled"] = bool(enabled)
        apcall(
            state,
            "master",
            APCALL_QA_BUS,
            "qa.toggle",
            {"enabled": bool(enabled)},
            f"QA verification {'enabled' if enabled else 'disabled'} by master.",
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


# ── Code Studio: live worktree file viewer ───────────────────────────────────

_BINARY_EXTS = {
    "png","jpg","jpeg","gif","svg","ico","webp","bmp","tiff",
    "pdf","zip","tar","gz","bz2","7z","rar","exe","dll","so","dylib",
    "woff","woff2","ttf","eot","otf","mp4","mp3","webm","avi","mov",
    "db","sqlite","pyc","pyo","class","jar","war","bin","dat",
}


def _is_binary(path: Path) -> bool:
    return path.suffix.lstrip(".").lower() in _BINARY_EXTS


def studio_snapshot() -> list[dict[str, Any]]:
    """Return each active agent with its recently modified files + content."""
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
    active_statuses = {"running", "starting", "healing", "testing"}
    results: list[dict[str, Any]] = []
    for idx, agent in enumerate(state.get("agents", [])):
        if agent.get("status") not in active_statuses:
            continue
        worktree = Path(agent.get("worktree", ""))
        if not worktree.exists():
            continue
        # Collect changed files: tracked modifications + untracked new files
        diff_out   = run(["git", "diff", "--name-only", "HEAD"], cwd=worktree, check=False)
        staged_out = run(["git", "diff", "--name-only", "--cached"], cwd=worktree, check=False)
        untracked  = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=worktree, check=False)
        changed: dict[str, float] = {}
        for line in (diff_out.stdout + staged_out.stdout + untracked.stdout).splitlines():
            fname = line.strip()
            if not fname:
                continue
            fpath = worktree / fname
            if fpath.is_file() and not _is_binary(fpath):
                try:
                    changed[fname] = fpath.stat().st_mtime
                except OSError:
                    pass
        # Sort by most recently modified (most active file first)
        sorted_files = sorted(changed.items(), key=lambda x: x[1], reverse=True)
        file_entries: list[dict[str, Any]] = []
        for fname, mtime in sorted_files[:10]:
            fpath = worktree / fname
            try:
                raw = fpath.read_text(encoding="utf-8", errors="replace")
                content = raw[:80_000]
                if len(raw) > 80_000:
                    content += "\n\n// ... file truncated for studio view ..."
                file_entries.append({
                    "path":    fname,
                    "content": content,
                    "lines":   len(content.splitlines()),
                    "mtime":   mtime,
                })
            except OSError:
                continue
        results.append({
            "agent_id":   agent["id"],
            "role":       agent.get("role", agent["id"]),
            "status":     agent.get("status", ""),
            "branch":     agent.get("branch", ""),
            "color_idx":  idx % 8,
            "files":      file_entries,
            "active_file": file_entries[0] if file_entries else None,
        })
    return results


def studio_file(agent_id: str, file_path: str) -> dict[str, Any]:
    """Read a specific file from an agent's worktree on demand."""
    with STATE_LOCK:
        state = load_state()
    agent = agent_by_id(state, agent_id)
    if not agent:
        raise RuntimeError(f"Unknown agent: {agent_id}")
    worktree = Path(agent.get("worktree", ""))
    target = (worktree / file_path).resolve()
    if not str(target).startswith(str(worktree.resolve())):
        raise PermissionError("Path is outside the agent worktree")
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    if _is_binary(target):
        raise ValueError("Binary files cannot be displayed in the studio")
    raw = target.read_text(encoding="utf-8", errors="replace")
    content = raw[:100_000]
    if len(raw) > 100_000:
        content += "\n\n// ... file truncated ..."
    return {
        "agent_id": agent_id,
        "path":     file_path,
        "content":  content,
        "lines":    len(content.splitlines()),
    }


def merge_finished(auto_pr: bool = False) -> dict[str, Any]:
    with STATE_LOCK:
        state = load_state()
        poll_processes(state)
        workspace = active_workspace()
        if not is_git_repo(workspace):
            raise RuntimeError("Selected workspace is not a git repo.")
        if dirty(workspace):
            raise RuntimeError("Workspace is dirty. Commit or stash before master merge.")
        merged: list[str] = []
        conflict_agents: list[dict[str, Any]] = []
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
                event(state, f"Conflict while merging {branch}. Spawning conflict resolver.")
                # Abort the failed merge so the workspace is clean for other branches
                run(["git", "merge", "--abort"], cwd=workspace, check=False)
                dispatch_conflict_resolver(state, agent, workspace)
                conflict_agents.append(agent)
                continue
            agent["merged"] = True
            merged.append(branch)
            apcall(state, agent["id"], "master", "branch.merged", {"branch": branch}, f"Merged {branch}")
        pr_result: dict[str, Any] = {}
        if not merged and not conflict_agents:
            event(state, "No completed worker branches were ready to merge.")
        else:
            whiteboard = state.get("whiteboard")
            if isinstance(whiteboard, dict) and not conflict_agents:
                whiteboard["status"] = "merged"
            apcall(state, "master", "all", "swarm.combined",
                   {"branches": merged, "conflicts": len(conflict_agents)})
            cost = cost_summary(state.get("mission_id", ""))
            fire_webhook("mission.merged", {
                "merged": merged,
                "conflicts": [a["id"] for a in conflict_agents],
                "cost_usd": cost["cost_usd"],
                "mission": str((state.get("whiteboard") or {}).get("mission") or ""),
            })
            if auto_pr and merged:
                pr_result = auto_pr_from_state(state)
                if pr_result.get("ok"):
                    state["last_pr_url"] = pr_result["url"]
        save_state(state)
        result = hydrate_state(state)
        if pr_result:
            result["pr"] = pr_result
        return result


# ============================================================================
# DevSpace MCP bridge
#
# A self-hosted, token-protected MCP server (Model Context Protocol) that lets a
# remote MCP client -- ChatGPT, Claude, etc. -- read, edit, search, run, and
# git-manage files in allow-listed local project folders, and launch a Jarvis
# swarm. Disabled by default; exposes nothing until the owner enables it and
# sets a token. Bind stays on localhost -- put a tunnel (Cloudflare/ngrok) in
# front for remote access. See docs/REMOTE_MCP_BRIDGE.md.
# ============================================================================

MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_SESSION_ID = "jcode-jarvise-devspace"


def devspace_config() -> dict[str, Any]:
    settings = load_settings(include_secrets=True)
    cfg = settings.get("devspace") or {}
    enabled = bool(cfg.get("enabled")) or str(os.environ.get("JARVIS_MCP_ENABLED", "")).lower() in ("1", "true", "yes")
    token = os.environ.get("JARVIS_MCP_TOKEN") or str(cfg.get("token") or "")
    roots_env = os.environ.get("JARVIS_MCP_ROOTS")
    raw_roots = [r for r in roots_env.split(os.pathsep) if r.strip()] if roots_env else (cfg.get("allowed_roots") or [str(ROOT)])
    roots: list[Path] = []
    for raw in raw_roots:
        try:
            roots.append(Path(os.path.expandvars(os.path.expanduser(str(raw)))).resolve())
        except OSError:
            continue
    # Generate and persist a token the first time the bridge is enabled empty.
    if enabled and not token and not os.environ.get("JARVIS_MCP_TOKEN"):
        token = secrets.token_urlsafe(24)
        full = load_settings(include_secrets=True)
        full["devspace"] = {**(full.get("devspace") or {}), "enabled": True, "token": token}
        SETTINGS_FILE.write_text(json.dumps(full, indent=2), encoding="utf-8")
        print(f"[jarvis] DevSpace MCP token generated: {token}")
    return {"enabled": enabled, "token": token, "roots": roots or [ROOT], "allow_shell": bool(cfg.get("allow_shell", True))}


def devspace_resolve(path_str: str | None, roots: list[Path]) -> Path:
    candidate = Path(os.path.expandvars(os.path.expanduser(str(path_str or "."))))
    if not candidate.is_absolute():
        candidate = (roots[0] / candidate)
    candidate = candidate.resolve()
    for root in roots:
        try:
            candidate.relative_to(root)
            return candidate
        except ValueError:
            continue
    raise PermissionError(f"Path is outside the allowed workspace roots: {path_str}")


def ds_list_projects(cfg: dict[str, Any]) -> Any:
    return [
        {"path": str(root), "exists": root.exists(), "is_git_repo": root.exists() and is_git_repo(root)}
        for root in cfg["roots"]
    ]


def ds_read_file(cfg: dict[str, Any], path: str, max_bytes: int = 200000) -> str:
    target = devspace_resolve(path, cfg["roots"])
    if not target.is_file():
        raise FileNotFoundError(f"No such file: {path}")
    return target.read_text(encoding="utf-8", errors="replace")[:max_bytes]


def ds_write_file(cfg: dict[str, Any], path: str, content: str) -> str:
    target = devspace_resolve(path, cfg["roots"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {target}"


def ds_list_dir(cfg: dict[str, Any], path: str = ".") -> Any:
    target = devspace_resolve(path, cfg["roots"])
    if not target.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    out = []
    for entry in sorted(target.iterdir()):
        out.append(
            {
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            }
        )
    return out


def ds_search(cfg: dict[str, Any], query: str, path: str | None = None, max_results: int = 100) -> Any:
    root = devspace_resolve(path, cfg["roots"]) if path else cfg["roots"][0]
    max_results = max(1, min(1000, int(max_results)))
    rg = shutil.which("rg")
    results: list[str] = []
    if rg:
        proc = run([rg, "--line-number", "--no-heading", "--color", "never", "-S", query, str(root)], cwd=root, check=False)
        results = proc.stdout.splitlines()[:max_results]
    else:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "target", ".jcode")]
            for filename in files:
                filepath = Path(dirpath) / filename
                try:
                    for line_no, line in enumerate(filepath.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                        if query in line:
                            results.append(f"{filepath}:{line_no}:{line.strip()[:200]}")
                            if len(results) >= max_results:
                                return results
                except OSError:
                    continue
    return results


def ds_run_command(cfg: dict[str, Any], command: str, cwd: str | None = None) -> Any:
    if not cfg["allow_shell"]:
        raise PermissionError("Shell execution is disabled (devspace.allow_shell = false).")
    workdir = devspace_resolve(cwd, cfg["roots"]) if cwd else cfg["roots"][0]
    proc = subprocess.run(
        command,
        cwd=str(workdir),
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
    )
    return {"exit_code": proc.returncode, "output": (proc.stdout or "")[-20000:]}


def ds_git_status(cfg: dict[str, Any], path: str | None = None) -> str:
    root = devspace_resolve(path, cfg["roots"]) if path else cfg["roots"][0]
    return git_status_for(root)


def ds_launch_swarm(cfg: dict[str, Any], mission: str, max_agents: int = 6) -> Any:
    mission = str(mission or "").strip()
    if not mission:
        raise ValueError("mission is required")
    plan = choose_plan(mission, max_agents=max(1, min(12, int(max_agents))))
    with STATE_LOCK:
        state = load_state()
        start_session(state)
        state["plan"] = plan
        state["plan_preview"] = True
        state["whiteboard"] = build_whiteboard(mission, plan)
        save_state(state)
    result = start_workers(mission, plan)
    return {"launched": len(result.get("agents", [])), "session_id": result.get("session_id"), "tasks": len(plan)}


def mcp_tools() -> list[dict[str, Any]]:
    return [
        {"name": "list_projects", "description": "List the local project folders this server may access.", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "read_file", "description": "Read a UTF-8 text file inside an allowed project.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        {"name": "write_file", "description": "Create or overwrite a text file inside an allowed project.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
        {"name": "list_directory", "description": "List entries of a directory inside an allowed project.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
        {"name": "search_files", "description": "Search file contents (ripgrep) inside an allowed project.", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}},
        {"name": "run_command", "description": "Run a shell command inside an allowed project (if shell is enabled).", "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}}, "required": ["command"]}},
        {"name": "git_status", "description": "Show git status --short for an allowed project.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}},
        {"name": "launch_swarm", "description": "Launch a Jarvis multi-agent swarm on a mission in the active workspace.", "inputSchema": {"type": "object", "properties": {"mission": {"type": "string"}, "max_agents": {"type": "integer"}}, "required": ["mission"]}},
    ]


def mcp_call_tool(cfg: dict[str, Any], name: str, args: dict[str, Any]) -> Any:
    if name == "list_projects":
        return ds_list_projects(cfg)
    if name == "read_file":
        return ds_read_file(cfg, args["path"])
    if name == "write_file":
        return ds_write_file(cfg, args["path"], args.get("content", ""))
    if name == "list_directory":
        return ds_list_dir(cfg, args.get("path", "."))
    if name == "search_files":
        return ds_search(cfg, args["query"], args.get("path"), int(args.get("max_results", 100)))
    if name == "run_command":
        return ds_run_command(cfg, args["command"], args.get("cwd"))
    if name == "git_status":
        return ds_git_status(cfg, args.get("path"))
    if name == "launch_swarm":
        return ds_launch_swarm(cfg, args["mission"], int(args.get("max_agents", 6)))
    raise ValueError(f"Unknown tool: {name}")


def mcp_handle(cfg: dict[str, Any], message: dict[str, Any]) -> dict[str, Any] | None:
    """Handle one JSON-RPC message; return a response dict or None for notifications."""
    msg_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        proto = params.get("protocolVersion") or MCP_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "jcode-jarvise-devspace", "version": "1.0.0"},
            },
        }
    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": mcp_tools()}}
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        try:
            result = mcp_call_tool(cfg, name, args)
            text = result if isinstance(result, str) else json.dumps(result, indent=2)
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": text}], "isError": False}}
        except Exception as exc:  # surface tool errors to the model
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": f"Error: {exc}"}], "isError": True}}
    if msg_id is None:
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}


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

    # --- remote auth helpers ---

    def _session_token(self) -> str:
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, val = part.strip().partition("=")
            if name.strip() == "jarvis_session":
                return val.strip()
        return ""

    def _is_local(self) -> bool:
        return self.client_address[0] in ("127.0.0.1", "::1", "localhost")

    def _authorized(self) -> bool:
        return self._is_local() or check_session(self._session_token())

    def _redirect_pin(self) -> None:
        self.send_response(302)
        self.send_header("Location", "/pin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _serve_asset(self, filename: str) -> None:
        path = (ASSET_DIR / filename).resolve()
        if not str(path).startswith(str(ASSET_DIR.resolve())) or not path.exists():
            self.send_error(404)
            return
        suffix = Path(filename).suffix
        ct = {"css": "text/css", "js": "text/javascript", "html": "text/html",
              "png": "image/png", "gif": "image/gif", "mp4": "video/mp4"}.get(suffix.lstrip("."), "text/html")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def mcp_authorized(self, cfg: dict[str, Any]) -> bool:
        token = cfg.get("token") or ""
        if not token:
            return False
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and secrets.compare_digest(auth[7:].strip(), token):
            return True
        if secrets.compare_digest(self.headers.get("X-DevSpace-Token", ""), token):
            return True
        supplied = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return bool(supplied) and secrets.compare_digest(supplied, token)

    def handle_mcp(self) -> None:
        """DevSpace MCP bridge: token-gated JSON-RPC over Streamable HTTP."""
        cfg = devspace_config()
        if not cfg["enabled"]:
            self.send_json({"error": "DevSpace MCP bridge is disabled. Enable devspace in settings."}, status=403)
            return
        if not self.mcp_authorized(cfg):
            data = json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "Unauthorized"}}).encode("utf-8")
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Bearer realm="devspace"')
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            message = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status=400)
            return
        if isinstance(message, list):
            responses = [r for r in (mcp_handle(cfg, m) for m in message if isinstance(m, dict)) if r is not None]
            self.send_mcp(responses if responses else None)
            return
        if not isinstance(message, dict):
            self.send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}, status=400)
            return
        self.send_mcp(mcp_handle(cfg, message))

    def send_mcp(self, response: Any) -> None:
        if response is None:
            self.send_response(202)
            self.send_header("Mcp-Session-Id", MCP_SESSION_ID)
            self.end_headers()
            return
        data = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Mcp-Session-Id", MCP_SESSION_ID)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
            # PIN entry page — no auth required
            if parsed.path == "/pin":
                self._serve_asset("pin.html")
                return
            # Static assets (css/js/images) — no auth so pin.html can load styles
            if parsed.path not in ("/", "") and not parsed.path.startswith("/api/") and not parsed.path.startswith("/apcall/"):
                route = parsed.path.lstrip("/")
                candidate = (ASSET_DIR / route).resolve()
                if str(candidate).startswith(str(ASSET_DIR.resolve())) and candidate.exists() and candidate.is_file():
                    self._serve_asset(route)
                    return
            # Remote-access routes open to authorized clients
            if parsed.path == "/api/tunnel/status":
                if not self._authorized():
                    self.send_json({"error": "unauthorized"}, status=401)
                    return
                self.send_json(tunnel_status())
                return
            # Auth gate for everything else
            if not self._authorized():
                if parsed.path.startswith("/api/"):
                    self.send_json({"error": "unauthorized"}, status=401)
                else:
                    self._redirect_pin()
                return
            if parsed.path == "/api/status":
                with STATE_LOCK:
                    state = load_state()
                    poll_processes(state)
                    self.send_json(hydrate_state(state))
                return
            if parsed.path == "/api/agent/log":
                agent_id  = parse_qs(parsed.query).get("id", [""])[0]
                after_raw = parse_qs(parsed.query).get("after", ["0"])[0]
                try:
                    after = max(0, int(after_raw))
                except ValueError:
                    after = 0
                self.send_json(read_agent_log(agent_id, after))
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
            if parsed.path == "/api/memory":
                q = parse_qs(parsed.query).get("q", [""])[0]
                mission = parse_qs(parsed.query).get("mission", [""])[0]
                tag = parse_qs(parsed.query).get("tag", [""])[0]
                limit = int(parse_qs(parsed.query).get("limit", ["200"])[0])
                self.send_json(memory_read(q=q, mission_id=mission, tag=tag, limit=limit))
                return
            if parsed.path == "/api/templates":
                self.send_json(templates_load())
                return
            if parsed.path == "/api/studio/snapshot":
                self.send_json(studio_snapshot())
                return
            if parsed.path == "/api/studio/file":
                agent_id  = parse_qs(parsed.query).get("agent", [""])[0]
                file_path = parse_qs(parsed.query).get("path",  [""])[0]
                self.send_json(studio_file(agent_id, file_path))
                return
            if parsed.path == "/api/diff":
                self.send_json(diff_preview())
                return
            if parsed.path == "/api/cost":
                mission_id = parse_qs(parsed.query).get("mission", [""])[0]
                self.send_json(cost_summary(mission_id))
                return
            if parsed.path == "/api/mcp-connectors/catalog":
                self.send_json({"catalog": MCP_CATALOG})
                return
            if parsed.path == "/api/mcp-connectors":
                self.send_json({"connectors": mcp_connectors_load()})
                return
            if parsed.path.startswith("/apcall/v1"):
                self.handle_apcall_get(parsed)
                return
            if parsed.path == "/mcp":
                cfg = devspace_config()
                self.send_json(
                    {
                        "server": "jcode-jarvise-devspace",
                        "protocol": MCP_PROTOCOL_VERSION,
                        "enabled": cfg["enabled"],
                        "transport": "POST /mcp (JSON-RPC 2.0)",
                        "tools": [tool["name"] for tool in mcp_tools()],
                    }
                )
                return
            route = "index.html" if parsed.path in ("/", "") else parsed.path.lstrip("/")
            self._serve_asset(route)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)
            return

    def do_POST(self) -> None:  # noqa: N802
        try:
            if urlparse(self.path).path == "/mcp":
                self.handle_mcp()
                return
            # PIN verification — no session required
            if urlparse(self.path).path == "/api/pin/verify":
                body = self.read_json()
                submitted = str(body.get("pin", "")).strip()
                if verify_pin(submitted):
                    token = create_session()
                    data = json.dumps({"ok": True, "local": self._is_local()}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header(
                        "Set-Cookie",
                        f"jarvis_session={token}; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}; Path=/",
                    )
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_json({"ok": False, "error": "Wrong PIN — try again."}, status=401)
                return
            # Auth gate for all other POST routes
            if not self._authorized():
                self.send_json({"error": "unauthorized"}, status=401)
                return
            body = self.read_json()
            # PIN reset (local only — remote callers already know the PIN)
            if self.path == "/api/pin/reset":
                new_pin = reset_pin()
                self.send_json({**tunnel_status(), "pin": new_pin})
                return
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
                auto_pr = bool(body.get("auto_pr", False))
                self.send_json(merge_finished(auto_pr=auto_pr))
                return
            if self.path == "/api/pr/create":
                title = str(body.get("title") or "").strip()
                pr_body = str(body.get("body") or "").strip()
                if not title:
                    raise RuntimeError("PR title is required.")
                self.send_json(create_github_pr(title, pr_body))
                return
            if self.path == "/api/templates":
                name   = str(body.get("name") or "").strip()
                prompt = str(body.get("prompt") or "").strip()
                tags   = str(body.get("tags") or "").strip()
                if not name or not prompt:
                    raise RuntimeError("Template name and prompt are required.")
                self.send_json(template_add(name, prompt, tags))
                return
            if self.path == "/api/templates/delete":
                tid = str(body.get("id") or "").strip()
                if not tid:
                    raise RuntimeError("Template id is required.")
                self.send_json(template_delete(tid))
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
            if self.path == "/api/qa/toggle":
                self.send_json(set_qa(bool(body.get("enabled", True))))
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
            if self.path == "/api/killswitch":
                self.send_json(killswitch())
                return
            if self.path == "/api/memory":
                key = str(body.get("key") or "").strip()
                if not key:
                    raise RuntimeError("Memory key is required.")
                self.send_json(memory_write(
                    key=key,
                    summary=str(body.get("summary") or ""),
                    agent_id=str(body.get("agent_id") or ""),
                    mission_id=str(body.get("mission_id") or ""),
                    tags=str(body.get("tags") or ""),
                    payload=str(body.get("payload") or ""),
                ))
                return
            if self.path == "/api/memory/clear":
                self.send_json(memory_clear())
                return
            mem_del = re.match(r"^/api/memory/(.+)$", urlparse(self.path).path)
            if mem_del:
                self.send_json(memory_delete(mem_del.group(1)))
                return
            if self.path == "/api/mcp-connectors":
                self.send_json(mcp_connector_add(body))
                return
            mcp_upd = re.match(r"^/api/mcp-connectors/([^/]+)$", urlparse(self.path).path)
            if mcp_upd:
                self.send_json(mcp_connector_update(mcp_upd.group(1), body))
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

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            if not self._authorized():
                self.send_json({"error": "unauthorized"}, status=401)
                return
            parsed = urlparse(self.path)
            mem_del = re.match(r"^/api/memory/(.+)$", parsed.path)
            if mem_del:
                self.send_json(memory_delete(mem_del.group(1)))
                return
            mcp_del = re.match(r"^/api/mcp-connectors/([^/]+)$", parsed.path)
            if mcp_del:
                self.send_json(mcp_connector_delete(mcp_del.group(1)))
                return
            self.send_json({"error": "Unknown route"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=400)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[jarvis] {self.address_string()} {fmt % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Jcode Jarvis console.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-tunnel", action="store_true", help="Skip Cloudflare Tunnel auto-start")
    args = parser.parse_args()
    global SERVER_PORT
    SERVER_PORT = args.port
    ensure_dirs()
    memory_init()
    cost_init()
    pin = ensure_pin()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[jarvis] Local console : http://{args.host}:{args.port}")
    print(f"[jarvis] Remote PIN    : {pin}  (change in Settings > Remote Access)")
    print("[jarvis] Set JARVIS_JCODE_ARGS to pin provider/model flags for workers.")
    settings = load_settings(include_secrets=True)
    tunnel_mode = settings.get("remote", {}).get("tunnel", "auto")
    if not args.no_tunnel and tunnel_mode != "off":
        threading.Thread(target=start_tunnel, args=(args.port,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[jarvis] Stopping console.")
    finally:
        if TUNNEL_PROC and TUNNEL_PROC.poll() is None:
            TUNNEL_PROC.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
