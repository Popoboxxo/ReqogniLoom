"""
REQ-127: MCP API-Key Role Propagation — in-process tests.

leaf_id : COMP-MC-001 + COMP-AT-001
req_id  : REQ-127 (MCP API-key role propagation)

Bug that was fixed:
    MCP tools called with an API key but WITHOUT a workspace_id in the
    tool arguments had active_roles=[] in the context.  This blocked all
    write operations with "Role '()' does not permit write operations".

Fix:
    mcp_server/tool_registry.py now falls back to loading roles from the
    UserRole table when the API key context has no roles (no workspace_id
    provided by the client or no pre-loaded roles).

How this suite used to run (issue #1102):
    It talked HTTP/urllib to a RUNNING Django stack (localhost:8000) with
    a seeded "Demo Workspace", and was guarded with
    ``skipif(CI or GITHUB_ACTIONS)``.  Result: skipped in CI, and broken
    locally whenever the local stack lacked the seed data (4 errors in the
    27.09.2026 QA sweep).  A real regression in role propagation went
    unnoticed in BOTH environments.

How it runs now:
    In-process against the Django test DB, reusing the established MCP
    e2e harness of this package:
      * tests/conftest.py — tenant / workspace / user / UserRole /
        ApiKey / pre-wired ``django.test.Client`` (``admin_client``
        carries the ``X-API-Key`` header like the live HTTP test did),
      * tests/helpers.py — ``make_jsonrpc_request`` / ``extract_result``
        / ``extract_error_code``.
    Requests go through the full vertical stack (URL routing ->
    ``McpHttpTransportView`` -> ``ProtocolHandler`` -> ``ToolRegistry``
    -> real tool group -> application service), so the coverage is the
    same the HTTP version exercised — same roles, same mapping, same
    assertions, no HTTP and no live stack.  No ``skipif``: these tests
    run everywhere, including CI.

Role coverage: admin (positive path + global-fallback path), viewer
(negative path — the role propagates AND still blocks writes), plus a
deliberately broken role-propagation probe (mutation guard) proving the
suite catches the original REQ-127 failure mode.

Run from inside backend container:
    pytest mcp_server/tests/test_mcp_api_key_roles.py -v
"""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Dict, Optional

import pytest
from django.test import Client

from auth_tenancy.models import UserRole
from mcp_server.tests.helpers import (
    extract_error_code,
    extract_result,
    make_jsonrpc_request,
)
from persistence.models import Workspace

# SYSTEMAUDIT SA-62: same classification as the `test_e2e_*` family — a full
# vertical slice in-process against the pytest-django test DB (no live stack,
# part of the regular suite; `e2e` is a selection marker, not an exclusion).
pytestmark = [pytest.mark.e2e, pytest.mark.django_db]


# ---------------------------------------------------------------------------
# In-process MCP request helper
# ---------------------------------------------------------------------------


def _tools_call(
    client: Client, tool_name: str, arguments: Optional[Dict[str, Any]] = None
):
    """POST a standard MCP ``tools/call`` frame via the Django test client.

    The ``X-API-Key`` header rides on ``client.defaults`` (set by the
    ``admin_client``/``viewer_client`` fixtures in conftest.py), exactly
    like the live HTTP test sent it.  Returns the Django response object.
    """
    return client.post(
        "/mcp/",
        data=make_jsonrpc_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}},
        ),
        content_type="application/json",
    )


def _tools_call_error_message(response) -> str:
    """Error message of a protocol-level (auth/RBAC) JSON-RPC error frame."""
    body = response.json()
    assert "error" in body, f"Expected a JSON-RPC error, got: {body}"
    return body["error"].get("message", "")


def _call_result_text(response, tool_name: str) -> Dict[str, Any]:
    """Parse the inner JSON payload of a successful MCP tool result.

    On the ``tools/call`` surface the handler's payload is wrapped in an
    MCP content block: ``result.content[0].text`` holds the JSON dump of
    the tool's data — the same shape the live HTTP test parsed.
    """
    result = extract_result(response)
    content = result.get("content") or []
    assert content, f"[REQ-127] {tool_name} result content must not be empty"
    return json.loads(content[0]["text"])


# ---------------------------------------------------------------------------
# [REQ-127] Tests: API-key auth propagates roles for MCP dispatch
# ---------------------------------------------------------------------------


class TestMcpApiKeyRolePropagation:
    """REQ-127: MCP API-key auth must propagate workspace roles to dispatch context."""

    def test_workspace_get_context_active_roles_not_empty(
        self,
        admin_client: Client,
        e2e_workspace: Workspace,
        e2e_userrole_admin: UserRole,
    ) -> None:
        """[REQ-127] workspace.get_context via API key has non-empty active_roles."""
        response = _tools_call(
            admin_client,
            "workspace.get_context",
            {"workspace_id": str(e2e_workspace.id)},
        )

        assert "error" not in response.json(), (
            f"[REQ-127] workspace.get_context returned error: "
            f"{response.json().get('error')}"
        )
        ctx_data = _call_result_text(response, "workspace.get_context")
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
        self,
        admin_client: Client,
        e2e_workspace: Workspace,
        e2e_userrole_admin: UserRole,
    ) -> None:
        """[REQ-127] requirement.create via API key must succeed (not Permission denied)."""
        response = _tools_call(
            admin_client,
            "requirement.create",
            {
                "workspace_id": str(e2e_workspace.id),
                "title": "REQ-127 in-process requirement",
                "description": "Created by REQ-127 API-key role propagation test",
            },
        )

        body = response.json()
        # Must not be a permission error
        if "error" in body:
            error_msg = body["error"].get("message", "")
            assert "permission" not in error_msg.lower(), (
                f"[REQ-127] Permission denied with API key — role propagation "
                f"regression: {error_msg}"
            )
            assert not ("role" in error_msg.lower() and "permit" in error_msg.lower()), (
                f"[REQ-127] Role-based rejection with API key: {error_msg}"
            )
            pytest.fail(f"[REQ-127] requirement.create returned error: {body['error']}")

        req_data = _call_result_text(response, "requirement.create")

        # The created requirement must have an ID
        requirement = req_data.get("requirement", {})
        assert requirement.get("id"), f"No requirement ID in response: {req_data}"
        assert requirement.get("workspace_id") == str(e2e_workspace.id)

    def test_workspace_get_context_without_workspace_id_param(
        self,
        admin_client: Client,
        e2e_userrole_admin: UserRole,
    ) -> None:
        """[REQ-127] workspace.get_context without explicit workspace_id still resolves roles."""
        # This is the core REQ-127 scenario: no workspace_id in args
        response = _tools_call(admin_client, "workspace.get_context", {})

        body = response.json()
        # If a workspace is loaded from session/default context, active_roles must not be empty
        # If no workspace context is available, we accept an informative error (not 500)
        if "error" in body:
            error_msg = body["error"].get("message", "")
            # Must not be a role/permission error
            assert not ("role" in error_msg.lower() and "permit" in error_msg.lower()), (
                f"[REQ-127] Role error without workspace_id param: {error_msg}"
            )
        else:
            ctx_data = _call_result_text(response, "workspace.get_context")
            workspace_ctx = ctx_data.get("workspace_context", {})
            active_roles = workspace_ctx.get("active_roles", [])
            # REQ-127 global fallback: the caller holds a UserRole, so the
            # aggregate resolution MUST come back non-empty even without a
            # workspace_id argument. Empty here is the original regression.
            assert active_roles, (
                f"[REQ-127] active_roles empty without workspace_id — the "
                f"UserRole fallback regressed: {workspace_ctx}"
            )
            assert "admin" in active_roles, (
                f"Expected 'admin' in active_roles, got: {active_roles}"
            )

    def test_api_key_write_operation_not_blocked_by_empty_role_tuple(
        self,
        admin_client: Client,
        e2e_workspace: Workspace,
        e2e_userrole_admin: UserRole,
    ) -> None:
        """[REQ-127] Write operation via API key must not fail with 'Role () does not permit'."""
        response = _tools_call(
            admin_client,
            "requirement.create",
            {
                "workspace_id": str(e2e_workspace.id),
                "title": "REQ-127 role-propagation write op test",
                "description": "Verifies empty-role tuple error is fixed (REQ-127)",
            },
        )

        body = response.json()
        if "error" in body:
            error_msg = body["error"].get("message", "")
            # The specific old error: "Role '()' does not permit write operations"
            assert "()" not in error_msg, (
                f"[REQ-127] regression — empty role tuple error still present: {error_msg}"
            )
            assert "does not permit write" not in error_msg, (
                f"[REQ-127] regression — write permission blocked by empty role: {error_msg}"
            )


# ---------------------------------------------------------------------------
# [REQ-127] Negative probes: broken role assignment/propagation must fail loudly
# ---------------------------------------------------------------------------


class TestMcpApiKeyRolePropagationNegative:
    """[REQ-127] Guards proving the suite catches broken role propagation.

    A test that can only pass is not a regression guard.  These tests pin
    the two directions role propagation can break in — the wrong role
    reaching the gate (mapping) and no role reaching the gate at all
    (the original REQ-127 failure) — and assert the OBSERVED, unintended
    outcome for each.
    """

    def test_viewer_role_propagates_and_cannot_write_via_api_key(
        self,
        viewer_client: Client,
        e2e_workspace: Workspace,
        e2e_userrole_viewer: UserRole,
    ) -> None:
        """[REQ-127] A viewer key propagates 'viewer' — and only 'viewer'.

        Two-sided probe on the role MAPPING: positive (the assigned role
        reaches the dispatch context — an empty propagation fails the
        first assertion) and negative (a viewer may NOT write — an
        over-broad propagation that hands out 'admin' fails the second).
        """
        response = _tools_call(
            viewer_client,
            "workspace.get_context",
            {"workspace_id": str(e2e_workspace.id)},
        )
        assert "error" not in response.json(), (
            f"[REQ-127] viewer get_context returned error: "
            f"{response.json().get('error')}"
        )
        active_roles = _call_result_text(response, "workspace.get_context")[
            "workspace_context"
        ].get("active_roles", [])
        assert active_roles, (
            f"[REQ-127] viewer active_roles empty — role propagation "
            f"regressed for the viewer key: {active_roles!r}"
        )
        assert "viewer" in active_roles and "admin" not in active_roles, (
            f"Expected exactly the viewer role, got: {active_roles}"
        )

        write_response = _tools_call(
            viewer_client,
            "requirement.create",
            {
                "workspace_id": str(e2e_workspace.id),
                "title": "REQ-127 viewer write probe",
                "description": "Must be denied — viewer holds no write permission",
            },
        )
        assert extract_error_code(write_response) == "PERMISSION_DENIED", (
            f"[REQ-127] viewer write must be PERMISSION_DENIED, got "
            f"{write_response.json()}"
        )

    def test_broken_role_propagation_is_caught(
        self,
        admin_client: Client,
        e2e_workspace: Workspace,
        e2e_userrole_admin: UserRole,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """[REQ-127] Mutation probe: the pre-fix failure mode MUST fail.

        The original bug was role resolution returning ``()`` for API-key
        contexts, which denied EVERY write with
        "Role '()' does not permit write operations".  This test injects
        exactly that break into the real ``ToolRegistry._resolve_roles``
        and asserts the production RBAC gate produces that signature
        denial — proving the assertions in the tests above are loaded
        with signal: a regression that reintroduces the empty-role-tuple
        behaviour surfaces here as a failure, never as a silent pass.
        """
        from mcp_server.tool_registry import ToolRegistry

        def _broken_resolve_roles(self, ctx, workspace_id):
            # The pre-REQ-127 behaviour: API-key contexts keep active_roles=()
            return replace(ctx, active_roles=())

        monkeypatch.setattr(ToolRegistry, "_resolve_roles", _broken_resolve_roles)

        response = _tools_call(
            admin_client,
            "requirement.create",
            {
                "workspace_id": str(e2e_workspace.id),
                "title": "REQ-127 broken-propagation probe",
                "description": "Deliberately broken role resolution probe",
            },
        )
        error_message = _tools_call_error_message(response)
        assert "()" in error_message, (
            f"[REQ-127] broken propagation not detected: expected the empty "
            f"role-tuple signature in the denial, got: {error_message!r}"
        )
        assert "does not permit write" in error_message, (
            f"[REQ-127] broken propagation not denied as a write: {error_message!r}"
        )
