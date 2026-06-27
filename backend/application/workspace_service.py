"""
COMP-AS-WS WorkspaceService — read-only Workspace lookup (REQ-L1-017).

Provides a single-entry-point (ADR-01) facade over the ``persistence.Workspace``
ORM for the REST API and MCP server. Workspaces are managed today via seeding
and the admin tooling; this service exposes the read-only surface that
downstream adapters need (list current tenant's workspaces, retrieve one by
id) without bypassing the application layer.

Interfaces consumed:
  IF-AS-EXT-OUT-007 persistence.models.Workspace (Django ORM)
  persistence.tenancy.TenantContext         (tenant scoping)
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.models import Workspace

from application.base import NotFoundError, ServiceBase

logger = logging.getLogger(__name__)


class WorkspaceService(ServiceBase):
    """COMP-AS-WS — read-only Workspace queries scoped to the active tenant."""

    # ---------- Read API ----------

    def list_workspaces(self, ctx: AuthContext) -> List[Workspace]:
        """Return all workspaces visible to *ctx*'s tenant.

        Tenant scoping is enforced by ``TenantContext`` via the default
        ``objects`` manager. Order: most recently modified first.
        """
        self._set_tenant_context(ctx)
        return list(Workspace.objects.all().order_by("-modified_at"))

    def get_workspace(self, workspace_id: UUID, ctx: AuthContext) -> Workspace:
        """Return a single workspace by id, scoped to the active tenant.

        Raises:
            NotFoundError: workspace does not exist or is in another tenant.
        """
        self._set_tenant_context(ctx)
        workspace: Optional[Workspace] = Workspace.objects.filter(
            id=workspace_id
        ).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return workspace


__all__ = ["WorkspaceService"]
