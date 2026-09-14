"""MCP handlers of the AWMS surface (WS7 #940, spec §7).

Exercises ``AttributeMigrationToolGroup`` end-to-end against real rows: plan
validation (read), dry-run, apply, run history and rollback. The admin-only
handlers must answer ``PERMISSION_DENIED`` for a non-admin instead of silently
succeeding.
"""
from __future__ import annotations

import uuid

import pytest

from attribute_definitions.plans import plan_path
from attribute_definitions.migration_plan import load_plan_file
from auth_tenancy.context import AuthContext, AuthMethod
from mcp_server.tools.attribute_migration import AttributeMigrationToolGroup
from persistence.models import Artifact, Requirement, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

API_KEY = "reqlo-test"


@pytest.fixture
def env():
    tenant = Tenant.objects.create(name="mcp-t", slug=f"mcp-{uuid.uuid4().hex[:8]}")
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant_id=tenant.id, name="ws", preset={"name": "standard"}
        )
        artifact = Artifact.objects.create(
            tenant_id=tenant.id,
            workspace=workspace,
            artifact_type="Requirement",
        )
        Requirement.objects.create(
            tenant_id=tenant.id,
            artifact=artifact,
            title="MCP Req",
            description="Begründung: der Agent braucht sie.",
        )
        admin = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            active_roles=("admin",),
            auth_method=AuthMethod.API_KEY,
        )
        editor = AuthContext(
            user_id=uuid.uuid4(),
            tenant_id=tenant.id,
            workspace_id=workspace.id,
            active_roles=("editor",),
            auth_method=AuthMethod.API_KEY,
        )
        yield tenant, workspace, artifact, admin, editor
    finally:
        TenantContext.clear_tenant()


def _plan() -> dict:
    return load_plan_file(plan_path("rationale_from_description.yaml"))


def _call(group, tool, params, ctx):
    return group.execute_tool(
        tool_name=tool, params=params, auth_context=ctx, api_key=API_KEY
    )


def test_plan_is_read_only_and_validates(env) -> None:
    _tenant, _workspace, _artifact, admin, _editor = env
    group = AttributeMigrationToolGroup()
    result = _call(group, "attribute_migration.plan", {"plan": _plan()}, admin)
    assert result.success is True, result.message
    assert result.data["plan"]["mode"] == "dry_run"
    assert len(result.data["plan_hash"]) == 64


def test_invalid_plan_is_validation_error(env) -> None:
    _tenant, _workspace, _artifact, admin, _editor = env
    group = AttributeMigrationToolGroup()
    result = _call(
        group, "attribute_migration.plan", {"plan": {"id": "x", "steps": []}}, admin
    )
    assert result.success is False
    assert result.error_code == "VALIDATION_ERROR"


def test_dry_run_apply_history_and_rollback(env) -> None:
    _tenant, _workspace, artifact, admin, _editor = env
    group = AttributeMigrationToolGroup()

    dry = _call(group, "attribute_migration.dry_run", {"plan": _plan()}, admin)
    assert dry.success is True, dry.message
    assert dry.data["report"]["status"] == "planned"
    assert "rationale" not in (Artifact.objects.get(id=artifact.id).custom_fields or {})

    applied = _call(group, "attribute_migration.apply", {"plan": _plan()}, admin)
    assert applied.success is True, applied.message
    run_id = applied.data["report"]["run_id"]
    assert Artifact.objects.get(id=artifact.id).custom_fields["rationale"]

    runs = _call(group, "attribute_migration.list_runs", {}, admin)
    assert runs.success is True
    assert runs.data["count"] >= 1

    detail = _call(group, "attribute_migration.get_run", {"run_id": run_id}, admin)
    assert detail.success is True
    assert detail.data["run"]["id"] == run_id

    rollback = _call(
        group, "attribute_migration.rollback", {"run_id": run_id}, admin
    )
    assert rollback.success is True, rollback.message
    assert rollback.data["status"] == "rolled_back"
    assert "rationale" not in (Artifact.objects.get(id=artifact.id).custom_fields or {})


def test_admin_is_required_for_data_touching_tools(env) -> None:
    _tenant, _workspace, _artifact, _admin, editor = env
    group = AttributeMigrationToolGroup()
    result = _call(group, "attribute_migration.apply", {"plan": _plan()}, editor)
    assert result.success is False
    assert result.error_code == "PERMISSION_DENIED"


def test_rollback_unknown_run_is_not_found(env) -> None:
    _tenant, _workspace, _artifact, admin, _editor = env
    group = AttributeMigrationToolGroup()
    result = _call(
        group,
        "attribute_migration.rollback",
        {"run_id": str(uuid.uuid4())},
        admin,
    )
    assert result.success is False
    assert result.error_code == "NOT_FOUND"
