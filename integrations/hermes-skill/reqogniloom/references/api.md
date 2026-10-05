# ReqogniLoom API surface (Hermes skill connector)

Minimal reference for the two calls this skill makes. Full schema:
`GET <base>/api/schema/` (OpenAPI) and `docs/agent-templates/tool-manifest.json` (MCP tools).

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `REQOGNILOOM_BASE_URL` | no | Server origin. Default `http://localhost:8001`. |
| `REQOGNILOOM_API_KEY` | yes | `reqlo_...` API key. Sent as the `X-API-Key` header. |
| `REQOGNILOOM_WORKSPACE_ID` | no | Default workspace UUID (informational; pass per call). |

No secret is ever hardcoded; only the environment is read.

## Authentication

Every call sends `X-API-Key: <reqlo_...>`. The REST layer accepts it with
precedence over `Authorization: Bearer` (`backend/auth_tenancy/rest.py`), and the
MCP HTTP transport reads it from the same header (`backend/mcp_server/protocol_handler.py`).

## Endpoints

### `GET /api/v1/workspaces/`

Lists the workspaces visible to the key. Returns a DRF page
`{"count": N, "next": ..., "results": [...]}` or a bare array.

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
