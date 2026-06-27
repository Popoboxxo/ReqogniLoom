"""
COMP-AS-WS WorkspaceService — Workspace lookup + creation (REQ-L1-017).

Provides a single-entry-point (ADR-01) facade over the ``persistence.Workspace``
ORM for the REST API and MCP server. Read paths (list/get) are tenant-scoped
via ``TenantContext``; the write path (``create_workspace``) provisions a new
Workspace together with its ``WorkspacePresetConfig`` companion so the
preset/terminology profile selection is persisted from the start.

Lifecycle operations (REQ-L1-042):
  ``close_workspace``     — soft-delete (is_active=False, closed_at, closed_by).
  ``reactivate_workspace`` — undo close (is_active=True, clear closed_at/by).
  ``delete_workspace``    — hard-delete with captcha confirmation + full cascade.

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
from django.utils import timezone
from persistence.models import (
    ArchitectureElement,
    Artifact,
    AuditLogEntry,
    Baseline,
    Requirement,
    TestCase,
    Tenant,
    TraceLink,
    Workspace,
)
from persistence.transactions import atomic_transaction
from presets.models import (
    PRESET_CHOICES,
    TERMINOLOGY_CHOICES,
    WorkspacePresetConfig,
)

from application.base import NotFoundError, PermissionDeniedError, ServiceBase, ValidationError

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

    # ---------- Lifecycle API (REQ-L1-042) ----------

    @atomic_transaction
    def close_workspace(self, workspace_id: UUID, ctx: AuthContext) -> Workspace:
        """Soft-delete a workspace (REQ-L1-042).

        Sets ``is_active=False``, ``closed_at=now``, ``closed_by=ctx.user_id``.
        Data is preserved; the workspace can be reactivated later.

        Requires ``admin`` role (COMP-AT-002).

        Raises:
            NotFoundError: workspace does not exist.
            PermissionDeniedError: user lacks admin role.
        """
        self._set_tenant_context(ctx)
        self._assert_permission(ctx, "admin")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        workspace.is_active = False
        workspace.closed_at = timezone.now()
        workspace.closed_by_id = ctx.user_id
        workspace.save(update_fields=["is_active", "closed_at", "closed_by"])

        self._audit(
            ctx=ctx,
            operation="workspace.close",
            entity_type="Workspace",
            entity_id=workspace.id,
            details={"name": workspace.name},
        )

        return workspace

    @atomic_transaction
    def reactivate_workspace(self, workspace_id: UUID, ctx: AuthContext) -> Workspace:
        """Undo a workspace close (REQ-L1-042).

        Sets ``is_active=True``, ``closed_at=None``, ``closed_by=None``.

        Requires ``admin`` role (COMP-AT-002).

        Raises:
            NotFoundError: workspace does not exist.
            PermissionDeniedError: user lacks admin role.
        """
        self._set_tenant_context(ctx)
        self._assert_permission(ctx, "admin")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        workspace.is_active = True
        workspace.closed_at = None
        workspace.closed_by = None
        workspace.save(update_fields=["is_active", "closed_at", "closed_by"])

        self._audit(
            ctx=ctx,
            operation="workspace.reactivate",
            entity_type="Workspace",
            entity_id=workspace.id,
            details={"name": workspace.name},
        )

        return workspace

    @atomic_transaction
    def delete_workspace(
        self,
        workspace_id: UUID,
        confirmation_text: str,
        ctx: AuthContext,
    ) -> None:
        """Hard-delete a workspace with captcha confirmation (REQ-L1-042).

        Validates that ``confirmation_text`` matches the workspace name
        (case-sensitive). If valid, performs a full cascade delete in this order:
          1. AuditLogEntry rows for this workspace
          2. Baseline rows
          3. TraceLink rows
          4. TestCase rows
          5. ArchitectureElement rows
          6. Requirement rows
          7. Artifact rows
          8. Workspace itself

        All operations are wrapped in ``transaction.atomic()`` for all-or-nothing
        semantics (REQ-L2-AS-018).

        Requires ``admin`` role (COMP-AT-002).

        Raises:
            NotFoundError: workspace does not exist.
            PermissionDeniedError: user lacks admin role.
            ValidationError: confirmation text does not match workspace name.
        """
        self._set_tenant_context(ctx)
        self._assert_permission(ctx, "admin")

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        # Captcha validation: case-sensitive match
        if confirmation_text != workspace.name:
            raise ValidationError(
                f"Confirmation mismatch: expected '{workspace.name}', "
                f"got '{confirmation_text}'"
            )

        # Cascade delete in specified order
        # Use unscoped manager to bypass tenant filtering for delete operations
        workspace_pk = workspace.pk

        # 1. AuditLogEntry rows for this workspace
        AuditLogEntry.unscoped.filter(
            object_type="Workspace", object_id=workspace_pk
        ).delete()

        # 2-7. Delete through artifacts (Baseline, TraceLink, TestCase,
        # ArchitectureElement, Requirement, Artifact)
        artifact_ids = list(
            Artifact.unscoped.filter(workspace_id=workspace_pk).values_list("id", flat=True)
        )

        if artifact_ids:
            # 2. Baseline rows
            Baseline.unscoped.filter(artifact_id__in=artifact_ids).delete()
            # 3. TraceLink rows (source or target)
            TraceLink.unscoped.filter(
                source_id__in=artifact_ids
            ).delete()
            TraceLink.unscoped.filter(
                target_id__in=artifact_ids
            ).delete()
            # 4. TestCase rows
            TestCase.unscoped.filter(artifact_id__in=artifact_ids).delete()
            # 5. ArchitectureElement rows
            ArchitectureElement.unscoped.filter(artifact_id__in=artifact_ids).delete()
            # 6. Requirement rows
            Requirement.unscoped.filter(artifact_id__in=artifact_ids).delete()
            # 7. Artifact rows
            Artifact.unscoped.filter(workspace_id=workspace_pk).delete()

        # Also delete WorkspacePresetConfig companion
        WorkspacePresetConfig.unscoped.filter(workspace_id=workspace_pk).delete()

        # 8. Workspace itself
        Workspace.unscoped.filter(pk=workspace_pk).delete()

        self._audit(
            ctx=ctx,
            operation="workspace.delete",
            entity_type="Workspace",
            entity_id=workspace_pk,
            details={"name": workspace.name, "artifact_count": len(artifact_ids)},
        )


__all__ = ["WorkspaceService"]
