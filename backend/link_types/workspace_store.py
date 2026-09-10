"""Per-workspace link-type overrides, reset-to-default and provisioning.

Provisioning intentionally seeds *rows*, not a lazy merge: the catalog is
read on every single link creation, so a materialized copy keeps the hot path
to one indexed query with no fallback branch.

``provision_workspace_link_types`` is idempotent (``get_or_create``), which is
what lets the backfill migration, ``application.workspace_provisioning`` and a
manual re-run all call it safely.
"""
from __future__ import annotations

import copy
from typing import Any, List, Optional
from uuid import UUID

from django.db import transaction

from persistence.errors import ValidationError

from .builtin import BUILTIN_LINK_TYPES, builtin_definition
from .catalog import invalidate_workspace
from .models import GlobalLinkTypeDefinition, WorkspaceLinkTypeDefinition
from .schema import validate_definition_json


class WorkspaceLinkTypeDefinitionStore:
    """Read/override/reset over ``WorkspaceLinkTypeDefinition``."""

    def get(
        self, tenant_id: UUID | str, workspace_id: UUID | str, key: str
    ) -> Optional[WorkspaceLinkTypeDefinition]:
        """Return the workspace row for *key*, or None."""
        return WorkspaceLinkTypeDefinition.unscoped.filter(
            tenant_id=tenant_id, workspace_id=workspace_id, key=key
        ).first()

    def list(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> List[WorkspaceLinkTypeDefinition]:
        """Return every workspace row, ordered by key (including inactive ones).

        The editor UI must see deactivated types to be able to re-enable them,
        so this is deliberately *not* filtered by ``active`` the way
        ``catalog.resolve_catalog`` is.
        """
        return list(
            WorkspaceLinkTypeDefinition.unscoped.filter(
                tenant_id=tenant_id, workspace_id=workspace_id
            ).order_by("key")
        )

    @transaction.atomic
    def update(
        self,
        tenant_id: UUID | str,
        workspace_id: UUID | str,
        key: str,
        definition_json: Any,
    ) -> WorkspaceLinkTypeDefinition:
        """Override a definition for one workspace (sets ``is_customized=True``).

        Raises:
            ValidationError: Unknown key or malformed definition.
        """
        row = self.get(tenant_id, workspace_id, key)
        if row is None:
            raise ValidationError(
                f"Link type '{key}' not found in this workspace."
            )
        row.definition_json = validate_definition_json(definition_json, key=key)
        row.is_customized = True
        row.version = (row.version or 1) + 1
        row.save(update_fields=["definition_json", "is_customized", "version"])
        invalidate_workspace(str(workspace_id))
        return row

    @transaction.atomic
    def reset(
        self, tenant_id: UUID | str, workspace_id: UUID | str, key: str
    ) -> WorkspaceLinkTypeDefinition:
        """Restore the workspace row from its default and clear the override flag.

        Default source order: the linked ``source_global`` row, then the
        built-in definition. A tenant-invented type that has neither has no
        default to fall back to, which is an error rather than a silent no-op.

        Raises:
            ValidationError: Unknown key, or no default exists.
        """
        row = self.get(tenant_id, workspace_id, key)
        if row is None:
            raise ValidationError(f"Link type '{key}' not found in this workspace.")

        default: Optional[dict] = None
        if row.source_global_id is not None:
            global_row = GlobalLinkTypeDefinition.unscoped.filter(
                id=row.source_global_id
            ).first()
            if global_row is not None:
                default = copy.deepcopy(global_row.definition_json)
        if default is None and key in BUILTIN_LINK_TYPES:
            default = builtin_definition(key)
        if default is None:
            raise ValidationError(
                f"Link type '{key}' has no default to reset to: it is neither "
                f"a built-in type nor derived from a global definition."
            )

        row.definition_json = default
        row.is_customized = False
        row.version = (row.version or 1) + 1
        row.save(update_fields=["definition_json", "is_customized", "version"])
        invalidate_workspace(str(workspace_id))
        return row


def provision_workspace_link_types(
    *, workspace_id: UUID | str, tenant_id: UUID | str
) -> int:
    """Seed the eight built-in link types for a workspace. Idempotent.

    Ensures the tenant's global templates exist first (creating any that are
    missing from ``BUILTIN_LINK_TYPES``), then materializes one workspace row
    per template. Existing rows — customized or not — are left untouched.

    Args:
        workspace_id: Target workspace UUID.
        tenant_id: Owning tenant UUID. Passed explicitly because the
            ``get_or_create`` calls below run on the unscoped QuerySet,
            bypassing the tenant manager's auto-inject on create — the same
            reason ``provision_workspace_defaults`` takes it.

    Returns:
        Number of workspace rows created (0 on a repeat run).
    """
    created = 0
    for key in sorted(BUILTIN_LINK_TYPES):
        global_row, _ = GlobalLinkTypeDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            key=key,
            defaults={"definition_json": builtin_definition(key), "version": 1},
        )
        _row, was_created = WorkspaceLinkTypeDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            key=key,
            defaults={
                "definition_json": copy.deepcopy(global_row.definition_json),
                "source_global": global_row,
                "is_customized": False,
                "version": 1,
            },
        )
        created += int(was_created)

    if created:
        invalidate_workspace(str(workspace_id))
    return created


__all__ = [
    "WorkspaceLinkTypeDefinitionStore",
    "provision_workspace_link_types",
]
