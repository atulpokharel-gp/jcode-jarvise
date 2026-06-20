# Remote MCP Bridge (DevSpace‑style)

The Jarvis console can expose your local projects to a remote MCP client —
ChatGPT, Claude, or any [Model Context Protocol](https://modelcontextprotocol.io)
client — so it can read, edit, search, run, and git‑manage files on your machine
and even launch a Jarvis swarm, **without uploading your code anywhere**. You
own the server and the tunnel.

This is inspired by [Waishnav/devspace](https://github.com/Waishnav/devspace).

> **It is disabled by default.** Nothing is exposed until you enable it and set a
> token. The server still binds to `127.0.0.1`; you put a tunnel in front of it
> for remote access.

## Enable it

Pick one of the two ways.

### A) Settings file

Edit `.jcode/jarvis-console/settings.json`:

```json
"devspace": {
  "enabled": true,
  "token": "",
  "allowed_roots": ["C:\\Users\\you\\projects\\my-app"],
  "allow_shell": true
}
```

If `token` is left blank, a strong token is generated on first use and printed
to the console log:

```
[jarvis] DevSpace MCP token generated: V3ry-l0ng-r4nd0m-t0k3n
```

### B) Environment variables (override the file)

```powershell
$env:JARVIS_MCP_ENABLED = "1"
$env:JARVIS_MCP_TOKEN   = "choose-a-long-secret"
$env:JARVIS_MCP_ROOTS   = "C:\Users\you\projects\my-app;C:\Users\you\projects\api"
python scripts/jarvis_console.py
```

`JARVIS_MCP_ROOTS` is OS‑path‑separator delimited (`;` on Windows, `:` elsewhere).

## Transport & endpoints

- `GET  /mcp` — server info + tool list (no auth; shows `enabled` state).
- `POST /mcp` — MCP JSON‑RPC 2.0 over Streamable HTTP. **Requires the token.**

Authenticate the POST in any of these ways:

```
Authorization: Bearer <token>
X-DevSpace-Token: <token>
POST /mcp?token=<token>
```

## Tools

| Tool | Description |
|------|-------------|
| `list_projects` | List the allowed project folders. |
| `read_file` | Read a UTF‑8 text file inside an allowed project. |
| `write_file` | Create/overwrite a text file inside an allowed project. |
| `list_directory` | List a directory's entries. |
| `search_files` | Search file contents (ripgrep if available). |
| `run_command` | Run a shell command in an allowed project (if `allow_shell`). |
| `git_status` | `git status --short` for an allowed project. |
| `launch_swarm` | Launch a Jarvis multi‑agent swarm on a mission. |

Every path is resolved and **must** live inside one of `allowed_roots`; anything
outside (including `../` traversal) is rejected.

## Connect from a client

The endpoint is `http(s)://<host>/mcp` with the bearer token. Quick check with curl:

```bash
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

For ChatGPT / Claude custom connectors, add an MCP/HTTP server with the URL and
an `Authorization: Bearer <token>` header.

## Expose it remotely with a tunnel

Keep the console on localhost and front it with a tunnel that terminates TLS:

```bash
# Cloudflare Tunnel
cloudflared tunnel --url http://127.0.0.1:8765

# or ngrok
ngrok http 8765
```

Use the resulting `https://…/mcp` URL in your MCP client. Because the token is
required and paths are sandboxed, only a client holding the token can act, and
only within your allow‑listed folders.

## Security model

- **Off by default** — no `/mcp` access until you enable it *and* a token exists.
- **Token required** — constant‑time compared; the token is never returned by
  `/api/settings`.
- **Localhost bind** — remote reach is only via a tunnel you run and can stop.
- **Workspace allowlist** — file/shell/git operations are confined to
  `allowed_roots`; traversal outside is blocked.
- **Shell is opt‑outable** — set `"allow_shell": false` to forbid `run_command`.
- Treat the token like an SSH key. Anyone with it can act inside your allowed
  folders (and, if shell is on, run commands). Rotate it by changing the value
  and restarting the console.
