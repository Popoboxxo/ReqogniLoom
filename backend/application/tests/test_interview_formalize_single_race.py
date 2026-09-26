"""CR-06 — concurrent single-mode ``formalize()``: exactly one completion.

Audit finding CR-06 (W2 slice): the single-kind formalize path took **no**
row lock. ``formalize()``'s ``in_progress`` guard reads the session with a
plain ``.filter().first()`` (unlocked), and ``_formalize_single()`` then
created an artifact, bumped ``version`` and emitted a successful
``InterviewFormalized`` event with nothing serialising the two writers. The
multi-kind path had been fixed in exactly this way (its M2 review finding);
the single path had not.

Concretely, pre-fix, two concurrent single-mode formalize calls on one
session both observed ``in_progress`` and both committed: two artifacts, two
version bumps, two outbox events, two provenance rows — and with CR-07 also
two audit entries, i.e. a session whose audit trail claims it was
formalized twice. ``session.version = F("version") + 1`` is *not* an
optimistic-lock compare (unlike ``WorkflowItemState.version`` + an
``expected_version`` check), so nothing else caught it either.

The fix takes the same ``select_for_update()`` + status recheck inside the
transaction that ``_formalize_multi`` uses, so the loser blocks on the lock
until the winner commits and then fails the recheck deterministically.

``@pytest.mark.django_db(transaction=True)`` is mandatory here, not cosmetic:
the two worker threads each open their own DB connection. Under the default
``django_db`` fixture the test body runs inside one outer transaction on the
*main* thread's connection, so the workers would neither see the fixture's
rows nor be able to take a row lock the main transaction is holding — the
race would silently degrade into two sequential writers and the test would
pass vacuously. ``transaction=True`` gives ``TransactionTestCase``
semantics, i.e. real committed rows and real cross-connection lock
contention.

The autouse ``TenantContext`` cleaners (backend/conftest.py and
application/tests/conftest.py) only ever run on the *main* thread, so each
worker clears its own thread-local tenant and closes its own connection in a
``finally``.
"""
from __future__ import annotations

import threading
import uuid

import pytest
from django.db import close_old_connections

from application.base import ValidationError
from application.interview_service import InterviewService
from application.models import DomainEventOutbox
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import (
    InterviewSessionArtifact,
    Requirement,
    Tenant,
    User,
    Workspace,
)
from persistence.tenancy import TenantContext
from workflow.services import create_default_workflow


@pytest.fixture
def tenant(db: None) -> Tenant:
    return Tenant.objects.create(name="CR06 Tenant", slug="cr06-tenant")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
    """A workspace that actually has an ``Interview`` workflow definition.

    Without one, ``start()`` initialises no ``WorkflowItemState`` row, the
    engine transition inside ``_write_single_artifact`` is swallowed by its
    deliberate legacy fallback, and the session's state never leaves
    ``in_progress`` -- which would make the recheck under test vacuous. The
    real stack provisions definitions at workspace creation; this fixture
    reproduces that so the race is exercised against a live engine.
    """
    TenantContext.set_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(tenant=tenant, name="WS")
        create_default_workflow(
            workspace_id=workspace.id,
            preset="interview_default",
            item_type="Interview",
            tenant_id=tenant.id,
        )
        return workspace
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def user(tenant: Tenant) -> User:
    """A real User row: ``Artifact.created_by`` is a real FK, not a free uuid."""
    return User.objects.create(
        username="cr06-user",
        email="cr06-user@example.test",
        tenant=tenant,
        is_active=True,
    )


@pytest.fixture
def ctx(tenant: Tenant, user: User) -> AuthContext:
    return AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=("editor",),
        auth_method=AuthMethod.API_KEY,
    )


@pytest.fixture
def answerable_session(ctx: AuthContext, workspace: Workspace):
    """A single-kind session the protocol already considers complete."""
    service = InterviewService()
    session = service.start(ctx, "Requirement", workspace.id)
    service.answer(ctx, session.id, "title", "Concurrent formalize probe")
    service.answer(
        ctx, session.id, "rationale", "so the completeness guard lets it through"
    )
    return session


def _interview_audit_rows(session_id: uuid.UUID) -> list[AuditEntry]:
    """Audit rows belonging to *this session's own* completion.

    Filtered on ``entity_type="Interview"``/``entity_id`` because the artifact
    the interview creates is audited separately (entity_type="Requirement"),
    and that row is not what this test counts.
    """
    return list(
        AuditEntry.objects.filter(
            entity_type="Interview", entity_id=session_id
        ).order_by("timestamp")
    )


def _formalized_events(session_id: uuid.UUID) -> list[DomainEventOutbox]:
    return list(
        DomainEventOutbox.objects.filter(
            event_type=DomainEventOutbox.EventType.INTERVIEW_FORMALIZED,
            entity_id=session_id,
        )
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_single_formalize_completes_exactly_once(
    tenant: Tenant, workspace: Workspace, ctx: AuthContext, answerable_session
):
    """Two racing single-mode formalizes on two connections: one winner (CR-06).

    Asserted contract — the W2 requirement of "exactly one completion and one
    audit/outbox correlation":

    * exactly one caller returns a completed result, the other is rejected
      with a ``ValidationError`` (the recheck, not a lock timeout);
    * exactly one ``Interview`` audit entry and exactly one
      ``INTERVIEW_FORMALIZED`` outbox event exist for the session, so the
      audit trail and the event stream agree that one completion happened;
    * exactly one Requirement was created and exactly one provenance row was
      written — the concrete damage the race used to cause.
    """
    session_id = answerable_session.id

    outcomes: dict[str, str] = {}
    outcomes_lock = threading.Lock()
    start_barrier = threading.Barrier(2, timeout=10)

    def _worker(name: str) -> None:
        close_old_connections()
        try:
            TenantContext.set_tenant(tenant.id)
            start_barrier.wait(timeout=10)
            result = InterviewService().formalize(ctx, session_id)
            outcome = f"ok:{result['status']}"
        except ValidationError:
            # The documented loser path: the row lock released, the recheck
            # found the session already completed, ValidationError raised.
            outcome = "rejected"
        except Exception as exc:  # pragma: no cover - diagnostic aid only
            outcome = f"error:{exc!r}"
        finally:
            with outcomes_lock:
                outcomes[name] = outcome
            TenantContext.clear_tenant()
            close_old_connections()

    threads = [
        threading.Thread(target=_worker, args=("formalize_a",)),
        threading.Thread(target=_worker, args=("formalize_b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not any(t.is_alive() for t in threads), "worker thread did not finish in time"
    assert set(outcomes) == {"formalize_a", "formalize_b"}, outcomes
    assert list(outcomes.values()).count("ok:completed") == 1, outcomes
    assert list(outcomes.values()).count("rejected") == 1, outcomes

    audit_rows = _interview_audit_rows(session_id)
    assert len(audit_rows) == 1, (
        f"exactly one audit entry for one committed completion, got {len(audit_rows)}: "
        f"{[(r.op, r.entity_type) for r in audit_rows]} ({outcomes})"
    )
    assert audit_rows[0].op == "transition", audit_rows[0].op
    assert audit_rows[0].details["workflow_transition_applied"] is True

    events = _formalized_events(session_id)
    assert len(events) == 1, (
        f"exactly one INTERVIEW_FORMALIZED event expected, got {len(events)} ({outcomes})"
    )

    TenantContext.set_tenant(tenant.id)
    try:
        assert Requirement.objects.filter(workspace_id=workspace.id).count() == 1, (
            "the loser must not have created a second artifact"
        )
        assert InterviewSessionArtifact.objects.filter(session_id=session_id).count() == 1
    finally:
        TenantContext.clear_tenant()


@pytest.mark.django_db(transaction=True)
def test_second_sequential_formalize_is_rejected_after_completion(
    ctx: AuthContext, answerable_session
):
    """Sequential twin of the race, so a failure points at the recheck itself.

    Same contract as above minus the threads: a second ``formalize()`` on an
    already-completed session must be refused, and must not add a second
    audit entry, a second outbox event, or a second artifact. This is the
    case that already worked via ``formalize()``'s outer guard — it is pinned
    here to prove the new lock/recheck did not change the *error type* callers
    see.
    """
    session_id = answerable_session.id
    service = InterviewService()

    first = service.formalize(ctx, session_id)
    assert first["status"] == "completed", first

    with pytest.raises(ValidationError):
        service.formalize(ctx, session_id)

    assert len(_interview_audit_rows(session_id)) == 1
    assert len(_formalized_events(session_id)) == 1
