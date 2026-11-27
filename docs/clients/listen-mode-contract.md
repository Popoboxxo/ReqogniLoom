# Listen-mode relay contract

Status: binding for every ReqogniLoom client plugin (Claude Code, Hermes,
OpenCode V1/V2, Antigravity). Source of the feature: the listen-mode
specification (`docs/superpowers/specs/2026-11-21-listen-modus-alle-clients-design.md`,
G1–G6) and ADR-032. The conformance suite
`docs/agent-templates/test_listen_conformance.py` checks the same scenarios
against every adapter.

The clients implement this contract natively, in their own language, but with
**identical values and an identical status schema**. Anything that decides what
is captured, deduplicated or redacted stays on the server
(`POST /api/v1/suggestions/capture/`, MCP `suggestion.capture`) — the relay only
does cheap pre-checks and delivery.

## State directory

| Item | Value |
|---|---|
| Linux/macOS | `~/.reqogniloom/listen` |
| Windows | `%USERPROFILE%\.reqogniloom\listen` |
| Test/diagnostic override | `REQNILOOM_LISTEN_DIR` (all clients) |
| Directory mode | `0700` |
| File mode | `0600` (every file below) |

The directory is shared by **all** clients on a machine, so one switch and one
queue serve Claude Code, Hermes, OpenCode and Antigravity alike. A client must
never resolve a different path from its own data directory (`CLAUDE_PLUGIN_DATA`,
`HERMES_HOME`, `XDG_*`) — a switch written to one path and read from another is
the defect that broke the first live run.

## Files

| File | Purpose | Format |
|---|---|---|
| `listen.json` | local switch + target | `{"enabled": <bool>, "workspace_id": "<uuid>", "client": "<id>"}` |
| `capture-queue.jsonl` | write-ahead queue, one JSON object per line | see below |
| `listen-status.json` | counters and last result | see below |
| `capture-incoming/` | per-message segments while the queue lock is held | one `<ts>-<pid>-<rand>.json` per entry |
| `capture-queue.lock` | lock directory (mkdir-based) | empty dir; stale after 5 min |
| `capture.log` | diagnostics **without message text and without the key** | one line per event |
| `capture-seen.json` | Antigravity only: dedupe set of `(session_id, sha256(text))` | `{"keys": [...]}`, capped |

`listen.json` is read on **every** message; a switch change takes effect on the
next message, no restart.

### Queue entry

```json
{
  "workspace_id": "<uuid>",
  "text": "<user message>",
  "client": "claude-code | hermes | opencode | antigravity",
  "source_session": "<client session id, optional>",
  "message_id": "<stable message id, optional>",
  "idempotency_key": "<sha256 hex, <=128 chars>",
  "created_at": "<ISO-8601 UTC>",
  "attempts": 0,
  "last_attempt_at": null
}
```

Write-ahead: the hook/event handler **only** appends (queue, or an immutable
`capture-incoming/` segment when the lock is held) and returns. Network work
happens in a drain run. A failed send stays queued for the next run.

Limits: at most 100 entries (oldest dropped), at most 5 per drain run, drop
entries older than 7 days or with `attempts >= 5`.

### Status file

```json
{
  "last_success_at": null,
  "last_error": null,
  "last_error_at": null,
  "captured": 0,
  "failed": 0,
  "queued": 0
}
```

* `captured` counts delivered items (HTTP 2xx).
* `failed` counts failed delivery attempts; the latest one sets
  `last_error`/`last_error_at`.
* A successful delivery resets `last_error` and `last_error_at` to `null` — a
  recovered error must not keep looking current.
* `queued` is the queue length after the run.
* `last_error` carries a code only (`timeout`, `network_error`,
  `missing_config:workspace_id`, `HTTP 500:INTERNAL`), never message text and
  never the key.

## Filter (client-side, cheap pre-check)

Applied **before** anything is written:

1. fewer than **40** characters → drop (trimmed text, `\r\n` normalised to `\n`);
2. first character `/`, `!` or `$` → drop (commands, shell prefixes);
3. more than **300** lines → drop (pasted logs/code).

The authoritative filters (commands, short messages, pasted content, secrets)
and the dedupe live in the server. The relay never redacts on its own — the
server does, before storage and before the model call.

## Delivery

* `POST {base}/api/v1/suggestions/capture/` with `X-API-Key: <reqlo_…>`,
  `Content-Type: application/json`, body `workspace_id`, `text`, `client`,
  `idempotency_key`, plus `source_session` / `message_id` when known.
* Request timeout **60 s** (the server runs a model turn inline). A shorter
  client timeout turns a success into a retry that then hits the idempotency
  duplicate.
* `2xx` → done (success).
* `409` (`CAPTURE_DISABLED`, `DUPLICATE`) → done, no retry.
* `400` (e.g. `TEXT_TOO_LONG`, `VALIDATION_ERROR`) → done, no retry (cannot
  succeed on retry and would grow the queue forever).
* `401`/`403`/`5xx`/timeout/network → keep queued, attempt + 1.
* Never follow a redirect (an API key must not travel to another host).
* **Fail-open:** the hook/event handler always exits 0 and writes nothing to
  stdout (a hook's stdout becomes model context; exit 2 blocks the prompt).

## Switch semantics

* Default **off**. Both switches must be on: local `listen.json.enabled` and the
  server-side workspace preference `capture.enabled`.
* `on` prints the privacy notice (message text leaves the machine for the
  ReqogniLoom server and its model provider).
* `off` is a privacy action: it stops capture **and deletes** the queue and
  `capture-incoming/` — nothing unsent is kept. Counters in
  `listen-status.json` survive (they are history, not content); `queued` is
  reset to 0.
* `status` prints the local switch, the workspace, the server switch (when
  reachable), the queue length, `captured`, `failed`, `last_success_at` and
  `last_error` (+ time).

The server switch is read through
`GET /api/v1/workspaces/{workspace_id}/preference-values/effective/?keys=capture.enabled`.
If it is unknown (not configured, unreachable), say `unknown` — never invent a
value.

## Per-client entry points

| Client | Capture event | Relay implementation | Switch |
|---|---|---|---|
| Claude Code | `UserPromptSubmit` (`async: true`) | `scripts/capture-hook.mjs` (+ detached `--drain`) | `/reqogniloom:listen` |
| Hermes | `pre_llm_call` | `reqogniloom_listen.py` + detached `_capture.py --drain` | `/reqogniloom listen` |
| OpenCode V1 | `chat.message` | `listen.mjs` (package root) | `node listen.mjs on\|off\|status` |
| OpenCode V2 | `session.hook("prompt")` | same `listen.mjs` | same |
| Antigravity | `PreInvocation` (`lastUserInput`) | `listen.py` (plugin root) | `python3 listen.py on\|off\|status` |

Antigravity has no submit event: it is **stage B** and needs its own dedupe over
`(session_id, sha256(text))`; `PreInvocation` fires before *every* model call, so
without that dedupe one message would be captured repeatedly.

## Conformance scenarios

Checked per adapter against an HTTP stub (`test_listen_conformance.py`):

| ID | Scenario | Expectation |
|---|---|---|
| a | default off | 0 requests, queue empty |
| b | short message / slash command | 0 requests |
| c | valid message | one request with the identical contract |
| d | server 500 | entry stays queued, next run delivers it |
| e | 400 / 409 / 401 | 400 and 409 terminal, 401 kept |
| f | `off` | stops capture, deletes unsent entries |
| g | no stdout | hook/handler writes nothing to stdout |

A client whose runtime (node/python) is missing is **skipped with a stated
reason**, never counted green.
