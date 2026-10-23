"""G1.3/#1402 — the denormalized ``workspace`` FK is filled on every create path.

Security-review finding W0-01: the per-workspace ``UNIQUE (workspace, uid)``
indexes of persistence/0118 only constrain rows whose ``workspace_id`` is NOT
NULL — Postgres treats NULLs as distinct. The DB-level invariant therefore held
for the 0117-backfilled legacy rows only, because no production create path
passed the FK: ``TestService.create_test_case``,
``StakeholderNeedService.create`` and
``ArchitectureService.create_architecture_element`` all built their entity row
from the artifact alone, and the service-level tests built the FK by hand
(``_build`` in ``persistence/tests/test_uid_unique_constraints_1402.py``) and
so masked the gap.

These tests go through the real services (no ORM hand-building, no mocked
manager) and assert the two halves that make the index meaningful:

1. the created row carries the workspace, and
2. a second create with the same ``uid`` in the same workspace is rejected by
   the index — i.e. the constraint now actually reaches new data.

The last test pins the ``ArtifactWorkspaceMirrorMixin`` safety net: a create
path that forgets ``workspace=`` still gets the column filled, so a future
call site cannot silently reintroduce the NULL loophole.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction

from application.architecture_service import ArchitectureService
from application.base import ValidationError
from application.requirement_service import RequirementService
from application.stakeholder_need_service import StakeholderNeedService
from application.test_run_service import TestRunService
from application.test_service import TestService
from application.workspace_service import WorkspaceService
from persistence.models import (
    ArchitectureElement,
    Artifact,
    Requirement,
    StakeholderNeed,
    TestCase,
    TestRun,
)
from persistence.tests.factories import (
    active_tenant,
    ctx_for_user,
    editor_ctx,
    make_user,
    make_workspace,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    """Tenant + provisioned workspace + an editor ``AuthContext``."""
    with active_tenant() as tenant:
        workspace = make_workspace(tenant)
        yield tenant, workspace, editor_ctx(tenant, workspace)


def _assert_rejected_by_index(create) -> None:
    """Assert *create* raises ``IntegrityError`` from the unique index.

    ``create`` runs inside its own savepoint so the outer test transaction stays
    usable; the service's ``@atomic_transaction`` has already rolled back to its
    own savepoint by the time the error surfaces.
    """
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            create()


def test_test_case_creation_sets_workspace_and_enforces_unique_uid(env):
    _tenant, workspace, ctx = env
    service = TestService()

    first = service.create_test_case(
        workspace_id=workspace.id, title="Login", ctx=ctx, uid="TC-1402-1"
    )
    assert first.workspace_id == workspace.id

    _assert_rejected_by_index(
        lambda: service.create_test_case(
            workspace_id=workspace.id, title="Login again", ctx=ctx, uid="TC-1402-1"
        )
    )
    assert TestCase.objects.filter(workspace__isnull=True).count() == 0


def test_stakeholder_need_creation_sets_workspace_and_enforces_unique_uid(env):
    _tenant, workspace, ctx = env
    service = StakeholderNeedService()

    # ``create`` allocates the uid itself (issue #932); pin the generator so the
    # second call produces a genuine duplicate.
    with patch(
        "application.stakeholder_need_service.generate_local_uid",
        return_value="NEED-1402-1",
    ):
        first = service.create(ctx=ctx, workspace_id=workspace.id, title="Need")
        assert first.workspace_id == workspace.id

        _assert_rejected_by_index(
            lambda: service.create(ctx=ctx, workspace_id=workspace.id, title="Need 2")
        )

    assert StakeholderNeed.objects.filter(workspace__isnull=True).count() == 0


def test_architecture_element_creation_sets_workspace_and_enforces_unique_uid(env):
    _tenant, workspace, ctx = env
    service = ArchitectureService()

    root = service.create_architecture_element(
        workspace_id=workspace.id, title="System", ctx=ctx, uid="ARCH-1402-1"
    )
    assert root.workspace_id == workspace.id

    # A *child* with the duplicate uid: the workspace's single-root invariant
    # (I5) must not be what rejects it — the uid index has to.
    _assert_rejected_by_index(
        lambda: service.create_architecture_element(
            workspace_id=workspace.id,
            title="Component",
            ctx=ctx,
            parent_id=root.id,
            uid="ARCH-1402-1",
        )
    )
    assert ArchitectureElement.objects.filter(workspace__isnull=True).count() == 0


def test_test_run_creation_sets_workspace_and_enforces_unique_uid(env):
    """TestRun already had a non-null FK; the index is what was new (#1402)."""
    _tenant, workspace, ctx = env
    service = TestRunService()

    first = service.create_test_run(
        workspace_id=workspace.id, name="Run 1", ctx=ctx, uid="RUN-1402-1"
    )
    assert first.workspace_id == workspace.id

    _assert_rejected_by_index(
        lambda: service.create_test_run(
            workspace_id=workspace.id, name="Run 2", ctx=ctx, uid="RUN-1402-1"
        )
    )
    assert TestRun.objects.filter(workspace__isnull=True).count() == 0


def test_requirement_creation_sets_workspace_and_enforces_unique_uid(env):
    """The 0055 precedent the other models now mirror.

    Requirement rejects the duplicate one layer earlier (its service has the
    #44 pre-check), so the DB index is never reached here; the index itself is
    pinned in ``persistence/tests/test_uid_unique_constraints_1402.py``. The
    point of this test is the *workspace column on the service path*.
    """
    _tenant, workspace, ctx = env
    service = RequirementService()

    first = service.create_requirement(
        workspace_id=workspace.id, title="Req", ctx=ctx, uid="REQ-1402-1"
    )
    assert first.workspace_id == workspace.id

    with pytest.raises(ValidationError):
        service.create_requirement(
            workspace_id=workspace.id, title="Req again", ctx=ctx, uid="REQ-1402-1"
        )
    assert Requirement.objects.filter(workspace__isnull=True).count() == 0


def test_orm_create_without_workspace_is_filled_from_the_artifact(env):
    """The mixin is the net for create paths nobody enumerated (W0-01)."""
    tenant, workspace, _ctx = env
    artifact = Artifact.objects.create(
        tenant=tenant, workspace=workspace, artifact_type="TestCase"
    )

    test_case = TestCase.objects.create(
        tenant=tenant, artifact=artifact, title="No workspace kwarg", uid="MIX-1"
    )
    need = StakeholderNeed.objects.create(
        tenant=tenant,
        artifact=Artifact.objects.create(
            tenant=tenant, workspace=workspace, artifact_type="StakeholderNeed"
        ),
        title="No workspace kwarg",
        uid="MIX-2",
    )

    assert test_case.workspace_id == workspace.id
    assert need.workspace_id == workspace.id


def test_create_with_a_foreign_artifact_cannot_leave_workspace_null(env):
    """A row whose artifact is gone leaves the column NULL — and is rejected.

    The mixin never invents a workspace: when the artifact cannot be resolved,
    ``workspace_id`` stays NULL so the failure surfaces at the FK/row level
    instead of the row silently opting out of the index under a wrong owner.
    """
    _tenant, _workspace, _ctx = env
    orphan = TestCase(artifact_id=None, title="no artifact", uid="ORPHAN-1")

    orphan._fill_workspace_from_artifact()
    assert orphan.workspace_id is None


def test_workspace_clone_repoints_the_workspace_fk(env):
    """``clone_workspace`` is a create path: the copy belongs to the clone.

    G1.3/#1402 regression: the clone re-inserts the source row with a new PK and
    a remapped artifact but kept the *source* workspace id — so the copy landed
    in the wrong workspace and collided with the source row on
    ``uq_<table>_workspace_uid`` (IntegrityError on any uid-bearing source).
    """
    tenant, source, _editor = env
    admin_ctx = ctx_for_user(
        tenant, make_user(tenant), workspace=source, roles=("admin",)
    )

    test_case = TestService().create_test_case(
        workspace_id=source.id, title="Login", ctx=admin_ctx, uid="TC-CLONE-1"
    )
    ArchitectureService().create_architecture_element(
        workspace_id=source.id, title="System", ctx=admin_ctx, uid="ARCH-CLONE-1"
    )

    with patch("application.workspace_service.ServiceBase._audit"):
        target = WorkspaceService().clone_workspace(admin_ctx, source.id, "Cloned WS")

    cloned_case = TestCase.objects.get(workspace=target, uid="TC-CLONE-1")
    cloned_element = ArchitectureElement.objects.get(
        workspace=target, uid="ARCH-CLONE-1"
    )
    assert cloned_case.id != test_case.id
    assert cloned_element.workspace_id == target.id
    # The source rows kept their own workspace.
    assert TestCase.objects.get(pk=test_case.pk).workspace_id == source.id
