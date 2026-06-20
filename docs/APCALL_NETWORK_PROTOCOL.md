# apcall Network Protocol

Status: HTTP read/ingest transport and the append-only session log are
implemented in `scripts/jarvis_console.py`. The WebSocket stream, node
handshake, acknowledgements, and auth remain on the roadmap.

`apcall` means **Agent Protocol Call**. In the current Jarvis console it is a
local persisted message bus stored in `.jcode/jarvis-console/state.json`. This
document defines the network version so a master Jcode agent, worker agents,
self-healing agents, observers, and future remote runners can coordinate across
processes or machines.

## Goals

- Keep the current hierarchical model: master controls planning, dispatch,
  merge, and escalation.
- Let workers communicate through structured messages instead of ad hoc logs.
- Support local-only operation first, then LAN or remote operation over TLS.
- Make agent actions auditable with an append-only message stream.
- Preserve safe git isolation: workers still operate in assigned worktrees and
  branches.
- Provide enough reliability for coding work: acknowledgements, retries,
  idempotency, heartbeats, and replay.

## Non-Goals

- It is not a general public chat protocol.
- It does not allow arbitrary peer-to-peer code execution.
- It does not move secrets between agents.
- It does not replace git; it coordinates the agents that operate around git.

## Topology

apcall-net uses a **hierarchical hub-and-spoke mesh**:

- **Master Node**: owns the mission, session, whiteboard, policy, model routing,
  worker dispatch, merge, and conflict escalation.
- **Worker Node**: receives one scoped task, reports progress, writes to its
  assigned worktree/branch, and exits with a result.
- **Healer Node**: subscribes to `apcall://heal`, receives failed worker context,
  and repairs the failed worker's own branch/worktree.
- **Observer Node**: dashboard, CLI, logger, or voice system that subscribes to
  the stream but cannot mutate unless granted capability.

Workers do not directly mutate each other's state. They communicate through the
master-owned apcall bus. This preserves hierarchy while still making the swarm
feel like a live team.

```text
                 observer/dashboard
                         |
                         v
worker-1  <---->  master apcall bus  <---->  worker-2
                         |
                         v
                  apcall://heal
                         |
                         v
                    healer node
```

## Transport

Primary transport:

```text
WSS /apcall/v1/sessions/{session_id}/stream
```

Fallback transport:

```text
POST /apcall/v1/sessions/{session_id}/messages
GET  /apcall/v1/sessions/{session_id}/messages?after={message_id}
POST /apcall/v1/sessions/{session_id}/ack
```

Local development may run on plain WebSocket bound to `127.0.0.1`. Anything
outside localhost must use TLS.

The stream uses one JSON object per message. Binary attachments are not sent
inline; messages reference artifacts by URI.

## Message Envelope

Every apcall network message uses the same envelope:

```json
{
  "apc_version": "apcall/1.0",
  "id": "apc_01HX8G7RW5Y2X3E4F9Q1C8V2RK",
  "session_id": "ses_01HX8G4Y9BN1D0M6DM4N0Q96PH",
  "mission_id": "mis_01HX8G50F3DQFTEQ6K6CGV8G31",
  "trace_id": "trc_01HX8G7RZQXH1J63ZC7HY65E1A",
  "parent_id": "apc_01HX8G7KM4F2H6F99X9V4QYVYD",
  "from": {
    "node_id": "master",
    "role": "Master Jcode",
    "kind": "master"
  },
  "to": {
    "node_id": "agent-20260620-001",
    "bus": null,
    "role": "Frontend Engineer"
  },
  "type": "task.dispatch",
  "seq": 42,
  "ts": "2026-06-20T18:35:42.125Z",
  "ttl_ms": 600000,
  "priority": "normal",
  "requires_ack": true,
  "idempotency_key": "task.dispatch:agent-20260620-001:jarvis/20260620/1",
  "payload": {
    "branch": "jarvis/20260620/1",
    "worktree": ".jcode/jarvis-console/worktrees/20260620/agent-1",
    "model": "nvidia/deepseek-ai/deepseek-v4-pro"
  },
  "attachments": [],
  "auth": {
    "kid": "session-key-1",
    "sig": "base64url(signature-over-canonical-message)"
  }
}
```

Required fields:

- `apc_version`
- `id`
- `session_id`
- `from`
- `to`
- `type`
- `seq`
- `ts`
- `payload`

Optional but recommended:

- `mission_id`
- `trace_id`
- `parent_id`
- `requires_ack`
- `idempotency_key`
- `auth`

## Addressing

`to` supports three routing styles:

```json
{ "node_id": "agent-1" }
{ "role": "Security Review Agent" }
{ "bus": "apcall://heal" }
```

Reserved buses:

- `apcall://master`
- `apcall://workers`
- `apcall://heal`
- `apcall://whiteboard`
- `apcall://observers`
- `apcall://all`

The master is the only node allowed to broadcast to `apcall://all` by default.

## Node Handshake

Each node joins with:

```json
{
  "type": "node.join",
  "payload": {
    "node_id": "agent-20260620-001",
    "kind": "worker",
    "role": "Frontend Engineer",
    "capabilities": ["task.execute", "git.commit", "log.stream"],
    "workspace": {
      "branch": "jarvis/20260620/1",
      "worktree": ".jcode/jarvis-console/worktrees/20260620/agent-1"
    },
    "protocols": ["apcall/1.0"]
  }
}
```

The master replies with:

```json
{
  "type": "node.accepted",
  "payload": {
    "heartbeat_ms": 5000,
    "replay_after": "apc_...",
    "capabilities_granted": ["task.execute", "git.commit", "log.stream"]
  }
}
```

If the node is not trusted or requested capabilities exceed policy, the master
returns `node.rejected`.

## Message Types

Planning:

- `plan.broadcast`: master sends mission, acceptance criteria, policy.
- `plan.contribute`: agent posts planning analysis to the whiteboard.
- `plan.note`: operator or agent adds a note.
- `plan.lock`: master freezes the plan before dispatch.

Task lifecycle:

- `task.dispatch`: master assigns scoped task, branch, model route.
- `task.accepted`: worker confirms it owns the task.
- `task.progress`: worker reports milestone or percent.
- `task.blocked`: worker needs input or dependency.
- `task.artifact`: worker publishes an artifact URI.
- `status.complete`: worker completed and committed.
- `status.failed`: worker failed.
- `status.stopped`: master stopped the worker.

Healing:

- `heal.request`: master or operator asks for repair.
- `heal.dispatch`: healer assigned to failed worker branch.
- `heal.progress`: healer reports diagnosis or fix step.
- `heal.result`: healer reports success or failure.
- `heal.giveup`: max repair attempts exhausted.
- `heal.muted`: auto-repair disabled by policy.

Git and merge:

- `branch.claimed`: worker branch/worktree is ready.
- `branch.committed`: worker created a commit.
- `branch.merge.request`: worker says branch is merge-ready.
- `branch.merged`: master merged branch.
- `branch.conflict`: git conflict requires master resolution.
- `swarm.combined`: master completed final integration.

Observability:

- `log.chunk`: streamed log tail.
- `node.heartbeat`: liveness signal.
- `node.metrics`: token/cost/runtime stats.
- `node.exit`: process exit code and reason.

Reliability:

- `ack`: message accepted.
- `nack`: message rejected with reason.
- `replay.request`: subscriber asks for missed messages.
- `replay.end`: replay stream completed.

## Delivery Semantics

apcall-net provides:

- **At-least-once delivery** for messages with `requires_ack: true`.
- **Best-effort delivery** for telemetry like `log.chunk`.
- **Per-sender ordering** using `seq`.
- **Idempotent processing** using `idempotency_key`.
- **Replay** from the append-only session log.

Workers must dedupe by `id` and `idempotency_key`.

Acknowledgement:

```json
{
  "type": "ack",
  "to": { "node_id": "master" },
  "payload": {
    "ack_id": "apc_01HX8G7RW5Y2X3E4F9Q1C8V2RK",
    "status": "accepted"
  }
}
```

Negative acknowledgement:

```json
{
  "type": "nack",
  "payload": {
    "ack_id": "apc_...",
    "reason": "capability_denied",
    "retryable": false
  }
}
```

Retry policy:

- `task.dispatch`, `heal.dispatch`, and `branch.merge.request`: retry with
  exponential backoff until ack or TTL expiry.
- `log.chunk`, `node.metrics`: no retry.
- `status.complete`, `status.failed`: retry until ack because they affect
  master state.

## Heartbeats and Failure Detection

Each active node sends:

```json
{
  "type": "node.heartbeat",
  "payload": {
    "status": "running",
    "pid": 12345,
    "last_log_id": "log_..."
  }
}
```

Default heartbeat interval: `5000 ms`.

If the master misses three heartbeats, it marks the node `unknown`. If the
worker process is also gone or unreachable, the master emits `status.failed`
and may dispatch the healer.

## Security Model

Default mode is local-only:

- bind to `127.0.0.1`
- use a per-session token
- do not expose to LAN by default

Remote mode requires:

- TLS
- short-lived session token minted by the master
- message signing using HMAC-SHA256 or Ed25519
- capability-based authorization
- no API keys, provider secrets, or raw credential files in payloads

Capability examples:

- `task.execute`
- `git.commit`
- `git.merge`
- `heal.dispatch`
- `whiteboard.write`
- `log.read`
- `settings.write`

Only the master should have `git.merge` by default.

## Payload Limits and Artifacts

Recommended limits:

- message envelope: 64 KB
- `log.chunk`: 16 KB
- replay batch: 100 messages
- artifact reference list: 32 items

Large data goes through artifact URIs:

```json
{
  "type": "task.artifact",
  "payload": {
    "artifacts": [
      {
        "kind": "patch",
        "uri": "file://.jcode/jarvis-console/artifacts/agent-1/fix.patch",
        "sha256": "..."
      }
    ]
  }
}
```

## Session Log

The master persists every accepted message to an append-only session log:

```text
.jcode/jarvis-console/sessions/<session_id>/apcall.ndjson
```

The current `state.json` can keep a compact recent projection for the dashboard,
but the network protocol should treat the NDJSON session log as the source of
truth for replay and audit.

## End-to-End Mission Flow

1. Operator enters a mission.
2. Master creates `mission_id` and broadcasts `plan.broadcast`.
3. Agent lanes reply with `plan.contribute`.
4. Master locks the whiteboard with `plan.lock`.
5. Workers join with `node.join`.
6. Master sends `task.dispatch` to each worker.
7. Workers send `task.accepted`, `task.progress`, and `log.chunk`.
8. Worker succeeds with `status.complete` or fails with `status.failed`.
9. Failure triggers `heal.request` and `heal.dispatch` on `apcall://heal`.
10. Healer sends `heal.result`.
11. Master merges completed branches with `branch.merged`.
12. Master publishes `swarm.combined`.

## Compatibility With Current Local apcall

The current local message:

```json
{
  "id": "apcall-...",
  "time": "18:35:42",
  "from": "master",
  "to": "all",
  "type": "plan.broadcast",
  "payload": {}
}
```

maps directly into the network envelope by adding:

- `apc_version`
- `session_id`
- `mission_id`
- `seq`
- ISO timestamp
- optional auth/signature

This means the browser UI can keep rendering `state.apcall` while the backend
gradually adds a real stream endpoint.

## Minimal Implementation Plan

- [x] Add an append-only `apcall.ndjson` writer alongside `state.json`.
- [x] Add `GET /apcall/v1/sessions/{session_id}/messages` (replay).
- [x] Add `POST /apcall/v1/sessions/{session_id}/messages` (ingest).
- [x] Add `GET /apcall/v1/sessions` and `GET /apcall/v1/session`.
- [ ] Add WebSocket stream endpoint.
- [ ] Add `node.join`, `ack`, `nack`, heartbeat, and replay handshake.
- [ ] Add per-session token auth for non-localhost access.
- [ ] Move worker/healer launchers to connect as apcall nodes.
- [ ] Keep the dashboard as an observer node.

This keeps the current Jarvis behavior working while turning apcall into a real
network protocol for distributed agent teams.

## Implementation Status

The HTTP fallback transport and the append-only session log are live in
`scripts/jarvis_console.py`:

- Every published apcall message is assigned a per-session `seq` and mirrored
  into `.jcode/jarvis-console/sessions/<session_id>/apcall.ndjson` as a full
  network envelope (`apc_version`, `session_id`, `mission_id`, `seq`, `ts`,
  `from`/`to`, `payload`).
- A fresh session + `mission_id` is opened at the start of each plan or launch.
- Live endpoints:
  - `GET /apcall/v1/session` — current session and mission ids.
  - `GET /apcall/v1/sessions` — list sessions that have a log.
  - `GET /apcall/v1/sessions/{session_id}/messages?after={id}&limit={n}` —
    replay the session log, optionally after a given message id.
  - `POST /apcall/v1/sessions/{session_id}/messages` — ingest a message from an
    external node; it is appended to the log and reflected on the live bus.

Still unbuilt from the design above: the WSS stream, `node.join`/`ack`/`nack`
handshake, heartbeats as a transport feature, capability tokens, and signing.
These are the next milestones before remote (non-localhost) operation.
