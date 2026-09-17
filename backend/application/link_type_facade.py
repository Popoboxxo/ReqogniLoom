"""Layer-2 facade over the LinkTypeCatalog (ADR-01, single entry point).

``rest_api`` and ``mcp_server`` reach the catalog only through here, exactly
as they reach the workflow definitions through ``application.workflow_facade``.
Two things the stores below deliberately do not do live at this layer:

* **Authorisation** — the global scope is tenant-admin only.
* **JSON safety** — the MCP transport serialises tool payloads with stdlib
  ``json.dumps``, which raises on a ``UUID`` or ``datetime`` and reaches the
  caller as an opaque INTERNAL_ERROR. Every dict returned from here is already
  primitive-only, so neither transport has to remember.
"""
from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from auth_tenancy.context import AuthContext
from link_types.global_store import GlobalLinkTypeDefinitionStore
from link_types.workspace_store import WorkspaceLinkTypeDefinitionStore
from persistence.errors import PermissionDeniedError

from .base import ServiceBase

_ADMIN_ROLES = frozenset({"admin", "tenant_admin"})


def _global_to_dict(row: Any, *, propagated_to: int | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": str(row.id),
        "key": row.key,
        "definition": row.definition_json or {},
        "version": row.version,
    }
    if propagated_to is not None:
        payload["propagated_to"] = propagated_to
    return payload


def _workspace_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "key": row.key,
        "definition": row.definition_json or {},
        "is_customized": row.is_customized,
        "source_global_id": (
            str(row.source_global_id) if row.source_global_id else None
        ),
        "version": row.version,
    }


class LinkTypeFacade(ServiceBase):
    """Read/write entry point for global and per-workspace link types."""

    def __init__(self) -> None:
        super().__init__()
        self._global = GlobalLinkTypeDefinitionStore()
        self._workspace = WorkspaceLinkTypeDefinitionStore()

    # ---------- guards ----------

    @staticmethod
    def _require_admin(ctx: AuthContext) -> None:
        """Global link types are tenant-wide configuration: admin only."""
        if not any(ctx.has_role(role) for role in _ADMIN_ROLES):
            raise PermissionDeniedError(
                "Editing link-type defaults requires a tenant administrator role."
            )

    # ---------- global scope ----------

    def list_global(self, ctx: AuthContext) -> List[Dict[str, Any]]:
        """Return every global link-type template of the tenant."""
        self._set_tenant_context(ctx)
        return [_global_to_dict(row) for row in self._global.list(ctx.tenant_id)]

    def create_global(
        self, ctx: AuthContext, key: str, definition: Any
    ) -> Dict[str, Any]:
        """Create a new tenant-wide link type."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row = self._global.create(ctx.tenant_id, key, definition)
        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="GlobalLinkTypeDefinition",
            entity_id=row.id,
        )
        return _global_to_dict(row)

    def update_global(
        self, ctx: AuthContext, key: str, definition: Any
    ) -> Dict[str, Any]:
        """Replace a global template and propagate it to on-default workspaces."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row, propagated = self._global.update(ctx.tenant_id, key, definition)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="GlobalLinkTypeDefinition",
            entity_id=row.id,
        )
        return _global_to_dict(row, propagated_to=propagated)

    def delete_global(self, ctx: AuthContext, key: str) -> None:
        """Delete a global template (workspace overrides survive, unlinked)."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row = self._global.get(ctx.tenant_id, key)
        self._global.delete(ctx.tenant_id, key)
        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="GlobalLinkTypeDefinition",
            entity_id=row.id if row is not None else None,
        )

    # ---------- workspace scope ----------

    def list_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> List[Dict[str, Any]]:
        """Return the resolved catalog rows of a workspace, inactive ones included.

        Read-only, so no admin gate: the trace-link dialog and the MCP schema
        validator both need this on every ordinary request.
        """
        self._set_tenant_context(ctx)
        return [
            _workspace_to_dict(row)
            for row in self._workspace.list(ctx.tenant_id, workspace_id)
        ]

    def update_workspace(
        self,
        ctx: AuthContext,
        workspace_id: UUID | str,
        key: str,
        definition: Any,
    ) -> Dict[str, Any]:
        """Override one link type for one workspace."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row = self._workspace.update(ctx.tenant_id, workspace_id, key, definition)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="WorkspaceLinkTypeDefinition",
            entity_id=row.id,
        )
        return _workspace_to_dict(row)

    def reset_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str, key: str
    ) -> Dict[str, Any]:
        """Restore a workspace override to its default."""
        self._set_tenant_context(ctx)
        self._require_admin(ctx)
        row = self._workspace.reset(ctx.tenant_id, workspace_id, key)
        self._audit(
            ctx=ctx,
            operation="update",
            entity_type="WorkspaceLinkTypeDefinition",
            entity_id=row.id,
        )
        return _workspace_to_dict(row)


__all__ = ["LinkTypeFacade"]
