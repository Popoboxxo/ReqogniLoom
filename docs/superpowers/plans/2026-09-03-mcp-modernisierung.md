# MCP-Modernisierung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the hand-rolled MCP server up to protocol revision 2025-06-18 with negotiated version fallback, add `resources/*` and `prompts/*` capabilities on top of existing domain seams, close the ICD read gap between REST and MCP, and add two additive manifest filters (`ApiKey.scope` = real security gate, `ApiKey.tool_groups` = catalogue curation only).

**Architecture:** All protocol-level work stays inside `backend/mcp_server/` (`protocol_handler.py` for JSON-RPC method routing, `views.py` for HTTP header semantics), all domain reads route through existing Layer-2 seams (`application/export_service.py`, `application/prompt_resolver.py`, `icd/services.py`, `traceability/service.py`) so the ADR-01 ORM ratchet in `backend/rest_api/tests/test_architecture.py` stays at its frozen ceilings. Protocol-version handling changes from a hard constant to a negotiated set so a client that still speaks `2024-11-05` keeps working — the spec's stated backwards-compatibility risk is resolved by negotiation, not by a version bump alone.

**Tech Stack:** Python 3.x, Django 5.2+, DRF, pytest / pytest-django, JSON-RPC 2.0 over HTTP + SSE (no MCP SDK — the server is hand-rolled; verified: `backend/requirements.txt` contains no MCP library, so no SDK pin constrains the version bump).

**Spec:** docs/superpowers/specs/2026-09-03-mcp-modernisierung-design.md

## Global Constraints

- `MCP_PROTOCOL_VERSION` becomes `"2025-06-18"`; `SUPPORTED_PROTOCOL_VERSIONS` is `("2025-06-18", "2025-03-26", "2024-11-05")` and `initialize` echoes the client's requested version when it is in that tuple, otherwise the latest (MCP lifecycle §Version Negotiation: "If the server supports the requested protocol version, it MUST respond with the same version").
- The legacy SSE transport (`POST /mcp/sse/`, `POST /mcp/messages/?session_id=`) is NOT removed, NOT deprecated, and NOT altered by this plan — the OpenCode fallback path depends on it (spec §3).
- `artifact.get` does not exist and is not created. `artifact.get_tree` (the real tool) stays unchanged. No existing tool name, schema or payload shape changes anywhere in this plan.
- `ApiKey.scope="read"` is a real security boundary: `tools/list` hides write tools AND `dispatch_request()` rejects them with `PERMISSION_DENIED` (spec §6.1).
- `ApiKey.tool_groups` is NOT a security boundary: it filters `tools/list` only. `tools/call` keeps working for every tool the caller's role and `scope` allow (spec §6.2). Every place it is exposed (REST field help text, `tool.list_groups` description, docs) must state this in words.
- `tool.list_groups` is always visible and never filtered — by `tool_groups`, by `scope`, or by role.
- ADR-01 ORM ratchet: `MCP_ROOT_MAX_ORM_LINES = {"tool_registry.py": 1}` and every other `backend/mcp_server/*.py` module has an implicit ceiling of **0** direct-ORM lines (`.objects.` / `.unscoped.`). New modules `mcp_server/resources.py`, `mcp_server/prompts.py` and `mcp_server/tools/icd.py` must contain **zero** such lines. Enforced by `backend/rest_api/tests/test_architecture.py::test_no_new_direct_orm_access_mcp_root` and `::test_no_new_direct_orm_access_mcp_tools`.
- Read-tool classification ratchet: every new read tool must be accounted for by exactly one of the four mechanisms in `backend/mcp_server/workspace_scope.py` (required `workspace_id`, `_TOOL_TARGETS` entry, `TOOL_ENFORCED_WORKSPACE_SCOPE`, `TENANT_SCOPED_READ_TOOLS`), or `backend/mcp_server/tests/test_mcp_workspace_scope.py` fails the build.
- `_is_write_tool()` is fail-closed: `_READ_ONLY_TOOL_SUFFIXES = (".read", ".query")`. A new read tool ending in `.get` or `.list_groups` is treated as a WRITE tool unless it is added to `_READ_ONLY_TOOL_NAMES` explicitly.
- CWE-209 masking policy: never pass `str(exc)` into `ToolResult.error(...)` or a JSON-RPC error message in new code. Log the detail, return the static `ERROR_CODES[...]` text.
- **PRECONDITION for Tasks 10, 12 and 13:** `ApiKey.scope` (`models.CharField(max_length=16, choices=[("read","Read"),("write","Write")], default="write")`) is delivered by `docs/superpowers/plans/2026-09-03-ki-vorschlag-als-zustand.md` (spec #4 in the series). Those three tasks must NOT create that field themselves — a duplicate migration would collide. Each of them opens with a Step 0 that verifies the field exists and blocks if it does not.

**Test command (one alias used throughout, `<UNIQUE>` = a run-specific DB name so concurrent runs do not share `test_reqogniloom`):**

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm -e DB_NAME=reqlo_mcpmod backend-test pytest <ARGS>
```

Referred to below as `PYTEST <ARGS>`.

---

## Spec corrections verified against the live tree

Checked on branch `main` (working tree `chore/archive-implemented-specs-plans`, backend identical):

| Spec claim | Reality | Consequence for this plan |
|---|---|---|
| `MCP_PROTOCOL_VERSION = "2024-11-05"` at `protocol_handler.py:45` | **Correct**, exact line. | none |
| `capabilities: {"tools": {}}` in the `initialize` answer | **Correct**, `protocol_handler.py:453-456`. Also: the handler ignores `params.protocolVersion` entirely — there is no negotiation at all today. | Task 1 adds negotiation, not just a constant bump. |
| `TenantToolRegistry.list_tools()` / `_is_write_tool()` in `tool_registry.py` | **Class name wrong.** The class is `ToolRegistry` (`tool_registry.py:461`). `list_tools()` is at `:604`, `_is_write_tool()` at `:934`. No `TenantToolRegistry` exists anywhere in the repo. | Plan targets `ToolRegistry`. |
| `McpArtifactProvider` "runs as a tool today for `artifact.get`" | **Wrong on both halves.** `McpArtifactProvider` (`backend/diagram/mcp_artifact_provider.py:164`) is **diagram-specific** and is wired only into `diagram/services.py:54` — it is imported by nothing under `mcp_server/`. There is **no `artifact.get` tool** in the registry; only `artifact.get_tree`. | See DECISION below. `resources/read` is built on the real generic Markdown seam (`ExportService.export_markdown`), not on `McpArtifactProvider`. |
| Bugfixes from H1/H4/R4 are "out of scope, tracked as #846" | Two of the three are **already fixed** in `54b09760`: `GET /mcp/` returns 405 for `Accept: text/event-stream` (`views.py:395`), JSON-RPC batch returns a clean 400 (`views.py:290-303`). | Nothing to do; plan does not touch them. |
| MCP SDK backwards compatibility | **No MCP SDK is used.** `backend/requirements.txt` has no MCP library; `frontend/package.json` has none. The server is hand-rolled JSON-RPC. Compatibility is therefore purely a *client*-side concern (Claude Code, OpenCode, the Antigravity plugin under `dist/plugins/`). | Version negotiation (Task 1) is the whole mitigation. No dependency bump needed. |

**DECISION — the Markdown renderer for `resources/read`**

```
context: Spec §4 says resources/read should reuse "the same Markdown renderer McpArtifactProvider
         uses for artifact.get". Neither the tool nor a generic renderer exists; McpArtifactProvider
         renders a *Diagram*, not an artifact.
choice:  Build one shared function application/artifact_markdown.py::render_artifact_markdown(),
         implemented on top of the existing generic exporter ExportService.export_markdown(),
         which already renders any of 7 artifact types to Markdown and already accepts an
         artifact_id filter. resources/read is a thin adapter over it. No tool is created.
alternatives:
  - Wire McpArtifactProvider into MCP — rejected: it only handles Diagram, and the spec's own
    §8 risk (two paths diverging) would be created rather than avoided.
  - Create an artifact.get tool as well — rejected: spec explicitly says artifact.get "stays
    unchanged"; creating it is new surface nobody asked for, and it would grow the manifest
    the spec is trying to shrink.
consequences: One renderer, one caller today, a second caller later (the Dokumentensicht spec's
         read mode consumes render_artifact_markdown directly, not through MCP). Diagram
         artifacts are not resources-readable in this MVP (Artifact.artifact_type has no
         "Diagram" value — diagrams are not Generic-Artifact-Model rows); diagram.get remains
         the access path for them.
```

**DECISION — POST response is always `application/json`, never an SSE stream**

```
context: Spec §3 asks for "Streamable HTTP (response either JSON or SSE depending on Accept)".
choice:  Implement Mcp-Session-Id + MCP-Protocol-Version header semantics, but always answer a
         POST with Content-Type: application/json.
alternatives:
  - Open an SSE stream per POST — rejected: MCP transports §"Sending Messages to the Server"
    point 5 makes JSON a fully compliant answer, and point 2 obliges the client to support it.
    The server has no server-initiated messages to push during a tool call, so the stream would
    carry exactly one event and cost an async generator, a Redis buffer and a resumability story.
consequences: Fully spec-compliant today. If server-initiated progress notifications are ever
         added, the POST handler grows the SSE branch then — the session id minted in Task 3 is
         already the cursor that branch would need.
```

---

## File Structure

```
backend/
  mcp_server/
    protocol_handler.py            MODIFY  version negotiation, capabilities, resources/* + prompts/* routing
    views.py                       MODIFY  MCP-Protocol-Version validation, Mcp-Session-Id response header
    tool_registry.py               MODIFY  scope/tool_groups gates, icd group registration, read-only names,
                                           auth helpers for resources/prompts
    resources.py                   CREATE  resources/list | resources/templates/list | resources/read handlers
    prompts.py                     CREATE  prompts/list | prompts/get handlers
    workspace_scope.py             MODIFY  read-tool classification for icd.get / icd.query / tool.list_groups
    tools/
      icd.py                       CREATE  IcdToolGroup — icd.get, icd.query
      introspection.py             CREATE  IntrospectionToolGroup — tool.list_groups
    tests/
      test_protocol_version.py     CREATE
      test_streamable_http_headers.py CREATE
      test_resources.py            CREATE
      test_prompts.py              CREATE
      test_icd_tool_group.py       CREATE
      test_api_key_scope_gate.py   CREATE
      test_tool_groups_filter.py   CREATE
      test_introspection_tool_group.py CREATE
  application/
    artifact_markdown.py           CREATE  render_artifact_markdown() — shared Markdown seam
    workspace_lookup.py            MODIFY  ENTITY_SPECS["icd"]
    tests/
      test_artifact_markdown.py    CREATE
  auth_tenancy/
    models.py                      MODIFY  ApiKey.tool_groups
    context.py                     MODIFY  IdentityClaims.scope/.tool_groups, AuthContext.scope/.tool_groups
    services/authentication.py     MODIFY  populate the two new claims
    migrations/00NN_apikey_tool_groups.py  CREATE
  rest_api/
    api_key_views.py               MODIFY  accept + return tool_groups
    tests/test_architecture.py     MODIFY  (only if a ratchet ceiling legitimately drops)
docs/
  MCP.md                           MODIFY  scope vs tool_groups, new capabilities, protocol version
  agent-templates/tool-manifest.json  REGENERATE
```

---

## Task 1: Protocol version negotiation

**Files:**
- Modify: `backend/mcp_server/protocol_handler.py:38-45` (constant block), `backend/mcp_server/protocol_handler.py:449-462` (`initialize` branch)
- Test: `backend/mcp_server/tests/test_protocol_version.py`

**Interfaces:**
- Consumes: nothing
- Produces: `MCP_PROTOCOL_VERSION: str`, `SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...]`, `negotiate_protocol_version(requested: Optional[str]) -> str`

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_protocol_version.py`:

```python
"""Protocol-version negotiation (MCP lifecycle, revision 2025-06-18)."""
from __future__ import annotations

from unittest.mock import MagicMock

from mcp_server.protocol_handler import (
    MCP_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    HttpTransportAdapter,
    ProtocolHandler,
    negotiate_protocol_version,
)


def _initialize(protocol_version: str | None) -> dict:
    params: dict = {}
    if protocol_version is not None:
        params["protocolVersion"] = protocol_version
    frame = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}
    import json

    handler = ProtocolHandler(tool_registry=MagicMock())
    adapter = HttpTransportAdapter(body=json.dumps(frame).encode(), headers={})
    return handler.handle(adapter, headers={})


class TestNegotiate:
    def test_latest_is_2025_06_18(self):
        assert MCP_PROTOCOL_VERSION == "2025-06-18"

    def test_supported_set_is_ordered_newest_first(self):
        assert SUPPORTED_PROTOCOL_VERSIONS == (
            "2025-06-18",
            "2025-03-26",
            "2024-11-05",
        )

    def test_supported_request_is_echoed(self):
        assert negotiate_protocol_version("2024-11-05") == "2024-11-05"

    def test_unsupported_request_falls_back_to_latest(self):
        assert negotiate_protocol_version("1.0.0") == "2025-06-18"

    def test_missing_request_falls_back_to_latest(self):
        assert negotiate_protocol_version(None) == "2025-06-18"

    def test_non_string_request_falls_back_to_latest(self):
        assert negotiate_protocol_version(42) == "2025-06-18"


class TestInitializeFrame:
    def test_legacy_client_keeps_its_own_version(self):
        response = _initialize("2024-11-05")
        assert response["result"]["protocolVersion"] == "2024-11-05"

    def test_modern_client_gets_2025_06_18(self):
        response = _initialize("2025-06-18")
        assert response["result"]["protocolVersion"] == "2025-06-18"

    def test_versionless_client_gets_latest(self):
        response = _initialize(None)
        assert response["result"]["protocolVersion"] == "2025-06-18"

    def test_tools_capability_is_still_advertised(self):
        response = _initialize("2025-06-18")
        assert response["result"]["capabilities"]["tools"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_protocol_version.py -v`
Expected: FAIL — `ImportError: cannot import name 'SUPPORTED_PROTOCOL_VERSIONS' from 'mcp_server.protocol_handler'`

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/protocol_handler.py`, replace the constant at line 45:

```python
# Newest revision this server implements. Bumped to 2025-06-18 (Streamable
# HTTP session/version headers, resources + prompts capabilities).
MCP_PROTOCOL_VERSION = "2025-06-18"

# Every revision this server answers on, newest first. A hard constant would
# have broken any client that still speaks 2024-11-05 strictly: the MCP
# lifecycle spec requires the server to echo the client's requested version
# when it supports it, and only to fall back to its own latest otherwise.
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)


def negotiate_protocol_version(requested: Any) -> str:
    """Return the revision to answer *requested* with (MCP lifecycle §Version Negotiation).

    Echoes *requested* when this server supports it, otherwise returns the
    newest revision this server implements. A missing or non-string value is
    treated as "unspecified" and also yields the newest revision.
    """
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return MCP_PROTOCOL_VERSION
```

Replace the `initialize` branch (currently `protocol_handler.py:449-462`) with:

```python
        if method == "initialize":
            response = ErrorFormatter.format_jsonrpc_result(request_id, {
                "protocolVersion": negotiate_protocol_version(
                    params.get("protocolVersion")
                ),
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "ReqogniLoom",
                    "version": "1.0.0"
                }
            })
            adapter.write_response(response)
            return response
```

Add `"MCP_PROTOCOL_VERSION"`, `"SUPPORTED_PROTOCOL_VERSIONS"` and `"negotiate_protocol_version"` to the module's `__all__` list at the bottom of the file.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_protocol_version.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Run the existing protocol suite for regressions**

Run: `PYTEST mcp_server/tests/test_protocol_handler.py mcp_server/tests/test_e2e_mcp.py -q`
Expected: PASS — no test asserts the literal string `"2024-11-05"`; if one does, update it to `MCP_PROTOCOL_VERSION`.

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/protocol_handler.py backend/mcp_server/tests/test_protocol_version.py
git commit -m "feat(mcp): negotiate protocol version, default 2025-06-18"
```

---

## Task 2: `MCP-Protocol-Version` request header validation

**Files:**
- Modify: `backend/mcp_server/views.py:262-276` (start of `McpHttpTransportView.post`)
- Test: `backend/mcp_server/tests/test_streamable_http_headers.py`

**Interfaces:**
- Consumes: `SUPPORTED_PROTOCOL_VERSIONS` (Task 1)
- Produces: `mcp_server.views._reject_unsupported_protocol_version(request) -> Optional[HttpResponse]`

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_streamable_http_headers.py`:

```python
"""Streamable-HTTP header semantics on POST /mcp/ (MCP transports, 2025-06-18)."""
from __future__ import annotations

import json

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def _post(client: Client, frame: dict, **extra: str):
    return client.post(
        "/mcp/",
        data=json.dumps(frame),
        content_type="application/json",
        **extra,
    )


INITIALIZE = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


class TestProtocolVersionHeader:
    def test_absent_header_is_accepted(self, client: Client):
        response = _post(client, INITIALIZE)
        assert response.status_code == 200

    def test_supported_header_is_accepted(self, client: Client):
        response = _post(client, INITIALIZE, HTTP_MCP_PROTOCOL_VERSION="2025-06-18")
        assert response.status_code == 200

    def test_legacy_supported_header_is_accepted(self, client: Client):
        response = _post(client, INITIALIZE, HTTP_MCP_PROTOCOL_VERSION="2024-11-05")
        assert response.status_code == 200

    def test_unsupported_header_is_rejected_with_400(self, client: Client):
        response = _post(client, INITIALIZE, HTTP_MCP_PROTOCOL_VERSION="1.0.0")
        assert response.status_code == 400

    def test_rejection_body_is_a_jsonrpc_error_frame(self, client: Client):
        response = _post(client, INITIALIZE, HTTP_MCP_PROTOCOL_VERSION="1.0.0")
        body = json.loads(response.content)
        assert body["jsonrpc"] == "2.0"
        assert body["error"]["error_code"] == "INVALID_REQUEST"
        assert body["error"]["details"]["supported"] == [
            "2025-06-18",
            "2025-03-26",
            "2024-11-05",
        ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_streamable_http_headers.py -v`
Expected: FAIL — `test_unsupported_header_is_rejected_with_400` gets 200 (header is ignored today).

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/views.py`, add next to the other module-level helpers (after `_jsonrpc_request_id`):

```python
def _reject_unsupported_protocol_version(
    request: HttpRequest,
) -> "HttpResponse | None":
    """Return a 400 frame when the client pins an MCP revision we do not speak.

    MCP transports §"Protocol Version Header": the client MUST send
    ``MCP-Protocol-Version`` on every request after initialization, and the
    server MUST answer an invalid or unsupported value with 400. An *absent*
    header is explicitly fine — the spec tells servers to assume 2025-03-26
    then, which is inside our supported set, so pre-2025-06-18 clients that
    never send the header keep working unchanged.
    """
    from mcp_server.protocol_handler import SUPPORTED_PROTOCOL_VERSIONS

    declared = request.headers.get("MCP-Protocol-Version")
    if not declared or declared in SUPPORTED_PROTOCOL_VERSIONS:
        return None

    error_body = {
        "jsonrpc": "2.0",
        "id": _jsonrpc_request_id(request.body),
        "error": {
            "error_code": "INVALID_REQUEST",
            "message": f"Unsupported MCP protocol version '{declared}'.",
            "details": {"supported": list(SUPPORTED_PROTOCOL_VERSIONS)},
        },
    }
    return HttpResponse(
        json.dumps(error_body),
        content_type="application/json",
        status=400,
    )
```

In `McpHttpTransportView.post`, insert immediately after the `cookie_rejection` block (currently `views.py:266-268`):

```python
        version_rejection = _reject_unsupported_protocol_version(request)
        if version_rejection is not None:
            return version_rejection
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_streamable_http_headers.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/views.py backend/mcp_server/tests/test_streamable_http_headers.py
git commit -m "feat(mcp): reject unsupported MCP-Protocol-Version with 400"
```

---

## Task 3: `Mcp-Session-Id` on the Streamable-HTTP response

**Files:**
- Modify: `backend/mcp_server/views.py` (`McpHttpTransportView.post` return paths, `_apply_cors_headers`)
- Test: `backend/mcp_server/tests/test_streamable_http_headers.py` (extend)

**Interfaces:**
- Consumes: nothing
- Produces: response header `Mcp-Session-Id` on the `initialize` response; `Access-Control-Expose-Headers` advertises it.

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_streamable_http_headers.py`:

```python
class TestSessionIdHeader:
    def test_initialize_response_carries_a_session_id(self, client: Client):
        response = _post(client, INITIALIZE)
        session_id = response.headers.get("Mcp-Session-Id")
        assert session_id
        # MCP transports §Session Management: visible ASCII 0x21..0x7E only.
        assert all(0x21 <= ord(c) <= 0x7E for c in session_id)

    def test_two_initializations_get_distinct_session_ids(self, client: Client):
        first = _post(client, INITIALIZE).headers["Mcp-Session-Id"]
        second = _post(client, INITIALIZE).headers["Mcp-Session-Id"]
        assert first != second

    def test_non_initialize_response_carries_no_session_id(self, client: Client):
        frame = {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}}
        response = _post(client, frame)
        assert "Mcp-Session-Id" not in response.headers

    def test_client_supplied_session_id_is_echoed_not_rejected(self, client: Client):
        frame = {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}}
        response = _post(client, frame, HTTP_MCP_SESSION_ID="abc123")
        # This server does not *require* a session id, so a stale or unknown
        # one must never produce 400/404 (MCP transports §Session Management
        # point 2 makes requiring it optional).
        assert response.status_code == 200

    def test_session_id_is_exposed_to_cors_callers(self, client: Client):
        response = _post(client, INITIALIZE, HTTP_ORIGIN="http://localhost:5173")
        assert "Mcp-Session-Id" in response.headers.get(
            "Access-Control-Expose-Headers", ""
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_streamable_http_headers.py::TestSessionIdHeader -v`
Expected: FAIL — `KeyError: 'Mcp-Session-Id'` / assertion on a missing header.

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/views.py`, add `import uuid` to the imports if it is not already there (`McpSseTransportView` already uses `uuid.uuid4()`, so it is).

Add a module-level helper after `_reject_unsupported_protocol_version`:

```python
def _is_initialize_frame(body: bytes) -> bool:
    """Return whether *body* is a JSON-RPC ``initialize`` request."""
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return False
    return isinstance(parsed, dict) and parsed.get("method") == "initialize"
```

In `McpHttpTransportView.post`, replace the final success return (currently `views.py:377-381`) with:

```python
        http_response = HttpResponse(
            body,
            content_type="application/json",
            status=http_status,
        )
        if _is_initialize_frame(request.body):
            # MCP transports §Session Management: the server MAY assign a
            # session id on the InitializeResult. We mint one so clients get
            # the modern header instead of the legacy ``?session_id=`` query
            # parameter, but we deliberately keep NO server-side state for it:
            # every Streamable-HTTP request re-authenticates via its API key
            # header, so there is nothing a session would additionally prove.
            # Consequence: we never require the id back and never answer 404
            # for an unknown one, which is what the spec permits for servers
            # that do not require sessions.
            # ponytail: stateless session id; bind it to Redis (see
            # sse_pubsub.store_session_api_key) only if server-initiated
            # messages on a POST-opened SSE stream are ever added.
            http_response["Mcp-Session-Id"] = uuid.uuid4().hex
        return http_response
```

In `_apply_cors_headers` (currently `views.py:208`), add the expose-headers line next to the existing CORS headers:

```python
    response["Access-Control-Expose-Headers"] = "Mcp-Session-Id, MCP-Protocol-Version"
```

and extend the allowed request headers so a browser client may send them back — find the `Access-Control-Allow-Headers` assignment in that function and append `, Mcp-Session-Id, MCP-Protocol-Version` to its value.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_streamable_http_headers.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Verify the legacy SSE transport is untouched**

Run: `PYTEST mcp_server/tests/test_e2e_sse_transport.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/views.py backend/mcp_server/tests/test_streamable_http_headers.py
git commit -m "feat(mcp): return Mcp-Session-Id on the initialize response"
```

---

## Task 4: Shared artifact-Markdown renderer

**Files:**
- Create: `backend/application/artifact_markdown.py`
- Test: `backend/application/tests/test_artifact_markdown.py`

**Interfaces:**
- Consumes: `application.artifact_service.ArtifactService.get_artifact(artifact_id: UUID, ctx: AuthContext) -> Artifact`, `application.export_service.ExportService.export_markdown(entity_type: str, workspace_id: UUID|str, ctx: AuthContext, artifact_id: Optional[UUID|str]) -> ExportResult`, `application.export_service.ENTITY_FIELD_SPECS`
- Produces: `application.artifact_markdown.ArtifactMarkdown` (frozen dataclass: `artifact_id: str`, `artifact_type: str`, `workspace_id: str`, `markdown: str`), `application.artifact_markdown.render_artifact_markdown(artifact_id: UUID | str, ctx: AuthContext) -> ArtifactMarkdown`, `application.artifact_markdown.MARKDOWN_RENDERABLE_TYPES: frozenset[str]`

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_artifact_markdown.py`:

```python
"""Shared Markdown renderer for a single Artifact (MCP resources/read seam)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from application.artifact_markdown import (
    MARKDOWN_RENDERABLE_TYPES,
    ArtifactMarkdown,
    render_artifact_markdown,
)
from application.base import NotFoundError


def _ctx():
    ctx = MagicMock()
    ctx.tenant_id = uuid4()
    return ctx


def _artifact(artifact_type: str):
    artifact = MagicMock()
    artifact.id = uuid4()
    artifact.artifact_type = artifact_type
    artifact.workspace_id = uuid4()
    return artifact


class TestRenderableTypes:
    def test_covers_the_seven_exportable_types(self):
        assert MARKDOWN_RENDERABLE_TYPES == frozenset(
            {
                "StakeholderNeed",
                "Requirement",
                "ArchitectureElement",
                "TestCase",
                "Adr",
                "Risk",
                "Issue",
            }
        )


class TestRenderArtifactMarkdown:
    def test_returns_the_exporter_content(self):
        ctx = _ctx()
        artifact = _artifact("Requirement")
        export = MagicMock()
        export.content = "# Requirement Export\n\n## Login\n"

        with patch(
            "application.artifact_markdown.ArtifactService"
        ) as svc_cls, patch(
            "application.artifact_markdown.ExportService"
        ) as export_cls:
            svc_cls.return_value.get_artifact.return_value = artifact
            export_cls.return_value.export_markdown.return_value = export

            result = render_artifact_markdown(artifact.id, ctx)

        assert isinstance(result, ArtifactMarkdown)
        assert result.markdown == "# Requirement Export\n\n## Login\n"
        assert result.artifact_type == "Requirement"
        assert result.artifact_id == str(artifact.id)
        assert result.workspace_id == str(artifact.workspace_id)

    def test_passes_artifact_id_through_to_the_exporter(self):
        ctx = _ctx()
        artifact = _artifact("Adr")

        with patch(
            "application.artifact_markdown.ArtifactService"
        ) as svc_cls, patch(
            "application.artifact_markdown.ExportService"
        ) as export_cls:
            svc_cls.return_value.get_artifact.return_value = artifact
            export_cls.return_value.export_markdown.return_value = MagicMock(content="x")

            render_artifact_markdown(artifact.id, ctx)

        export_cls.return_value.export_markdown.assert_called_once_with(
            entity_type="Adr",
            workspace_id=artifact.workspace_id,
            ctx=ctx,
            artifact_id=artifact.id,
        )

    def test_strips_a_legacy_subtype_suffix(self):
        """Historic rows carry ``TestCase:System`` in artifact_type."""
        ctx = _ctx()
        artifact = _artifact("TestCase:System")

        with patch(
            "application.artifact_markdown.ArtifactService"
        ) as svc_cls, patch(
            "application.artifact_markdown.ExportService"
        ) as export_cls:
            svc_cls.return_value.get_artifact.return_value = artifact
            export_cls.return_value.export_markdown.return_value = MagicMock(content="x")

            result = render_artifact_markdown(artifact.id, ctx)

        assert result.artifact_type == "TestCase"
        assert (
            export_cls.return_value.export_markdown.call_args.kwargs["entity_type"]
            == "TestCase"
        )

    def test_unrenderable_type_raises_not_found(self):
        ctx = _ctx()
        artifact = _artifact("Goal")

        with patch("application.artifact_markdown.ArtifactService") as svc_cls:
            svc_cls.return_value.get_artifact.return_value = artifact

            with pytest.raises(NotFoundError):
                render_artifact_markdown(artifact.id, ctx)

    def test_malformed_id_raises_not_found(self):
        with pytest.raises(NotFoundError):
            render_artifact_markdown("not-a-uuid", _ctx())

    def test_unknown_artifact_propagates_not_found(self):
        ctx = _ctx()
        with patch("application.artifact_markdown.ArtifactService") as svc_cls:
            svc_cls.return_value.get_artifact.side_effect = NotFoundError("nope")

            with pytest.raises(NotFoundError):
                render_artifact_markdown(uuid4(), ctx)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST application/tests/test_artifact_markdown.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'application.artifact_markdown'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/artifact_markdown.py`:

```python
"""Render one Artifact as Markdown — the single seam behind MCP ``resources/read``.

Spec: docs/superpowers/specs/2026-09-03-mcp-modernisierung-design.md §4, §8.

§8 warns that a Markdown path duplicated across a tool handler and a resource
handler will drift. This module is the answer: one function, thin adapters.
It is deliberately built on :class:`~application.export_service.ExportService`,
which already renders every Generic-Artifact-Model type the exporter knows and
already accepts an ``artifact_id`` filter — so this file adds an addressing
scheme (Artifact id -> entity type + workspace) and nothing else.

Diagrams are intentionally out of scope: they are not ``Artifact`` rows, and
``diagram.get`` remains their access path.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.artifact_service import ArtifactService
from application.base import NotFoundError
from application.export_service import ENTITY_FIELD_SPECS, ExportService

#: Artifact types this renderer can produce Markdown for. Derived from the
#: exporter's own field registry so the two cannot drift apart.
MARKDOWN_RENDERABLE_TYPES: frozenset[str] = frozenset(ENTITY_FIELD_SPECS.keys())


@dataclass(frozen=True)
class ArtifactMarkdown:
    """One artifact rendered as a Markdown document."""

    artifact_id: str
    artifact_type: str
    workspace_id: str
    markdown: str


def render_artifact_markdown(
    artifact_id: UUID | str, ctx: AuthContext
) -> ArtifactMarkdown:
    """Return *artifact_id* rendered as Markdown, tenant-scoped via *ctx*.

    Args:
        artifact_id: ``Artifact`` primary key (the generic id, not a domain id).
        ctx: Authenticated caller; supplies the tenant isolation boundary.

    Returns:
        The rendered document plus the addressing metadata a caller needs to
        label it.

    Raises:
        NotFoundError: The id is malformed, names no artifact visible to the
            caller's tenant, or names an artifact type this renderer does not
            cover (e.g. ``Goal``, ``Interview``).
    """
    try:
        parsed_id = UUID(str(artifact_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise NotFoundError(f"Artifact '{artifact_id}' not found") from exc

    artifact = ArtifactService().get_artifact(parsed_id, ctx)

    # Historic rows encode a subtype in the column ("TestCase:System"); the
    # subtype was promoted to a real field long ago, so only the prefix is
    # meaningful for type dispatch.
    entity_type = str(artifact.artifact_type).split(":", 1)[0]
    if entity_type not in MARKDOWN_RENDERABLE_TYPES:
        raise NotFoundError(
            f"Artifact type '{entity_type}' has no Markdown representation"
        )

    export = ExportService().export_markdown(
        entity_type=entity_type,
        workspace_id=artifact.workspace_id,
        ctx=ctx,
        artifact_id=artifact.id,
    )

    return ArtifactMarkdown(
        artifact_id=str(artifact.id),
        artifact_type=entity_type,
        workspace_id=str(artifact.workspace_id),
        markdown=export.content,
    )


__all__ = [
    "ArtifactMarkdown",
    "MARKDOWN_RENDERABLE_TYPES",
    "render_artifact_markdown",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST application/tests/test_artifact_markdown.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/application/artifact_markdown.py backend/application/tests/test_artifact_markdown.py
git commit -m "feat(application): add render_artifact_markdown shared seam"
```

---

## Task 5: `ToolRegistry` auth helper for non-tool methods

**Files:**
- Modify: `backend/mcp_server/tool_registry.py` (new method next to `list_tools`, `tool_registry.py:604`)
- Test: `backend/mcp_server/tests/test_resources.py` (created here, extended in Task 6)

**Interfaces:**
- Consumes: `ToolRegistry._validate_api_key`, `ToolRegistry._resolve_roles`, `mcp_server.tool_registry.McpAuthenticationError`
- Produces: `ToolRegistry.authenticated_context(api_key: str, workspace_id: Optional[str] = None) -> AuthContext` (raises `McpAuthenticationError`)

> `resources/*` and `prompts/*` are protocol methods, not tools, so they cannot go through `dispatch_request`. They still need the exact same identity work (validate key, resolve roles, arm the tenant). This helper is that shared seam — and it keeps the ORM out of `protocol_handler.py`, whose ratchet ceiling is 0.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_resources.py`:

```python
"""MCP resources/* capability — auth seam and handlers."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import McpAuthenticationError, ToolRegistry

pytestmark = pytest.mark.django_db


def _ctx(tenant_id=None):
    return AuthContext(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
    )


class TestAuthenticatedContext:
    def test_invalid_key_raises(self):
        registry = ToolRegistry()
        with patch.object(
            registry, "_validate_api_key", return_value=(None, "invalid_api_key")
        ):
            with pytest.raises(McpAuthenticationError):
                registry.authenticated_context("reqlo_bogus")

    def test_valid_key_returns_resolved_roles(self):
        registry = ToolRegistry()
        partial = _ctx()
        resolved = _ctx(tenant_id=partial.tenant_id)
        with patch.object(
            registry, "_validate_api_key", return_value=(partial, None)
        ), patch.object(registry, "_resolve_roles", return_value=resolved) as resolve:
            result = registry.authenticated_context("reqlo_ok", workspace_id="ws-1")

        assert result is resolved
        resolve.assert_called_once_with(partial, "ws-1")

    def test_tenant_is_armed_and_cleared(self):
        registry = ToolRegistry()
        partial = _ctx()
        with patch.object(
            registry, "_validate_api_key", return_value=(partial, None)
        ), patch.object(
            registry, "_resolve_roles", return_value=partial
        ), patch(
            "persistence.middleware.set_request_tenant"
        ) as arm, patch(
            "persistence.middleware.clear_request_tenant"
        ) as disarm:
            registry.authenticated_context("reqlo_ok")

        arm.assert_called_once_with(partial.tenant_id)
        disarm.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_resources.py -v`
Expected: FAIL — `AttributeError: 'ToolRegistry' object has no attribute 'authenticated_context'`

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/tool_registry.py`, add immediately before `def list_tools(` (line 604):

```python
    def authenticated_context(
        self, api_key: str, workspace_id: Optional[str] = None
    ) -> AuthContext:
        """Return a fully resolved :class:`AuthContext` for *api_key*.

        The identity seam for the MCP protocol methods that are not tool calls
        (``resources/*``, ``prompts/*``): they need the same validate-key /
        resolve-roles work ``dispatch_request`` does, but must not route
        through the tool router. Keeping it here rather than in
        ``protocol_handler`` also keeps ORM access out of that module, whose
        ADR-01 ratchet ceiling is 0.

        The tenant is armed only for the duration of role resolution — the
        caller arms it again around its own reads, exactly like
        :meth:`list_tools` does.

        Raises:
            McpAuthenticationError: The credential is missing or invalid.
        """
        auth_ctx, auth_error = self._validate_api_key(api_key)
        if auth_error or auth_ctx is None:
            raise McpAuthenticationError(auth_error or "invalid_api_key")

        from persistence.middleware import set_request_tenant, clear_request_tenant

        try:
            if auth_ctx.tenant_id is not None:
                set_request_tenant(auth_ctx.tenant_id)
            return self._resolve_roles(auth_ctx, workspace_id)
        finally:
            if auth_ctx.tenant_id is not None:
                clear_request_tenant()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_resources.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Verify the ORM ratchet still holds**

Run: `PYTEST rest_api/tests/test_architecture.py -q`
Expected: PASS — `tool_registry.py` is still at exactly 1 direct-ORM line (the helper adds none).

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_resources.py
git commit -m "feat(mcp): add ToolRegistry.authenticated_context auth seam"
```

---

## Task 6: `resources/*` handlers

**Files:**
- Create: `backend/mcp_server/resources.py`
- Modify: `backend/mcp_server/protocol_handler.py` (`initialize` capabilities + method routing after the `tools/list` branch, `protocol_handler.py:493`)
- Test: `backend/mcp_server/tests/test_resources.py` (extend)

**Interfaces:**
- Consumes: `application.artifact_markdown.render_artifact_markdown(artifact_id, ctx) -> ArtifactMarkdown` (Task 4), `ToolRegistry.authenticated_context(api_key, workspace_id) -> AuthContext` (Task 5), `application.workspace_lookup.resolve_owning_workspace_id`
- Produces: `mcp_server.resources.RESOURCE_URI_SCHEME = "reqogniloom"`, `mcp_server.resources.ARTIFACT_URI_TEMPLATE = "reqogniloom://artifact/{id}"`, `mcp_server.resources.parse_artifact_uri(uri: str) -> Optional[str]`, `mcp_server.resources.list_resource_templates() -> dict`, `mcp_server.resources.list_resources(registry, api_key, params) -> dict`, `mcp_server.resources.read_resource(registry, api_key, params) -> dict`; every one of the three returns either a `result` dict or raises `ResourceError(error_code: str, message: str, details: dict | None)`

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_resources.py`:

```python
from mcp_server.protocol_handler import HttpTransportAdapter, ProtocolHandler
from mcp_server.resources import (
    ARTIFACT_URI_TEMPLATE,
    ResourceError,
    list_resource_templates,
    parse_artifact_uri,
    read_resource,
)


class TestUriParsing:
    def test_template_is_the_documented_scheme(self):
        assert ARTIFACT_URI_TEMPLATE == "reqogniloom://artifact/{id}"

    def test_valid_uri_yields_the_id(self):
        art_id = str(uuid4())
        assert parse_artifact_uri(f"reqogniloom://artifact/{art_id}") == art_id

    def test_foreign_scheme_yields_none(self):
        assert parse_artifact_uri("file:///etc/passwd") is None

    def test_wrong_host_yields_none(self):
        assert parse_artifact_uri(f"reqogniloom://diagram/{uuid4()}") is None

    def test_missing_id_yields_none(self):
        assert parse_artifact_uri("reqogniloom://artifact/") is None

    def test_non_string_yields_none(self):
        assert parse_artifact_uri(None) is None


class TestResourceTemplates:
    def test_lists_the_artifact_template(self):
        result = list_resource_templates()
        templates = result["resourceTemplates"]
        assert len(templates) == 1
        assert templates[0]["uriTemplate"] == ARTIFACT_URI_TEMPLATE
        assert templates[0]["name"] == "artifact"
        assert templates[0]["mimeType"] == "text/markdown"


class TestReadResource:
    def _registry(self, ctx):
        registry = MagicMock()
        registry.authenticated_context.return_value = ctx
        return registry

    def test_missing_uri_is_a_validation_error(self):
        with pytest.raises(ResourceError) as exc:
            read_resource(self._registry(_ctx()), "reqlo_k", {})
        assert exc.value.error_code == "VALIDATION_ERROR"

    def test_unknown_scheme_is_not_found(self):
        with pytest.raises(ResourceError) as exc:
            read_resource(self._registry(_ctx()), "reqlo_k", {"uri": "file:///x"})
        assert exc.value.error_code == "NOT_FOUND"

    def test_valid_uri_returns_markdown_contents(self):
        art_id = str(uuid4())
        rendered = MagicMock()
        rendered.artifact_id = art_id
        rendered.artifact_type = "Requirement"
        rendered.workspace_id = str(uuid4())
        rendered.markdown = "# Requirement Export\n"

        with patch(
            "mcp_server.resources.render_artifact_markdown", return_value=rendered
        ), patch("mcp_server.resources._assert_workspace_read_access"):
            result = read_resource(
                self._registry(_ctx()), "reqlo_k", {"uri": f"reqogniloom://artifact/{art_id}"}
            )

        assert result == {
            "contents": [
                {
                    "uri": f"reqogniloom://artifact/{art_id}",
                    "name": f"Requirement {art_id}",
                    "mimeType": "text/markdown",
                    "text": "# Requirement Export\n",
                }
            ]
        }

    def test_unknown_artifact_is_not_found(self):
        from application.base import NotFoundError

        art_id = str(uuid4())
        with patch(
            "mcp_server.resources.render_artifact_markdown",
            side_effect=NotFoundError("gone"),
        ), patch("mcp_server.resources._assert_workspace_read_access"):
            with pytest.raises(ResourceError) as exc:
                read_resource(
                    self._registry(_ctx()),
                    "reqlo_k",
                    {"uri": f"reqogniloom://artifact/{art_id}"},
                )
        assert exc.value.error_code == "NOT_FOUND"


class TestCapabilityAdvertised:
    def test_initialize_advertises_resources(self):
        import json

        frame = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        handler = ProtocolHandler(tool_registry=MagicMock())
        adapter = HttpTransportAdapter(body=json.dumps(frame).encode(), headers={})
        response = handler.handle(adapter, headers={})
        assert response["result"]["capabilities"]["resources"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_resources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.resources'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/resources.py`:

```python
"""MCP ``resources/*`` capability (spec §4).

A second, standards-native access path onto the artifact Markdown renderer.
It adds no domain logic of its own: every read goes through
``application.artifact_markdown.render_artifact_markdown``, the single shared
function §8 asks for, and this module is one of its two thin adapters.

ADR-01: this file must stay free of direct ORM access — the ratchet ceiling
for ``mcp_server/*.py`` is 0 (see rest_api/tests/test_architecture.py).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from application.artifact_markdown import render_artifact_markdown
from application.base import NotFoundError
from auth_tenancy.context import AuthContext

logger = logging.getLogger(__name__)

#: Custom URI scheme (RFC 3986) for artifacts served as MCP resources.
RESOURCE_URI_SCHEME = "reqogniloom"

#: RFC 6570 template advertised via ``resources/templates/list``.
ARTIFACT_URI_TEMPLATE = f"{RESOURCE_URI_SCHEME}://artifact/{{id}}"

_ARTIFACT_URI_PREFIX = f"{RESOURCE_URI_SCHEME}://artifact/"


class ResourceError(Exception):
    """A resource operation failed with a mappable MCP error code."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details


def parse_artifact_uri(uri: Any) -> Optional[str]:
    """Return the artifact id inside *uri*, or ``None`` if it is not ours.

    Deliberately strict: only the exact ``reqogniloom://artifact/<id>`` shape
    is accepted. Anything else — a ``file://`` URI, another host segment, an
    empty id — is not this server's resource and must surface as NOT_FOUND
    rather than being coerced into a lookup.
    """
    if not isinstance(uri, str) or not uri.startswith(_ARTIFACT_URI_PREFIX):
        return None
    candidate = uri[len(_ARTIFACT_URI_PREFIX):]
    return candidate or None


def list_resource_templates() -> Dict[str, Any]:
    """Return the ``resources/templates/list`` result.

    One template. Artifacts are addressed by id, so there is no meaningful
    concrete listing without a workspace — see :func:`list_resources`.
    """
    return {
        "resourceTemplates": [
            {
                "uriTemplate": ARTIFACT_URI_TEMPLATE,
                "name": "artifact",
                "title": "ReqogniLoom artifact",
                "description": (
                    "One requirement, architecture element, stakeholder need, "
                    "test case, ADR, risk or issue rendered as Markdown. "
                    "{id} is the generic Artifact id (the id the trace graph "
                    "uses), not the domain-entity id."
                ),
                "mimeType": "text/markdown",
            }
        ]
    }


def list_resources(
    registry: Any, api_key: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Return the ``resources/list`` result for one workspace.

    ``workspace_id`` is **required**: an unbounded tenant-wide artifact listing
    would both bypass the workspace read gate and be unbounded in size. Without
    it the caller is pointed at ``resources/templates/list`` instead.
    """
    workspace_id = params.get("workspace_id")
    if not workspace_id:
        raise ResourceError(
            "VALIDATION_ERROR",
            "Parameter 'workspace_id' is required for resources/list. Use "
            "resources/templates/list to discover the URI template, then read "
            "an artifact directly by id.",
        )

    ctx = registry.authenticated_context(api_key, str(workspace_id))
    _assert_workspace_read_access(registry, ctx, workspace_id)

    from application.services import ArtifactService
    from persistence.middleware import set_request_tenant, clear_request_tenant

    try:
        if ctx.tenant_id is not None:
            set_request_tenant(ctx.tenant_id)
        summaries = ArtifactService().list_child_summaries(
            ctx, UUID(str(workspace_id))
        )
        resources = [
            {
                "uri": f"{_ARTIFACT_URI_PREFIX}{row['id']}",
                "name": f"{row['artifact_type']} {row['id']}",
                "mimeType": "text/markdown",
            }
            for row in summaries
        ]
    finally:
        if ctx.tenant_id is not None:
            clear_request_tenant()

    return {"resources": resources}


def read_resource(
    registry: Any, api_key: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Return the ``resources/read`` result for one artifact URI."""
    uri = params.get("uri")
    if not uri:
        raise ResourceError(
            "VALIDATION_ERROR", "Parameter 'uri' is required for resources/read."
        )

    artifact_id = parse_artifact_uri(uri)
    if artifact_id is None:
        raise ResourceError(
            "NOT_FOUND",
            "Resource not found.",
            {"uri": str(uri)},
        )

    ctx = registry.authenticated_context(api_key, params.get("workspace_id"))

    from persistence.middleware import set_request_tenant, clear_request_tenant

    try:
        if ctx.tenant_id is not None:
            set_request_tenant(ctx.tenant_id)
        try:
            rendered = render_artifact_markdown(artifact_id, ctx)
        except NotFoundError:
            raise ResourceError(
                "NOT_FOUND", "Resource not found.", {"uri": str(uri)}
            )
        except Exception:
            # CWE-209: log the detail, hand the caller the static message.
            logger.exception("resources/read failed for uri=%s", uri)
            raise ResourceError("INTERNAL_ERROR", "An internal error occurred.")

        _assert_workspace_read_access(registry, ctx, rendered.workspace_id)
    finally:
        if ctx.tenant_id is not None:
            clear_request_tenant()

    return {
        "contents": [
            {
                "uri": uri,
                "name": f"{rendered.artifact_type} {rendered.artifact_id}",
                "mimeType": "text/markdown",
                "text": rendered.markdown,
            }
        ]
    }


def _assert_workspace_read_access(
    registry: Any, ctx: AuthContext, workspace_id: Any
) -> None:
    """Raise PERMISSION_DENIED unless *ctx* may read in *workspace_id*.

    Mirrors ``ToolRegistry._check_read_rbac``'s contract for read tools whose
    target workspace is resolved from the object rather than a parameter (see
    mcp_server/workspace_scope.py). Tenant isolation alone is not the gate the
    rest of the read surface applies, so the resource path must not be laxer.
    """
    scoped = registry._resolve_roles(ctx, str(workspace_id))
    error = registry._check_read_rbac(scoped, "resources/read")
    if error:
        raise ResourceError("PERMISSION_DENIED", error)


__all__ = [
    "ARTIFACT_URI_TEMPLATE",
    "RESOURCE_URI_SCHEME",
    "ResourceError",
    "list_resource_templates",
    "list_resources",
    "parse_artifact_uri",
    "read_resource",
]
```

In `backend/mcp_server/protocol_handler.py`, extend the `initialize` capabilities dict:

```python
                "capabilities": {
                    "tools": {},
                    # Neither subscribe nor listChanged is implemented; an
                    # empty object is the spec's own "capability present, no
                    # optional features" shape.
                    "resources": {}
                },
```

and add the routing block immediately after the `tools/list` branch (after `protocol_handler.py:509`):

```python
        if method in ("resources/list", "resources/templates/list", "resources/read"):
            from mcp_server.resources import (
                ResourceError,
                list_resource_templates,
                list_resources,
                read_resource,
            )
            from mcp_server.tool_registry import McpAuthenticationError

            try:
                if method == "resources/templates/list":
                    result_data = list_resource_templates()
                elif method == "resources/list":
                    result_data = list_resources(self._registry, api_key, clean_params)
                else:
                    result_data = read_resource(self._registry, api_key, clean_params)
                response = ErrorFormatter.format_jsonrpc_result(request_id, result_data)
            except ResourceError as exc:
                response = ErrorFormatter.format_jsonrpc_error(
                    request_id, exc.error_code, exc.message, exc.details
                )
            except McpAuthenticationError as exc:
                response = ErrorFormatter.format_jsonrpc_error(
                    request_id, "AUTH_FAILED", str(exc)
                )
            except Exception:
                logger.exception("Error handling %s", method)
                response = ErrorFormatter.format_jsonrpc_error(
                    request_id, "INTERNAL_ERROR"
                )
            adapter.write_response(response)
            return response
```

> Note on the error code: the MCP resources page suggests `-32002` for "resource not found". This server already maps `-32002` to `FEATURE_NOT_ENABLED` (`ERROR_CODE_MAP`), and remapping it would silently change the meaning of an existing code for every current client and test. We therefore use the project's own `NOT_FOUND` (`-32004`). The spec wording is SHOULD, not MUST.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_resources.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Verify the ORM ratchet**

Run: `PYTEST rest_api/tests/test_architecture.py -q`
Expected: PASS — `mcp_server/resources.py` contains no `.objects.` / `.unscoped.` line (all ORM lives behind `ArtifactService`).

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/resources.py backend/mcp_server/protocol_handler.py backend/mcp_server/tests/test_resources.py
git commit -m "feat(mcp): add resources/list, resources/read and templates/list"
```

---

## Task 7: `prompts/*` handlers

**Files:**
- Create: `backend/mcp_server/prompts.py`
- Modify: `backend/mcp_server/protocol_handler.py` (`initialize` capabilities + routing block from Task 6)
- Test: `backend/mcp_server/tests/test_prompts.py`

**Interfaces:**
- Consumes: `application.prompt_slots.get_prompt_slots() -> Dict[str, PromptSlotSpec]` (`PromptSlotSpec(name, default_content, data_variables)`), `application.prompt_resolver.try_resolve_template_content(slot_name, ctx, workspace_id) -> Optional[str]`, `application.prompt_template_versioning.list_active_templates(tenant_id=..., workspace_id=...) -> list[PromptTemplate]`, `ToolRegistry.authenticated_context` (Task 5)
- Produces: `mcp_server.prompts.PromptError` (same shape as `ResourceError`), `mcp_server.prompts.list_prompts(registry, api_key, params) -> dict`, `mcp_server.prompts.get_prompt(registry, api_key, params) -> dict`

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_prompts.py`:

```python
"""MCP prompts/* capability (spec §4)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.prompts import PromptError, get_prompt, list_prompts
from mcp_server.protocol_handler import HttpTransportAdapter, ProtocolHandler

pytestmark = pytest.mark.django_db


def _ctx():
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
    )


def _registry(ctx):
    registry = MagicMock()
    registry.authenticated_context.return_value = ctx
    return registry


class _Slot:
    def __init__(self, name, data_variables):
        self.name = name
        self.default_content = "body"
        self.data_variables = data_variables


class TestListPrompts:
    def test_slots_become_prompts_with_arguments(self):
        slots = {
            "need_to_sysreq": _Slot(
                "need_to_sysreq", ("need_title", "need_description")
            )
        }
        with patch("mcp_server.prompts.get_prompt_slots", return_value=slots), patch(
            "mcp_server.prompts.list_active_templates", return_value=[]
        ):
            result = list_prompts(_registry(_ctx()), "reqlo_k", {})

        assert result["prompts"] == [
            {
                "name": "need_to_sysreq",
                "title": "need_to_sysreq",
                "description": (
                    "ReqogniLoom prompt template 'need_to_sysreq'. Manage it "
                    "with the prompt_template.* tools."
                ),
                "arguments": [
                    {"name": "need_title", "description": "Template variable 'need_title'.", "required": True},
                    {"name": "need_description", "description": "Template variable 'need_description'.", "required": True},
                ],
            }
        ]

    def test_tenant_rows_without_a_factory_slot_are_included(self):
        row = MagicMock()
        row.name = "custom_slot"
        with patch("mcp_server.prompts.get_prompt_slots", return_value={}), patch(
            "mcp_server.prompts.list_active_templates", return_value=[row]
        ):
            result = list_prompts(_registry(_ctx()), "reqlo_k", {})

        assert [p["name"] for p in result["prompts"]] == ["custom_slot"]

    def test_names_are_deduplicated_and_sorted(self):
        row = MagicMock()
        row.name = "need_to_sysreq"
        slots = {"zzz_last": _Slot("zzz_last", ()), "need_to_sysreq": _Slot("need_to_sysreq", ())}
        with patch("mcp_server.prompts.get_prompt_slots", return_value=slots), patch(
            "mcp_server.prompts.list_active_templates", return_value=[row]
        ):
            result = list_prompts(_registry(_ctx()), "reqlo_k", {})

        assert [p["name"] for p in result["prompts"]] == ["need_to_sysreq", "zzz_last"]


class TestGetPrompt:
    def test_missing_name_is_a_validation_error(self):
        with pytest.raises(PromptError) as exc:
            get_prompt(_registry(_ctx()), "reqlo_k", {})
        assert exc.value.error_code == "VALIDATION_ERROR"

    def test_unknown_name_is_not_found(self):
        with patch("mcp_server.prompts.try_resolve_template_content", return_value=None):
            with pytest.raises(PromptError) as exc:
                get_prompt(_registry(_ctx()), "reqlo_k", {"name": "nope"})
        assert exc.value.error_code == "NOT_FOUND"

    def test_known_name_returns_a_user_message(self):
        with patch(
            "mcp_server.prompts.try_resolve_template_content",
            return_value="Derive requirements from {need_title}.",
        ), patch("mcp_server.prompts.get_prompt_slots", return_value={}):
            result = get_prompt(
                _registry(_ctx()), "reqlo_k", {"name": "need_to_sysreq"}
            )

        assert result == {
            "description": "ReqogniLoom prompt template 'need_to_sysreq'.",
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": "Derive requirements from {need_title}.",
                    },
                }
            ],
        }

    def test_arguments_are_substituted_into_the_body(self):
        with patch(
            "mcp_server.prompts.try_resolve_template_content",
            return_value="Derive from {need_title} / {need_description}.",
        ), patch("mcp_server.prompts.get_prompt_slots", return_value={}):
            result = get_prompt(
                _registry(_ctx()),
                "reqlo_k",
                {
                    "name": "need_to_sysreq",
                    "arguments": {"need_title": "Login", "need_description": "SSO"},
                },
            )

        assert (
            result["messages"][0]["content"]["text"]
            == "Derive from Login / SSO."
        )

    def test_unknown_placeholders_survive_substitution(self):
        with patch(
            "mcp_server.prompts.try_resolve_template_content",
            return_value="Keep {unfilled} intact.",
        ), patch("mcp_server.prompts.get_prompt_slots", return_value={}):
            result = get_prompt(
                _registry(_ctx()),
                "reqlo_k",
                {"name": "x", "arguments": {"other": "1"}},
            )

        assert result["messages"][0]["content"]["text"] == "Keep {unfilled} intact."


class TestCapabilityAdvertised:
    def test_initialize_advertises_prompts(self):
        frame = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        handler = ProtocolHandler(tool_registry=MagicMock())
        adapter = HttpTransportAdapter(body=json.dumps(frame).encode(), headers={})
        response = handler.handle(adapter, headers={})
        assert response["result"]["capabilities"]["prompts"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.prompts'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/prompts.py`:

```python
"""MCP ``prompts/*`` capability (spec §4).

The read/use path onto the existing versioned ``PromptTemplate`` system. The
``prompt_template.*`` tool group stays the *management* path (create/update,
admin-gated) — this capability neither replaces nor duplicates it: both read
through ``application.prompt_resolver``.

ADR-01: no direct ORM access in this file (ratchet ceiling 0 for
``mcp_server/*.py``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from application.prompt_resolver import try_resolve_template_content
from application.prompt_slots import get_prompt_slots
from application.prompt_template_versioning import list_active_templates

logger = logging.getLogger(__name__)


class PromptError(Exception):
    """A prompt operation failed with a mappable MCP error code."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details


def _argument_specs(data_variables: Any) -> list:
    """Map a slot's ``data_variables`` onto MCP prompt ``arguments``.

    All of them are marked required: a prompt body renders every one of its
    placeholders, so omitting one leaves a literal ``{placeholder}`` in the
    text the client hands to a model.
    """
    return [
        {
            "name": variable,
            "description": f"Template variable '{variable}'.",
            "required": True,
        }
        for variable in (data_variables or ())
    ]


def list_prompts(
    registry: Any, api_key: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Return the ``prompts/list`` result.

    The union of the factory slot registry and the tenant's own active rows —
    a tenant may have published a template under a name that has no factory
    default, and that name is just as usable.
    """
    workspace_id = params.get("workspace_id")
    ctx = registry.authenticated_context(api_key, workspace_id)

    from persistence.middleware import set_request_tenant, clear_request_tenant

    slots = get_prompt_slots()
    try:
        if ctx.tenant_id is not None:
            set_request_tenant(ctx.tenant_id)
        rows = list_active_templates(
            tenant_id=ctx.tenant_id,
            workspace_id=UUID(str(workspace_id)) if workspace_id else None,
        )
    except Exception:
        logger.exception("prompts/list: template lookup failed")
        raise PromptError("INTERNAL_ERROR", "An internal error occurred.")
    finally:
        if ctx.tenant_id is not None:
            clear_request_tenant()

    names = sorted({*slots.keys(), *(row.name for row in rows)})

    return {
        "prompts": [
            {
                "name": name,
                "title": name,
                "description": (
                    f"ReqogniLoom prompt template '{name}'. Manage it with the "
                    "prompt_template.* tools."
                ),
                "arguments": _argument_specs(
                    getattr(slots.get(name), "data_variables", ())
                ),
            }
            for name in names
        ]
    }


def get_prompt(
    registry: Any, api_key: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Return the ``prompts/get`` result — the effective body as one message."""
    name = params.get("name")
    if not name:
        raise PromptError(
            "VALIDATION_ERROR", "Parameter 'name' is required for prompts/get."
        )

    workspace_id = params.get("workspace_id")
    ctx = registry.authenticated_context(api_key, workspace_id)

    from persistence.middleware import set_request_tenant, clear_request_tenant

    try:
        if ctx.tenant_id is not None:
            set_request_tenant(ctx.tenant_id)
        content = try_resolve_template_content(str(name), ctx, workspace_id)
    except Exception:
        logger.exception("prompts/get: resolution failed for name=%s", name)
        raise PromptError("INTERNAL_ERROR", "An internal error occurred.")
    finally:
        if ctx.tenant_id is not None:
            clear_request_tenant()

    if content is None:
        raise PromptError(
            "NOT_FOUND",
            f"No prompt template named '{name}'.",
            {"name": str(name)},
        )

    arguments = params.get("arguments") or {}
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            # Plain replace, not str.format: a template body legitimately
            # contains braces the caller did not supply, and str.format would
            # raise KeyError on the first of them.
            content = content.replace("{" + str(key) + "}", str(value))

    return {
        "description": f"ReqogniLoom prompt template '{name}'.",
        "messages": [
            {"role": "user", "content": {"type": "text", "text": content}}
        ],
    }


__all__ = ["PromptError", "get_prompt", "list_prompts"]
```

In `backend/mcp_server/protocol_handler.py`, extend the capabilities dict once more:

```python
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {}
                },
```

and add the routing block after the `resources/*` block from Task 6:

```python
        if method in ("prompts/list", "prompts/get"):
            from mcp_server.prompts import PromptError, get_prompt, list_prompts
            from mcp_server.tool_registry import McpAuthenticationError

            try:
                if method == "prompts/list":
                    result_data = list_prompts(self._registry, api_key, clean_params)
                else:
                    result_data = get_prompt(self._registry, api_key, clean_params)
                response = ErrorFormatter.format_jsonrpc_result(request_id, result_data)
            except PromptError as exc:
                response = ErrorFormatter.format_jsonrpc_error(
                    request_id, exc.error_code, exc.message, exc.details
                )
            except McpAuthenticationError as exc:
                response = ErrorFormatter.format_jsonrpc_error(
                    request_id, "AUTH_FAILED", str(exc)
                )
            except Exception:
                logger.exception("Error handling %s", method)
                response = ErrorFormatter.format_jsonrpc_error(
                    request_id, "INTERNAL_ERROR"
                )
            adapter.write_response(response)
            return response
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_prompts.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Verify the resources capability assertion still passes**

Run: `PYTEST mcp_server/tests/test_resources.py mcp_server/tests/test_protocol_version.py rest_api/tests/test_architecture.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/prompts.py backend/mcp_server/protocol_handler.py backend/mcp_server/tests/test_prompts.py
git commit -m "feat(mcp): add prompts/list and prompts/get capability"
```

---

## Task 8: `icd.*` tool group

**Files:**
- Create: `backend/mcp_server/tools/icd.py`
- Modify: `backend/mcp_server/tool_registry.py` (`_READ_ONLY_TOOL_NAMES` at `:204`, `_ensure_groups` registration at `:557`), `backend/application/workspace_lookup.py` (`ENTITY_SPECS`, near line 97), `backend/mcp_server/workspace_scope.py` (`_TOOL_TARGETS` reads block)
- Test: `backend/mcp_server/tests/test_icd_tool_group.py`

**Interfaces:**
- Consumes: `icd.services.get_icd(icd_id: UUID, tenant_id: UUID) -> Icd`, `icd.services.list_icds(workspace_id: UUID, tenant_id: UUID) -> list[Icd]`, `icd.services.list_icd_parameters(icd_version_id: UUID, tenant_id: UUID)`, `mcp_server.tools.base.BaseToolGroup / require_uuid / optional_uuid`
- Produces: `mcp_server.tools.icd.IcdToolGroup` with tools `icd.get`, `icd.query`

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_icd_tool_group.py`:

```python
"""IcdToolGroup — read-only MCP access to Interface Control Documents (spec §5)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.icd import IcdToolGroup


def _ctx():
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=uuid4(),
    )


def _icd():
    version = MagicMock()
    version.id = uuid4()
    version.version_number = 3
    version.direction = "unidirectional"
    version.interface_type = "provides"
    version.semantic_description = "REST contract"
    version.preconditions = ["caller authenticated"]
    version.postconditions = ["200 or 4xx"]
    version.invariants = []

    icd = MagicMock()
    icd.id = uuid4()
    icd.name = "Auth <-> Gateway"
    icd.workspace_id = uuid4()
    icd.source_element_id = uuid4()
    icd.target_element_id = uuid4()
    icd.current_version = version
    return icd


class TestSchemas:
    def test_exactly_two_read_tools(self):
        names = {s["name"] for s in IcdToolGroup().get_tool_schemas()}
        assert names == {"icd.get", "icd.query"}

    def test_get_requires_id(self):
        schema = next(
            s for s in IcdToolGroup().get_tool_schemas() if s["name"] == "icd.get"
        )
        assert schema["inputSchema"]["required"] == ["id"]

    def test_query_requires_workspace_id(self):
        schema = next(
            s for s in IcdToolGroup().get_tool_schemas() if s["name"] == "icd.query"
        )
        assert schema["inputSchema"]["required"] == ["workspace_id"]


class TestIcdGet:
    def test_returns_the_current_version_contract(self):
        icd = _icd()
        with patch("mcp_server.tools.icd.get_icd", return_value=icd):
            result = IcdToolGroup()._handle_get(
                params={"id": str(icd.id)}, auth_context=_ctx(), api_key="reqlo_k"
            )

        assert result.success
        payload = result.data["icd"]
        assert payload["id"] == str(icd.id)
        assert payload["name"] == "Auth <-> Gateway"
        assert payload["version_number"] == 3
        assert payload["direction"] == "unidirectional"
        assert payload["interface_type"] == "provides"
        assert payload["preconditions"] == ["caller authenticated"]

    def test_versionless_icd_reports_nulls_not_a_crash(self):
        icd = _icd()
        icd.current_version = None
        with patch("mcp_server.tools.icd.get_icd", return_value=icd):
            result = IcdToolGroup()._handle_get(
                params={"id": str(icd.id)}, auth_context=_ctx(), api_key="reqlo_k"
            )

        assert result.success
        assert result.data["icd"]["version_number"] is None
        assert result.data["icd"]["preconditions"] == []

    def test_unknown_id_is_not_found(self):
        from icd.models import Icd

        with patch("mcp_server.tools.icd.get_icd", side_effect=Icd.DoesNotExist):
            result = IcdToolGroup()._handle_get(
                params={"id": str(uuid4())}, auth_context=_ctx(), api_key="reqlo_k"
            )

        assert not result.success
        assert result.error_code == "NOT_FOUND"

    def test_internal_error_message_is_masked(self):
        with patch(
            "mcp_server.tools.icd.get_icd",
            side_effect=RuntimeError('relation "icd_icd" does not exist'),
        ):
            result = IcdToolGroup()._handle_get(
                params={"id": str(uuid4())}, auth_context=_ctx(), api_key="reqlo_k"
            )

        assert result.error_code == "INTERNAL_ERROR"
        assert "icd_icd" not in (result.message or "")


class TestIcdQuery:
    def test_lists_workspace_icds(self):
        icds = [_icd(), _icd()]
        with patch("mcp_server.tools.icd.list_icds", return_value=icds):
            result = IcdToolGroup()._handle_query(
                params={"workspace_id": str(uuid4())},
                auth_context=_ctx(),
                api_key="reqlo_k",
            )

        assert result.success
        assert result.data["count"] == 2
        assert len(result.data["icds"]) == 2

    def test_missing_workspace_id_is_a_validation_error(self):
        result = IcdToolGroup()._handle_query(
            params={}, auth_context=_ctx(), api_key="reqlo_k"
        )
        assert result.error_code == "VALIDATION_ERROR"


class TestRegistryWiring:
    def test_both_tools_are_classified_read_only(self):
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        assert registry._is_write_tool("icd.get") is False
        assert registry._is_write_tool("icd.query") is False

    def test_group_is_registered_under_the_icd_prefix(self):
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry._ensure_groups()
        assert isinstance(registry._groups["icd"], IcdToolGroup)

    def test_icd_get_resolves_its_workspace_for_the_read_gate(self):
        from mcp_server.workspace_scope import _TOOL_TARGETS

        assert _TOOL_TARGETS["icd.get"] == (("id", "icd"),)

    def test_icd_entity_is_registered_for_workspace_lookup(self):
        from application.workspace_lookup import ENTITY_SPECS

        assert ENTITY_SPECS["icd"].model_path == "icd.models.Icd"
        assert ENTITY_SPECS["icd"].workspace_field == "workspace_id"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_icd_tool_group.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.tools.icd'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/icd.py`:

```python
"""IcdToolGroup — read-only ICD access over MCP (spec §5).

Closes the REST/MCP parity gap audit finding C6 reported: an AI agent could
not read interface contracts even though the product treats them as a core
artifact. Writes (``icd.create``/``icd.update``) are deliberately out of
scope — the audit asked for read access, and ICD versions are immutable rows
guarded by a DB trigger, so a write path is a materially larger change.

Wraps ``icd.services``, the same ADR-01 facade ``rest_api/icd_views.py`` uses.
No direct ORM access here (ratchet ceiling 0 for mcp_server/tools/icd.py).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from auth_tenancy.context import AuthContext
from icd.models import Icd
from icd.services import get_icd, list_icds

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, optional_uuid, require_uuid

logger = logging.getLogger(__name__)


def _icd_to_dict(icd: Any) -> Dict[str, Any]:
    """Serialise an ICD plus its current contract version for MCP responses.

    ``current_version`` is nullable (an ICD header exists before its first
    version is saved), so every version-derived field degrades to None/[]
    rather than raising.
    """
    version = getattr(icd, "current_version", None)
    return {
        "id": str(icd.id),
        "name": icd.name,
        "workspace_id": str(icd.workspace_id),
        "source_element_id": str(icd.source_element_id),
        "target_element_id": str(icd.target_element_id),
        "version_id": str(version.id) if version else None,
        "version_number": version.version_number if version else None,
        "direction": version.direction if version else None,
        "interface_type": version.interface_type if version else None,
        "semantic_description": version.semantic_description if version else "",
        "preconditions": list(version.preconditions or []) if version else [],
        "postconditions": list(version.postconditions or []) if version else [],
        "invariants": list(version.invariants or []) if version else [],
    }


class IcdToolGroup(BaseToolGroup):
    """Interface Control Document tool group (2 read-only tools)."""

    _TOOL_MAP = {
        "icd.get": "_handle_get",
        "icd.query": "_handle_query",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "icd.get",
            "description": (
                "Fetch one Interface Control Document with its current "
                "contract version — direction, interface type, semantic "
                "description, preconditions, postconditions, invariants "
                "(read-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "UUID of the ICD."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "icd.query",
            "description": (
                "List all Interface Control Documents in a workspace, newest "
                "first, each with its current contract version (read-only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the owning workspace.",
                    },
                },
                "required": ["workspace_id"],
            },
        },
    ]

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """icd.get — fetch one ICD by id (read-only)."""
        icd_id = require_uuid(params, "id")
        try:
            icd = get_icd(icd_id, auth_context.tenant_id)
        except Icd.DoesNotExist:
            return ToolResult.error("NOT_FOUND", "ICD not found")
        except Exception:
            # CWE-209: the raw text can carry SQL/table fragments.
            logger.exception("icd.get failed for id=%s", icd_id)
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

        return ToolResult.ok({"icd": _icd_to_dict(icd)})

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """icd.query — list the ICDs of one workspace (read-only)."""
        workspace_id = optional_uuid(params, "workspace_id")
        if not workspace_id:
            return ToolResult.error(
                "VALIDATION_ERROR",
                "Parameter 'workspace_id' is required for icd.query.",
            )
        try:
            icds = list_icds(workspace_id, auth_context.tenant_id)
        except Exception:
            logger.exception("icd.query failed for workspace=%s", workspace_id)
            return ToolResult.error("INTERNAL_ERROR", "An internal error occurred.")

        return ToolResult.ok(
            {"icds": [_icd_to_dict(i) for i in icds], "count": len(icds)}
        )


__all__ = ["IcdToolGroup"]
```

In `backend/mcp_server/tool_registry.py`:

1. Add to `_READ_ONLY_TOOL_NAMES` (after the `"diagram.query",` entry). `icd.query` is already exempt via the `.query` suffix; `icd.get` is not — `.get` is deliberately not a read-only suffix, so it must be listed by name:

```python
        # Spec §5 (MCP-Modernisierung): REST/MCP parity for ICDs. icd.query is
        # already suffix-exempt; icd.get is not, since ".get" is not a
        # read-only suffix.
        "icd.get",
        "icd.query",
```

2. Add the import inside `_ensure_groups` next to the other tool-group imports:

```python
        from mcp_server.tools.icd import IcdToolGroup
```

3. Add the registration entry to the `register_groups({...})` dict:

```python
            # Spec §5: read-only ICD parity with the REST /api/v1/icds/ surface.
            "icd": IcdToolGroup(),
```

In `backend/application/workspace_lookup.py`, add to `ENTITY_SPECS` after the `"diagram"` entry:

```python
    # Icd carries a local ``workspace_id`` UUID column (icd/models.py:105).
    "icd": EntityWorkspaceSpec("icd.models.Icd"),
```

In `backend/mcp_server/workspace_scope.py`, add to `_TOOL_TARGETS` in the reads block, alphabetically after `"goal.read"`:

```python
    "icd.get": (("id", "icd"),),
```

`icd.query` needs no entry — its `workspace_id` is required by its input schema, which is classification mechanism 1.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_icd_tool_group.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Verify the read-tool classification ratchet and the ORM ratchet**

Run: `PYTEST mcp_server/tests/test_mcp_workspace_scope.py rest_api/tests/test_architecture.py -q`
Expected: PASS — both new tools are classified, `mcp_server/tools/icd.py` has 0 direct-ORM lines.

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tools/icd.py backend/mcp_server/tool_registry.py backend/application/workspace_lookup.py backend/mcp_server/workspace_scope.py backend/mcp_server/tests/test_icd_tool_group.py
git commit -m "feat(mcp): add read-only icd.get and icd.query tool group"
```

---

## Task 9: `ApiKey.tool_groups` field and migration

**Files:**
- Modify: `backend/auth_tenancy/models.py:86-92` (`ApiKey` field block)
- Create: `backend/auth_tenancy/migrations/00NN_apikey_tool_groups.py` (`NN` = next free number; `0012_refreshtoken` is the highest today, so `0013` unless the KI-Vorschlag plan has already taken it)
- Test: `backend/mcp_server/tests/test_tool_groups_filter.py`

**Interfaces:**
- Consumes: nothing
- Produces: `ApiKey.tool_groups: models.JSONField(default=list, blank=True)`

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_tool_groups_filter.py`:

```python
"""ApiKey.tool_groups — catalogue curation, NOT a security boundary (spec §6.2)."""
from __future__ import annotations

import pytest

from auth_tenancy.models import ApiKey

pytestmark = pytest.mark.django_db


class TestField:
    def test_default_is_an_empty_list(self):
        field = ApiKey._meta.get_field("tool_groups")
        assert field.default is list
        assert field.blank is True

    def test_field_is_nullable_free_json(self):
        field = ApiKey._meta.get_field("tool_groups")
        assert field.get_internal_type() == "JSONField"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_tool_groups_filter.py -v`
Expected: FAIL — `FieldDoesNotExist: ApiKey has no field named 'tool_groups'`

- [ ] **Step 3: Write minimal implementation**

In `backend/auth_tenancy/models.py`, add to `ApiKey` after `last_used_at`:

```python
    #: Optional catalogue curation for ``tools/list`` — spec §6.2.
    #:
    #: NOT A SECURITY BOUNDARY. An empty list (the default) means "show every
    #: group", exactly as before this field existed. A non-empty list narrows
    #: only what ``tools/list`` *advertises*, so a client that needs a small
    #: menu pays fewer manifest tokens. ``tools/call`` is completely unaffected:
    #: a key with narrow ``tool_groups`` can still invoke any tool its role and
    #: its ``scope`` allow, simply by naming it. The real security gates are
    #: the RBAC write check and ``scope`` — see ``ToolRegistry.dispatch_request``.
    tool_groups = models.JSONField(default=list, blank=True)
```

Generate the migration:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm backend-test python manage.py makemigrations auth_tenancy --name apikey_tool_groups
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_tool_groups_filter.py -v --create-db`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/auth_tenancy/models.py backend/auth_tenancy/migrations/ backend/mcp_server/tests/test_tool_groups_filter.py
git commit -m "feat(auth): add ApiKey.tool_groups manifest curation field"
```

---

## Task 10: Carry `scope` and `tool_groups` into `AuthContext`

**Files:**
- Modify: `backend/auth_tenancy/context.py:44-66` (`IdentityClaims`), `backend/auth_tenancy/context.py:88-120` (`AuthContext`), `backend/auth_tenancy/services/authentication.py:539-545` (the `IdentityClaims(...)` return), `backend/mcp_server/tool_registry.py:846-855` (the `AuthContext(...)` build in `_validate_api_key`) plus the two `AuthContext(...)` rebuilds in `_resolve_roles` (`tool_registry.py:770-777` and `:893-899`)
- Test: `backend/mcp_server/tests/test_api_key_scope_gate.py`

> **Step 0 (precondition):** run
> `docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . run --rm backend-test python -c "from auth_tenancy.models import ApiKey; print(ApiKey._meta.get_field('scope').choices)"`
> Expected: `[('read', 'Read'), ('write', 'Write')]`. If this raises `FieldDoesNotExist`, STOP — land `docs/superpowers/plans/2026-09-03-ki-vorschlag-als-zustand.md` first. Do not add the field here.

**Interfaces:**
- Consumes: `ApiKey.scope: str`, `ApiKey.tool_groups: list[str]` (Task 9)
- Produces: `IdentityClaims.scope: str = "write"`, `IdentityClaims.tool_groups: tuple[str, ...] = ()`, `AuthContext.scope: str = "write"`, `AuthContext.tool_groups: tuple[str, ...] = ()`

> The lookup deliberately lives in `AuthenticationService.validate_api_key`, which already has the `ApiKey` row in hand. Reading the two columns in `tool_registry.py` instead would add ORM lines to a module whose ratchet ceiling is 1 and would cost a second query per dispatch.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_api_key_scope_gate.py`:

```python
"""ApiKey.scope propagation and enforcement (spec §6.1)."""
from __future__ import annotations

from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod, IdentityClaims


class TestClaimDefaults:
    def test_identity_claims_default_to_write_and_no_curation(self):
        claims = IdentityClaims(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=(),
            auth_method=AuthMethod.API_KEY,
        )
        assert claims.scope == "write"
        assert claims.tool_groups == ()

    def test_auth_context_defaults_to_write_and_no_curation(self):
        ctx = AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            active_roles=(),
            auth_method=AuthMethod.API_KEY,
        )
        assert ctx.scope == "write"
        assert ctx.tool_groups == ()

    def test_auth_context_is_still_frozen(self):
        import dataclasses

        ctx = AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            active_roles=(),
            auth_method=AuthMethod.API_KEY,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.scope = "read"  # type: ignore[misc]


@pytest.mark.django_db
class TestPropagation:
    def _key(self, scope: str, tool_groups: list[str]):
        from auth_tenancy.models import ApiKey
        from auth_tenancy.services.authentication import AuthenticationService
        from persistence.models import Tenant, User

        tenant = Tenant.objects.create(name="t-scope")
        user = User.objects.create(
            email=f"scope-{uuid4()}@example.com", tenant=tenant, is_active=True
        )
        created = AuthenticationService().create_api_key(
            user_id=user.id, tenant_id=tenant.id, name="k"
        )
        ApiKey.unscoped.filter(id=created.api_key_id).update(
            scope=scope, tool_groups=tool_groups
        )
        return created.plaintext

    def test_scope_and_tool_groups_reach_identity_claims(self):
        from auth_tenancy.services.authentication import AuthenticationService

        plaintext = self._key("read", ["requirement", "traceability"])
        claims = AuthenticationService().validate_api_key(plaintext)

        assert claims.scope == "read"
        assert claims.tool_groups == ("requirement", "traceability")

    def test_scope_and_tool_groups_reach_the_registry_auth_context(self):
        from mcp_server.tool_registry import ToolRegistry

        plaintext = self._key("read", ["requirement"])
        ctx, error = ToolRegistry()._validate_api_key(plaintext)

        assert error is None
        assert ctx.scope == "read"
        assert ctx.tool_groups == ("requirement",)

    def test_role_resolution_preserves_scope_and_tool_groups(self):
        from mcp_server.tool_registry import ToolRegistry

        plaintext = self._key("read", ["requirement"])
        registry = ToolRegistry()
        partial, _ = registry._validate_api_key(plaintext)
        resolved = registry._resolve_roles(partial, None)

        assert resolved.scope == "read"
        assert resolved.tool_groups == ("requirement",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_api_key_scope_gate.py -v --create-db`
Expected: FAIL — `AttributeError: 'IdentityClaims' object has no attribute 'scope'`

- [ ] **Step 3: Write minimal implementation**

In `backend/auth_tenancy/context.py`, add to `IdentityClaims` (after `api_key_id`):

```python
    #: Credential scope for API keys: "write" (default) or "read". A "read"
    #: key is refused every write tool at dispatch time, regardless of the
    #: user's RBAC roles.
    scope: str = "write"
    #: MCP tool-group names this credential's manifest is narrowed to. Empty
    #: means "no narrowing". Presentation only — never an execution gate.
    tool_groups: tuple[str, ...] = ()
```

Add the same two fields with the same defaults and docstring entries to `AuthContext` (after `workspace_id`):

```python
    scope: str = "write"
    tool_groups: tuple[str, ...] = ()
```

In `backend/auth_tenancy/services/authentication.py`, extend the `IdentityClaims(...)` return of `validate_api_key`:

```python
        return IdentityClaims(
            user_id=api_key.user_id,
            tenant_id=api_key.user.tenant_id,
            roles=(),  # roles are resolved by AuthorizationService from UserRole.
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
            # Read here, where the row is already loaded: the MCP registry
            # must not query it itself (ADR-01 ratchet, ceiling 1 for
            # tool_registry.py) and would otherwise pay a second query per
            # dispatch.
            scope=api_key.scope or "write",
            tool_groups=tuple(api_key.tool_groups or ()),
        )
```

In `backend/mcp_server/tool_registry.py`, extend all three `AuthContext(...)` constructions (the one in `_validate_api_key` and the two rebuilds in `_resolve_roles`) with:

```python
            scope=claims.scope,          # in _validate_api_key
            tool_groups=claims.tool_groups,
```

```python
            scope=ctx.scope,             # in the two _resolve_roles rebuilds
            tool_groups=ctx.tool_groups,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_api_key_scope_gate.py -v --create-db`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the auth regression suites**

Run: `PYTEST auth_tenancy/ mcp_server/tests/test_mcp_api_key_roles.py mcp_server/tests/test_mcp_rbac_role_matrix.py -q --create-db`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/auth_tenancy/context.py backend/auth_tenancy/services/authentication.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_api_key_scope_gate.py
git commit -m "feat(auth): carry api-key scope and tool_groups into AuthContext"
```

---

## Task 11: `tools/list` filters by `tool_groups` (curation)

**Files:**
- Modify: `backend/mcp_server/tool_registry.py:604-676` (`list_tools`)
- Test: `backend/mcp_server/tests/test_tool_groups_filter.py` (extend)

**Interfaces:**
- Consumes: `AuthContext.tool_groups` (Task 10)
- Produces: `ToolRegistry._filter_by_tool_groups(tools: list[dict], tool_groups: tuple[str, ...]) -> list[dict]`

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_tool_groups_filter.py`:

```python
from mcp_server.tool_registry import ToolRegistry

_TOOLS = [
    {"name": "requirement.get"},
    {"name": "requirement.create"},
    {"name": "traceability.query"},
    {"name": "icd.get"},
    {"name": "tool.list_groups"},
]


class TestFilter:
    def test_empty_curation_is_a_no_op(self):
        assert ToolRegistry()._filter_by_tool_groups(_TOOLS, ()) == _TOOLS

    def test_only_listed_groups_survive(self):
        result = ToolRegistry()._filter_by_tool_groups(_TOOLS, ("requirement",))
        assert [t["name"] for t in result] == [
            "requirement.get",
            "requirement.create",
            "tool.list_groups",
        ]

    def test_multiple_groups_are_unioned(self):
        result = ToolRegistry()._filter_by_tool_groups(_TOOLS, ("icd", "traceability"))
        assert [t["name"] for t in result] == [
            "traceability.query",
            "icd.get",
            "tool.list_groups",
        ]

    def test_introspection_tool_is_never_filtered_out(self):
        result = ToolRegistry()._filter_by_tool_groups(_TOOLS, ("nonexistent",))
        assert [t["name"] for t in result] == ["tool.list_groups"]

    def test_unknown_group_name_does_not_crash(self):
        assert ToolRegistry()._filter_by_tool_groups(_TOOLS, ("nope",)) == [
            {"name": "tool.list_groups"}
        ]

    def test_nameless_entry_is_dropped_not_crashed_on(self):
        assert ToolRegistry()._filter_by_tool_groups([{}], ("requirement",)) == []


@pytest.mark.django_db
class TestListToolsIntegration:
    def test_curated_key_sees_fewer_tools_but_can_still_call_them(self, monkeypatch):
        """Curation narrows the manifest only — dispatch is untouched (spec §6.2)."""
        from unittest.mock import patch
        from uuid import uuid4

        from auth_tenancy.context import AuthContext, AuthMethod

        curated = AuthContext(
            user_id=uuid4(),
            tenant_id=uuid4(),
            active_roles=("admin",),
            auth_method=AuthMethod.API_KEY,
            tool_groups=("icd",),
        )
        registry = ToolRegistry()
        with patch.object(
            registry, "_validate_api_key", return_value=(curated, None)
        ), patch.object(
            registry, "_resolve_list_roles", return_value=("admin",)
        ), patch(
            "persistence.middleware.set_request_tenant"
        ), patch(
            "persistence.middleware.clear_request_tenant"
        ):
            listed = {t["name"] for t in registry.list_tools("reqlo_k")}

        assert "icd.get" in listed
        assert "tool.list_groups" in listed
        assert not any(n.startswith("requirement.") for n in listed)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_tool_groups_filter.py -v --create-db`
Expected: FAIL — `AttributeError: 'ToolRegistry' object has no attribute '_filter_by_tool_groups'`

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/tool_registry.py`, add near `_is_write_tool` (line 934):

```python
    #: Tools that no manifest filter may ever hide. Pure metadata, and the
    #: only way a client can discover which group names exist before it
    #: configures ``ApiKey.tool_groups`` (spec §6.2).
    _ALWAYS_VISIBLE_TOOLS: frozenset[str] = frozenset({"tool.list_groups"})

    def _filter_by_tool_groups(
        self, tools: list[Dict[str, Any]], tool_groups: Tuple[str, ...]
    ) -> list[Dict[str, Any]]:
        """Narrow *tools* to the listed groups — catalogue curation only.

        Spec §6.2: this is **not** a security boundary. It changes what
        ``tools/list`` advertises, never what ``dispatch_request`` executes:
        a key with narrow ``tool_groups`` keeps every capability its role and
        its ``scope`` grant and can call any tool by name. The point is
        context cost — a 99 KB manifest a client only needs a slice of.

        An empty *tool_groups* means "no curation", which is the behaviour
        every key had before the field existed.
        """
        if not tool_groups:
            return tools
        allowed = set(tool_groups)
        result = []
        for tool in tools:
            name = tool.get("name", "")
            if not name:
                continue
            if name in self._ALWAYS_VISIBLE_TOOLS:
                result.append(tool)
                continue
            if name.split(".", 1)[0] in allowed:
                result.append(tool)
        return result
```

In `list_tools`, insert immediately before `return tools` (after the existing write-tool filter block):

```python
            tools = self._filter_by_tool_groups(tools, auth_ctx.tool_groups)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_tool_groups_filter.py -v --create-db`
Expected: PASS (9 tests) — the integration test needs Task 12's `tool.list_groups` to be registered; if it is run before Task 12, temporarily assert only the negative half and re-enable after Task 12.

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_tool_groups_filter.py
git commit -m "feat(mcp): filter tools/list by ApiKey.tool_groups curation"
```

---

## Task 12: `tool.list_groups` introspection tool

**Files:**
- Create: `backend/mcp_server/tools/introspection.py`
- Modify: `backend/mcp_server/tool_registry.py` (`_READ_ONLY_TOOL_NAMES`, `_ensure_groups`), `backend/mcp_server/workspace_scope.py` (`TENANT_SCOPED_READ_TOOLS`)
- Test: `backend/mcp_server/tests/test_introspection_tool_group.py`

**Interfaces:**
- Consumes: `ToolRegistry._groups: Dict[str, Any]`, `BaseToolGroup.get_tool_schemas()`
- Produces: `mcp_server.tools.introspection.IntrospectionToolGroup(registry)` with tool `tool.list_groups`

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_introspection_tool_group.py`:

```python
"""tool.list_groups — always-visible group catalogue (spec §6.2)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.introspection import IntrospectionToolGroup


def _ctx(tool_groups=()):
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
        tool_groups=tool_groups,
    )


def _registry_with(groups: dict):
    registry = MagicMock()
    registry._groups = groups
    return registry


def _group(*names):
    group = MagicMock()
    group.get_tool_schemas.return_value = [{"name": n} for n in names]
    return group


class TestSchema:
    def test_single_tool_named_tool_list_groups(self):
        schemas = IntrospectionToolGroup(_registry_with({})).get_tool_schemas()
        assert [s["name"] for s in schemas] == ["tool.list_groups"]

    def test_description_states_it_is_not_a_security_boundary(self):
        schema = IntrospectionToolGroup(_registry_with({})).get_tool_schemas()[0]
        assert "not a security boundary" in schema["description"].lower()

    def test_takes_no_required_parameters(self):
        schema = IntrospectionToolGroup(_registry_with({})).get_tool_schemas()[0]
        assert schema["inputSchema"].get("required", []) == []


class TestHandler:
    def test_returns_every_group_with_its_tool_count(self):
        registry = _registry_with(
            {"requirement": _group("requirement.get", "requirement.create"),
             "icd": _group("icd.get", "icd.query")}
        )
        result = IntrospectionToolGroup(registry)._handle_list_groups(
            params={}, auth_context=_ctx(), api_key="reqlo_k"
        )

        assert result.success
        assert result.data["groups"] == [
            {"name": "icd", "tool_count": 2, "curated": False},
            {"name": "requirement", "tool_count": 2, "curated": False},
        ]
        assert result.data["total_groups"] == 2

    def test_shared_group_instances_are_counted_per_prefix(self):
        shared = _group("traceability.query", "artifact.search")
        registry = _registry_with({"traceability": shared, "artifact": shared})
        result = IntrospectionToolGroup(registry)._handle_list_groups(
            params={}, auth_context=_ctx(), api_key="reqlo_k"
        )
        assert [g["name"] for g in result.data["groups"]] == [
            "artifact",
            "traceability",
        ]

    def test_curated_flag_reflects_the_callers_tool_groups(self):
        registry = _registry_with({"requirement": _group("requirement.get"),
                                   "icd": _group("icd.get")})
        result = IntrospectionToolGroup(registry)._handle_list_groups(
            params={}, auth_context=_ctx(tool_groups=("icd",)), api_key="reqlo_k"
        )
        by_name = {g["name"]: g for g in result.data["groups"]}
        assert by_name["icd"]["curated"] is True
        assert by_name["requirement"]["curated"] is False

    def test_group_without_schemas_reports_zero(self):
        bare = MagicMock(spec=[])
        registry = _registry_with({"bare": bare})
        result = IntrospectionToolGroup(registry)._handle_list_groups(
            params={}, auth_context=_ctx(), api_key="reqlo_k"
        )
        assert result.data["groups"] == [
            {"name": "bare", "tool_count": 0, "curated": False}
        ]


@pytest.mark.django_db
class TestRegistryWiring:
    def test_is_classified_read_only(self):
        from mcp_server.tool_registry import ToolRegistry

        assert ToolRegistry()._is_write_tool("tool.list_groups") is False

    def test_is_registered_under_the_tool_prefix(self):
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry._ensure_groups()
        assert isinstance(registry._groups["tool"], IntrospectionToolGroup)

    def test_is_classified_as_a_tenant_scoped_read(self):
        from mcp_server.workspace_scope import TENANT_SCOPED_READ_TOOLS

        assert "tool.list_groups" in TENANT_SCOPED_READ_TOOLS

    def test_a_viewer_can_actually_call_it(self):
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        with patch.object(
            registry, "_validate_api_key", return_value=(_ctx(), None)
        ), patch.object(registry, "_resolve_roles", side_effect=lambda c, w: c), patch(
            "persistence.middleware.set_request_tenant"
        ), patch(
            "persistence.middleware.clear_request_tenant"
        ):
            result = registry.dispatch_request(
                tool_name="tool.list_groups", params={}, api_key="reqlo_k"
            )
        assert result.success
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_introspection_tool_group.py -v --create-db`
Expected: FAIL — `ModuleNotFoundError: No module named 'mcp_server.tools.introspection'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/introspection.py`:

```python
"""IntrospectionToolGroup — the MCP tool catalogue's own table of contents.

Spec §6.2: ``ApiKey.tool_groups`` narrows what ``tools/list`` shows, so a
client that has been curated cannot discover from the manifest alone which
group names exist. This tool answers exactly that question and is therefore
excluded from every manifest filter (see
``ToolRegistry._ALWAYS_VISIBLE_TOOLS``): it returns group names and counts,
never a tool's schema, arguments or data.
"""
from __future__ import annotations

from typing import Any, Dict, List

from auth_tenancy.context import AuthContext

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup


class IntrospectionToolGroup(BaseToolGroup):
    """Registry-metadata tool group (1 read-only tool)."""

    _TOOL_MAP = {
        "tool.list_groups": "_handle_list_groups",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "tool.list_groups",
            "description": (
                "List every MCP tool group on this server with its tool count. "
                "Always visible, never filtered — use it to find the group "
                "names accepted by an API key's tool_groups setting. Note that "
                "tool_groups is catalogue curation, not a security boundary: "
                "it changes only which tools tools/list advertises, never "
                "which tools you may call."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    ]

    def __init__(self, registry: Any) -> None:
        """Bind to the ``ToolRegistry`` whose groups this tool reports on."""
        self._registry = registry

    def _handle_list_groups(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """tool.list_groups — every registered prefix with its tool count."""
        curated = set(getattr(auth_context, "tool_groups", ()) or ())
        groups: List[Dict[str, Any]] = []
        for prefix, group in self._registry._groups.items():
            schemas = (
                group.get_tool_schemas()
                if hasattr(group, "get_tool_schemas")
                else []
            )
            groups.append(
                {
                    "name": prefix,
                    "tool_count": len(schemas),
                    # True when this caller's manifest is narrowed to this
                    # group. Purely informational — see the class docstring.
                    "curated": prefix in curated,
                }
            )
        groups.sort(key=lambda g: g["name"])
        return ToolResult.ok({"groups": groups, "total_groups": len(groups)})


__all__ = ["IntrospectionToolGroup"]
```

In `backend/mcp_server/tool_registry.py`:

1. Add to `_READ_ONLY_TOOL_NAMES`:

```python
        # Spec §6.2: registry metadata only, no domain data. ".list_groups" is
        # not a read-only suffix, so the fail-closed default would otherwise
        # write-gate it and hide it from exactly the Viewer-class callers who
        # need it most.
        "tool.list_groups",
```

2. In `_ensure_groups`, add the import and the registration. It must be the LAST entry so the instance can be handed the fully populated registry — but `register_groups` assigns `self._groups` in one shot, so instead register it in a second call right after the main dict:

```python
        from mcp_server.tools.introspection import IntrospectionToolGroup
```

and immediately after the `self.register_groups({...})` call:

```python
        # Registered last and separately: it reports on ``self._groups``, so it
        # must be constructed once that dict already exists. Re-registering
        # rebuilds the router with the introspection prefix included.
        self.register_groups({**self._groups, "tool": IntrospectionToolGroup(self)})
```

In `backend/mcp_server/workspace_scope.py`, add to `TENANT_SCOPED_READ_TOOLS`:

```python
        # Spec §6.2: registry metadata (group names + counts). No workspace,
        # no tenant data, nothing to narrow — deliberately tenant-wide.
        "tool.list_groups",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_introspection_tool_group.py -v --create-db`
Expected: PASS (11 tests)

- [ ] **Step 5: Re-enable and run the Task 11 integration assertion**

Run: `PYTEST mcp_server/tests/test_tool_groups_filter.py mcp_server/tests/test_mcp_workspace_scope.py rest_api/tests/test_architecture.py -q --create-db`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tools/introspection.py backend/mcp_server/tool_registry.py backend/mcp_server/workspace_scope.py backend/mcp_server/tests/test_introspection_tool_group.py
git commit -m "feat(mcp): add always-visible tool.list_groups introspection tool"
```

---

## Task 13: `scope="read"` enforcement in `tools/list` and `dispatch_request`

**Files:**
- Modify: `backend/mcp_server/tool_registry.py` (`list_tools` write-filter block at `:659-676`, `dispatch_request` between Step 2b and Step 3 at `:733-747`)
- Test: `backend/mcp_server/tests/test_api_key_scope_gate.py` (extend)

> **Step 0 (precondition):** same check as Task 10. `AuthContext.scope` must already carry the value. If Task 10 has not landed, this task cannot start.

**Interfaces:**
- Consumes: `AuthContext.scope` (Task 10), `ToolRegistry._is_write_tool` (existing)
- Produces: `ToolRegistry._is_read_scoped(ctx: AuthContext) -> bool`

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_api_key_scope_gate.py`:

```python
from unittest.mock import patch

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tool_registry import ToolRegistry


def _scoped_ctx(scope: str, roles=("admin",)):
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=roles,
        auth_method=AuthMethod.API_KEY,
        scope=scope,
    )


class TestReadScopePredicate:
    def test_read_scope_is_detected(self):
        assert ToolRegistry()._is_read_scoped(_scoped_ctx("read")) is True

    def test_write_scope_is_not(self):
        assert ToolRegistry()._is_read_scoped(_scoped_ctx("write")) is False

    def test_case_and_whitespace_are_normalised(self):
        assert ToolRegistry()._is_read_scoped(_scoped_ctx(" READ ")) is True

    def test_unknown_value_is_not_read_scoped(self):
        # Fail-open on scope is correct here: scope only ever *adds* a
        # restriction on top of RBAC, and an unrecognised value must not
        # silently lock a working key out of its write tools.
        assert ToolRegistry()._is_read_scoped(_scoped_ctx("banana")) is False


@pytest.mark.django_db
class TestDispatchGate:
    def _registry_with(self, ctx):
        registry = ToolRegistry()
        registry._ensure_groups()
        return registry

    def _dispatch(self, registry, ctx, tool_name, params=None):
        with patch.object(
            registry, "_validate_api_key", return_value=(ctx, None)
        ), patch.object(
            registry, "_resolve_roles", side_effect=lambda c, w: c
        ), patch(
            "persistence.middleware.set_request_tenant"
        ), patch(
            "persistence.middleware.clear_request_tenant"
        ):
            return registry.dispatch_request(
                tool_name=tool_name, params=params or {}, api_key="reqlo_k"
            )

    def test_read_key_is_denied_a_write_tool(self):
        ctx = _scoped_ctx("read")
        registry = self._registry_with(ctx)
        result = self._dispatch(registry, ctx, "requirement.create")

        assert not result.success
        assert result.error_code == "PERMISSION_DENIED"
        assert "read" in (result.message or "").lower()

    def test_read_key_is_denied_even_as_a_tenant_admin(self):
        """scope outranks every RBAC exemption (bootstrap, tenant-admin)."""
        ctx = _scoped_ctx("read")
        registry = self._registry_with(ctx)
        with patch.object(registry, "_is_tenant_admin_exempt", return_value=True):
            result = self._dispatch(
                registry, ctx, "user.assign_role", {"user_id": str(ctx.user_id), "role": "admin"}
            )
        assert result.error_code == "PERMISSION_DENIED"

    def test_read_key_may_still_call_a_read_tool(self):
        ctx = _scoped_ctx("read")
        registry = self._registry_with(ctx)
        result = self._dispatch(registry, ctx, "tool.list_groups")
        assert result.success

    def test_unknown_tool_still_reports_unknown_tool_not_permission_denied(self):
        ctx = _scoped_ctx("read")
        registry = self._registry_with(ctx)
        result = self._dispatch(registry, ctx, "does.not.exist")
        assert result.error_code == "UNKNOWN_TOOL"

    def test_write_key_is_unaffected(self):
        ctx = _scoped_ctx("write")
        registry = self._registry_with(ctx)
        result = self._dispatch(registry, ctx, "tool.list_groups")
        assert result.success


@pytest.mark.django_db
class TestListGate:
    def test_read_key_sees_no_write_tools(self):
        ctx = _scoped_ctx("read")
        registry = ToolRegistry()
        with patch.object(
            registry, "_validate_api_key", return_value=(ctx, None)
        ), patch.object(
            registry, "_resolve_list_roles", return_value=("admin",)
        ), patch(
            "persistence.middleware.set_request_tenant"
        ), patch(
            "persistence.middleware.clear_request_tenant"
        ):
            listed = [t["name"] for t in registry.list_tools("reqlo_k")]

        assert "requirement.create" not in listed
        assert "requirement.get" in listed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_api_key_scope_gate.py -v --create-db`
Expected: FAIL — `AttributeError: 'ToolRegistry' object has no attribute '_is_read_scoped'`

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/tool_registry.py`, add next to `_is_write_tool`:

```python
    #: The one credential scope that removes write access. Any other value —
    #: including an unrecognised one — leaves the caller's RBAC roles as the
    #: sole authority, so a typo in the column cannot lock out a working key.
    _READ_ONLY_SCOPE = "read"

    def _is_read_scoped(self, ctx: AuthContext) -> bool:
        """Return whether *ctx*'s credential is restricted to reads (spec §6.1).

        Unlike ``tool_groups`` (presentation only) this **is** a security
        boundary: it is enforced in ``dispatch_request`` on top of, and
        independently of, the RBAC gate — including on the paths that bypass
        RBAC (``_is_bootstrap_candidate``, ``_is_tenant_admin_exempt``). A
        read-scoped key must not be able to write, no matter how privileged
        the human behind it is.
        """
        scope = getattr(ctx, "scope", "") or ""
        return scope.strip().lower() == self._READ_ONLY_SCOPE
```

In `list_tools`, replace the write-filter condition so a read-scoped key is filtered even when it holds write roles. Change:

```python
            if not can_write:
```

to:

```python
            # spec §6.1: a read-scoped credential is filtered exactly like a
            # role-less Viewer, because dispatch_request will refuse those
            # tools anyway — advertising them would misdescribe the surface.
            if not can_write or self._is_read_scoped(auth_ctx):
```

and inside that block, drop the tenant-admin exemption when the reason is the scope:

```python
                read_scoped = self._is_read_scoped(auth_ctx)
                tools = [
                    t
                    for t in tools
                    if not self._is_write_tool(t.get("name", ""))
                    or (
                        not read_scoped
                        and self._is_tenant_admin_exempt(t.get("name", ""), auth_ctx)
                    )
                ]
```

In `dispatch_request`, insert between Step 2b (the `route_error` check) and Step 3:

```python
            # --- Step 2c: credential scope gate (spec §6.1) ---
            # Placed after the existence check so an unknown name still yields
            # UNKNOWN_TOOL, and before the RBAC gate so it applies even to the
            # callers RBAC exempts (bootstrap, tenant admin). Unlike
            # ``tool_groups`` this is a real boundary: it refuses execution,
            # not just visibility.
            if self._is_write_tool(tool_name) and self._is_read_scoped(auth_ctx):
                return ToolResult.error(
                    "PERMISSION_DENIED",
                    f"Tool '{tool_name}' is a write tool and this API key has "
                    f"scope 'read'. Use a key with scope 'write'.",
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST mcp_server/tests/test_api_key_scope_gate.py -v --create-db`
Expected: PASS (16 tests)

- [ ] **Step 5: Run the RBAC regression suites**

Run: `PYTEST mcp_server/tests/test_mcp_rbac_role_matrix.py mcp_server/tests/test_mcp_api_key_roles.py mcp_server/tests/test_permissions_tool_group.py -q --create-db`
Expected: PASS — no existing test creates a key with `scope="read"`, so the default `"write"` keeps every current expectation intact.

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_api_key_scope_gate.py
git commit -m "feat(mcp): enforce ApiKey.scope=read in tools/list and dispatch"
```

---

## Task 14: Expose `tool_groups` on the API-key REST surface

**Files:**
- Modify: `backend/rest_api/api_key_views.py` (the `create` and `list`/`retrieve` actions)
- Test: `backend/rest_api/tests/test_api_key_tool_groups.py`

**Interfaces:**
- Consumes: `ApiKey.tool_groups` (Task 9)
- Produces: `POST /api/v1/api-keys/` accepts `tool_groups: list[str]`; `GET /api/v1/api-keys/` and `GET /api/v1/api-keys/<pk>/` return it.

- [ ] **Step 1: Write the failing test**

Create `backend/rest_api/tests/test_api_key_tool_groups.py`:

```python
"""tool_groups on the API-key REST surface (spec §6.2)."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestCreate:
    def test_default_is_an_empty_list(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/api-keys/", {"name": "plain"}, format="json"
        )
        assert response.status_code == 201
        assert response.data["tool_groups"] == []

    def test_supplied_groups_are_persisted(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/api-keys/",
            {"name": "curated", "tool_groups": ["requirement", "icd"]},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["tool_groups"] == ["requirement", "icd"]

    def test_non_list_is_rejected(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/api-keys/",
            {"name": "bad", "tool_groups": "requirement"},
            format="json",
        )
        assert response.status_code == 400

    def test_non_string_entries_are_rejected(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/api-keys/",
            {"name": "bad", "tool_groups": [1, 2]},
            format="json",
        )
        assert response.status_code == 400


class TestList:
    def test_listing_echoes_tool_groups(self, authenticated_client):
        authenticated_client.post(
            "/api/v1/api-keys/",
            {"name": "curated", "tool_groups": ["icd"]},
            format="json",
        )
        response = authenticated_client.get("/api/v1/api-keys/")
        assert response.status_code == 200
        rows = response.data["results"] if "results" in response.data else response.data
        assert any(row["tool_groups"] == ["icd"] for row in rows)
```

> If `authenticated_client` is not the fixture name used by the existing `rest_api` tests, open `backend/rest_api/tests/conftest.py` and use the fixture that yields a Bearer-authenticated DRF `APIClient` for a role-holding user; the assertions above do not depend on which one it is.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST rest_api/tests/test_api_key_tool_groups.py -v --create-db`
Expected: FAIL — `KeyError: 'tool_groups'` on the create response.

- [ ] **Step 3: Write minimal implementation**

In `backend/rest_api/api_key_views.py`:

1. Add a module-level validator:

```python
def _parse_tool_groups(raw: Any) -> list[str]:
    """Validate and normalise the optional ``tool_groups`` request field.

    Spec §6.2 — catalogue curation, NOT a security boundary. A key with
    narrow tool_groups sees a smaller ``tools/list`` manifest and keeps every
    capability its role and its ``scope`` grant: ``tools/call`` is unaffected.
    Use ``scope="read"`` when you actually want to take write access away.

    Raises:
        ValidationError: The value is not a list of non-empty strings.
    """
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(
        isinstance(entry, str) and entry.strip() for entry in raw
    ):
        raise ValidationError(
            "tool_groups must be a list of group-name strings, e.g. "
            '["requirement", "traceability"]. It filters what tools/list '
            "advertises only — it does not restrict which tools may be "
            "called. Use scope='read' for that."
        )
    return [entry.strip() for entry in raw]
```

Import `ValidationError` from `application.base` if it is not already imported in that module, and `Any` from `typing`.

2. In the `create` action, parse the field before creating the key and persist it on the created row (the existing code calls `AuthenticationService().create_api_key(...)`; add the update immediately after, mirroring how the view already reads back metadata):

```python
        tool_groups = _parse_tool_groups(request.data.get("tool_groups"))
        ...  # existing create_api_key(...) call, result bound as `created`
        if tool_groups:
            ApiKey.unscoped.filter(id=created.api_key_id).update(
                tool_groups=tool_groups
            )
```

3. Add `"tool_groups"` to the metadata dict every action returns (create, list, retrieve) — the view builds these dicts inline; add `"tool_groups": list(key.tool_groups or [])` next to `"name"` in each, and `"tool_groups": tool_groups` in the create response.

> `api_key_views.py` is not on the ADR-01 model-import allowlist (`MODEL_IMPORT_ALLOWLIST` in `rest_api/tests/test_architecture.py` lists only `icd_views.py`, `diagram_views.py`, `diagram_canvas_views.py`, `serializers.py`) and its ORM ceiling is 0. If the implementation above trips `test_no_new_direct_orm_access` or `test_model_import_only_where_allowlisted`, move the two lines into `auth_tenancy/services/authentication.py` as a `set_tool_groups(api_key_id: UUID, tool_groups: list[str]) -> None` service function and call that instead. Do **not** raise a ratchet ceiling.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTEST rest_api/tests/test_api_key_tool_groups.py -v --create-db`
Expected: PASS (5 tests)

- [ ] **Step 5: Verify the ratchet**

Run: `PYTEST rest_api/tests/test_architecture.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/rest_api/api_key_views.py backend/rest_api/tests/test_api_key_tool_groups.py
git commit -m "feat(api): accept and return tool_groups on api-key endpoints"
```

---

## Task 15: Regenerate the tool manifest and document the new surface

**Files:**
- Modify: `docs/agent-templates/tool-manifest.json` (regenerated, not hand-edited)
- Modify: `docs/MCP.md` (if absent, create it at that path)
- Test: `backend/mcp_server/tests/test_export_tool_manifest.py` (existing — must stay green)

**Interfaces:**
- Consumes: everything above
- Produces: a manifest containing `icd.get`, `icd.query`, `tool.list_groups`

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_export_tool_manifest.py`:

```python
class TestNewToolsInManifest:
    def test_icd_tools_are_present(self):
        from mcp_server.management.commands.export_tool_manifest import build_manifest

        names = {t["name"] for t in build_manifest()["tools"]}
        assert {"icd.get", "icd.query"} <= names

    def test_introspection_tool_is_present(self):
        from mcp_server.management.commands.export_tool_manifest import build_manifest

        names = {t["name"] for t in build_manifest()["tools"]}
        assert "tool.list_groups" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST mcp_server/tests/test_export_tool_manifest.py -v`
Expected: PASS if Tasks 8 and 12 are already merged; FAIL with a missing name otherwise. If it fails, Task 8/12 is incomplete — fix there, not here.

- [ ] **Step 3: Regenerate the manifest**

Run:

```bash
docker compose -f deploy/docker-compose.yml -f testing/docker-compose.test.yml --project-directory . \
  run --rm backend-test python manage.py export_tool_manifest
```

- [ ] **Step 4: Document the new surface**

Edit `docs/MCP.md` (create it if it does not exist) and add these sections verbatim:

```markdown
## Protokollversion

Der Server implementiert MCP-Revision **2025-06-18** und verhandelt abwärts:
Fordert ein Client in `initialize` eine Revision aus `2025-06-18`, `2025-03-26`
oder `2024-11-05` an, antwortet der Server mit **genau dieser** Revision. Bei
jeder anderen Anforderung — oder ohne Angabe — antwortet er mit `2025-06-18`.
Ein Client, der weiterhin strikt `2024-11-05` spricht, funktioniert unverändert.

Über HTTP darf der Client ab `initialize` den Header
`MCP-Protocol-Version: <revision>` mitsenden. Ein **nicht unterstützter** Wert
wird mit HTTP 400 abgelehnt; ein **fehlender** Header ist ausdrücklich erlaubt.

Die `initialize`-Antwort trägt einen `Mcp-Session-Id`-Header. Der Server
*verlangt* ihn nicht zurück und terminiert Sessions nicht — jede Anfrage
authentifiziert sich ohnehin über ihren API-Key-Header. Ein unbekannter oder
alter Wert führt daher nie zu 400 oder 404.

Der Legacy-SSE-Transport (`GET /mcp/sse/` plus `POST /mcp/messages/?session_id=`)
bleibt unverändert bestehen.

## Capabilities

| Capability | Methoden |
|---|---|
| `tools` | `tools/list`, `tools/call` |
| `resources` | `resources/list`, `resources/templates/list`, `resources/read` |
| `prompts` | `prompts/list`, `prompts/get` |

`resources/read` liest ein Artefakt als Markdown unter der URI
`reqogniloom://artifact/{id}` — `{id}` ist die generische `Artifact`-ID (die ID,
mit der auch der Trace-Graph arbeitet), nicht die Domain-Entity-ID. Unterstützte
Typen: StakeholderNeed, Requirement, ArchitectureElement, TestCase, Adr, Risk,
Issue. Diagramme sind bewusst nicht dabei — dafür bleibt `diagram.get` der Weg.
`resources/list` verlangt `workspace_id`.

`prompts/*` ist der **Lese-/Nutzungspfad** auf das versionierte
PromptTemplate-System. Anlegen und Ändern bleibt bei der Tool-Gruppe
`prompt_template.*` (Admin-Gate).

## API-Key: `scope` vs. `tool_groups`

Zwei Felder, die leicht verwechselt werden — sie tun bewusst Verschiedenes:

| Feld | Wirkung auf `tools/list` | Wirkung auf `tools/call` | Sicherheitsgrenze? |
|---|---|---|---|
| `scope="read"` | Write-Tools verschwinden | Write-Tools werden mit `PERMISSION_DENIED` **abgelehnt** | **Ja** |
| `tool_groups=[...]` | Nur die gelisteten Gruppen erscheinen | **Keine** — jedes erlaubte Tool bleibt aufrufbar | **Nein** |

`tool_groups` ist reine Katalog-Kuration: weniger Manifest-Tokens im Kontext
eines Clients, der nur einen Ausschnitt braucht. Ein Key mit engen
`tool_groups` verliert **keine** Fähigkeit — er bekommt nur ein kleineres Menü
angezeigt und kann jedes andere erlaubte Tool weiterhin direkt beim Namen
aufrufen. Wer Schreibrechte tatsächlich entziehen will, setzt `scope="read"`.

`tool.list_groups` listet alle existierenden Gruppen mit Tool-Anzahl. Es ist
immer sichtbar und wird von **keinem** Filter erfasst — sonst könnte ein
kuratierter Client die Gruppennamen nicht mehr herausfinden.
```

- [ ] **Step 5: Run the full MCP suite one last time**

Run: `PYTEST mcp_server/ rest_api/tests/test_architecture.py application/tests/test_artifact_markdown.py -q --create-db`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/agent-templates/tool-manifest.json docs/MCP.md backend/mcp_server/tests/test_export_tool_manifest.py
git commit -m "docs(mcp): document 2025-06-18 protocol, resources/prompts and key scoping"
```

---

## Task 16: Client compatibility smoke test (spec §8, manual)

**Files:**
- Modify: none (verification only)
- Test: manual, against a running stack

> Spec §8 requires a live test against the clients that already exercised H1/H2 before rollout. This is the only step in the plan that is not automatable here — the clients are external processes.

- [ ] **Step 1: Bring the stack up**

Run: `make up`

- [ ] **Step 2: Verify legacy negotiation over HTTP**

```bash
curl -s -i -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}'
```

Expected: HTTP 200, an `Mcp-Session-Id` response header, and `"protocolVersion":"2024-11-05"` in the body.

- [ ] **Step 3: Verify modern negotiation and the capability set**

```bash
curl -s -X POST http://localhost:8000/mcp/ \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "MCP-Protocol-Version: 2025-06-18" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}'
```

Expected: `"protocolVersion":"2025-06-18"` and `"capabilities":{"tools":{},"resources":{},"prompts":{}}`.

- [ ] **Step 4: Verify the new methods answer with a real key**

```bash
KEY=<a reqlo_ key from the UI, Settings -> API Keys>
for M in resources/templates/list prompts/list; do
  curl -s -X POST http://localhost:8000/mcp/ -H "Content-Type: application/json" \
    -H "X-API-Key: $KEY" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$M\",\"params\":{}}"
  echo
done
curl -s -X POST http://localhost:8000/mcp/ -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"tool.list_groups","arguments":{}}}'
```

Expected: three `result` frames, no `error`; the third lists `icd` and `tool` among the groups.

- [ ] **Step 5: Connect Claude Code and OpenCode**

Point both clients at `http://localhost:8000/mcp/` (StreamableHTTP) with the same key. Confirm each lists tools, and that OpenCode's SSE fallback (`http://localhost:8000/mcp/sse/`) still connects when StreamableHTTP is disabled in its config.
Expected: both connect; the SSE path behaves exactly as before this change.

- [ ] **Step 6: Record the result**

Note the two client versions tested in the PR description. No commit.

---

## Self-Review

**1. Spec coverage**

| Spec section | Covered by |
|---|---|
| §3 protocol version → 2025-06-18 | Task 1 (as a negotiated set, resolving the §8 risk) |
| §3 Streamable HTTP, `Mcp-Session-Id` header | Tasks 2, 3 (+ DECISION: POST answers JSON, spec-compliant) |
| §3 legacy SSE stays | Global Constraints; Task 3 Step 5 asserts it |
| §3 `capabilities` gains `resources` + `prompts` | Tasks 6, 7 |
| §4 `resources/list`, `resources/read`, `resources/templates/list` | Task 6 |
| §4 shared renderer, two thin adapters | Task 4 (`render_artifact_markdown`), Task 6 adapter |
| §4 `prompts/list`, `prompts/get`; `prompt_template.*` stays | Task 7 + docs in Task 15 |
| §5 `icd.get`, `icd.query`, no writes | Task 8 |
| §6.1 `scope="read"` filters AND refuses | Tasks 10, 13 |
| §6.2 `tool_groups` JSONField, list-only filter | Tasks 9, 11, 14 |
| §6.2 `tool.list_groups`, always visible | Task 12 |
| §7 migration steps 1–6 | Tasks 1/6/7 (1), 3 (2), 6/7 (3), 8 (4), 9–11/13 (5), 12 (6) |
| §8 downgrade compatibility, live client test | Task 1 + Task 16 |
| §8 duplication risk | Task 4 DECISION — one function, one adapter today |
| §8 `tool_groups` misuse risk | Task 12 tool description, Task 14 validator message, Task 15 docs table |

**2. Placeholder scan** — no "TBD", no "similar to Task N", no untyped "add error handling". Every test body and every implementation body is literal code. The one deliberately non-literal step is Task 14 Step 3 item 3 ("add to the metadata dict every action returns"), which names the exact key, the exact value expression and the exact fallback if the ratchet objects.

**3. Type consistency** — `render_artifact_markdown` produces `ArtifactMarkdown`, consumed in Task 6 by `.artifact_type` / `.artifact_id` / `.markdown` / `.workspace_id`, all four of which the dataclass declares. `authenticated_context` produces `AuthContext`, consumed in Tasks 6 and 7 via `.tenant_id`. `AuthContext.scope: str` / `.tool_groups: tuple[str, ...]` (Task 10) are consumed as `str` in `_is_read_scoped` and as an iterable of `str` in `_filter_by_tool_groups` and `IntrospectionToolGroup`. `PromptSlotSpec.data_variables: Tuple[str, ...]` feeds `_argument_specs`, which tolerates `None`/`()`. `ENTITY_SPECS["icd"]` uses the declared default `workspace_field="workspace_id"`, which matches `Icd.workspace_id` (a real local column).

---

## OFFENE FRAGEN

None that block implementation. Two spec statements were factually wrong against the live tree and are resolved by explicit, documented decisions rather than guesses (`TenantToolRegistry` → `ToolRegistry`; `McpArtifactProvider`/`artifact.get` → a new shared renderer on `ExportService`, see the DECISION block). One hard dependency is named rather than assumed: `ApiKey.scope` comes from the KI-Vorschlag-als-Zustand plan, and Tasks 10 and 13 each open with a Step 0 that verifies it and blocks instead of duplicating the migration.
