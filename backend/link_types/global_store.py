"""CRUD + propagation for tenant-wide global link-type templates.

Mirrors ``workflow.global_definition_store.GlobalWorkflowDefinitionStore``:
an edit here is copied into every ``is_customized=False`` derived workspace
row (materialized copy, not merge-on-read), and each affected workspace's
resolved catalog cache is invalidated explicitly — the bulk
``QuerySet.update()`` bypasses ``save()``/signals, so without it every worker
would keep validating against the pre-edit pairs for the rest of its life.

``unscoped`` is used deliberately: these helpers are called with an explicit
``tenant_id`` from admin endpoints and from the seed migration, and RLS
remains the second isolation layer underneath either way.
"""
from __future__ import annotations

import copy
from typing import Any, List, Optional, Tuple
from uuid import UUID

from django.db import transaction

from persistence.errors import ValidationError

from .catalog import invalidate_workspace
from .models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from .schema import validate_definition_json

#: Flags a tenant may never flip on a system-owned type. ``diagram-ref`` is
#: reconciler-owned; unlocking it would let a hand-authored link be silently
#: deleted on the diagram's next node_graph save.
_LOCKED_FLAGS = ("system_owned", "manual_creatable")


class GlobalLinkTypeDefinitionStore:
    """Tenant-admin CRUD over ``GlobalLinkTypeDefinition``."""

    # ---------- Read ----------

    def get(
        self, tenant_id: UUID | str, key: str
    ) -> Optional[GlobalLinkTypeDefinition]:
        """Return the global row for ``(tenant, key)`` or None."""
        return GlobalLinkTypeDefinition.unscoped.filter(
            tenant_id=tenant_id, key=key
        ).first()

    def list(self, tenant_id: UUID | str) -> List[GlobalLinkTypeDefinition]:
        """Return every global row of the tenant, ordered by key."""
        return list(
            GlobalLinkTypeDefinition.unscoped.filter(tenant_id=tenant_id).order_by("key")
        )

    # ---------- Write ----------

    @transaction.atomic
    def create(
        self, tenant_id: UUID | str, key: str, definition_json: Any
    ) -> GlobalLinkTypeDefinition:
        """Create a new global template.

        Raises:
            ValidationError: The key already exists, or the definition is
                malformed.
        """
        if not key or not key.strip():
            raise ValidationError("Link type key must not be empty.")
        if self.get(tenant_id, key) is not None:
            raise ValidationError(f"Link type '{key}' already exists for this tenant.")
        validated = validate_definition_json(definition_json, key=key)
        return GlobalLinkTypeDefinition.unscoped.create(
            tenant_id=tenant_id, key=key, definition_json=validated, version=1
        )

    @transaction.atomic
    def update(
        self, tenant_id: UUID | str, key: str, definition_json: Any
    ) -> Tuple[GlobalLinkTypeDefinition, int]:
        """Replace a global template and propagate it.

        Returns:
            ``(row, propagated_count)`` — how many non-customized workspace
            rows received the new definition.

        Raises:
            ValidationError: Unknown key, malformed definition, or an attempt
                to unlock a system-owned type.
        """
        row = self.get(tenant_id, key)
        if row is None:
            raise ValidationError(f"Link type '{key}' not found for this tenant.")

        validated = validate_definition_json(definition_json, key=key)
        current = row.definition_json or {}
        if current.get("system_owned"):
            for flag in _LOCKED_FLAGS:
                if validated.get(flag) != current.get(flag):
                    raise ValidationError(
                        f"'{key}' is a system-managed link type: '{flag}' is "
                        f"locked and cannot be changed."
                    )

        row.definition_json = validated
        row.version = (row.version or 1) + 1
        row.save(update_fields=["definition_json", "version"])
        return row, self._propagate(row)

    @transaction.atomic
    def delete(self, tenant_id: UUID | str, key: str) -> None:
        """Delete a global template.

        Deliberately does **not** touch derived workspace rows: their
        ``source_global`` FK is SET_NULL, so they survive as standalone
        definitions. Deactivating a type across a tenant is done by setting
        ``active=False`` via :meth:`update`, which propagates — hard-deleting
        the template is an admin cleanup, not a soft-disable.

        Raises:
            ValidationError: Unknown key, or the type is system-owned.
        """
        row = self.get(tenant_id, key)
        if row is None:
            raise ValidationError(f"Link type '{key}' not found for this tenant.")
        if (row.definition_json or {}).get("system_owned"):
            raise ValidationError(
                f"'{key}' is a system-managed link type and cannot be deleted."
            )
        row.delete()

    # ---------- Propagation ----------

    def _propagate(self, row: GlobalLinkTypeDefinition) -> int:
        """Copy ``definition_json`` into every non-customized derived row.

        Invalidates the resolved-catalog cache of each affected workspace: the
        bulk update below bypasses ``save()``/signals, so without this every
        other worker keeps validating against the stale pre-edit pairs.
        """
        derived = WorkspaceLinkTypeDefinition.unscoped.filter(
            source_global_id=row.id, is_customized=False
        )
        affected = list(derived.values_list("workspace_id", flat=True))
        count = derived.update(definition_json=copy.deepcopy(row.definition_json))
        for workspace_id in affected:
            invalidate_workspace(str(workspace_id))
        return count


__all__ = ["GlobalLinkTypeDefinitionStore"]
