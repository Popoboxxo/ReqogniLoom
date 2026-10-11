"""
Dispatch-level tests for RequirementsToolGroup (COMP-MC-003, REQ-L2-MC-001).

``test_tool_groups.py`` already drives the group's handlers against mocked
services (call forwarding, audit calls, the ADR-005 ``level`` contract). This
module closes the gaps that a mocked service cannot see — it drives the same
PUBLIC interface ``BaseToolGroup.execute_tool`` but from the boundaries a real
call arrives through:

* a full real-DB round trip (create -> get -> query -> update -> outdate),
* the RBAC fence of the application service (viewer write -> PERMISSION_DENIED),
* the cross-tenant read fence (another tenant's requirement id -> NOT_FOUND),
* parameter validation for every tool's required id / title / task_id,
* the LLM-availability gate that precedes validation on the AI tools,
* service-error -> MCP-code mapping (NOT_FOUND / VALIDATION_ERROR /
  PERMISSION_DENIED / INVALID_STATE / LLM_NOT_CONFIGURED / INTERNAL_ERROR),
* the CWE-209 masking contract (unmapped exceptions never leak their message).

leaf_id : COMP-MC-003
req_id  : REQ-L2-MC-001
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from application.base import (
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext, AuthMethod
from link_types.workspace_store import provision_workspace_link_types
from mcp_server.tools.requirements import RequirementsToolGroup
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

_API_KEY = "reqlo_testkey_req_dispatch"

# tool name -> the schema-required UUID parameter the handler validates first
_ID_PARAM_BY_TOOL = {
    "requirement.get": "id",
    "requirement.update": "id",
    "requirement.outdate": "id",
    "requirement.reactivate": "id",
    "requirement.derive": "parent_requirement_id",
}


@pytest.fixture
def caller():
    """Tenant + workspace + AuthContext, tenant scope armed for the whole test.

    Mirrors ``test_ai_derivation_tool_group_dispatch.py``'s ``caller``: both
    isolation layers (thread-local + PostgreSQL session variable) are armed so
    the RLS fence of the test database applies while the tool runs.
    """
    tenant = Tenant.objects.create(name="MCP req dispatch", slug="mcp-req-dispatch")
    user = User.objects.create(
        username="mcp-req-dispatch-user",
        email="mcp-req-dispatch@t.test",
        tenant=tenant,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(
            tenant=tenant, name="ws-dispatch"
        )
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
        # The outdate/reactivate tools route through the workflow engine, which
        # needs a definition for (workspace, item_type) to exist.
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


def _foreign_caller(tenant_a_id):
    """A second tenant's workspace + ctx; the caller's fence is re-armed."""
    tenant = Tenant.objects.create(name="mcp-req-dispatch-b", slug="mcp-req-dispatch-b")
    user = User.objects.create(
        username="mcp-req-dispatch-b-user",
        email="mcp-req-dispatch-b@t.test",
        tenant=tenant,
    )
    set_request_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(
            tenant=tenant, name="ws-dispatch-b"
        )
        provision_workspace_link_types(workspace_id=workspace.id, tenant_id=tenant.id)
    finally:
        set_request_tenant(tenant_a_id)
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )
    return tenant, workspace, ctx


def _exec(group, tool, params, ctx):
    """Run *tool* through the public tool-group dispatch interface."""
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=_API_KEY
    )


def _create(caller, title="Dispatch Req", **extra):
    """requirement.create through the public interface; returns the payload."""
    _tenant, workspace, ctx = caller
    group = RequirementsToolGroup()
    result = _exec(
        group,
        "requirement.create",
        {"workspace_id": str(workspace.id), "title": title, **extra},
        ctx,
    )
    assert result.success is True, result.message
    return result.data["requirement"]


def _group_with_service(**methods):
    """A group whose RequirementService is a MagicMock with configured methods."""
    service = MagicMock()
    for name, value in methods.items():
        getattr(service, name).return_value = value
    return RequirementsToolGroup(service=service), service


def _viewer_ctx() -> AuthContext:
    """A viewer context (write is fail-closed denied by the RBAC matrix)."""
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("viewer",),
        auth_method=AuthMethod.API_KEY,
        api_key_id=None,
    )


def _viewer_ctx_of(caller) -> AuthContext:
    """A viewer context inside the SAME tenant as *caller*."""
    return AuthContext(
        user_id=uuid4(),
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
    req_id = str(uuid4())
    params = {
        "requirement.get": {"id": req_id},
        "requirement.query": {"workspace_id": req_id},
        "requirement.update": {"id": req_id, "data": {}},
        "requirement.outdate": {"id": req_id},
        "requirement.reactivate": {"id": req_id},
        "requirement.derive": {
            "parent_requirement_id": req_id,
            "architecture_element_id": str(uuid4()),
            "title": "Derived",
        },
        "requirement.decompose": {"requirement_id": req_id},
        "requirement.validate": {"requirement_id": req_id},
        "requirement.check_consistency": {"workspace_id": req_id},
        "requirement.check_consistency_status": {"task_id": "task-unknown"},
        "requirement.create": {"workspace_id": req_id, "title": "T"},
    }
    return params[tool_name]


# ---------------------------------------------------------------------------
# Real-DB round trip: create -> get -> query -> update
# ---------------------------------------------------------------------------


def test_create_then_get_round_trip_through_dispatch(caller):
    """The SE mask fields (#409) survive create and are read back by get."""
    created = _create(
        caller,
        title="Round Trip",
        description="desc",
        acceptance_criteria="acriteria",
        rationale="because",
        source="stakeholder",
        type="SyReq",
        complexity_fibonacci=5,
        verification_method="Test",
    )

    group = RequirementsToolGroup()
    fetched = _exec(group, "requirement.get", {"id": created["id"]}, caller[2])

    assert fetched.success is True
    req = fetched.data["requirement"]
    assert req["id"] == created["id"]
    assert req["artifact_id"] == created["artifact_id"]
    assert req["title"] == "Round Trip"
    assert req["acceptance_criteria"] == "acriteria"
    assert req["rationale"] == "because"
    assert req["source"] == "stakeholder"
    assert req["complexity_fibonacci"] == 5
    assert req["verification_method"] == "Test"
    assert req["status"]  # engine-resolved, never empty
    assert req["version"] == 1


def test_query_lists_created_requirements_with_count(caller):
    """requirement.query returns the workspace's requirements plus a count."""
    _create(caller, "Q One")
    _create(caller, "Q Two")

    result = _exec(
        RequirementsToolGroup(),
        "requirement.query",
        {"workspace_id": str(caller[1].id)},
        caller[2],
    )

    assert result.success is True
    assert result.data["count"] == 2
    assert {r["title"] for r in result.data["requirements"]} == {"Q One", "Q Two"}


def test_query_without_workspace_id_is_validation_error(caller):
    """The stable message names the missing parameter."""
    result = _exec(RequirementsToolGroup(), "requirement.query", {}, caller[2])

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert result.message == (
        "Parameter 'workspace_id' is required for requirement.query."
    )


def test_query_forwards_include_outdated_to_the_service(caller, monkeypatch):
    """``include_outdated`` is forwarded as ``include_deleted``."""
    _service = RequirementService()
    group = RequirementsToolGroup(service=_service)
    seen: dict = {}
    original = _service.list_requirements

    def _spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(_service, "list_requirements", _spy)
    result = _exec(
        group,
        "requirement.query",
        {"workspace_id": str(caller[1].id), "include_outdated": True},
        caller[2],
    )

    assert result.success is True
    assert seen["include_deleted"] is True


def test_update_changes_title_and_version_on_real_db(caller):
    """The nested ``data`` contract reaches update_requirement; version bumps."""
    created = _create(caller, "Before")

    updated = _exec(
        RequirementsToolGroup(),
        "requirement.update",
        {"id": created["id"], "data": {"title": "After"}},
        caller[2],
    )

    assert updated.success is True, updated.message
    assert updated.data["requirement"]["title"] == "After"
    assert updated.data["requirement"]["version"] == created["version"] + 1


def test_outdate_hides_requirement_from_query_unless_include_outdated(caller):
    """Soft-delete fence: the write tool hides the row from the default list."""
    created = _create(caller, "To Outdate")

    outdated = _exec(
        RequirementsToolGroup(),
        "requirement.outdate",
        {"id": created["id"], "reason": "no longer needed"},
        caller[2],
    )
    assert outdated.success is True, outdated.message
    assert outdated.data["status"] == "outdated"

    default = _exec(
        RequirementsToolGroup(),
        "requirement.query",
        {"workspace_id": str(caller[1].id)},
        caller[2],
    )
    assert default.data["count"] == 0

    included = _exec(
        RequirementsToolGroup(),
        "requirement.query",
        {"workspace_id": str(caller[1].id), "include_outdated": True},
        caller[2],
    )
    assert included.data["count"] == 1


def test_reactivate_restores_an_outdated_requirement(caller):
    """The reactivate path answers the new engine state of the item."""
    created = _create(caller, "To Reactivate")
    _exec(
        RequirementsToolGroup(),
        "requirement.outdate",
        {"id": created["id"]},
        caller[2],
    )

    result = _exec(
        RequirementsToolGroup(), "requirement.reactivate", {"id": created["id"]}, caller[2]
    )

    assert result.success is True, result.message
    assert result.data["id"] == created["id"]
    assert result.data["status"]


# ---------------------------------------------------------------------------
# Cross-tenant fence
# ---------------------------------------------------------------------------


def test_get_foreign_tenant_requirement_is_not_found(caller):
    """Another tenant's requirement id must be NOT_FOUND, never its payload."""
    tenant_a, _workspace_a, ctx_a = caller
    _tenant_b, _workspace_b, ctx_b = _foreign_caller(tenant_a.id)
    foreign = _create((_tenant_b, _workspace_b, ctx_b), "Tenant B Req")

    result = _exec(RequirementsToolGroup(), "requirement.get", {"id": foreign["id"]}, ctx_a)

    assert result.success is False
    assert result.error_code == "NOT_FOUND"


def test_update_and_outdate_of_foreign_requirement_are_not_found(caller):
    """The write tools answer NOT_FOUND on a foreign id before any mutation."""
    tenant_a, _workspace_a, ctx_a = caller
    _tenant_b, _workspace_b, ctx_b = _foreign_caller(tenant_a.id)
    foreign = _create((_tenant_b, _workspace_b, ctx_b), "Tenant B Req")

    update = _exec(
        RequirementsToolGroup(),
        "requirement.update",
        {"id": foreign["id"], "data": {"title": "hijacked"}},
        ctx_a,
    )
    outdate = _exec(
        RequirementsToolGroup(), "requirement.outdate", {"id": foreign["id"]}, ctx_a
    )

    assert update.success is False
    assert update.error_code == "NOT_FOUND"
    assert outdate.success is False
    assert outdate.error_code == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Parameter validation (dispatch level, no service call)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", sorted(_ID_PARAM_BY_TOOL))
def test_missing_required_uuid_param_is_validation_error(caller, tool_name):
    """Every required id is enforced before any service call."""
    result = _exec(RequirementsToolGroup(), tool_name, {}, caller[2])

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert _ID_PARAM_BY_TOOL[tool_name] in result.message


@pytest.mark.parametrize("tool_name", sorted(_ID_PARAM_BY_TOOL))
def test_non_uuid_param_is_validation_error_naming_the_value(caller, tool_name):
    """An unparseable id is rejected with the offending value in the message."""
    param = _ID_PARAM_BY_TOOL[tool_name]
    result = _exec(RequirementsToolGroup(), tool_name, {param: "not-a-uuid"}, caller[2])

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "not-a-uuid" in result.message


def test_create_without_title_is_validation_error(caller):
    """``title`` is required (``require_param``) before the service is called."""
    service = MagicMock()
    group = RequirementsToolGroup(service=service)

    result = _exec(
        group, "requirement.create", {"workspace_id": str(caller[1].id)}, caller[2]
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "title" in result.message
    service.create_requirement.assert_not_called()


def test_derive_requires_title_param(caller):
    """The third required param of requirement.derive is the title."""
    parent = _create(caller, "Derive parent")
    result = _exec(
        RequirementsToolGroup(),
        "requirement.derive",
        {
            "parent_requirement_id": parent["id"],
            "architecture_element_id": str(uuid4()),
        },
        caller[2],
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "title" in result.message


@pytest.mark.parametrize("task_id", [None, "", 42])
def test_check_consistency_status_rejects_non_string_task_id(task_id):
    """GH-796: the status poller fails with INVALID_PARAMS, not VALIDATION."""
    group = RequirementsToolGroup()

    result = group.execute_tool(
        tool_name="requirement.check_consistency_status",
        params={"task_id": task_id} if task_id is not None else {},
        auth_context=_viewer_ctx(),
        api_key=_API_KEY,
    )

    assert result.success is False
    assert result.error_code == "INVALID_PARAMS"
    assert "task_id" in result.message


# ---------------------------------------------------------------------------
# LLM gate ordering
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the env-based LLM availability check answer False."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.mark.parametrize(
    "tool_name", ["requirement.decompose", "requirement.validate"]
)
def test_ai_tools_without_llm_return_llm_not_configured(caller, llm_unavailable, tool_name):
    """ADR-L3-MC003-02: the early LLM check precedes every other path."""
    result = _exec(
        RequirementsToolGroup(), tool_name, {"requirement_id": str(uuid4())}, caller[2]
    )

    assert result.success is False
    assert result.error_code == "LLM_NOT_CONFIGURED"
    assert tool_name in result.message


def test_check_consistency_without_llm_returns_llm_not_configured(
    caller, llm_unavailable
):
    """The workspace-scoped AI tool carries the same early gate."""
    result = _exec(
        RequirementsToolGroup(),
        "requirement.check_consistency",
        {"workspace_id": str(caller[1].id)},
        caller[2],
    )

    assert result.success is False
    assert result.error_code == "LLM_NOT_CONFIGURED"
    assert "requirement.check_consistency" in result.message


@pytest.mark.parametrize(
    "tool_name,param_name",
    [
        ("requirement.decompose", "requirement_id"),
        ("requirement.validate", "requirement_id"),
        ("requirement.check_consistency", "workspace_id"),
    ],
)
def test_ai_tools_validate_their_id_after_the_llm_gate(
    caller, monkeypatch, tool_name, param_name
):
    """Once the LLM gate passes, the missing id is a VALIDATION_ERROR."""
    monkeypatch.setattr(
        "mcp_server.tools.requirements._check_llm_configured", lambda: True
    )
    service = MagicMock()

    result = _exec(RequirementsToolGroup(service=service), tool_name, {}, caller[2])

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert param_name in result.message
    service.decompose.assert_not_called()
    service.validate_requirement.assert_not_called()
    service.check_consistency.assert_not_called()


# ---------------------------------------------------------------------------
# RBAC fence (application-service layer)
# ---------------------------------------------------------------------------


def test_viewer_write_is_permission_denied(caller):
    """Real DB RBAC: a viewer's create never reaches persistence."""
    group = RequirementsToolGroup()

    result = _exec(
        group,
        "requirement.create",
        {"workspace_id": str(caller[1].id), "title": "Viewer write"},
        _viewer_ctx_of(caller),
    )

    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


@pytest.mark.parametrize(
    "tool_name,params",
    [
        ("requirement.get", {}),
        ("requirement.query", {}),
        ("requirement.update", {}),
        ("requirement.derive", {}),
        ("requirement.decompose", {}),
        ("requirement.validate", {}),
        ("requirement.check_consistency", {}),
    ],
)
def test_service_permission_denied_maps_to_permission_denied(tool_name, params):
    """Every PermissionDeniedError-raising handler funnels to the same code."""
    group, service = _group_with_service()
    service.get_requirement.side_effect = PermissionDeniedError("denied")
    service.list_requirements.side_effect = PermissionDeniedError("denied")
    service.derive_requirement.side_effect = PermissionDeniedError("denied")
    service.decompose.side_effect = PermissionDeniedError("denied")
    service.validate_requirement.side_effect = PermissionDeniedError("denied")
    service.check_consistency.side_effect = PermissionDeniedError("denied")

    result = _exec(group, tool_name, _params_for(tool_name), _viewer_ctx())

    assert result.success is False, tool_name
    assert result.error_code == "PERMISSION_DENIED", tool_name


# ---------------------------------------------------------------------------
# Service-error -> MCP code mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,params",
    [
        ("requirement.get", {}),
        ("requirement.update", {}),
        ("requirement.outdate", {}),
        ("requirement.reactivate", {}),
        ("requirement.derive", {}),
        ("requirement.decompose", {}),
        ("requirement.validate", {}),
        ("requirement.check_consistency", {}),
        ("requirement.check_consistency_status", {}),
    ],
)
def test_service_not_found_maps_to_not_found(tool_name, params):
    """NotFoundError is NOT_FOUND for every handler that can raise it."""
    group, service = _group_with_service()
    service.get_requirement.side_effect = NotFoundError("gone")
    service.derive_requirement.side_effect = NotFoundError("gone")
    service.decompose.side_effect = NotFoundError("gone")
    service.validate_requirement.side_effect = NotFoundError("gone")
    service.check_consistency.side_effect = NotFoundError("gone")
    service.get_consistency_status.side_effect = NotFoundError("gone")

    result = _exec(group, tool_name, _params_for(tool_name), _viewer_ctx())

    assert result.success is False, tool_name
    assert result.error_code == "NOT_FOUND", tool_name


@pytest.mark.parametrize(
    "tool_name,params",
    [
        ("requirement.create", {}),
        ("requirement.update", {}),
        ("requirement.derive", {}),
    ],
)
def test_service_validation_error_maps_to_validation_error(tool_name, params):
    """ValidationError is forwarded as VALIDATION_ERROR, never a 500."""
    group, service = _group_with_service()
    service.create_requirement.side_effect = ValidationError("bad field")
    service.update_requirement.side_effect = ValidationError("bad field")
    service.derive_requirement.side_effect = ValidationError("bad field")
    service.get_requirement.return_value = _stub_requirement(uuid4())

    result = _exec(group, tool_name, _params_for(tool_name), _viewer_ctx())

    assert result.success is False, tool_name
    assert result.error_code == "VALIDATION_ERROR", tool_name
    assert result.message == "bad field", tool_name


def _stub_requirement(req_id):
    """A minimal requirement stand-in for the mocked-service handlers."""
    req = MagicMock()
    req.id = req_id
    req.artifact_id = uuid4()
    req.workspace_id = uuid4()
    req.title = "T"
    req.description = ""
    req.category = ""
    req.status = "draft"
    req.version = 1
    req.level = 1
    req.artifact = MagicMock()
    req.artifact.workspace_id = uuid4()
    return req


def test_reactivate_invalid_state_maps_to_invalid_state():
    """A wrong-state reactivation is INVALID_STATE, not INTERNAL_ERROR.

    ``get_requirement`` is called outside the ``ValueError`` guard, so the
    wrong-state answer must come from the reactivate transition itself.
    """
    group, service = _group_with_service()
    service.get_requirement.return_value = _stub_requirement(uuid4())

    with patch(
        "workflow.services.reactivate", side_effect=ValueError("not outdated")
    ):
        result = _exec(
            group, "requirement.reactivate", {"id": str(uuid4())}, _viewer_ctx()
        )

    assert result.success is False
    assert result.error_code == "INVALID_STATE"
    assert result.message == "not outdated"


@pytest.mark.parametrize(
    "tool_name,params",
    [
        ("requirement.get", {"id": str(uuid4())}),
        ("requirement.query", {"workspace_id": str(uuid4())}),
        ("requirement.create", {"workspace_id": str(uuid4()), "title": "T"}),
    ],
)
def test_unmapped_exception_is_masked_as_internal_error(tool_name, params):
    """#697 / CWE-209: the raw exception text never reaches the agent."""
    group, service = _group_with_service()
    leak = "SELECT * FROM persistence_requirement WHERE id='x'"
    service.get_requirement.side_effect = RuntimeError(leak)
    service.list_requirements.side_effect = RuntimeError(leak)
    service.create_requirement.side_effect = RuntimeError(leak)

    result = _exec(group, tool_name, params, _viewer_ctx())

    assert result.success is False, tool_name
    assert result.error_code == "INTERNAL_ERROR", tool_name
    assert result.message == "An internal error occurred."
    assert leak not in result.message


def test_outdate_engine_failure_is_masked_as_internal_error():
    """The outdate handler's own catch-all masks the unmapped cause."""
    group, service = _group_with_service()
    service.get_requirement.return_value = _stub_requirement(uuid4())

    with patch("workflow.services.outdate", side_effect=RuntimeError("engine down: psql")):
        result = _exec(group, "requirement.outdate", {"id": str(uuid4())}, _viewer_ctx())

    assert result.success is False
    assert result.error_code == "INTERNAL_ERROR"
    assert result.message == "An internal error occurred."


# ---------------------------------------------------------------------------
# Group dispatch contract
# ---------------------------------------------------------------------------


def test_unknown_tool_name_returns_unknown_tool(caller):
    """A tool name this group does not own is UNKNOWN_TOOL, not INTERNAL."""
    result = _exec(RequirementsToolGroup(), "requirement.not_a_tool", {}, caller[2])

    assert result.success is False
    assert result.error_code == "UNKNOWN_TOOL"
