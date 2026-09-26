"""REQ-178 — GlobalWorkflowDefinition store: tenant-wide per-preset defaults.

CRUD + graph editing for :class:`GlobalWorkflowDefinition`, the tenant-wide
source-of-truth from which non-customized per-workspace
:class:`WorkflowEngineDefinition` rows inherit. Structurally symmetric to
:class:`workflow.definition_store.WorkflowDefinitionStore` but operates on the
tenant-wide template.

Both integrity dimensions of the per-workspace store are enforced here:

* **Structural graph integrity** — a state referenced by any transition cannot
  be deleted (:class:`~workflow.definition_store.StateReferencedError`).
* **Live-item orphan gate** — the global row has no ``WorkflowItemState`` of
  its own, but an edit to it PROPAGATES into every non-customized derived
  workspace, and those workspaces DO hold live item states. Removing a state
  that a live item still occupies in any inheriting non-customized workspace
  would silently strand that item, so :meth:`GlobalWorkflowDefinitionStore.
  delete_state` fails closed with
  :class:`~workflow.definition_store.OrphanedStateError` — the same exception
  type and the same "move the items first" contract the per-workspace store
  uses at ``_check_orphaned_state``. Customized workspaces
  (``is_customized=True``) are deliberately exempt: they no longer mirror this
  template, so their live items are unaffected by the edit.

Every mutation persists the global row and PROPAGATES ``workflow_json`` into
every ``is_customized=False`` derived definition of the SAME preset, returning
the propagated workspace count so the UI can surface it. Both writes form ONE
logical operation and share a single ``transaction.atomic()`` block — see
:meth:`GlobalWorkflowDefinitionStore._persist`.
"""
from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from django.db import transaction

from .definition_store import (
    PRESET_SCHEMAS,
    OrphanedStateError,
    StateReferencedError,
    WorkflowDefinitionError,
    WorkflowDefinitionStore,
)
from .models import (
    GlobalWorkflowDefinition,
    WorkflowEngineDefinition,
    WorkflowItemState,
)


def _empty_graph() -> dict[str, Any]:
    return {"states": [], "transitions": []}


class GlobalWorkflowDefinitionStore:
    """CRUD + graph edits for tenant-wide global workflow defaults (REQ-178)."""

    # ---------- Read ----------

    def get(
        self, tenant_id: UUID | str, item_type: str, preset: str
    ) -> GlobalWorkflowDefinition | None:
        """Return the global row for ``(tenant, item_type, preset)`` or None."""
        return GlobalWorkflowDefinition.unscoped.filter(
            tenant_id=tenant_id, item_type=item_type, preset=preset
        ).first()

    def list(
        self,
        tenant_id: UUID | str,
        *,
        item_type: str | None = None,
        preset: str | None = None,
    ) -> list[GlobalWorkflowDefinition]:
        """Return all global rows for the tenant, optionally filtered."""
        qs = GlobalWorkflowDefinition.unscoped.filter(tenant_id=tenant_id)
        if item_type:
            qs = qs.filter(item_type=item_type)
        if preset:
            qs = qs.filter(preset=preset)
        return list(qs.order_by("item_type", "preset"))

    # ---------- Bootstrap ----------

    def initialize(
        self, tenant_id: UUID | str, item_type: str, preset: str
    ) -> GlobalWorkflowDefinition:
        """Create an empty global definition for ``(item_type, preset)``.

        Raises:
            WorkflowDefinitionError: A row already exists ("already initialized"),
                mapped to 409 by the view.
        """
        existing = self.get(tenant_id, item_type, preset)
        if existing is not None:
            raise WorkflowDefinitionError(
                f"Global workflow definition for '{item_type}/{preset}' "
                f"already initialized"
            )
        return GlobalWorkflowDefinition.unscoped.create(
            tenant_id=tenant_id,
            item_type=item_type,
            preset=preset,
            workflow_json=_empty_graph(),
        )

    def get_or_seed_from_preset(
        self, tenant_id: UUID | str, item_type: str, preset: str
    ) -> GlobalWorkflowDefinition:
        """Return the global row, seeding it from ``PRESET_SCHEMAS`` if absent.

        Used by provisioning so a workspace can inherit a fully-formed default.
        The seed graph is a deep copy of the preset schema so the persisted row
        never shares a mutable reference with the module-level schema.
        """
        existing = self.get(tenant_id, item_type, preset)
        if existing is not None:
            return existing
        schema = PRESET_SCHEMAS.get(preset)
        seed = copy.deepcopy(schema) if schema is not None else _empty_graph()
        obj, _created = GlobalWorkflowDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            item_type=item_type,
            preset=preset,
            defaults={"workflow_json": seed},
        )
        return obj

    # ---------- Graph edits (+ propagation) ----------

    def _require(
        self, tenant_id: UUID | str, item_type: str, preset: str
    ) -> GlobalWorkflowDefinition:
        obj = self.get(tenant_id, item_type, preset)
        if obj is None:
            raise WorkflowDefinitionError(
                f"No global workflow definition for '{item_type}/{preset}'"
            )
        return obj

    @staticmethod
    def _graph(obj: GlobalWorkflowDefinition) -> tuple[list[str], list[dict]]:
        wf = obj.workflow_json or {}
        states = list(wf.get("states", []))
        transitions = [dict(t) for t in wf.get("transitions", [])]
        return states, transitions

    def _persist(
        self,
        obj: GlobalWorkflowDefinition,
        states: list[str],
        transitions: list[dict],
    ) -> int:
        """Persist the edited graph and propagate to non-customized derived rows.

        CR-09 (atomicity): the global row and its derived rows are ONE logical
        operation, so both writes share a single ``transaction.atomic()`` block.
        Without it, ``obj.save()`` ran in autocommit and a failure anywhere in
        ``_propagate()`` (SQL/DB error) left the tenant-wide default mutated
        while every ``is_customized=False`` derived row kept the previous graph
        — a silent divergence of the inheritance invariant that no reader
        detects afterwards, because both layers are individually valid graphs.
        Same fix shape as
        ``attribute_definitions/global_definition_store.py::_persist``'s caller.

        Tenant handling is unchanged: every statement here runs on the unscoped
        manager, so the block does not require an active ``TenantContext``; an
        already-open outer atomic block (e.g. a wrapping request/service
        transaction) is simply reused by ``atomic()``. Concretely, when a caller
        already holds the global row lock in an outer block (``delete_state``
        does), the nested ``atomic()`` opens a SAVEPOINT and the row lock is
        still held until the OUTERMOST commit — which is what lets that caller
        treat a check and this write as one indivisible unit.

        Note that the in-memory ``obj`` keeps the new graph even if the block
        rolls back — callers must not report success from a raised exception;
        every re-read goes through the ORM (see the fault-injection tests).
        """
        with transaction.atomic():
            obj.workflow_json = {"states": states, "transitions": transitions}
            obj.save(update_fields=["workflow_json", "modified_at"])
            propagated = self._propagate(obj)
        return propagated

    def _propagate(self, obj: GlobalWorkflowDefinition) -> int:
        """Copy ``workflow_json`` into every non-customized derived definition.

        Also invalidates TransitionValidator's in-process definition cache
        (workflow.transition_validator._definition_cache) for every affected
        workspace — this bulk QuerySet.update() bypasses save()/signals, so
        without an explicit invalidation here, TransitionValidator kept
        enforcing the stale pre-edit role/gate/transition rules for the rest
        of the worker process's life (code review finding: a role removed
        from allowed_roles, or a SignatureGate just added, would silently
        keep the old, more permissive behavior on any worker holding a cached
        copy).
        """
        affected_workspace_ids = list(
            WorkflowEngineDefinition.unscoped.filter(
                source_global_id=obj.id, is_customized=False
            ).values_list("workspace_id", flat=True)
        )
        count = WorkflowEngineDefinition.unscoped.filter(
            source_global_id=obj.id, is_customized=False
        ).update(workflow_json=copy.deepcopy(obj.workflow_json))

        if affected_workspace_ids:
            from .transition_validator import TransitionValidator

            validator = TransitionValidator()
            for workspace_id in affected_workspace_ids:
                validator.invalidate_cache(str(workspace_id), obj.item_type)

        return count

    def _non_customized_workspace_ids(
        self, obj: GlobalWorkflowDefinition
    ) -> list[str]:
        """Workspace IDs whose definition still mirrors ``obj`` (``is_customized=False``).

        Read through the unscoped manager, like every other query in this
        store: ``source_global_id`` is a globally unique FK target, so the
        derived rows it selects are necessarily the same tenant's — no
        cross-tenant leakage, and no active ``TenantContext`` required.
        """
        return [
            str(workspace_id)
            for workspace_id in WorkflowEngineDefinition.unscoped.filter(
                source_global_id=obj.id, is_customized=False
            ).values_list("workspace_id", flat=True)
        ]

    def _check_live_items_in_state(
        self, obj: GlobalWorkflowDefinition, state: str
    ) -> None:
        """Fail closed when a live item would be stranded by removing ``state``.

        CR-09b: the global template owns no ``WorkflowItemState`` row itself,
        but it is the source of truth for every non-customized derived
        workspace, and those workspaces DO carry live item states. Deleting a
        state that such an item still occupies would leave the item pointing at
        a state its own definition no longer declares — a workflow state that
        can never be transitioned out of and is invisible to the state
        transition validator. This is the global-level counterpart of
        ``WorkflowDefinitionStore._check_orphaned_state`` (REQ-L2-WE-004) and
        raises the same exception type, so both edit paths render one identical
        "move the items first" conflict in the UI.

        Customized workspaces (``is_customized=True``) are exempt by
        construction: they no longer mirror this template, so a global edit
        never reaches them and cannot strand their items.

        ROLLBACK FORM: this is a single fail-closed condition, not a schema
        step. To revert, delete the ``_check_live_items_in_state`` call (and
        optionally the method) from ``delete_state`` — no migration, no data
        backfill, no model change is involved. (Deferring is NOT an option: the
        stranding it prevents is silent and unrecoverable without a state
        mapping, so the gate stays fail-closed even though it can block admin
        deletions that previously succeeded.)
        """
        workspace_ids = self._non_customized_workspace_ids(obj)
        if not workspace_ids:
            return
        qs = WorkflowItemState.unscoped.filter(
            workspace_id__in=workspace_ids,
            item_type=obj.item_type,
            current_state=state,
        )
        count = qs.count()
        if count == 0:
            return
        # Collect up to 100 item IDs for the error message (same cap and
        # message shape as the per-workspace store).
        item_ids = list(qs.values_list("item_id", flat=True)[:100])
        raise OrphanedStateError(
            orphaned_state=state,
            count=count,
            item_ids=[str(i) for i in item_ids],
        )

    def add_state(
        self, tenant_id: UUID | str, item_type: str, preset: str, name: str
    ) -> tuple[GlobalWorkflowDefinition, int]:
        obj = self._require(tenant_id, item_type, preset)
        clean = WorkflowDefinitionStore._validate_state_name(name)
        states, transitions = self._graph(obj)
        if clean in states:
            raise WorkflowDefinitionError(f"State '{clean}' already exists")
        states.append(clean)
        count = self._persist(obj, states, transitions)
        return obj, count

    def rename_state(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        old_name: str,
        new_name: str,
    ) -> tuple[GlobalWorkflowDefinition, int]:
        obj = self._require(tenant_id, item_type, preset)
        clean = WorkflowDefinitionStore._validate_state_name(new_name)
        states, transitions = self._graph(obj)
        if old_name not in states:
            raise WorkflowDefinitionError(f"Unknown state '{old_name}'")
        if clean != old_name and clean in states:
            raise WorkflowDefinitionError(f"State '{clean}' already exists")
        states = [clean if s == old_name else s for s in states]
        for t in transitions:
            if t["from_state"] == old_name:
                t["from_state"] = clean
            if t["to_state"] == old_name:
                t["to_state"] = clean
        count = self._persist(obj, states, transitions)
        return obj, count

    def delete_state(
        self, tenant_id: UUID | str, item_type: str, preset: str, name: str
    ) -> tuple[GlobalWorkflowDefinition, int]:
        """Remove a state and propagate the shortened graph.

        Two independent blocks, both enforced BEFORE any write:

        1. structural — the state must not be referenced by a transition
           (:class:`StateReferencedError`),
        2. live items — no item in a non-customized inheriting workspace may
           sit in the state (:class:`OrphanedStateError`, CR-09b).

        BOTH blocks and the write run inside a single ``transaction.atomic()``
        that first re-reads the global row under ``select_for_update()``. The
        earlier shape called ``_check_live_items_in_state`` in its own
        transaction and then let ``_persist`` open a SECOND one for the write,
        so an item could enter the doomed state inside that window and the
        delete would then strand it — a check-then-act that was not fail-closed
        despite the wording. The row lock also serialises two admins editing
        the same template: without it, a concurrent ``rename_state`` could land
        between the graph read and the persist and be silently overwritten.

        Raises:
            WorkflowDefinitionError: no such global row / unknown state name.
            StateReferencedError: a transition references the state.
            OrphanedStateError: live items would be stranded (fail-closed).

        KNOWN RESIDUAL WINDOW (honest, not closed by this method): the
        transaction above makes the gate atomic with respect to the global
        template and to any other admin edit of it, but it cannot lock the
        ``WorkflowItemState`` rows it merely *counts* — a concurrent transition
        on another connection can still move an item INTO ``name`` after the
        count and before this transaction commits. In practice the structural
        gate narrows that window to nearly nothing: the state is only deletable
        when NO transition references it, and
        ``TransitionValidator`` Rule 1 requires a declared edge
        (``definition.get_transition(from, to)``), so no validated transition
        can target it — a racing writer would have to be validating against a
        stale in-process definition cache
        (``workflow.transition_validator._definition_cache``). Closing the
        remainder properly means a state-declaration check on the transition
        write path itself (reject a ``target_state`` the item's own
        ``WorkflowEngineDefinition`` does not declare). That is a new fail-closed
        validation rule on the engine's hottest write path for EVERY item type,
        not a local fix, so it is deliberately NOT smuggled in here.
        """
        obj = self._require(tenant_id, item_type, preset)
        with transaction.atomic():
            locked = GlobalWorkflowDefinition.unscoped.select_for_update().get(pk=obj.pk)
            states, transitions = self._graph(locked)
            if name not in states:
                raise WorkflowDefinitionError(f"Unknown state '{name}'")
            referencing = [
                f"{t['from_state']} -> {t['to_state']}"
                for t in transitions
                if t["from_state"] == name or t["to_state"] == name
            ]
            if referencing:
                raise StateReferencedError(name, referencing)
            # CR-09b: fail closed before touching the graph. Checked after the
            # structural gate so the pre-existing StateReferencedError precedence
            # (a purely local, cheaper check) is unchanged for callers.
            self._check_live_items_in_state(locked, name)
            states = [s for s in states if s != name]
            count = self._persist(locked, states, transitions)
        # Return the LOCKED instance, not the pre-lock ``obj``: ``_persist``
        # writes the shortened graph onto the instance it is handed, so
        # returning ``obj`` would hand the caller a stale graph (the very
        # "the response still shows the deleted state" shape the REST
        # serializer would render).
        return locked, count

    def add_transition(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        from_state: str,
        to_state: str,
        *,
        allowed_roles: list[str] | None = None,
        requires_change_reason: bool = False,
        signature_gate: bool = False,
    ) -> tuple[GlobalWorkflowDefinition, int]:
        obj = self._require(tenant_id, item_type, preset)
        states, transitions = self._graph(obj)
        if from_state not in states:
            raise WorkflowDefinitionError(f"Unknown from_state '{from_state}'")
        if to_state not in states:
            raise WorkflowDefinitionError(f"Unknown to_state '{to_state}'")
        for t in transitions:
            if t["from_state"] == from_state and t["to_state"] == to_state:
                raise WorkflowDefinitionError(
                    f"Transition '{from_state} -> {to_state}' already exists"
                )
        roles = [r for r in (allowed_roles or []) if r and r.strip()]
        if "admin" not in roles:
            roles.append("admin")
        transitions.append(
            {
                "from_state": from_state,
                "to_state": to_state,
                "allowed_roles": roles,
                "requires_change_reason": bool(requires_change_reason),
                "signature_gate": bool(signature_gate),
            }
        )
        count = self._persist(obj, states, transitions)
        return obj, count

    def update_transition(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        from_state: str,
        to_state: str,
        *,
        allowed_roles: list[str] | None = None,
        requires_change_reason: bool | None = None,
        signature_gate: bool | None = None,
    ) -> tuple[GlobalWorkflowDefinition, int]:
        obj = self._require(tenant_id, item_type, preset)
        states, transitions = self._graph(obj)
        target = next(
            (
                t
                for t in transitions
                if t["from_state"] == from_state and t["to_state"] == to_state
            ),
            None,
        )
        if target is None:
            raise WorkflowDefinitionError(
                f"Unknown transition '{from_state} -> {to_state}'"
            )
        if allowed_roles is not None:
            roles = [r for r in allowed_roles if r and r.strip()]
            if "admin" not in roles:
                roles.append("admin")
            target["allowed_roles"] = roles
        if requires_change_reason is not None:
            target["requires_change_reason"] = bool(requires_change_reason)
        if signature_gate is not None:
            target["signature_gate"] = bool(signature_gate)
        count = self._persist(obj, states, transitions)
        return obj, count

    def delete_transition(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        from_state: str,
        to_state: str,
    ) -> tuple[GlobalWorkflowDefinition, int]:
        obj = self._require(tenant_id, item_type, preset)
        states, transitions = self._graph(obj)
        remaining = [
            t
            for t in transitions
            if not (t["from_state"] == from_state and t["to_state"] == to_state)
        ]
        if len(remaining) == len(transitions):
            raise WorkflowDefinitionError(
                f"Unknown transition '{from_state} -> {to_state}'"
            )
        count = self._persist(obj, states, remaining)
        return obj, count


__all__ = ["GlobalWorkflowDefinitionStore"]
