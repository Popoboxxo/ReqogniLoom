"""
Tests for COMP-MC-010 AuditToolGroup (REQ-L1-046 admin observability).

leaf_id : COMP-MC-010
req_id  : REQ-L1-046 (admin DR / observability),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-011 (structured error response),
          REQ-L2-MC-012 (MCP audit trail)

Covers:
- audit.query: filter validation, success, service error mapping (NOT_FOUND,
  PERMISSION_DENIED, VALIDATION_ERROR), pagination
- events.dlq_list: filter validation, success, error mapping
- events.dlq_replay: required event_id, success, NOT_FOUND, audit written
- Admin role enforcement: non-admin roles always get PERMISSION_DENIED
  BEFORE the service is called.
- Unknown tool returns UNKNOWN_TOOL
- ToolGroup is registered under the ``audit`` and ``events`` prefixes in
  the registry; events.dlq_replay is in _WRITE_TOOL_PREFIXES.
- E2E: JSON-RPC pipeline reaches the AuditToolGroup handlers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from auth_tenancy.context import AuthContext, AuthMethod, IdentityClaims
from auth_tenancy.errors import AuthenticationFailed

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from application.dlq_service import _DlqSnapshot

from mcp_server.protocol_handler import ProtocolHandler
from mcp_server.tool_registry import ToolRegistry
from mcp_server.tools.audit import AuditToolGroup


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

VALID_API_KEY = "rf_admin_audit_key"
EVENT_UUID = UUID("00000000-0000-0000-0000-0000000000aa")
WORKSPACE_UUID = UUID("00000000-0000-0000-0000-0000000000bb")
ENTITY_UUID = UUID("00000000-0000-0000-0000-0000000000cc")


def _mock_audit_entry(
    *,
    id_val: UUID = None,
    actor: str = "user-1",
    op: str = "create",
    entity_type: str = "Requirement",
    entity_id: UUID = None,
    timestamp: datetime = None,
    change_reason: str = "",
    source: str = "rest",
) -> MagicMock:
    """Build a MagicMock that mimics an AuditEntry ORM instance."""
    row = MagicMock()
    row.id = id_val or uuid4()
    row.actor = actor
    row.actor_type = "user"
    row.op = op
    row.entity_type = entity_type
    row.entity_id = entity_id or ENTITY_UUID
    row.entity_version = 1
    row.change_reason = change_reason
    row.source = source
    row.client_name = None
    row.timestamp = timestamp or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return row


def _mock_dlq_row(
    *,
    event_id: UUID = None,
    event_type: str = "RequirementCreated",
    retry_count: int = 5,
    error_message: str = "max retries exceeded",
    moved_at: datetime = None,
) -> MagicMock:
    """Build a MagicMock that mimics a DomainEventDLQ ORM instance."""
    row = MagicMock()
    row.id = uuid4()
    row.event_id = event_id or EVENT_UUID
    row.event_type = event_type
    row.workspace_id = WORKSPACE_UUID
    row.entity_id = ENTITY_UUID
    row.payload = {"foo": "bar"}
    row.error_message = error_message
    row.retry_count = retry_count
    row.moved_at = moved_at or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return row


def _mock_dlq_snapshot(
    *,
    event_id: UUID = None,
    event_type: str = "RequirementCreated",
    retry_count: int = 5,
) -> _DlqSnapshot:
    """Build an in-memory _DlqSnapshot (replay return value)."""
    return _DlqSnapshot(
        event_id=event_id or EVENT_UUID,
        event_type=event_type,
        workspace_id=WORKSPACE_UUID,
        entity_id=ENTITY_UUID,
        payload={"foo": "bar"},
        error_message="max retries exceeded",
        retry_count=retry_count,
    )


def _mock_paginated_result(*, entries=None, total=None, page=1, page_size=100):
    """Build a MagicMock that mimics a PaginatedAuditResult."""
    r = MagicMock()
    r.entries = entries or []
    r.total = total if total is not None else len(r.entries)
    r.page = page
    r.page_size = page_size
    return r


# ---------------------------------------------------------------------------
# AuditToolGroup unit tests
# ---------------------------------------------------------------------------


class TestAuditToolGroup:
    """Unit tests for the audit.query / events.dlq_list / events.dlq_replay tools."""

    def _group(self, dlq=None):
        """Build an AuditToolGroup with a mocked DlqService."""
        dlq = dlq or MagicMock()
        return AuditToolGroup(dlq_service=dlq), dlq

    # ------------------------------------------------------------------
    # Admin gate (all three handlers)
    # ------------------------------------------------------------------

    def test_audit_query_with_editor_role_returns_permission_denied(self):
        group, _ = self._group()
        with patch("mcp_server.tools.audit.audit_query") as mock_query:
            result = group.execute_tool(
                tool_name="audit.query",
                params={},
                auth_context=EDITOR_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        mock_query.assert_not_called()

    def test_audit_query_with_viewer_role_returns_permission_denied(self):
        group, _ = self._group()
        with patch("mcp_server.tools.audit.audit_query") as mock_query:
            result = group.execute_tool(
                tool_name="audit.query",
                params={},
                auth_context=VIEWER_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        mock_query.assert_not_called()

    def test_dlq_list_with_editor_role_returns_permission_denied(self):
        group, dlq = self._group()
        result = group.execute_tool(
            tool_name="events.dlq_list",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        dlq.list_dlq.assert_not_called()

    def test_dlq_replay_with_editor_role_returns_permission_denied(self):
        group, dlq = self._group()
        result = group.execute_tool(
            tool_name="events.dlq_replay",
            params={"event_id": str(EVENT_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"
        dlq.replay_dlq_event.assert_not_called()

    # ------------------------------------------------------------------
    # audit.query
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_calls_service_and_returns_entries(self, mock_query, mock_set_tenant):
        group, _ = self._group()
        e1 = _mock_audit_entry(actor="user-42", op="create")
        e2 = _mock_audit_entry(
            id_val=UUID("00000000-0000-0000-0000-0000000000d1"),
            actor="user-42",
            op="update",
            change_reason="fix typo",
        )
        mock_query.return_value = _mock_paginated_result(entries=[e1, e2], total=2)

        result = group.execute_tool(
            tool_name="audit.query",
            params={"actor": "user-42", "limit": 50},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["total"] == 2
        assert len(result.data["entries"]) == 2
        assert result.data["entries"][0]["operation"] == "create"
        assert result.data["entries"][1]["change_reason"] == "fix typo"

        mock_set_tenant.assert_called_once_with(ADMIN_CTX.tenant_id)
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args.kwargs
        assert call_kwargs["page"] == 1
        assert call_kwargs["page_size"] == 50
        filters = call_kwargs["filters"]
        assert filters.actor == "user-42"
        assert filters.operation is None

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_with_time_range_and_operation(self, mock_query, mock_set_tenant):
        group, _ = self._group()
        mock_query.return_value = _mock_paginated_result(entries=[], total=0)

        result = group.execute_tool(
            tool_name="audit.query",
            params={
                "operation": "delete",
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-01-31T23:59:59+00:00",
                "limit": 10,
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        call_kwargs = mock_query.call_args.kwargs
        filters = call_kwargs["filters"]
        assert filters.operation == "delete"
        assert filters.timestamp_from is not None
        assert filters.timestamp_to is not None
        # Both timestamps should be timezone-aware
        assert filters.timestamp_from.tzinfo is not None
        assert filters.timestamp_to.tzinfo is not None

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_invalid_operation_returns_validation_error(self, mock_query, mock_set_tenant):
        group, _ = self._group()
        result = group.execute_tool(
            tool_name="audit.query",
            params={"operation": "explode"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        mock_query.assert_not_called()

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_invalid_iso8601_returns_validation_error(self, mock_query, mock_set_tenant):
        group, _ = self._group()
        result = group.execute_tool(
            tool_name="audit.query",
            params={"start_time": "not-a-date"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        mock_query.assert_not_called()

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_start_after_end_returns_validation_error(self, mock_query, mock_set_tenant):
        group, _ = self._group()
        result = group.execute_tool(
            tool_name="audit.query",
            params={
                "start_time": "2026-12-31T00:00:00Z",
                "end_time": "2026-01-01T00:00:00Z",
            },
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        mock_query.assert_not_called()

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_invalid_limit_returns_validation_error(self, mock_query, mock_set_tenant):
        group, _ = self._group()
        # Negative limit
        result = group.execute_tool(
            tool_name="audit.query",
            params={"limit": 0},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        # Non-integer limit
        result = group.execute_tool(
            tool_name="audit.query",
            params={"limit": "abc"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        # Limit over max
        result = group.execute_tool(
            tool_name="audit.query",
            params={"limit": 9999},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        mock_query.assert_not_called()

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_service_validation_error(self, mock_query, mock_set_tenant):
        group, _ = self._group()
        mock_query.side_effect = ValueError("page_size > 200")
        result = group.execute_tool(
            tool_name="audit.query",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_service_not_found(self, mock_query, mock_set_tenant):
        group, _ = self._group()
        mock_query.side_effect = NotFoundError("no entries")
        result = group.execute_tool(
            tool_name="audit.query",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_workspace_id_is_validated_but_not_applied(self, mock_query, mock_set_tenant):
        """workspace_id param is reserved/forward-compat — validate UUID but
        do not pass to the service (AuditEntry is tenant-scoped)."""
        group, _ = self._group()
        mock_query.return_value = _mock_paginated_result(entries=[], total=0)
        result = group.execute_tool(
            tool_name="audit.query",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        # Bad UUID must be rejected
        result = group.execute_tool(
            tool_name="audit.query",
            params={"workspace_id": "not-a-uuid"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_audit_query_does_not_write_audit(self, mock_query, mock_set_tenant):
        """audit.query is a read tool — must NOT call write_mcp_audit."""
        group, _ = self._group()
        mock_query.return_value = _mock_paginated_result(entries=[], total=0)
        with patch("mcp_server.tools.audit.write_mcp_audit") as mock_audit:
            result = group.execute_tool(
                tool_name="audit.query",
                params={},
                auth_context=ADMIN_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is True
        mock_audit.assert_not_called()

    # ------------------------------------------------------------------
    # events.dlq_list
    # ------------------------------------------------------------------

    def test_dlq_list_calls_service_and_returns_events(self):
        group, dlq = self._group()
        r1 = _mock_dlq_row(event_id=UUID("00000000-0000-0000-0000-0000000000a1"))
        r2 = _mock_dlq_row(event_id=UUID("00000000-0000-0000-0000-0000000000a2"))
        dlq.list_dlq.return_value = [r1, r2]

        result = group.execute_tool(
            tool_name="events.dlq_list",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["count"] == 2
        assert len(result.data["events"]) == 2
        assert result.data["events"][0]["event_id"] == str(r1.event_id)
        dlq.list_dlq.assert_called_once_with(
            ADMIN_CTX, event_type=None, limit=100
        )

    def test_dlq_list_with_event_type_filter(self):
        group, dlq = self._group()
        dlq.list_dlq.return_value = []

        result = group.execute_tool(
            tool_name="events.dlq_list",
            params={"event_type": "RequirementDeleted", "limit": 25},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        dlq.list_dlq.assert_called_once_with(
            ADMIN_CTX, event_type="RequirementDeleted", limit=25
        )

    def test_dlq_list_invalid_limit_returns_validation_error(self):
        group, dlq = self._group()
        result = group.execute_tool(
            tool_name="events.dlq_list",
            params={"limit": 5000},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        dlq.list_dlq.assert_not_called()

    def test_dlq_list_non_integer_limit_returns_validation_error(self):
        group, dlq = self._group()
        result = group.execute_tool(
            tool_name="events.dlq_list",
            params={"limit": "abc"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        dlq.list_dlq.assert_not_called()

    def test_dlq_list_invalid_event_type_returns_validation_error(self):
        group, dlq = self._group()
        result = group.execute_tool(
            tool_name="events.dlq_list",
            params={"event_type": 42},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        dlq.list_dlq.assert_not_called()

    def test_dlq_list_permission_denied_from_service(self):
        group, dlq = self._group()
        dlq.list_dlq.side_effect = PermissionDeniedError("admin required")
        result = group.execute_tool(
            tool_name="events.dlq_list",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_dlq_list_does_not_write_audit(self):
        group, dlq = self._group()
        dlq.list_dlq.return_value = []
        with patch("mcp_server.tools.audit.write_mcp_audit") as mock_audit:
            result = group.execute_tool(
                tool_name="events.dlq_list",
                params={},
                auth_context=ADMIN_CTX,
                api_key=VALID_API_KEY,
            )
        assert result.success is True
        mock_audit.assert_not_called()

    # ------------------------------------------------------------------
    # events.dlq_replay
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.audit.write_mcp_audit")
    def test_dlq_replay_calls_service_and_audits(self, mock_audit):
        group, dlq = self._group()
        dlq.replay_dlq_event.return_value = _mock_dlq_snapshot(retry_count=5)

        result = group.execute_tool(
            tool_name="events.dlq_replay",
            params={"event_id": str(EVENT_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["replayed"] is True
        assert result.data["event"]["event_id"] == str(EVENT_UUID)
        assert result.data["event"]["retry_count"] == 5
        dlq.replay_dlq_event.assert_called_once_with(
            ADMIN_CTX, event_id=EVENT_UUID
        )
        mock_audit.assert_called_once()
        audit_kwargs = mock_audit.call_args.kwargs
        assert audit_kwargs["tool_name"] == "events.dlq_replay"
        assert audit_kwargs["operation"] == "replay"
        assert audit_kwargs["entity_type"] == "DomainEventDLQ"
        assert audit_kwargs["entity_id"] == EVENT_UUID
        assert audit_kwargs["details"]["previous_retry_count"] == 5
        assert audit_kwargs["details"]["event_type"] == "RequirementCreated"

    def test_dlq_replay_missing_event_id_returns_validation_error(self):
        group, dlq = self._group()
        result = group.execute_tool(
            tool_name="events.dlq_replay",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        dlq.replay_dlq_event.assert_not_called()

    def test_dlq_replay_invalid_event_id_returns_validation_error(self):
        group, dlq = self._group()
        result = group.execute_tool(
            tool_name="events.dlq_replay",
            params={"event_id": "not-a-uuid"},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        dlq.replay_dlq_event.assert_not_called()

    def test_dlq_replay_not_found(self):
        group, dlq = self._group()
        dlq.replay_dlq_event.side_effect = NotFoundError(
            f"DLQ event {EVENT_UUID} not found"
        )
        result = group.execute_tool(
            tool_name="events.dlq_replay",
            params={"event_id": str(EVENT_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_dlq_replay_permission_denied(self):
        group, dlq = self._group()
        dlq.replay_dlq_event.side_effect = PermissionDeniedError("admin required")
        result = group.execute_tool(
            tool_name="events.dlq_replay",
            params={"event_id": str(EVENT_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    @patch("mcp_server.tools.audit.write_mcp_audit")
    def test_dlq_replay_does_not_audit_on_failure(self, mock_audit):
        group, dlq = self._group()
        dlq.replay_dlq_event.side_effect = NotFoundError("not found")
        result = group.execute_tool(
            tool_name="events.dlq_replay",
            params={"event_id": str(EVENT_UUID)},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        mock_audit.assert_not_called()

    # ------------------------------------------------------------------
    # Unknown tool
    # ------------------------------------------------------------------

    def test_unknown_audit_tool_returns_unknown_tool(self):
        group, _ = self._group()
        result = group.execute_tool(
            tool_name="audit.does_not_exist",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    def test_unknown_events_tool_returns_unknown_tool(self):
        group, _ = self._group()
        result = group.execute_tool(
            tool_name="events.does_not_exist",
            params={},
            auth_context=ADMIN_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


# ---------------------------------------------------------------------------
# Tool map / constructor wiring
# ---------------------------------------------------------------------------


class TestAuditToolGroupWiring:
    def test_default_constructor_uses_real_dlq_service(self):
        group = AuditToolGroup()
        assert group._dlq_service is not None

    def test_tool_map_has_exactly_three_entries(self):
        assert set(AuditToolGroup._TOOL_MAP.keys()) == {
            "audit.query",
            "events.dlq_list",
            "events.dlq_replay",
        }


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------


class TestToolRegistryWiring:
    """The ToolRegistry must register AuditToolGroup under both the
    ``audit`` and ``events`` prefixes."""

    def test_audit_prefix_is_registered(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        assert "audit" in registry._groups
        assert isinstance(registry._groups["audit"], AuditToolGroup)

    def test_events_prefix_is_registered(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        assert "events" in registry._groups
        # Both prefixes point to the SAME AuditToolGroup instance (router
        # uses startswith, and the group owns both namespaces).
        assert registry._groups["events"] is registry._groups["audit"]

    def test_events_dlq_replay_is_registered_as_write_tool(self):
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        assert "events.dlq_replay" in _WRITE_TOOL_PREFIXES
        # Read tools must NOT be in the write set.
        assert "audit.query" not in _WRITE_TOOL_PREFIXES
        assert "events.dlq_list" not in _WRITE_TOOL_PREFIXES

    def test_router_routes_audit_and_events_prefixes(self):
        registry = ToolRegistry()
        registry._ensure_groups()
        router = registry._router
        assert router is not None
        for tool_name in (
            "audit.query",
            "events.dlq_list",
            "events.dlq_replay",
        ):
            group, err = router.route(tool_name)
            assert err is None, f"{tool_name} did not route: {err}"
            assert group is registry._groups["audit"]


# ---------------------------------------------------------------------------
# E2E — JSON-RPC pipeline
# ---------------------------------------------------------------------------


TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")
USER_ID = UUID("00000000-0000-0000-0000-000000000001")
API_KEY_ID = UUID("00000000-0000-0000-0000-000000000003")


def _claims(roles=("admin",)):
    return IdentityClaims(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        roles=roles,
        auth_method=AuthMethod.API_KEY,
        api_key_id=API_KEY_ID,
    )


def _build_registry(*, roles=("admin",), dlq: MagicMock = None):
    """Build a ToolRegistry with mocked auth services and the real
    AuditToolGroup registered (with optionally mocked DlqService)."""
    auth_svc = MagicMock()
    auth_svc.validate_api_key.return_value = _claims(roles=roles)

    authz_svc = MagicMock()
    authz_svc.active_roles_for.return_value = roles
    authz_svc.decide_access.return_value = MagicMock(allow=("viewer" not in roles))

    registry = ToolRegistry(auth_service=auth_svc, authz_service=authz_svc)
    registry._ensure_groups()

    if dlq is not None:
        audit_group = registry._groups["audit"]
        audit_group._dlq_service = dlq
    return registry, auth_svc, authz_svc


def _post(handler: ProtocolHandler, method: str, params: dict, request_id: int = 1, *, api_key: str = VALID_API_KEY):
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


class TestE2EAuditQuery:
    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_successful_query_returns_jsonrpc_result_envelope(self, mock_query, mock_set_tenant):
        e1 = _mock_audit_entry(actor="user-1", op="create")
        e2 = _mock_audit_entry(
            id_val=UUID("00000000-0000-0000-0000-0000000000d2"),
            actor="user-1",
            op="update",
        )
        mock_query.return_value = _mock_paginated_result(entries=[e1, e2], total=2)
        registry, _, _ = _build_registry()
        handler = _handler(registry)

        response = _post(
            handler,
            "audit.query",
            {"actor": "user-1", "limit": 50, "workspace_id": str(WORKSPACE_UUID)},
        )

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert "error" not in response
        assert response["result"]["total"] == 2
        assert len(response["result"]["entries"]) == 2

    @patch("mcp_server.tools.audit.TenantContext.set_tenant")
    @patch("mcp_server.tools.audit.audit_query")
    def test_query_with_editor_role_returns_permission_denied(self, mock_query, mock_set_tenant):
        # Use editor role to reach the handler: viewer would be blocked by RBAC
        # before the admin gate. The AuditToolGroup enforces admin at the
        # handler level (defence in depth), so editor still gets denied.
        registry, _, _ = _build_registry(roles=("editor",))
        handler = _handler(registry)

        response = _post(
            handler,
            "audit.query",
            {"workspace_id": str(WORKSPACE_UUID)},
        )

        assert "error" in response
        assert response["error"]["error_code"] == "PERMISSION_DENIED"
        mock_query.assert_not_called()

    def test_query_with_invalid_api_key_returns_auth_failed(self):
        registry, auth_svc, _ = _build_registry()
        auth_svc.validate_api_key.side_effect = AuthenticationFailed("invalid_api_key")
        handler = _handler(registry)

        response = _post(
            handler,
            "audit.query",
            {"workspace_id": str(WORKSPACE_UUID)},
            api_key="rf_bad_key",
        )

        assert "error" in response
        assert response["error"]["error_code"] == "AUTH_FAILED"


class TestE2EDlqReplay:
    @patch("mcp_server.tools.audit.write_mcp_audit")
    def test_successful_replay_returns_jsonrpc_result_envelope(self, mock_audit):
        dlq = MagicMock()
        dlq.replay_dlq_event.return_value = _mock_dlq_snapshot(retry_count=5)
        registry, _, _ = _build_registry(dlq=dlq)
        handler = _handler(registry)

        response = _post(
            handler,
            "events.dlq_replay",
            {"event_id": str(EVENT_UUID), "workspace_id": str(WORKSPACE_UUID)},
        )

        assert "result" in response
        assert "error" not in response
        assert response["result"]["replayed"] is True
        assert response["result"]["event"]["event_id"] == str(EVENT_UUID)
        mock_audit.assert_called_once()

    def test_replay_with_viewer_role_returns_permission_denied(self):
        dlq = MagicMock()
        registry, _, authz_svc = _build_registry(roles=("viewer",), dlq=dlq)
        # RBAC must deny writes for viewers
        authz_svc.decide_access.return_value = MagicMock(allow=False)
        handler = _handler(registry)

        response = _post(
            handler,
            "events.dlq_replay",
            {"event_id": str(EVENT_UUID), "workspace_id": str(WORKSPACE_UUID)},
        )

        assert "error" in response
        assert response["error"]["error_code"] == "PERMISSION_DENIED"
        dlq.replay_dlq_event.assert_not_called()
