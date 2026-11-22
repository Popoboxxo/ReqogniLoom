"""MCP requirement/architecture boundary fixes, wave 2.

Covers #1984/#2003 (update SE-mask fields + unknown-key rejection), #2002
(``reject_unknown_params`` on the update handler), #1970 (strict title type)
and #2007 (architecture.link reports resolved Artifact ids).

The tests drive the public ``execute_tool`` seam so the ParameterError ->
VALIDATION_ERROR mapping is exercised, not just the pure helpers.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.architecture import ArchitectureToolGroup
from mcp_server.tools.requirements import RequirementsToolGroup

pytestmark = pytest.mark.django_db

EDITOR_CTX = AuthContext(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    active_roles=("editor",),
    auth_method=AuthMethod.API_KEY,
    api_key_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
)
API_KEY = "reqlo_testkey_boundary_wave2"
WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


def _requirement() -> MagicMock:
    req = MagicMock()
    req.id = uuid.UUID("00000000-0000-0000-0000-000000000020")
    req.artifact_id = uuid.UUID("00000000-0000-0000-0000-000000000021")
    req.title = "Req"
    req.description = ""
    req.category = ""
    req.status = "draft"
    req.version = 1
    req.level = 1
    req.acceptance_criteria = ""
    req.verification_method = None
    req.artifact = MagicMock()
    req.artifact.workspace_id = WORKSPACE_ID
    req.artifact.owner = None
    req.artifact.reporter = None
    req.artifact.priority = ""
    req.artifact.custom_fields = {}
    return req


def _update_group() -> tuple[RequirementsToolGroup, MagicMock]:
    svc = MagicMock()
    svc.get_requirement.return_value = _requirement()
    svc.update_requirement.return_value = _requirement()
    return RequirementsToolGroup(service=svc), svc


@patch("mcp_server.tools.requirements.write_mcp_audit")
class TestRequirementUpdateFieldBoundary:
    def test_schema_advertises_se_mask_fields(self, _audit) -> None:
        """#1984/#2003: the static schema must list what the service accepts."""
        group, _ = _update_group()
        schemas = {s["name"]: s for s in group.get_tool_schemas()}
        props = schemas["requirement.update"]["inputSchema"]["properties"]["data"][
            "properties"
        ]
        assert props["acceptance_criteria"]["type"] == "string"
        assert props["verification_method"]["type"] == "string"
        assert "Test" in props["verification_method"]["enum"]

    def test_forwards_acceptance_criteria_and_verification_method(self, _audit) -> None:
        """#1984/#2003: both fields reach RequirementService.update_requirement."""
        group, svc = _update_group()
        result = group.execute_tool(
            "requirement.update",
            params={
                "id": str(uuid.uuid4()),
                "data": {
                    "title": "renamed",
                    "acceptance_criteria": "AC-1 holds",
                    "verification_method": "Test",
                },
            },
            auth_context=EDITOR_CTX,
            api_key=API_KEY,
        )
        assert result.success is True, result.message
        kwargs = svc.update_requirement.call_args.kwargs
        assert kwargs["acceptance_criteria"] == "AC-1 holds"
        assert kwargs["verification_method"] == "Test"

    def test_unset_verification_method_is_not_forwarded(self, _audit) -> None:
        """An implicit None must not clear a nullable SE field (_UNSET sentinel)."""
        group, svc = _update_group()
        result = group.execute_tool(
            "requirement.update",
            params={"id": str(uuid.uuid4()), "data": {"title": "renamed"}},
            auth_context=EDITOR_CTX,
            api_key=API_KEY,
        )
        assert result.success is True, result.message
        assert "verification_method" not in svc.update_requirement.call_args.kwargs
        assert "acceptance_criteria" not in svc.update_requirement.call_args.kwargs

    def test_unknown_nested_key_is_rejected(self, _audit) -> None:
        """#1984/#2002: a typo inside ``data`` is a 400, not a silent no-op."""
        group, svc = _update_group()
        result = group.execute_tool(
            "requirement.update",
            params={"id": str(uuid.uuid4()), "data": {"foo": "bar"}},
            auth_context=EDITOR_CTX,
            api_key=API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "foo" in result.message
        assert "acceptance_criteria" in result.message
        svc.update_requirement.assert_not_called()

    def test_unknown_top_level_key_is_rejected(self, _audit) -> None:
        """#2002: reject_unknown_params also guards the flat envelope."""
        group, svc = _update_group()
        result = group.execute_tool(
            "requirement.update",
            params={"id": str(uuid.uuid4()), "foo": "bar"},
            auth_context=EDITOR_CTX,
            api_key=API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "foo" in result.message
        svc.update_requirement.assert_not_called()

    def test_flat_top_level_fields_still_accepted(self, _audit) -> None:
        """#601 compatibility: strict keys must not break flat callers."""
        group, svc = _update_group()
        result = group.execute_tool(
            "requirement.update",
            params={
                "id": str(uuid.uuid4()),
                "title": "renamed",
                "change_reason": "QA",
                "verification_method": "Analysis",
            },
            auth_context=EDITOR_CTX,
            api_key=API_KEY,
        )
        assert result.success is True, result.message
        kwargs = svc.update_requirement.call_args.kwargs
        assert kwargs["title"] == "renamed"
        assert kwargs["change_reason"] == "QA"
        assert kwargs["verification_method"] == "Analysis"

    def test_status_reporting_still_works(self, _audit) -> None:
        """#2004: read-only reporting survives the strict-key gate."""
        group, svc = _update_group()
        result = group.execute_tool(
            "requirement.update",
            params={"id": str(uuid.uuid4()), "data": {"status": "approved"}},
            auth_context=EDITOR_CTX,
            api_key=API_KEY,
        )
        assert result.success is True, result.message
        assert result.data["ignored_read_only_fields"] == ["status"]
        assert "status" not in svc.update_requirement.call_args.kwargs


@patch("mcp_server.tools.requirements.write_mcp_audit")
class TestRequirementCreateStrictTitle:
    def test_numeric_title_is_rejected(self, _audit) -> None:
        """#1970: ``title=123`` must not be persisted as ``\"123\"``."""
        svc = MagicMock()
        group = RequirementsToolGroup(service=svc)
        result = group.execute_tool(
            "requirement.create",
            params={"workspace_id": str(WORKSPACE_ID), "title": 123},
            auth_context=EDITOR_CTX,
            api_key=API_KEY,
        )
        assert result.success is False
        assert result.error_code == "VALIDATION_ERROR"
        assert "title" in result.message
        assert "string" in result.message
        svc.create_requirement.assert_not_called()

    def test_string_title_still_accepted(self, _audit) -> None:
        svc = MagicMock()
        svc.create_requirement.return_value = _requirement()
        group = RequirementsToolGroup(service=svc)
        result = group.execute_tool(
            "requirement.create",
            params={"workspace_id": str(WORKSPACE_ID), "title": "Valid title"},
            auth_context=EDITOR_CTX,
            api_key=API_KEY,
        )
        assert result.success is True, result.message
        assert svc.create_requirement.call_args.kwargs["title"] == "Valid title"


@patch("mcp_server.tools.architecture.write_mcp_audit")
def test_architecture_link_reports_resolved_artifact_ids(_audit) -> None:
    """#2007: echo the persisted Artifact ids, keep raw ids under old keys."""
    trace_service = MagicMock()
    link = MagicMock()
    link.id = uuid.UUID("00000000-0000-0000-0000-000000000040")
    link.source_id = uuid.UUID("00000000-0000-0000-0000-000000000041")
    link.target_id = uuid.UUID("00000000-0000-0000-0000-000000000042")
    trace_service.create_trace_link.return_value = link
    group = ArchitectureToolGroup(trace_service=trace_service)

    arch_id = uuid.UUID("00000000-0000-0000-0000-000000000050")
    target_id = uuid.UUID("00000000-0000-0000-0000-000000000051")
    result = group.execute_tool(
        "architecture.link",
        params={
            "arch_id": str(arch_id),
            "target_id": str(target_id),
            "link_type": "decomposes",
        },
        auth_context=EDITOR_CTX,
        api_key=API_KEY,
    )

    assert result.success is True, result.message
    trace = result.data["trace_link"]
    assert trace["source_id"] == str(arch_id)
    assert trace["target_id"] == str(target_id)
    assert trace["source_artifact_id"] == str(link.source_id)
    assert trace["target_artifact_id"] == str(link.target_id)
