"""Issue #2000 — an empty AI decomposition explains itself.

The decomposition capability is asynchronous, so a successful call can yield
an empty ``children`` list (the children are not in this response yet).
``requirement.decompose`` used to return a bare ``{"children": []}``, which is
indistinguishable from a broken pipeline. The empty result now
carries ``degraded``/``degraded_reason``; the populated result and the async
task-id path are untouched.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.requirement_service import (
    DecompositionResultDTO,
    RequirementDTO,
)
from application.services import LlmNotConfiguredError
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.requirements import RequirementsToolGroup

pytestmark = pytest.mark.django_db

EDITOR_CTX = AuthContext(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("editor",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
)
API_KEY = "reqlo_testkey_2000"


def _group() -> tuple[RequirementsToolGroup, MagicMock]:
    svc = MagicMock()
    return RequirementsToolGroup(service=svc), svc


def _child() -> RequirementDTO:
    return RequirementDTO(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000010"),
        title="Derived child",
        description="content",
        category="",
        status="draft",
        version=1,
    )


@patch("mcp_server.tools.requirements.write_mcp_audit")
@patch("mcp_server.tools.requirements._check_llm_configured", return_value=True)
def test_empty_decomposition_carries_degraded_reason(mock_llm, mock_audit) -> None:
    """The empty answer stays a success but reports a stable, neutral code.

    The decompose capability is async: an empty ``children`` list means the
    adapter dispatched a task and the children are not in this response yet.
    The response must not assert that the provider returned nothing or that
    the requirement lacked detail.
    """
    group, svc = _group()
    parent_id = uuid.uuid4()
    svc.decompose.return_value = DecompositionResultDTO(
        parent_id=parent_id, children=[]
    )

    result = group.execute_tool(
        "requirement.decompose",
        params={"requirement_id": str(parent_id)},
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is True
    assert result.data["parent_id"] == str(parent_id)
    assert result.data["children"] == []
    assert result.data["degraded"] is True
    assert result.data["degraded_reason"] == "NO_CHILDREN_DERIVED"
    assert result.data["message"]
    # Cause-neutral: never blame the provider or the requirement's detail.
    message = result.data["message"].lower()
    assert "provider" not in message
    assert "description" not in message
    assert "asynchronously" in message
    # F2: the repo pairs `degraded` with stable `degraded_reason`, not a
    # free-text `reason` field.
    assert "reason" not in result.data


@patch("mcp_server.tools.requirements.write_mcp_audit")
@patch("mcp_server.tools.requirements._check_llm_configured", return_value=True)
def test_nonempty_decomposition_has_no_degraded_fields(mock_llm, mock_audit) -> None:
    """The additive keys appear only on the empty-result path."""
    group, svc = _group()
    parent_id = uuid.uuid4()
    svc.decompose.return_value = DecompositionResultDTO(
        parent_id=parent_id, children=[_child()]
    )

    result = group.execute_tool(
        "requirement.decompose",
        params={"requirement_id": str(parent_id)},
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is True
    assert len(result.data["children"]) == 1
    assert "degraded" not in result.data
    assert "degraded_reason" not in result.data
    assert "message" not in result.data
    assert "reason" not in result.data


@patch("mcp_server.tools.requirements.write_mcp_audit")
@patch("mcp_server.tools.requirements._check_llm_configured", return_value=True)
def test_unconfigured_provider_still_returns_llm_not_configured(
    mock_llm, mock_audit
) -> None:
    """#2000 does not change the early ADR-L3-MC003-02 guard."""
    group, svc = _group()
    parent_id = uuid.uuid4()
    svc.decompose.side_effect = LlmNotConfiguredError("no provider")

    result = group.execute_tool(
        "requirement.decompose",
        params={"requirement_id": str(parent_id)},
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is False
    assert result.error_code == "LLM_NOT_CONFIGURED"
