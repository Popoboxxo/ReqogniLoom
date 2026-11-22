"""Issue #2004 — read-only fields are reported, not silently dropped.

``requirement.update`` and ``needs.update`` both leave lifecycle state to the
workflow engine. A client-sent ``status`` used to be accepted with no trace;
the response now carries ``ignored_read_only_fields`` so an agent can tell
"accepted but not applied" from "applied". The payload is purely additive —
the persisted entity never changes, and ``level``'s ADR-005 rejection stays.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.needs import StakeholderNeedsToolGroup
from mcp_server.tools.requirements import RequirementsToolGroup

pytestmark = pytest.mark.django_db

EDITOR_CTX = AuthContext(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("editor",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
)
API_KEY = "reqlo_testkey_2004"
WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


def _artifact() -> MagicMock:
    artifact = MagicMock()
    artifact.workspace_id = WORKSPACE_ID
    artifact.owner = None
    artifact.reporter = None
    artifact.priority = ""
    artifact.custom_fields = {}
    return artifact


def _requirement(level: int = 1) -> MagicMock:
    req = MagicMock()
    req.id = uuid.UUID("00000000-0000-0000-0000-000000000020")
    req.artifact_id = uuid.UUID("00000000-0000-0000-0000-000000000021")
    req.title = "Req"
    req.description = ""
    req.category = ""
    req.status = "draft"
    req.version = 1
    req.level = level
    req.artifact = _artifact()
    return req


def _need() -> MagicMock:
    need = MagicMock()
    need.id = uuid.UUID("00000000-0000-0000-0000-000000000030")
    need.uid = "NEED-001"
    need.workspace_id = WORKSPACE_ID
    need.title = "Need"
    need.description = ""
    need.category = ""
    need.status = "draft"
    need.moscow_priority = "Must"
    need.version = 1
    need.artifact = _artifact()
    return need


@patch("mcp_server.tools.requirements.write_mcp_audit")
def test_requirement_update_reports_status_as_ignored(mock_audit) -> None:
    """A client-sent ``status`` survives as a response field, never a write."""
    svc = MagicMock()
    svc.get_requirement.return_value = _requirement()
    svc.update_requirement.return_value = _requirement()
    group = RequirementsToolGroup(service=svc)

    result = group.execute_tool(
        "requirement.update",
        params={
            "id": str(uuid.uuid4()),
            "data": {"title": "renamed", "status": "approved"},
        },
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is True
    assert result.data["ignored_read_only_fields"] == ["status"]
    # status was never forwarded to the write path.
    assert "status" not in svc.update_requirement.call_args.kwargs
    assert svc.update_requirement.call_args.kwargs["title"] == "renamed"


@patch("mcp_server.tools.requirements.write_mcp_audit")
def test_requirement_update_reports_echoed_level_as_ignored(mock_audit) -> None:
    """An unchanged ``level`` echo is tolerated but reported as not applied."""
    svc = MagicMock()
    svc.get_requirement.return_value = _requirement(level=2)
    svc.update_requirement.return_value = _requirement(level=2)
    group = RequirementsToolGroup(service=svc)

    result = group.execute_tool(
        "requirement.update",
        params={
            "id": str(uuid.uuid4()),
            "data": {"level": 2, "status": "approved"},
        },
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is True
    assert result.data["ignored_read_only_fields"] == ["level", "status"]
    assert "level" not in svc.update_requirement.call_args.kwargs


@patch("mcp_server.tools.requirements.write_mcp_audit")
def test_requirement_update_still_rejects_changed_level(mock_audit) -> None:
    """#2004 is additive: the ADR-005 VALIDATION_ERROR for ``level`` stays."""
    svc = MagicMock()
    svc.get_requirement.return_value = _requirement(level=1)
    group = RequirementsToolGroup(service=svc)

    result = group.execute_tool(
        "requirement.update",
        params={"id": str(uuid.uuid4()), "data": {"level": 4}},
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    svc.update_requirement.assert_not_called()


@patch("mcp_server.tools.requirements.write_mcp_audit")
def test_requirement_update_without_read_only_fields_reports_empty_list(
    mock_audit,
) -> None:
    """The new response key is always present, even when nothing was ignored."""
    svc = MagicMock()
    svc.get_requirement.return_value = _requirement()
    svc.update_requirement.return_value = _requirement()
    group = RequirementsToolGroup(service=svc)

    result = group.execute_tool(
        "requirement.update",
        params={"id": str(uuid.uuid4()), "data": {"title": "renamed"}},
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is True
    assert result.data["ignored_read_only_fields"] == []


def test_needs_update_reports_status_as_ignored() -> None:
    """``needs.update`` reports the same channel for its read-only ``status``."""
    svc = MagicMock()
    svc.get.return_value = _need()
    svc.update.return_value = _need()
    group = StakeholderNeedsToolGroup(service=svc)

    result = group.execute_tool(
        "needs.update",
        params={"id": str(uuid.uuid4()), "title": "renamed", "status": "approved"},
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is True
    assert result.data["ignored_read_only_fields"] == ["status"]
    assert "status" not in svc.update.call_args.kwargs
    assert svc.update.call_args.kwargs["title"] == "renamed"


def test_needs_update_without_status_reports_empty_list() -> None:
    svc = MagicMock()
    svc.get.return_value = _need()
    svc.update.return_value = _need()
    group = StakeholderNeedsToolGroup(service=svc)

    result = group.execute_tool(
        "needs.update",
        params={"id": str(uuid.uuid4()), "title": "renamed"},
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is True
    assert result.data["ignored_read_only_fields"] == []
