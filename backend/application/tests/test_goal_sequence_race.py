"""AUD-2026-09-281: Goal.sequence_number must be unique per lineage.

``GoalService.create_version`` derives the next version with a read-then-write
(``MAX(sequence_number) + 1``) with no lock on the *insert* it is about to make.
Two concurrent creates in the same lineage could read the same maximum and both
persist it, silently producing two rows claiming to be "v2" -- and because
``list_versions``/``list_current`` resolve versions by that number, "which Goal
is current" became non-deterministic.

The application-side guard is only a lock on the lineage's current row, which
cannot serialise the first-ever insert (no row to lock) nor a concurrent INSERT
of the *next* row. The authoritative guard is therefore the DB constraint
``uq_goal_lineage_sequence (lineage_id, sequence_number)``; the service catches
its ``IntegrityError`` and retries with a freshly read maximum.

Covered here:
  * the constraint is present in the live schema (it is the guard the retry
    depends on),
  * the database rejects a duplicate (lineage_id, sequence_number),
  * the service absorbs a lost race and allocates the next free number,
  * the retry is bounded rather than an infinite spin,
  * the no-contention path is unchanged.

req_id : REQ-L2-TE-020
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from django.db import IntegrityError, connection, transaction

from application.base import NotFoundError
from application.goal_service import GoalService
from application.models import Goal
from persistence.models import Artifact, Tenant, Workspace
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db(transaction=True)

_CONSTRAINT = "uq_goal_lineage_sequence"


def _ctx(tenant_id):
    ctx = MagicMock()
    ctx.tenant_id = tenant_id
    ctx.user_id = uuid.uuid4()
    ctx.active_roles = ("editor",)
    ctx.has_role = lambda role: role in ctx.active_roles
    return ctx


@pytest.fixture
def workspace():
    tenant = Tenant.objects.create(name="AUD-281 Tenant", slug="aud281-tenant")
    TenantContext.set_tenant(tenant.id)
    try:
        yield Workspace.objects.create(
            tenant=tenant, name="AUD-281 WS", goals_enabled=True
        )
    finally:
        TenantContext.clear_tenant()


def _raw_insert(workspace, lineage_id, sequence_number: int) -> Goal:
    """Insert a Goal bypassing the service (constraint test shortcut)."""
    artifact = Artifact.objects.create(
        tenant=workspace.tenant, workspace=workspace, artifact_type="Goal"
    )
    return Goal.objects.create(
        artifact=artifact,
        tenant_id=workspace.tenant_id,
        workspace_id=workspace.id,
        lineage_id=lineage_id,
        sequence_number=sequence_number,
        title=f"v{sequence_number}",
        description="",
    )


def test_unique_constraint_is_present_in_the_live_schema():
    """The DB constraint is the authoritative guard the retry depends on."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s", [_CONSTRAINT]
        )
        rows = cur.fetchall()
    assert rows, f"{_CONSTRAINT} is missing from the live schema"
    indexdef = rows[0][0]
    assert "UNIQUE" in indexdef.upper()
    assert "lineage_id" in indexdef
    assert "sequence_number" in indexdef


def test_duplicate_sequence_number_is_rejected_by_the_database(workspace) -> None:
    """The constraint must actually reject a duplicate -- otherwise the retry
    below would be dead code and the original corruption would return."""
    lineage_id = uuid.uuid4()
    _raw_insert(workspace, lineage_id, 1)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _raw_insert(workspace, lineage_id, 1)


def test_same_sequence_number_is_allowed_in_a_different_lineage(workspace) -> None:
    """The constraint is scoped per lineage, not global: every lineage's chain
    starts at 1."""
    _raw_insert(workspace, uuid.uuid4(), 1)
    assert _raw_insert(workspace, uuid.uuid4(), 1).sequence_number == 1


class _StaleFirstRead:
    """Proxy that makes the first ``.first()`` read miss a committed row.

    Reproduces the interleaving without threads: the rival's row is committed
    between our MAX read and our INSERT, which is exactly what the stale read
    looks like from inside the retry loop.
    """

    def __init__(self, queryset, stale_row, state):
        self._queryset = queryset
        self._stale_row = stale_row
        self._state = state

    def filter(self, *args, **kwargs):
        return _StaleFirstRead(
            self._queryset.filter(*args, **kwargs), self._stale_row, self._state
        )

    def order_by(self, *args, **kwargs):
        return _StaleFirstRead(
            self._queryset.order_by(*args, **kwargs), self._stale_row, self._state
        )

    def first(self):
        if not self._state["done"]:
            self._state["done"] = True
            return self._stale_row
        return self._queryset.first()


def test_create_retries_onto_the_next_free_number_after_losing_the_race(
    workspace, monkeypatch
) -> None:
    """A create that loses the race allocates v3 instead of failing with a 500.

    The lineage already holds v1 and v2; the first MAX read is forced to see
    only v1, so the INSERT targets v2 and collides for real. The retry re-reads
    the true maximum and lands on v3.
    """
    svc = GoalService()
    ctx = _ctx(workspace.tenant_id)
    lineage_id = uuid.UUID(
        svc.create_version(
            workspace_id=workspace.id, title="Goal A", description="", ctx=ctx
        )["lineage_id"]
    )
    svc.create_version(
        workspace_id=workspace.id,
        title="Goal A v2",
        description="",
        lineage_id=lineage_id,
        ctx=ctx,
    )
    stale_v1 = Goal.objects.get(lineage_id=lineage_id, sequence_number=1)

    real_select_for_update = Goal.objects.select_for_update
    state = {"done": False}

    def _stale_select_for_update(*args, **kwargs):
        return _StaleFirstRead(
            real_select_for_update(*args, **kwargs), stale_v1, state
        )

    monkeypatch.setattr(
        Goal.objects, "select_for_update", _stale_select_for_update
    )

    result = svc.create_version(
        workspace_id=workspace.id,
        title="loser of the race",
        description="",
        lineage_id=lineage_id,
        ctx=ctx,
    )

    assert state["done"], "the stale MAX-read interception never fired"
    assert result["sequence_number"] == 3, (
        "the losing create must take the next free number, not fail"
    )
    numbers = sorted(
        Goal.objects.filter(lineage_id=lineage_id).values_list(
            "sequence_number", flat=True
        )
    )
    assert numbers == [1, 2, 3]


def test_retry_is_bounded_and_reraises(workspace, monkeypatch) -> None:
    """Permanent contention surfaces the IntegrityError instead of spinning."""
    import application.goal_service as module

    monkeypatch.setattr(module, "_SEQUENCE_ALLOCATION_ATTEMPTS", 3)

    attempts = {"n": 0}

    def _always_collide(self, *args, **kwargs):
        attempts["n"] += 1
        raise IntegrityError(
            f'duplicate key value violates unique constraint "{_CONSTRAINT}"'
        )

    monkeypatch.setattr(Goal, "save", _always_collide)

    with pytest.raises(IntegrityError):
        GoalService().create_version(
            workspace_id=workspace.id,
            title="never wins",
            description="",
            ctx=_ctx(workspace.tenant_id),
        )

    assert attempts["n"] == 3, "the loop must stop at the configured attempt cap"


def test_unrelated_integrity_error_is_not_retried(workspace, monkeypatch) -> None:
    """Only a collision on ``uq_goal_lineage_sequence`` is absorbed; an
    unrelated constraint failure must propagate immediately."""
    attempts = {"n": 0}

    def _unrelated_collision(self, *args, **kwargs):
        attempts["n"] += 1
        raise IntegrityError(
            'duplicate key value violates unique constraint "some_other_constraint"'
        )

    monkeypatch.setattr(Goal, "save", _unrelated_collision)

    with pytest.raises(IntegrityError):
        GoalService().create_version(
            workspace_id=workspace.id,
            title="unrelated",
            description="",
            ctx=_ctx(workspace.tenant_id),
        )

    assert attempts["n"] == 1, "an unrelated IntegrityError must not be retried"


def test_unknown_lineage_still_raises_not_found(workspace) -> None:
    """A stale MAX-read proxy must not defeat the unknown-lineage guard."""
    with pytest.raises(NotFoundError):
        GoalService().create_version(
            workspace_id=workspace.id,
            title="orphan",
            description="",
            lineage_id=uuid.uuid4(),
            ctx=_ctx(workspace.tenant_id),
        )


def test_sequential_creates_still_number_consecutively(workspace) -> None:
    """No-contention path is unchanged: v1, v2, v3."""
    svc = GoalService()
    ctx = _ctx(workspace.tenant_id)

    first = svc.create_version(
        workspace_id=workspace.id, title="goal 1", description="", ctx=ctx
    )
    lineage_id = uuid.UUID(first["lineage_id"])
    numbers = [
        svc.create_version(
            workspace_id=workspace.id,
            title=f"goal {i}",
            description="",
            lineage_id=lineage_id,
            ctx=ctx,
        )["sequence_number"]
        for i in range(2, 4)
    ]
    assert [first["sequence_number"], *numbers] == [1, 2, 3]
