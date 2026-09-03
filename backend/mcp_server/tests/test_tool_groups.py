"""
Tests for COMP-MC-003..006 Tool Groups.

leaf_id : COMP-MC-003, COMP-MC-004, COMP-MC-005, COMP-MC-006
req_id  : REQ-L2-MC-001 (Requirements tools), REQ-L2-MC-002 (Architecture tools),
          REQ-L2-MC-003 (Test tools), REQ-L2-MC-004 (Cross-cutting tools),
          REQ-L2-MC-009 (direct ApplicationService access),
          REQ-L2-MC-012 (MCP audit trail)

Covers:
- RequirementsToolGroup: all 6 tools call ApplicationService correctly
- ArchitectureToolGroup: all 5 tools including architecture.link
- TestToolGroup: all 5 tools including test.create auto-link and test.link
- CrossCuttingToolGroup: tool routing only (integration tests require DB)
- LLM_NOT_CONFIGURED returned when LLM env var absent
- RBAC errors from ApplicationService propagated correctly
- Audit writes happen for write tools (via write_mcp_audit mock)
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from auth_tenancy.context import AuthContext, AuthMethod

from application.base import (
    NotFoundError,
    PermissionDeniedError,
)

from mcp_server.tools.requirements import RequirementsToolGroup
from mcp_server.tools.architecture import ArchitectureToolGroup
from mcp_server.tools.tests import TestToolGroup
from mcp_server.tools.cross_cutting import CrossCuttingToolGroup
from mcp_server.tools.needs import StakeholderNeedsToolGroup
from mcp_server.tools.base import require_param, require_uuid, ParameterError


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

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

VALID_API_KEY = "reqlo_testkey1234"
WORKSPACE_UUID = UUID("00000000-0000-0000-0000-000000000010")


def _mock_requirement(id_val=None, title="Test Req", description="", category="", status="draft"):
    req = MagicMock()
    req.id = id_val or UUID("00000000-0000-0000-0000-000000000020")
    req.title = title
    req.description = description
    req.category = category
    req.status = status
    req.version = 1
    req.artifact = MagicMock()
    req.artifact.workspace_id = WORKSPACE_UUID
    return req


def _mock_arch_element(id_val=None, title="Arch El", element_type="component", artifact_id=None):
    el = MagicMock()
    el.id = id_val or UUID("00000000-0000-0000-0000-000000000030")
    el.title = title
    el.description = ""
    el.element_type = element_type
    el.version = 1
    el.parent_id = None
    el.artifact = MagicMock()
    el.artifact.workspace_id = WORKSPACE_UUID
    # Backing Artifact FK id (ArchitectureElement.artifact_id) — distinct from
    # el.id, mirrors the real Django OneToOneField auto-attribute.
    el.artifact_id = artifact_id or UUID("00000000-0000-0000-0000-000000000031")
    return el


def _mock_test_case(id_val=None, title="TC-1"):
    tc = MagicMock()
    tc.id = id_val or UUID("00000000-0000-0000-0000-000000000040")
    tc.title = title
    tc.description = ""
    tc.steps = []
    tc.artifact = MagicMock()
    tc.artifact.workspace_id = WORKSPACE_UUID
    tc.artifact.artifact_type = "TestCase:Unit"
    tc.artifact_id = UUID("00000000-0000-0000-0000-000000000041")
    return tc


def _mock_trace_link(id_val=None):
    tl = MagicMock()
    tl.id = id_val or UUID("00000000-0000-0000-0000-000000000050")
    return tl


def _mock_need(id_val=None, title="Test Need", description="", category="", status="draft"):
    need = MagicMock()
    need.id = id_val or UUID("00000000-0000-0000-0000-000000000060")
    need.workspace_id = WORKSPACE_UUID
    need.title = title
    need.description = description
    need.category = category
    need.status = status
    need.moscow_priority = "Must"
    need.version = 1
    return need


# ---------------------------------------------------------------------------
# Base tool group helpers
# ---------------------------------------------------------------------------


class TestBaseHelpers:
    def test_require_param_raises_on_missing(self):
        with pytest.raises(ParameterError):
            require_param({}, "title")

    def test_require_param_returns_value(self):
        assert require_param({"title": "Hello"}, "title") == "Hello"

    def test_require_uuid_raises_on_bad_uuid(self):
        with pytest.raises(ParameterError):
            require_uuid({"id": "not-a-uuid"}, "id")

    def test_require_uuid_returns_uuid(self):
        val = require_uuid({"id": "00000000-0000-0000-0000-000000000001"}, "id")
        assert isinstance(val, UUID)


# ---------------------------------------------------------------------------
# RequirementsToolGroup tests
# ---------------------------------------------------------------------------


class TestRequirementsToolGroup:

    def _group(self, service=None):
        if service is None:
            service = MagicMock()
        return RequirementsToolGroup(service=service), service

    @patch("mcp_server.tools.requirements.write_mcp_audit")
    def test_requirement_get_calls_service(self, mock_audit):
        group, svc = self._group()
        mock_req = _mock_requirement()
        svc.get_requirement.return_value = mock_req

        result = group.execute_tool(
            tool_name="requirement.get",
            params={"id": str(mock_req.id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.get_requirement.assert_called_once_with(mock_req.id, EDITOR_CTX)
        mock_audit.assert_not_called()  # read tool → no audit

    @pytest.mark.parametrize("suspect", [True, False])
    @patch("mcp_server.tools.requirements.write_mcp_audit")
    def test_requirement_get_exposes_suspect_flag(self, mock_audit, suspect):
        """Response fidelity (same class of gap as #409): the MCP surface must
        expose `suspect`, which REST already returns. Without it an agent
        cannot see that TraceLinkService.propagate_suspect_status flagged the
        requirement."""
        group, svc = self._group()
        mock_req = _mock_requirement()
        mock_req.suspect = suspect
        svc.get_requirement.return_value = mock_req

        result = group.execute_tool(
            tool_name="requirement.get",
            params={"id": str(mock_req.id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert result.data["requirement"]["suspect"] is suspect

    @patch("mcp_server.tools.requirements.write_mcp_audit")
    def test_requirement_query_exposes_suspect_flag(self, mock_audit):
        group, svc = self._group()
        mock_req = _mock_requirement()
        mock_req.suspect = True
        svc.list_requirements.return_value = [mock_req]

        result = group.execute_tool(
            tool_name="requirement.query",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert result.data["requirements"][0]["suspect"] is True

    @patch("mcp_server.tools.requirements.write_mcp_audit")
    def test_requirement_create_calls_service_and_audits(self, mock_audit):
        group, svc = self._group()
        mock_req = _mock_requirement()
        svc.create_requirement.return_value = mock_req

        result = group.execute_tool(
            tool_name="requirement.create",
            params={"title": "New Req", "workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.create_requirement.assert_called_once()
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["tool_name"] == "requirement.create"
        assert call_kwargs["operation"] == "create"

    @patch("mcp_server.tools.requirements.write_mcp_audit")
    def test_requirement_update_calls_service_and_audits(self, mock_audit):
        group, svc = self._group()
        mock_req = _mock_requirement()
        svc.update_requirement.return_value = mock_req

        result = group.execute_tool(
            tool_name="requirement.update",
            params={"id": str(mock_req.id), "data": {"title": "Updated"}},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        mock_audit.assert_called_once()

    @patch("mcp_server.tools.requirements.write_mcp_audit")
    def test_requirement_update_accepts_flat_top_level_change_reason(self, mock_audit):
        """Issue #601: requirement.update's documented contract nests fields
        under `data` (issue #21), but need.update accepts flat top-level
        params -- the cross-tool inconsistency led real callers to send
        change_reason at the top level, where it was silently dropped
        (data.get("change_reason") saw None even though the client did send
        it), producing a confusing "change_reason required" error. The
        handler must fall back to top-level params when `data` omits a
        field, without breaking the documented nested contract."""
        group, svc = self._group()
        mock_req = _mock_requirement()
        svc.update_requirement.return_value = mock_req

        result = group.execute_tool(
            tool_name="requirement.update",
            params={
                "id": str(mock_req.id),
                "title": "renamed",
                "change_reason": "QA-Test",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.update_requirement.assert_called_once()
        call_kwargs = svc.update_requirement.call_args.kwargs
        assert call_kwargs["title"] == "renamed"
        assert call_kwargs["change_reason"] == "QA-Test"

    def test_requirement_get_not_found_returns_error(self):
        group, svc = self._group()
        svc.get_requirement.side_effect = NotFoundError("not found")

        result = group.execute_tool(
            tool_name="requirement.get",
            params={"id": "00000000-0000-0000-0000-000000000001"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_requirement_create_permission_denied(self):
        group, svc = self._group()
        svc.create_requirement.side_effect = PermissionDeniedError("no write")

        result = group.execute_tool(
            tool_name="requirement.create",
            params={"title": "X", "workspace_id": str(WORKSPACE_UUID)},
            auth_context=VIEWER_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    @patch.dict(os.environ, {}, clear=True)
    def test_requirement_decompose_without_llm_returns_llm_error(self):
        # Remove any LLM env vars
        for key in ("LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)

        group, svc = self._group()
        result = group.execute_tool(
            tool_name="requirement.decompose",
            params={"requirement_id": "00000000-0000-0000-0000-000000000001"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "LLM_NOT_CONFIGURED"
        svc.decompose.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    def test_requirement_validate_without_llm_returns_llm_error(self):
        for key in ("LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)

        group, svc = self._group()
        result = group.execute_tool(
            tool_name="requirement.validate",
            params={"requirement_id": "00000000-0000-0000-0000-000000000001"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "LLM_NOT_CONFIGURED"

    @patch.dict(os.environ, {"LLM_PROVIDER": "mock"}, clear=True)
    def test_requirement_validate_delegates_to_service_content_path(self):
        """REQ-089: validate routes through the content-bearing service method.

        Before REQ-089 the tool called llm_adapter.validate_artifact(id) with an
        ID only. It must now delegate to RequirementService.validate_requirement,
        which forwards the requirement's title/content (REQ-046).
        """
        req_uuid = "00000000-0000-0000-0000-000000000001"
        group, svc = self._group()
        svc.validate_requirement.return_value = {"valid": True, "issues": []}

        result = group.execute_tool(
            tool_name="requirement.validate",
            params={"requirement_id": req_uuid},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        svc.validate_requirement.assert_called_once_with(UUID(req_uuid), EDITOR_CTX)
        assert result.data["validation_result"] == {"valid": True, "issues": []}

    @patch.dict(os.environ, {"LLM_PROVIDER": "mock"}, clear=True)
    def test_requirement_check_consistency_delegates_to_service(self):
        """REQ-089: the newly wired tool delegates to the service capability."""
        group, svc = self._group()
        svc.check_consistency.return_value = {"task_id": "task-123"}

        result = group.execute_tool(
            tool_name="requirement.check_consistency",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        svc.check_consistency.assert_called_once_with(WORKSPACE_UUID, EDITOR_CTX)
        assert result.data["consistency_result"] == {"task_id": "task-123"}

    @patch.dict(os.environ, {}, clear=True)
    def test_requirement_check_consistency_without_llm_returns_llm_error(self):
        for key in ("LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)

        group, svc = self._group()
        result = group.execute_tool(
            tool_name="requirement.check_consistency",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "LLM_NOT_CONFIGURED"
        svc.check_consistency.assert_not_called()

    def test_requirement_check_consistency_status_delegates_to_service(self):
        """GH-796: the status tool delegates to the service's status query."""
        group, svc = self._group()
        svc.get_consistency_status.return_value = {
            "task_id": "task-123",
            "status": "done",
            "result": {"score": 0.9},
        }

        result = group.execute_tool(
            tool_name="requirement.check_consistency_status",
            params={"task_id": "task-123"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        svc.get_consistency_status.assert_called_once_with("task-123", EDITOR_CTX)
        assert result.data == {
            "task_id": "task-123",
            "status": "done",
            "result": {"score": 0.9},
        }

    def test_requirement_check_consistency_status_requires_task_id(self):
        group, svc = self._group()
        result = group.execute_tool(
            tool_name="requirement.check_consistency_status",
            params={},  # no task_id
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "INVALID_PARAMS"
        svc.get_consistency_status.assert_not_called()

    def test_requirement_query_requires_workspace_id(self):
        group, svc = self._group()
        result = group.execute_tool(
            tool_name="requirement.query",
            params={},  # no workspace_id
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_requirement_query_calls_list(self):
        group, svc = self._group()
        svc.list_requirements.return_value = [_mock_requirement()]

        result = group.execute_tool(
            tool_name="requirement.query",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert result.data["count"] == 1

    def test_unknown_tool_returns_error(self):
        group, _ = self._group()
        result = group.execute_tool(
            tool_name="requirement.nonexistent",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"

    # -----------------------------------------------------------------
    # requirement.derive (Issue #459 finding 2: the MCP handler forwards
    # description as-is — the inherit-from-parent-if-omitted fallback lives
    # in RequirementService.derive_requirement, covered by
    # application/tests/test_requirement_service.py
    # TestDeriveRequirementDescriptionInheritance)
    # -----------------------------------------------------------------

    @patch("mcp_server.tools.requirements.write_mcp_audit")
    def test_requirement_derive_without_description_forwards_empty_string(self, mock_audit):
        group, svc = self._group()
        child = _mock_requirement(
            id_val=UUID("00000000-0000-0000-0000-000000000021"),
            title="Child",
            description="Inherited parent description",
        )
        derive_result = MagicMock()
        derive_result.children = [child]
        derive_result.parent_id = UUID("00000000-0000-0000-0000-000000000020")
        derive_result.trace_link_ids = [UUID("00000000-0000-0000-0000-000000000050")]
        svc.derive_requirement.return_value = derive_result

        result = group.execute_tool(
            tool_name="requirement.derive",
            params={
                "parent_requirement_id": "00000000-0000-0000-0000-000000000020",
                "architecture_element_id": "00000000-0000-0000-0000-000000000030",
                "title": "Child",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        # No description passed by the caller → MCP layer forwards "" and
        # relies on RequirementService.derive_requirement to inherit the
        # parent's description (it must NOT invent one itself here).
        assert svc.derive_requirement.call_args.kwargs["description"] == ""
        # The response reflects whatever the service actually persisted.
        assert result.data["requirement"]["description"] == "Inherited parent description"
        mock_audit.assert_called_once()

    @patch("mcp_server.tools.requirements.write_mcp_audit")
    def test_requirement_derive_with_explicit_description_forwards_it(self, mock_audit):
        group, svc = self._group()
        child = _mock_requirement(
            id_val=UUID("00000000-0000-0000-0000-000000000021"),
            title="Child",
            description="Explicit description",
        )
        derive_result = MagicMock()
        derive_result.children = [child]
        derive_result.parent_id = UUID("00000000-0000-0000-0000-000000000020")
        derive_result.trace_link_ids = []
        svc.derive_requirement.return_value = derive_result

        result = group.execute_tool(
            tool_name="requirement.derive",
            params={
                "parent_requirement_id": "00000000-0000-0000-0000-000000000020",
                "architecture_element_id": "00000000-0000-0000-0000-000000000030",
                "title": "Child",
                "description": "Explicit description",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert svc.derive_requirement.call_args.kwargs["description"] == "Explicit description"


# ---------------------------------------------------------------------------
# ArchitectureToolGroup tests
# ---------------------------------------------------------------------------


class TestArchitectureToolGroup:

    def _group(self, service=None, trace_service=None):
        service = service or MagicMock()
        trace_service = trace_service or MagicMock()
        return ArchitectureToolGroup(service=service, trace_service=trace_service), service, trace_service

    def test_architecture_get_calls_service(self):
        group, svc, _ = self._group()
        el = _mock_arch_element()
        svc.get_architecture_element.return_value = el

        result = group.execute_tool(
            tool_name="architecture.get",
            params={"id": str(el.id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.get_architecture_element.assert_called_once_with(el.id, EDITOR_CTX)

    def test_architecture_get_includes_artifact_id(self):
        """Follow-up fix: _arch_el_to_dict must expose 'artifact_id' (the
        ArchitectureElement's backing Artifact id) so MCP callers can resolve
        requirement_bundle.export's item-level 'found_under_element_id',
        which is documented as being that same artifact_id, not an
        ArchitectureElement id. Restores parity with
        ArchitectureElementSerializer (rest_api/serializers.py), which
        already exposes this field."""
        group, svc, _ = self._group()
        artifact_id = UUID("00000000-0000-0000-0000-0000000000aa")
        el = _mock_arch_element(artifact_id=artifact_id)
        svc.get_architecture_element.return_value = el

        result = group.execute_tool(
            tool_name="architecture.get",
            params={"id": str(el.id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert result.data["architecture_element"]["artifact_id"] == str(artifact_id)
        # It must be the Artifact id, not the ArchitectureElement id itself.
        assert result.data["architecture_element"]["artifact_id"] != str(el.id)

    @patch("mcp_server.tools.architecture.write_mcp_audit")
    def test_architecture_create_calls_service_and_audits(self, mock_audit):
        group, svc, _ = self._group()
        el = _mock_arch_element()
        svc.create_architecture_element.return_value = el

        result = group.execute_tool(
            tool_name="architecture.create",
            params={"title": "My System", "workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert "architecture_element" in result.data
        mock_audit.assert_called_once()
        # Backward compatibility: omitting parent_id forwards None (root).
        assert svc.create_architecture_element.call_args.kwargs["parent_id"] is None

    @patch("mcp_server.tools.architecture.write_mcp_audit")
    def test_architecture_create_forwards_parent_id_to_service(self, mock_audit):
        """#fix: architecture.create previously dropped 'parent_id' silently.
        Confirm it now reaches the ArchitectureService call, matching the
        REST API's ArchitectureElementViewSet.create behaviour."""
        group, svc, _ = self._group()
        el = _mock_arch_element()
        svc.create_architecture_element.return_value = el
        parent_id = "00000000-0000-0000-0000-000000000099"

        result = group.execute_tool(
            tool_name="architecture.create",
            params={
                "title": "Child",
                "workspace_id": str(WORKSPACE_UUID),
                "parent_id": parent_id,
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.create_architecture_element.assert_called_once_with(
            workspace_id=WORKSPACE_UUID,
            title="Child",
            ctx=EDITOR_CTX,
            description="",
            element_type="component",
            parent_id=UUID(parent_id),
        )

    @patch("mcp_server.tools.architecture.write_mcp_audit")
    def test_architecture_update_forwards_parent_id_to_service(self, mock_audit):
        """architecture.update must forward an explicit 'parent_id' (including
        null, to detach to root) for re-parenting via MCP, matching REST's
        partial_update contract."""
        group, svc, _ = self._group()
        el = _mock_arch_element()
        svc.update_architecture_element.return_value = el
        parent_id = "00000000-0000-0000-0000-000000000088"

        result = group.execute_tool(
            tool_name="architecture.update",
            params={
                "id": str(el.id),
                "data": {"expected_version": 1, "parent_id": parent_id},
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.update_architecture_element.assert_called_once_with(
            arch_el_id=el.id,
            ctx=EDITOR_CTX,
            expected_version=1,
            title=None,
            description=None,
            element_type=None,
            parent_id=UUID(parent_id),
        )

    @patch("mcp_server.tools.architecture.write_mcp_audit")
    def test_architecture_link_with_valid_type_calls_trace_service(self, mock_audit):
        group, svc, trace_svc = self._group()
        tl = _mock_trace_link()
        trace_svc.create_trace_link.return_value = tl

        result = group.execute_tool(
            tool_name="architecture.link",
            params={
                "arch_id": "00000000-0000-0000-0000-000000000030",
                "target_id": "00000000-0000-0000-0000-000000000020",
                "link_type": "implements",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert "trace_link" in result.data
        trace_svc.create_trace_link.assert_called_once()
        mock_audit.assert_called_once()

    def test_architecture_link_invalid_type_returns_validation_error(self):
        group, _, _ = self._group()
        result = group.execute_tool(
            tool_name="architecture.link",
            params={
                "arch_id": "00000000-0000-0000-0000-000000000030",
                "target_id": "00000000-0000-0000-0000-000000000020",
                "link_type": "invalid_link_type",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_architecture_query_requires_workspace_id(self):
        group, _, _ = self._group()
        result = group.execute_tool(
            tool_name="architecture.query",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_architecture_link_schema_documents_valid_link_types(self):
        """#33: architecture.link's published schema must enumerate the
        valid link_type values so callers (including LLM/MCP clients) can
        discover them without a failed round-trip first.

        Codeberg #353 final review (I1): the enum is MANUAL_LINK_TYPES, not
        the full VALID_LINK_TYPES — 'diagram-ref' is reconciler-owned and
        must never be offered as a manually-createable link type."""
        from traceability.types import MANUAL_LINK_TYPES, LinkType

        schema = next(
            s
            for s in ArchitectureToolGroup._TOOL_SCHEMAS
            if s["name"] == "architecture.link"
        )
        link_type_prop = schema["inputSchema"]["properties"]["link_type"]
        assert "enum" in link_type_prop
        assert set(link_type_prop["enum"]) == set(MANUAL_LINK_TYPES)
        assert LinkType.DIAGRAM_REF.value not in link_type_prop["enum"]

    def test_architecture_get_not_found(self):
        group, svc, _ = self._group()
        svc.get_architecture_element.side_effect = NotFoundError("not found")

        result = group.execute_tool(
            tool_name="architecture.get",
            params={"id": "00000000-0000-0000-0000-000000000001"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# TestToolGroup tests
# ---------------------------------------------------------------------------


class TestTestToolGroup:

    def _group(self, service=None, trace_service=None, ai_derivation_service=None):
        service = service or MagicMock()
        trace_service = trace_service or MagicMock()
        ai_derivation_service = ai_derivation_service or MagicMock()
        return (
            TestToolGroup(
                service=service,
                trace_service=trace_service,
                ai_derivation_service=ai_derivation_service,
            ),
            service,
            trace_service,
            ai_derivation_service,
        )

    def test_test_get_calls_service(self):
        group, svc, _, _ = self._group()
        tc = _mock_test_case()
        svc.get_test_case.return_value = tc

        result = group.execute_tool(
            tool_name="test.get",
            params={"id": str(tc.id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.get_test_case.assert_called_once_with(tc.id, EDITOR_CTX)

    @patch("mcp_server.tools.tests.write_mcp_audit")
    def test_test_create_calls_service_and_audits(self, mock_audit):
        group, svc, trace_svc, _ = self._group()
        tc = _mock_test_case()
        svc.create_test_case.return_value = tc

        result = group.execute_tool(
            tool_name="test.create",
            params={"title": "TC-New", "workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.create_test_case.assert_called_once()
        mock_audit.assert_called()

    @patch("mcp_server.tools.tests.write_mcp_audit")
    def test_test_create_with_linked_req_creates_trace_link(self, mock_audit):
        group, svc, trace_svc, _ = self._group()
        tc = _mock_test_case()
        svc.create_test_case.return_value = tc
        tl = _mock_trace_link()
        trace_svc.create_trace_link.return_value = tl

        result = group.execute_tool(
            tool_name="test.create",
            params={
                "title": "TC-Linked",
                "workspace_id": str(WORKSPACE_UUID),
                "linked_req_id": "00000000-0000-0000-0000-000000000020",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        trace_svc.create_trace_link.assert_called_once()
        _, kwargs = trace_svc.create_trace_link.call_args
        assert kwargs["link_type"] == "verifies"

    @patch("mcp_server.tools.tests.write_mcp_audit")
    def test_test_update_status_calls_update_test_status(self, mock_audit):
        group, svc, _, _ = self._group()
        tc = _mock_test_case()
        svc.update_test_status.return_value = tc

        result = group.execute_tool(
            tool_name="test.update",
            params={"id": str(tc.id), "data": {"status": "Passed"}},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.update_test_status.assert_called_once_with(
            test_case_id=tc.id, execution_status="Passed", ctx=EDITOR_CTX
        )
        mock_audit.assert_called_once()

    def test_test_update_invalid_status_returns_validation_error(self):
        group, svc, _, _ = self._group()
        result = group.execute_tool(
            tool_name="test.update",
            params={"id": "00000000-0000-0000-0000-000000000040", "data": {"status": "Unknown"}},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.update_test_status.assert_not_called()

    @patch("mcp_server.tools.tests.write_mcp_audit")
    def test_test_link_creates_verifies_trace_link(self, mock_audit):
        group, svc, trace_svc, _ = self._group()
        tc = _mock_test_case()
        svc.get_test_case.return_value = tc
        tl = _mock_trace_link()
        trace_svc.create_trace_link.return_value = tl

        result = group.execute_tool(
            tool_name="test.link",
            params={
                "test_id": str(tc.id),
                "req_id": "00000000-0000-0000-0000-000000000020",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert result.data["trace_link"]["link_type"] == "verifies"
        mock_audit.assert_called_once()

    def test_test_query_requires_workspace_id(self):
        group, _, _, _ = self._group()
        result = group.execute_tool(
            tool_name="test.query",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    # -----------------------------------------------------------------
    # test.run_create (Issue #459 finding 1: unknown params must be rejected,
    # not silently ignored)
    # -----------------------------------------------------------------

    @patch("mcp_server.tools.tests.write_mcp_audit")
    def test_run_create_with_correct_test_case_ids_succeeds(self, mock_audit):
        # test.run_create uses a dedicated `run_service` (TestRunService),
        # not the `service` (TestService) constructed by self._group() —
        # must be mocked explicitly here.
        run_service = MagicMock()
        group = TestToolGroup(
            service=MagicMock(),
            trace_service=MagicMock(),
            run_service=run_service,
            ai_derivation_service=MagicMock(),
        )
        tr = MagicMock()
        tr.id = UUID("00000000-0000-0000-0000-000000000099")
        tr.workspace_id = WORKSPACE_UUID
        run_service.create_test_run.return_value = tr

        tc_id = "00000000-0000-0000-0000-000000000042"
        result = group.execute_tool(
            tool_name="test.run_create",
            params={
                "workspace_id": str(WORKSPACE_UUID),
                "name": "Run 1",
                "test_case_ids": [tc_id],
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        run_service.create_test_run.assert_called_once()
        assert run_service.create_test_run.call_args.kwargs["test_case_ids"] == [UUID(tc_id)]

    def test_run_create_rejects_unknown_singular_test_case_id_param(self):
        """A caller sending 'test_case_id' (singular, the wrong/undocumented
        name) instead of 'test_case_ids' must get a VALIDATION_ERROR naming
        the unknown parameter, instead of the run silently being created
        without any test cases attached."""
        run_service = MagicMock()
        group = TestToolGroup(
            service=MagicMock(),
            trace_service=MagicMock(),
            run_service=run_service,
            ai_derivation_service=MagicMock(),
        )

        result = group.execute_tool(
            tool_name="test.run_create",
            params={
                "workspace_id": str(WORKSPACE_UUID),
                "name": "Run 1",
                "test_case_id": "00000000-0000-0000-0000-000000000042",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "test_case_id" in result.message
        assert "test_case_ids" in result.message
        run_service.create_test_run.assert_not_called()

    def test_run_create_with_title_instead_of_name_names_unknown_param(self):
        """A caller sending 'title' instead of the documented 'name' must be
        told which parameter is unknown, not just that 'name' is missing."""
        run_service = MagicMock()
        group = TestToolGroup(
            service=MagicMock(),
            trace_service=MagicMock(),
            run_service=run_service,
            ai_derivation_service=MagicMock(),
        )

        result = group.execute_tool(
            tool_name="test.run_create",
            params={"workspace_id": str(WORKSPACE_UUID), "title": "Run 1"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "title" in result.message
        run_service.create_test_run.assert_not_called()

    # -----------------------------------------------------------------
    # test.derive_from_requirement (SysEng 2.0 N5)
    # -----------------------------------------------------------------

    def test_derive_from_requirement_calls_service(self):
        group, _, _, ai_svc = self._group()
        req_id = "00000000-0000-0000-0000-000000000020"
        ai_svc.derive_testcase_from_requirement.return_value = {
            "draft": {
                "title": "Test: Req",
                "description": "Verifies the requirement.",
                "steps": [{"step": "Do X", "expected_result": "Y happens"}],
            },
            "requirement_id": req_id,
        }

        result = group.execute_tool(
            tool_name="test.derive_from_requirement",
            params={"requirement_id": req_id},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        assert result.data["requirement_id"] == req_id
        assert result.data["draft"]["title"] == "Test: Req"
        ai_svc.derive_testcase_from_requirement.assert_called_once_with(
            EDITOR_CTX, UUID(req_id)
        )

    def test_derive_from_requirement_not_found(self):
        group, _, _, ai_svc = self._group()
        ai_svc.derive_testcase_from_requirement.side_effect = NotFoundError("gone")

        result = group.execute_tool(
            tool_name="test.derive_from_requirement",
            params={"requirement_id": "00000000-0000-0000-0000-000000000020"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"

    def test_derive_from_requirement_requires_requirement_id(self):
        group, _, _, _ = self._group()
        result = group.execute_tool(
            tool_name="test.derive_from_requirement",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_derive_from_requirement_is_registered_as_write_tool(self):
        """Phase 3 (REQ-L2-AI-003): mode='write' makes this tool capable of
        mutation, so it is now registered in tool_registry._WRITE_TOOL_PREFIXES
        (name-based gate, not mode-aware — see mcp_server/tools/tests.py
        module docstring). Supersedes the pre-Phase-3
        test_derive_from_requirement_is_not_a_write_tool assumption.
        """
        from mcp_server.tool_registry import _WRITE_TOOL_PREFIXES

        tool_name = "test.derive_from_requirement"
        assert any(
            tool_name == wt or tool_name.startswith(wt) for wt in _WRITE_TOOL_PREFIXES
        )

    # ------------------------------------------------------------------
    # test.run_report_results (Codeberg #106 -- single object rejected)
    # ------------------------------------------------------------------

    def _group_with_run_service(self, run_service=None):
        run_service = run_service or MagicMock()
        group = TestToolGroup(
            service=MagicMock(),
            trace_service=MagicMock(),
            run_service=run_service,
            ai_derivation_service=MagicMock(),
        )
        return group, run_service

    def test_run_report_results_accepts_single_object(self):
        """A single result object (not wrapped in a list) must be accepted."""
        group, run_svc = self._group_with_run_service()
        run_svc.add_results_bulk.return_value = [MagicMock()]
        run_id = "00000000-0000-0000-0000-000000000070"
        tc_id = "00000000-0000-0000-0000-000000000071"

        result = group.execute_tool(
            tool_name="test.run_report_results",
            params={
                "run_id": run_id,
                "results": {"test_case_id": tc_id, "status": "passed"},
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        run_svc.add_results_bulk.assert_called_once()
        call_kwargs = run_svc.add_results_bulk.call_args.kwargs
        assert call_kwargs["results"] == [
            {
                "test_case_id": tc_id,
                "status": "passed",
                "message": "",
                "duration_ms": None,
            }
        ]

    def test_run_report_results_accepts_list(self):
        group, run_svc = self._group_with_run_service()
        run_svc.add_results_bulk.return_value = [MagicMock()]
        run_id = "00000000-0000-0000-0000-000000000070"
        tc_id = "00000000-0000-0000-0000-000000000071"

        result = group.execute_tool(
            tool_name="test.run_report_results",
            params={
                "run_id": run_id,
                "results": [{"test_case_id": tc_id, "status": "passed"}],
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        run_svc.add_results_bulk.assert_called_once()

    def test_run_report_results_rejects_empty_list(self):
        group, run_svc = self._group_with_run_service()

        result = group.execute_tool(
            tool_name="test.run_report_results",
            params={"run_id": "00000000-0000-0000-0000-000000000070", "results": []},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        run_svc.add_results_bulk.assert_not_called()

    # ------------------------------------------------------------------
    # test.run_complete (GH-403: lifecycle had no way to leave in_progress)
    # ------------------------------------------------------------------

    @patch("mcp_server.tools.tests.write_mcp_audit")
    def test_run_complete_calls_close_test_run(self, mock_audit):
        group, run_svc = self._group_with_run_service()
        run_id = UUID("00000000-0000-0000-0000-000000000070")
        tr = MagicMock()
        tr.id = run_id
        tr.workspace_id = WORKSPACE_UUID
        tr.name = "Run 1"
        tr.status = "passed"
        tr.ci_job_id = ""
        tr.started_at = None
        tr.finished_at = None
        run_svc.close_test_run.return_value = tr

        result = group.execute_tool(
            tool_name="test.run_complete",
            params={"run_id": str(run_id)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is True
        run_svc.close_test_run.assert_called_once_with(
            test_run_id=run_id, ctx=EDITOR_CTX
        )
        assert result.data["test_run"]["status"] == "passed"
        mock_audit.assert_called_once()

    def test_run_complete_not_found_returns_error(self):
        from application.base import NotFoundError

        group, run_svc = self._group_with_run_service()
        run_svc.close_test_run.side_effect = NotFoundError("TestRun not found")

        result = group.execute_tool(
            tool_name="test.run_complete",
            params={"run_id": "00000000-0000-0000-0000-000000000070"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )

        assert result.success is False
        assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# CrossCuttingToolGroup tests (basic routing, no DB)
# ---------------------------------------------------------------------------


class TestCrossCuttingToolGroup:

    def _group(self, artifact_svc=None, search_svc=None, trace_svc=None):
        artifact_svc = artifact_svc or MagicMock()
        search_svc = search_svc or MagicMock()
        trace_svc = trace_svc or MagicMock()
        return (
            CrossCuttingToolGroup(
                artifact_service=artifact_svc,
                search_service=search_svc,
                trace_service=trace_svc,
            ),
            artifact_svc,
            search_svc,
            trace_svc,
        )

    def test_artifact_search_calls_search_service(self):
        group, artifact_svc, search_svc, _ = self._group()

        from application.services import SearchResult

        mock_result = MagicMock(spec=SearchResult)
        mock_result.results = []
        mock_result.total_count = 0
        mock_result.page = 1
        mock_result.limit = 20
        search_svc.search.return_value = mock_result

        result = group.execute_tool(
            tool_name="artifact.search",
            params={"query": "authentication"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        search_svc.search.assert_called_once()

    def test_artifact_search_schema_publishes_full_type_filter_enum(self):
        """#345 Finding 2b: `type_filter` used to accept only Requirement/
        ArchitectureElement/TestCase — Needs, Goals and ADRs 400ed. The
        published enum must be exactly what the service accepts."""
        from application.search_service import SEARCHABLE_ARTIFACT_TYPES

        group, _, _, _ = self._group()
        schema = next(
            s for s in group.get_tool_schemas() if s["name"] == "artifact.search"
        )["inputSchema"]

        enum_values = schema["properties"]["type_filter"]["items"]["enum"]
        assert set(enum_values) == set(SEARCHABLE_ARTIFACT_TYPES)
        assert {"StakeholderNeed", "Goal", "Adr"} <= set(enum_values)

    def test_artifact_search_requires_query(self):
        group, _, _, _ = self._group()
        result = group.execute_tool(
            tool_name="artifact.search",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        # Empty query param → ParameterError → VALIDATION_ERROR
        assert result.success is False

    def test_artifact_get_tree_requires_workspace_id(self):
        group, _, _, _ = self._group()
        result = group.execute_tool(
            tool_name="artifact.get_tree",
            params={"root_id": "00000000-0000-0000-0000-000000000001"},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_workspace_get_context_returns_tenant_id(self):
        group, _, _, _ = self._group()
        result = group.execute_tool(
            tool_name="workspace.get_context",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        assert result.data["workspace_context"]["tenant_id"] == str(EDITOR_CTX.tenant_id)

    def test_traceability_query_invalid_direction(self):
        group, _, _, _ = self._group()
        result = group.execute_tool(
            tool_name="traceability.query",
            params={
                "artifact_id": "00000000-0000-0000-0000-000000000001",
                "direction": "sideways",
            },
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"

    def test_unknown_tool_returns_unknown_tool_error(self):
        group, _, _, _ = self._group()
        result = group.execute_tool(
            tool_name="workspace.nonexistent",
            params={},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "UNKNOWN_TOOL"


    def test_workspace_get_context_description_documents_response_fields(self):
        """Codeberg #110 -- active_roles/preset/terminology/open_requirements_count
        must be documented in the tool description, not just present at runtime."""
        group, _, _, _ = self._group()
        schema = next(
            s for s in group.get_tool_schemas() if s["name"] == "workspace.get_context"
        )
        description = schema["description"]
        for field in (
            "active_roles",
            "preset",
            "preset_features",
            "terminology",
            "open_requirements_count",
        ):
            assert field in description, f"{field!r} missing from workspace.get_context description"


# ---------------------------------------------------------------------------
# StakeholderNeedsToolGroup tests (Codeberg #116 -- needs.query was missing)
# ---------------------------------------------------------------------------

class TestStakeholderNeedsToolGroup:

    def _group(self, service=None):
        if service is None:
            service = MagicMock()
        return StakeholderNeedsToolGroup(service=service), service

    def test_needs_query_requires_workspace_id(self):
        group, svc = self._group()
        result = group.execute_tool(
            tool_name="needs.query",
            params={},  # no workspace_id
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        svc.list_by_workspace.assert_not_called()

    def test_needs_query_calls_service(self):
        group, svc = self._group()
        svc.list_by_workspace.return_value = [_mock_need()]

        result = group.execute_tool(
            tool_name="needs.query",
            params={"workspace_id": str(WORKSPACE_UUID)},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.list_by_workspace.assert_called_once_with(
            EDITOR_CTX, WORKSPACE_UUID, include_deleted=False
        )
        assert result.data["count"] == 1
        assert result.data["needs"][0]["title"] == "Test Need"

    def test_needs_query_passes_include_deleted(self):
        group, svc = self._group()
        svc.list_by_workspace.return_value = []

        result = group.execute_tool(
            tool_name="needs.query",
            params={"workspace_id": str(WORKSPACE_UUID), "include_deleted": True},
            auth_context=EDITOR_CTX,
            api_key=VALID_API_KEY,
        )
        assert result.success is True
        svc.list_by_workspace.assert_called_once_with(
            EDITOR_CTX, WORKSPACE_UUID, include_deleted=True
        )
