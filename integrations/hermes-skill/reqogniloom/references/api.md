# ReqogniLoom API surface (Hermes skill connector)

Minimal reference for the REST and MCP calls this skill makes. Full schema:
`GET <base>/api/schema/` (OpenAPI) and `docs/agent-templates/tool-manifest.json` (MCP tools).

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `REQOGNILOOM_BASE_URL` | no | Server origin. Default `http://localhost:8001`. |
| `REQOGNILOOM_API_KEY` | yes | `reqlo_...` API key. Sent as the `X-API-Key` header. |
| `REQOGNILOOM_WORKSPACE_ID` | no | Default workspace UUID for the memory commands (also settable via the global `--workspace-id` flag). |

No secret is ever hardcoded; only the environment is read.

## Authentication

Every call sends `X-API-Key: <reqlo_...>`. The REST layer accepts it with
precedence over `Authorization: Bearer` (`backend/auth_tenancy/rest.py`), and the
MCP HTTP transport reads it from the same header (`backend/mcp_server/protocol_handler.py`).

## Endpoints

### `GET /api/v1/workspaces/`

Lists the workspaces visible to the key. Returns a DRF page
`{"count": N, "next": ..., "results": [...]}` or a bare array. The client
follows `next` to the last page (guarding against a repeated `next`) and merges
every page into one page dict — `results` concatenated, `next` cleared,
`count`/`previous` kept — or into one array when the endpoint returns a bare
array.

### `POST /mcp/`

JSON-RPC 2.0. A tool call is:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": { "name": "<tool>", "arguments": { } }
}
```

`protocol_handler.py` reads the tool name from `params.name` and the arguments
from `params.arguments` for `tools/call`. Other methods (`tools/list`,
`initialize`, `ping`) exist but are not used here.

## Memory tools

Tool names use dots. All four are addressed through the same `tools/call`
frame; the client exposes one subcommand per tool and only sends the arguments
you actually provide.

| Subcommand | MCP tool | Arguments (after `--`) |
|---|---|---|
| `memory-query` | `memory.query` | `--query` (required), `--scope`, `--scopes` (comma-separated, repeatable), `--workspace-id`, `--artifact-id`, `--top-k` |
| `memory-digest` | `memory.digest` | `--workspace-id` (required via flag/env), `--artifact-id` |
| `memory-ask` | `memory.ask` | `--query` (required), `--workspace-id` (required via flag/env), `--artifact-id`, `--reasoning-level` (`minimal\|low\|medium\|high\|max`) |
| `memory-write` | `memory.write` | `--content` (required), `--scope` (required: `workspace\|user\|artifact`), `--workspace-id`, `--artifact-id`, `--confidence` (float), `--change-reason` |

Scope rules — the client pre-validates the cases it can (a missing target id
for `workspace`/`artifact`, or an incompatible `--artifact-id`/`--workspace-id`
combination, fails locally with a clear `reqogniloom: error:` line and no
request). Whatever reaches the backend is still enforced there and its
`VALIDATION_ERROR` is surfaced as a normalised `code: message` line:

- `scope=workspace` requires `workspace_id`.
- `scope=artifact` requires `artifact_id`.
- `scope=user` must carry **neither** `workspace_id` nor `artifact_id` — the
  client does not inject the configured default, and an explicitly supplied
  target id is rejected rather than silently dropped.
- For `memory-query` the decision is made from the **effective** scope set:
  `--scopes` takes precedence over `--scope` (same as the backend), and when
  `--scopes` is given the single `--scope` value is not sent. A `workspace` in
  the set requires (and injects) a workspace id; an `artifact` in the set
  requires `--artifact-id`; `--scope user` alone injects neither.

`--workspace-id` is a global flag defaulting to `REQOGNILOOM_WORKSPACE_ID`.
`memory-digest`, `memory-ask`, `memory-query --scope/--scopes workspace` and
`memory-write --scope workspace` fail with a clear client-side error when
neither the flag nor the env yields a value.

`memory.write` is a write and its response is a single entry view object
(`entry_id`, `content`, `scope`, `workspace_id`, `user_id`, `artifact_id`,
`entity_type`, `contributor_user_id`, `source_event_id`, `source_session_id`,
`confidence`, `language`, `created_at`, plus the `superseded_by`/`backend`/
`degraded` envelope fields). In the plugin it is gated by an explicit user
confirmation before the call is issued; this skill only frames the call.

The follow-up stage "memory → proposed artifact" is **P4** and out of scope for
this connector.

## Error shapes (both normalised to `code: message`)

Nested — the REST envelope and JSON-RPC error frames:

```json
{ "error": { "code": "invalid_api_key", "message": "Invalid API key." } }
```

Flat — legacy/simple shape:

```json
{ "error": "invalid_api_key", "message": "Invalid API key." }
```

## MCP errors: protocol vs. tool execution

**Protocol errors** return their natural HTTP status and carry a top-level
`error` object: `AUTH_FAILED` → 401, `PERMISSION_DENIED` → 403,
`PARSE_ERROR`/`INVALID_REQUEST`/`VALIDATION_ERROR`/`UNKNOWN_TOOL` → 400,
`NOT_FOUND` → 404, `INTERNAL_ERROR` → 500.

**Tool-execution errors** stay **HTTP 200**; the error lives in the body:
`{"result": {"content": [...], "isError": true}}`.

The client detects both — protocol errors via the non-200 status or the error
body, tool errors via `result.isError` — prints one normalised line to stderr
and exits `1`.
