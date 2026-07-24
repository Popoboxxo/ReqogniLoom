"""
Tests for COMP-MC-007 AdminToolGroup (REQ-L1-042).

leaf_id : COMP-MC-007
req_id  : REQ-L1-042 (Workspace-Lifecycle MCP-Wrapper),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Covers:
- workspace.close: calls service, audits, error mapping (NOT_FOUND, PERMISSION_DENIED, VALIDATION_ERROR)
- workspace.reactivate: calls service, audits, error mapping
- workspace.delete: calls service, audits, captcha mismatch mapped to VALIDATION_ERROR
- Fallthrough: workspace.get_context delegates to wrapped CrossCuttingToolGroup
- Unknown workspace.* tool returns UNKNOWN_TOOL via fallthrough
- Audit is written for every successful write tool, never on read tools
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID


from auth_tenancy.context import AuthContext, AuthMethod

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

from mcp_server.protocol_handler import ToolResult
from mcp_server.tools.admin import AdminToolGroup


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


ADMIN_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("admin",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)

EDITOR_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("editor",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)

VIEWER_CTX = AuthContext(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("viewer",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=UUID("00000000-0000-0000-0000-000000000003"),
)

VALID_API_KEY = "reqlo_admin_test_key"
WORKSPACE_UUID = UUID("00000000-0000-0000-0000-000000000010")
WORKSPACE_NAME = "Production Workspace"


def _mock_workspace(
    *,
    id_val: UUID = None,
    name: str = WORKSPACE_NAME,
    is_active: bool = False,
    closed_at: datetime = None,
    closed_by_id: UUID = None,
) -> MagicMock:
    """Build a MagicMock that mimics a Workspace ORM instance."""
    ws = MagicMock()
    ws.id = id_val or WORKSPACE_UUID
    ws.name = name
    ws.is_active = is_active
    ws.closed_at = closed_at
    ws.closed_by_id = closed_by_id
    return ws


# ---------------------------------------------------------------------------
# AdminToolGroup tests
# ---------------------------------------------------------------------------


class TestAdminToolGroup:
    """Unit tests for AdminToolGroup lifecycle tools."""

    def _group(self, service=None, cross_cutting=None):
        """Build an AdminToolGroup with mocked dependencies."""
        service = service or MagicMock()
        cross_cutting = cross_cutting or MagicMock()
        return (
            AdminToolGroup(service=service, cross_cutting=cross_cutting),
            service,
            cross_cutting,
        )

    # ------------------------------------------------------------------
    # workspace.close
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.admin.write_mcp_audit")
    def test_workspace_close_calls_service_and_audits(self, mock_audit):
        group, svc, _ = self._group()
        ws = _mock_workspace(is_active=False, closed_at=datetime.now(timezone.utc))
        svc.close_workspace.return_value = ws

        result = group.execute_tool(
            tool_name="workspace.close",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["workspace"]["id"] == str(WORKSPACE_UUID)
        assert result.data["workspace"]["is_active"] is False
        svc.close_workspace.assert_called_once_with(WORKSPACE_UUID, ADMIN_CTX)
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "workspace.close"
        assert audit_kwargs["operation"] == "workspace.close"
        assert audit_kwargs["entity_type"] == "Workspace"
        assert audit_kwargs["entity_id"] == WORKSPACE_UUID

    def test_workspace_close_missing_workspace_id_returns_validation_error(self):
        group, svc, _ = self._group()
        result = group.execute_tool(
            tool_name="workspace.close",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.close_workspace.assert_not_called()

    def test_workspace_close_invalid_uuid_returns_validation_error(self):
        group, svc, _ = self._group()
        result = group.execute_tool(
            tool_name="workspace.close",
            params={"workspace_id": "not-a-uuid"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.close_workspace.assert_not_called()

    def test_workspace_close_not_found(self):
        group, svc, _ = self._group()
        svc.close_workspace.side_effect = NotFoundError("Workspace not found")

        result = group.execute_tool(
            tool_name="workspace.close",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_workspace_close_permission_denied(self):
        group, svc, _ = self._group()
        svc.close_workspace.side_effect = PermissionDeniedError("admin required")

        result = group.execute_tool(
            tool_name="workspace.close",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_workspace_close_validation_error(self):
        group, svc, _ = self._group()
        svc.close_workspace.side_effect = ValidationError("invalid state")

        result = group.execute_tool(
            tool_name="workspace.close",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    # ------------------------------------------------------------------
    # workspace.reactivate
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.admin.write_mcp_audit")
    def test_workspace_reactivate_calls_service_and_audits(self, mock_audit):
        group, svc, _ = self._group()
        ws = _mock_workspace(is_active=True, closed_at=None, closed_by_id=None)
        svc.reactivate_workspace.return_value = ws

        result = group.execute_tool(
            tool_name="workspace.reactivate",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["workspace"]["is_active"] is True
        assert result.data["workspace"]["closed_at"] is None
        svc.reactivate_workspace.assert_called_once_with(WORKSPACE_UUID, ADMIN_CTX)
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "workspace.reactivate"
        assert audit_kwargs["operation"] == "workspace.reactivate"

    def test_workspace_reactivate_not_found(self):
        group, svc, _ = self._group()
        svc.reactivate_workspace.side_effect = NotFoundError("Workspace not found")

        result = group.execute_tool(
            tool_name="workspace.reactivate",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_workspace_reactivate_permission_denied(self):
        group, svc, _ = self._group()
        svc.reactivate_workspace.side_effect = PermissionDeniedError("admin required")

        result = group.execute_tool(
            tool_name="workspace.reactivate",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_workspace_reactivate_missing_workspace_id_returns_validation_error(self):
        group, svc, _ = self._group()
        result = group.execute_tool(
            tool_name="workspace.reactivate",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.reactivate_workspace.assert_not_called()

    # ------------------------------------------------------------------
    # workspace.delete
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.admin.write_mcp_audit")
    def test_workspace_delete_calls_service_and_audits(self, mock_audit):
        group, svc, _ = self._group()
        svc.delete_workspace.return_value = None

        result = group.execute_tool(
            tool_name="workspace.delete",
            params={
                "workspace_id": str(WORKSPACE_UUID),
                "confirmation_text": WORKSPACE_NAME,
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data == {"deleted": True, "workspace_id": str(WORKSPACE_UUID)}
        svc.delete_workspace.assert_called_once_with(
            workspace_id=WORKSPACE_UUID,
            confirmation_text=WORKSPACE_NAME,
            ctx=ADMIN_CTX,
        )
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "workspace.delete"
        assert audit_kwargs["operation"] == "workspace.delete"
        assert audit_kwargs["entity_id"] == WORKSPACE_UUID

    def test_workspace_delete_captcha_mismatch_returns_validation_error(self):
        group, svc, _ = self._group()
        # The service raises ValidationError when confirmation_text does not
        # match the workspace name; MCP wrapper must propagate as
        # VALIDATION_ERROR without rewriting the message.
        svc.delete_workspace.side_effect = ValidationError(
            f"Confirmation mismatch: expected '{WORKSPACE_NAME}', got 'wrong'"
        )

        result = group.execute_tool(
            tool_name="workspace.delete",
            params={
                "workspace_id": str(WORKSPACE_UUID),
                "confirmation_text": "wrong",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "Confirmation mismatch" in result.message

    def test_workspace_delete_not_found(self):
        group, svc, _ = self._group()
        svc.delete_workspace.side_effect = NotFoundError("Workspace not found")

        result = group.execute_tool(
            tool_name="workspace.delete",
            params={
                "workspace_id": str(WORKSPACE_UUID),
                "confirmation_text": WORKSPACE_NAME,
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_workspace_delete_permission_denied(self):
        group, svc, _ = self._group()
        svc.delete_workspace.side_effect = PermissionDeniedError("admin required")

        result = group.execute_tool(
            tool_name="workspace.delete",
            params={
                "workspace_id": str(WORKSPACE_UUID),
                "confirmation_text": WORKSPACE_NAME,
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_workspace_delete_missing_confirmation_text_returns_validation_error(self):
        group, svc, _ = self._group()
        result = group.execute_tool(
            tool_name="workspace.delete",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.delete_workspace.assert_not_called()

    def test_workspace_delete_missing_workspace_id_returns_validation_error(self):
        group, svc, _ = self._group()
        result = group.execute_tool(
            tool_name="workspace.delete",
            params={"confirmation_text": WORKSPACE_NAME},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.delete_workspace.assert_not_called()

    # ------------------------------------------------------------------
    # Fallthrough: workspace.get_context + unknown workspace.* tools
    # ------------------------------------------------------------------

    def test_workspace_get_context_falls_through_to_cross_cutting(self):
        group, _, cross_cutting = self._group()
        cross_cutting.execute_tool.return_value = ToolResult.ok(
            {"workspace_context": {"tenant_id": str(ADMIN_CTX.tenant_id)}}
        )

        result = group.execute_tool(
            tool_name="workspace.get_context",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["workspace_context"]["tenant_id"] == str(ADMIN_CTX.tenant_id)
        cross_cutting.execute_tool.assert_called_once()
        call_kwargs = cross_cutting.execute_tool.call_args.kwargs
        assert call_kwargs["tool_name"] == "workspace.get_context"
        assert call_kwargs["auth_context"] is ADMIN_CTX

    def test_unknown_workspace_tool_falls_through_and_returns_unknown_tool(self):
        """A non-lifecycle workspace.* tool the wrapped group also does not
        know about must still return UNKNOWN_TOOL (via fallthrough)."""
        group, _, cross_cutting = self._group()
        cross_cutting.execute_tool.return_value = ToolResult.error(
            "UNKNOWN_TOOL", "Tool 'workspace.does_not_exist' not found."
        )

        result = group.execute_tool(
            tool_name="workspace.does_not_exist",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"
        cross_cutting.execute_tool.assert_called_once()

    def test_lifecycle_handler_does_not_call_cross_cutting(self):
        """Lifecycle tools must be handled locally — the wrapped
        CrossCuttingToolGroup must NOT be invoked for them."""
        group, svc, cross_cutting = self._group()
        ws = _mock_workspace(is_active=False, closed_at=datetime.now(timezone.utc))
        svc.close_workspace.return_value = ws

        with patch("mcp_server.tools.admin.write_mcp_audit"):
            group.execute_tool(
                tool_name="workspace.close",
                params={"workspace_id": str(WORKSPACE_UUID)},
                auth_context=ADMIN_CTX,
                api_key=VALID_API_KEY,
            )

        cross_cutting.execute_tool.assert_not_called()


# ---------------------------------------------------------------------------
# Constructor / wiring tests
# ---------------------------------------------------------------------------


class TestAdminToolGroupWiring:
    def test_default_constructor_uses_real_services(self):
        """Without args, the group instantiates real WorkspaceService and
        CrossCuttingToolGroup. We only assert the attributes are set —
        actual construction must not raise at import time."""
        group = AdminToolGroup()
        assert group._service is not None
        assert group._cross_cutting is not None

    def test_tool_map_has_exactly_three_entries(self):
        """Guard against accidental additions or removals."""
        assert set(AdminToolGroup._TOOL_MAP.keys()) == {
            "workspace.close",
            "workspace.reactivate",
            "workspace.delete",
        }
