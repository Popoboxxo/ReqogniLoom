"""
End-to-end audit tests for MCP write tools.

For every successful MCP write-tool call we assert that:

* exactly one ``AuditEntry`` row is written to the DB (no mock of the
  audit layer — the real ``audit.services.log_write`` path is exercised);
* the entry's ``source`` is ``"mcp"``;
* the ``actor`` matches the caller's user UUID and ``actor_type`` is
  ``"agent"`` (the MCP client identity);
* the ``op`` and ``entity_type`` fields match the contract from
  ``WRITE_TOOL_AUDIT_OPS`` in the test module;
* the ``entity_id`` matches the created/modified entity.

In addition:

* failed write calls (RBAC denial, validation error) must NOT create
  an audit entry — they short-circuit before ``write_mcp_audit`` runs;
* the dedicated field-validation tests check ``api_key_hash`` SHA-256
  prefix, ``client_name == tool_name`` contract and the rest of the
  per-tool ``op``/``entity_type`` mapping.
* two ``audit.services.query`` tests prove the public query interface
  can locate MCP-written entries.

Leaf IDs: COMP-MC-001..011 (McpServer + 9 ToolGroups).
Req IDs: REQ-L2-MC-012 (MCP audit trail), REQ-L2-AL-001 (complete
audit fields), REQ-L2-AL-002 (MCP enrichment: client_name,
api_key_hash SHA-256).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from django.test import Client

# Persistence — direct ORM access used to seed entities per-test.
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    StakeholderNeed,
    Tenant,
    TestCase,
    TestRun,
    User,
    Workspace,
)
from presets.models import WorkspacePresetConfig

# Auth & tenancy — for UserRole/ApiKey seeding and role constants.
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import (
    ROLE_ADMIN,
    ItemPermission,
    ITEM_PERMISSION_READ,
    UserRole,
)

# Application — RequirementService for the REST-simulated regression test
# (Codeberg #313: calls the service directly, bypassing MCP entirely).
from application.requirement_service import RequirementService

# Application — DLQ rows live outside the TenantScopedModel lineage.
from application.models import DomainEventDLQ

# Audit — the model + service facade the tests inspect.
from audit.models import AuditEntry
from audit.query import AuditQueryFilters
from audit.services import query

# AdminOps — BackupMetadata is system-level (not tenant-scoped).
from admin_ops.models import BackupMetadata, BackupStatus, BackupType

# MCP e2e fixtures (auto-imported via conftest.py).

# JSON-RPC helpers.
from mcp_server.tests.helpers import (
    extract_error_code,
    extract_result,
    post_mcp,
)

# SYSTEMAUDIT SA-62: classification marker for the `test_e2e_*.py` family —
# see the `e2e` marker docstring in pyproject.toml.
pytestmark = pytest.mark.e2e


# ---------------------------------------------------------------------------
# WRITE_TOOL_AUDIT_OPS — contract under test
# ---------------------------------------------------------------------------
# Maps every MCP write-tool name to the (op, entity_type) tuple that the
# production ``write_mcp_audit`` helper is expected to write into the
# ``op`` and ``entity_type`` columns of the ``AuditEntry`` row.
#
# The mapping is the single source of truth for the per-tool contract.
# The parametrized "Pro Write-Tool" test below iterates over this dict,
# drives the corresponding MCP tool, and asserts that the produced
# ``AuditEntry`` carries exactly these field values.

WRITE_TOOL_AUDIT_OPS: Dict[str, Dict[str, str]] = {
    "requirement.create": {"op": "create", "entity_type": "Requirement"},
    "requirement.update": {"op": "update", "entity_type": "Requirement"},
    # #573: the lifecycle tools map onto the op their REST pendant writes —
    # ``outdate`` is the MCP spelling of ``DELETE /requirements/{id}/``
    # (RequirementService.delete_requirement -> op="delete") and ``reactivate``
    # mirrors ``POST /requirements/{id}/reactivate/`` (WorkflowFacade.reactivate
    # -> op="transition"), so an auditor filtering on op=delete sees REST and
    # MCP deletions alike.
    "requirement.outdate": {"op": "delete", "entity_type": "Requirement"},
    "requirement.reactivate": {"op": "transition", "entity_type": "Requirement"},
    # #573: LLM analyses have no REST pendant, so they get their own declared
    # ops in the ``ai.`` namespace (see AuditEntry.OP_CHOICES).
    "requirement.decompose": {"op": "ai.decompose", "entity_type": "Requirement"},
    "requirement.validate": {"op": "ai.validate", "entity_type": "Requirement"},
    "requirement.check_consistency": {
        "op": "ai.check_consistency",
        "entity_type": "Workspace",
    },
    "needs.outdate": {"op": "delete", "entity_type": "StakeholderNeed"},
    "needs.reactivate": {"op": "transition", "entity_type": "StakeholderNeed"},
    "architecture.create": {"op": "create", "entity_type": "ArchitectureElement"},
    "architecture.update": {"op": "update", "entity_type": "ArchitectureElement"},
    "architecture.link": {"op": "create", "entity_type": "TraceLink"},
    "test.create": {"op": "create", "entity_type": "TestCase"},
    "test.update": {"op": "update", "entity_type": "TestCase"},
    "test.link": {"op": "create", "entity_type": "TraceLink"},
    "test.run_create": {"op": "create", "entity_type": "TestRun"},
    "test.run_report_results": {"op": "update", "entity_type": "TestRun"},
    "workspace.close": {"op": "workspace.close", "entity_type": "Workspace"},
    "workspace.reactivate": {
        "op": "workspace.reactivate",
        "entity_type": "Workspace",
    },
    "workspace.delete": {"op": "workspace.delete", "entity_type": "Workspace"},
    "permissions.set_rule": {
        "op": "permissions.set_rule",
        "entity_type": "ItemPermission",
    },
    "permissions.revoke": {
        "op": "permissions.revoke",
        "entity_type": "ItemPermission",
    },
    "admin.backup_create": {
        "op": "admin.backup_create",
        "entity_type": "BackupMetadata",
    },
    "admin.restore": {"op": "admin.restore", "entity_type": "BackupRestore"},
    # #626: "replay" was undeclared and silently swallowed by write_mcp_audit
    # (relaxed in the fixture below to mask it); now "events.replay", a real
    # declared choice with no REST pendant to reuse.
    "events.dlq_replay": {"op": "events.replay", "entity_type": "DomainEventDLQ"},
    "user.create": {"op": "user.create", "entity_type": "User"},
    "user.assign_role": {"op": "user.assign_role", "entity_type": "UserRole"},
    "user.deactivate": {"op": "user.deactivate", "entity_type": "User"},
}


# ---------------------------------------------------------------------------
# Autouse fixtures — relax the audit ``op`` choices and provide a real
# BackupService/AdminRestoreService mock (the default conftest mock
# returns a bare dict; the production code reads attribute accessors on
# the returned object).
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _relax_audit_op_choices(monkeypatch: pytest.MonkeyPatch) -> None:
    """Permit non-canonical ``op`` values in the audit model.

    The production ``AuditEntry`` model restricts ``op`` to a closed
    ``choices`` enum. Several MCP tools use richer operation names (e.g.
    ``"workspace.close"``, ``"replay"``) that are not yet
    part of that enum. Those audit writes are legitimate but the model's
    ``full_clean()`` rejects them.

    This autouse fixture widens the choices list on the field's
    ``_choices`` attribute at test setup and restores the original via
    ``monkeypatch`` so the tests exercise the real service code path
    without modifying the production schema.

    #539: the admin/user/permissions op values (``"user.create"``,
    ``"admin.restore"``, ``"permissions.set_rule"``, ...) used to be relaxed
    here too — that masked the production bug where ``write_mcp_audit``
    silently swallowed the ``ValidationError`` these undeclared values
    caused, so ``test_write_tool_creates_audit_entry`` passed while real MCP
    calls wrote zero audit rows. Those values are now declared in
    ``AuditEntry.OP_CHOICES`` for real (see migration
    ``0008_alter_auditentry_op``) and no longer need relaxing.

    #573: same story for ``"decompose"`` and ``"validate"`` — relaxing them
    here is exactly what let ``requirement.decompose`` / ``requirement.validate``
    (and their unrelaxed siblings ``outdate`` / ``reactivate`` /
    ``check_consistency``, which were not covered by this test at all) ship
    while writing zero audit rows in production. The requirements/needs tool
    groups now emit declared ops only (migration
    ``0009_alter_auditentry_op``), so nothing from those groups is relaxed.

    #626: ``"replay"`` (events.dlq_replay) is fixed too — it now emits
    ``"events.replay"``, a real declared choice (migration
    ``0010_alter_auditentry_op``), so it is no longer relaxed here either.
    The ``ai_derivation.*``/``review.*``/lifecycle tools #626 also fixed are
    not in ``WRITE_TOOL_AUDIT_OPS`` at all (never covered by this harness);
    see ``audit/tests/test_op_vocabulary.py`` for their static coverage.
    """
    from audit import models as audit_models

    op_field = audit_models.AuditEntry._meta.get_field("op")
    original_choices = op_field.choices
    relaxed = list(original_choices) + [
        ("workspace.close", "Workspace Close"),
        ("workspace.reactivate", "Workspace Reactivate"),
        ("workspace.delete", "Workspace Delete"),
    ]
    op_field.choices = relaxed
    yield
    op_field.choices = original_choices


@pytest.fixture
def mock_backup_service(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Mock ``BackupService`` and ``AdminRestoreService`` with MagicMocks
    shaped like their real return types.

    The conftest :func:`mock_backup_filesystem` returns a bare dict;
    the production tool code accesses ``row.id``/``row.file_size_bytes``
    on the returned object, so we need a MagicMock with the right spec.
    """
    backup_row = MagicMock(spec=BackupMetadata)
    backup_row.id = uuid4()
    backup_row.status = BackupStatus.COMPLETED
    backup_row.backup_type = BackupType.FULL
    backup_row.file_path = str(tmp_path / "backup.json")
    backup_row.file_size_bytes = 1024
    backup_row.checksum_sha256 = "0" * 64
    backup_row.error_message = ""
    backup_row.metadata = {}
    backup_row.completed_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    backup_row.is_restorable = True
    backup_row.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    backup_row.created_by_id = None

    restore_result = MagicMock()
    restore_result.backup_id = uuid4()
    restore_result.started_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    restore_result.completed_at = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)
    restore_result.restored_tables = []
    restore_result.rows_per_table = {}

    monkeypatch.setattr(
        "admin_ops.services.BackupService.create_backup",
        MagicMock(return_value=backup_row),
    )
    monkeypatch.setattr(
        "admin_ops.services.BackupService.list_backups",
        MagicMock(return_value=[]),
    )
    monkeypatch.setattr(
        "admin_ops.services.AdminRestoreService.restore",
        MagicMock(return_value=restore_result),
    )


@pytest.fixture
def mock_llm_deep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deep-mock the LLM stack so requirement.decompose / requirement.validate
    can run end-to-end without an actual LLM provider.
    """
    def _fake_decompose(requirement_id, title=None, content=None):
        return [
            {"title": "Child A", "description": "First child"},
            {"title": "Child B", "description": "Second child"},
        ]

    monkeypatch.setattr(
        "application.requirement_service.RequirementService._decompose_via_llm",
        staticmethod(_fake_decompose),
    )

    def _fake_validate(artifact_id, title=None, content=None, ctx=None):
        return {
            "result": "valid",
            "score": 0.95,
            "issues": [],
            "artifact_id": artifact_id,
        }

    monkeypatch.setattr(
        "llm_adapter.services.validate_artifact",
        _fake_validate,
    )

    # #573: requirement.check_consistency is asynchronous — the real capability
    # returns a task id. Stub it so the tool reaches its write_mcp_audit call.
    def _fake_check_consistency(workspace_id, artifacts=None):
        return {"task_id": str(uuid4()), "status": "queued"}

    monkeypatch.setattr(
        "llm_adapter.services.check_consistency",
        _fake_check_consistency,
    )


# ---------------------------------------------------------------------------
# Local helpers — seed entities inside an active tenant context.
# ---------------------------------------------------------------------------


def _seed_requirement(workspace: Workspace, title: str = "Seeded Requirement") -> Requirement:
    set_request_tenant(workspace.tenant_id)
    try:
        artifact = Artifact.unscoped.create(
            workspace=workspace,
            tenant=workspace.tenant,
            artifact_type="Requirement",
        )
        # Task 12: `status` column dropped -- a fresh Requirement's engine
        # state already starts at "draft" (every rigor preset's states[0]).
        return Requirement.unscoped.create(
            tenant=workspace.tenant,
            artifact=artifact,
            title=title,
            description="seeded for audit test",
            category="functional",
        )
    finally:
        clear_request_tenant()


def _seed_stakeholder_need(
    workspace: Workspace, title: str = "Seeded Need"
) -> StakeholderNeed:
    set_request_tenant(workspace.tenant_id)
    try:
        artifact = Artifact.unscoped.create(
            workspace=workspace,
            tenant=workspace.tenant,
            artifact_type="StakeholderNeed",
        )
        # Task 12: `status` column dropped -- need_default's initial state is
        # also "draft" (see workflow/definition_store.py PRESET_SCHEMAS).
        return StakeholderNeed.unscoped.create(
            tenant=workspace.tenant,
            artifact=artifact,
            title=title,
            description="seeded for audit test",
        )
    finally:
        clear_request_tenant()


def _ensure_workflow_definitions(workspace: Workspace) -> None:
    """Provision the per-entity workflow definitions for an ORM-built workspace.

    ``e2e_workspace`` creates the ``Workspace`` row directly, which skips the
    provisioning that ``WorkspaceService`` normally performs — and
    ``workflow.services.outdate`` needs a ``WorkflowEngineDefinition`` to
    initialise the item state against. Idempotent (``get_or_create``
    throughout), so calling it per test case is safe.
    """
    from application.workspace_provisioning import provision_workspace_defaults

    set_request_tenant(workspace.tenant_id)
    try:
        provision_workspace_defaults(
            workspace_id=workspace.id,
            tenant_id=workspace.tenant_id,
            requirement_preset="extended",
        )
    finally:
        clear_request_tenant()


def _outdate_for_reactivate(
    workspace: Workspace, item_id: Any, item_type: str, user: User
) -> None:
    """Soft-delete *item_id* so a ``*.reactivate`` tool call has work to do.

    ``workflow.services.outdate`` is the same escape hatch the MCP outdate
    handlers use; calling it directly here keeps the arrange step out of the
    tool under test.
    """
    from auth_tenancy.context import AuthContext as _AuthContext

    set_request_tenant(workspace.tenant_id)
    try:
        from workflow.services import outdate

        outdate(
            item_id=item_id,
            item_type=item_type,
            workspace_id=workspace.id,
            ctx=_AuthContext(
                user_id=user.id,
                tenant_id=workspace.tenant_id,
                active_roles=(ROLE_ADMIN,),
                auth_method=AuthMethod.API_KEY,
                workspace_id=workspace.id,
            ),
            reason="arranged for reactivate audit test",
        )
    finally:
        clear_request_tenant()


def _seed_architecture_element(
    workspace: Workspace, title: str = "Seeded Component"
) -> ArchitectureElement:
    set_request_tenant(workspace.tenant_id)
    try:
        artifact = Artifact.unscoped.create(
            workspace=workspace,
            tenant=workspace.tenant,
            artifact_type="ArchitectureElement",
        )
        return ArchitectureElement.unscoped.create(
            tenant=workspace.tenant,
            artifact=artifact,
            title=title,
            description="seeded for audit test",
            element_type="component",
        )
    finally:
        clear_request_tenant()


def _seed_test_case(workspace: Workspace, title: str = "Seeded Test") -> TestCase:
    set_request_tenant(workspace.tenant_id)
    try:
        artifact = Artifact.unscoped.create(
            workspace=workspace,
            tenant=workspace.tenant,
            artifact_type="TestCase:Unit",
        )
        return TestCase.unscoped.create(
            tenant=workspace.tenant,
            artifact=artifact,
            title=title,
            description="seeded for audit test",
            steps=["step 1", "step 2"],
        )
    finally:
        clear_request_tenant()


def _seed_test_run(workspace: Workspace, name: str = "Seeded Run") -> TestRun:
    set_request_tenant(workspace.tenant_id)
    try:
        return TestRun.objects.create(
            workspace=workspace,
            name=name,
            ci_job_id="ci-audit-1",
            status="in_progress",
        )
    finally:
        clear_request_tenant()


def _seed_item_permission(
    workspace: Workspace, user: User, granted_by: Optional[User] = None
) -> ItemPermission:
    set_request_tenant(workspace.tenant_id)
    try:
        return ItemPermission.unscoped.create(
            tenant=workspace.tenant,
            user=user,
            workspace=workspace,
            artifact=None,
            permission_level=ITEM_PERMISSION_READ,
            granted_by=granted_by,
        )
    finally:
        clear_request_tenant()


def _seed_dlq_row(workspace: Workspace) -> DomainEventDLQ:
    return DomainEventDLQ.objects.create(
        event_id=uuid4(),
        event_type="RequirementCreated",
        workspace_id=workspace.id,
        entity_id=uuid4(),
        payload={"title": "audit dlq test"},
        error_message="simulated failure",
        retry_count=5,
    )


def _seed_deletable_workspace(workspace: Workspace, user: User) -> Workspace:
    """Create a fresh workspace + admin role that can be hard-deleted."""
    set_request_tenant(workspace.tenant_id)
    try:
        new_ws = Workspace.objects.create(
            tenant=workspace.tenant,
            name=f"Audit-Deletable {uuid4().hex[:6]}",
            is_active=True,
            preset={"name": "e2e_preset"},
        )
        WorkspacePresetConfig.unscoped.create(
            tenant=workspace.tenant,
            workspace=new_ws,
            active_tier="extended",
            terminology_profile="dev_mode",
            downgrade_policy="allow",
        )
        UserRole.unscoped.create(
            tenant=workspace.tenant,
            user=user,
            workspace=new_ws,
            role=ROLE_ADMIN,
            suspended_at=None,
        )
    finally:
        clear_request_tenant()
    return new_ws


# ---------------------------------------------------------------------------
# Per-tool parametrisation: build the request params and seed any
# dependencies the tool needs before the POST.
# ---------------------------------------------------------------------------


def _build_audit_params(
    tool_name: str,
    workspace: Workspace,
    user_admin: User,
    user_member: User,
    user_viewer: User,
) -> Dict[str, Any]:
    """Return the params dict for a single write-tool call.

    Seeds any prerequisite entity inside the tenant context, and
    substitutes the real id into the params dict. Returns both the
    params and the seeded entity (when applicable) so the test can
    assert the audit entry's ``entity_id`` matches.
    """
    if tool_name == "requirement.create":
        return {"title": "Audit Test", "workspace_id": str(workspace.id)}
    if tool_name == "requirement.update":
        req = _seed_requirement(workspace)
        return {
            "id": str(req.id),
            "workspace_id": str(workspace.id),
            "data": {"title": "Updated Audit Title", "change_reason": "audit test"},
        }
    if tool_name == "requirement.outdate":
        _ensure_workflow_definitions(workspace)
        req = _seed_requirement(workspace)
        return {"id": str(req.id), "workspace_id": str(workspace.id)}
    if tool_name == "requirement.reactivate":
        _ensure_workflow_definitions(workspace)
        req = _seed_requirement(workspace)
        _outdate_for_reactivate(workspace, req.id, "Requirement", user_admin)
        return {"id": str(req.id), "workspace_id": str(workspace.id)}
    if tool_name == "requirement.decompose":
        req = _seed_requirement(workspace)
        return {"requirement_id": str(req.id), "workspace_id": str(workspace.id)}
    if tool_name == "requirement.validate":
        req = _seed_requirement(workspace)
        return {"requirement_id": str(req.id), "workspace_id": str(workspace.id)}
    if tool_name == "requirement.check_consistency":
        _seed_requirement(workspace, "Consistency Subject")
        return {"workspace_id": str(workspace.id)}
    if tool_name == "needs.outdate":
        _ensure_workflow_definitions(workspace)
        need = _seed_stakeholder_need(workspace)
        return {"id": str(need.id), "workspace_id": str(workspace.id)}
    if tool_name == "needs.reactivate":
        _ensure_workflow_definitions(workspace)
        need = _seed_stakeholder_need(workspace)
        _outdate_for_reactivate(workspace, need.id, "StakeholderNeed", user_admin)
        return {"id": str(need.id), "workspace_id": str(workspace.id)}
    if tool_name == "architecture.create":
        return {"title": "Audit Arch", "workspace_id": str(workspace.id)}
    if tool_name == "architecture.update":
        arch = _seed_architecture_element(workspace)
        return {
            "id": str(arch.id),
            "workspace_id": str(workspace.id),
            "data": {"title": "Updated Arch"},
        }
    if tool_name == "architecture.link":
        a1 = _seed_architecture_element(workspace, "Source")
        a2 = _seed_architecture_element(workspace, "Target")
        # architecture.link takes artifact_ids, not element ids.
        return {
            "arch_id": str(a1.artifact_id),
            "target_id": str(a2.artifact_id),
            "link_type": "satisfies",
            "workspace_id": str(workspace.id),
        }
    if tool_name == "test.create":
        return {"title": "Audit Test Case", "workspace_id": str(workspace.id)}
    if tool_name == "test.update":
        tc = _seed_test_case(workspace)
        return {
            "id": str(tc.id),
            "workspace_id": str(workspace.id),
            "data": {"title": "Updated TC"},
        }
    if tool_name == "test.link":
        tc = _seed_test_case(workspace)
        req = _seed_requirement(workspace)
        return {
            "test_id": str(tc.id),
            "req_id": str(req.artifact_id),
            "workspace_id": str(workspace.id),
        }
    if tool_name == "test.run_create":
        return {"workspace_id": str(workspace.id), "name": "Audit Run"}
    if tool_name == "test.run_report_results":
        tr = _seed_test_run(workspace)
        tc = _seed_test_case(workspace, "Reported TC")
        return {
            "run_id": str(tr.id),
            "workspace_id": str(workspace.id),
            "results": [
                {
                    "test_case_id": str(tc.id),
                    "status": "passed",
                    "message": "ok",
                }
            ],
        }
    if tool_name == "workspace.close":
        return {"workspace_id": str(workspace.id)}
    if tool_name == "workspace.reactivate":
        return {"workspace_id": str(workspace.id)}
    if tool_name == "workspace.delete":
        target = _seed_deletable_workspace(workspace, user_admin)
        return {
            "workspace_id": str(target.id),
            "confirmation_text": target.name,
        }
    if tool_name == "permissions.set_rule":
        return {
            "workspace_id": str(workspace.id),
            "user_id": str(user_viewer.id),
            "permission_level": "read",
        }
    if tool_name == "permissions.revoke":
        perm = _seed_item_permission(workspace, user_viewer, granted_by=user_admin)
        return {
            "permission_id": str(perm.id),
            "workspace_id": str(workspace.id),
        }
    if tool_name == "admin.backup_create":
        return {"workspace_id": str(workspace.id)}
    if tool_name == "admin.restore":
        return {
            "backup_id": str(uuid4()),
            "confirmation_text": "RESTORE",
            "workspace_id": str(workspace.id),
        }
    if tool_name == "events.dlq_replay":
        dlq = _seed_dlq_row(workspace)
        return {
            "event_id": str(dlq.event_id),
            "workspace_id": str(workspace.id),
        }
    if tool_name == "user.create":
        return {
            "username": f"audit_user_{uuid4().hex[:8]}",
            "email": f"audit_{uuid4().hex[:8]}@e2e.test",
            "password": "verysecret123",
            "workspace_id": str(workspace.id),
        }
    if tool_name == "user.assign_role":
        # user.assign_role requires a user who is already a member of the
        # target workspace. The e2e_member fixture has an editor role in
        # the e2e workspace, so re-assigning is allowed.
        return {
            "user_id": str(user_member.id),
            "workspace_id": str(workspace.id),
            "role": "viewer",
            "preset": "extended",
        }
    if tool_name == "user.deactivate":
        return {
            "user_id": str(user_viewer.id),
            "workspace_id": str(workspace.id),
        }
    raise ValueError(f"Unknown tool: {tool_name}")


# ---------------------------------------------------------------------------
# 1. PRO WRITE-TOOL TESTS — one test per tool (23 cases)
# ---------------------------------------------------------------------------


_WRITE_TOOL_NAMES: List[str] = list(WRITE_TOOL_AUDIT_OPS.keys())


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("tool_name", _WRITE_TOOL_NAMES, ids=_WRITE_TOOL_NAMES)
def test_write_tool_creates_audit_entry(
    tool_name: str,
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_user_admin: User,
    e2e_user_member: User,
    e2e_user_viewer: User,
    e2e_userrole_admin: UserRole,
    e2e_userrole_member: UserRole,
    e2e_userrole_viewer: UserRole,
    mock_llm_configured: None,
    mock_llm_deep: None,
    mock_backup_service: None,
):
    """A successful ``<tool>`` call writes exactly one AuditEntry row.

    The audit row must carry:

    * ``source == "mcp"``
    * ``actor == str(caller_user_id)`` and ``actor_type == "agent"``
    * ``op`` and ``entity_type`` matching ``WRITE_TOOL_AUDIT_OPS[tool]``
    * ``client_name`` populated with the tool name (per the contract
      documented in the task spec).

    This is a real DB roundtrip — no mock of the audit writer.
    """
    params = _build_audit_params(
        tool_name, e2e_workspace, e2e_user_admin, e2e_user_member, e2e_user_viewer
    )

    response = post_mcp(admin_client, tool_name, params)
    assert response.status_code == 200, (
        f"{tool_name} returned HTTP {response.status_code}: {response.content!r}"
    )
    body = response.json()
    assert "result" in body, f"{tool_name} missing 'result': {body}"

    expected = WRITE_TOOL_AUDIT_OPS[tool_name]
    expected_op = expected["op"]
    expected_entity_type = expected["entity_type"]

    # Locate the AuditEntry for this tool + entity_type — there is at
    # least one new entry (the one just written).
    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entry = (
            AuditEntry.unscoped
            .filter(
                tenant_id=e2e_workspace.tenant_id,
                client_name=tool_name,
                entity_type=expected_entity_type,
            )
            .order_by("-timestamp")
            .first()
        )
    finally:
        clear_request_tenant()

    assert entry is not None, (
        f"{tool_name}: no AuditEntry with client_name={tool_name!r} "
        f"and entity_type={expected_entity_type!r}"
    )

    # The most recent new entry must match the contract.
    assert entry.source == AuditEntry.SOURCE_MCP, (
        f"{tool_name}: source={entry.source!r}, expected 'mcp'"
    )
    assert entry.actor_type == AuditEntry.ACTOR_TYPE_AGENT, (
        f"{tool_name}: actor_type={entry.actor_type!r}, expected 'agent'"
    )
    assert entry.actor == str(e2e_user_admin.id), (
        f"{tool_name}: actor={entry.actor!r}, expected {e2e_user_admin.id!r}"
    )
    assert entry.op == expected_op, (
        f"{tool_name}: op={entry.op!r}, expected {expected_op!r}"
    )
    assert entry.entity_type == expected_entity_type, (
        f"{tool_name}: entity_type={entry.entity_type!r}, "
        f"expected {expected_entity_type!r}"
    )
    assert entry.client_name == tool_name, (
        f"{tool_name}: client_name={entry.client_name!r}, "
        f"expected {tool_name!r}"
    )


# ---------------------------------------------------------------------------
# 2. AUDIT-FELD-VALIDIERUNG — per-field contract checks (7 tests)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_audit_entry_has_correct_actor(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_user_admin: User,
    e2e_userrole_admin: UserRole,
):
    """Audit entry's ``actor`` field equals the calling user's UUID string."""
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entries = list(
            AuditEntry.unscoped.filter(
                tenant_id=e2e_workspace.tenant_id,
                source=AuditEntry.SOURCE_MCP,
                client_name="workspace.close",
            )
        )
    finally:
        clear_request_tenant()

    assert len(entries) == 1, f"Expected 1 entry, got {len(entries)}"
    assert entries[0].actor == str(e2e_user_admin.id)


@pytest.mark.django_db(transaction=True)
def test_audit_entry_has_sha256_api_key_hash(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_user_admin: User,
    e2e_api_key_admin: str,
    e2e_userrole_admin: UserRole,
):
    """Audit entry's ``api_key_hash`` is the SHA-256 of the caller's API key,
    prefixed with ``"sha256:"`` — never the raw key."""
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entry = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            source=AuditEntry.SOURCE_MCP,
            client_name="workspace.close",
        ).first()
    finally:
        clear_request_tenant()

    assert entry is not None
    assert entry.api_key_hash is not None
    assert entry.api_key_hash.startswith("sha256:"), entry.api_key_hash

    expected = "sha256:" + hashlib.sha256(e2e_api_key_admin.encode()).hexdigest()
    assert entry.api_key_hash == expected

    # And the raw key must NEVER appear in the hash itself.
    assert e2e_api_key_admin not in entry.api_key_hash


@pytest.mark.django_db(transaction=True)
def test_audit_entry_source_is_mcp(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """Audit entry's ``source`` is the literal string ``"mcp"``."""
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entry = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            client_name="workspace.close",
        ).first()
    finally:
        clear_request_tenant()

    assert entry is not None
    assert entry.source == "mcp"


@pytest.mark.django_db(transaction=True)
def test_audit_entry_client_name_equals_tool_name(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """Audit entry's ``client_name`` records the MCP tool name verbatim."""
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entry = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            source=AuditEntry.SOURCE_MCP,
        ).first()
    finally:
        clear_request_tenant()

    assert entry is not None
    assert entry.client_name == "workspace.close"


@pytest.mark.django_db(transaction=True)
def test_audit_entry_actor_type_is_agent(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """MCP writes use ``actor_type == "agent"`` (NOT ``"user"``)."""
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entry = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            source=AuditEntry.SOURCE_MCP,
        ).first()
    finally:
        clear_request_tenant()

    assert entry is not None
    assert entry.actor_type == "agent"


@pytest.mark.django_db(transaction=True)
def test_failed_write_does_not_create_audit_entry(
    viewer_client: Client,
    e2e_workspace: Workspace,
    e2e_user_viewer: User,
    e2e_userrole_viewer: UserRole,
):
    """A write call denied at RBAC must NOT produce an AuditEntry.

    The dispatcher short-circuits with ``403 PERMISSION_DENIED`` before
    the tool handler runs, so ``write_mcp_audit`` is never invoked.
    """
    set_request_tenant(e2e_workspace.tenant_id)
    try:
        before = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            client_name="workspace.close",
        ).count()
    finally:
        clear_request_tenant()

    response = post_mcp(
        viewer_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 403, response.content
    assert extract_error_code(response) == "PERMISSION_DENIED"

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        after = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            client_name="workspace.close",
        ).count()
    finally:
        clear_request_tenant()

    assert after == before, (
        f"RBAC-denied write created audit entry: before={before}, after={after}"
    )


@pytest.mark.django_db(transaction=True)
def test_validation_error_does_not_create_audit_entry(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """A write call that fails parameter validation must NOT produce an
    AuditEntry.

    ``workspace.delete`` checks the captcha inside the service; a wrong
    confirmation text raises ValidationError before the audit write.
    """
    set_request_tenant(e2e_workspace.tenant_id)
    try:
        before = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            client_name="workspace.delete",
        ).count()
    finally:
        clear_request_tenant()

    response = post_mcp(
        admin_client,
        "workspace.delete",
        {
            "workspace_id": str(e2e_workspace.id),
            "confirmation_text": "WRONG CONFIRMATION",
        },
    )
    assert response.status_code == 400, response.content
    assert extract_error_code(response) == "VALIDATION_ERROR"

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        after = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            client_name="workspace.delete",
        ).count()
    finally:
        clear_request_tenant()

    assert after == before, (
        f"Validation-failed write created audit entry: before={before}, after={after}"
    )


# ---------------------------------------------------------------------------
# 3. AUDIT-QUERY TESTS — verify the public query interface
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_audit_query_finds_mcp_entries(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_user_admin: User,
    e2e_userrole_admin: UserRole,
):
    """``audit.services.query`` with source='mcp' filter returns the MCP entry
    just written by workspace.close.
    """
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        result = query(
            filters=AuditQueryFilters(source="mcp"),
            page=1,
            page_size=50,
        )
    finally:
        clear_request_tenant()

    assert result.total >= 1
    mcp_entries = [e for e in result.entries if e.source == "mcp"]
    assert len(mcp_entries) >= 1

    # Find at least one entry for our tool.
    matching = [
        e for e in mcp_entries
        if e.client_name == "workspace.close"
        and e.entity_type == "Workspace"
    ]
    assert len(matching) >= 1
    assert str(matching[0].entity_id) == str(e2e_workspace.id)


@pytest.mark.django_db(transaction=True)
def test_audit_query_finds_by_entity_id(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_user_admin: User,
    e2e_userrole_admin: UserRole,
):
    """``audit.services.query`` with entity_id filter returns the MCP entry
    whose entity_id matches.
    """
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        result = query(
            filters=AuditQueryFilters(
                entity_id=e2e_workspace.id,
                entity_type="Workspace",
            ),
            page=1,
            page_size=50,
        )
    finally:
        clear_request_tenant()

    assert result.total >= 1
    assert any(
        e.entity_id == e2e_workspace.id
        and e.source == "mcp"
        and e.client_name == "workspace.close"
        for e in result.entries
    )


# ---------------------------------------------------------------------------
# 4. ADDITIONAL CONTRACT CHECKS — granular per-field behaviour
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_audit_entry_is_append_only_at_model_level(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """After a write, the AuditEntry cannot be UPDATEd or DELETEd via the
    ORM — REQ-L2-AL-003 / APPEND-ONLY contract.
    """
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entry = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            source=AuditEntry.SOURCE_MCP,
            client_name="workspace.close",
        ).first()
    finally:
        clear_request_tenant()

    assert entry is not None
    # Update at instance level must raise.
    with pytest.raises(RuntimeError, match="append-only"):
        entry.save()
    # Delete at instance level must raise.
    with pytest.raises(RuntimeError, match="append-only"):
        entry.delete()


@pytest.mark.django_db(transaction=True)
def test_audit_entry_carries_tenant_id(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_tenant: Tenant,
    e2e_userrole_admin: UserRole,
):
    """Audit entry's ``tenant_id`` matches the caller's tenant context."""
    response = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_tenant.id)
    try:
        entry = AuditEntry.unscoped.filter(
            source=AuditEntry.SOURCE_MCP,
            client_name="workspace.close",
        ).first()
    finally:
        clear_request_tenant()

    assert entry is not None
    assert entry.tenant_id == e2e_tenant.id


@pytest.mark.django_db(transaction=True)
def test_multiple_write_calls_create_multiple_audit_entries(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """Two workspace.close calls (after reactivate) produce two MCP entries."""
    # 1. close
    r1 = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert r1.status_code == 200, r1.content
    # 2. reactivate
    r2 = post_mcp(
        admin_client, "workspace.reactivate", {"workspace_id": str(e2e_workspace.id)}
    )
    assert r2.status_code == 200, r2.content
    # 3. close again
    r3 = post_mcp(
        admin_client, "workspace.close", {"workspace_id": str(e2e_workspace.id)}
    )
    assert r3.status_code == 200, r3.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entries = list(
            AuditEntry.unscoped.filter(
                tenant_id=e2e_workspace.tenant_id,
                source=AuditEntry.SOURCE_MCP,
            ).order_by("timestamp")
        )
    finally:
        clear_request_tenant()

    tools = [e.client_name for e in entries]
    assert tools == ["workspace.close", "workspace.reactivate", "workspace.close"]


@pytest.mark.django_db(transaction=True)
def test_audit_entry_for_requirement_create_records_requirement_id(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """``requirement.create`` writes an audit entry whose entity_id matches
    the new Requirement's id.
    """
    response = post_mcp(
        admin_client,
        "requirement.create",
        {"title": "Audit Req", "workspace_id": str(e2e_workspace.id)},
    )
    assert response.status_code == 200, response.content
    req_id = extract_result(response)["requirement"]["id"]

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entry = AuditEntry.unscoped.filter(
            tenant_id=e2e_workspace.tenant_id,
            source=AuditEntry.SOURCE_MCP,
            client_name="requirement.create",
            entity_type="Requirement",
        ).first()
    finally:
        clear_request_tenant()

    assert entry is not None
    assert str(entry.entity_id) == req_id
    assert entry.op == "create"


# ---------------------------------------------------------------------------
# Codeberg #313 — MCP write tools must not double-audit
# ---------------------------------------------------------------------------
#
# test_write_tool_creates_audit_entry (above) filters
# ``AuditEntry.objects.filter(client_name=tool_name, ...)`` and only
# inspects the *most recent* match — it would never have caught #313,
# because the redundant internal ServiceBase._audit() entry has
# client_name=None and is silently excluded by that filter. The three
# tests below count ALL AuditEntry rows for the affected entity_id,
# unfiltered by client_name, which is what actually proves "exactly one".


@pytest.mark.django_db(transaction=True)
def test_requirement_create_writes_exactly_one_audit_entry_total(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_user_admin: User,
    e2e_userrole_admin: UserRole,
):
    """Codeberg #313: requirement.create must write exactly ONE AuditEntry
    row for the created Requirement — not two (one from
    RequirementService._audit via ServiceBase, one from write_mcp_audit).

    The sole entry must still carry the MCP enrichment (client_name,
    hashed api_key, actor_type='agent') write_mcp_audit adds.
    """
    response = post_mcp(
        admin_client,
        "requirement.create",
        {"title": "313 regression", "workspace_id": str(e2e_workspace.id)},
    )
    assert response.status_code == 200, response.content
    req_id = extract_result(response)["requirement"]["id"]

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entries = list(
            AuditEntry.unscoped.filter(
                tenant_id=e2e_workspace.tenant_id,
                entity_type="Requirement",
                entity_id=req_id,
            )
        )
    finally:
        clear_request_tenant()

    assert len(entries) == 1, (
        f"requirement.create wrote {len(entries)} AuditEntry row(s) for "
        f"entity_id={req_id}, expected exactly 1 (Codeberg #313): "
        f"{[(e.op, e.client_name, e.actor_type) for e in entries]}"
    )
    entry = entries[0]
    assert entry.source == AuditEntry.SOURCE_MCP
    assert entry.actor_type == AuditEntry.ACTOR_TYPE_AGENT
    assert entry.client_name == "requirement.create"
    assert entry.api_key_hash, "sole entry must carry the MCP-hashed api_key"
    assert entry.actor == str(e2e_user_admin.id)


@pytest.mark.django_db(transaction=True)
def test_requirement_update_writes_exactly_one_audit_entry_total(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
):
    """Codeberg #313: requirement.update must write exactly ONE AuditEntry
    row (same duplicate pattern as create, on the update path)."""
    req = _seed_requirement(e2e_workspace)
    response = post_mcp(
        admin_client,
        "requirement.update",
        {
            "id": str(req.id),
            "workspace_id": str(e2e_workspace.id),
            "data": {"title": "313 updated", "change_reason": "regression test"},
        },
    )
    assert response.status_code == 200, response.content

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        entries = list(
            AuditEntry.unscoped.filter(
                tenant_id=e2e_workspace.tenant_id,
                entity_type="Requirement",
                entity_id=req.id,
            )
        )
    finally:
        clear_request_tenant()

    assert len(entries) == 1, (
        f"requirement.update wrote {len(entries)} AuditEntry row(s) for "
        f"entity_id={req.id}, expected exactly 1 (Codeberg #313): "
        f"{[(e.op, e.client_name, e.actor_type) for e in entries]}"
    )
    assert entries[0].client_name == "requirement.update"


@pytest.mark.django_db(transaction=True)
def test_rest_originated_create_still_writes_exactly_one_audit_entry(
    e2e_workspace: Workspace,
    e2e_tenant: Tenant,
    e2e_user_admin: User,
):
    """Codeberg #313 regression guard: a REST-style caller (no MCP, no
    ``mcp_audit_handoff()`` in play at all) calling
    ``RequirementService.create_requirement`` directly must still produce
    exactly one AuditEntry row, with the pre-#313 REST shape (source='rest',
    actor_type='user', client_name=None) — proving the new suppression
    mechanism defaults to inactive and does not leak across calls.
    """
    ctx = AuthContext(
        user_id=e2e_user_admin.id,
        tenant_id=e2e_tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        req = RequirementService().create_requirement(
            workspace_id=e2e_workspace.id,
            title="313 REST regression",
            ctx=ctx,
        )
        entries = list(
            AuditEntry.unscoped.filter(
                tenant_id=e2e_workspace.tenant_id,
                entity_type="Requirement",
                entity_id=req.id,
            )
        )
    finally:
        clear_request_tenant()

    assert len(entries) == 1, (
        f"direct RequirementService.create_requirement() call wrote "
        f"{len(entries)} AuditEntry row(s), expected exactly 1: "
        f"{[(e.op, e.client_name, e.source) for e in entries]}"
    )
    entry = entries[0]
    assert entry.source == AuditEntry.SOURCE_REST
    assert entry.actor_type == AuditEntry.ACTOR_TYPE_USER
    assert entry.client_name is None
    assert entry.op == "create"


@pytest.mark.django_db(transaction=True)
def test_requirement_decompose_still_writes_one_entry_per_child(
    admin_client: Client,
    e2e_workspace: Workspace,
    e2e_userrole_admin: UserRole,
    mock_llm_configured: None,
    mock_llm_deep: None,
):
    """Codeberg #313 non-regression: requirement.decompose is a genuine
    multi-entity operation (mock_llm_deep returns 2 children) — the fix
    must NOT suppress the per-child internal audit entries. Each child
    Requirement gets its own ``_audit(op='create', entity_type='Requirement',
    entity_id=child.id)`` from RequirementService.create_requirement,
    distinct from the single MCP-level ``op='decompose'`` summary entry
    write_mcp_audit writes for the *parent*.
    """
    parent = _seed_requirement(e2e_workspace, title="313 decompose parent")

    response = post_mcp(
        admin_client,
        "requirement.decompose",
        {"requirement_id": str(parent.id), "workspace_id": str(e2e_workspace.id)},
    )
    assert response.status_code == 200, response.content
    result = extract_result(response)
    child_ids = [c["id"] for c in result["children"]]
    assert len(child_ids) == 2, f"expected 2 children from mock_llm_deep, got {result}"

    set_request_tenant(e2e_workspace.tenant_id)
    try:
        child_create_entries = list(
            AuditEntry.unscoped.filter(
                tenant_id=e2e_workspace.tenant_id,
                entity_type="Requirement",
                entity_id__in=child_ids,
                op="create",
            )
        )
        parent_decompose_entries = list(
            AuditEntry.unscoped.filter(
                tenant_id=e2e_workspace.tenant_id,
                entity_type="Requirement",
                entity_id=parent.id,
                op="ai.decompose",
            )
        )
    finally:
        clear_request_tenant()

    # One legitimate internal "create" entry per child — not suppressed.
    assert len(child_create_entries) == 2, (
        f"expected one internal 'create' AuditEntry per decomposed child, "
        f"got {len(child_create_entries)}: {[e.entity_id for e in child_create_entries]}"
    )
    assert {str(e.entity_id) for e in child_create_entries} == set(child_ids)
    # And exactly one MCP-level "ai.decompose" summary entry for the parent.
    assert len(parent_decompose_entries) == 1
