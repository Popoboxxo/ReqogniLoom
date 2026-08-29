"""SA-16 regressions: MainGoal.sequence_number must be unique per workspace.

Systemaudit 2026-08-27 §4.2 #6. ``MainGoalService._create_row`` derived the next
version with ``MAX(sequence_number) + 1`` and immediately inserted, with no lock
and no constraint. Two concurrent creates read the same maximum and both wrote
it, leaving two rows claiming to be the same version — and because
``get_current`` / ``list_versions`` resolve the valid MainGoal purely by highest
``sequence_number``, "which MainGoal is current" became non-deterministic.

Covered here:
  * the database rejects the duplicate (the authoritative guard),
  * the service absorbs that rejection and allocates the next free number
    instead of surfacing a 500,
  * the retry is bounded rather than an infinite spin.

req_id : REQ-L2-TE-020
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from django.db import IntegrityError, transaction

from application.main_goal_service import MainGoalService
from application.models import MainGoal
from persistence.models import Artifact, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db(transaction=True)


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    ctx.has_role = lambda role: role in ctx.active_roles
    return ctx


@pytest.fixture
def workspace():
    tenant = Tenant.objects.create(name="SA-16 Tenant", slug="sa16-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        yield Workspace.objects.create(
            tenant=tenant, name="SA-16 WS", goals_enabled=True
        )
    finally:
        TenantContext.clear_tenant()


def _raw_insert(workspace, sequence_number: int) -> MainGoal:
    """Insert a MainGoal bypassing the service (test-fixture shortcut)."""
    artifact = Artifact.objects.create(
        tenant=workspace.tenant, workspace=workspace, artifact_type="MainGoal"
    )
    return MainGoal.objects.create(
        artifact=artifact,
        tenant_id=workspace.tenant_id,
        workspace_id=workspace.id,
        sequence_number=sequence_number,
        content=f"v{sequence_number}",
        source="manual",
        generated_from_goal_ids=[],
        status="Entwurf",
    )


def test_duplicate_sequence_number_is_rejected_by_the_database(workspace) -> None:
    """The UNIQUE constraint is the guard the service's retry depends on.

    If it were ever dropped, the retry below would be dead code and the original
    corruption would silently return.
    """
    _raw_insert(workspace, 1)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_insert(workspace, 1)


def test_same_sequence_number_is_allowed_in_a_different_workspace(workspace) -> None:
    """The constraint is scoped per workspace, not global.

    Every workspace's version chain starts at 1; a global unique index would
    make the second workspace's first MainGoal impossible.
    """
    _raw_insert(workspace, 1)

    other = Workspace.objects.create(
        tenant=workspace.tenant, name="SA-16 WS 2", goals_enabled=True
    )
    assert _raw_insert(other, 1).sequence_number == 1


def test_create_retries_onto_the_next_free_number_after_losing_the_race(
    workspace, monkeypatch
) -> None:
    """A create that loses the race allocates v2 instead of failing with a 500.

    Reproduces the interleaving without threads: the rival's v1 is committed
    between our MAX read and our INSERT, which is exactly what the stale read
    looks like from inside the loop.
    """
    # The rival's v1 is already committed...
    _raw_insert(workspace, 1)

    # ...but our first MAX read does not see it yet, so we compute 1 as free and
    # the INSERT hits uq_main_goal_workspace_sequence for real.
    real_filter = MainGoal.objects.filter
    first_read = {"done": False}

    def _first_read_misses(*args, **kwargs):
        queryset = real_filter(*args, **kwargs)
        if not first_read["done"] and kwargs.get("workspace_id") == workspace.id:
            first_read["done"] = True
            return queryset.none()
        return queryset

    monkeypatch.setattr(MainGoal.objects, "filter", _first_read_misses)

    result = MainGoalService().create_manual(
        workspace_id=workspace.id,
        content="loser of the race",
        ctx=_ctx(workspace.tenant_id),
    )

    assert first_read["done"], "the MAX-read interception never fired"
    assert result["sequence_number"] == 2, (
        "the losing create must take the next free number, not fail"
    )
    numbers = sorted(
        MainGoal.objects.filter(workspace_id=workspace.id).values_list(
            "sequence_number", flat=True
        )
    )
    assert numbers == [1, 2]


def test_retry_is_bounded_and_reraises(workspace, monkeypatch) -> None:
    """Permanent contention surfaces the IntegrityError instead of spinning forever."""
    import application.main_goal_service as module

    monkeypatch.setattr(module, "_SEQUENCE_ALLOCATION_ATTEMPTS", 3)

    attempts = {"n": 0}

    def _always_collide(self, *args, **kwargs):
        attempts["n"] += 1
        raise IntegrityError(
            'duplicate key value violates unique constraint '
            '"uq_main_goal_workspace_sequence"'
        )

    monkeypatch.setattr(MainGoal, "save", _always_collide)

    with pytest.raises(IntegrityError):
        MainGoalService().create_manual(
            workspace_id=workspace.id,
            content="never wins",
            ctx=_ctx(workspace.tenant_id),
        )

    assert attempts["n"] == 3, "the loop must stop at the configured attempt cap"


def test_sequential_creates_still_number_consecutively(workspace) -> None:
    """No-contention path is unchanged: v1, v2, v3."""
    service = MainGoalService()
    ctx = _ctx(workspace.tenant_id)

    numbers = [
        service.create_manual(
            workspace_id=workspace.id, content=f"goal {i}", ctx=ctx
        )["sequence_number"]
        for i in range(3)
    ]
    assert numbers == [1, 2, 3]
