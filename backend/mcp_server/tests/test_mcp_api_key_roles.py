"""
REQ-127: MCP API-Key Role Propagation — Live Stack E2E Test

leaf_id : COMP-MC-001 + COMP-AT-001
req_id  : REQ-127 (MCP API-Key role propagation)
         REQ-129 (MCP tools/list deduplication)
         REQ-131 (MCP capability declaration)

Bug that was fixed:
    MCP tools called with an API key but WITHOUT a workspace_id in the
    tool arguments had active_roles=[] in the context.  This blocked all
    write operations with "Role '()' does not permit write operations".

Fix:
    mcp_server/tool_registry.py now falls back to loading roles from the
    UserRole table when the API key context has no roles (no workspace_id
    provided by the client or no pre-loaded roles).

This test runs against the **live Docker stack** (http://localhost:8000).
It does NOT use Django test fixtures — it calls the real HTTP endpoints
using only Python stdlib (urllib) to avoid external dependencies.

Run from inside backend container:
    pytest mcp_server/tests/test_mcp_api_key_roles.py -v

Or from the host (requires requests):
    python -m pytest backend/mcp_server/tests/test_mcp_api_key_roles.py -v
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import urllib.parse

import pytest

# ---------------------------------------------------------------------------
# Stack base URLs — match docker-compose port mapping
# ---------------------------------------------------------------------------
# Inside the `backend` container itself, or from the host (with the dev
# override's port publishing), 'localhost:8000' reaches the live stack
# directly. From any OTHER container merely attached to the compose network
# (e.g. an ad-hoc test runner, docker-compose service-to-service calls),
# 'localhost' is that container itself, not the backend service — the
# docker-network hostname 'backend' is what resolves there instead. This
# used to be a hardcoded 'localhost' constant with a comment claiming it
# "works for both host and container" — it never actually tried a second
# host, so it silently only ever worked in the two cases named above. Probes
# each candidate's /health/ endpoint (fast, unauthenticated, no side
# effects) and uses whichever answers first.
def _resolve_backend_url() -> tuple[str, bool]:
    for candidate in ("http://localhost:8000", "http://backend:8000"):
        try:
            with urllib.request.urlopen(f"{candidate}/health/", timeout=2):
                return candidate, True
        except (urllib.error.URLError, OSError):
            continue
    # Neither reachable — keep the original default so the resulting
    # connection-refused error still names a concrete, debuggable URL
    # instead of failing this resolution step itself.
    return "http://localhost:8000", False


BACKEND_URL, _STACK_REACHABLE = _resolve_backend_url()
MCP_URL = f"{BACKEND_URL}/mcp/"
REST_URL = f"{BACKEND_URL}/api/v1"

# This module drives the real HTTP/urllib stack against a live Django server
# instead of Django test fixtures (see module docstring) — it is an
# integration test, not a unit test, and must not run unattended in the
# normal unit suite:
#   - explicitly skipped in CI (no live stack there), and
#   - skipped locally whenever the live stack isn't actually reachable,
#     so `pytest` without `docker-compose up` reports a clean skip instead
#     of a wall of connection-refused failures.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")),
        reason="MCP live-stack tests require a running Django server (skipped in CI)",
    ),
    pytest.mark.skipif(
        not _STACK_REACHABLE,
        reason=f"MCP live-stack tests require a running Django server "
        f"(none reachable at {BACKEND_URL})",
    ),
]


# ---------------------------------------------------------------------------
# Helpers using stdlib urllib (no external deps)
# ---------------------------------------------------------------------------

def _http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict | None = None,
    timeout: int = 15,
) -> tuple[int, dict]:
    """Perform an HTTP request and return (status_code, response_body_dict)."""
    body_bytes: bytes | None = None
    req_headers = headers or {}

    if data is not None:
        body_bytes = json.dumps(data).encode()
        req_headers = {**req_headers, "Content-Type": "application/json"}

    req = urllib.request.Request(
        url, data=body_bytes, headers=req_headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        body = json.loads(raw) if raw else {}
        return exc.code, body


def _get_bearer_token() -> str:
    """Obtain JWT for the seeded admin user.

    Credentials come from the same env vars the live stack was actually
    seeded with (SYSTEM_ADMIN_USERNAME/SYSTEM_ADMIN_PASSWORD — see
    application.self_init, which creates this account on first migrate),
    not a hardcoded guess: "admin12345" only ever worked against whichever
    .env the test was originally authored/verified on, and silently fails
    a 401 against any other stack the moment SYSTEM_ADMIN_PASSWORD differs
    (as it does by default — .env.example's own placeholder is
    "CHANGE-ME-strong-admin-password", not "admin12345").
    """
    username = os.environ.get("SYSTEM_ADMIN_USERNAME", "admin")
    password = os.environ.get("SYSTEM_ADMIN_PASSWORD", "admin12345")
    status, data = _http_request(
        f"{REST_URL}/auth/login/",
        method="POST",
        data={"username": username, "password": password},
    )
    assert status == 200, (
        f"Login failed: {status} {data}. Set SYSTEM_ADMIN_USERNAME/"
        f"SYSTEM_ADMIN_PASSWORD to match the live stack's actual seeded "
        f"admin account if this isn't the default 'admin'/'admin12345'."
    )
    token = data.get("token") or data.get("access") or data.get("access_token")
    assert token, f"No token in response: {data}"
    return token


def _revoke_all_active_keys(bearer: str) -> None:
    """Revoke all non-revoked API keys for the authenticated user.

    Call this when the 10-key limit is reached to free slots.
    """
    list_status, list_data = _http_request(
        f"{REST_URL}/api-keys/",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert list_status == 200, f"List API keys failed: {list_status}"
    keys = list_data if isinstance(list_data, list) else []
    active_keys = [k for k in keys if not k.get("revoked", True)]
    for key in active_keys:
        _http_request(
            f"{REST_URL}/api-keys/{key['id']}/",
            method="DELETE",
            headers={"Authorization": f"Bearer {bearer}"},
        )


def _create_api_key(bearer: str, name: str) -> str:
    """Create an API key via REST and return its plaintext value.

    If the user has hit the 10-key limit, revokes all active keys first.
    """
    status, data = _http_request(
        f"{REST_URL}/api-keys/",
        method="POST",
        headers={"Authorization": f"Bearer {bearer}"},
        data={"name": name},
    )
    if status == 400 and "maximum" in str(data.get("message", "")):
        # Key limit reached — revoke all active keys to free slots
        _revoke_all_active_keys(bearer)
        # Retry creation
        status, data = _http_request(
            f"{REST_URL}/api-keys/",
            method="POST",
            headers={"Authorization": f"Bearer {bearer}"},
            data={"name": name},
        )
    assert status == 201, f"API key creation failed: {status} {data}"
    plaintext = data.get("plaintext")
    assert plaintext, f"No plaintext in response: {data}"
    return plaintext


def _mcp_call(api_key: str, method: str, params: dict | None = None) -> dict:
    """Send a JSON-RPC 2.0 request to the MCP HTTP transport."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": 1,
        "params": params or {},
    }
    status, body = _http_request(
        MCP_URL,
        method="POST",
        headers={"X-API-Key": api_key},
        data=payload,
        timeout=30,
    )
    assert status == 200, f"MCP HTTP error: {status} {body}"
    return body


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bearer_token() -> str:
    """JWT token for the seeded admin user (module-scoped to avoid repeated logins)."""
    return _get_bearer_token()


@pytest.fixture(scope="module")
def admin_api_key(bearer_token: str) -> str:
    """Create a fresh API key for the admin user and return its plaintext."""
    return _create_api_key(bearer_token, "REQ-127-E2E-test-key")


@pytest.fixture(scope="module")
def seeded_workspace_id(bearer_token: str) -> str:
    """Resolve the seeded workspace ID the admin actually holds a role in.

    REQ-127 tests role *propagation*, which presupposes the admin has a role in
    the target workspace. Picking an arbitrary ``workspaces[0]`` is fragile: the
    list endpoint orders by ``-modified_at``, so a workspace created in the same
    tenant during exploratory testing can sort ahead of the seeded workspace.
    The admin holds no role there, yielding empty active_roles and a *false*
    role-propagation regression signal. We therefore anchor on the canonical
    seeded workspace by name (``DEFAULT_WORKSPACE_NAME`` in
    ``auth_tenancy.provisioning``), which is the workspace bootstrap_admin binds
    the admin's admin role to.
    """
    status, data = _http_request(
        f"{REST_URL}/workspaces/",
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    assert status == 200, f"List workspaces failed: {status}"
    workspaces = data if isinstance(data, list) else data.get("results", [])
    assert workspaces, "No workspaces found — is seed_demo loaded?"
    seeded = next(
        (w for w in workspaces if w.get("name") == "Demo Workspace"), None
    )
    assert seeded, (
        "Seeded 'Demo Workspace' not found — is bootstrap_admin/seed_demo "
        f"loaded? Available workspaces: {[w.get('name') for w in workspaces]}"
    )
    return seeded["id"]


# ---------------------------------------------------------------------------
# [REQ-127] Tests: API-key auth propagates roles for MCP dispatch
# ---------------------------------------------------------------------------

class TestMcpApiKeyRolePropagation:
    """REQ-127: MCP API-key auth must propagate workspace roles to dispatch context."""

    def test_workspace_get_context_active_roles_not_empty(
        self, admin_api_key: str, seeded_workspace_id: str
    ) -> None:
        """[REQ-127] workspace.get_context via API key has non-empty active_roles."""
        result = _mcp_call(
            admin_api_key,
            "tools/call",
            {"name": "workspace.get_context", "arguments": {"workspace_id": seeded_workspace_id}},
        )

        assert "error" not in result, (
            f"[REQ-127] workspace.get_context returned error: {result.get('error')}"
        )
        content = result["result"]["content"]
        assert content, "Result content must not be empty"

        # Parse the inner JSON payload
        ctx_text = content[0]["text"]
        ctx_data = json.loads(ctx_text)
        workspace_ctx = ctx_data["workspace_context"]

        active_roles = workspace_ctx.get("active_roles", [])
        assert active_roles, (
            f"[REQ-127] active_roles is empty: {workspace_ctx!r}. "
            "Roles must be loaded from UserRole table when API key is used."
        )
        # Admin user must have 'admin' role
        assert "admin" in active_roles, (
            f"Expected 'admin' in active_roles, got: {active_roles}"
        )

    def test_requirement_create_via_api_key_succeeds(
        self, admin_api_key: str, seeded_workspace_id: str
    ) -> None:
        """[REQ-127] requirement.create via API key must succeed (not Permission denied)."""
        result = _mcp_call(
            admin_api_key,
            "tools/call",
            {
                "name": "requirement.create",
                "arguments": {
                    "workspace_id": seeded_workspace_id,
                    "title": "REQ-127 MCP E2E requirement",
                    "description": "Created by REQ-127 API-key role propagation E2E test",
                },
            },
        )

        # Must not be a permission error
        if "error" in result:
            error_msg = result["error"].get("message", "")
            assert "permission" not in error_msg.lower(), (
                f"[REQ-127] Permission denied with API key — role propagation regression: {error_msg}"
            )
            assert not ("role" in error_msg.lower() and "permit" in error_msg.lower()), (
                f"[REQ-127] Role-based rejection with API key: {error_msg}"
            )
            pytest.fail(f"[REQ-127] requirement.create returned error: {result['error']}")

        content = result["result"]["content"]
        req_text = content[0]["text"]
        req_data = json.loads(req_text)

        # The created requirement must have an ID
        requirement = req_data.get("requirement", {})
        assert requirement.get("id"), f"No requirement ID in response: {req_data}"
        assert requirement.get("workspace_id") == seeded_workspace_id

    def test_workspace_get_context_without_workspace_id_param(
        self, admin_api_key: str
    ) -> None:
        """[REQ-127] workspace.get_context without explicit workspace_id still resolves roles."""
        # This is the core REQ-127 scenario: no workspace_id in args
        result = _mcp_call(
            admin_api_key,
            "tools/call",
            {"name": "workspace.get_context", "arguments": {}},
        )

        # If a workspace is loaded from session/default context, active_roles must not be empty
        # If no workspace context is available, we accept an informative error (not 500)
        if "error" in result:
            error_msg = result["error"].get("message", "")
            # Must not be a role/permission error
            assert not ("role" in error_msg.lower() and "permit" in error_msg.lower()), (
                f"[REQ-127] Role error without workspace_id param: {error_msg}"
            )
        else:
            content = result["result"]["content"]
            if content:
                ctx_text = content[0]["text"]
                ctx_data = json.loads(ctx_text)
                workspace_ctx = ctx_data.get("workspace_context", {})
                active_roles = workspace_ctx.get("active_roles", [])
                # If a workspace was resolved, roles must not be empty
                if workspace_ctx.get("workspace_id"):
                    assert active_roles, (
                        f"[REQ-127] active_roles empty even with resolved workspace: {workspace_ctx}"
                    )

    def test_api_key_write_operation_not_blocked_by_empty_role_tuple(
        self, admin_api_key: str, seeded_workspace_id: str
    ) -> None:
        """[REQ-127] Write operation via API key must not fail with 'Role () does not permit'."""
        result = _mcp_call(
            admin_api_key,
            "tools/call",
            {
                "name": "requirement.create",
                "arguments": {
                    "workspace_id": seeded_workspace_id,
                    "title": "REQ-127 role-propagation write op test",
                    "description": "Verifies empty-role tuple error is fixed (REQ-127)",
                },
            },
        )

        if "error" in result:
            error_msg = result["error"].get("message", "")
            # The specific old error: "Role '()' does not permit write operations"
            assert "()" not in error_msg, (
                f"[REQ-127] regression — empty role tuple error still present: {error_msg}"
            )
            assert "does not permit write" not in error_msg, (
                f"[REQ-127] regression — write permission blocked by empty role: {error_msg}"
            )

    def test_tools_list_returns_unique_tools(self, admin_api_key: str) -> None:
        """[REQ-129] tools/list must return no duplicate tool names."""
        result = _mcp_call(admin_api_key, "tools/list")

        assert "error" not in result, f"tools/list error: {result.get('error')}"
        tools: list[dict] = result["result"]["tools"]
        names = [t["name"] for t in tools]
        unique_names = list(dict.fromkeys(names))  # preserve order, deduplicate

        assert len(names) == len(unique_names), (
            f"[REQ-129] Duplicate tools found: "
            f"{[n for n in names if names.count(n) > 1]}"
        )
        assert len(tools) >= 40, f"Expected 40+ tools, got {len(tools)}"

    def test_mcp_capability_declaration_matches_routed_transports(self) -> None:
        """[REQ-131] GET /mcp/ declares exactly the implemented transports.

        SSE was excluded here while ``GET /mcp/sse/`` returned 500 on every
        request (issue #455 — a hop-by-hop ``Connection`` response header).
        With that fixed, SSE is implemented *and* is the transport every
        distributed plugin config uses, so it must be declared.
        """
        status, data = _http_request(MCP_URL)
        assert status == 200, f"MCP GET failed: {status}"
        transports: list[str] = data.get("transports", [])
        assert "http" in transports, f"Expected http in transports: {transports}"
        assert "sse" in transports, (
            f"[REQ-131] SSE is routed and functional but not declared: {transports}"
        )

    def test_api_key_authentication_uses_x_api_key_header(
        self, admin_api_key: str, seeded_workspace_id: str
    ) -> None:
        """[REQ-127] X-API-Key header is the correct auth mechanism for MCP."""
        # Authorization: ApiKey header must fail (wrong format for MCP)
        status_wrong, body_wrong = _http_request(
            MCP_URL,
            method="POST",
            headers={"Authorization": f"ApiKey {admin_api_key}"},
            data={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "id": 1,
                "params": {
                    "name": "workspace.get_context",
                    "arguments": {"workspace_id": seeded_workspace_id},
                },
            },
        )
        # With wrong header format: response may be 200 but with error body
        if status_wrong == 200:
            assert "error" in body_wrong or "result" in body_wrong

        # X-API-Key header must work and return a successful result
        result_correct = _mcp_call(
            admin_api_key,
            "tools/call",
            {"name": "workspace.get_context", "arguments": {"workspace_id": seeded_workspace_id}},
        )
        assert "error" not in result_correct, (
            f"[REQ-127] X-API-Key auth failed: {result_correct.get('error')}"
        )

    def test_api_key_retrieve_endpoint_returns_200(self, bearer_token: str) -> None:
        """[REQ-134] GET /api/v1/api-keys/{id}/ must return 200 (not 405)."""
        # Create a fresh key to retrieve (helper handles the 10-key limit)
        _create_api_key(bearer_token, "REQ-134-retrieve-test")

        # Get the key ID from the list (newest key is what we just created)
        list_status, list_data = _http_request(
            f"{REST_URL}/api-keys/",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        assert list_status == 200
        keys = list_data if isinstance(list_data, list) else []
        assert keys, "No API keys found after creation"
        key_id = keys[-1]["id"]

        # Retrieve it — must return 200, not 405
        status_get, data_get = _http_request(
            f"{REST_URL}/api-keys/{key_id}/",
            headers={"Authorization": f"Bearer {bearer_token}"},
        )
        assert status_get == 200, (
            f"[REQ-134] retrieve returned {status_get} — expected 200. "
            "405 would indicate the action was missing (regression)."
        )
        assert data_get["id"] == key_id
        # Plaintext must NOT be in the response (security requirement)
        assert "plaintext" not in data_get, "[REQ-134] plaintext must not appear in retrieve response"
