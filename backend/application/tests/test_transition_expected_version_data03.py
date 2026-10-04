"""DATA-03 (AUD-2026-09-282) — the remaining service transition wrappers.

The audit found six service methods whose ``WorkflowFacade.transition`` call
dropped the caller's ``expected_version``, leaving REST transitions
last-writer-wins even though the same services' ``update_*`` methods were
CAS-protected. ``adr_service`` and ``change_request_service`` were fixed by
``5e392aa7``; this file pins the remaining wrappers:

* ``RiskService.transition_status``
* ``IssueService.transition_status``
* ``MainGoalService.approve``
* ``GoalService.archive`` / ``GoalService.restore``

``GoalService.transition_status`` itself already forwards the revision (fixed
by ``c2c25a03``); its ``archive``/``restore`` wrappers are the two that only
called ``transition_status`` without threading it through.

Each test asserts the three-part contract the audit asks for:

* a stale ``expected_version`` raises ``OptimisticLockError`` (409 CONFLICT at
  the REST boundary);
* the *current* revision still succeeds (a compare, not a blanket rejection);
* omitting it still succeeds (the historical last-writer-wins path is
  unchanged for callers that do not track revisions).

Before the fix every stale case failed with ``TypeError: transition_status()
got an unexpected keyword argument 'expected_version'`` — the parameter did not
exist at all, so the assertion below is genuinely red pre-fix.
"""
from __future__ import annotations

import uuid

import pytest

from application.base import OptimisticLockError
from application.goal_service import GoalService
from application.issue_service import IssueService
from application.main_goal_service import MainGoalService
from application.risk_service import RiskService
from auth_tenancy.context import AuthContext
from persistence.models import Tenant, User
from persistence.models import Workspace as PersistenceWorkspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _auth_ctx(*, tenant_id, user_id, workspace_id, roles):
    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        active_roles=roles,
        auth_method="test",
        api_key_id=None,
        workspace_id=workspace_id,
    )


def _new_tenant_workspace_user(slug: str, **workspace_kwargs):
    tenant = Tenant.objects.create(name=slug, slug=slug)
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = PersistenceWorkspace.objects.create(
            tenant=tenant, name=f"{slug}-ws", **workspace_kwargs
        )
        user = User.objects.create(
            username=f"{slug}-user", email=f"{slug}@example.com", tenant=tenant
        )
    finally:
        TenantContext.clear_tenant()
    return tenant, workspace, user


def _provision(workspace, preset: str, item_type: str) -> None:
    TenantContext.set_tenant(workspace.tenant_id)
    try:
        create_default_workflow(
            workspace_id=workspace.id,
            preset=preset,
            item_type=item_type,
            tenant_id=workspace.tenant_id,
        )
    finally:
        TenantContext.clear_tenant()


def _engine_version(tenant_id, item_id, item_type, workspace_id) -> int:
    TenantContext.set_tenant(tenant_id)
    try:
        return WorkflowItemState.objects.get(
            item_id=item_id, item_type=item_type, workspace_id=workspace_id
        ).version
    finally:
        TenantContext.clear_tenant()


# ---------------------------------------------------------------------------
# RiskService.transition_status
# ---------------------------------------------------------------------------


@pytest.fixture
def risk_env():
    tenant, workspace, user = _new_tenant_workspace_user("data03-risk")
    _provision(workspace, "risk_default", "Risk")
    editor = _auth_ctx(
        tenant_id=tenant.id,
        user_id=user.id,
        workspace_id=workspace.id,
        roles=("editor",),
    )
    risk = RiskService().create_risk(
        workspace_id=workspace.id,
        title="DATA-03 risk",
        probability="low",
        impact="low",
        ctx=editor,
    )
    return tenant, workspace, user, editor, risk


def test_risk_transition_stale_expected_version_is_a_conflict(risk_env):
    tenant, workspace, _user, editor, risk = risk_env
    svc = RiskService()
    # First transition bumps the engine revision from 1 to 2.
    svc.transition_status(risk_id=risk.id, target_status="Monitored", ctx=editor)
    stale = _engine_version(tenant.id, risk.id, "Risk", workspace.id) - 1

    with pytest.raises(OptimisticLockError):
        svc.transition_status(
            risk_id=risk.id,
            target_status="Monitored",
            ctx=editor,
            expected_version=stale,
        )


def test_risk_transition_current_expected_version_succeeds(risk_env):
    tenant, workspace, _user, editor, risk = risk_env
    current = _engine_version(tenant.id, risk.id, "Risk", workspace.id)

    updated = RiskService().transition_status(
        risk_id=risk.id,
        target_status="Monitored",
        ctx=editor,
        expected_version=current,
    )

    assert updated.status == "Monitored"


def test_risk_transition_without_expected_version_still_succeeds(risk_env):
    _tenant, _workspace, _user, editor, risk = risk_env

    updated = RiskService().transition_status(
        risk_id=risk.id, target_status="Monitored", ctx=editor
    )

    assert updated.status == "Monitored"


# ---------------------------------------------------------------------------
# IssueService.transition_status
# ---------------------------------------------------------------------------


@pytest.fixture
def issue_env():
    tenant, workspace, user = _new_tenant_workspace_user("data03-issue")
    _provision(workspace, "issue_default", "Issue")
    editor = _auth_ctx(
        tenant_id=tenant.id,
        user_id=user.id,
        workspace_id=workspace.id,
        roles=("editor",),
    )
    issue = IssueService().create_issue(
        workspace_id=workspace.id,
        title="DATA-03 issue",
        severity="medium",
        ctx=editor,
    )
    return tenant, workspace, user, editor, issue


def test_issue_transition_stale_expected_version_is_a_conflict(issue_env):
    tenant, workspace, _user, editor, issue = issue_env
    svc = IssueService()
    svc.transition_status(
        issue_id=issue.id,
        target_status="In Progress",
        ctx=editor,
        change_reason="starting work",
    )
    stale = _engine_version(tenant.id, issue.id, "Issue", workspace.id) - 1

    with pytest.raises(OptimisticLockError):
        svc.transition_status(
            issue_id=issue.id,
            target_status="In Progress",
            ctx=editor,
            change_reason="stale retry",
            expected_version=stale,
        )


def test_issue_transition_current_expected_version_succeeds(issue_env):
    tenant, workspace, _user, editor, issue = issue_env
    current = _engine_version(tenant.id, issue.id, "Issue", workspace.id)

    updated = IssueService().transition_status(
        issue_id=issue.id,
        target_status="In Progress",
        ctx=editor,
        change_reason="starting work",
        expected_version=current,
    )

    assert updated.status == "In Progress"


# ---------------------------------------------------------------------------
# MainGoalService.approve
# ---------------------------------------------------------------------------


@pytest.fixture
def main_goal_env():
    tenant, workspace, user = _new_tenant_workspace_user(
        "data03-main-goal", goals_enabled=True
    )
    _provision(workspace, "main_goal_default", "MainGoal")
    editor = _auth_ctx(
        tenant_id=tenant.id,
        user_id=user.id,
        workspace_id=workspace.id,
        roles=("editor",),
    )
    approver = _auth_ctx(
        tenant_id=tenant.id,
        user_id=user.id,
        workspace_id=workspace.id,
        roles=("approver",),
    )
    created = MainGoalService().create_manual(
        workspace_id=workspace.id, content="DATA-03 main goal.", ctx=editor
    )
    return tenant, workspace, user, editor, approver, created


def test_main_goal_approve_stale_expected_version_is_a_conflict(main_goal_env):
    tenant, workspace, _user, _editor, approver, created = main_goal_env
    main_goal_id = uuid.UUID(created["id"])
    current = _engine_version(tenant.id, main_goal_id, "MainGoal", workspace.id)

    with pytest.raises(OptimisticLockError):
        MainGoalService().approve(
            main_goal_id,
            approver,
            change_reason="stale approval",
            expected_version=current + 1,
        )


def test_main_goal_approve_current_expected_version_succeeds(main_goal_env):
    tenant, workspace, _user, _editor, approver, created = main_goal_env
    main_goal_id = uuid.UUID(created["id"])
    current = _engine_version(tenant.id, main_goal_id, "MainGoal", workspace.id)

    result = MainGoalService().approve(
        main_goal_id,
        approver,
        change_reason="approved",
        expected_version=current,
    )

    assert result["status"] == "Freigegeben"


# ---------------------------------------------------------------------------
# GoalService.archive / GoalService.restore
# ---------------------------------------------------------------------------


@pytest.fixture
def goal_env():
    tenant, workspace, user = _new_tenant_workspace_user(
        "data03-goal", goals_enabled=True
    )
    _provision(workspace, "goal_default", "Goal")
    editor = _auth_ctx(
        tenant_id=tenant.id,
        user_id=user.id,
        workspace_id=workspace.id,
        roles=("editor",),
    )
    approver = _auth_ctx(
        tenant_id=tenant.id,
        user_id=user.id,
        workspace_id=workspace.id,
        roles=("approver",),
    )
    created = GoalService().create_version(
        workspace_id=workspace.id,
        title="DATA-03 goal",
        description="",
        lineage_id=None,
        ctx=editor,
    )
    return tenant, workspace, user, editor, approver, created


def test_goal_archive_stale_expected_version_is_a_conflict(goal_env):
    tenant, workspace, _user, _editor, approver, created = goal_env
    goal_id = uuid.UUID(created["id"])
    current = _engine_version(tenant.id, goal_id, "Goal", workspace.id)

    with pytest.raises(OptimisticLockError):
        GoalService().archive(
            goal_id,
            approver,
            change_reason="archive attempt",
            expected_version=current + 1,
        )


def test_goal_archive_current_expected_version_succeeds(goal_env):
    tenant, workspace, _user, _editor, approver, created = goal_env
    goal_id = uuid.UUID(created["id"])
    current = _engine_version(tenant.id, goal_id, "Goal", workspace.id)

    goal = GoalService().archive(
        goal_id,
        approver,
        change_reason="archive",
        expected_version=current,
    )

    assert goal.status == "Archiviert"


def test_goal_restore_stale_expected_version_is_a_conflict(goal_env):
    tenant, workspace, _user, _editor, approver, created = goal_env
    goal_id = uuid.UUID(created["id"])
    svc = GoalService()
    # Archive first: the restored revision is genuinely stale afterwards.
    svc.archive(goal_id, approver, change_reason="archive")
    stale = _engine_version(tenant.id, goal_id, "Goal", workspace.id) - 1

    with pytest.raises(OptimisticLockError):
        svc.restore(
            goal_id,
            approver,
            change_reason="restore attempt",
            expected_version=stale,
        )


def test_goal_restore_current_expected_version_succeeds(goal_env):
    tenant, workspace, _user, _editor, approver, created = goal_env
    goal_id = uuid.UUID(created["id"])
    svc = GoalService()
    svc.archive(goal_id, approver, change_reason="archive")
    current = _engine_version(tenant.id, goal_id, "Goal", workspace.id)

    goal = svc.restore(
        goal_id,
        approver,
        change_reason="restore",
        expected_version=current,
    )

    assert goal.status == "Entwurf"
