# ReqFlow MCP Server — Complete Reference

> **Version:** 1.0.0 — 2026-06-28

## 1. Overview

ReqFlow ships a native MCP (Model Context Protocol) server alongside its REST API, providing AI-native programmatic access to requirements engineering, test management, traceability, and administration features.

The server adheres to the **JSON-RPC 2.0** wire format and the **Model Context Protocol** tool-calling convention. It exposes **11 tool groups** (40+ individual tools) controlled by role-based access control (RBAC), workspace-preset gating, and full audit logging. Every call is scoped to the caller's workspace and role, making the MCP server suitable for both personal AI assistants (Claude Desktop, ChatGPT) and multi-tenant enterprise deployments.

## 2. Transports

| Endpoint | Method | Transport | Auth |
|----------|--------|-----------|------|
| `/mcp/` | POST | HTTP/JSON-RPC 2.0 | `X-API-Key` header OR `params.api_key` |
| `/mcp/sse/` | POST | SSE (single event) | `X-API-Key` header |
| `/mcp/` | GET | — | Server info / health (no auth) |
| (stdio) | — | stdio (local pipe) | `params.api_key` argument |

**HTTP transport** is the primary mode for cloud and containerised deployments. The SSE endpoint enables server-sent event streaming for long-running operations. The stdio transport is designed for local tool runners (e.g., Claude Desktop with a local Docker exec command) where HTTP headers are impractical.

## 3. Authentication

### API Key Header (preferred)

```
X-API-Key: rfk_<40 character hex string>
```

### API Key in Body (fallback, for stdio)

Include `params.api_key` in the JSON-RPC request body alongside the tool name and arguments.

### Creating an API Key

```bash
# Obtain a JWT session token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"•••"}' | jq -r .access)

# Create a new API key
curl -X POST http://localhost:8000/api/v1/api-keys/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"claude-desktop"}'
# Response: {"id":7, "key":"rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12", ...}
```

**The plaintext key is returned exactly once.** Store it in a password manager or environment variable immediately.

### Revoking a Key

```bash
curl -X DELETE http://localhost:8000/api/v1/api-keys/7/ \
  -H "Authorization: Bearer $TOKEN"
```

Returns `204 No Content`. The key is immediately invalidated.

### Key Behaviour

- Keys **inherit the creator's role and workspace scope** at creation time. Creating a key as Admin gives it full Admin scope; there is no separate key-role system.
- Rotation workflow: create a new key → switch clients to use the new key → revoke the old one.
- The `rfk_` prefix is intentional so secrets-scanners (truffleHog, Gitleaks, etc.) can detect leaked keys in source code.

## 4. Quickstart

### (a) curl + JSON-RPC over HTTP

```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "requirement.query",
      "arguments": {"workspace_id": 1, "limit": 5}
    }
  }'
```

### (b) Claude Desktop Configuration

Add to `~/.claude/claude_desktop_config.json` (or the equivalent path for your OS):

```json
{
  "mcpServers": {
    "reqflow": {
      "url": "http://localhost:8000/mcp/",
      "headers": {
        "X-API-Key": "rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12"
      }
    }
  }
}
```

### (c) Python requests

```python
import requests

r = requests.post(
    "http://localhost:8000/mcp/",
    headers={"X-API-Key": "rfk_Ab12Cd34Ef56Gh78Ij90Kl12Mn34Op56Qr78St90Uv12"},
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "requirement.query",
            "arguments": {"workspace_id": 1, "limit": 5}
        }
    }
)
r.raise_for_status()
data = r.json()
print(data["result"])
```

## 5. Tool Reference

All 11 tool groups listed below. Tools are called as `<prefix>.<tool_name>` (e.g., `requirement.query`, `test.run_create`).

### 5.1 `requirement.*` — Requirements Management

Read, create, update, decompose, and validate requirements.

**Tools:** `get`, `query`, `create`, `update`, `decompose`, `validate`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "requirement.get",
      "arguments": {"workspace_id": 1, "requirement_id": 42}
    }
  }'
```

**Role required:** Member

---

### 5.2 `architecture.*` — Architecture Elements

Read, create, update, and link architecture artifacts (system components, subsystems, interfaces).

**Tools:** `get`, `query`, `create`, `update`, `link`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "architecture.query",
      "arguments": {"workspace_id": 1, "parent_id": 10}
    }
  }'
```

**Role required:** Member

---

### 5.3 `test.*` — Test Management

Read, create, link, execute test runs, and report results.

**Tools:** `get`, `query`, `create`, `update`, `link`, `run_create`, `run_get`, `run_report_results`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "test.run_create",
      "arguments": {"workspace_id": 1, "testcase_ids": [10, 11, 12]}
    }
  }'
```

**Role required:** Member

---

### 5.4 `traceability.*` — Cross-Cutting Traceability

Cross-cutting queries across requirements, architecture, and tests. Search artifacts and retrieve full workspace traceability trees.

**Tools:** `query`, `artifact.search`, `artifact.get_tree`, `workspace.get_context`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "traceability.artifact.search",
      "arguments": {"workspace_id": 1, "q": "safety"}
    }
  }'
```

**Role required:** Member

---

### 5.5 `artifact.*` — Artifact Tree & Comments

Retrieve the full artifact tree and comments for a workspace.

**Tools:** `get_tree`, `get_comments`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "artifact.get_tree",
      "arguments": {"workspace_id": 1, "root_id": null}
    }
  }'
```

**Role required:** Member

---

### 5.6 `workspace.*` — Workspace Lifecycle Management (Admin)

Close, reactivate, and delete workspaces. These are destructive or state-changing operations on the workspace itself.

**Tools:** `get_context`, `close`, `reactivate`, `delete`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "workspace.close",
      "arguments": {"workspace_id": 1}
    }
  }'
```

**Role required:** Admin

---

### 5.7 `permissions.*` — RBAC Rule Management (Admin)

Set, list, revoke, and check RBAC permission rules.

**Tools:** `set_rule`, `list`, `revoke`, `check`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "permissions.check",
      "arguments": {"workspace_id": 1, "user_id": 5, "permission": "workspace.close"}
    }
  }'
```

**Role required:** Admin

---

### 5.8 `admin.*` — Backup & Restore (Admin)

Create and list backups; restore a workspace from a backup.

**Tools:** `backup_create`, `backup_list`, `restore`

**Restore requires** the `X-Captcha: RESTORE` header in addition to the Admin role.

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "admin.backup_create",
      "arguments": {"workspace_id": 1}
    }
  }'
```

**Role required:** Admin (+ `X-Captcha: RESTORE` for restore)

---

### 5.9 `audit.*` — Audit Log Query

Query the system-wide audit log with filters for actor, operation, workspace, and time range.

**Tools:** `query` (supports filters: `actor`, `operation`, `workspace`, `time_from`, `time_to`, `limit`, `offset`)

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "audit.query",
      "arguments": {"workspace_id": 1, "limit": 20}
    }
  }'
```

**Role required:** Member (own scope) / Admin (all scopes)

---

### 5.10 `events.*` — Dead-Letter Queue Management

Inspect and replay failed events from the dead-letter queue (DLQ).

**Tools:** `dlq_list`, `dlq_replay`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "events.dlq_list",
      "arguments": {"workspace_id": 1, "limit": 10}
    }
  }'
```

**Role required:** Member

---

### 5.11 `user.*` — User & Role Management (Admin)

Create, list, assign roles, and deactivate users.

**Tools:** `create`, `assign_role`, `list`, `deactivate`

**Example:**
```bash
curl -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rfk_..." \
  -d '{
    "jsonrpc": "2.0", "id": 1,
    "method": "tools/call",
    "params": {
      "name": "user.list",
      "arguments": {"workspace_id": 1}
    }
  }'
```

**Role required:** Admin

---

## 6. RBAC Matrix

| Tool Group | Member | Admin | Owner |
|------------|--------|-------|-------|
| `requirement.*` | ✓ | ✓ | ✓ |
| `architecture.*` | ✓ | ✓ | ✓ |
| `test.*` | ✓ | ✓ | ✓ |
| `traceability.*` | ✓ | ✓ | ✓ |
| `artifact.*` | ✓ | ✓ | ✓ |
| `workspace.*` | — | ✓ | ✓ |
| `permissions.*` | — | ✓ | ✓ |
| `admin.*` | — | ✓ | ✓ |
| `audit.*` | ✓ (own scope) | ✓ (all) | ✓ (all) |
| `events.*` | ✓ | ✓ | ✓ |
| `user.*` | — | ✓ | ✓ |

- **Member**: Standard authenticated user. Can manage requirements, architecture, tests, traceability, artifacts, and audit (own events).
- **Admin**: Full access to workspace lifecycle, permissions, backups, user management, and cross-scope audit.
- **Owner**: Inherits all Admin privileges; additionally has workspace-level configuration rights.

Attempting a tool without the required role returns error code `PERMISSION_DENIED`.

## 7. Error Codes

The MCP server returns errors in JSON-RPC standard format (`{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"AUTH_FAILED","data":"..."}}`). The following error codes are defined:

| Code | Meaning | When returned |
|------|---------|---------------|
| `AUTH_FAILED` | Authentication failed | API key missing, invalid, revoked, or expired |
| `PERMISSION_DENIED` | Insufficient permissions | Member trying an Admin tool; role lacks required scope |
| `FEATURE_NOT_ENABLED` | Tool not available | The tool's prefix is not in the active workspace preset |
| `UNKNOWN_TOOL` | Tool not registered | Typo in tool name or a tool was removed |
| `VALIDATION_ERROR` | Bad parameters | Arguments failed JSON Schema validation |
| `LLM_NOT_CONFIGURED` | LLM provider missing | Tool requires an LLM call but no provider is configured |
| `NOT_FOUND` | Resource not found | Requested requirement, test case, or workspace ID does not exist |
| `INTERNAL_ERROR` | Server error | Unexpected exception; check backend logs for details |
| `PARSE_ERROR` | JSON parse failure | Malformed JSON in request body |
| `INVALID_REQUEST` | Invalid JSON-RPC frame | Missing required fields: `jsonrpc`, `method`, or `id` |

| JSON-RPC code | MCP code | HTTP status |
|:---|---:|:---:|
| -32700 | `PARSE_ERROR` | 400 |
| -32600 | `INVALID_REQUEST` | 400 |
| -32601 | `UNKNOWN_TOOL` | 404 |
| -32000 | `VALIDATION_ERROR` | 422 |
| -32001 | `AUTH_FAILED` | 401 |
| -32002 | `PERMISSION_DENIED` | 403 |
| -32003 | `FEATURE_NOT_ENABLED` | 403 |
| -32004 | `LLM_NOT_CONFIGURED` | 503 |
| -32005 | `NOT_FOUND` | 404 |
| -32006 | `INTERNAL_ERROR` | 500 |

## 8. Troubleshooting

### AUTH_FAILED

- **Verify the key prefix** — keys start with `rfk_`. If yours starts with anything else (e.g., `sk-`, `rf_`) it was not created through the API-key endpoint.
- **Check revocation** — the key may have been deleted. Create a new one and update your client config.
- **Confirm workspace scope** — if the key was created in a different workspace, it cannot access resources in other workspaces.
- **No expiry** — ReqFlow API keys do not expire automatically, but they are invalidated on user deactivation.

### UNKNOWN_TOOL

- **List available tools** — call `tools/list` to get the full inventory of registered tools:
  ```bash
  curl -X POST http://localhost:8000/mcp/ \
    -H "Content-Type: application/json" \
    -H "X-API-Key: rfk_..." \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
  ```
- **Check spelling** — tool names are lowercase with a dot separator (`requirement.query`, not `requirement_query` or `Requirement.query`).
- **Preset gating** — if the tool prefix is not in your workspace's active preset, the tool will not be registered. Switch to a preset that includes it (e.g., "extended" includes all groups).

### PERMISSION_DENIED

- **Check your role** — use `permissions.check` to verify your current role and effective permissions.
- **Request escalation** — ask a workspace Admin to grant the required role via `permissions.set_rule`.
- **Workspace scope** — your key inherits the role from the creating user at the time of creation. If the user's role was changed later, the key still holds the original role. Create a fresh key after a role change.

### FEATURE_NOT_ENABLED

- The workspace preset (minimal / standard / extended) determines which tool groups are active.
- Ask an Admin to switch the workspace to the "extended" preset if you need access to all 11 tool groups.

### LLM_NOT_CONFIGURED

- Some tools (e.g., `requirement.decompose`, `traceability.artifact.search` with semantic mode) require an LLM provider.
- Set `LLM_PROVIDER` and `LLM_API_KEY` environment variables and restart the backend.
- Supported providers: `anthropic`, `openai`, `ollama`.
