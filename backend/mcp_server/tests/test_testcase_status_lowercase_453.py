"""GH-453 — MCP exposes the TestCase lifecycle status, in lowercase.

The issue is about automated evaluations ("list every draft item") coming back
empty. For MCP clients there were two causes, not one:

  1. the value was Title Case while every other entity used lowercase, and
  2. ``_test_case_to_dict`` did not return ``status`` at all, so a test case's
     lifecycle state was invisible to ``test.get`` / ``test.query``.

These tests pin both, plus the disambiguation between the lifecycle status and
the unrelated *execution* status (Passed/Failed/Not Run) that ``test.update``
writes under the same key name.
"""
from __future__ import annotations

import pytest

from application.test_service import TestService
from auth_tenancy.context import AuthContext
from mcp_server.tools.tests import TestToolGroup
from persistence.models import Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow, transition

pytestmark = pytest.mark.django_db

API_KEY = "reqlo_gh453"


def _setup(name: str):
    """Tenant + workspace + TestCase workflow + AuthContext."""
    tenant = Tenant.objects.create(name=name, slug=name)
    user = User.objects.create(
        username=f"{name}-user", email=f"{name}@example.com", tenant=tenant
    )
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name=f"{name}-ws")
        create_default_workflow(
            workspace_id=workspace.id,
            preset="testcase_default",
            item_type="TestCase",
            tenant_id=tenant.id,
        )
    finally:
        TenantContext.clear_tenant()

    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor", "approver", "admin"),
        auth_method="test",
        api_key_id=None,
        tenant_name=name,
    )
    return tenant, workspace, ctx


def test_query_exposes_a_lowercase_status(monkeypatch) -> None:
    tenant, workspace, ctx = _setup("gh453-mcp-query")
    service = TestService()
    service.create_test_case(workspace_id=workspace.id, title="TC-1", ctx=ctx)

    group = TestToolGroup(service=service)
    result = group._handle_query(
        params={"workspace_id": str(workspace.id)}, auth_context=ctx, api_key=API_KEY
    )

    assert result.success is True
    rows = result.data["test_cases"]
    assert len(rows) == 1
    assert rows[0]["status"] == "draft"


def test_get_exposes_a_lowercase_status() -> None:
    tenant, workspace, ctx = _setup("gh453-mcp-get")
    service = TestService()
    test_case = service.create_test_case(
        workspace_id=workspace.id, title="TC-1", ctx=ctx
    )

    group = TestToolGroup(service=service)
    result = group._handle_get(
        params={"id": str(test_case.id)}, auth_context=ctx, api_key=API_KEY
    )

    assert result.success is True
    payload = result.data.get("test_case", result.data)
    assert payload["status"] == "draft"


def test_query_status_tracks_workflow_transitions() -> None:
    """The value an agent reads must follow the workflow, in the new spelling."""
    tenant, workspace, ctx = _setup("gh453-mcp-transition")
    service = TestService()
    test_case = service.create_test_case(
        workspace_id=workspace.id, title="TC-1", ctx=ctx
    )

    TenantContext.set_tenant(tenant.id)
    try:
        transition(
            item_id=test_case.id,
            target_state="ready",
            change_reason="",
            ctx=ctx,
            item_type="TestCase",
            workspace_id=workspace.id,
        )
    finally:
        TenantContext.clear_tenant()

    group = TestToolGroup(service=service)
    result = group._handle_query(
        params={"workspace_id": str(workspace.id)}, auth_context=ctx, api_key=API_KEY
    )
    assert result.data["test_cases"][0]["status"] == "ready"


def test_a_lifecycle_value_sent_to_update_gets_an_actionable_error() -> None:
    """Read-then-write round trip: `status` in test.update is the EXECUTION
    status, so a lifecycle value must be rejected with a pointer to the
    transition tools rather than a bare list of unrelated values."""
    tenant, workspace, ctx = _setup("gh453-mcp-update")
    service = TestService()
    test_case = service.create_test_case(
        workspace_id=workspace.id, title="TC-1", ctx=ctx
    )

    group = TestToolGroup(service=service)
    result = group._handle_update(
        params={"id": str(test_case.id), "data": {"status": "draft"}},
        auth_context=ctx,
        api_key=API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "lifecycle status" in result.message
    assert "transition" in result.message


def test_execution_status_still_works_unchanged() -> None:
    """Guard: the disambiguation must not break the legitimate write path."""
    tenant, workspace, ctx = _setup("gh453-mcp-exec")
    service = TestService()
    test_case = service.create_test_case(
        workspace_id=workspace.id, title="TC-1", ctx=ctx
    )

    group = TestToolGroup(service=service)
    result = group._handle_update(
        params={"id": str(test_case.id), "data": {"status": "Passed"}},
        auth_context=ctx,
        api_key=API_KEY,
    )

    assert result.success is True, result.message


def test_tool_descriptions_document_the_lowercase_lifecycle_values() -> None:
    schemas = {s["name"]: s for s in TestToolGroup._TOOL_SCHEMAS}

    for name in ("test.get", "test.query"):
        description = schemas[name]["description"]
        assert "draft|ready|approved|deprecated" in description, name

    update_description = schemas["test.update"]["description"]
    assert "EXECUTION" in update_description
    assert "Passed|Failed|Not Run" in update_description


# ---------------------------------------------------------------------------
# #1151 — `type` and `test_type` are two fields for one piece of information.
# They must carry the same enum and be validated through the same path: the
# same value is accepted (or rejected) identically regardless of which key
# carried it.
# ---------------------------------------------------------------------------

def test_create_schema_advertises_the_same_enum_for_type_and_test_type() -> None:
    """#1151: `type` used to have no enum while `test_type` did. Both must now
    publish the identical closed value set, or a client is told two different
    contracts for the same field."""
    schema = {s["name"]: s for s in TestToolGroup._TOOL_SCHEMAS}["test.create"]
    props = schema["inputSchema"]["properties"]

    from persistence.models import TestCaseType

    assert "enum" in props["type"], "`type` must advertise an enum (#1151)"
    assert props["type"]["enum"] == props["test_type"]["enum"]
    assert set(props["type"]["enum"]) == set(TestCaseType.values)


@pytest.mark.parametrize("param_name", ["type", "test_type"])
def test_create_accepts_canonical_lowercase_via_either_key(param_name) -> None:
    service = TestService()
    _, workspace, ctx = _setup("test1151-canonical")
    group = TestToolGroup(service=service)
    from persistence.models import TestCaseType

    canonical = TestCaseType.choices[0][0]

    result = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "TC",
            param_name: canonical,
        },
        auth_context=ctx,
        api_key=API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["test_case"]["test_type"] == canonical


@pytest.mark.parametrize("param_name", ["type", "test_type"])
def test_create_accepts_legacy_titlecase_alias_via_either_key(param_name) -> None:
    """The deprecated TitleCase spelling is folded onto the canonical value
    identically through both keys (#816 semantics preserved, #1151)."""
    service = TestService()
    _, workspace, ctx = _setup("test1151-legacy")
    group = TestToolGroup(service=service)

    result = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "TC",
            param_name: "Unit",
        },
        auth_context=ctx,
        api_key=API_KEY,
    )

    assert result.success is True, result.message
    assert result.data["test_case"]["test_type"] == "unit"


@pytest.mark.parametrize("param_name", ["type", "test_type"])
def test_create_rejects_an_invalid_value_identically_via_either_key(param_name) -> None:
    """An invalid value must be refused in BOTH forms with the same
    VALIDATION_ERROR — not accepted silently through one of the keys."""
    service = TestService()
    _, workspace, ctx = _setup("test1151-invalid")
    group = TestToolGroup(service=service)

    result = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "TC",
            param_name: "Acceptance",
        },
        auth_context=ctx,
        api_key=API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "Invalid test_type" in result.message


def test_create_rejects_conflicting_type_and_test_type() -> None:
    """When both keys are supplied and normalise to different values, refuse
    rather than silently preferring one."""
    service = TestService()
    _, workspace, ctx = _setup("test1151-conflict")
    group = TestToolGroup(service=service)

    result = group._handle_create(
        params={
            "workspace_id": str(workspace.id),
            "title": "TC",
            "type": "unit",
            "test_type": "system",
        },
        auth_context=ctx,
        api_key=API_KEY,
    )

    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"
    assert "Conflicting test type" in result.message

