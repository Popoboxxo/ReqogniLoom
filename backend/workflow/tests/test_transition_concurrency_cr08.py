"""CR-08 — concurrent workflow transitions: one winner, no unvalidated history edge.

Audit finding CR-08 (W2 slice): the graph validation of a transition ran on an
*unlocked* read of ``WorkflowItemState.current_state`` (``workflow.services
.transition``), while the row lock was only taken later, inside
``StateLifecycleManager.perform_transition``. ``expected_version`` was never
forwarded by any caller either, so two concurrent requests could both validate
their edge against the same superseded ``current_state``, and the loser still
appended a history entry for an edge nobody ever validated.

The fix moves the state read *inside* the lock (``lock_item_state``) and
re-checks the edge against the locked row before the compare-and-swap. This
module pins the resulting contract with a genuine two-connection race.

``@pytest.mark.django_db(transaction=True)`` is mandatory here, not cosmetic:
the two worker threads below each open their own DB connection. With the
default ``django_db`` fixture the whole test body runs inside one outer
transaction on the *main* thread's connection, so the workers' connections
would neither see the fixture's uncommitted rows nor be able to take a row
lock the main transaction is holding — the race would silently degrade into
two sequential writers and the test would pass vacuously. ``transaction=True``
gives ``TransactionTestCase`` semantics, i.e. real committed rows and real
cross-connection lock contention.
"""
from __future__ import annotations

import threading
import uuid

import pytest
from django.db import close_old_connections, transaction

from application.base import OptimisticLockError
from application.workflow_facade import WorkflowFacade
from auth_tenancy.context import AuthContext
from persistence.tenancy import TenantContext
from workflow.models import WorkflowHistoryEntry, WorkflowItemState
from workflow.services import get_workflow_json


class _tenant_scope:
    """Set the thread-local tenant for the duration of the block."""

    def __init__(self, tenant_id) -> None:
        self._tenant_id = tenant_id

    def __enter__(self):
        TenantContext.set_tenant(self._tenant_id)
        return self

    def __exit__(self, *exc_info) -> None:
        TenantContext.clear_tenant()


def _admin_ctx(tenant_id, workspace_id) -> AuthContext:
    """A context whose roles may perform either outgoing edge of the race.

    The ``standard`` Requirement workflow gates ``draft -> approved`` behind
    approver/admin and ``draft -> deprecated`` behind admin, so a plain editor
    context could not exercise both branches of the fork.
    """
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        active_roles=("admin",),
        auth_method="test",
        workspace_id=workspace_id,
    )


def _item_state(tenant_id, item_id, workspace_id) -> WorkflowItemState:
    """Read the item state in the *main* thread's tenant scope."""
    with _tenant_scope(tenant_id):
        return WorkflowItemState.objects.get(
            item_id=item_id, item_type="Requirement", workspace_id=workspace_id
        )


@pytest.mark.django_db(transaction=True)
def test_concurrent_transitions_produce_one_winner_and_only_valid_history_edges(
    tenant, workspace, auth_ctx, requirement_with_workflow
):
    """Two racing transitions on two connections: exactly one may win (CR-08).

    Both requests target a *different* valid outgoing edge of ``draft`` (the
    standard Requirement workflow forks into ``approved`` and ``deprecated``)
    and both claim the same last-seen revision. That is the shape that used to
    produce the defect: pre-fix, both validated against the stale ``draft`` and
    both went on to write a history row.

    Asserted contract:

    * exactly one ``ok`` and one conflict (the conflict is remapped to
      ``OptimisticLockError``, i.e. the 409 the REST/MCP layers answer);
    * ``WorkflowItemState.version`` advanced exactly once (1 -> 2);
    * every ``from_state -> to_state`` history edge exists in the freshly read
      workflow definition — no edge that was never validated.
    """
    item_id, workspace_id = requirement_with_workflow
    ctx = _admin_ctx(tenant.id, workspace.id)

    start_state = _item_state(tenant.id, item_id, workspace_id)
    assert start_state.current_state == "draft", start_state.current_state
    stale_version = start_state.version
    assert stale_version == 1, stale_version

    outcomes: dict[str, str] = {}
    outcomes_lock = threading.Lock()
    start_barrier = threading.Barrier(2, timeout=10)

    def _worker(name: str, target_state: str) -> None:
        close_old_connections()
        try:
            TenantContext.set_tenant(tenant.id)
            start_barrier.wait(timeout=10)
            with transaction.atomic():
                WorkflowFacade().transition(
                    item_id=item_id,
                    target_state=target_state,
                    change_reason=f"cr08 race ({name})",
                    ctx=ctx,
                    item_type="Requirement",
                    workspace_id=workspace_id,
                    expected_version=stale_version,
                )
            result = "ok"
        except OptimisticLockError:
            result = "conflict"
        except Exception as exc:  # pragma: no cover - diagnostic aid only
            result = f"error:{exc!r}"
        finally:
            with outcomes_lock:
                outcomes[name] = result
            # The autouse TenantContext cleaners (backend/conftest.py and
            # workflow/tests/conftest.py) only ever run on the main thread —
            # worker threads must clean up after themselves or the thread-local
            # tenant leaks into whatever connection this thread hands back.
            TenantContext.clear_tenant()
            close_old_connections()

    threads = [
        threading.Thread(target=_worker, args=("to_approved", "approved")),
        threading.Thread(target=_worker, args=("to_deprecated", "deprecated")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "worker thread did not finish in time"
    assert set(outcomes) == {"to_approved", "to_deprecated"}, outcomes
    assert list(outcomes.values()).count("ok") == 1, outcomes
    assert list(outcomes.values()).count("conflict") == 1, outcomes

    final_state = _item_state(tenant.id, item_id, workspace_id)
    assert final_state.version == 2, (
        f"version must advance exactly once for one committed transition, "
        f"got {final_state.version}"
    )
    winner = "approved" if outcomes["to_approved"] == "ok" else "deprecated"
    assert final_state.current_state == winner, (final_state.current_state, outcomes)

    # The decisive CR-08 assertion: no history edge may exist that the
    # workflow definition does not declare. Read the definition *fresh* (not
    # from a cached DTO) so nothing can mask a bad edge.
    with _tenant_scope(tenant.id):
        workflow_json = get_workflow_json(workspace_id, "Requirement")
        declared_edges = {
            (t["from_state"], t["to_state"])
            for t in (workflow_json.get("transitions") or [])
        }
        assert declared_edges, workflow_json
        entries = list(
            WorkflowHistoryEntry.objects.filter(
                item_state__item_id=item_id,
                item_state__item_type="Requirement",
                workspace_id=workspace_id,
            ).order_by("transitioned_at")
        )

    transitions = [e for e in entries if e.from_state]
    assert len(transitions) == 1, (
        [(e.from_state, e.to_state) for e in entries],
        "exactly one transition must have been committed",
    )
    invalid = [
        (e.from_state, e.to_state)
        for e in transitions
        if (e.from_state, e.to_state) not in declared_edges
    ]
    assert not invalid, (
        f"history contains edge(s) the workflow definition does not declare: "
        f"{invalid} (declared: {sorted(declared_edges)})"
    )
    assert (transitions[0].from_state, transitions[0].to_state) == ("draft", winner)


@pytest.mark.django_db(transaction=True)
def test_second_transition_on_a_stale_revision_is_rejected_as_a_conflict(
    tenant, workspace, auth_ctx, requirement_with_workflow
):
    """Sequential twin of the race: a stale ``expected_version`` must be a conflict.

    Same contract as above, minus the threads, so a failure points at the
    version compare itself rather than at lock-contention timing. The engine
    raises ``WorkflowConflictError``; the facade remaps it to
    ``OptimisticLockError`` — the single seam that gives REST its 409 and MCP
    its "Version conflict" without a parallel mapping in either layer.
    """
    item_id, workspace_id = requirement_with_workflow
    ctx = _admin_ctx(tenant.id, workspace.id)

    stale_version = _item_state(tenant.id, item_id, workspace_id).version

    with _tenant_scope(tenant.id):
        WorkflowFacade().transition(
            item_id=item_id,
            target_state="approved",
            change_reason="first",
            ctx=ctx,
            item_type="Requirement",
            workspace_id=workspace_id,
            expected_version=stale_version,
        )
        with pytest.raises(OptimisticLockError):
            WorkflowFacade().transition(
                item_id=item_id,
                target_state="deprecated",
                change_reason="second, stale revision",
                ctx=ctx,
                item_type="Requirement",
                workspace_id=workspace_id,
                expected_version=stale_version,
            )

    final_state = _item_state(tenant.id, item_id, workspace_id)
    assert final_state.current_state == "approved", (
        "the rejected transition must not have been applied"
    )
    assert final_state.version == stale_version + 1
