# MCP-Modernisierung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the MCP server to protocol revision 2025-06-18 with Streamable-HTTP sessions, add `resources/*` and `prompts/*` capabilities on top of a new shared artifact-Markdown renderer, close the ICD read gap with an `icd.*` tool group, and add two additive manifest filters (`ApiKey.scope` as a real security boundary, `ApiKey.tool_groups` as pure catalog curation).

**Architecture:** `resources/*` and `prompts/*` are dispatched through the **existing** `ToolRegistry.dispatch_request()` as internal pseudo-tools (`resource.*`, `prompt.*`) whose tool groups return an empty `get_tool_schemas()` — so they inherit the full auth/tenant/RBAC/preset chain for free while staying invisible in `tools/list`. The generic artifact Markdown renderer is a new Layer-2 module (`application/artifact_markdown.py`) that reflects over Django `_meta.fields`, so it covers all nine artifact types with one implementation and is the module the Dokumentensicht spec consumes later. `ApiKey.scope` is enforced in **both** `list_tools()` and `dispatch_request()`; `ApiKey.tool_groups` is enforced **only** in `list_tools()`.

**Tech Stack:** Python 3.x, Django 5.2+, pytest / pytest-django, Redis (existing `mcp_server.sse_pubsub` session store), DRF (API-key REST surface).

**Spec:** docs/superpowers/specs/2026-09-03-mcp-modernisierung-design.md

## Global Constraints

- `MCP_PROTOCOL_VERSION` becomes exactly `"2025-06-18"` (currently `"2024-11-05"` at `backend/mcp_server/protocol_handler.py:45`).
- Backwards compatibility is mandatory: a client that requests `"2024-11-05"` must keep working (spec §8, risk 1). Negotiation echoes a supported requested version instead of forcing the server's newest.
- `initialize` `capabilities` must carry `resources: {}` and `prompts: {}` **in addition to** the existing `tools: {}` — never replacing it.
- **Legacy SSE transport (`/mcp/sse/`, `/mcp/messages/`) is not removed and not modified.** The OpenCode fallback path of issue #846 depends on it (spec §3).
- `artifact.get` **does not exist** in this codebase (only `artifact.search` and `artifact.get_tree`); `McpArtifactProvider` (`backend/diagram/mcp_artifact_provider.py`) is diagram-specific and stays untouched. The shared renderer is new (Task 5, see "Spec corrections").
- The class in `backend/mcp_server/tool_registry.py` is `ToolRegistry`, not `TenantToolRegistry`.
- `ApiKey.tool_groups` is **catalog curation only**: `tools/list` filters on it, `tools/call` must remain fully functional for every tool the caller's role and `scope` allow.
- `ApiKey.scope == "read"` is a **real security boundary**: it filters `tools/list` *and* rejects write tools in `dispatch_request()` with `PERMISSION_DENIED`, before any bootstrap or tenant-admin exemption.
- `tool.list_groups` is always visible and never filtered by `tool_groups` or `scope`.
- The write gate stays fail-closed: every new read-only tool must be added explicitly to `_READ_ONLY_TOOL_NAMES` (`backend/mcp_server/tool_registry.py:204`) or end in `.read` / `.query`.
- Every `ToolResult.data` payload must be `json.dumps`-encodable with the stdlib encoder (no raw `UUID` / `datetime`) — the MCP transport uses stdlib `json`, unlike DRF.
- Scope exclusions: JSON-RPC batch support, `GET /mcp/` behaviour and the parse-error HTTP status are GitHub issue **#846**, not this plan.
- Writing ICD tools (`icd.create` / `icd.update`) is explicitly out of scope (spec §5).

## Spec corrections (verified against the codebase before planning)

| Spec claim | Reality | Consequence |
|---|---|---|
| `TenantToolRegistry.list_tools()` (§1) | Class is `ToolRegistry` (`backend/mcp_server/tool_registry.py:461`) | Use `ToolRegistry` everywhere. |
| `MCP_PROTOCOL_VERSION = "2024-11-05"` at `protocol_handler.py:45` (§1) | **Confirmed exactly.** | Task 1 changes that one line. |
| `capabilities: {"tools": {}}` only (§1) | **Confirmed** (`protocol_handler.py:454-456`). | Task 1 extends it. |
| `McpArtifactProvider` renders artifact Markdown for the tool `artifact.get` (§4) | **Wrong twice.** There is no `artifact.get` tool (only `artifact.search`, `artifact.get_tree`), and `McpArtifactProvider` is only reachable from `diagram/services.py` — it renders *diagrams*. | The "one renderer, two thin adapters" recommendation (§8, risk 2) is still right, but the renderer must be **built**, not reused. Task 5. |
| Dokumentensicht already provides a generic Markdown renderer | `docs/superpowers/plans/2026-09-03-dokumentensicht.md` does not exist, and that spec's §4 explicitly consumes *this* spec's renderer. | This plan is the producer. Task 5 must land before Dokumentensicht starts. |
| `ApiKey.scope` already exists (§7.5) | Not in `backend/auth_tenancy/models.py` yet — it ships with the KI-Vorschlag-als-Zustand spec (order #4; this spec is #7). | Task 9 detects it and adds it if that plan has not landed, using that spec's exact definition. |

## File Structure

```
backend/
  mcp_server/
    protocol_handler.py                      MODIFY  version negotiation, capabilities,
                                                     resources/* + prompts/* method routing
    views.py                                 MODIFY  Mcp-Session-Id, SSE-on-POST, DELETE,
                                                     MCP-Protocol-Version validation
    urls.py                                  UNCHANGED
    sse_pubsub.py                            MODIFY  + delete_session_api_key()
    tool_registry.py                         MODIFY  scope/tool_groups gates, new groups,
                                                     _READ_ONLY_TOOL_NAMES entries
    api_key_policy.py                        CREATE  ApiKeyPolicy lookup by api_key_id
    tools/
      resources.py                           CREATE  ResourcesToolGroup (schemas = [])
      prompts.py                             CREATE  PromptsToolGroup (schemas = [])
      icd.py                                 CREATE  IcdToolGroup (icd.get, icd.query)
      introspection.py                       CREATE  IntrospectionToolGroup (tool.list_groups)
    tests/
      test_protocol_version_negotiation.py   CREATE
      test_streamable_http_session.py        CREATE
      test_resources_capability.py           CREATE
      test_prompts_capability.py             CREATE
      test_icd_tool_group.py                 CREATE
      test_introspection_tool_group.py       CREATE
      test_api_key_scope_gate.py             CREATE
      test_api_key_tool_groups_filter.py     CREATE
  application/
    artifact_markdown.py                     CREATE  render_artifact_markdown()
    artifact_service.py                      MODIFY  + list_artifact_resources()
    tests/
      test_artifact_markdown.py              CREATE
  auth_tenancy/
    models.py                                MODIFY  + ApiKey.tool_groups (+ scope if absent)
    migrations/00XX_apikey_tool_groups.py    CREATE
    services/authentication.py               MODIFY  create_api_key(tool_groups=...)
  rest_api/
    api_key_views.py                         MODIFY  expose scope + tool_groups
docs/
  agent-templates/tool-manifest.json         REGENERATE
  <MCP integrator page>                      MODIFY  scope-vs-tool_groups wording
                                                     (exact path located in Task 15 Step 2)
```

## Task order and dependencies

```
Task 1 -> Task 2 -> Task 3 -> Task 4                       (protocol & transport)
Task 5 -> Task 6 -> Task 7 -> Task 8                       (renderer -> resources -> prompts -> icd)
Task 9 -> Task 10 -> Task 11 -> Task 12 -> Task 13 -> 14   (manifest filters)
Task 15                                                    (docs + manifest regeneration, last)
```

Two cross-edges that are easy to miss:

- **Task 1 must precede Task 6** — the `resources` capability has to be advertised before it is served.
- **Task 8 depends on Task 7**, not just on Phase C: `IcdToolGroup` imports `accessible_workspace_ids` from `mcp_server/tools/prompts.py` for its workspace-membership check. If Task 8 is pulled forward, move that helper to `mcp_server/tools/base.py` first and import it from there in both places.
- **Task 13 closes two tests deferred from Task 12** (`_ALWAYS_VISIBLE_TOOLS` does not exist until Task 12 Step 3, and nothing populates it until Task 13). Task 12 Step 4 therefore runs a filtered subset on purpose.

**Test command convention:** every `pytest` invocation below is run inside the backend container:
`docker compose exec backend pytest <args>`. Only the changed modules are run per task; the full matrix is CI's job.

---

## Phase A — Protocol & Transport

### Task 1: Protocol version negotiation and extended capabilities

**Files:**
- Modify: `backend/mcp_server/protocol_handler.py:45` (constant), `:451-463` (`initialize` branch), `:609-619` (`__all__`)
- Test: `backend/mcp_server/tests/test_protocol_version_negotiation.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `MCP_PROTOCOL_VERSION: str = "2025-06-18"`, `SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...]`, `negotiate_protocol_version(requested: object) -> str`.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_protocol_version_negotiation.py`:

```python
"""Protocol revision 2025-06-18 negotiation (MCP-Modernisierung Task 1)."""
import json

import pytest

from mcp_server.protocol_handler import (
    MCP_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    HttpTransportAdapter,
    ProtocolHandler,
    negotiate_protocol_version,
)


def test_constant_is_2025_06_18():
    assert MCP_PROTOCOL_VERSION == "2025-06-18"


def test_supported_versions_include_legacy():
    assert SUPPORTED_PROTOCOL_VERSIONS[0] == "2025-06-18"
    assert "2024-11-05" in SUPPORTED_PROTOCOL_VERSIONS


@pytest.mark.parametrize(
    "requested,expected",
    [
        ("2025-06-18", "2025-06-18"),
        ("2024-11-05", "2024-11-05"),
        ("1999-01-01", "2025-06-18"),
        (None, "2025-06-18"),
        (12345, "2025-06-18"),
    ],
)
def test_negotiate_echoes_supported_else_newest(requested, expected):
    assert negotiate_protocol_version(requested) == expected


def _initialize(params):
    handler = ProtocolHandler(tool_registry=object())
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}
    ).encode()
    return handler.handle(HttpTransportAdapter(body=body, headers={}), headers={})


def test_initialize_advertises_resources_and_prompts():
    capabilities = _initialize({})["result"]["capabilities"]
    assert capabilities["tools"] == {}
    assert capabilities["resources"] == {}
    assert capabilities["prompts"] == {}


def test_initialize_echoes_legacy_client_version():
    result = _initialize({"protocolVersion": "2024-11-05"})["result"]
    assert result["protocolVersion"] == "2024-11-05"


def test_initialize_defaults_to_newest_without_params():
    assert _initialize({})["result"]["protocolVersion"] == "2025-06-18"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_protocol_version_negotiation.py -v`
Expected: FAIL with `ImportError: cannot import name 'SUPPORTED_PROTOCOL_VERSIONS' from 'mcp_server.protocol_handler'`

- [ ] **Step 3: Bump the constant and add the negotiator**

In `backend/mcp_server/protocol_handler.py`, replace line 45 (`MCP_PROTOCOL_VERSION = "2024-11-05"`) with:

```python
MCP_PROTOCOL_VERSION = "2025-06-18"

#: Every revision this server can speak, newest first. MCP negotiation is
#: "echo the client's revision when we support it, otherwise answer with ours"
#: — a client pinned to 2024-11-05 (spec section 8, risk 1) therefore keeps
#: working unchanged after the bump.
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)


def negotiate_protocol_version(requested: object) -> str:
    """Return the revision to answer ``initialize`` with.

    Args:
        requested: ``params.protocolVersion`` exactly as received — any type,
            since it comes straight off the wire.

    Returns:
        *requested* when it is a supported revision string, else
        :data:`MCP_PROTOCOL_VERSION`.
    """
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return MCP_PROTOCOL_VERSION
```

- [ ] **Step 4: Extend the initialize response**

Replace the `initialize` branch body (`protocol_handler.py:451-463`) with:

```python
        if method == "initialize":
            response = ErrorFormatter.format_jsonrpc_result(request_id, {
                "protocolVersion": negotiate_protocol_version(
                    params.get("protocolVersion")
                ),
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                },
                "serverInfo": {
                    "name": "ReqogniLoom",
                    "version": "1.0.0"
                }
            })
            adapter.write_response(response)
            return response
```

Add to `__all__` (`protocol_handler.py:609`):

```python
    "MCP_PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "negotiate_protocol_version",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_protocol_version_negotiation.py -v`
Expected: PASS (10 passed)

- [ ] **Step 6: Run the neighbouring protocol suites for regressions**

Run: `docker compose exec backend pytest mcp_server/tests/test_protocol_handler.py mcp_server/tests/test_e2e_mcp.py -q`
Expected: PASS, no new failures versus the pre-change baseline.

- [ ] **Step 7: Commit**

```bash
git add backend/mcp_server/protocol_handler.py backend/mcp_server/tests/test_protocol_version_negotiation.py
git commit -m "feat(mcp): negotiate protocol 2025-06-18, advertise resources+prompts"
```

---

### Task 2: `Mcp-Session-Id` for the Streamable HTTP transport

**Files:**
- Modify: `backend/mcp_server/sse_pubsub.py` (append `delete_session_api_key` after `get_session_api_key`, ~line 132)
- Modify: `backend/mcp_server/views.py` (`McpHttpTransportView`, `:262-385`)
- Test: `backend/mcp_server/tests/test_streamable_http_session.py`

**Interfaces:**
- Consumes: `store_session_api_key(session_id: str, api_key: str, ttl: int = SESSION_TTL_SECONDS) -> None` and `get_session_api_key(session_id: str) -> Optional[str]` (existing, `mcp_server/sse_pubsub.py:74` / `:107`).
- Produces: `delete_session_api_key(session_id: str) -> None`; `_incoming_session_id(request) -> str`; `McpHttpTransportView._attach_session(...)`; `DELETE /mcp/`.

**Decision:** the Streamable-HTTP session reuses the existing Redis-backed SSE session store instead of introducing a second one — both bind a session id to an authenticated API key with a TTL, which is the same primitive. Encryption at rest and TTL come along for free.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_streamable_http_session.py`:

```python
"""Mcp-Session-Id on the Streamable-HTTP transport (Task 2/3)."""
import json
from unittest.mock import patch

import pytest
from django.test import Client


def _initialize_body():
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )


@pytest.mark.django_db
def test_initialize_mints_session_id_header():
    stored = {}
    with patch(
        "mcp_server.views.store_session_api_key",
        side_effect=lambda sid, key, **kw: stored.update({sid: key}),
    ):
        response = Client().post(
            "/mcp/",
            data=_initialize_body(),
            content_type="application/json",
            HTTP_X_API_KEY="reqlo_dummy",
        )
    assert response.status_code == 200
    session_id = response.headers["Mcp-Session-Id"]
    assert stored[session_id] == "reqlo_dummy"


@pytest.mark.django_db
def test_initialize_without_credential_mints_no_session():
    response = Client().post(
        "/mcp/", data=_initialize_body(), content_type="application/json"
    )
    assert response.status_code == 200
    assert "Mcp-Session-Id" not in response.headers


@pytest.mark.django_db
def test_non_initialize_echoes_incoming_session_id():
    body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    with patch("mcp_server.views.get_session_api_key", return_value="reqlo_dummy"):
        response = Client().post(
            "/mcp/",
            data=body,
            content_type="application/json",
            HTTP_MCP_SESSION_ID="sess-1",
        )
    assert response.headers["Mcp-Session-Id"] == "sess-1"


@pytest.mark.django_db
def test_session_id_supplies_the_api_key_when_header_absent():
    body = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    with patch(
        "mcp_server.views.get_session_api_key", return_value="reqlo_from_session"
    ) as lookup:
        Client().post(
            "/mcp/",
            data=body,
            content_type="application/json",
            HTTP_MCP_SESSION_ID="sess-1",
        )
    lookup.assert_called_once_with("sess-1")


@pytest.mark.django_db
def test_delete_terminates_a_known_session():
    with patch(
        "mcp_server.views.get_session_api_key", return_value="reqlo_dummy"
    ), patch("mcp_server.views.delete_session_api_key") as delete:
        response = Client().delete("/mcp/", HTTP_MCP_SESSION_ID="sess-1")
    assert response.status_code == 204
    delete.assert_called_once_with("sess-1")


@pytest.mark.django_db
def test_delete_unknown_session_is_404():
    with patch("mcp_server.views.get_session_api_key", return_value=None):
        response = Client().delete("/mcp/", HTTP_MCP_SESSION_ID="nope")
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_without_session_header_is_400():
    assert Client().delete("/mcp/").status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_streamable_http_session.py -v`
Expected: FAIL — `AttributeError: <module 'mcp_server.views'> does not have the attribute 'store_session_api_key'`

- [ ] **Step 3: Add the session-deletion primitive**

Append to `backend/mcp_server/sse_pubsub.py`, directly after `get_session_api_key` (which ends at line 131):

```python
def delete_session_api_key(session_id: str) -> None:
    """Drop the API-key binding of *session_id* (Streamable-HTTP DELETE).

    Idempotent and best-effort: a Redis failure is logged, never raised. The
    binding carries its own TTL, so a missed delete expires on its own — an
    exception here would turn an optional client courtesy call into a 500.
    """
    try:
        _get_redis_client().delete(_session_auth_key(session_id))
    except Exception:
        logger.exception(f"Failed to delete session api key for {session_id}")
```

- [ ] **Step 4: Import the session store into the view module**

In `backend/mcp_server/views.py`, extend the existing `mcp_server.sse_pubsub` import (used today by `McpMessagesView` / `McpSseTransportView`) so all three names are available at module level — the tests patch them there:

```python
from mcp_server.sse_pubsub import (
    delete_session_api_key,
    get_session_api_key,
    store_session_api_key,
)
```

If those names are currently imported inside functions rather than at module scope, move them to module scope; leave every other `sse_pubsub` import (e.g. `publish_mcp_message`, `async_sse_generator`) exactly as it is.

- [ ] **Step 5: Add the session-header helper**

In `backend/mcp_server/views.py`, next to `_extract_django_headers` (`:176`):

```python
#: Streamable-HTTP session header (MCP 2025-06-18). ``request.headers`` handles
#: the HTTP_-prefix canonicalisation, so the literal spelling is enough here.
_SESSION_HEADER = "Mcp-Session-Id"


def _incoming_session_id(request: HttpRequest) -> str:
    """Return the caller's ``Mcp-Session-Id``, or ``""`` when absent."""
    return request.headers.get(_SESSION_HEADER, "").strip()
```

- [ ] **Step 6: Let a session id stand in for the credential header**

In `McpHttpTransportView.post`, directly after `headers = _extract_django_headers(request)` (`views.py:279`):

```python
        # Streamable HTTP (MCP 2025-06-18): a session id may stand in for the
        # credential on follow-up requests, exactly as it already does on the
        # legacy SSE message endpoint. An explicit header always wins, so this
        # can never downgrade or override a credential the caller did send.
        session_id = _incoming_session_id(request)
        if session_id and not headers.get("X-API-Key") and not headers.get("Authorization"):
            bound_key = get_session_api_key(session_id)
            if bound_key:
                headers["X-API-Key"] = bound_key
```

- [ ] **Step 7: Mint / echo the session header on the response**

In `McpHttpTransportView.post`, replace the final `return HttpResponse(body, content_type="application/json", status=http_status)` (`views.py:381-385`) with:

```python
        http_response = HttpResponse(
            body,
            content_type="application/json",
            status=http_status,
        )
        self._attach_session(request, http_response, response_frame, headers)
        return http_response
```

Add these two methods to `McpHttpTransportView`:

```python
    def _attach_session(
        self,
        request: HttpRequest,
        response: HttpResponse,
        frame: dict,
        headers: dict,
    ) -> None:
        """Mint or echo the ``Mcp-Session-Id`` header on *response*.

        A session is minted only on a successful ``initialize`` that carried a
        credential. An anonymous or failed initialize gets none, so an
        unauthenticated caller can never obtain a binding to trade in later.
        """
        session_id = _incoming_session_id(request)
        if session_id:
            response[_SESSION_HEADER] = session_id
            return

        if "error" in frame:
            return
        try:
            method = json.loads(request.body).get("method")
        except (ValueError, TypeError, AttributeError):
            return
        if method != "initialize":
            return

        api_key = headers.get("X-API-Key") or ""
        if not api_key:
            authorization = headers.get("Authorization", "")
            if authorization.startswith("Bearer "):
                api_key = authorization[len("Bearer "):].strip()
        if not api_key:
            return

        new_session_id = str(uuid.uuid4())
        try:
            store_session_api_key(new_session_id, api_key)
        except Exception:
            # A session is an optimisation, not a requirement: the caller can
            # keep sending its credential header on every request. Failing the
            # whole initialize over a Redis hiccup would be strictly worse.
            logger.exception("Failed to store Streamable-HTTP session binding")
            return
        response[_SESSION_HEADER] = new_session_id

    def delete(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Terminate a Streamable-HTTP session (MCP 2025-06-18)."""
        session_id = _incoming_session_id(request)
        if not session_id:
            return HttpResponse(status=400)
        if get_session_api_key(session_id) is None:
            return HttpResponse(status=404)
        delete_session_api_key(session_id)
        return HttpResponse(status=204)
```

`import uuid` and `logger` already exist at the top of `views.py` (`McpSseTransportView._resolve_session_id` uses `uuid.uuid4()`); do not re-add them.

- [ ] **Step 8: Allow DELETE through CORS**

Read `_apply_cors_headers` (`views.py:208`) and `CorsMixin` (`views.py:233`). Change only the `methods=` value that `McpHttpTransportView` passes / defaults to, from `"POST, GET, OPTIONS"` to:

```python
"POST, GET, DELETE, OPTIONS"
```

Leave `McpMessagesView`'s own value untouched.

- [ ] **Step 9: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_streamable_http_session.py -v`
Expected: PASS (7 passed)

- [ ] **Step 10: Run the transport regression suites**

Run: `docker compose exec backend pytest mcp_server/tests/test_e2e_sse_transport.py mcp_server/tests/test_csrf_exempt_invariant.py mcp_server/tests/test_mcp_transport_throttling.py -q`
Expected: PASS, unchanged versus baseline — the legacy SSE transport must be provably untouched.

- [ ] **Step 11: Commit**

```bash
git add backend/mcp_server/sse_pubsub.py backend/mcp_server/views.py backend/mcp_server/tests/test_streamable_http_session.py
git commit -m "feat(mcp): Mcp-Session-Id sessions for the Streamable HTTP transport"
```

---

### Task 3: SSE response body on POST `/mcp/` when the client asks for it

**Files:**
- Modify: `backend/mcp_server/views.py` (`McpHttpTransportView`)
- Test: `backend/mcp_server/tests/test_streamable_http_session.py` (append)

**Interfaces:**
- Consumes: `_incoming_session_id`, `McpHttpTransportView._attach_session` (Task 2).
- Produces: `McpHttpTransportView._wants_event_stream(request) -> bool`, `McpHttpTransportView._sse_frame(frame: dict) -> str`.

**Decision:** Streamable HTTP lets the server answer a POST with either JSON or an SSE stream. This server answers every request in exactly one frame, so the SSE form is a single `message` event followed by stream close — no long-lived generator, no ASGI streaming requirement, no change to the legacy SSE endpoint.

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_streamable_http_session.py`:

```python
@pytest.mark.django_db
def test_post_returns_sse_when_client_prefers_event_stream():
    response = Client().post(
        "/mcp/",
        data=_initialize_body(),
        content_type="application/json",
        HTTP_ACCEPT="text/event-stream",
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/event-stream")
    text = response.content.decode()
    assert text.startswith("event: message\ndata: ")
    assert text.endswith("\n\n")
    payload = json.loads(text.split("data: ", 1)[1].strip())
    assert payload["result"]["protocolVersion"] == "2025-06-18"


@pytest.mark.django_db
def test_post_still_returns_json_by_default():
    response = Client().post(
        "/mcp/", data=_initialize_body(), content_type="application/json"
    )
    assert response["Content-Type"] == "application/json"


@pytest.mark.django_db
def test_sse_response_still_carries_the_session_header():
    with patch("mcp_server.views.store_session_api_key"):
        response = Client().post(
            "/mcp/",
            data=_initialize_body(),
            content_type="application/json",
            HTTP_ACCEPT="text/event-stream",
            HTTP_X_API_KEY="reqlo_dummy",
        )
    assert "Mcp-Session-Id" in response.headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_streamable_http_session.py -k event_stream -v`
Expected: FAIL — `AssertionError` because `response["Content-Type"]` is `application/json`.

- [ ] **Step 3: Add the two helpers**

Add to `McpHttpTransportView` in `backend/mcp_server/views.py`:

```python
    @staticmethod
    def _wants_event_stream(request: HttpRequest) -> bool:
        """Return whether the caller asked for the SSE form of the response.

        JSON stays the default: only an explicit ``text/event-stream`` in
        ``Accept`` selects SSE, so a client sending ``*/*`` is unaffected.
        """
        return "text/event-stream" in request.headers.get("Accept", "")

    @staticmethod
    def _sse_frame(frame: dict) -> str:
        """Serialise one JSON-RPC frame as a single SSE ``message`` event."""
        return f"event: message\ndata: {json.dumps(frame)}\n\n"
```

- [ ] **Step 4: Branch the response construction**

Replace the response construction added in Task 2 Step 7 with:

```python
        if self._wants_event_stream(request):
            http_response = HttpResponse(
                self._sse_frame(response_frame),
                content_type="text/event-stream",
                status=http_status,
            )
            http_response["Cache-Control"] = "no-cache"
        else:
            http_response = HttpResponse(
                body,
                content_type="application/json",
                status=http_status,
            )
        self._attach_session(request, http_response, response_frame, headers)
        return http_response
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_streamable_http_session.py -v`
Expected: PASS (10 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/mcp_server/views.py backend/mcp_server/tests/test_streamable_http_session.py
git commit -m "feat(mcp): answer POST /mcp/ with SSE when Accept requests it"
```

---

### Task 4: `MCP-Protocol-Version` request-header validation

**Files:**
- Modify: `backend/mcp_server/views.py` (`McpHttpTransportView.post`, after the rate-limit block at `:272-276`)
- Test: `backend/mcp_server/tests/test_protocol_version_negotiation.py` (append)

**Interfaces:**
- Consumes: `SUPPORTED_PROTOCOL_VERSIONS` (Task 1).
- Produces: no new symbol; a 400 JSON-RPC error frame for an unsupported header value.

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_protocol_version_negotiation.py`:

```python
from django.test import Client


def _tools_list_body():
    return json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"})


@pytest.mark.django_db
def test_unsupported_protocol_header_is_rejected():
    response = Client().post(
        "/mcp/",
        data=_tools_list_body(),
        content_type="application/json",
        HTTP_MCP_PROTOCOL_VERSION="1999-01-01",
    )
    assert response.status_code == 400
    body = json.loads(response.content)
    assert body["error"]["error_code"] == "INVALID_REQUEST"
    assert "1999-01-01" in body["error"]["message"]


@pytest.mark.django_db
def test_supported_protocol_header_passes_through():
    response = Client().post(
        "/mcp/",
        data=_tools_list_body(),
        content_type="application/json",
        HTTP_MCP_PROTOCOL_VERSION="2024-11-05",
    )
    assert response.status_code != 400


@pytest.mark.django_db
def test_absent_protocol_header_passes_through():
    response = Client().post(
        "/mcp/", data=_tools_list_body(), content_type="application/json"
    )
    assert response.status_code != 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_protocol_version_negotiation.py -k protocol_header -v`
Expected: FAIL — `assert 401 == 400`; the header is ignored today, so the request falls through to the auth failure.

- [ ] **Step 3: Write minimal implementation**

Extend the `mcp_server.protocol_handler` import in `backend/mcp_server/views.py` with `SUPPORTED_PROTOCOL_VERSIONS`, then insert into `McpHttpTransportView.post`, after the rate-limit block (`views.py:272-276`) and before `handler = _get_handler()`:

```python
        # MCP 2025-06-18 (Transports): after initialize, a Streamable-HTTP
        # client sends the negotiated revision on every request. A value this
        # server cannot speak is a client bug, not an auth or routing problem —
        # answer 400 rather than dispatching under a false assumption.
        declared_version = request.headers.get("MCP-Protocol-Version", "").strip()
        if declared_version and declared_version not in SUPPORTED_PROTOCOL_VERSIONS:
            error_body = {
                "jsonrpc": "2.0",
                "id": _jsonrpc_request_id(request.body),
                "error": {
                    "error_code": "INVALID_REQUEST",
                    "message": (
                        f"Unsupported MCP-Protocol-Version '{declared_version}'. "
                        f"Supported: {', '.join(SUPPORTED_PROTOCOL_VERSIONS)}."
                    ),
                },
            }
            return HttpResponse(
                json.dumps(error_body),
                content_type="application/json",
                status=400,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_protocol_version_negotiation.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/views.py backend/mcp_server/tests/test_protocol_version_negotiation.py
git commit -m "feat(mcp): reject unsupported MCP-Protocol-Version request header"
```

---

## Phase B — Shared Markdown renderer, `resources/*`, `prompts/*`

### Task 5: Generic artifact Markdown renderer

**Files:**
- Create: `backend/application/artifact_markdown.py`
- Test: `backend/application/tests/test_artifact_markdown.py`

**Interfaces:**
- Consumes: `traceability.service.resolve_artifacts(artifact_ids: list[UUID | str], tenant_id: UUID) -> list[ResolvedArtifact]` (existing, `traceability/service.py:546`); `ResolvedArtifact(artifact_id: str, resolved: bool, entity_type: Optional[str], entity_id: Optional[str])`; `persistence.domain_model_registry.get_models(*names) -> Dict[str, Type]`; `application.base.NotFoundError`.
- Produces:
  - `render_artifact_markdown(artifact_id: UUID | str, ctx: AuthContext) -> str`
  - `ARTIFACT_MARKDOWN_MIME: str = "text/markdown"`

**Decision (architecture note):** the renderer is field-*class*-driven, not field-*name*-driven — H1 from a title-like `CharField`, bullet metadata from short scalar fields, one `##` section per non-empty `TextField`. One implementation covers all nine artifact types and keeps working when the Datenmodell-Konsolidierung and Attribut-Definition specs add columns. Alternatives rejected: a per-type template table (nine copies, silently stale after each schema change) and reusing `McpArtifactProvider` (diagram-specific, see "Spec corrections").

- [ ] **Step 1: Write the failing test**

Create `backend/application/tests/test_artifact_markdown.py`:

```python
"""Generic artifact Markdown renderer (MCP-Modernisierung Task 5)."""
import uuid

import pytest

from application.artifact_markdown import (
    ARTIFACT_MARKDOWN_MIME,
    render_artifact_markdown,
)
from application.base import NotFoundError


def test_mime_constant():
    assert ARTIFACT_MARKDOWN_MIME == "text/markdown"


@pytest.mark.django_db
def test_renders_requirement_title_as_h1(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert markdown.splitlines()[0] == f"# {seeded_requirement.title}"


@pytest.mark.django_db
def test_renders_type_and_artifact_id_metadata(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert "- **Type:** Requirement" in markdown
    assert f"- **Artifact ID:** {seeded_requirement.artifact_id}" in markdown


@pytest.mark.django_db
def test_renders_short_scalar_fields_as_bullets(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert f"- **Status:** {seeded_requirement.status}" in markdown


@pytest.mark.django_db
def test_renders_text_fields_as_sections(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert "## Description" in markdown
    assert seeded_requirement.description in markdown


@pytest.mark.django_db
def test_omits_empty_fields(seeded_requirement, md_auth_ctx):
    seeded_requirement.acceptance_criteria = ""
    seeded_requirement.save(update_fields=["acceptance_criteria"])
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    assert "## Acceptance Criteria" not in markdown


@pytest.mark.django_db
def test_never_leaks_technical_columns(seeded_requirement, md_auth_ctx):
    markdown = render_artifact_markdown(seeded_requirement.artifact_id, md_auth_ctx)
    for hidden in ("tenant", "embedding", "**Id:**"):
        assert hidden not in markdown


@pytest.mark.django_db
def test_unknown_artifact_id_raises_not_found(md_auth_ctx):
    with pytest.raises(NotFoundError):
        render_artifact_markdown(uuid.uuid4(), md_auth_ctx)
```

Read `backend/application/tests/conftest.py` first. If it already provides an `AuthContext` fixture and a seeded `Requirement`, reuse those names instead of the two below and rename the parameters in the test accordingly. Otherwise append:

```python
@pytest.fixture
def md_auth_ctx(db):
    """Minimal AuthContext for the seeded tenant (artifact-markdown tests)."""
    import uuid

    from auth_tenancy.context import AuthContext, AuthMethod
    from persistence.models import Tenant

    tenant = Tenant.objects.first()
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


@pytest.fixture
def seeded_requirement(db, md_auth_ctx):
    """A Requirement with its backing Artifact, description and status set."""
    from persistence.middleware import set_request_tenant
    from persistence.models import Artifact, Requirement, Workspace

    set_request_tenant(md_auth_ctx.tenant_id)
    workspace = Workspace.objects.first()
    artifact = Artifact.objects.create(
        tenant_id=md_auth_ctx.tenant_id,
        workspace=workspace,
        artifact_type="Requirement",
    )
    return Requirement.objects.create(
        tenant_id=md_auth_ctx.tenant_id,
        artifact=artifact,
        workspace=workspace,
        title="Login must be possible",
        description="The user can authenticate with email and password.",
        acceptance_criteria="Given valid credentials, a session is issued.",
        status="draft",
    )
```

`set_request_tenant` is the arming call used by `ToolRegistry.list_tools` (`tool_registry.py:633`) — it arms both the thread-local and the DB-level RLS session variable, which a `django_db` test needs.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest application/tests/test_artifact_markdown.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.artifact_markdown'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/application/artifact_markdown.py`:

```python
"""Generic artifact -> Markdown renderer (MCP-Modernisierung, spec section 4).

Single source of Markdown for an artifact, consumed by two thin adapters:

* ``mcp_server.tools.resources`` — the MCP ``resources/read`` capability;
* the Dokument-Lesemodus of the Dokumentensicht spec (its section 4), which
  renders one document section artifact by artifact.

Spec section 8 (risk 2) asks explicitly for "one shared internal function, two
thin adapters" so the two access paths cannot drift apart. This is that
function. Note that ``diagram.mcp_artifact_provider.McpArtifactProvider`` is
NOT that function: it renders diagrams only, and the ``artifact.get`` tool the
spec attributes to it does not exist in this codebase.

Rendering is driven by Django field *classes*, not field *names*: a title-like
``CharField`` becomes the H1, short scalar fields become bullet metadata, and
every non-empty ``TextField`` becomes its own ``##`` section. All nine Generic
Artifact Model types are therefore covered by one implementation, and a column
added by a later spec shows up without touching this module.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Type
from uuid import UUID

from django.db import models

from auth_tenancy.context import AuthContext

from application.base import NotFoundError

logger = logging.getLogger(__name__)

#: MIME type announced for rendered artifacts on the MCP resource surface.
ARTIFACT_MARKDOWN_MIME = "text/markdown"

#: Columns that are infrastructure, not content. ``embedding`` is a
#: thousand-plus float vector, ``tenant``/``artifact``/``workspace`` are join
#: keys the reader already holds, and the audit timestamps are noise inside a
#: specification document (the History endpoint is the place for those).
_HIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "tenant",
        "tenant_id",
        "artifact",
        "artifact_id",
        "workspace",
        "workspace_id",
        "embedding",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "search_vector",
    }
)

#: Field names probed, in order, for the document heading.
_TITLE_FIELDS: tuple[str, ...] = ("title", "name", "summary")

#: Scalar field classes rendered as one-line bullet metadata.
_SCALAR_FIELD_TYPES: tuple[type, ...] = (
    models.CharField,
    models.BooleanField,
    models.IntegerField,
    models.PositiveIntegerField,
    models.PositiveSmallIntegerField,
    models.SmallIntegerField,
    models.DecimalField,
    models.FloatField,
    models.DateField,
)


def _model_for(entity_type: str) -> Optional[Type[models.Model]]:
    """Return the Django model backing *entity_type*, or ``None``.

    Probes ``persistence.models`` first (Requirement, ArchitectureElement,
    StakeholderNeed, TestCase) and falls back to the Layer-0 domain-model
    registry for the five application-layer models (Adr, Risk, Issue, Goal,
    MainGoal), mirroring ``traceability.service._domain_model_registry``.
    """
    from persistence import models as persistence_models
    from persistence.domain_model_registry import get_models

    model = getattr(persistence_models, entity_type, None)
    if model is not None:
        return model
    return get_models(entity_type).get(entity_type)


def _label(field: models.Field) -> str:
    """Return the human-readable heading for *field*."""
    verbose = str(getattr(field, "verbose_name", "") or field.name)
    return verbose.replace("_", " ").strip().title()


def _display(row: models.Model, field: models.Field) -> str:
    """Return the display value of *field* on *row* (choices resolved)."""
    if field.choices:
        getter = getattr(row, f"get_{field.name}_display", None)
        if callable(getter):
            return str(getter())
    return str(getattr(row, field.name, "") or "")


def render_artifact_markdown(artifact_id: UUID | str, ctx: AuthContext) -> str:
    """Render one artifact as a Markdown document.

    Args:
        artifact_id: ``persistence.models.Artifact`` primary key. This is the
            *artifact* id space, not the domain-entity id space — the same
            space the trace graph and the ``resources/read`` URIs use.
        ctx: Caller identity. Tenant isolation is enforced by
            ``traceability.service.resolve_artifacts``, which only ever returns
            ids visible to ``ctx.tenant_id``.

    Returns:
        A Markdown string: H1 heading, bullet metadata, one ``##`` section per
        non-empty long-text field. Always ends with a newline.

    Raises:
        NotFoundError: The artifact does not exist, is not visible to the
            caller's tenant, or has no backing domain row.
    """
    from persistence.middleware import set_request_tenant
    from traceability.service import resolve_artifacts

    set_request_tenant(ctx.tenant_id)
    resolved = resolve_artifacts([artifact_id], tenant_id=ctx.tenant_id)
    if not resolved or not resolved[0].resolved:
        raise NotFoundError(f"Artifact {artifact_id} not found")

    entry = resolved[0]
    model = _model_for(str(entry.entity_type))
    if model is None:
        raise NotFoundError(f"Artifact {artifact_id} not found")

    row = model.objects.filter(pk=entry.entity_id).first()
    if row is None:
        raise NotFoundError(f"Artifact {artifact_id} not found")

    heading = ""
    for candidate in _TITLE_FIELDS:
        value = getattr(row, candidate, "")
        if value:
            heading = str(value)
            break
    if not heading:
        heading = f"{entry.entity_type} {entry.entity_id}"

    lines: List[str] = [f"# {heading}", ""]
    lines.append(f"- **Type:** {entry.entity_type}")
    lines.append(f"- **Artifact ID:** {entry.artifact_id}")

    sections: List[tuple[str, str]] = []
    for field in row._meta.fields:
        if field.name in _HIDDEN_FIELDS:
            continue
        if field.name in _TITLE_FIELDS and str(getattr(row, field.name, "")) == heading:
            continue
        value = _display(row, field)
        if not value:
            continue
        if isinstance(field, models.TextField):
            sections.append((_label(field), value))
        elif isinstance(field, _SCALAR_FIELD_TYPES):
            lines.append(f"- **{_label(field)}:** {value}")

    for label, value in sections:
        lines.extend(["", f"## {label}", "", value])

    return "\n".join(lines) + "\n"


__all__ = ["ARTIFACT_MARKDOWN_MIME", "render_artifact_markdown"]
```

The `TextField` branch must stay **before** the `_SCALAR_FIELD_TYPES` branch: Django's `TextField` is not a `CharField` subclass today, but the explicit order documents that long text must never collapse into a one-line bullet. Do not reorder.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest application/tests/test_artifact_markdown.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Verify a second artifact type by hand**

Run:

```bash
docker compose exec backend python manage.py shell -c "
import uuid
from application.artifact_markdown import render_artifact_markdown
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import set_request_tenant
from persistence.models import Artifact, Tenant
t = Tenant.objects.first()
set_request_tenant(t.id)
ctx = AuthContext(user_id=uuid.uuid4(), tenant_id=t.id, active_roles=('admin',), auth_method=AuthMethod.API_KEY)
for a in Artifact.objects.exclude(artifact_type='Requirement')[:2]:
    print('---', a.artifact_type)
    print(render_artifact_markdown(a.id, ctx))
"
```

Expected: readable Markdown for at least one non-Requirement type (e.g. `StakeholderNeed`, `ArchitectureElement`) with an H1, a `- **Type:**` line and at least one `##` section. A type that renders metadata only is correct behaviour, not a failure — note which and continue.

- [ ] **Step 6: Commit**

```bash
git add backend/application/artifact_markdown.py backend/application/tests/test_artifact_markdown.py backend/application/tests/conftest.py
git commit -m "feat(application): shared generic artifact Markdown renderer"
```

---

### Task 6: `resources/*` capability

**Files:**
- Create: `backend/mcp_server/tools/resources.py`
- Modify: `backend/application/artifact_service.py` (add `list_artifact_resources` to `ArtifactService`, class starts at `:210`)
- Modify: `backend/mcp_server/tool_registry.py` (`_READ_ONLY_TOOL_NAMES` `:204-283`, `_ensure_groups` imports `:532-543` and registration dict ending `:602`)
- Modify: `backend/mcp_server/protocol_handler.py` (new map next to `:96`, dispatch fallthrough `:510-511`, `__all__` `:609`)
- Test: `backend/mcp_server/tests/test_resources_capability.py`

**Interfaces:**
- Consumes: `render_artifact_markdown(artifact_id, ctx) -> str` and `ARTIFACT_MARKDOWN_MIME` (Task 5); `ArtifactService.resolve_artifact_titles(artifact_ids: List[Any]) -> Dict[str, Dict[str, Any]]` (existing, `application/artifact_service.py:410`); `AuthorizationService().accessible_workspace_ids(user_id=..., tenant_id=...)` (existing).
- Produces:
  - `ArtifactService.list_artifact_resources(self, ctx: AuthContext, workspace_id: Optional[UUID] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]`
  - `mcp_server.tools.resources.ResourcesToolGroup` handling `resource.list`, `resource.read`, `resource.templates_list`
  - `ARTIFACT_URI_PREFIX: str = "reqogniloom://artifact/"`, `ARTIFACT_URI_TEMPLATE: str = "reqogniloom://artifact/{id}"`, `MAX_RESOURCE_PAGE: int = 200`
  - `parse_artifact_uri(uri: str) -> UUID`
  - `mcp_server.protocol_handler._METHOD_TO_INTERNAL_TOOL: Dict[str, str]`

**Decision (architecture note):** `resources/*` and `prompts/*` are dispatched as internal pseudo-tools through the existing `ToolRegistry.dispatch_request()`, and their tool groups override `get_tool_schemas()` to return `[]`. Consequence: API-key validation, `TenantContext`/RLS arming, role resolution, the RBAC gate and the preset gate all apply to the new surfaces unchanged, with zero new auth code — while `tools/list` stays free of five phantom entries. Alternatives rejected: a parallel auth path inside `ProtocolHandler` (duplicates the exact chain fix #110 hardened) and exposing them as real tools (pollutes the very manifest this spec shrinks).

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_resources_capability.py`:

```python
"""resources/* capability (MCP-Modernisierung Task 6)."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.base import ParameterError
from mcp_server.tools.resources import (
    ARTIFACT_URI_PREFIX,
    ResourcesToolGroup,
    parse_artifact_uri,
)


def _ctx():
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
    )


def test_uri_prefix():
    assert ARTIFACT_URI_PREFIX == "reqogniloom://artifact/"


def test_parse_valid_uri():
    artifact_id = uuid.uuid4()
    assert parse_artifact_uri(f"{ARTIFACT_URI_PREFIX}{artifact_id}") == artifact_id


@pytest.mark.parametrize(
    "bad", ["", "http://example.com/1", "reqogniloom://artifact/not-a-uuid"]
)
def test_parse_rejects_bad_uri(bad):
    with pytest.raises(ParameterError):
        parse_artifact_uri(bad)


def test_group_is_invisible_in_tools_list():
    assert ResourcesToolGroup().get_tool_schemas() == []


def test_read_returns_mcp_contents_envelope():
    artifact_id = uuid.uuid4()
    with patch(
        "mcp_server.tools.resources.render_artifact_markdown",
        return_value="# Title\n",
    ):
        result = ResourcesToolGroup().execute_tool(
            tool_name="resource.read",
            params={"uri": f"{ARTIFACT_URI_PREFIX}{artifact_id}"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert result.success
    content = result.data["contents"][0]
    assert content["uri"] == f"{ARTIFACT_URI_PREFIX}{artifact_id}"
    assert content["mimeType"] == "text/markdown"
    assert content["text"] == "# Title\n"


def test_read_maps_not_found():
    from application.base import NotFoundError

    with patch(
        "mcp_server.tools.resources.render_artifact_markdown",
        side_effect=NotFoundError("nope"),
    ):
        result = ResourcesToolGroup().execute_tool(
            tool_name="resource.read",
            params={"uri": f"{ARTIFACT_URI_PREFIX}{uuid.uuid4()}"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_read_requires_a_uri():
    result = ResourcesToolGroup().execute_tool(
        tool_name="resource.read",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_list_returns_resource_descriptors():
    artifact_id = uuid.uuid4()
    service = MagicMock()
    service.list_artifact_resources.return_value = [
        {
            "artifact_id": str(artifact_id),
            "artifact_type": "Requirement",
            "title": "Login must be possible",
        }
    ]
    result = ResourcesToolGroup(artifact_service=service).execute_tool(
        tool_name="resource.list",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert result.success
    resource = result.data["resources"][0]
    assert resource["uri"] == f"{ARTIFACT_URI_PREFIX}{artifact_id}"
    assert resource["name"] == "Login must be possible"
    assert resource["mimeType"] == "text/markdown"


def test_list_clamps_limit():
    service = MagicMock()
    service.list_artifact_resources.return_value = []
    ResourcesToolGroup(artifact_service=service).execute_tool(
        tool_name="resource.list",
        params={"limit": 99999},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert service.list_artifact_resources.call_args.kwargs["limit"] == 200


def test_templates_list_advertises_the_artifact_uri_template():
    result = ResourcesToolGroup().execute_tool(
        tool_name="resource.templates_list",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert result.success
    template = result.data["resourceTemplates"][0]
    assert template["uriTemplate"] == "reqogniloom://artifact/{id}"
    assert template["mimeType"] == "text/markdown"


def test_protocol_handler_maps_resource_methods():
    from mcp_server.protocol_handler import _METHOD_TO_INTERNAL_TOOL

    assert _METHOD_TO_INTERNAL_TOOL["resources/list"] == "resource.list"
    assert _METHOD_TO_INTERNAL_TOOL["resources/read"] == "resource.read"
    assert (
        _METHOD_TO_INTERNAL_TOOL["resources/templates/list"]
        == "resource.templates_list"
    )


def test_resource_tools_are_read_only():
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    for name in ("resource.list", "resource.read", "resource.templates_list"):
        assert registry._is_write_tool(name) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_resources_capability.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.resources'`

- [ ] **Step 3: Add the bounded listing to ArtifactService**

Append this method to `ArtifactService` in `backend/application/artifact_service.py`, next to `resolve_artifact_titles`:

```python
    def list_artifact_resources(
        self,
        ctx: AuthContext,
        workspace_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> "List[Dict[str, Any]]":
        """Return a bounded page of artifacts for the MCP resource surface.

        Scoping mirrors ``artifact.search`` and ``prompt_template.list``: with
        an explicit *workspace_id* the dispatcher has already gated the caller
        on that workspace; without one, the result spans exactly the workspaces
        the caller holds an active role in — never the whole tenant.

        Args:
            ctx: Caller identity.
            workspace_id: Restrict to one workspace, or ``None`` for every
                accessible one.
            limit: Page size. Callers clamp; this method does not.
            offset: Rows to skip.

        Returns:
            ``[{"artifact_id": str, "artifact_type": str, "title": str}]``,
            newest first. Every value is a string: the MCP transport
            serialises with the stdlib JSON encoder, which cannot encode UUIDs.
        """
        self._set_tenant_context(ctx)

        queryset = Artifact.objects.all()
        if workspace_id is not None:
            queryset = queryset.filter(workspace_id=workspace_id)
        else:
            from auth_tenancy.services.authorization import AuthorizationService

            accessible = list(
                AuthorizationService().accessible_workspace_ids(
                    user_id=ctx.user_id, tenant_id=ctx.tenant_id
                )
            )
            queryset = queryset.filter(workspace_id__in=accessible)

        rows = list(
            queryset.order_by("-created_at").values("id", "artifact_type")[
                offset : offset + limit
            ]
        )
        titles = self.resolve_artifact_titles([row["id"] for row in rows])
        return [
            {
                "artifact_id": str(row["id"]),
                "artifact_type": row["artifact_type"],
                "title": titles.get(str(row["id"]), {}).get("title", ""),
            }
            for row in rows
        ]
```

Check the module's existing imports and add only the missing names among `Optional`, `List`, `Dict`, `Any`, `UUID`, `AuthContext`, `Artifact`.

- [ ] **Step 4: Create the resources tool group**

Create `backend/mcp_server/tools/resources.py`:

```python
"""MCP ``resources/*`` capability (MCP-Modernisierung, spec section 4).

URI scheme: ``reqogniloom://artifact/{id}`` where ``{id}`` is a
``persistence.models.Artifact`` primary key.

These are internal pseudo-tools, not part of the public tool surface:
``get_tool_schemas()`` returns an empty list, so ``tools/list`` never shows
them, while ``ToolGroupRouter`` still routes ``resource.*`` here. Dispatching
through ``ToolRegistry.dispatch_request()`` is deliberate — API-key validation,
TenantContext/RLS arming, role resolution and the RBAC gate then apply to the
resource surface exactly as they do to every tool, with no second auth path to
keep in sync.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.artifact_markdown import (
    ARTIFACT_MARKDOWN_MIME,
    render_artifact_markdown,
)
from application.base import NotFoundError, PermissionDeniedError, ValidationError

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import (
    BaseToolGroup,
    ParameterError,
    optional_uuid,
    require_param,
)

logger = logging.getLogger(__name__)

#: Every artifact resource URI starts with this.
ARTIFACT_URI_PREFIX = "reqogniloom://artifact/"

#: Advertised on ``resources/templates/list``.
ARTIFACT_URI_TEMPLATE = "reqogniloom://artifact/{id}"

#: Hard ceiling for one ``resources/list`` page. The MCP spec gives a client no
#: page-size parameter it can rely on, so the server owns the bound — an
#: unbounded enumeration of a large tenant would be exactly the context-cost
#: problem this spec set out to reduce.
MAX_RESOURCE_PAGE = 200
DEFAULT_RESOURCE_PAGE = 100


def parse_artifact_uri(uri: str) -> UUID:
    """Return the ``Artifact`` id encoded in *uri*.

    Raises:
        ParameterError: *uri* does not use the artifact scheme, or its id is
            not a UUID. Surfaces as ``VALIDATION_ERROR`` through
            ``BaseToolGroup.execute_tool``.
    """
    if not isinstance(uri, str) or not uri.startswith(ARTIFACT_URI_PREFIX):
        raise ParameterError(
            f"Unsupported resource URI '{uri}'. Expected '{ARTIFACT_URI_TEMPLATE}'."
        )
    raw = uri[len(ARTIFACT_URI_PREFIX):].strip()
    try:
        return UUID(raw)
    except (ValueError, AttributeError):
        raise ParameterError(
            f"Resource URI '{uri}' does not carry a valid artifact UUID."
        )


class ResourcesToolGroup(BaseToolGroup):
    """Artifact resources over MCP (``resource.*``, invisible in tools/list)."""

    _TOOL_MAP = {
        "resource.list": "_handle_list",
        "resource.read": "_handle_read",
        "resource.templates_list": "_handle_templates_list",
    }

    def __init__(self, artifact_service: Optional[Any] = None) -> None:
        if artifact_service is None:
            from application.artifact_service import ArtifactService

            artifact_service = ArtifactService()
        self._artifact_service = artifact_service

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return no schemas — this group is a capability, not a tool group.

        ``BaseToolGroup``'s default would synthesise a fallback schema per
        ``_TOOL_MAP`` entry and leak three phantom tools into every manifest.
        """
        return []

    # ------------------------------------------------------------------
    # resources/list
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """resource.list — a bounded page of artifact resources."""
        workspace_id = optional_uuid(params, "workspace_id")
        try:
            limit = int(params.get("limit", DEFAULT_RESOURCE_PAGE))
            offset = int(params.get("cursor", 0))
        except (TypeError, ValueError):
            raise ParameterError("'limit' and 'cursor' must be integers.")
        limit = max(1, min(limit, MAX_RESOURCE_PAGE))
        offset = max(0, offset)

        try:
            rows = self._artifact_service.list_artifact_resources(
                ctx=auth_context,
                workspace_id=workspace_id,
                limit=limit,
                offset=offset,
            )
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))
        except ValidationError as exc:
            return ToolResult.error("VALIDATION_ERROR", str(exc))

        resources = [
            {
                "uri": f"{ARTIFACT_URI_PREFIX}{row['artifact_id']}",
                "name": row.get("title")
                or f"{row['artifact_type']} {row['artifact_id']}",
                "description": f"{row['artifact_type']} artifact rendered as Markdown.",
                "mimeType": ARTIFACT_MARKDOWN_MIME,
            }
            for row in rows
        ]
        payload: Dict[str, Any] = {"resources": resources}
        if len(rows) == limit:
            payload["nextCursor"] = str(offset + limit)
        return ToolResult.ok(payload)

    # ------------------------------------------------------------------
    # resources/read
    # ------------------------------------------------------------------

    def _handle_read(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """resource.read — one artifact as Markdown."""
        uri = str(require_param(params, "uri"))
        artifact_id = parse_artifact_uri(uri)

        try:
            markdown = render_artifact_markdown(artifact_id, auth_context)
        except NotFoundError as exc:
            return ToolResult.error("NOT_FOUND", str(exc))
        except PermissionDeniedError as exc:
            return ToolResult.error("PERMISSION_DENIED", str(exc))

        return ToolResult.ok(
            {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": ARTIFACT_MARKDOWN_MIME,
                        "text": markdown,
                    }
                ]
            }
        )

    # ------------------------------------------------------------------
    # resources/templates/list
    # ------------------------------------------------------------------

    def _handle_templates_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """resource.templates_list — the parameterised artifact URI."""
        return ToolResult.ok(
            {
                "resourceTemplates": [
                    {
                        "uriTemplate": ARTIFACT_URI_TEMPLATE,
                        "name": "Artifact",
                        "description": (
                            "Any ReqogniLoom artifact (Requirement, "
                            "StakeholderNeed, ArchitectureElement, TestCase, "
                            "Adr, Risk, Issue, Goal, MainGoal) rendered as "
                            "Markdown, addressed by its Artifact id."
                        ),
                        "mimeType": ARTIFACT_MARKDOWN_MIME,
                    }
                ]
            }
        )


__all__ = [
    "ARTIFACT_URI_PREFIX",
    "ARTIFACT_URI_TEMPLATE",
    "MAX_RESOURCE_PAGE",
    "ResourcesToolGroup",
    "parse_artifact_uri",
]
```

- [ ] **Step 5: Register the group and mark its tools read-only**

In `backend/mcp_server/tool_registry.py`, add inside `_READ_ONLY_TOOL_NAMES` (before the closing brace at `:283`):

```python
        # MCP-Modernisierung Task 6: the resources/* capability is a pure read
        # path. Listed explicitly because the fail-closed default (#99) would
        # otherwise RBAC-gate it as a write tool.
        "resource.list",
        "resource.read",
        "resource.templates_list",
```

In `_ensure_groups`, add the import beside the other tool-group imports:

```python
        from mcp_server.tools.resources import ResourcesToolGroup
```

and this entry to the `self.register_groups({...})` dict:

```python
            # MCP-Modernisierung Task 6: internal pseudo-tools backing the
            # resources/* capability. get_tool_schemas() returns [] so this
            # prefix is routable but invisible in tools/list.
            "resource": ResourcesToolGroup(),
```

- [ ] **Step 6: Route the JSON-RPC methods**

In `backend/mcp_server/protocol_handler.py`, add after `_PROTOCOL_ERROR_CODES` (`:96-103`):

```python
#: MCP capability methods served by internal pseudo-tools. Dispatching them
#: through ToolRegistry gives them the full auth/tenant/RBAC/preset chain for
#: free; their tool groups return an empty get_tool_schemas(), so they never
#: appear in tools/list. The handlers return the MCP-shaped payload directly,
#: which the non-``tools/call`` serialisation branch passes through unwrapped.
_METHOD_TO_INTERNAL_TOOL: Dict[str, str] = {
    "resources/list": "resource.list",
    "resources/read": "resource.read",
    "resources/templates/list": "resource.templates_list",
    "prompts/list": "prompt.list",
    "prompts/get": "prompt.get",
}
```

Change the direct-dispatch fallthrough (`:510`) from `tool_name = method` to:

```python
        tool_name = _METHOD_TO_INTERNAL_TOOL.get(method, method)
```

Leave the following `tool_args = clean_params` line unchanged. Add `"_METHOD_TO_INTERNAL_TOOL"` to `__all__`.

- [ ] **Step 7: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_resources_capability.py -v`
Expected: PASS (14 passed)

- [ ] **Step 8: Verify end to end against a real key**

Run (paste an active `reqlo_` key when prompted):

```bash
docker compose exec -it backend python manage.py shell -c "
import json
from django.test import Client
key = input('paste an active reqlo_ key: ').strip()
c = Client()
for method, params in [('resources/templates/list', {}), ('resources/list', {'limit': 3})]:
    r = c.post('/mcp/', data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}),
               content_type='application/json', HTTP_X_API_KEY=key)
    print(method, r.status_code, r.content[:500])
"
```

Expected: both return 200 with a `result` carrying `resourceTemplates` / `resources`. Take one `uri` from the second output and repeat the call with `{'method': 'resources/read', 'params': {'uri': '<that uri>'}}` — expect `result.contents[0].text` to start with a Markdown H1. Use the Django test `Client`, not `curl`: a `uvicorn --reload` worker can hold the port in a zombie state.

- [ ] **Step 9: Run the registry regression suites**

Run: `docker compose exec backend pytest mcp_server/tests/test_export_tool_manifest.py mcp_server/tests/test_e2e_all_tools.py mcp_server/tests/test_own_tool_groups_lifecycle.py -q`
Expected: PASS — `test_export_tool_manifest.py` in particular must show the manifest tool count **unchanged**, proving the `resource.*` group stayed invisible.

- [ ] **Step 10: Commit**

```bash
git add backend/mcp_server/tools/resources.py backend/mcp_server/tool_registry.py backend/mcp_server/protocol_handler.py backend/application/artifact_service.py backend/mcp_server/tests/test_resources_capability.py
git commit -m "feat(mcp): resources/* capability over the shared Markdown renderer"
```

---

### Task 7: `prompts/*` capability

**Files:**
- Create: `backend/mcp_server/tools/prompts.py`
- Modify: `backend/mcp_server/tool_registry.py` (`_READ_ONLY_TOOL_NAMES`, `_ensure_groups`)
- Test: `backend/mcp_server/tests/test_prompts_capability.py`

**Interfaces:**
- Consumes: `application.prompt_template_versioning.list_active_templates(*, tenant_id: UUID, workspace_id: UUID | None = None) -> list[PromptTemplate]` (existing, `:53`); `application.prompt_resolver.try_resolve_template_content(name: str, ctx: AuthContext, workspace_id: Optional[UUID]) -> Optional[str]` (existing); `AuthorizationService().accessible_workspace_ids(...)`; `_METHOD_TO_INTERNAL_TOOL` (Task 6).
- Produces: `mcp_server.tools.prompts.PromptsToolGroup` handling `prompt.list`, `prompt.get`; `mcp_server.tools.prompts.accessible_workspace_ids(ctx: AuthContext) -> List[UUID]`.

**Decision:** `prompts/get` returns the template body verbatim as a single `user` message and advertises `arguments: []`. Placeholder substitution stays where it already lives (`application.prompt_resolver` / `prompt_variables`) and is deliberately not duplicated here — spec §4 scopes Prompts as the *read/use* path, with `prompt_template.*` remaining the management path.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_prompts_capability.py`:

```python
"""prompts/* capability (MCP-Modernisierung Task 7)."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.prompts import PromptsToolGroup


def _ctx():
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
    )


def _template(name, workspace_id=None):
    return SimpleNamespace(
        name=name, workspace_id=workspace_id, version=2, content="Body", is_active=True
    )


def test_group_is_invisible_in_tools_list():
    assert PromptsToolGroup().get_tool_schemas() == []


def test_list_returns_mcp_prompt_descriptors():
    with patch(
        "mcp_server.tools.prompts.list_active_templates",
        return_value=[_template("need_to_sysreq")],
    ), patch("mcp_server.tools.prompts.accessible_workspace_ids", return_value=[]):
        result = PromptsToolGroup().execute_tool(
            tool_name="prompt.list",
            params={},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert result.success
    prompt = result.data["prompts"][0]
    assert prompt["name"] == "need_to_sysreq"
    assert prompt["arguments"] == []
    assert "version 2" in prompt["description"]


def test_list_hides_templates_of_inaccessible_workspaces():
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    with patch(
        "mcp_server.tools.prompts.list_active_templates",
        return_value=[
            _template("global"),
            _template("mine", workspace_id=mine),
            _template("theirs", workspace_id=theirs),
        ],
    ), patch("mcp_server.tools.prompts.accessible_workspace_ids", return_value=[mine]):
        result = PromptsToolGroup().execute_tool(
            tool_name="prompt.list",
            params={},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert {p["name"] for p in result.data["prompts"]} == {"global", "mine"}


def test_get_returns_a_single_user_message():
    with patch(
        "mcp_server.tools.prompts.try_resolve_template_content",
        return_value="Derive requirements from: {{need}}",
    ):
        result = PromptsToolGroup().execute_tool(
            tool_name="prompt.get",
            params={"name": "need_to_sysreq"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert result.success
    message = result.data["messages"][0]
    assert message["role"] == "user"
    assert message["content"]["type"] == "text"
    assert message["content"]["text"] == "Derive requirements from: {{need}}"


def test_get_unknown_name_is_not_found():
    with patch(
        "mcp_server.tools.prompts.try_resolve_template_content", return_value=None
    ):
        result = PromptsToolGroup().execute_tool(
            tool_name="prompt.get",
            params={"name": "nope"},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_get_requires_a_name():
    result = PromptsToolGroup().execute_tool(
        tool_name="prompt.get",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_protocol_handler_maps_prompt_methods():
    from mcp_server.protocol_handler import _METHOD_TO_INTERNAL_TOOL

    assert _METHOD_TO_INTERNAL_TOOL["prompts/list"] == "prompt.list"
    assert _METHOD_TO_INTERNAL_TOOL["prompts/get"] == "prompt.get"


def test_prompt_tools_are_read_only():
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    assert registry._is_write_tool("prompt.list") is False
    assert registry._is_write_tool("prompt.get") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_prompts_capability.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.prompts'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/prompts.py`:

```python
"""MCP ``prompts/*`` capability (MCP-Modernisierung, spec section 4).

Exposes the existing, versioned ``PromptTemplate`` system as MCP prompts — the
natural path for a client that wants to offer a human a menu of ready-made
prompts instead of iterating the ``prompt_template.*`` tools. Those tools stay
in place for management (create/update, admin-gated); this capability is the
read/use path only.

Like ``mcp_server.tools.resources``, this group returns an empty
``get_tool_schemas()`` so it is routable but invisible in ``tools/list``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext

from application.prompt_resolver import try_resolve_template_content
from application.prompt_template_versioning import list_active_templates

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, optional_uuid, require_param

logger = logging.getLogger(__name__)


def accessible_workspace_ids(ctx: AuthContext) -> List[UUID]:
    """Return the workspaces *ctx* holds an active role in.

    A module-level function so the visibility filter below has one obvious seam
    to patch in tests. It applies the same narrowing
    ``PromptTemplateToolGroup._handle_list`` applies for the same reason
    (Systemaudit 2026-08-29 section 6.5: an omitted workspace_id must not mean
    "every workspace in the tenant").
    """
    from auth_tenancy.services.authorization import AuthorizationService

    return list(
        AuthorizationService().accessible_workspace_ids(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )
    )


class PromptsToolGroup(BaseToolGroup):
    """Prompt templates over MCP (``prompt.*``, invisible in tools/list)."""

    _TOOL_MAP = {
        "prompt.list": "_handle_list",
        "prompt.get": "_handle_get",
    }

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return no schemas — capability, not tool group (see resources.py)."""
        return []

    # ------------------------------------------------------------------
    # prompts/list
    # ------------------------------------------------------------------

    def _handle_list(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """prompt.list — active templates visible to the caller."""
        workspace_id: Optional[UUID] = optional_uuid(params, "workspace_id")
        rows = list_active_templates(
            tenant_id=auth_context.tenant_id, workspace_id=workspace_id
        )

        if workspace_id is None:
            accessible = set(accessible_workspace_ids(auth_context))
            rows = [
                row
                for row in rows
                if row.workspace_id is None or row.workspace_id in accessible
            ]

        prompts = [
            {
                "name": row.name,
                "description": (
                    f"ReqogniLoom prompt template '{row.name}' (version "
                    f"{row.version}"
                    + (
                        f", workspace {row.workspace_id}"
                        if row.workspace_id
                        else ", tenant-wide"
                    )
                    + ")."
                ),
                # Placeholder substitution stays in application.prompt_resolver
                # / prompt_variables. Declaring arguments here would duplicate
                # that catalog into a second, silently diverging place.
                "arguments": [],
            }
            for row in rows
        ]
        return ToolResult.ok({"prompts": prompts})

    # ------------------------------------------------------------------
    # prompts/get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """prompt.get — the effective body of one template as one message."""
        name = str(require_param(params, "name"))
        workspace_id = optional_uuid(params, "workspace_id")

        content = try_resolve_template_content(name, auth_context, workspace_id)
        if content is None:
            return ToolResult.error(
                "NOT_FOUND",
                f"No prompt template named '{name}' is available to this tenant.",
            )

        return ToolResult.ok(
            {
                "description": f"ReqogniLoom prompt template '{name}'.",
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": content}}
                ],
            }
        )


__all__ = ["PromptsToolGroup", "accessible_workspace_ids"]
```

- [ ] **Step 4: Register the group and mark its tools read-only**

In `backend/mcp_server/tool_registry.py`, add inside `_READ_ONLY_TOOL_NAMES`:

```python
        # MCP-Modernisierung Task 7: prompts/* is the read/use path for the
        # PromptTemplate system; prompt_template.create/update remain the
        # admin-gated write path and are untouched.
        "prompt.list",
        "prompt.get",
```

In `_ensure_groups`, add the import:

```python
        from mcp_server.tools.prompts import PromptsToolGroup
```

and add this entry as the **last** key of the `self.register_groups({...})` dict:

```python
            # MCP-Modernisierung Task 7: internal pseudo-tools backing the
            # prompts/* capability (invisible in tools/list, see resources).
            # Registered last so ToolGroupRouter's first-match-wins scan can
            # never shadow the prompt_template.* / prompt_variable.* prefixes.
            "prompt": PromptsToolGroup(),
```

- [ ] **Step 5: Verify no prefix collision with prompt_template / prompt_variable**

Run:

```bash
docker compose exec backend python -c "
from mcp_server.tool_registry import ToolRegistry
r = ToolRegistry(); r._ensure_groups()
for name in ('prompt.list','prompt.get','prompt_template.get','prompt_template.list','prompt_variable.list'):
    group, err = r._router.route(name)
    print(name, '->', type(group).__name__ if group else err)
"
```

Expected: `prompt.list` / `prompt.get` → `PromptsToolGroup`; `prompt_template.*` → `PromptTemplateToolGroup`; `prompt_variable.list` → `PromptVariableToolGroup`. `ToolGroupRouter.route` matches `tool_name.startswith(f"{prefix}.")`, and `prompt_template.get` does not start with `prompt.` — but the check must pass before continuing, because `_groups` is a plain dict whose iteration order decides the winner.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_prompts_capability.py -v`
Expected: PASS (8 passed)

- [ ] **Step 7: Run the prompt-template regression suites**

Run: `docker compose exec backend pytest mcp_server/tests/test_prompt_template_tool_group.py mcp_server/tests/test_prompt_variable_tool_group.py mcp_server/tests/test_export_tool_manifest.py -q`
Expected: PASS, manifest tool count still unchanged.

- [ ] **Step 8: Commit**

```bash
git add backend/mcp_server/tools/prompts.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_prompts_capability.py
git commit -m "feat(mcp): prompts/* capability over the PromptTemplate system"
```

---

## Phase C — `icd.*` tool group

### Task 8: ICD read tools (`icd.get`, `icd.query`)

**Files:**
- Create: `backend/mcp_server/tools/icd.py`
- Modify: `backend/mcp_server/tool_registry.py` (`_READ_ONLY_TOOL_NAMES`, `_ensure_groups`)
- Test: `backend/mcp_server/tests/test_icd_tool_group.py`

**Interfaces:**
- Consumes (all existing in `backend/icd/services.py`):
  - `get_icd(icd_id: uuid.UUID, tenant_id: uuid.UUID) -> Icd` (`:55`, raises `Icd.DoesNotExist`)
  - `list_icds(workspace_id: uuid.UUID, tenant_id: uuid.UUID) -> list[Icd]` (`:76`)
  - `list_icd_parameters(icd_version_id: uuid.UUID, tenant_id: uuid.UUID)` (`:395`)
  - `mcp_server.tools.prompts.accessible_workspace_ids(ctx) -> List[UUID]` (Task 7)
- Produces: `mcp_server.tools.icd.IcdToolGroup` handling `icd.get`, `icd.query`.

**Decision:** read-only MVP exactly as spec §5 scopes it. `Icd` is not an `Artifact`, so `mcp_server/workspace_scope.py` cannot derive a workspace from an `icd_id` — the group therefore performs its own explicit membership check against `accessible_workspace_ids`, the same narrowing `artifact.search` and `prompt_template.list` apply. Without it, a valid key from workspace A could read workspace B's interface contracts.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_icd_tool_group.py`:

```python
"""icd.* tool group (MCP-Modernisierung Task 8)."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.icd import IcdToolGroup

WORKSPACE = uuid.uuid4()


def _ctx():
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
    )


def _version():
    return SimpleNamespace(
        id=uuid.uuid4(),
        version_number=3,
        direction="bidirectional",
        interface_type="data",
        semantic_description="Telemetry frame exchange.",
        preconditions=["link is up"],
        postconditions=["frame acknowledged"],
        invariants=["checksum valid"],
    )


def _icd(workspace_id=WORKSPACE, version=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Sensor <-> Controller",
        workspace_id=workspace_id,
        source_element_id=uuid.uuid4(),
        target_element_id=uuid.uuid4(),
        current_version=version,
    )


def _parameter():
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="frame_rate",
        description="Frames per second.",
        unit="Hz",
        data_type="float",
        direction="out",
        min_value=1,
        max_value=60,
        nominal_value="30",
        tolerance="+/-2",
        ordering=0,
    )


def test_group_exposes_exactly_two_tools():
    names = {schema["name"] for schema in IcdToolGroup().get_tool_schemas()}
    assert names == {"icd.get", "icd.query"}


def test_schemas_declare_required_params():
    schemas = {s["name"]: s for s in IcdToolGroup().get_tool_schemas()}
    assert schemas["icd.get"]["inputSchema"]["required"] == ["icd_id"]
    assert schemas["icd.query"]["inputSchema"]["required"] == ["workspace_id"]


def test_get_returns_versioned_contract_with_parameters():
    version = _version()
    with patch(
        "mcp_server.tools.icd.get_icd", return_value=_icd(version=version)
    ), patch(
        "mcp_server.tools.icd.list_icd_parameters", return_value=[_parameter()]
    ), patch(
        "mcp_server.tools.icd.accessible_workspace_ids", return_value=[WORKSPACE]
    ):
        result = IcdToolGroup().execute_tool(
            tool_name="icd.get",
            params={"icd_id": str(uuid.uuid4())},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert result.success
    icd = result.data["icd"]
    assert icd["name"] == "Sensor <-> Controller"
    assert icd["version"]["version_number"] == 3
    assert icd["version"]["preconditions"] == ["link is up"]
    assert icd["version"]["parameters"][0]["name"] == "frame_rate"


def test_get_stringifies_every_id():
    version = _version()
    with patch(
        "mcp_server.tools.icd.get_icd", return_value=_icd(version=version)
    ), patch("mcp_server.tools.icd.list_icd_parameters", return_value=[]), patch(
        "mcp_server.tools.icd.accessible_workspace_ids", return_value=[WORKSPACE]
    ):
        result = IcdToolGroup().execute_tool(
            tool_name="icd.get",
            params={"icd_id": str(uuid.uuid4())},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    import json

    json.dumps(result.data)  # must not raise: stdlib encoder, no raw UUIDs
    assert isinstance(result.data["icd"]["id"], str)
    assert isinstance(result.data["icd"]["workspace_id"], str)


def test_get_denies_an_icd_outside_the_callers_workspaces():
    with patch(
        "mcp_server.tools.icd.get_icd", return_value=_icd(workspace_id=uuid.uuid4())
    ), patch(
        "mcp_server.tools.icd.accessible_workspace_ids", return_value=[WORKSPACE]
    ):
        result = IcdToolGroup().execute_tool(
            tool_name="icd.get",
            params={"icd_id": str(uuid.uuid4())},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "PERMISSION_DENIED"


def test_get_missing_icd_is_not_found():
    from icd.models import Icd

    with patch("mcp_server.tools.icd.get_icd", side_effect=Icd.DoesNotExist()):
        result = IcdToolGroup().execute_tool(
            tool_name="icd.get",
            params={"icd_id": str(uuid.uuid4())},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "NOT_FOUND"


def test_get_rejects_a_non_uuid_id():
    result = IcdToolGroup().execute_tool(
        tool_name="icd.get",
        params={"icd_id": "banana"},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_query_lists_workspace_icd_summaries():
    with patch(
        "mcp_server.tools.icd.list_icds", return_value=[_icd(version=_version())]
    ), patch(
        "mcp_server.tools.icd.accessible_workspace_ids", return_value=[WORKSPACE]
    ):
        result = IcdToolGroup().execute_tool(
            tool_name="icd.query",
            params={"workspace_id": str(WORKSPACE)},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert result.success
    assert result.data["count"] == 1
    summary = result.data["icds"][0]
    assert summary["name"] == "Sensor <-> Controller"
    assert summary["current_version_number"] == 3
    assert "parameters" not in summary  # summaries stay cheap


def test_query_denies_a_foreign_workspace():
    with patch(
        "mcp_server.tools.icd.accessible_workspace_ids", return_value=[WORKSPACE]
    ):
        result = IcdToolGroup().execute_tool(
            tool_name="icd.query",
            params={"workspace_id": str(uuid.uuid4())},
            auth_context=_ctx(),
            api_key="reqlo_dummy",
        )
    assert not result.success
    assert result.error_code == "PERMISSION_DENIED"


def test_icd_tools_are_read_only():
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    assert registry._is_write_tool("icd.get") is False
    assert registry._is_write_tool("icd.query") is False


def test_icd_group_is_registered():
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    group, err = registry._router.route("icd.get")
    assert err is None
    assert type(group).__name__ == "IcdToolGroup"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_icd_tool_group.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.icd'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/icd.py`:

```python
"""ICD read tools for MCP (MCP-Modernisierung, spec section 5).

Closes the REST/MCP parity gap the audit reported in chapter C6: an AI agent
could not read interface contracts although the product carries them as a core
artifact. Read-only by design — ``icd.create`` / ``icd.update`` are a natural
follow-up but explicitly out of this spec's scope.

Workspace scoping is enforced here rather than by
``mcp_server.workspace_scope``: an ``Icd`` is not an ``Artifact``, so the
dispatcher's scope resolver cannot derive a workspace from an ``icd_id``. The
explicit ``accessible_workspace_ids`` check below is the same narrowing
``artifact.search`` and ``prompt_template.list`` apply for the identical reason
(Systemaudit 2026-08-29 section 6.5).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from auth_tenancy.context import AuthContext

from icd.models import Icd
from icd.services import get_icd, list_icd_parameters, list_icds

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup, require_uuid
from mcp_server.tools.prompts import accessible_workspace_ids

logger = logging.getLogger(__name__)


def _parameter_to_dict(row: Any) -> Dict[str, Any]:
    """Serialise one ``IcdParameter`` for an MCP payload (JSON-safe)."""
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "unit": row.unit,
        "data_type": row.data_type,
        "direction": row.direction,
        "min_value": str(row.min_value) if row.min_value is not None else None,
        "max_value": str(row.max_value) if row.max_value is not None else None,
        "nominal_value": row.nominal_value,
        "tolerance": row.tolerance,
        "ordering": row.ordering,
    }


def _version_to_dict(version: Any, parameters: List[Any]) -> Dict[str, Any]:
    """Serialise one ``IcdVersion`` plus its parameters (JSON-safe)."""
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "direction": version.direction,
        "interface_type": version.interface_type,
        "semantic_description": version.semantic_description,
        "preconditions": list(version.preconditions or []),
        "postconditions": list(version.postconditions or []),
        "invariants": list(version.invariants or []),
        "parameters": [_parameter_to_dict(p) for p in parameters],
    }


def _summary_to_dict(row: Icd) -> Dict[str, Any]:
    """Serialise one ``Icd`` header without its contract body."""
    version = row.current_version
    return {
        "id": str(row.id),
        "name": row.name,
        "workspace_id": str(row.workspace_id),
        "source_element_id": str(row.source_element_id),
        "target_element_id": str(row.target_element_id),
        "current_version_number": version.version_number if version else None,
    }


class IcdToolGroup(BaseToolGroup):
    """Interface Control Document read tools (2 tools, read-only)."""

    _TOOL_MAP = {
        "icd.get": "_handle_get",
        "icd.query": "_handle_query",
    }

    _TOOL_SCHEMAS = [
        {
            "name": "icd.get",
            "description": (
                "Fetch one Interface Control Document with its current "
                "Design-by-Contract version: direction, interface type, "
                "semantic description, pre-/postconditions, invariants and "
                "the structured parameter list (unit, data type, value range, "
                "tolerance). Read-only."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "icd_id": {
                        "type": "string",
                        "description": "UUID of the ICD to fetch.",
                    }
                },
                "required": ["icd_id"],
            },
        },
        {
            "name": "icd.query",
            "description": (
                "List the Interface Control Documents of one workspace as "
                "summaries (id, name, source/target element, current version "
                "number), newest first. Use icd.get for the full contract of "
                "a single ICD. Read-only."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_id": {
                        "type": "string",
                        "description": "UUID of the workspace to list ICDs for.",
                    }
                },
                "required": ["workspace_id"],
            },
        },
    ]

    # ------------------------------------------------------------------
    # Shared workspace gate
    # ------------------------------------------------------------------

    @staticmethod
    def _deny_if_foreign(
        workspace_id: Any, auth_context: AuthContext
    ) -> Optional[ToolResult]:
        """Return PERMISSION_DENIED unless the caller holds a role in *workspace_id*."""
        if workspace_id in set(accessible_workspace_ids(auth_context)):
            return None
        return ToolResult.error(
            "PERMISSION_DENIED",
            "You do not hold an active role in the workspace owning this ICD.",
        )

    # ------------------------------------------------------------------
    # icd.get
    # ------------------------------------------------------------------

    def _handle_get(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """icd.get — one ICD with its current contract version."""
        icd_id = require_uuid(params, "icd_id")

        try:
            row = get_icd(icd_id, auth_context.tenant_id)
        except Icd.DoesNotExist:
            return ToolResult.error("NOT_FOUND", f"ICD '{icd_id}' not found.")

        denied = self._deny_if_foreign(row.workspace_id, auth_context)
        if denied is not None:
            return denied

        payload = _summary_to_dict(row)
        version = row.current_version
        if version is None:
            payload["version"] = None
        else:
            parameters = list(
                list_icd_parameters(version.id, auth_context.tenant_id)
            )
            payload["version"] = _version_to_dict(version, parameters)
        return ToolResult.ok({"icd": payload})

    # ------------------------------------------------------------------
    # icd.query
    # ------------------------------------------------------------------

    def _handle_query(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """icd.query — ICD summaries for one workspace."""
        workspace_id = require_uuid(params, "workspace_id")

        denied = self._deny_if_foreign(workspace_id, auth_context)
        if denied is not None:
            return denied

        rows = list_icds(workspace_id, auth_context.tenant_id)
        summaries = [_summary_to_dict(row) for row in rows]
        return ToolResult.ok({"icds": summaries, "count": len(summaries)})


__all__ = ["IcdToolGroup"]
```

- [ ] **Step 4: Register the group and mark `icd.get` read-only**

In `backend/mcp_server/tool_registry.py`, add inside `_READ_ONLY_TOOL_NAMES`:

```python
        # MCP-Modernisierung Task 8: ICD read tools (spec section 5).
        # icd.query is already exempt via the ".query" suffix; icd.get needs
        # the explicit entry or the fail-closed default (#99) gates it as a
        # write tool.
        "icd.get",
```

In `_ensure_groups`, add the import:

```python
        from mcp_server.tools.icd import IcdToolGroup
```

and this entry to the registration dict:

```python
            # MCP-Modernisierung Task 8: REST/MCP parity for ICDs (spec
            # section 5, audit chapter C6). Read-only MVP.
            "icd": IcdToolGroup(),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_icd_tool_group.py -v`
Expected: PASS (11 passed)

- [ ] **Step 6: Verify the manifest grew by exactly two tools**

Run:

```bash
docker compose exec backend python -c "
from mcp_server.management.commands.export_tool_manifest import build_manifest
m = build_manifest()
icd = [t['name'] for t in m['tools'] if t['prefix'] == 'icd']
print('tool_count =', m['tool_count'])
print('icd tools  =', icd)
print('write?     =', [t['is_write'] for t in m['tools'] if t['prefix'] == 'icd'])
print('phantom?   =', [t['name'] for t in m['tools'] if t['prefix'] in ('resource','prompt','tool')])
"
```

Expected: `icd tools = ['icd.get', 'icd.query']`, `write? = [False, False]`, `phantom? = []`, and `tool_count` exactly two higher than before Task 8.

- [ ] **Step 7: Run the ICD regression suite**

Run: `docker compose exec backend pytest icd/ mcp_server/tests/test_export_tool_manifest.py -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/mcp_server/tools/icd.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_icd_tool_group.py
git commit -m "feat(mcp): icd.get and icd.query for REST/MCP parity"
```

---

## Phase D — Manifest filters

### Task 9: `ApiKey.tool_groups` field and migration

**Files:**
- Modify: `backend/auth_tenancy/models.py` (`ApiKey`, `:62-108`)
- Create: `backend/auth_tenancy/migrations/00XX_apikey_tool_groups.py` (generated)
- Test: `backend/mcp_server/tests/test_api_key_tool_groups_filter.py` (model-level tests only in this task)

**Interfaces:**
- Consumes: nothing.
- Produces: `ApiKey.tool_groups: JSONField(default=list, blank=True)`; and, only if it is still missing, `ApiKey.scope: CharField(max_length=16, choices=[("read","Read"),("write","Write")], default="write")` exactly as defined in `docs/superpowers/specs/2026-09-03-ki-vorschlag-als-zustand-design.md:47`.

- [ ] **Step 1: Determine whether `ApiKey.scope` already exists**

Run:

```bash
docker compose exec backend python -c "
from auth_tenancy.models import ApiKey
names = [f.name for f in ApiKey._meta.fields]
print('scope       :', 'scope' in names)
print('tool_groups :', 'tool_groups' in names)
"
```

Record the answer. If `scope` is `True`, the KI-Vorschlag-als-Zustand plan (implementation order #4) has landed — skip its half of Step 3. If `False`, this task adds it too, using that spec's exact definition, and the field stays compatible when that plan merges later.

- [ ] **Step 2: Write the failing test**

Create `backend/mcp_server/tests/test_api_key_tool_groups_filter.py`:

```python
"""ApiKey.tool_groups / ApiKey.scope model contract (Task 9)."""
import pytest

from auth_tenancy.models import ApiKey


def _field(name):
    return ApiKey._meta.get_field(name)


def test_tool_groups_field_exists_with_list_default():
    field = _field("tool_groups")
    assert field.default is list
    assert field.blank is True


def test_scope_field_exists_with_write_default():
    field = _field("scope")
    assert field.default == "write"
    assert set(dict(field.choices)) == {"read", "write"}


@pytest.mark.django_db
def test_defaults_are_backwards_compatible(seeded_api_key):
    """An existing key keeps full visibility and write ability."""
    assert seeded_api_key.tool_groups == []
    assert seeded_api_key.scope == "write"
```

Add the `seeded_api_key` fixture to `backend/mcp_server/tests/conftest.py` only if an equivalent one is not already there — read that file plus `backend/mcp_server/tests/helpers.py` first and reuse whatever key-creation helper exists. If none does:

```python
@pytest.fixture
def seeded_api_key(db):
    """One active ApiKey created through the production service path."""
    from auth_tenancy.services.authentication import AuthenticationService
    from auth_tenancy.models import ApiKey
    from persistence.models import User

    user = User.objects.filter(is_active=True).exclude(tenant_id=None).first()
    result = AuthenticationService().create_api_key(
        user_id=user.id, tenant_id=user.tenant_id, name="tool-groups-test"
    )
    return ApiKey.unscoped.get(id=result.api_key_id)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_tool_groups_filter.py -v`
Expected: FAIL with `FieldDoesNotExist: ApiKey has no field named 'tool_groups'`

- [ ] **Step 4: Add the field(s) to the model**

In `backend/auth_tenancy/models.py`, add to `ApiKey` after `last_used_at` (`:93`):

```python
    tool_groups = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "MCP-Modernisierung spec section 6.2 — CATALOG CURATION ONLY, NOT "
            "A SECURITY BOUNDARY. A non-empty list of tool-group prefixes "
            "(e.g. [\"requirement\", \"traceability\"]) narrows what "
            "tools/list advertises to this key, which shrinks the client's "
            "context cost. It does NOT restrict what tools/call may execute: "
            "any tool this key's role and 'scope' allow stays callable by "
            "name. Use 'scope' for a real restriction. Empty list = every "
            "group, the pre-existing behaviour."
        ),
    )
```

If Step 1 reported `scope: False`, also add — verbatim from `docs/superpowers/specs/2026-09-03-ki-vorschlag-als-zustand-design.md:47`, extended only by a `help_text`:

```python
    scope = models.CharField(
        max_length=16,
        choices=[("read", "Read"), ("write", "Write")],
        default="write",
        help_text=(
            "KI-Vorschlag-als-Zustand spec — REAL SECURITY BOUNDARY. A key "
            "with scope='read' has every write tool hidden from tools/list "
            "AND rejected by tools/call with PERMISSION_DENIED, regardless of "
            "the owner's roles. Contrast 'tool_groups', which only changes "
            "what is advertised."
        ),
    )
```

- [ ] **Step 5: Generate and apply the migration**

Run:

```bash
docker compose exec backend python manage.py makemigrations auth_tenancy --name apikey_tool_groups
docker compose exec backend python manage.py migrate auth_tenancy
```

Expected: one new migration adding `tool_groups` (and `scope`, if Step 1 said it was missing). Both are additive with defaults, so no existing row is rewritten and no `RunPython` is needed. If `makemigrations` reports "No changes detected", the field edit did not save — re-check Step 4.

Migrations and the test database need the DB **owner** role, not the app role: if `migrate` silently no-ops or `pytest` reports permission errors, re-run with the owner credentials from `.env` and always pass `--create-db` on the first pytest run after a migration.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_tool_groups_filter.py -v --create-db`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/auth_tenancy/models.py backend/auth_tenancy/migrations/ backend/mcp_server/tests/test_api_key_tool_groups_filter.py backend/mcp_server/tests/conftest.py
git commit -m "feat(auth): add ApiKey.tool_groups for MCP manifest curation"
```

---

### Task 10: `ApiKeyPolicy` lookup seam

**Files:**
- Create: `backend/mcp_server/api_key_policy.py`
- Test: `backend/mcp_server/tests/test_api_key_scope_gate.py` (policy-lookup tests only in this task)

**Interfaces:**
- Consumes: `ApiKey.unscoped` (`backend/auth_tenancy/models.py:62`); `AuthContext.api_key_id: UUID | None` (`auth_tenancy/context.py:115`).
- Produces:
  - `@dataclass(frozen=True) class ApiKeyPolicy: scope: str = "write"; tool_groups: tuple[str, ...] = ()`
  - `ApiKeyPolicy.is_read_only: bool` (property)
  - `ApiKeyPolicy.allows_group(prefix: str) -> bool`
  - `get_api_key_policy(api_key_id: UUID | None) -> ApiKeyPolicy`

**Decision:** the policy is read with one indexed primary-key query rather than being threaded through `IdentityClaims` / `AuthContext`. Those two are project-wide identity contracts consumed by REST, Celery and the audit writer; hanging MCP-specific manifest-curation fields off them would ripple into every consumer and collide with the KI-Vorschlag-als-Zustand plan's own edits to the same dataclasses. One extra PK lookup per MCP call is negligible beside the role-resolution queries already on that path.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_api_key_scope_gate.py`:

```python
"""ApiKey.scope / tool_groups policy lookup and enforcement (Tasks 10-12)."""
import uuid

import pytest

from mcp_server.api_key_policy import ApiKeyPolicy, get_api_key_policy


def test_default_policy_is_permissive():
    policy = ApiKeyPolicy()
    assert policy.scope == "write"
    assert policy.tool_groups == ()
    assert policy.is_read_only is False
    assert policy.allows_group("anything") is True


def test_read_scope_is_read_only():
    assert ApiKeyPolicy(scope="read").is_read_only is True


def test_non_empty_tool_groups_narrow_the_catalog():
    policy = ApiKeyPolicy(tool_groups=("requirement", "traceability"))
    assert policy.allows_group("requirement") is True
    assert policy.allows_group("traceability") is True
    assert policy.allows_group("baseline") is False


def test_none_api_key_id_yields_the_default_policy():
    assert get_api_key_policy(None) == ApiKeyPolicy()


@pytest.mark.django_db
def test_unknown_api_key_id_yields_the_default_policy():
    assert get_api_key_policy(uuid.uuid4()) == ApiKeyPolicy()


@pytest.mark.django_db
def test_policy_is_read_from_the_row(seeded_api_key):
    seeded_api_key.scope = "read"
    seeded_api_key.tool_groups = ["requirement"]
    seeded_api_key.save(update_fields=["scope", "tool_groups"])

    policy = get_api_key_policy(seeded_api_key.id)
    assert policy.scope == "read"
    assert policy.tool_groups == ("requirement",)


@pytest.mark.django_db
def test_malformed_tool_groups_degrade_to_no_filter(seeded_api_key):
    """A non-list value must never silently hide the whole catalog."""
    seeded_api_key.tool_groups = "requirement"
    seeded_api_key.save(update_fields=["tool_groups"])
    assert get_api_key_policy(seeded_api_key.id).tool_groups == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_scope_gate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.api_key_policy'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/api_key_policy.py`:

```python
"""Per-API-key MCP policy: ``scope`` and ``tool_groups`` (spec section 6).

Two filters with deliberately different force, which the spec calls out as the
important distinction:

* ``scope="read"`` is a REAL security boundary — write tools are hidden from
  ``tools/list`` *and* rejected by ``tools/call``.
* ``tool_groups`` is PURE CATALOG CURATION — it only narrows what
  ``tools/list`` advertises, so a client carries fewer tokens of manifest.
  Every tool the key's role and ``scope`` allow stays callable by name.

Read via one indexed primary-key query instead of being threaded through
``IdentityClaims`` / ``AuthContext``: those are project-wide identity
contracts shared with REST, Celery and the audit writer, and MCP-specific
curation fields do not belong on them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

#: Value of ``ApiKey.scope`` that forbids every write tool.
SCOPE_READ = "read"


@dataclass(frozen=True)
class ApiKeyPolicy:
    """Effective MCP policy of one API key.

    Attributes:
        scope: ``"read"`` or ``"write"``. Anything other than ``"read"`` is
            treated as full write ability — fail-*open* is correct here
            because the RBAC gate remains the primary authority; this is an
            additional narrowing on top of it, never a replacement.
        tool_groups: Group prefixes to advertise. Empty means "every group",
            which is the pre-existing behaviour every key already has.
    """

    scope: str = "write"
    tool_groups: tuple[str, ...] = ()

    @property
    def is_read_only(self) -> bool:
        """Return whether this key may not execute write tools."""
        return self.scope == SCOPE_READ

    def allows_group(self, prefix: str) -> bool:
        """Return whether *prefix* may appear in this key's ``tools/list``."""
        if not self.tool_groups:
            return True
        return prefix in self.tool_groups


#: Returned whenever no key-specific policy can be read.
DEFAULT_POLICY = ApiKeyPolicy()


def get_api_key_policy(api_key_id: Optional[UUID]) -> ApiKeyPolicy:
    """Return the policy of *api_key_id*, or :data:`DEFAULT_POLICY`.

    Uses the ``unscoped`` manager: the key has already been authenticated by
    ``AuthenticationService.validate_api_key`` at this point, and the lookup
    is by primary key, so no tenant context is required — the same reasoning
    that manager is used for during authentication itself.

    Degrades to the permissive default on any lookup or shape problem. A
    malformed ``tool_groups`` value must not silently blank a caller's whole
    catalog, and a DB hiccup must not escalate into an MCP outage; the RBAC
    gate is untouched either way.
    """
    if api_key_id is None:
        return DEFAULT_POLICY

    try:
        from auth_tenancy.models import ApiKey

        row = (
            ApiKey.unscoped.filter(id=api_key_id)
            .values("scope", "tool_groups")
            .first()
        )
    except Exception:
        logger.exception("Failed to load ApiKey policy for %s", api_key_id)
        return DEFAULT_POLICY

    if row is None:
        return DEFAULT_POLICY

    raw_groups = row.get("tool_groups")
    if isinstance(raw_groups, list):
        groups = tuple(str(g) for g in raw_groups if isinstance(g, str) and g)
    else:
        groups = ()

    return ApiKeyPolicy(scope=str(row.get("scope") or "write"), tool_groups=groups)


__all__ = ["SCOPE_READ", "ApiKeyPolicy", "DEFAULT_POLICY", "get_api_key_policy"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_scope_gate.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/api_key_policy.py backend/mcp_server/tests/test_api_key_scope_gate.py
git commit -m "feat(mcp): ApiKeyPolicy lookup seam for scope and tool_groups"
```

---

### Task 11: Enforce `scope="read"` in `list_tools` and `dispatch_request`

**Files:**
- Modify: `backend/mcp_server/tool_registry.py` (`list_tools` `:604-676`, `dispatch_request` `:678-801`)
- Test: `backend/mcp_server/tests/test_api_key_scope_gate.py` (append)

**Interfaces:**
- Consumes: `get_api_key_policy(api_key_id) -> ApiKeyPolicy`, `ApiKeyPolicy.is_read_only` (Task 10); `ToolRegistry._is_write_tool(tool_name) -> bool` (existing, `:934`).
- Produces: no new public symbol; a `PERMISSION_DENIED` `ToolResult` for a write tool called with a read-scoped key.

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_api_key_scope_gate.py`:

```python
from unittest.mock import MagicMock, patch

from mcp_server.tool_registry import ToolRegistry


def _registry_with_policy(policy, *, can_write=True):
    """A ToolRegistry whose auth/roles are stubbed and whose policy is fixed."""
    registry = ToolRegistry()
    ctx = MagicMock()
    ctx.tenant_id = None
    ctx.api_key_id = uuid.uuid4()
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",) if can_write else ("viewer",)
    registry._validate_api_key = MagicMock(return_value=(ctx, None))
    registry._resolve_roles = MagicMock(return_value=ctx)
    registry._resolve_list_roles = MagicMock(return_value=ctx.active_roles)
    registry._authz_service = MagicMock()
    registry._authz_service.decide_access.return_value = MagicMock(allow=can_write)
    registry._is_tenant_admin_exempt = MagicMock(return_value=False)
    return registry


@pytest.mark.django_db
def test_read_scope_hides_write_tools_from_tools_list():
    registry = _registry_with_policy(ApiKeyPolicy(scope="read"))
    with patch(
        "mcp_server.tool_registry.get_api_key_policy",
        return_value=ApiKeyPolicy(scope="read"),
    ):
        tools = registry.list_tools(api_key="reqlo_dummy")
    names = [t["name"] for t in tools]
    assert names, "a read-scoped key must still see the read tools"
    assert all(not registry._is_write_tool(name) for name in names)


@pytest.mark.django_db
def test_write_scope_still_shows_write_tools():
    registry = _registry_with_policy(ApiKeyPolicy())
    with patch(
        "mcp_server.tool_registry.get_api_key_policy", return_value=ApiKeyPolicy()
    ):
        tools = registry.list_tools(api_key="reqlo_dummy")
    assert any(registry._is_write_tool(t["name"]) for t in tools)


@pytest.mark.django_db
def test_read_scope_rejects_a_write_tool_call():
    registry = _registry_with_policy(ApiKeyPolicy(scope="read"))
    with patch(
        "mcp_server.tool_registry.get_api_key_policy",
        return_value=ApiKeyPolicy(scope="read"),
    ):
        result = registry.dispatch_request(
            tool_name="requirement.create", params={}, api_key="reqlo_dummy"
        )
    assert not result.success
    assert result.error_code == "PERMISSION_DENIED"
    assert "scope" in result.message.lower()


@pytest.mark.django_db
def test_read_scope_still_allows_a_read_tool_call():
    registry = _registry_with_policy(ApiKeyPolicy(scope="read"))
    with patch(
        "mcp_server.tool_registry.get_api_key_policy",
        return_value=ApiKeyPolicy(scope="read"),
    ):
        result = registry.dispatch_request(
            tool_name="requirement.get", params={}, api_key="reqlo_dummy"
        )
    assert result.error_code != "PERMISSION_DENIED"


@pytest.mark.django_db
def test_read_scope_beats_the_bootstrap_exemption():
    """A read key must not reach the self-targeted admin bootstrap path."""
    registry = _registry_with_policy(ApiKeyPolicy(scope="read"))
    registry._is_bootstrap_candidate = MagicMock(return_value=True)
    with patch(
        "mcp_server.tool_registry.get_api_key_policy",
        return_value=ApiKeyPolicy(scope="read"),
    ):
        result = registry.dispatch_request(
            tool_name="user.assign_role", params={}, api_key="reqlo_dummy"
        )
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_read_scope_beats_the_tenant_admin_exemption():
    registry = _registry_with_policy(ApiKeyPolicy(scope="read"))
    registry._is_tenant_admin_exempt = MagicMock(return_value=True)
    with patch(
        "mcp_server.tool_registry.get_api_key_policy",
        return_value=ApiKeyPolicy(scope="read"),
    ):
        result = registry.dispatch_request(
            tool_name="user.create", params={}, api_key="reqlo_dummy"
        )
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.django_db
def test_unknown_tool_still_reports_unknown_tool_for_a_read_key():
    """The scope gate must sit after routing, so it cannot mask UNKNOWN_TOOL."""
    registry = _registry_with_policy(ApiKeyPolicy(scope="read"))
    with patch(
        "mcp_server.tool_registry.get_api_key_policy",
        return_value=ApiKeyPolicy(scope="read"),
    ):
        result = registry.dispatch_request(
            tool_name="nosuchgroup.create", params={}, api_key="reqlo_dummy"
        )
    assert result.error_code == "UNKNOWN_TOOL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_scope_gate.py -k scope -v`
Expected: FAIL — `test_read_scope_rejects_a_write_tool_call` gets `UNKNOWN_TOOL`/success instead of `PERMISSION_DENIED`; the gate does not exist yet.

- [ ] **Step 3: Import the policy in the registry**

Add to the imports at the top of `backend/mcp_server/tool_registry.py`:

```python
from mcp_server.api_key_policy import get_api_key_policy
```

- [ ] **Step 4: Filter `tools/list` on scope**

In `ToolRegistry.list_tools`, replace the write-tool hiding block (`:658-672`) with:

```python
            # Spec section 6.1: ApiKey.scope="read" is a real boundary, so it
            # narrows the manifest exactly like a missing WRITE role does.
            # ``policy`` is also what Task 12's tool_groups curation reads.
            policy = get_api_key_policy(auth_ctx.api_key_id)
            if not can_write or policy.is_read_only:
                # Hide write tools from read-only callers (Viewer role, or a
                # read-scoped key) — except the tenant-admin-elevated
                # ``user.*`` tools (_TENANT_ADMIN_ELEVATED_USER_TOOLS), which a
                # pure tenant-admin can actually execute via the same
                # ``_is_tenant_admin_exempt`` bypass ``dispatch_request``'s
                # Step 3 RBAC gate already applies. That elevation does NOT
                # survive a read scope, though: scope is a hard boundary the
                # dispatcher enforces before any exemption, so advertising
                # those tools to a read-scoped key would promise something
                # tools/call refuses.
                tools = [
                    t
                    for t in tools
                    if not self._is_write_tool(t.get("name", ""))
                    or (
                        not policy.is_read_only
                        and self._is_tenant_admin_exempt(t.get("name", ""), auth_ctx)
                    )
                ]
            return tools
```

- [ ] **Step 5: Enforce scope in `dispatch_request`**

In `ToolRegistry.dispatch_request`, insert immediately **after** the Step 2b routing block (right after the `if route_error: return ToolResult.error("UNKNOWN_TOOL", ...)` at `:744-745`) and **before** the Step 3 RBAC comment:

```python
            # --- Step 2c: API-key scope gate (spec section 6.1) ---
            # Placed after routing so an unknown tool still reports
            # UNKNOWN_TOOL rather than leaking a 403 for a name that does not
            # exist (same ordering rationale as Step 2b's own comment), and
            # before Step 3 so it outranks BOTH write-gate exemptions: a
            # read-scoped key must not reach the admin-bootstrap path
            # (_is_bootstrap_candidate) or the tenant-admin elevation
            # (_is_tenant_admin_exempt). Unlike tool_groups (section 6.2,
            # catalogue only), scope is enforced here on every call, whether
            # or not the caller learned the tool name from tools/list.
            if self._is_write_tool(tool_name) and get_api_key_policy(
                auth_ctx.api_key_id  # type: ignore[union-attr]
            ).is_read_only:
                return ToolResult.error(
                    "PERMISSION_DENIED",
                    f"Tool '{tool_name}' performs a write; this API key has "
                    "scope='read'. Issue a key with scope='write' to call it.",
                )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_scope_gate.py -v`
Expected: PASS (14 passed)

- [ ] **Step 7: Run the RBAC regression suites**

Run: `docker compose exec backend pytest mcp_server/tests/test_mcp_rbac_role_matrix.py mcp_server/tests/test_mcp_api_key_roles.py mcp_server/tests/test_mcp_workspace_scope.py -q`
Expected: PASS — a default (`scope="write"`) key must behave exactly as before.

- [ ] **Step 8: Commit**

```bash
git add backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_api_key_scope_gate.py
git commit -m "feat(mcp): enforce ApiKey.scope=read in tools/list and tools/call"
```

---

### Task 12: `tool_groups` catalog curation in `tools/list` only

**Files:**
- Modify: `backend/mcp_server/tool_registry.py` (`list_tools`)
- Test: `backend/mcp_server/tests/test_api_key_tool_groups_filter.py` (append)

**Interfaces:**
- Consumes: `ApiKeyPolicy.allows_group(prefix) -> bool` (Task 10); the `policy` local introduced in Task 11 Step 4.
- Produces: `mcp_server.tool_registry._ALWAYS_VISIBLE_TOOLS: frozenset[str]` — a **module-level** constant, not a class attribute (Task 13's test imports it directly from the module).

- [ ] **Step 1: Write the failing test**

Append to `backend/mcp_server/tests/test_api_key_tool_groups_filter.py`:

```python
import uuid
from unittest.mock import MagicMock, patch

from mcp_server.api_key_policy import ApiKeyPolicy
from mcp_server.tool_registry import ToolRegistry


def _registry():
    registry = ToolRegistry()
    ctx = MagicMock()
    ctx.tenant_id = None
    ctx.api_key_id = uuid.uuid4()
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    registry._validate_api_key = MagicMock(return_value=(ctx, None))
    registry._resolve_roles = MagicMock(return_value=ctx)
    registry._resolve_list_roles = MagicMock(return_value=ctx.active_roles)
    registry._authz_service = MagicMock()
    registry._authz_service.decide_access.return_value = MagicMock(allow=True)
    registry._is_tenant_admin_exempt = MagicMock(return_value=False)
    return registry


def _list_with(policy):
    registry = _registry()
    with patch("mcp_server.tool_registry.get_api_key_policy", return_value=policy):
        return registry, registry.list_tools(api_key="reqlo_dummy")


@pytest.mark.django_db
def test_empty_tool_groups_shows_every_group():
    _, tools = _list_with(ApiKeyPolicy())
    prefixes = {t["name"].split(".", 1)[0] for t in tools}
    assert len(prefixes) > 5


@pytest.mark.django_db
def test_tool_groups_narrows_the_manifest():
    _, tools = _list_with(ApiKeyPolicy(tool_groups=("requirement", "traceability")))
    prefixes = {t["name"].split(".", 1)[0] for t in tools}
    assert prefixes <= {"requirement", "traceability", "tool"}
    assert "requirement" in prefixes


@pytest.mark.django_db
def test_tool_groups_shrinks_the_manifest_measurably():
    _, everything = _list_with(ApiKeyPolicy())
    _, narrowed = _list_with(ApiKeyPolicy(tool_groups=("requirement",)))
    assert len(narrowed) < len(everything)


@pytest.mark.django_db
def test_tool_groups_never_blocks_a_call():
    """Spec section 6.2: curation is not a security boundary."""
    registry = _registry()
    with patch(
        "mcp_server.tool_registry.get_api_key_policy",
        return_value=ApiKeyPolicy(tool_groups=("requirement",)),
    ):
        result = registry.dispatch_request(
            tool_name="baseline.list", params={}, api_key="reqlo_dummy"
        )
    assert result.error_code != "PERMISSION_DENIED"


@pytest.mark.django_db
def test_unknown_group_name_does_not_empty_the_manifest():
    """A typo'd group must still leave the always-visible tools reachable."""
    _, tools = _list_with(ApiKeyPolicy(tool_groups=("typo_group",)))
    assert [t["name"] for t in tools] == ["tool.list_groups"]
```

`test_unknown_group_name_does_not_empty_the_manifest` and the `"tool"` allowance in `test_tool_groups_narrows_the_manifest` depend on Task 13. Expect them red until Task 13 Step 4 lands; every other test in this task must pass at Step 4 below.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_tool_groups_filter.py -k tool_groups -v`
Expected: FAIL — `test_tool_groups_narrows_the_manifest` sees every prefix; the filter does not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `backend/mcp_server/tool_registry.py`, add next to `_INSTANCE_LEVEL_TOOLS` (`:307`):

```python
# ---------------------------------------------------------------------------
# Tools exempt from the ApiKey.tool_groups catalogue filter (spec section 6.2).
#
# tool.list_groups is how a client discovers which groups exist in the first
# place, so filtering it out of a narrowed manifest would strand the caller:
# they would see a short menu and have no way to learn what else they could
# ask for. It is pure metadata (group names + counts), carries no tenant data
# and is read-only, so leaving it always visible costs nothing.
# ---------------------------------------------------------------------------

_ALWAYS_VISIBLE_TOOLS: frozenset[str] = frozenset({"tool.list_groups"})
```

In `list_tools`, insert this block directly after the scope-filter block from Task 11 Step 4 and before `return tools`:

```python
            # Spec section 6.2: ApiKey.tool_groups is CATALOGUE CURATION ONLY.
            # It changes what this key SEES, never what it may EXECUTE — there
            # is deliberately no counterpart to this block in
            # dispatch_request(). A key with narrow tool_groups loses no
            # ability; it just gets a smaller menu (fewer manifest tokens in
            # the client's context) and can still call any other permitted
            # tool directly by name.
            if policy.tool_groups:
                tools = [
                    t
                    for t in tools
                    if t.get("name", "") in _ALWAYS_VISIBLE_TOOLS
                    or policy.allows_group(t.get("name", "").split(".", 1)[0])
                ]
            return tools
```

Remove the now-duplicated `return tools` left over from Task 11 Step 4 so the method has exactly one exit inside the `try` block.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_tool_groups_filter.py -k "tool_groups and not unknown_group" -v`
Expected: PASS. `test_unknown_group_name_does_not_empty_the_manifest` stays red until Task 13.

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_api_key_tool_groups_filter.py
git commit -m "feat(mcp): curate tools/list by ApiKey.tool_groups (catalog only)"
```

---

### Task 13: `tool.list_groups` introspection tool

**Files:**
- Create: `backend/mcp_server/tools/introspection.py`
- Modify: `backend/mcp_server/tool_registry.py` (`_READ_ONLY_TOOL_NAMES`, `_ensure_groups`)
- Test: `backend/mcp_server/tests/test_introspection_tool_group.py`

**Interfaces:**
- Consumes: `ToolRegistry._ensure_groups()`, `ToolRegistry._groups: Dict[str, Any]`, `group.get_tool_schemas()` (existing); `_ALWAYS_VISIBLE_TOOLS` (Task 12).
- Produces: `mcp_server.tools.introspection.IntrospectionToolGroup` handling `tool.list_groups`.

- [ ] **Step 1: Write the failing test**

Create `backend/mcp_server/tests/test_introspection_tool_group.py`:

```python
"""tool.list_groups introspection tool (MCP-Modernisierung Task 13)."""
import uuid

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.introspection import IntrospectionToolGroup


def _ctx():
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
    )


def _run():
    return IntrospectionToolGroup().execute_tool(
        tool_name="tool.list_groups",
        params={},
        auth_context=_ctx(),
        api_key="reqlo_dummy",
    )


def test_group_exposes_exactly_one_tool():
    schemas = IntrospectionToolGroup().get_tool_schemas()
    assert [s["name"] for s in schemas] == ["tool.list_groups"]


def test_schema_takes_no_required_parameters():
    schema = IntrospectionToolGroup().get_tool_schemas()[0]
    assert schema["inputSchema"].get("required", []) == []


def test_returns_group_names_with_tool_counts():
    result = _run()
    assert result.success
    groups = {g["name"]: g for g in result.data["groups"]}
    assert groups["requirement"]["tool_count"] > 0
    assert result.data["count"] == len(result.data["groups"])


def test_payload_is_stdlib_json_encodable():
    import json

    json.dumps(_run().data)


def test_hides_the_invisible_capability_groups():
    """resource.* / prompt.* have no schemas, so they are not real groups."""
    names = {g["name"] for g in _run().data["groups"]}
    assert "resource" not in names
    assert "prompt" not in names


def test_includes_the_icd_group():
    groups = {g["name"]: g for g in _run().data["groups"]}
    assert groups["icd"]["tool_count"] == 2


def test_groups_are_sorted_by_name():
    names = [g["name"] for g in _run().data["groups"]]
    assert names == sorted(names)


def test_tool_is_read_only():
    from mcp_server.tool_registry import ToolRegistry

    assert ToolRegistry()._is_write_tool("tool.list_groups") is False


def test_tool_is_always_visible():
    from mcp_server.tool_registry import _ALWAYS_VISIBLE_TOOLS

    assert "tool.list_groups" in _ALWAYS_VISIBLE_TOOLS


def test_group_is_registered():
    from mcp_server.tool_registry import ToolRegistry

    registry = ToolRegistry()
    registry._ensure_groups()
    group, err = registry._router.route("tool.list_groups")
    assert err is None
    assert type(group).__name__ == "IntrospectionToolGroup"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest mcp_server/tests/test_introspection_tool_group.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mcp_server.tools.introspection'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/mcp_server/tools/introspection.py`:

```python
"""Tool-catalogue introspection (MCP-Modernisierung, spec section 6.2).

``tool.list_groups`` reports which tool groups exist and how many tools each
holds. It is always visible and never filtered by ``ApiKey.tool_groups`` (see
``mcp_server.tool_registry._ALWAYS_VISIBLE_TOOLS``): a client whose manifest was
narrowed still needs a way to learn what else it could ask for, and group names
plus counts are pure metadata — no tenant data, no security value.

Counts come from the registry's own schema build, so this cannot drift from
``tools/list``. Groups with no schemas (the ``resource``/``prompt`` capability
pseudo-tools) are omitted by construction: they are not part of the tool
surface at all.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from auth_tenancy.context import AuthContext

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.base import BaseToolGroup

logger = logging.getLogger(__name__)


class IntrospectionToolGroup(BaseToolGroup):
    """Catalogue metadata about the MCP tool surface (1 tool, read-only)."""

    _TOOL_MAP = {"tool.list_groups": "_handle_list_groups"}

    _TOOL_SCHEMAS = [
        {
            "name": "tool.list_groups",
            "description": (
                "List every MCP tool group with its tool count. Always "
                "visible, never narrowed by an API key's tool_groups "
                "curation — call it to discover which group names exist "
                "before configuring a key's tool_groups list. Note that "
                "tool_groups only changes what tools/list advertises; every "
                "tool your role and key scope permit stays callable by name."
            ),
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        }
    ]

    def _handle_list_groups(
        self, *, params: Dict[str, Any], auth_context: AuthContext, api_key: str
    ) -> ToolResult:
        """tool.list_groups — every group name with its tool count."""
        from mcp_server.tool_registry import ToolRegistry

        registry = ToolRegistry()
        registry._ensure_groups()

        counts: Dict[str, int] = {}
        seen_group_ids: set[int] = set()
        for group in registry._groups.values():
            if id(group) in seen_group_ids:
                continue
            seen_group_ids.add(id(group))
            if not hasattr(group, "get_tool_schemas"):
                continue
            for schema in group.get_tool_schemas():
                name = schema.get("name", "")
                if "." not in name:
                    continue
                prefix = name.split(".", 1)[0]
                counts[prefix] = counts.get(prefix, 0) + 1

        groups: List[Dict[str, Any]] = [
            {"name": prefix, "tool_count": count}
            for prefix, count in sorted(counts.items())
        ]
        return ToolResult.ok({"groups": groups, "count": len(groups)})


__all__ = ["IntrospectionToolGroup"]
```

Deduplicating by `id(group)` mirrors `list_tools` (`:643-654`) and `build_manifest`: several prefixes deliberately share one instance (`audit`/`events`, `traceability`/`artifact`), and counting per prefix instead would double-count their schemas.

- [ ] **Step 4: Register the group and mark the tool read-only**

In `backend/mcp_server/tool_registry.py`, add inside `_READ_ONLY_TOOL_NAMES`:

```python
        # MCP-Modernisierung Task 13: pure catalogue metadata, no tenant data.
        "tool.list_groups",
```

In `_ensure_groups`, add the import:

```python
        from mcp_server.tools.introspection import IntrospectionToolGroup
```

and this entry to the registration dict:

```python
            # MCP-Modernisierung Task 13: always-visible introspection so a
            # client with narrowed tool_groups can still discover what exists.
            "tool": IntrospectionToolGroup(),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_introspection_tool_group.py -v`
Expected: PASS (10 passed)

- [ ] **Step 6: Close out Task 12's deferred tests**

Run: `docker compose exec backend pytest mcp_server/tests/test_api_key_tool_groups_filter.py -v`
Expected: PASS in full, including `test_unknown_group_name_does_not_empty_the_manifest`.

- [ ] **Step 7: Verify the manifest by hand**

Run:

```bash
docker compose exec backend python -c "
from mcp_server.management.commands.export_tool_manifest import build_manifest
m = build_manifest()
print('tool_count =', m['tool_count'])
print('groups     =', sorted({t['prefix'] for t in m['tools']}))
print('introspect =', [t['name'] for t in m['tools'] if t['prefix'] == 'tool'])
"
```

Expected: `introspect = ['tool.list_groups']`; `groups` contains `icd` and `tool` and does **not** contain `resource` or `prompt`.

- [ ] **Step 8: Commit**

```bash
git add backend/mcp_server/tools/introspection.py backend/mcp_server/tool_registry.py backend/mcp_server/tests/test_introspection_tool_group.py
git commit -m "feat(mcp): add always-visible tool.list_groups introspection tool"
```

---

### Task 14: Expose `scope` and `tool_groups` on the API-key REST surface

**Files:**
- Modify: `backend/auth_tenancy/services/authentication.py` (`create_api_key` `:549`, `ApiKeyCreationResult` `:49`)
- Modify: `backend/rest_api/api_key_views.py` (`list` `:102`, `retrieve` `:117`, `create` `:162`)
- Test: `backend/rest_api/tests/test_api_key_views.py` (append; create the file if it does not exist)

**Interfaces:**
- Consumes: `ApiKey.scope`, `ApiKey.tool_groups` (Task 9).
- Produces:
  - `AuthenticationService.create_api_key(self, *, user_id: UUID, tenant_id: UUID, name: str, scope: str = "write", tool_groups: Optional[list[str]] = None) -> ApiKeyCreationResult`
  - `ApiKeyCreationResult.scope: str`, `ApiKeyCreationResult.tool_groups: tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

Read `backend/rest_api/api_key_views.py` and the existing API-key tests first, then append to `backend/rest_api/tests/test_api_key_views.py` (create it with the surrounding suite's fixtures/auth helper if absent):

```python
import pytest


@pytest.mark.django_db
def test_create_defaults_to_write_scope_and_no_curation(api_client_authenticated):
    response = api_client_authenticated.post(
        "/api/v1/api-keys/", {"name": "default-key"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["scope"] == "write"
    assert response.data["tool_groups"] == []


@pytest.mark.django_db
def test_create_accepts_read_scope_and_tool_groups(api_client_authenticated):
    response = api_client_authenticated.post(
        "/api/v1/api-keys/",
        {"name": "agent-key", "scope": "read", "tool_groups": ["requirement"]},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["scope"] == "read"
    assert response.data["tool_groups"] == ["requirement"]


@pytest.mark.django_db
def test_create_rejects_an_unknown_scope(api_client_authenticated):
    response = api_client_authenticated.post(
        "/api/v1/api-keys/", {"name": "bad", "scope": "admin"}, format="json"
    )
    assert response.status_code == 400
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_create_rejects_non_list_tool_groups(api_client_authenticated):
    response = api_client_authenticated.post(
        "/api/v1/api-keys/",
        {"name": "bad", "tool_groups": "requirement"},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_list_reports_scope_and_tool_groups(api_client_authenticated):
    api_client_authenticated.post(
        "/api/v1/api-keys/",
        {"name": "listed", "scope": "read", "tool_groups": ["requirement"]},
        format="json",
    )
    response = api_client_authenticated.get("/api/v1/api-keys/")
    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["name"] == "listed")
    assert row["scope"] == "read"
    assert row["tool_groups"] == ["requirement"]
```

Adjust the route prefix, the pagination envelope key (`results` vs a bare list) and the auth fixture name to match the existing suite — read one neighbouring REST test before writing these.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec backend pytest rest_api/tests/test_api_key_views.py -k "scope or tool_groups" -v`
Expected: FAIL with `KeyError: 'scope'` on the create response.

- [ ] **Step 3: Extend the creation service**

In `backend/auth_tenancy/services/authentication.py`, extend `ApiKeyCreationResult` (`:49`):

```python
    scope: str = "write"
    tool_groups: tuple[str, ...] = ()
```

and change `create_api_key`'s signature (`:549`) to:

```python
    def create_api_key(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        name: str,
        scope: str = "write",
        tool_groups: Optional[list[str]] = None,
    ) -> ApiKeyCreationResult:
```

Extend its docstring `Args:` block with:

```
            scope: ``"write"`` (default, unchanged behaviour) or ``"read"``.
                A read-scoped key cannot execute any write tool over MCP.
            tool_groups: Optional group prefixes to advertise in the MCP
                manifest. Catalogue curation only — it does not restrict what
                the key may execute (see ``ApiKey.tool_groups``).
```

Pass both through to the `ApiKey.objects.create(...)` / `ApiKey(...)` call inside the method:

```python
            scope=scope,
            tool_groups=list(tool_groups or []),
```

and include them in the returned `ApiKeyCreationResult`:

```python
            scope=scope,
            tool_groups=tuple(tool_groups or ()),
```

Add `Optional` to the module's `typing` import if it is not already there.

- [ ] **Step 4: Validate and surface the fields in the REST view**

In `backend/rest_api/api_key_views.py`, inside `create` (`:162`), after the existing `name` validation (`:189-193`):

```python
        scope = request.data.get("scope", "write")
        if scope not in ("read", "write"):
            return Response(
                build_error_response(
                    code="VALIDATION_ERROR",
                    message="Field 'scope' must be 'read' or 'write'.",
                ),
                status=400,
            )

        tool_groups = request.data.get("tool_groups", [])
        if not isinstance(tool_groups, list) or not all(
            isinstance(g, str) for g in tool_groups
        ):
            return Response(
                build_error_response(
                    code="VALIDATION_ERROR",
                    message="Field 'tool_groups' must be a list of group-name strings.",
                ),
                status=400,
            )
```

Pass them to the service call (`:201`) as `scope=scope, tool_groups=tool_groups`, and add to the 201 response body (`:212`):

```python
                "scope": result.scope,
                "tool_groups": list(result.tool_groups),
```

In `list` (`:102`) and `retrieve` (`:117`), add `"scope"` and `"tool_groups"` to the per-row payload each already builds. Read those two methods before editing — reuse whatever row-building helper they share rather than duplicating a dict.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker compose exec backend pytest rest_api/tests/test_api_key_views.py -v`
Expected: PASS.

- [ ] **Step 6: Run the auth regression suites**

Run: `docker compose exec backend pytest auth_tenancy/ rest_api/tests/test_api_key_views.py -q`
Expected: PASS — every existing `create_api_key(user_id=…, tenant_id=…, name=…)` caller keeps working, since both new parameters are keyword-only with defaults.

- [ ] **Step 7: Verify the whole gate end to end**

Run (paste a `reqlo_` key from a freshly created read-scoped key when prompted):

```bash
docker compose exec -it backend python manage.py shell -c "
import json
from django.test import Client
key = input('paste a scope=read reqlo_ key: ').strip()
c = Client()
def call(method, params=None):
    r = c.post('/mcp/', data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params or {}}),
               content_type='application/json', HTTP_X_API_KEY=key)
    return r.status_code, json.loads(r.content)
s, body = call('tools/list')
names = [t['name'] for t in body['result']['tools']]
print('visible tools    :', len(names))
print('any write listed :', any(n.endswith(('.create','.update','.delete')) for n in names))
print('list_groups here :', 'tool.list_groups' in names)
print('write call       :', call('tools/call', {'name':'requirement.create','arguments':{}}))
print('read call        :', call('tools/call', {'name':'artifact.search','arguments':{'query':'a'}})[0])
"
```

Expected: `any write listed` is `False`; `list_groups here` is `True`; the write call returns a JSON-RPC error with code `-32001` (`PERMISSION_DENIED`) mentioning `scope='read'`; the read call returns 200.

- [ ] **Step 8: Commit**

```bash
git add backend/auth_tenancy/services/authentication.py backend/rest_api/api_key_views.py backend/rest_api/tests/test_api_key_views.py
git commit -m "feat(api): expose ApiKey scope and tool_groups on the REST surface"
```

---

## Phase E — Documentation and manifest

### Task 15: Regenerate the tool manifest and document the scope/tool_groups distinction

**Files:**
- Regenerate: `docs/agent-templates/tool-manifest.json`
- Modify: the MCP documentation page (locate it in Step 2)
- Test: `backend/mcp_server/tests/test_export_tool_manifest.py` (existing; must stay green)

**Interfaces:**
- Consumes: `mcp_server.management.commands.export_tool_manifest.build_manifest() -> Dict[str, Any]`.
- Produces: no code symbol.

**Why this task exists:** spec §8 (risk 3) states explicitly that the `scope` vs `tool_groups` distinction must be made in the implementation's documentation, not only in the spec — otherwise `tool_groups` will be mistaken for a security feature.

- [ ] **Step 1: Regenerate the manifest**

Run:

```bash
docker compose exec backend python manage.py export_tool_manifest
```

Then verify the delta:

```bash
git diff --stat docs/agent-templates/tool-manifest.json
docker compose exec backend python -c "
import json, pathlib
m = json.loads(pathlib.Path('/app/docs/agent-templates/tool-manifest.json').read_text())
print('tool_count =', m['tool_count'])
print('new groups =', sorted({t['prefix'] for t in m['tools']} & {'icd','tool','resource','prompt'}))
"
```

Expected: `tool_count` exactly three higher than before this plan (`icd.get`, `icd.query`, `tool.list_groups`), and `new groups = ['icd', 'tool']` — `resource` and `prompt` must be absent.

- [ ] **Step 2: Locate the MCP documentation page**

Run:

```bash
grep -rln "tools/list\|MCP Server\|/mcp/" docs/*.md docs/**/*.md 2>/dev/null | head -20
```

Pick the page that documents the MCP server for integrators (likely `docs/MCP_SERVER.md` or a section of the API docs). Use that path in Step 3. If more than one candidate exists, edit the one the README links to.

- [ ] **Step 3: Document the two filters and the new surfaces**

Append this section to that page:

```markdown
## API-Key-Filter: `scope` vs. `tool_groups`

Zwei Felder auf einem API-Key beeinflussen die MCP-Oberfläche. Sie sehen
ähnlich aus, haben aber **grundlegend verschiedene Wirkung**:

| Feld | Wirkung auf `tools/list` | Wirkung auf `tools/call` | Sicherheitsgrenze? |
|---|---|---|---|
| `scope="read"` | Write-Tools werden ausgeblendet | Write-Tools werden **abgelehnt** (`PERMISSION_DENIED`) | **Ja** |
| `tool_groups=[...]` | Nur die gelisteten Gruppen erscheinen | **Keine** — jedes erlaubte Tool bleibt aufrufbar | **Nein** |

`tool_groups` ist reine **Katalog-Kuration**: ein Client, der nur einen
Ausschnitt braucht, bekommt ein kleineres Manifest und damit weniger Tokens im
Kontext. Der Key verliert dadurch **keine Fähigkeit** — er kann jedes andere
erlaubte Tool weiterhin direkt beim Namen aufrufen. Wer eine echte
Einschränkung braucht, setzt `scope="read"` oder entzieht die Rolle.

`tool.list_groups` ist immer sichtbar und wird von `tool_groups` nie gefiltert:
ein Client mit engem Katalog muss erfahren können, welche Gruppen es überhaupt
gibt.

## Protokoll und Transporte

- Protokollrevision: **2025-06-18**. Ältere Clients werden weiter bedient —
  `initialize` spiegelt eine unterstützte angefragte Revision zurück
  (`2025-06-18`, `2025-03-26`, `2024-11-05`).
- **Streamable HTTP** (empfohlen): `POST /mcp/`. Die Antwort ist JSON, oder ein
  einzelnes SSE-`message`-Event, wenn `Accept: text/event-stream` gesetzt ist.
  `initialize` liefert einen `Mcp-Session-Id`-Header zurück; der Client sendet
  ihn auf Folge-Requests und kann die Session mit `DELETE /mcp/` beenden.
- **Legacy SSE** (`GET /mcp/sse/` + `POST /mcp/messages/?session_id=...`)
  bleibt unverändert bestehen — Fallback-Pfad für Clients ohne
  Streamable-HTTP-Unterstützung.

## Capabilities

Neben `tools` meldet `initialize` jetzt `resources` und `prompts`:

- `resources/list`, `resources/read`, `resources/templates/list` —
  URI-Schema `reqogniloom://artifact/{id}`, liefert das Artefakt als Markdown.
  `resources/list` ist auf 200 Einträge pro Seite begrenzt (`cursor` für die
  nächste Seite).
- `prompts/list`, `prompts/get` — Lese-/Nutzungspfad auf das versionierte
  `PromptTemplate`-System. Die Verwaltung (`create`/`update`) bleibt bei der
  `prompt_template.*`-Tool-Gruppe.

Beide Capabilities laufen über dieselbe Auth-/RBAC-/Preset-Kette wie jedes
Tool, erscheinen aber bewusst nicht in `tools/list`.
```

- [ ] **Step 4: Add the same warning to the API-key REST docs**

If the REST API documentation lists the `POST /api/v1/api-keys/` body fields, add there:

```markdown
- `scope` (optional, `"read"` | `"write"`, default `"write"`) — **Sicherheitsgrenze.**
  `"read"` verbietet dem Key jeden schreibenden MCP-Tool-Aufruf.
- `tool_groups` (optional, Liste von Gruppennamen, default `[]`) — **keine
  Sicherheitsgrenze**, nur Manifest-Kuration. Siehe die Tabelle in der
  MCP-Dokumentation.
```

- [ ] **Step 5: Verify the manifest test still passes**

Run: `docker compose exec backend pytest mcp_server/tests/test_export_tool_manifest.py -v`
Expected: PASS — including the idempotence check (`tool_count` unchanged on a second export).

- [ ] **Step 6: Commit**

```bash
git add docs/agent-templates/tool-manifest.json docs/
git commit -m "docs(mcp): document scope vs tool_groups, 2025-06-18 transports, capabilities"
```

---

## Cross-cutting verification (run once, after Task 15)

- [ ] **Step 1: Run every suite this plan touched**

Run:

```bash
docker compose exec backend pytest \
  mcp_server/ application/tests/test_artifact_markdown.py \
  auth_tenancy/ icd/ rest_api/tests/test_api_key_views.py -q
```

Expected: PASS. Compare against the baseline recorded before Task 1 — this repo has a known set of pre-existing red tests, so judge by *new* failures, not by absolute green.

- [ ] **Step 2: Smoke-test both real clients (spec §8, risk 1)**

Point Claude Code and OpenCode at the running server (the same two clients that verified H1/H2) and confirm for each:
1. `initialize` succeeds and the client reports the tool count;
2. one read tool call succeeds;
3. the SSE fallback path still connects if StreamableHTTP is disabled in the client config.

Record the outcome in the PR description. Do not ship without this: it is the only check that covers the downgrade-compatibility risk the spec names.

- [ ] **Step 3: Confirm the Dokumentensicht hand-off**

Run:

```bash
docker compose exec backend python -c "
from application.artifact_markdown import render_artifact_markdown, ARTIFACT_MARKDOWN_MIME
print(render_artifact_markdown.__doc__.splitlines()[0])
print(ARTIFACT_MARKDOWN_MIME)
"
```

Expected: the renderer is importable under exactly `application.artifact_markdown.render_artifact_markdown(artifact_id, ctx)`. The Dokumentensicht spec's §4 ("ein Renderer, zwei Zugriffswege") consumes this signature — do not rename it there afterwards.

---

## OFFENE FRAGEN

**1. `ApiKey.scope` gehört zwei Plänen (nicht blockierend, Handhabung entschieden).**
Die KI-Vorschlag-als-Zustand-Spec (Reihenfolge #4) definiert `ApiKey.scope`; dieser Plan (#7) konsumiert es. Der Plan zu #4 existiert noch nicht, das Feld ist im Code nicht vorhanden. Task 9 Step 1 prüft das zur Laufzeit und legt das Feld nur an, falls es fehlt — mit der wörtlichen Definition aus jener Spec, damit beide Pläne in beliebiger Reihenfolge zusammenpassen. **Wenn #4 zwischenzeitlich gemergt wird, entfällt nur der zweite Teil von Task 9 Step 4.** Kein Blocker, aber die Migrationsnummer kollidiert, falls beide Pläne gleichzeitig laufen — dann `makemigrations --merge`.

**2. `resources/list`-Semantik ist unterspezifiziert (entschieden, nicht blockierend).**
Die Spec nennt `resources/list`, sagt aber nicht, *welche* Artefakte gelistet werden — bei einem großen Tenant wäre eine vollständige Aufzählung genau die Kontextkosten-Explosion, die diese Spec reduzieren will. **Entscheidung:** gedeckelte Seite (Default 100, Maximum 200, `cursor`-Paginierung), begrenzt auf die Workspaces, in denen der Aufrufer eine aktive Rolle hat — dieselbe Eingrenzung, die `artifact.search` und `prompt_template.list` bereits anwenden. `resources/templates/list` bleibt der eigentliche Einstieg für gezielte Zugriffe.

**3. `prompts/get`-Argumente (entschieden, nicht blockierend).**
MCP-Prompts können deklarierte `arguments` haben; die `PromptTemplate`-Inhalte enthalten `{{...}}`-Platzhalter, deren Katalog in `application/prompt_variables.py` liegt. **Entscheidung:** MVP meldet `arguments: []` und liefert den Template-Text unverändert. Eine Ableitung der Argumentliste aus dem Variablenkatalog wäre eine zweite, still divergierende Kopie dieses Katalogs — sinnvoller Ausbau, sobald der Bedarf real ist, nicht Teil dieser Spec.

**4. Echte blockierende Frage: keine.**
Alle drei zu verifizierenden Punkte aus dem Auftrag wurden am Code geprüft (siehe "Spec corrections"); die einzigen Spec-Fehler (`TenantToolRegistry`, `artifact.get`/`McpArtifactProvider`) sind im Plan korrigiert und ändern nur den Umfang von Task 5, nicht das Ziel.
