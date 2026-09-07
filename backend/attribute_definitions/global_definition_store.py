"""Store for the tenant-wide ``GlobalAttributeDefinition`` rows.

Structurally symmetric to ``workflow.global_definition_store``: every mutation
persists the global row and PROPAGATES ``definition_json`` into every
``is_customized=False`` derived definition of the SAME preset, returning the
propagated workspace count so the UI can surface it.

Uses ``unscoped`` on purpose: the tenant is passed explicitly by the caller
(the service already asserted the admin role for that tenant), which mirrors
``GlobalWorkflowDefinitionStore`` and keeps the store usable from management
commands and data migrations where no thread-local tenant is armed.
"""
from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from .models import GlobalAttributeDefinition, WorkspaceAttributeDefinition
from .schema import (
    AttributeSchemaError,
    validate_definition_json,
    validate_meta_only_change,
)


class AttributeDefinitionNotFound(LookupError):
    """No definition row exists for the requested key."""


class GlobalAttributeDefinitionStore:
    """CRUD + propagation for tenant-wide global attribute defaults."""

    # ---------- Read ----------

    def get(
        self, tenant_id: UUID | str, item_type: str, preset: str
    ) -> GlobalAttributeDefinition | None:
        """Return the global row for ``(tenant, item_type, preset)`` or None."""
        return GlobalAttributeDefinition.unscoped.filter(
            tenant_id=tenant_id, item_type=item_type, preset=preset
        ).first()

    def list(
        self,
        tenant_id: UUID | str,
        *,
        item_type: str | None = None,
        preset: str | None = None,
    ) -> list[GlobalAttributeDefinition]:
        """Return all global rows for the tenant, optionally filtered."""
        qs = GlobalAttributeDefinition.unscoped.filter(tenant_id=tenant_id)
        if item_type:
            qs = qs.filter(item_type=item_type)
        if preset:
            qs = qs.filter(preset=preset)
        return list(qs.order_by("item_type", "preset"))

    # ---------- Write ----------

    def initialize(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> GlobalAttributeDefinition:
        """Create the global definition for ``(item_type, preset)``.

        Raises:
            AttributeSchemaError: a row already exists, or *attributes* is
                malformed. The view maps the "already initialized" case to 409.
        """
        if self.get(tenant_id, item_type, preset) is not None:
            raise AttributeSchemaError(
                [
                    f"Global attribute definition for '{item_type}/{preset}' "
                    f"is already initialized"
                ]
            )
        payload = validate_definition_json({"attributes": attributes})
        return GlobalAttributeDefinition.unscoped.create(
            tenant_id=tenant_id,
            item_type=item_type,
            preset=preset,
            definition_json=payload,
        )

    def update(
        self,
        tenant_id: UUID | str,
        item_type: str,
        preset: str,
        attributes: list[dict[str, Any]],
    ) -> tuple[GlobalAttributeDefinition, int]:
        """Replace the attribute list, bump ``version``, propagate.

        Returns:
            ``(row, propagated_workspace_count)``.

        Raises:
            AttributeDefinitionNotFound: no global row for that key.
            AttributeSchemaError: malformed payload, or a change that the
                core-lock / ``locked`` rules forbid.
        """
        obj = self.get(tenant_id, item_type, preset)
        if obj is None:
            raise AttributeDefinitionNotFound(
                f"No global attribute definition for '{item_type}/{preset}'"
            )
        payload = validate_definition_json({"attributes": attributes})
        old = (obj.definition_json or {}).get("attributes", [])
        validate_meta_only_change(old, payload["attributes"])

        obj.definition_json = payload
        obj.version = (obj.version or 1) + 1
        obj.save(update_fields=["definition_json", "version", "modified_at"])
        return obj, self._propagate(obj)

    # ---------- Propagation ----------

    def _propagate(self, obj: GlobalAttributeDefinition) -> int:
        """Copy ``definition_json`` into every non-customized derived row.

        ``preset`` is part of the derived row's identity, so the filter narrows
        on it too: a standard-preset edit must never rewrite a minimal-preset
        workspace that happens to point at a stale ``source_global``.

        ``copy.deepcopy`` is load-bearing: without it every derived row would
        share one mutable dict with the global, so an in-place edit on one row
        would silently rewrite the tenant default and all of its siblings.
        """
        return WorkspaceAttributeDefinition.unscoped.filter(
            source_global_id=obj.id,
            preset=obj.preset,
            is_customized=False,
        ).update(definition_json=copy.deepcopy(obj.definition_json))


__all__ = ["AttributeDefinitionNotFound", "GlobalAttributeDefinitionStore"]
