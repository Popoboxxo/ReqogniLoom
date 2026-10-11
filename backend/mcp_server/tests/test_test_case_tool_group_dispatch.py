"""
Dispatch-level tests for the TestCase tool group (COMP-MC-005, 14 tools).

``test_testcase_status_lowercase_453.py`` and ``test_tool_groups.py`` already
pin selected handlers (lowercase lifecycle status, call forwarding against a
mocked service). This module closes the gaps a mocked service cannot see: it
drives every ``test.*`` tool through the PUBLIC interface
``BaseToolGroup.execute_tool`` from the boundaries a real call arrives through:

* real-DB round trips (create -> get -> query -> update (status + fields)
  -> link -> mark_reviewed -> outdate/reactivate;
  run_create -> run_report_results -> run_get -> run_list -> run_complete),
* parameter validation for every tool's required uuid / array / boolean,
* the RBAC fence of a real viewer context (write -> PERMISSION_DENIED),
* the cross-tenant read fence (another tenant's id -> NOT_FOUND via RLS),
* service-error -> MCP-code mapping (NotFoundError -> NOT_FOUND,
  ValidationError -> VALIDATION_ERROR, PermissionDeniedError ->
  PERMISSION_DENIED, unmapped exception -> masked INTERNAL_ERROR),
* the CWE-209 masking contract: an unmapped error never leaks its message.

leaf_id : COMP-MC-005
req_id  : REQ-L2-MC-005
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from application.requirement_service import RequirementService
from application.test_service import TestService
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.workspace_store import provision_workspace_link_types
from mcp_server.tools.tests import McpTestToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

_API_KEY = "reqlo_testkey_test_dispatch"

# tool name -> the schema-required UUID parameter the handler validates first
_ID_PARAM_BY_TOOL = {
    "test.get": "id",
    "test.update": "id",
    "test.link": "test_id",
    "test.outdate": "id",
    "test.reactivate": "id",
    "test.run_get": "run_id",
    "test.run_complete": "run_id",
    "test.run_report_results": "run_id",
    "test.mark_reviewed": "test_case_id",
    "test.derive_from_requirement": "requirement_id",
}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def caller():
    """Tenant + workspace + workflows + editor AuthContext, tenant-scoped.

    Mirrors ``test_requirements_tool_group_dispatch.py``'s ``caller``: the
    request tenant is armed for BOTH isolation layers (thread-local +
    PostgreSQL ``app.current_tenant``), so the RLS fence of the test database
    applies while the tool runs. Both the TestCase and Requirement workflows
    are provisioned: the lifecycle tools (outdate/reactivate) and the
    test.link target need them.
    """
    suffix = uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"MCP test dispatch {suffix}", slug=f"mcp-test-{suffix}"
    )
    user = User.objects.create(
        username=f"mcptest-{suffix}-user",
        email=f"mcptest-{suffix}@t.test",
        tenant=tenant,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(
            tenant=tenant, name=f"ws-{suffix}"
        )
        # TraceLink validation is always-on: an unprovisioned workspace has an
        # empty link-type catalog and rejects every trace link (test.link).
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        # The outdate/reactivate tools route through the workflow engine, which
        # needs a (workspace, item_type) definition to exist.
        create_default_workflow(
            workspace_id=workspace.id,
            preset="testcase_default",
            item_type="TestCase",
            tenant_id=tenant.id,
        )
        # test.link / the derive write path resolve Requirements as targets.
        create_default_workflow(
            workspace_id=workspace.id,
            preset="standard",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=tenant.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
            api_key_id=None,
        )
        yield tenant, workspace, ctx
    finally:
        TenantContext.clear_tenant()
        clear_request_tenant()


def _exec(group, tool, params, ctx):
    """Run *tool* through the public tool-group dispatch interface."""
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=_API_KEY
    )


def _create(caller, title="Dispatch TC", **extra):
    """test.create through the public interface; returns the payload."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.create",
        {"workspace_id": str(workspace.id), "title": title, **extra},
        ctx,
    )
    assert result.success is True, result.message
    return result.data["test_case"]


def _make_requirement(caller, title="Link target"):
    """A real Requirement in the caller's workspace (test.link target)."""
    _tenant, workspace, ctx = caller
    return RequirementService().create_requirement(
        workspace_id=workspace.id, title=title, ctx=ctx
    )


def _group_with_service():
    """A group whose TestService is a MagicMock (other services default)."""
    service = MagicMock()
    return McpTestToolGroup(service=service), service


def _group_with_run_service():
    """A group whose TestRunService is a MagicMock."""
    run_service = MagicMock()
    return McpTestToolGroup(run_service=run_service), run_service


def _viewer_ctx_of(caller) -> AuthContext:
    """A viewer context inside the SAME tenant as *caller*."""
    return AuthContext(
        user_id=caller[0].id,
        tenant_id=caller[0].id,
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )


def _params_for(tool_name: str) -> dict:
    """Valid-on-the-wire params whose *values* never resolve to a row.

    Every value is a syntactically valid UUID/string so parameter validation
    passes and the mocked service error under test is the FIRST thing the
    handler returns.
    """
    some_id = str(uuid4())
    params = {
        "test.get": {"id": some_id},
        "test.query": {"workspace_id": some_id},
        "test.create": {"workspace_id": some_id, "title": "T"},
        "test.update": {"id": some_id, "data": {}},
        "test.link": {"test_id": some_id, "req_id": some_id},
        "test.run_get": {"run_id": some_id},
        "test.run_complete": {"run_id": some_id},
        "test.run_report_results": {
            "run_id": some_id,
            "results": [{"test_case_id": some_id, "status": "passed"}],
        },
        "test.run_create": {"workspace_id": some_id, "name": "Run"},
        "test.mark_reviewed": {"test_case_id": some_id},
        "test.derive_from_requirement": {"requirement_id": some_id},
        "test.outdate": {"id": some_id},
        "test.reactivate": {"id": some_id},
    }
    return params[tool_name]


def _ai_service():
    """An AiDerivationService double for the derive preview/write paths."""
    ai = MagicMock()
    ai.derive_testcase_from_requirement.return_value = {
        "draft": {
            "title": "Draft TC",
            "description": "Draft description",
            "steps": [{"step": "do", "expected_result": "ok"}],
        },
        "is_mock_fallback": True,
    }
    requirement = MagicMock()
    requirement.artifact.workspace_id = uuid4()
    ai._get_requirement.return_value = requirement
    ai._write_derived_entity.return_value = {"id": str(uuid4()), "title": "Draft TC"}
    return ai


# ---------------------------------------------------------------------------
# Real-DB round trip: create -> get -> query -> update
# ---------------------------------------------------------------------------


def test_create_then_get_round_trip_through_dispatch(caller):
    """The create payload (custom_fields incl.) survives and reads back."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.create",
        {
            "workspace_id": str(workspace.id),
            "title": "Roundtrip TC",
            "description": "steps live on the case",
            "test_type": "unit",
            "custom_fields": {"suite": "smoke"},
        },
        ctx,
    )

    assert result.success is True
    payload = result.data["test_case"]
    assert payload["title"] == "Roundtrip TC"
    assert payload["test_type"] == "unit"
    assert payload["custom_fields"]["suite"] == "smoke"
    assert payload["status"] == "draft"
    assert payload["workspace_id"] == str(workspace.id)

    fetched = _exec(group, "test.get", {"id": payload["id"]}, ctx)
    assert fetched.success is True
    assert fetched.data["test_case"]["custom_fields"]["suite"] == "smoke"


def test_create_accepts_deprecated_type_alias(caller):
    """#1151: `type` is the documented deprecated alias of `test_type`."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.create",
        {
            "workspace_id": str(workspace.id),
            "title": "Alias TC",
            "type": "Unit",
        },
        ctx,
    )

    assert result.success is True, result.message
    assert result.data["test_case"]["test_type"] == "unit"


def test_create_rejects_conflicting_test_type_spellings(caller):
    """#1151: two spellings normalising to different values are refused."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.create",
        {
            "workspace_id": str(workspace.id),
            "title": "Conflict TC",
            "test_type": "unit",
            "type": "Acceptance",
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_query_lists_created_test_cases_with_count(caller):
    """The list payload carries the lowercase lifecycle status (GH-453)."""
    _tenant, workspace, ctx = caller
    _create(caller, "Query TC")

    group = McpTestToolGroup()
    result = _exec(group, "test.query", {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is True
    assert result.data["count"] == 1
    row = result.data["test_cases"][0]
    assert row["title"] == "Query TC"
    assert row["status"] == "draft"


def test_update_execution_status_path_round_trip(caller):
    """data.status carries the EXECUTION status (Passed/Failed/Not Run)."""
    _tenant, _workspace, ctx = caller
    tc = _create(caller, "Status TC")
    group = McpTestToolGroup()

    result = _exec(
        group,
        "test.update",
        {"id": tc["id"], "data": {"status": "Passed"}},
        ctx,
    )

    assert result.success is True
    assert result.data["test_case"]["id"] == tc["id"]


def test_update_rejects_lifecycle_value_with_actionable_hint(caller):
    """GH-453: a lifecycle value in data.status gets the review/workflow hint."""
    _tenant, _workspace, ctx = caller
    tc = _create(caller, "Hint TC")
    group = McpTestToolGroup()

    result = _exec(
        group,
        "test.update",
        {"id": tc["id"], "data": {"status": "draft"}},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "lifecycle status" in result.message


def test_update_field_path_changes_title(caller):
    """The general field branch writes title and reads the new value back."""
    _tenant, _workspace, ctx = caller
    tc = _create(caller, "Old title")
    group = McpTestToolGroup()

    updated = _exec(
        group,
        "test.update",
        {"id": tc["id"], "data": {"title": "New title"}},
        ctx,
    )
    assert updated.success is True
    assert updated.data["test_case"]["title"] == "New title"

    fetched = _exec(group, "test.get", {"id": tc["id"]}, ctx)
    assert fetched.data["test_case"]["title"] == "New title"


def test_link_creates_verifies_trace_link_on_real_db(caller):
    """ADR-L3-MC005-03: the link type is always 'verifies' for test -> req."""
    _tenant, _workspace, ctx = caller
    tc = _create(caller, "Link TC")
    requirement = _make_requirement(caller)
    group = McpTestToolGroup()

    result = _exec(
        group,
        "test.link",
        {"test_id": tc["id"], "req_id": str(requirement.id)},
        ctx,
    )

    assert result.success is True
    trace_link = result.data["trace_link"]
    assert trace_link["link_type"] == "verifies"
    assert trace_link["test_case_id"] == tc["id"]
    assert trace_link["requirement_id"] == str(requirement.id)


def test_mark_reviewed_is_idempotent_and_audited(caller):
    """#424: the only write path for `reviewed`; a second call changes nothing."""
    _tenant, _workspace, ctx = caller
    tc = _create(caller, "Review TC")
    group = McpTestToolGroup()

    first = _exec(
        group,
        "test.mark_reviewed",
        {"test_case_id": tc["id"], "change_reason": "checked"},
        ctx,
    )
    assert first.success is True
    assert first.data["reviewed"] is True

    second = _exec(group, "test.mark_reviewed", {"test_case_id": tc["id"]}, ctx)
    assert second.success is True
    assert second.data["version"] == first.data["version"]


def test_outdate_hides_case_unless_include_outdated_then_reactivate(caller):
    """The soft-delete escape hatch and its inverse, via the workflow engine."""
    _tenant, workspace, ctx = caller
    tc = _create(caller, "Lifecycle TC")
    group = McpTestToolGroup()

    outdated = _exec(group, "test.outdate", {"id": tc["id"], "reason": "obsolete"}, ctx)
    assert outdated.success is True
    assert outdated.data["status"] == "outdated"

    hidden = _exec(group, "test.query", {"workspace_id": str(workspace.id)}, ctx)
    assert hidden.data["count"] == 0
    visible = _exec(
        group,
        "test.query",
        {"workspace_id": str(workspace.id), "include_outdated": True},
        ctx,
    )
    assert visible.data["count"] == 1

    restored = _exec(group, "test.reactivate", {"id": tc["id"]}, ctx)
    assert restored.success is True
    assert restored.data["id"] == tc["id"]

    back = _exec(group, "test.query", {"workspace_id": str(workspace.id)}, ctx)
    assert back.data["count"] == 1


# ---------------------------------------------------------------------------
# Real-DB round trip: the TestRun lifecycle
# ---------------------------------------------------------------------------


def test_run_lifecycle_end_to_end_through_dispatch(caller):
    """run_create -> report_results -> get/list -> complete."""
    _tenant, workspace, ctx = caller
    tc = _create(caller, "Run TC")
    group = McpTestToolGroup()

    created = _exec(
        group,
        "test.run_create",
        {
            "workspace_id": str(workspace.id),
            "name": "Nightly",
            "ci_job_id": "job-42",
            "test_case_ids": [tc["id"]],
        },
        ctx,
    )
    assert created.success is True, created.message
    run = created.data["test_run"]
    assert run["name"] == "Nightly"
    assert run["status"]

    reported = _exec(
        group,
        "test.run_report_results",
        {
            "run_id": run["id"],
            "results": [
                {"test_case_id": tc["id"], "status": "passed", "duration_ms": 12}
            ],
        },
        ctx,
    )
    assert reported.success is True
    assert reported.data["recorded"] == 1
    assert reported.data["results"][0]["status"] == "passed"

    fetched = _exec(group, "test.run_get", {"run_id": run["id"]}, ctx)
    assert fetched.success is True
    assert fetched.data["result_count"] == 1
    assert fetched.data["test_run"]["result_summary"]["passed"] == 1

    listed = _exec(group, "test.run_list", {"workspace_id": str(workspace.id)}, ctx)
    assert listed.success is True
    assert listed.data["count"] == 1

    completed = _exec(group, "test.run_complete", {"run_id": run["id"]}, ctx)
    assert completed.success is True
    assert completed.data["test_run"]["finished_at"] is not None


def test_run_list_filters_by_status_with_string_limit(caller):
    """The status filter matches the value test.run_create just returned."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()

    created = _exec(
        group,
        "test.run_create",
        {"workspace_id": str(workspace.id), "name": "Filter Run"},
        ctx,
    )
    assert created.success is True, created.message
    status = created.data["test_run"]["status"]

    filtered = _exec(
        group,
        "test.run_list",
        {"workspace_id": str(workspace.id), "status": status, "limit": "1"},
        ctx,
    )

    assert filtered.success is True
    assert filtered.data["count"] == 1


# ---------------------------------------------------------------------------
# Parameter validation (every required UUID / array / boolean param)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", sorted(_ID_PARAM_BY_TOOL))
def test_missing_required_uuid_param_is_validation_error(caller, tool_name):
    """A missing id parameter is VALIDATION_ERROR naming the parameter."""
    group = McpTestToolGroup()
    result = _exec(group, tool_name, {}, caller[2])

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "is required" in result.message or "is missing" in result.message


@pytest.mark.parametrize("tool_name", sorted(_ID_PARAM_BY_TOOL))
def test_non_uuid_param_is_validation_error_naming_the_value(caller, tool_name):
    """An unparseable UUID value is VALIDATION_ERROR naming the value."""
    group = McpTestToolGroup()
    result = _exec(
        group, tool_name, {_ID_PARAM_BY_TOOL[tool_name]: "not-a-uuid"}, caller[2]
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "not-a-uuid" in result.message


def test_query_without_workspace_id_is_validation_error(caller):
    """test.query does not silently list across workspaces."""
    group = McpTestToolGroup()
    result = _exec(group, "test.query", {}, caller[2])

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "workspace_id" in result.message


def test_create_without_title_is_validation_error(caller):
    """title is the one required string on test.create."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(group, "test.create", {"workspace_id": str(workspace.id)}, ctx)

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_create_rejects_unknown_origin(caller):
    """#424: `origin` is a closed vocabulary; `unknown` is system-only."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.create",
        {
            "workspace_id": str(workspace.id),
            "title": "Bad origin",
            "origin": "unknown",
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_create_rejects_invalid_scenario_kind(caller):
    """#402: scenario_kind is nominal | off_nominal."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.create",
        {
            "workspace_id": str(workspace.id),
            "title": "Bad kind",
            "scenario_kind": "alien",
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_run_create_rejects_unknown_param(caller):
    """#459: a typo'd parameter (test_case_id) is refused, not dropped."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.run_create",
        {
            "workspace_id": str(workspace.id),
            "name": "Run",
            "test_case_id": str(uuid4()),
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "test_case_id" in result.message


def test_run_create_rejects_non_uuid_test_case_ids(caller):
    """A string inside test_case_ids is VALIDATION_ERROR, not a 500."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.run_create",
        {
            "workspace_id": str(workspace.id),
            "name": "Run",
            "test_case_ids": ["not-a-uuid"],
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_run_list_limit_bounds_are_validation_errors(caller):
    """_parse_run_list_limit: a bool or an out-of-range page size fails."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    params = {"workspace_id": str(workspace.id)}

    for bad_limit in (0, 501, "abc", True):
        result = _exec(
            group, "test.run_list", {**params, "limit": bad_limit}, ctx
        )
        assert result.success is False, bad_limit
        assert result.error_code == "VALIDATION_ERROR", bad_limit


def test_run_list_rejects_unknown_status(caller):
    """status must be a model TestRun.status choice value."""
    _tenant, workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.run_list",
        {"workspace_id": str(workspace.id), "status": "galaxy"},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_run_report_results_requires_non_empty_results(caller):
    """REQ-L2-MC-013: an empty results array is a validation failure."""
    _tenant, _workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.run_report_results",
        {"run_id": str(uuid4()), "results": []},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_run_report_results_rejects_invalid_result_status(caller):
    """Result statuses are the lowercase execution vocabulary."""
    _tenant, _workspace, ctx = caller
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.run_report_results",
        {
            "run_id": str(uuid4()),
            "results": [{"test_case_id": str(uuid4()), "status": "Passed"}],
        },
        ctx,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_mark_reviewed_rejects_non_boolean(caller):
    """`reviewed` is a strict boolean; nothing else reaches the service."""
    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.mark_reviewed",
        {"test_case_id": str(uuid4()), "reviewed": "yes"},
        caller[2],
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# derive_from_requirement (draft/accept + mode/policy)
# ---------------------------------------------------------------------------


def test_derive_preview_returns_draft_only(caller):
    """mode defaults to preview: the service draft is forwarded verbatim."""
    group, _service = _group_with_service()
    group = McpTestToolGroup(service=_service, ai_derivation_service=_ai_service())

    result = _exec(
        group,
        "test.derive_from_requirement",
        {"requirement_id": str(uuid4())},
        caller[2],
    )

    assert result.success is True
    assert result.data["draft"]["title"] == "Draft TC"
    assert result.data["is_mock_fallback"] is True


def test_derive_write_mode_persists_and_links(caller):
    """mode=write persists the draft via the AI service write path."""
    ai = _ai_service()
    group, _service = _group_with_service()
    group = McpTestToolGroup(service=_service, ai_derivation_service=ai)

    result = _exec(
        group,
        "test.derive_from_requirement",
        {"requirement_id": str(uuid4()), "mode": "write"},
        caller[2],
    )

    assert result.success is True, result.message
    assert result.data["written"]["title"] == "Draft TC"
    assert result.data["is_mock_fallback"] is True
    assert ai._write_derived_entity.call_count == 1


def test_derive_unknown_requirement_is_not_found(caller):
    """The handler maps the service NotFoundError before the LLM round-trip."""
    ai = _ai_service()
    ai.derive_testcase_from_requirement.side_effect = NotFoundError("gone")
    group, _service = _group_with_service()
    group = McpTestToolGroup(service=_service, ai_derivation_service=ai)

    result = _exec(
        group,
        "test.derive_from_requirement",
        {"requirement_id": str(uuid4())},
        caller[2],
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Cross-tenant read fence (RLS)
# ---------------------------------------------------------------------------


def _foreign_test_case(tenant_a_id):
    """A TestCase owned by a second tenant; the caller's fence is re-armed."""
    suffix = uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"MCP test dispatch B {suffix}", slug=f"mcp-test-b-{suffix}"
    )
    user = User.objects.create(
        username=f"mcptest-b-{suffix}-user",
        email=f"mcptest-b-{suffix}@t.test",
        tenant=tenant,
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(
            tenant=tenant, name=f"ws-b-{suffix}"
        )
        tc = TestService().create_test_case(
            workspace_id=workspace.id, title="Tenant B TC", ctx=ctx
        )
    finally:
        set_request_tenant(tenant_a_id)
    return ctx, tc


def test_get_foreign_tenant_test_case_is_not_found(caller):
    """Another tenant's test case id must be NOT_FOUND, never its payload."""
    tenant, _workspace, ctx = caller
    _ctx_b, foreign_tc = _foreign_test_case(tenant.id)

    group = McpTestToolGroup()
    result = _exec(group, "test.get", {"id": str(foreign_tc.id)}, ctx)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_link_with_foreign_tenant_test_case_is_not_found(caller):
    """The write tools answer NOT_FOUND on a foreign id before any mutation."""
    tenant, _workspace, ctx = caller
    _ctx_b, foreign_tc = _foreign_test_case(tenant.id)
    requirement = _make_requirement(caller)

    group = McpTestToolGroup()
    result = _exec(
        group,
        "test.link",
        {"test_id": str(foreign_tc.id), "req_id": str(requirement.id)},
        ctx,
    )

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# RBAC fence (real viewer context)
# ---------------------------------------------------------------------------


def test_viewer_execution_status_update_is_permission_denied(caller):
    """Real DB RBAC: a viewer's status update never reaches persistence."""
    tc = _create(caller, "Viewer TC")
    group = McpTestToolGroup()

    result = _exec(
        group,
        "test.update",
        {"id": tc["id"], "data": {"status": "Passed"}},
        _viewer_ctx_of(caller),
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_viewer_mark_reviewed_is_permission_denied(caller):
    """The viewer fence holds on the provenance write path too."""
    tc = _create(caller, "Viewer review TC")
    group = McpTestToolGroup()

    result = _exec(
        group,
        "test.mark_reviewed",
        {"test_case_id": tc["id"], "reviewed": True},
        _viewer_ctx_of(caller),
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.parametrize(
    "tool_name",
    [
        "test.get",
        "test.link",
        "test.run_get",
        "test.run_create",
        "test.run_report_results",
        "test.mark_reviewed",
    ],
)
def test_service_permission_denied_maps_to_permission_denied(caller, tool_name):
    """Every PermissionDeniedError-raising handler funnels to the same code."""
    group, service = _group_with_service()
    _group2, run_service = _group_with_run_service()
    for method in (
        "create_test_case",
        "update_test_status",
        "update_test_case",
        "get_test_case",
        "list_test_cases",
        "mark_reviewed",
    ):
        getattr(service, method).side_effect = PermissionDeniedError("denied")
    for method in (
        "create_test_run",
        "get_test_run",
        "list_test_runs",
        "add_results_bulk",
        "close_test_run",
    ):
        getattr(run_service, method).side_effect = PermissionDeniedError("denied")
    group = McpTestToolGroup(service=service, run_service=run_service)

    result = _exec(group, tool_name, _params_for(tool_name), caller[2])

    assert result.success is False, tool_name
    assert result.error_code == "PERMISSION_DENIED", tool_name


# ---------------------------------------------------------------------------
# Service-error -> MCP-code mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name",
    [
        "test.get",
        "test.update",
        "test.link",
        "test.outdate",
        "test.reactivate",
        "test.run_get",
        "test.run_complete",
        "test.run_report_results",
        "test.mark_reviewed",
    ],
)
def test_service_not_found_maps_to_not_found(caller, tool_name):
    """NotFoundError is NOT_FOUND for every handler that can raise it."""
    group, service = _group_with_service()
    _group2, run_service = _group_with_run_service()
    for method in (
        "get_test_case",
        "update_test_status",
        "update_test_case",
        "mark_reviewed",
    ):
        getattr(service, method).side_effect = NotFoundError("gone")
    for method in (
        "get_test_run",
        "add_results_bulk",
        "close_test_run",
    ):
        getattr(run_service, method).side_effect = NotFoundError("gone")
    group = McpTestToolGroup(service=service, run_service=run_service)

    result = _exec(group, tool_name, _params_for(tool_name), caller[2])

    assert result.success is False, tool_name
    assert result.error_code == "NOT_FOUND", tool_name


@pytest.mark.parametrize(
    "tool_name",
    [
        "test.create",
        "test.run_create",
        "test.run_report_results",
    ],
)
def test_service_validation_error_maps_to_validation_error(caller, tool_name):
    """ValidationError is forwarded as VALIDATION_ERROR, never a 500."""
    group, service = _group_with_service()
    _group2, run_service = _group_with_run_service()
    service.create_test_case.side_effect = ValidationError("bad field")
    run_service.create_test_run.side_effect = ValidationError("bad field")
    run_service.add_results_bulk.side_effect = ValidationError("bad field")
    group = McpTestToolGroup(service=service, run_service=run_service)

    result = _exec(group, tool_name, _params_for(tool_name), caller[2])

    assert result.success is False, tool_name
    assert result.error_code == "VALIDATION_ERROR", tool_name
    assert result.message == "bad field", tool_name


def test_unmapped_service_error_is_masked_internal_error(caller):
    """CWE-209 / fix #108: an unmapped exception never leaks its message."""
    group, service = _group_with_service()
    service.update_test_status.side_effect = RuntimeError(
        "SQL fragment leakage: SELECT * FROM secret_table"
    )

    result = _exec(group, "test.update", _params_for("test.update"), caller[2])

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == "An internal error occurred."
    assert "secret_table" not in result.message
