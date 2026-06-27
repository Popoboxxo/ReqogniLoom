"""
COMP-AS-WS WorkspaceService — Workspace lookup + creation (REQ-L1-017).

Provides a single-entry-point (ADR-01) facade over the ``persistence.Workspace``
ORM for the REST API and MCP server. Read paths (list/get) are tenant-scoped
via ``TenantContext``; the write path (``create_workspace``) provisions a new
Workspace together with its ``WorkspacePresetConfig`` companion so the
preset/terminology profile selection is persisted from the start.

Interfaces consumed:
  IF-AS-EXT-OUT-007 persistence.models.Workspace (Django ORM)
  persistence.tenancy.TenantContext         (tenant scoping)
  persistence.transactions.atomic_transaction (ACID write path)
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from auth_tenancy.context import AuthContext
from persistence.models import Tenant, Workspace
from persistence.transactions import atomic_transaction
from presets.models import (
    PRESET_CHOICES,
    TERMINOLOGY_CHOICES,
    WorkspacePresetConfig,
)

from application.base import NotFoundError, ServiceBase, ValidationError

logger = logging.getLogger(__name__)


_VALID_PRESETS = {key for key, _ in PRESET_CHOICES}
_VALID_TERMINOLOGY_PROFILES = {key for key, _ in TERMINOLOGY_CHOICES}


class WorkspaceService(ServiceBase):
    """COMP-AS-WS — Workspace queries + create scoped to the active tenant."""

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

    # ---------- Write API ----------

    @atomic_transaction
    def create_workspace(
        self,
        ctx: AuthContext,
        name: str,
        preset: str = "standard",
        terminology_profile: str = "se_mode",
        language: str = "de",
    ) -> Workspace:
        """Create a Workspace + its WorkspacePresetConfig companion.

        ``preset`` and ``terminology_profile`` are validated against the
        canonical choice lists in ``presets.models``. ``language`` is reserved
        for a future per-workspace setting and currently stored only on the
        Workspace.preset JSON blob alongside the tier (the Workspace model
        does not have a dedicated language column yet).

        REQ-L2-AS-018 (ACID), REQ-L2-AS-019 (Audit), REQ-L2-AS-021 (Auth),
        REQ-L2-AS-022 (Tenant scoping).
        """
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        name_clean = (name or "").strip()
        if not name_clean:
            raise ValidationError("name is required")

        if preset not in _VALID_PRESETS:
            raise ValidationError(
                f"Invalid preset '{preset}'. Valid: {sorted(_VALID_PRESETS)}"
            )
        if terminology_profile not in _VALID_TERMINOLOGY_PROFILES:
            raise ValidationError(
                f"Invalid terminology_profile '{terminology_profile}'. "
                f"Valid: {sorted(_VALID_TERMINOLOGY_PROFILES)}"
            )

        tenant = Tenant.objects.filter(id=ctx.tenant_id).first()
        if tenant is None:
            raise NotFoundError(f"Tenant {ctx.tenant_id} not found")

        workspace = Workspace.objects.create(
            tenant=tenant,
            name=name_clean,
            preset={
                "tier": preset,
                "terminology_profile": terminology_profile,
                "language": language,
            },
        )

        WorkspacePresetConfig.objects.create(
            tenant=tenant,
            workspace=workspace,
            active_tier=preset,
            terminology_profile=terminology_profile,
        )

        self._audit(
            ctx=ctx,
            operation="create",
            entity_type="Workspace",
            entity_id=workspace.id,
            details={
                "name": name_clean,
                "preset": preset,
                "terminology_profile": terminology_profile,
                "language": language,
            },
        )

        return workspace


__all__ = ["WorkspaceService"]
