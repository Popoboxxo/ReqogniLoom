"""Slice 2 (Tabellenansicht) — ``BulkUpdateService.bulk_transition``.

The contract under test (plan ``2026-11-04-tabellenansicht-neu.md``, task 2.1
and spec §3.2):

* every id runs through :class:`application.workflow_facade.WorkflowFacade` —
  the workspace's graph decides per row whether the edge exists, so a mixed
  batch moves the reachable rows and reports the unreachable ones;
* **partial success** is the specified behaviour: one refusal neither aborts nor
  rolls back the others (the opposite of ``bulk_update``), and each refusal
  carries ``index``, ``artifact_id``, ``code`` and ``message``;
* the id list is bounded (1..``MAX_TRANSITION_IDS``) — empty, duplicate and 101
  are request defects (400-class), as is an empty ``change_reason``;
* the workspace is derived from the artifacts: ids of two workspaces reject the
  whole request, a foreign tenant's id is a per-row ``NOT_FOUND``;
* the role fence is evaluated **in the derived workspace**, not against the
  tenant-wide role union the transport hands in — the exact ADR-011 hole an
  editor of workspace B would otherwise use to transition A's rows;
* ``status`` is never written directly: the only writer is the facade.
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from application.base import PermissionDeniedError, ValidationError
from application.bulk_update_service import (
    MAX_TRANSITION_IDS,
    BulkUpdateService,
)
from application.requirement_service import RequirementService
from auth_tenancy.context import AuthContext
from auth_tenancy.models import ROLE_APPROVER, ROLE_EDITOR, UserRole
from persistence.models import Requirement, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db

#: Extended-preset requirement edges used below.
DRAFT = "draft"
IN_REVIEW = "in_review"
APPROVED = "approved"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant() -> Tenant:
    return Tenant.objects.create(name="Bulk Transition", slug="bulk-transition")


def _make_workspace(tenant: Tenant, name: str) -> Workspace:
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=name, preset={"name": "extended"}
        )
        create_default_workflow(
            workspace_id=workspace.id,
            preset="extended",
            item_type="Requirement",
            tenant_id=tenant.id,
        )
        return workspace
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    return _make_workspace(tenant, "Transition Workspace")


@pytest.fixture
def sibling_workspace(tenant: Tenant) -> Workspace:
    """A second workspace of the same tenant (the mixed-workspace case)."""
    return _make_workspace(tenant, "Sibling Transition Workspace")


def _user(tenant: Tenant, username: str) -> User:
    return User.objects.create(
        username=username, email=f"{username}@example.com", tenant=tenant
    )


def _context(user: User, *roles: str) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=user.tenant_id,
        # Deliberately the *tenant-wide* union a workspace-less route receives:
        # the service must narrow it to the derived workspace itself.
        active_roles=tuple(roles),
        auth_method="test",
        tenant_name=user.tenant.name,
    )


def _grant(user: User, *pairs: tuple[Workspace, str]) -> None:
    """Persist the ``UserRole`` rows the workspace role fence resolves.

    The service deliberately re-resolves the caller's roles *in the derived
    workspace* (``AuthorizationService.active_roles_for``), so a context whose
    ``active_roles`` are merely set would be denied — exactly the tenant-wide
    union shortcut this slice closes.
    """
    TenantContext.set_tenant(user.tenant_id)
    try:
        for workspace, role in pairs:
            UserRole.objects.create(
                tenant_id=user.tenant_id,
                user=user,
                workspace=workspace,
                role=role,
            )
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def editor_ctx(
    tenant: Tenant, workspace: Workspace, sibling_workspace: Workspace
) -> AuthContext:
    user = _user(tenant, "transition-editor")
    _grant(user, (workspace, ROLE_EDITOR), (sibling_workspace, ROLE_EDITOR))
    return _context(user, "editor")


@pytest.fixture
def approver_ctx(
    tenant: Tenant, workspace: Workspace, sibling_workspace: Workspace
) -> AuthContext:
    user = _user(tenant, "transition-approver")
    _grant(
        user,
        (workspace, ROLE_APPROVER),
        (workspace, ROLE_EDITOR),
        (sibling_workspace, ROLE_APPROVER),
    )
    return _context(user, "approver", "editor")


@pytest.fixture
def service() -> BulkUpdateService:
    return BulkUpdateService()


def _requirement(workspace: Workspace, ctx: AuthContext, title: str) -> Requirement:
    """A requirement that satisfies the extended preset's approval fields.

    Without ``description``/``acceptance_criteria``/``verification_method`` the
    extended preset refuses ``in_review -> approved`` on mandatory-field grounds,
    which would mask the role/graph cases these tests are about.
    """
    return RequirementService().create_requirement(
        workspace_id=workspace.id,
        title=title,
        description="System shall behave",
        acceptance_criteria="Given X, when Y, then Z",
        verification_method="Inspection",
        ctx=ctx,
    )


def _state_of(requirement: Requirement) -> str:
    """Return the workflow state the engine recorded for *requirement*."""
    return WorkflowItemState.objects.get(
        item_id=requirement.id, item_type="Requirement"
    ).current_state


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_transitions_every_id_and_reports_the_new_state(
    service, workspace, editor_ctx
) -> None:
    first = _requirement(workspace, editor_ctx, "Req A")
    second = _requirement(workspace, editor_ctx, "Req B")

    result = service.bulk_transition(
        editor_ctx,
        "Requirement",
        [first.artifact_id, second.artifact_id],
        IN_REVIEW,
        "ready for review",
    )

    assert result.ok is True
    assert result.failed == ()
    assert [set(row) for row in result.transitioned] == [
        {"artifact_id", "state"},
        {"artifact_id", "state"},
    ]
    assert [row["artifact_id"] for row in result.transitioned] == [
        str(first.artifact_id),
        str(second.artifact_id),
    ]
    assert [row["state"] for row in result.transitioned] == [IN_REVIEW, IN_REVIEW]
    assert _state_of(first) == IN_REVIEW
    assert _state_of(second) == IN_REVIEW
    # The payload is what both transports publish, JSON primitives only.
    assert result.to_dict() == {
        "transitioned": list(result.transitioned),
        "failed": [],
    }


# ---------------------------------------------------------------------------
# Partial success
# ---------------------------------------------------------------------------


def test_unreachable_target_is_reported_while_the_others_move(
    service, workspace, editor_ctx, approver_ctx
) -> None:
    first = _requirement(workspace, editor_ctx, "Draft A")
    approved = _requirement(workspace, editor_ctx, "Approved B")
    second = _requirement(workspace, editor_ctx, "Draft C")
    # Put one row where the extended graph has no edge back to ``in_review``.
    service.bulk_transition(
        editor_ctx, "Requirement", [approved.artifact_id], IN_REVIEW, "into review"
    )
    approval = service.bulk_transition(
        approver_ctx, "Requirement", [approved.artifact_id], APPROVED, "approved"
    )
    assert approval.failed == ()

    result = service.bulk_transition(
        editor_ctx,
        "Requirement",
        [first.artifact_id, approved.artifact_id, second.artifact_id],
        IN_REVIEW,
        "batch review",
    )

    assert [row["artifact_id"] for row in result.transitioned] == [
        str(first.artifact_id),
        str(second.artifact_id),
    ]
    assert len(result.failed) == 1
    failure = result.failed[0]
    assert failure["index"] == 1
    assert failure["artifact_id"] == str(approved.artifact_id)
    assert failure["code"] == "VALIDATION_ERROR"
    assert failure["message"]
    # The valid rows really moved (no all-or-nothing rollback).
    assert _state_of(first) == IN_REVIEW
    assert _state_of(second) == IN_REVIEW
    assert _state_of(approved) == APPROVED


def test_permission_denied_row_is_forbidden_and_others_move(
    service, workspace, editor_ctx, approver_ctx
) -> None:
    """``in_review -> approved`` needs an approver: an editor's row is refused."""
    first = _requirement(workspace, editor_ctx, "Review A")
    second = _requirement(workspace, editor_ctx, "Review B")
    service.bulk_transition(
        editor_ctx,
        "Requirement",
        [first.artifact_id, second.artifact_id],
        IN_REVIEW,
        "into review",
    )

    editor_bulk = service.bulk_transition(
        editor_ctx,
        "Requirement",
        [first.artifact_id, second.artifact_id],
        APPROVED,
        "approve please",
    )

    assert editor_bulk.transitioned == ()
    assert [row["code"] for row in editor_bulk.failed] == [
        "FORBIDDEN",
        "FORBIDDEN",
    ]
    assert _state_of(first) == IN_REVIEW

    approver_bulk = service.bulk_transition(
        approver_ctx,
        "Requirement",
        [first.artifact_id, second.artifact_id],
        APPROVED,
        "approved",
    )
    assert [row["code"] for row in approver_bulk.failed] == []
    assert _state_of(first) == APPROVED


def test_status_is_never_written_directly(
    service, workspace, editor_ctx
) -> None:
    """The only writer is the facade — pinned by spying on its public method."""
    from application.workflow_facade import WorkflowFacade

    requirement = _requirement(workspace, editor_ctx, "Guarded")
    original = WorkflowFacade.transition
    calls: list[tuple[tuple, dict]] = []

    def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return original(self, *args, **kwargs)

    with patch.object(WorkflowFacade, "transition", spy):
        result = service.bulk_transition(
            editor_ctx, "Requirement", [requirement.artifact_id], IN_REVIEW, "go"
        )

    assert result.ok is True
    assert len(calls) == 1
    args, kwargs = calls[0]
    # The facade received the *typed row* id, not the artifact id, plus the
    # derived workspace and the requested state.
    assert args[0] == requirement.id
    assert args[1] == IN_REVIEW
    assert kwargs["item_type"] == "Requirement"
    assert kwargs["workspace_id"] == workspace.id
    assert _state_of(requirement) == IN_REVIEW


# ---------------------------------------------------------------------------
# Request-level defects
# ---------------------------------------------------------------------------


def test_101_ids_are_rejected(service, workspace, editor_ctx) -> None:
    requirement = _requirement(workspace, editor_ctx, "Many")
    ids = [requirement.artifact_id]

    with pytest.raises(ValidationError) as exc:
        service.bulk_transition(
            editor_ctx, "Requirement", ids * (MAX_TRANSITION_IDS + 1), IN_REVIEW, "why"
        )

    assert str(MAX_TRANSITION_IDS) in str(exc.value)
    assert _state_of(requirement) == DRAFT


def test_empty_ids_are_rejected(service, workspace, editor_ctx) -> None:
    with pytest.raises(ValidationError):
        service.bulk_transition(editor_ctx, "Requirement", [], IN_REVIEW, "why")


def test_duplicate_ids_are_rejected(service, workspace, editor_ctx) -> None:
    requirement = _requirement(workspace, editor_ctx, "Twice")

    with pytest.raises(ValidationError) as exc:
        service.bulk_transition(
            editor_ctx,
            "Requirement",
            [requirement.artifact_id, requirement.artifact_id],
            IN_REVIEW,
            "why",
        )

    assert "repeats" in str(exc.value)
    assert _state_of(requirement) == DRAFT


@pytest.mark.parametrize("reason", ["", "   "])
def test_empty_change_reason_is_rejected(
    service, workspace, editor_ctx, reason: str
) -> None:
    requirement = _requirement(workspace, editor_ctx, "No reason")

    with pytest.raises(ValidationError) as exc:
        service.bulk_transition(
            editor_ctx, "Requirement", [requirement.artifact_id], IN_REVIEW, reason
        )

    assert "change_reason" in str(exc.value)
    assert _state_of(requirement) == DRAFT


def test_unknown_item_type_is_rejected(service, workspace, editor_ctx) -> None:
    requirement = _requirement(workspace, editor_ctx, "Typo")

    with pytest.raises(ValidationError):
        service.bulk_transition(
            editor_ctx, "Requirements", [requirement.artifact_id], IN_REVIEW, "why"
        )


def test_ids_from_two_workspaces_are_rejected(
    service, workspace, sibling_workspace, editor_ctx
) -> None:
    here = _requirement(workspace, editor_ctx, "Here")
    there = _requirement(sibling_workspace, editor_ctx, "There")

    with pytest.raises(ValidationError) as exc:
        service.bulk_transition(
            editor_ctx,
            "Requirement",
            [here.artifact_id, there.artifact_id],
            IN_REVIEW,
            "why",
        )

    assert str(there.artifact_id) in str(exc.value)
    assert _state_of(here) == DRAFT
    assert _state_of(there) == DRAFT


# ---------------------------------------------------------------------------
# Per-row resolution
# ---------------------------------------------------------------------------


def test_foreign_tenant_or_missing_id_reports_not_found(
    service, workspace, editor_ctx
) -> None:
    requirement = _requirement(workspace, editor_ctx, "Exists")
    missing = uuid4()

    result = service.bulk_transition(
        editor_ctx,
        "Requirement",
        [requirement.artifact_id, missing],
        IN_REVIEW,
        "mixed",
    )

    assert [row["artifact_id"] for row in result.transitioned] == [
        str(requirement.artifact_id)
    ]
    assert len(result.failed) == 1
    assert result.failed[0]["index"] == 1
    assert result.failed[0]["code"] == "NOT_FOUND"
    assert str(missing) in result.failed[0]["message"]


def test_only_missing_ids_are_all_not_found(
    service, workspace, editor_ctx
) -> None:
    missing = uuid4()

    result = service.bulk_transition(
        editor_ctx, "Requirement", [missing], IN_REVIEW, "nothing"
    )

    assert result.transitioned == ()
    assert [row["code"] for row in result.failed] == ["NOT_FOUND"]


def test_artifact_of_another_type_is_a_validation_error(
    service, workspace, editor_ctx
) -> None:
    from application.stakeholder_need_service import StakeholderNeedService

    need_answer = StakeholderNeedService().create(
        editor_ctx, workspace.id, title="A need"
    )
    requirement = _requirement(workspace, editor_ctx, "A requirement")

    result = service.bulk_transition(
        editor_ctx,
        "Requirement",
        [requirement.artifact_id, need_answer.artifact_id],
        IN_REVIEW,
        "type mix",
    )

    assert [row["artifact_id"] for row in result.transitioned] == [
        str(requirement.artifact_id)
    ]
    assert result.failed[0]["index"] == 1
    assert result.failed[0]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Auth in the derived workspace
# ---------------------------------------------------------------------------


def test_viewer_role_is_denied(service, workspace, tenant) -> None:
    writer = _user(tenant, "transition-writer")
    _grant(writer, (workspace, ROLE_EDITOR))
    requirement = _requirement(workspace, _context(writer, "editor"), "Guarded")
    viewer_ctx = _context(_user(tenant, "transition-viewer"), "viewer")

    with pytest.raises(PermissionDeniedError):
        service.bulk_transition(
            viewer_ctx, "Requirement", [requirement.artifact_id], IN_REVIEW, "why"
        )

    assert _state_of(requirement) == DRAFT


def test_editor_of_another_workspace_cannot_transition_these_rows(
    service, workspace, sibling_workspace, tenant
) -> None:
    """The tenant-wide role union must not leak across workspaces (ADR-011)."""
    owner = _user(tenant, "transition-owner")
    _grant(owner, (workspace, ROLE_EDITOR))
    requirement_ctx = _context(owner, "editor")
    requirement = _requirement(workspace, requirement_ctx, "Workspace A row")

    outsider = _user(tenant, "transition-outsider")
    _grant(outsider, (sibling_workspace, ROLE_EDITOR))
    outsider_ctx = _context(outsider, "editor")

    with pytest.raises(PermissionDeniedError):
        service.bulk_transition(
            outsider_ctx, "Requirement", [requirement.artifact_id], IN_REVIEW, "why"
        )

    assert _state_of(requirement) == DRAFT
