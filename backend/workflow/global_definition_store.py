"""REQ-178 — GlobalWorkflowDefinition store: tenant-wide per-preset defaults.

CRUD + graph editing for :class:`GlobalWorkflowDefinition`, the tenant-wide
source-of-truth from which non-customized per-workspace
:class:`WorkflowEngineDefinition` rows inherit. Structurally symmetric to
:class:`workflow.definition_store.WorkflowDefinitionStore` but operates on the
global template (no live ``WorkflowItemState`` rows exist for a global, so
orphaned-item checks do not apply — only structural graph integrity is enforced).

Every mutation persists the global row and PROPAGATES ``workflow_json`` into
every ``is_customized=False`` derived definition of the SAME preset, returning
the propagated workspace count so the UI can surface it.
"""
from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from .definition_store import (
    PRESET_SCHEMAS,
    StateReferencedError,
    WorkflowDefinitionError,
    WorkflowDefinitionStore,
)
from .models import GlobalWorkflowDefinition, WorkflowEngineDefinition


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
        """Persist the edited graph and propagate to non-customized derived rows."""
        obj.workflow_json = {"states": states, "transitions": transitions}
        obj.save(update_fields=["workflow_json", "modified_at"])
        return self._propagate(obj)

    def _propagate(self, obj: GlobalWorkflowDefinition) -> int:
        """Copy ``workflow_json`` into every non-customized derived definition."""
        return WorkflowEngineDefinition.unscoped.filter(
            source_global_id=obj.id, is_customized=False
        ).update(workflow_json=copy.deepcopy(obj.workflow_json))

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
        obj = self._require(tenant_id, item_type, preset)
        states, transitions = self._graph(obj)
        if name not in states:
            raise WorkflowDefinitionError(f"Unknown state '{name}'")
        referencing = [
            f"{t['from_state']} -> {t['to_state']}"
            for t in transitions
            if t["from_state"] == name or t["to_state"] == name
        ]
        if referencing:
            raise StateReferencedError(name, referencing)
        states = [s for s in states if s != name]
        count = self._persist(obj, states, transitions)
        return obj, count

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
