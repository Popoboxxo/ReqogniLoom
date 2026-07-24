"""
End-to-end tests for the workspace-lifecycle MCP tools (REQ-L1-042).

leaf_id : COMP-MC-001 + COMP-MC-002 + COMP-MC-007
req_id  : REQ-L1-042, REQ-L2-MC-005 (transport),
          REQ-L2-MC-006 (API-key auth), REQ-L2-MC-007 (RBAC),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-011 (structured error response),
          REQ-L2-MC-012 (MCP audit trail)

Pipeline exercised end-to-end:
  HTTP / JSON-RPC  →  ProtocolHandler  →  ToolRegistry  →  ToolGroupRouter
    →  AdminToolGroup  →  WorkspaceService (mocked)

The goal of this test is to verify that:
  * A JSON-RPC ``workspace.close`` request reaches the
    ``WorkspaceService.close_workspace`` method via the real
    ToolGroupRouter (no shortcuts).
  * A successful response is wrapped in a valid JSON-RPC 2.0 result
    envelope and contains the workspace data.
  * A failed response (e.g. unknown tool, RBAC denial) is wrapped in
    a valid JSON-RPC 2.0 error envelope with the correct error code.
  * The new lifecycle tools are registered as write tools and the
    RBAC check is honoured (viewer role → PERMISSION_DENIED).
  * The audit trail (``write_mcp_audit``) is called for every
    successful write.
  * The ``workspace.get_context`` read tool is still reachable via
    fallthrough in AdminToolGroup.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import ANY, MagicMock, patch
from uuid import UUID


from auth_tenancy.context import AuthContext, AuthMethod, IdentityClaims
from auth_tenancy.errors import AuthenticationFailed

from mcp_server.protocol_handler import ERROR_CODE_MAP, ProtocolHandler
from mcp_server.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------


TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")
API_KEY_ID = UUID("00000000-0000-0000-0000-000000000003")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000010")
WORKSPACE_NAME = "Production Workspace"
VALID_API_KEY = "reqlo_e2e_admin_key"


def _claims(roles=("admin",)):
    return IdentityClaims(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=API_KEY_ID,
    )


def _mock_workspace(*, is_active=False, closed_at=None, closed_by_id=None):
    ws = MagicMock()
    ws.id = WORKSPACE_ID
    ws.name = WORKSPACE_NAME
    ws.is_active = is_active
    ws.closed_at = closed_at
    ws.closed_by_id = closed_by_id
    return ws


def _build_registry(*, roles=("admin",), service: MagicMock = None):
    """Build a ToolRegistry with mocked auth services and the real
    AdminToolGroup / CrossCuttingToolGroup registered.

    The ``service`` mock replaces the real ``WorkspaceService`` for all
    three lifecycle methods.
    """
    auth_svc = MagicMock()
    auth_svc.validate_api_key.return_value = _claims(roles=roles)

    authz_svc = MagicMock()
    authz_svc.active_roles_for.return_value = roles
    # RBAC: admin/editor allowed, viewer denied
    authz_svc.decide_access.return_value = MagicMock(
        allow=("viewer" not in roles)
    )

    registry = ToolRegistry(
        auth_service=auth_svc,
        authz_service=authz_svc,
        workspace_exists=lambda workspace_id: True,
    )

    # Force the real groups to be initialised, then swap in a mocked
    # WorkspaceService for AdminToolGroup so the lifecycle handlers
    # can be observed.
    registry._ensure_groups()

    if service is not None:
        admin_group = registry._groups["workspace"]
        admin_group._service = service

    return registry, auth_svc, authz_svc, service


def _post(handler: ProtocolHandler, method: str, params: dict, request_id: int = 1, *, api_key: str = VALID_API_KEY):
    """Build a JSON-RPC body and run it through ProtocolHandler."""
    payload = {"api_key": api_key}
    payload.update(params)
    body = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id,
        "params": payload,
    }).encode()
    return handler.handle_http_request(body=body)


def _handler(registry: ToolRegistry) -> ProtocolHandler:
    return ProtocolHandler(tool_registry=registry)


# ---------------------------------------------------------------------------
# E2E — workspace.close
# ---------------------------------------------------------------------------


class TestE2EWorkspaceClose:
    @patch("mcp_server.tools.admin.write_mcp_audit")
    def test_successful_close_returns_jsonrpc_result_envelope(self, mock_audit):
        svc = MagicMock()
        svc.close_workspace.return_value = _mock_workspace(
            is_active=False,
            closed_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        registry, _, _, _ = _build_registry(roles=("admin",), service=svc)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.close",
            {"workspace_id": str(WORKSPACE_ID)},
        )

        # JSON-RPC 2.0 envelope
        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert "error" not in response
        assert response["result"]["workspace"]["id"] == str(WORKSPACE_ID)
        assert response["result"]["workspace"]["is_active"] is False

        # Service was reached with the right UUID and AuthContext
        svc.close_workspace.assert_called_once()
        call_args = svc.close_workspace.call_args
        assert call_args.args[0] == WORKSPACE_ID
        assert isinstance(call_args.args[1], AuthContext)
        assert call_args.args[1].active_roles == ("admin",)

        # MCP audit entry was written
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "workspace.close"

    def test_close_with_viewer_role_returns_permission_denied(self):
        svc = MagicMock()
        registry, _, authz_svc, _ = _build_registry(roles=("viewer",), service=svc)
        # RBAC must deny writes for viewers
        authz_svc.decide_access.return_value = MagicMock(allow=False)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.close",
            {"workspace_id": str(WORKSPACE_ID)},
        )

        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]
        # Service must NOT be reached because the RBAC gate blocked it
        svc.close_workspace.assert_not_called()

    def test_close_with_invalid_api_key_returns_auth_failed(self):
        svc = MagicMock()
        registry, auth_svc, _, _ = _build_registry(roles=("admin",), service=svc)
        auth_svc.validate_api_key.side_effect = AuthenticationFailed("invalid_api_key")
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.close",
            {"workspace_id": str(WORKSPACE_ID)},
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["AUTH_FAILED"]
        svc.close_workspace.assert_not_called()

    def test_close_not_found_propagates_as_jsonrpc_error(self):
        from application.base import NotFoundError

        svc = MagicMock()
        svc.close_workspace.side_effect = NotFoundError("Workspace not found")
        registry, _, _, _ = _build_registry(roles=("admin",), service=svc)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.close",
            {"workspace_id": str(WORKSPACE_ID)},
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["NOT_FOUND"]
        assert "Workspace not found" in response["error"]["message"]

    def test_close_missing_workspace_id_returns_validation_error(self):
        svc = MagicMock()
        registry, _, _, _ = _build_registry(roles=("admin",), service=svc)
        handler = _handler(registry)

        response = _post(handler, "workspace.close", {})
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["VALIDATION_ERROR"]
        svc.close_workspace.assert_not_called()


# ---------------------------------------------------------------------------
# E2E — workspace.reactivate
# ---------------------------------------------------------------------------


class TestE2EWorkspaceReactivate:
    @patch("mcp_server.tools.admin.write_mcp_audit")
    def test_successful_reactivate_returns_jsonrpc_result_envelope(self, mock_audit):
        svc = MagicMock()
        svc.reactivate_workspace.return_value = _mock_workspace(
            is_active=True, closed_at=None, closed_by_id=None
        )
        registry, _, _, _ = _build_registry(roles=("admin",), service=svc)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.reactivate",
            {"workspace_id": str(WORKSPACE_ID)},
        )

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert response["result"]["workspace"]["is_active"] is True
        assert response["result"]["workspace"]["closed_at"] is None
        svc.reactivate_workspace.assert_called_once()
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "workspace.reactivate"

    def test_reactivate_validation_error_propagates(self):
        from application.base import ValidationError

        svc = MagicMock()
        svc.reactivate_workspace.side_effect = ValidationError("invalid state")
        registry, _, _, _ = _build_registry(roles=("admin",), service=svc)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.reactivate",
            {"workspace_id": str(WORKSPACE_ID)},
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["VALIDATION_ERROR"]


# ---------------------------------------------------------------------------
# E2E — workspace.delete
# ---------------------------------------------------------------------------


class TestE2EWorkspaceDelete:
    @patch("mcp_server.tools.admin.write_mcp_audit")
    def test_successful_delete_with_correct_captcha(self, mock_audit):
        svc = MagicMock()
        svc.delete_workspace.return_value = None
        registry, _, _, _ = _build_registry(roles=("admin",), service=svc)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.delete",
            {
                "workspace_id": str(WORKSPACE_ID),
                "confirmation_text": WORKSPACE_NAME,
            },
        )

        assert "result" in response
        assert response["result"]["deleted"] is True
        assert response["result"]["workspace_id"] == str(WORKSPACE_ID)
        svc.delete_workspace.assert_called_once_with(
            workspace_id=WORKSPACE_ID,
            confirmation_text=WORKSPACE_NAME,
            ctx=ANY,
        )
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "workspace.delete"

    def test_delete_captcha_mismatch_returns_validation_error(self):
        from application.base import ValidationError

        svc = MagicMock()
        svc.delete_workspace.side_effect = ValidationError(
            f"Confirmation mismatch: expected '{WORKSPACE_NAME}', got 'nope'"
        )
        registry, _, _, _ = _build_registry(roles=("admin",), service=svc)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.delete",
            {
                "workspace_id": str(WORKSPACE_ID),
                "confirmation_text": "nope",
            },
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["VALIDATION_ERROR"]
        assert "Confirmation mismatch" in response["error"]["message"]

    def test_delete_missing_confirmation_text_returns_validation_error(self):
        svc = MagicMock()
        registry, _, _, _ = _build_registry(roles=("admin",), service=svc)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.delete",
            {"workspace_id": str(WORKSPACE_ID)},
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["VALIDATION_ERROR"]
        svc.delete_workspace.assert_not_called()

    def test_delete_with_viewer_role_is_blocked_by_rbac(self):
        svc = MagicMock()
        registry, _, authz_svc, _ = _build_registry(roles=("viewer",), service=svc)
        authz_svc.decide_access.return_value = MagicMock(allow=False)
        handler = _handler(registry)

        response = _post(
            handler,
            "workspace.delete",
            {
                "workspace_id": str(WORKSPACE_ID),
                "confirmation_text": WORKSPACE_NAME,
            },
        )
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["PERMISSION_DENIED"]
        svc.delete_workspace.assert_not_called()


# ---------------------------------------------------------------------------
# E2E — namespace fallthrough
# ---------------------------------------------------------------------------


class TestE2EWorkspaceNamespace:
    def test_workspace_get_context_falls_through_to_cross_cutting(self):
        """The new AdminToolGroup owns the ``workspace`` prefix but
        ``workspace.get_context`` is still reachable via fallthrough."""
        registry, _, _, _ = _build_registry(roles=("admin",))
        handler = _handler(registry)

        # The wrapped CrossCuttingToolGroup's _handle_workspace_get_context
        # builds a context dict from auth_context.tenant_id / user_id.
        response = _post(
            handler,
            "workspace.get_context",
            {},
        )
        assert "result" in response
        assert response["result"]["workspace_context"]["tenant_id"] == str(TENANT_ID)
        assert response["result"]["workspace_context"]["user_id"] == str(USER_ID)

    def test_unknown_workspace_tool_returns_unknown_tool_error(self):
        registry, _, _, _ = _build_registry(roles=("admin",))
        handler = _handler(registry)

        response = _post(handler, "workspace.does_not_exist", {})
        assert "error" in response
        assert response["error"]["code"] == ERROR_CODE_MAP["UNKNOWN_TOOL"]


# ---------------------------------------------------------------------------
# E2E — registry write prefixes
# ---------------------------------------------------------------------------


class TestE2EWritePrefixRegistration:
    """The ToolRegistry must treat the three new tools as write tools."""

    def test_lifecycle_tools_are_registered_as_write_tools(self):
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        assert "workspace.close" in _WRITE_TOOL_PREFIXES
        assert "workspace.reactivate" in _WRITE_TOOL_PREFIXES
        assert "workspace.delete" in _WRITE_TOOL_PREFIXES

    def test_registry_routes_workspace_prefix_to_admin_group(self):
        registry, _, _, _ = _build_registry(roles=("admin",))
        admin_group = registry._groups["workspace"]
        from mcp_server.tools.admin import AdminToolGroup

        assert isinstance(admin_group, AdminToolGroup)

    def test_all_three_lifecycle_tools_resolve_through_router(self):
        registry, _, _, _ = _build_registry(roles=("admin",))
        router = registry._router
        assert router is not None
        for tool_name in ("workspace.close", "workspace.reactivate", "workspace.delete"):
            group, err = router.route(tool_name)
            assert err is None, f"{tool_name} did not route: {err}"
            assert group is registry._groups["workspace"]
