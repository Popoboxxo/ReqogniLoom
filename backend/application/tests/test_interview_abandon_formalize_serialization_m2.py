"""M2/M4 — ``abandon()`` is serialised against ``formalize()``, one shared guard.

Review finding M2: ``abandon()`` read ``session.status`` from an unlocked
``_get_session`` and never took a row lock, while both formalize paths locked
the session and re-validated ``in_progress`` under that lock. The two were
therefore not serialised against each other:

    T1 formalize()  engine transition  in_progress -> completed   (commits)
    T2 abandon()    read in_progress, validate AFTER T1's commit,
                    apply              completed -> abandoned   (commits)

``completed -> abandoned`` is a DECLARED edge of the interview workflow, so the
graph validator accepts it: a just-formalized interview — artifacts created,
provenance rows written — was silently flipped to ``abandoned``. Nothing
errored; both calls returned success.

Review finding M4: the lock + engine-resolved status re-read + ``in_progress``
precondition had TWO owners — the shared ``_lock_in_progress_session`` and a
byte-identical inline block in ``_formalize_multi`` (identical down to the error
message). Two owners of one invariant drift; the fix gives the guard a single
owner and makes ``abandon()`` its third caller.

``transaction=True`` is load-bearing: the two workers below each open their own
connection, which under the default ``django_db`` fixture could neither see the
fixture's uncommitted rows nor block on the lock the other holds.
"""
from __future__ import annotations

import threading
import uuid

import pytest
from django.db import close_old_connections, transaction

from application.base import ValidationError
from application.interview_service import InterviewService
from application.models import DomainEventOutbox
from audit.models import AuditEntry
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.models import InterviewSession, Tenant, User, Workspace
from persistence.tenancy import TenantContext
from workflow.models import WorkflowItemState
from workflow.services import create_default_workflow

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db: None) -> Tenant:
    return Tenant.objects.create(name="M2 Tenant", slug=f"m2-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def workspace(tenant: Tenant) -> Workspace:
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
    return User.objects.create(
        username="m2-user",
        email="m2-user@example.test",
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


def _ready_session(ctx: AuthContext, workspace: Workspace) -> InterviewSession:
    """A session with enough answers that ``formalize()`` is actually allowed."""
    service = InterviewService()
    session = service.start(ctx, "Requirement", workspace.id)
    service.answer(ctx, session.id, "title", "M2 race probe")
    service.answer(ctx, session.id, "rationale", "so formalize() succeeds")
    return session


def _engine_state(tenant_id, session_id) -> str | None:
    TenantContext.set_tenant(tenant_id)
    try:
        return (
            WorkflowItemState.objects.filter(
                item_id=session_id, item_type="Interview"
            )
            .values_list("current_state", flat=True)
            .first()
        )
    finally:
        TenantContext.clear_tenant()


def _abandon_events(tenant_id, session_id):
    return DomainEventOutbox.objects.filter(
        event_type=DomainEventOutbox.EventType.INTERVIEW_ABANDONED, entity_id=session_id
    ).count()


def _abandon_audits(session_id):
    return AuditEntry.objects.filter(
        entity_type="Interview", entity_id=session_id, op="transition"
    ).count()


# ---------------------------------------------------------------------------
# M2 — the race itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_abandon_racing_formalize_never_undoes_a_committed_formalize(
    tenant, workspace, ctx
):
    """The production shape, on two real connections released together.

    Both workers pass the same barrier, so either may win the lock. The
    invariant asserted is the one the defect violated, and it is
    order-independent:

        a session that was FORMALIZED is never afterwards ``abandoned``.

    Pre-fix, T2 could read ``in_progress`` before T1 committed and then apply
    ``completed -> abandoned`` (a declared edge) after it — artifacts created,
    provenance written, session un-completed, both calls returning success.
    Post-fix the two are serialised on the session row, so the loser's locked
    re-read sees the winner's state and refuses.
    """
    session = _ready_session(ctx, workspace)
    session_id = session.id
    tenant_id = tenant.id
    barrier = threading.Barrier(2, timeout=30)
    outcomes: dict[str, str] = {}
    outcomes_lock = threading.Lock()

    def _formalize_worker() -> None:
        close_old_connections()
        try:
            TenantContext.set_tenant(tenant_id)
            barrier.wait(timeout=30)
            with transaction.atomic():
                InterviewService().formalize(ctx, session_id)
            result = "formalized"
        except ValidationError:
            result = "refused"
        except Exception as exc:  # pragma: no cover - diagnostic aid only
            result = f"error:{exc!r}"
        finally:
            with outcomes_lock:
                outcomes["formalize"] = result
            TenantContext.clear_tenant()
            close_old_connections()

    def _abandon_worker() -> None:
        close_old_connections()
        try:
            TenantContext.set_tenant(tenant_id)
            barrier.wait(timeout=30)
            with transaction.atomic():
                InterviewService().abandon(ctx, session_id)
            result = "abandoned"
        except ValidationError:
            result = "refused"
        except Exception as exc:  # pragma: no cover - diagnostic aid only
            result = f"error:{exc!r}"
        finally:
            with outcomes_lock:
                outcomes["abandon"] = result
            TenantContext.clear_tenant()
            close_old_connections()

    threads = [
        threading.Thread(target=_formalize_worker),
        threading.Thread(target=_abandon_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "a worker did not finish in time"
    assert set(outcomes) == {"formalize", "abandon"}, outcomes
    assert not any(v.startswith("error:") for v in outcomes.values()), outcomes

    final = _engine_state(tenant_id, session_id)
    if outcomes["formalize"] == "formalized":
        assert final == "completed", (
            f"formalize() committed but the session ended up {final!r} — a "
            f"concurrent abandon undid it ({outcomes})"
        )
        assert _abandon_events(tenant_id, session_id) == 0, (
            "a refused abandon must not emit a success event"
        )
    else:
        # abandon legitimately won the race: formalize was refused, so there
        # is nothing to undo. Pinned so the assertion above cannot be satisfied
        # by simply always losing the formalize.
        assert outcomes["abandon"] == "abandoned", outcomes
        assert final == "abandoned", final


def test_abandon_after_formalize_is_refused_outright(ctx, workspace):
    """The sequential twin, asserted on its own.

    Pins the *reason* as well as the outcome: the refusal must come from the
    locked ``in_progress`` guard, which means a caller that races (and so
    learned its ``in_progress`` read was stale) is told WHY. Without the message
    assertion a future "fix" that silently returns the current state instead of
    raising would pass the status check above while breaking the contract that
    the losing racer learns it lost.
    """
    session = _ready_session(ctx, workspace)
    InterviewService().formalize(ctx, session.id)

    with pytest.raises(ValidationError) as exc_info:
        InterviewService().abandon(ctx, session.id)

    assert "cannot abandon" in str(exc_info.value), str(exc_info.value)
    assert _engine_state(ctx.tenant_id, session.id) == "completed"


def test_abandon_message_does_not_claim_the_guard_is_a_formalize_guard(ctx, workspace):
    """M4: the shared guard is parameterised, so the message stays truthful.

    ``_lock_in_progress_session`` is now used by three call sites. Before the
    ``action`` parameter it hard-coded "cannot formalize", so a cancelled session
    would have been reported as a formalization failure — sending the caller
    (and the user) after the wrong problem.
    """
    session = _ready_session(ctx, workspace)
    InterviewService().formalize(ctx, session.id)

    with pytest.raises(ValidationError) as exc_info:
        InterviewService().abandon(ctx, session.id)

    message = str(exc_info.value)
    assert "cannot formalize" not in message, message


def test_guard_is_a_single_owner(ctx, workspace):
    """M4: the multi path delegates to the shared guard, it does not repeat it.

    Not a source-inspection test — a behavioural one. The inline block and the
    helper produced the same result, so the only way to tell them apart is to
    make the HELPER observable and assert the multi path goes through it. If
    someone re-inlines the block, the observable fires zero times here.
    """
    service = InterviewService()
    session = service.start(
        ctx, None, workspace.id, session_kind=InterviewSession.SESSION_KIND_MULTI
    )
    proposal = [
        {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}
    ]

    calls: list[int] = []
    real_lock = InterviewService._lock_in_progress_session

    def _spy(inner_session, *args, **kwargs):
        calls.append(1)
        return real_lock(inner_session, *args, **kwargs)

    service._lock_in_progress_session = _spy
    try:
        result = service.formalize(ctx, session.id, proposal)
    finally:
        del service._lock_in_progress_session

    assert result["status"] == "completed", result
    assert calls, (
        "the multi formalize path did not route through the shared guard — the "
        "inline block is back and the two owners can drift again"
    )


def test_multi_formalize_still_refuses_a_non_in_progress_session(ctx, workspace):
    """Counter-case: the de-duplicated guard did not weaken the multi path.

    The inline block and the helper must agree on the refusal, otherwise the
    de-duplication traded a maintenance hazard for a real regression.
    """
    service = InterviewService()
    session = service.start(
        ctx, None, workspace.id, session_kind=InterviewSession.SESSION_KIND_MULTI
    )
    proposal = [
        {"type": "StakeholderNeed", "fields": {"title": "Need A"}, "links": []}
    ]
    service.formalize(ctx, session.id, proposal)

    with pytest.raises(ValidationError) as exc_info:
        service.formalize(ctx, session.id, proposal)

    assert "cannot formalize" in str(exc_info.value), str(exc_info.value)
