"""CR-09 / CR-09b — global workflow definition atomicity + live-item orphan gate.

Two defects are pinned here, both in
:class:`workflow.global_definition_store.GlobalWorkflowDefinitionStore`:

**CR-09 (atomicity).** ``_persist`` saved the tenant-wide global row in
autocommit and only THEN called ``_propagate``. A failure inside ``_propagate``
therefore left the global truth mutated while every ``is_customized=False``
derived row kept the old graph — two individually-valid layers that silently
disagree, which no reader can detect afterwards. Both writes now share one
``transaction.atomic()`` block.

Scope note (deliberate): the propagation is a SINGLE ``QuerySet.update()``.
There is NO selective row-wise partial propagation — the defect proven here is
strictly the missing atomicity between the global and the derived layer, never
"some workspaces updated, some not" within a successful call.

**CR-09b (live-item orphan gate, fail-closed).** A global row owns no
``WorkflowItemState`` itself, but it propagates into every non-customized
derived workspace, and those workspaces hold live items. ``delete_state`` now
raises :class:`~workflow.definition_store.OrphanedStateError` when a live item
in a non-customized inheriting workspace sits in the state being removed, before
any write.

**B2 (the gate is atomic with the write).** The first shape of CR-09b ran
``_check_live_items_in_state`` in its own transaction and then let ``_persist``
open a SECOND one — a check-then-act across two transactions that is not
fail-closed no matter how the docstring reads. Gate, structural check and write
now share one ``transaction.atomic()`` that first re-reads the global row under
``select_for_update()``. The section at the bottom pins that binding
*behaviourally* (a second connection cannot lock the global row while the gate
runs) and pins the tenant isolation of the gate's workspace lookup.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from uuid import uuid4

import pytest
from django.db import OperationalError, close_old_connections, connections

from persistence.models import Tenant
from persistence.tenancy import TenantContext
from workflow.definition_store import (
    OrphanedStateError,
    StateReferencedError,
    WorkflowDefinitionError,
)
from workflow.global_definition_store import GlobalWorkflowDefinitionStore
from workflow.models import (
    GlobalWorkflowDefinition,
    WorkflowEngineDefinition,
    WorkflowItemState,
)

pytestmark = pytest.mark.django_db


@contextmanager
def _tenant_scope(tenant_id):
    """GlobalWorkflowDefinition / WorkflowEngineDefinition / WorkflowItemState
    are TenantScopedModel (ADR-03) — mirrors the idiom used across
    workflow/tests/ (e.g. test_global_definition_store_cache_invalidation.py)."""
    TenantContext.set_tenant(tenant_id)
    try:
        yield
    finally:
        TenantContext.clear_tenant()


@pytest.fixture
def tenant():
    return Tenant.objects.create(
        name="gdsatomic-tenant", slug=f"gdsatomic-{uuid4().hex[:8]}"
    )


def _graph(states=("Open", "Closed")) -> dict:
    """A graph whose states carry no referencing transitions, so the structural
    gate never masks the orphan gate in these tests."""
    return {"states": list(states), "transitions": []}


def _make_global(tenant, states=("Open", "Closed")) -> GlobalWorkflowDefinition:
    return GlobalWorkflowDefinition.objects.create(
        tenant=tenant,
        item_type="Issue",
        preset="issue_default",
        workflow_json=_graph(states),
    )


def _make_derived(tenant, global_def, *, is_customized, states=None):
    return WorkflowEngineDefinition.objects.create(
        tenant=tenant,
        workspace_id=uuid4(),
        item_type="Issue",
        preset="issue_default",
        workflow_json=_graph(states or ("Open", "Closed")),
        source_global=global_def,
        is_customized=is_customized,
    )


def _make_live_item(tenant, definition, state) -> WorkflowItemState:
    """A live item sitting in ``state``, bound to ``definition`` (PROTECT FK)."""
    return WorkflowItemState.objects.create(
        tenant=tenant,
        item_id=uuid4(),
        item_type="Issue",
        workspace_id=definition.workspace_id,
        definition=definition,
        current_state=state,
    )


def _states_of_global(global_pk) -> list[str]:
    return list(
        (GlobalWorkflowDefinition.unscoped.get(pk=global_pk).workflow_json or {}).get(
            "states", []
        )
    )


def _states_of_derived(derived_pk) -> list[str]:
    return list(
        (
            WorkflowEngineDefinition.unscoped.get(pk=derived_pk).workflow_json or {}
        ).get("states", [])
    )


# ---------------------------------------------------------------------------
# CR-09 — atomicity (fault injection)
# ---------------------------------------------------------------------------


def test_fault_in_propagate_leaves_neither_layer_mutated(tenant, monkeypatch) -> None:
    """A failure inside ``_propagate`` must not leave the global row committed.

    Pre-fix this is the exact divergence: ``obj.save()`` ran in autocommit, the
    derived rows kept ``["Open", "Closed"]`` and the global already carried
    ``"In Review"``. Post-fix neither layer moved.
    """
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        derived_a = _make_derived(tenant, global_def, is_customized=False)
        derived_b = _make_derived(tenant, global_def, is_customized=False)

        def _explode(self, obj):
            raise RuntimeError("injected propagation fault")

        monkeypatch.setattr(GlobalWorkflowDefinitionStore, "_propagate", _explode)
        store = GlobalWorkflowDefinitionStore()
        with pytest.raises(RuntimeError, match="injected propagation fault"):
            store.add_state(tenant.id, "Issue", "issue_default", "In Review")
        monkeypatch.undo()

        # Both layers re-read from the DB, not from the in-memory object: after a
        # rollback the in-memory ``obj`` still carries the new graph by design.
        assert _states_of_global(global_def.pk) == ["Open", "Closed"], (
            "the global row was committed despite the failed propagation"
        )
        assert _states_of_derived(derived_a.pk) == ["Open", "Closed"]
        assert _states_of_derived(derived_b.pk) == ["Open", "Closed"]


def test_fault_after_the_derived_write_rolls_both_layers_back(tenant, monkeypatch) -> None:
    """A failure raised AFTER ``_propagate`` already wrote the derived rows also
    rolls everything back — the derived write is inside the block, not after it.

    Without ``transaction.atomic()`` this is the mirror-image partial state:
    the derived rows would carry the new graph while the caller saw an exception.
    """
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        derived = _make_derived(tenant, global_def, is_customized=False)

        real_propagate = GlobalWorkflowDefinitionStore._propagate

        def _propagate_then_explode(self, obj):
            real_propagate(self, obj)  # the derived rows really are written …
            raise RuntimeError("injected fault after the derived write")

        monkeypatch.setattr(
            GlobalWorkflowDefinitionStore, "_propagate", _propagate_then_explode
        )
        store = GlobalWorkflowDefinitionStore()
        with pytest.raises(RuntimeError, match="after the derived write"):
            store.add_state(tenant.id, "Issue", "issue_default", "In Review")
        monkeypatch.undo()

        assert _states_of_global(global_def.pk) == ["Open", "Closed"]
        assert _states_of_derived(derived.pk) == ["Open", "Closed"], (
            "the derived write escaped the atomic block"
        )


def test_successful_edit_moves_both_layers_together(tenant) -> None:
    """Positive control: on the happy path both layers carry the new graph —
    the layers never legitimately disagree."""
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        derived = _make_derived(tenant, global_def, is_customized=False)
        customized = _make_derived(
            tenant, global_def, is_customized=True, states=("Custom",)
        )

        obj, propagated = GlobalWorkflowDefinitionStore().add_state(
            tenant.id, "Issue", "issue_default", "In Review"
        )

        assert propagated == 1, "only the non-customized row is propagated"
        assert "In Review" in obj.workflow_json["states"]
        assert "In Review" in _states_of_global(global_def.pk)
        assert "In Review" in _states_of_derived(derived.pk)
        # A customized workspace no longer mirrors the template — untouched.
        assert _states_of_derived(customized.pk) == ["Custom"]


# ---------------------------------------------------------------------------
# CR-09b — live-item orphan gate (fail-closed)
# ---------------------------------------------------------------------------


def test_delete_state_blocked_by_live_item_in_inheriting_workspace(tenant) -> None:
    """Fail-closed: a live item in a non-customized inheriting workspace blocks
    the delete, and NOTHING is written (global and derived both unchanged)."""
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        derived = _make_derived(tenant, global_def, is_customized=False)
        item = _make_live_item(tenant, derived, "Closed")

        store = GlobalWorkflowDefinitionStore()
        with pytest.raises(OrphanedStateError) as exc_info:
            store.delete_state(tenant.id, "Issue", "issue_default", "Closed")

        exc = exc_info.value
        assert exc.orphaned_state == "Closed"
        assert exc.count == 1
        assert str(item.item_id) in exc.item_ids
        # Gate is raised BEFORE any write: neither layer moved.
        assert _states_of_global(global_def.pk) == ["Open", "Closed"]
        assert _states_of_derived(derived.pk) == ["Open", "Closed"]
        assert (
            WorkflowItemState.unscoped.get(pk=item.pk).current_state == "Closed"
        ), "the live item must be left exactly as found"


def test_delete_state_blocked_counts_every_affected_workspace(tenant) -> None:
    """The gate aggregates across ALL non-customized inheriting workspaces, not
    just the first one."""
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        derived_a = _make_derived(tenant, global_def, is_customized=False)
        derived_b = _make_derived(tenant, global_def, is_customized=False)
        _make_live_item(tenant, derived_a, "Closed")
        _make_live_item(tenant, derived_b, "Closed")
        _make_live_item(tenant, derived_b, "Closed")

        with pytest.raises(OrphanedStateError) as exc_info:
            GlobalWorkflowDefinitionStore().delete_state(
                tenant.id, "Issue", "issue_default", "Closed"
            )

        assert exc_info.value.count == 3
        assert _states_of_global(global_def.pk) == ["Open", "Closed"]


def test_delete_state_succeeds_without_any_live_item(tenant) -> None:
    """Counter-case: no live item in the state -> the delete goes through and
    still propagates atomically to the derived layer."""
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        derived = _make_derived(tenant, global_def, is_customized=False)
        # A live item, but in a DIFFERENT state than the one being removed.
        _make_live_item(tenant, derived, "Open")

        obj, propagated = GlobalWorkflowDefinitionStore().delete_state(
            tenant.id, "Issue", "issue_default", "Closed"
        )

        assert propagated == 1
        assert "Closed" not in obj.workflow_json["states"]
        assert _states_of_global(global_def.pk) == ["Open"]
        assert _states_of_derived(derived.pk) == ["Open"]


def test_delete_state_ignores_items_in_customized_workspaces(tenant) -> None:
    """Counter-case: a customized workspace no longer mirrors the template, so a
    global edit never reaches it and cannot strand its items."""
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        customized = _make_derived(
            tenant, global_def, is_customized=True, states=("Open", "Closed")
        )
        item = _make_live_item(tenant, customized, "Closed")

        obj, propagated = GlobalWorkflowDefinitionStore().delete_state(
            tenant.id, "Issue", "issue_default", "Closed"
        )

        assert propagated == 0, "a customized row is never propagated to"
        assert "Closed" not in obj.workflow_json["states"]
        assert _states_of_global(global_def.pk) == ["Open"]
        # The customized row — and the item living in it — are untouched.
        assert _states_of_derived(customized.pk) == ["Open", "Closed"]
        assert WorkflowItemState.unscoped.get(pk=item.pk).current_state == "Closed"


def test_delete_state_ignores_items_outside_inheriting_workspaces(tenant) -> None:
    """Counter-case: an unlinked legacy row (``source_global=None``) is not
    derived from this template, so its items are out of scope for the gate."""
    with _tenant_scope(tenant.id):
        _make_global(tenant)
        legacy = WorkflowEngineDefinition.objects.create(
            tenant=tenant,
            workspace_id=uuid4(),
            item_type="Issue",
            preset="issue_default",
            workflow_json=_graph(),
            source_global=None,
            is_customized=False,
        )
        _make_live_item(tenant, legacy, "Closed")

        obj, _propagated = GlobalWorkflowDefinitionStore().delete_state(
            tenant.id, "Issue", "issue_default", "Closed"
        )

        assert "Closed" not in obj.workflow_json["states"]


def test_structural_gate_still_takes_precedence(tenant) -> None:
    """A state referenced by a transition keeps raising ``StateReferencedError``
    even with live items present — the pre-existing error precedence is intact."""
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        global_def.workflow_json = {
            "states": ["Open", "Closed"],
            "transitions": [
                {
                    "from_state": "Closed",
                    "to_state": "Open",
                    "allowed_roles": ["admin"],
                    "requires_change_reason": False,
                    "signature_gate": False,
                }
            ],
        }
        global_def.save(update_fields=["workflow_json"])
        derived = _make_derived(tenant, global_def, is_customized=False)
        _make_live_item(tenant, derived, "Closed")

        with pytest.raises(StateReferencedError):
            GlobalWorkflowDefinitionStore().delete_state(
                tenant.id, "Issue", "issue_default", "Closed"
            )


def test_unknown_state_still_raises_workflow_definition_error(tenant) -> None:
    """The pre-fix guard rails are unchanged."""
    with _tenant_scope(tenant.id):
        _make_global(tenant)
        with pytest.raises(WorkflowDefinitionError, match="Unknown state"):
            GlobalWorkflowDefinitionStore().delete_state(
                tenant.id, "Issue", "issue_default", "Nope"
            )


# ---------------------------------------------------------------------------
# B2 — the gate is bound to the write (NEGATIVE CONTROL)
# ---------------------------------------------------------------------------


class _StopAfterGate(Exception):
    """Sentinel: abort ``delete_state`` right after the gate, before the write."""


def _can_another_connection_lock_the_global_row(global_pk) -> bool:
    """From a genuinely separate connection: try to lock the global row NOW.

    Returns ``True`` when the row could be locked (i.e. nobody holds it) and
    ``False`` when PostgreSQL refused because the caller's transaction already
    holds the lock. ``FOR UPDATE NOWAIT`` is the right primitive: it fails
    IMMEDIATELY instead of blocking, so the probe cannot deadlock the
    transaction it is inspecting, and the outcome is a clean boolean rather
    than a lock-wait timeout that would depend on timing.
    """
    outcome: dict[str, bool] = {}

    def _probe() -> None:
        close_old_connections()
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM we_global_definition "
                    "WHERE id = %s FOR UPDATE NOWAIT",
                    [str(global_pk)],
                )
                cursor.fetchone()
            outcome["acquired"] = True
        except OperationalError:
            outcome["acquired"] = False
        finally:
            close_old_connections()

    thread = threading.Thread(target=_probe)
    thread.start()
    thread.join(timeout=15)
    assert not thread.is_alive(), "the lock probe deadlocked against the main transaction"
    return outcome["acquired"]


@pytest.mark.django_db(transaction=True)
def test_delete_state_holds_the_global_row_lock_while_the_gate_runs(
    tenant, monkeypatch
) -> None:
    """NEGATIVE CONTROL for B2 — remove the atomic/lock and this goes RED.

    ``delete_state`` must keep the global row locked from before the live-item
    gate until the write is committed. The probe asks, from a second connection
    *while the gate is executing*, whether the row is still lockable. With the
    atomic+``select_for_update`` binding in place it is not; with the pre-fix
    shape — gate in its own transaction, ``_persist`` opening a second one — the
    gate runs with no lock held at all, the probe succeeds, and the assertion
    below fails. That is the whole point of this test: it fails on the
    check-then-act version even though that version still passes every
    "the delete is blocked" assertion above.

    ``transaction=True`` is load-bearing, not cosmetic: the probe runs on its
    own connection, which under the default ``django_db`` fixture could neither
    see the fixture's uncommitted rows nor be blocked by them.
    """
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        derived = _make_derived(tenant, global_def, is_customized=False)
        _make_live_item(tenant, derived, "Closed")

        probed: dict[str, bool] = {}

        def _probe_then_stop(self, obj, state):
            probed["acquired"] = _can_another_connection_lock_the_global_row(obj.pk)
            raise _StopAfterGate

        monkeypatch.setattr(
            GlobalWorkflowDefinitionStore, "_check_live_items_in_state", _probe_then_stop
        )

        with pytest.raises(_StopAfterGate):
            GlobalWorkflowDefinitionStore().delete_state(
                tenant.id, "Issue", "issue_default", "Closed"
            )
        monkeypatch.undo()

        assert probed["acquired"] is False, (
            "while the live-item gate runs, another connection could lock the "
            "global row — the gate and the write are NOT bound to one "
            "transaction, so this is a check-then-act (the B2 defect)"
        )


@pytest.mark.django_db(transaction=True)
def test_the_binding_probe_detects_the_pre_fix_shape(tenant, monkeypatch) -> None:
    """Positive control for the control: the probe CAN observe an unlocked row.

    Without this, the negative control above would also pass for the wrong
    reason — e.g. if the probe thread were broken and always reported
    ``False``, the assertion would be vacuously green. Here the row is
    deliberately NOT locked, so the probe must report that it acquired the lock.
    This is the assertion that gives the negative control its meaning.
    """
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)

        assert _can_another_connection_lock_the_global_row(global_def.pk) is True, (
            "the probe can never report an unlocked row — the negative control "
            "above is therefore vacuous and proves nothing"
        )


# ---------------------------------------------------------------------------
# Tenant isolation of the gate's workspace lookup
# ---------------------------------------------------------------------------


def test_gate_does_not_see_live_items_of_a_foreign_tenant(tenant) -> None:
    """``_non_customized_workspace_ids`` reads ``unscoped`` — prove that is safe.

    The gate resolves the inheriting workspaces through
    ``WorkflowEngineDefinition.unscoped.filter(source_global_id=obj.id)``. That
    is only correct because ``source_global_id`` points at a globally unique
    global row, so every row it selects is necessarily the same tenant's. The
    reasoning is a claim until it is negative-tested: here a SECOND tenant has a
    live item in the very state being deleted, and the delete must still go
    through. If the lookup ever widened to, say, "all workspaces of the
    item_type", this test would fail — the foreign item would block a delete it
    has no business blocking.
    """
    other_tenant = Tenant.objects.create(
        name="gdsatomic-other", slug=f"gdsatomic-other-{uuid4().hex[:8]}"
    )
    other_workspace_id = uuid4()

    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        # Same tenant, no live item anywhere -> the delete must succeed.
        assert (
            GlobalWorkflowDefinitionStore()._non_customized_workspace_ids(global_def)
            == []
        )

        with _tenant_scope(other_tenant.id):
            other_global = _make_global(other_tenant)
            _make_derived(other_tenant, other_global, is_customized=False)
            foreign_item = _make_live_item(
                other_tenant,
                WorkflowEngineDefinition.objects.get(
                    source_global=other_global, is_customized=False
                ),
                "Closed",
            )

        # The foreign tenant's row hangs off a DIFFERENT global, so it can
        # never appear in this template's inheriting set.
        assert (
            GlobalWorkflowDefinitionStore()._non_customized_workspace_ids(global_def)
            == []
        )
        assert str(other_workspace_id) not in (
            GlobalWorkflowDefinitionStore()._non_customized_workspace_ids(global_def)
        )

        obj, propagated = GlobalWorkflowDefinitionStore().delete_state(
            tenant.id, "Issue", "issue_default", "Closed"
        )

        assert propagated == 0, (
            "a foreign tenant's workspace must never be treated as an "
            "inheriting workspace of this template"
        )
        assert "Closed" not in obj.workflow_json["states"]
        # And the foreign item is untouched.
        assert WorkflowItemState.unscoped.get(pk=foreign_item.pk).current_state == "Closed"


def test_gate_does_see_this_tenant_s_own_inheriting_items(tenant) -> None:
    """Counter-case for the isolation test above: the gate is not simply off.

    Pins the positive direction on the SAME fixture shape, so a regression that
    broke the lookup entirely (returning ``[]`` always, or filtering on
    something that never matches) cannot pass the isolation test by disabling
    the gate.
    """
    with _tenant_scope(tenant.id):
        global_def = _make_global(tenant)
        derived = _make_derived(tenant, global_def, is_customized=False)
        item = _make_live_item(tenant, derived, "Closed")

        assert GlobalWorkflowDefinitionStore()._non_customized_workspace_ids(
            global_def
        ) == [str(derived.workspace_id)]

        with pytest.raises(OrphanedStateError):
            GlobalWorkflowDefinitionStore().delete_state(
                tenant.id, "Issue", "issue_default", "Closed"
            )
        assert WorkflowItemState.unscoped.get(pk=item.pk).current_state == "Closed"
