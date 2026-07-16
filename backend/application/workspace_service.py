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
from django.db.models import QuerySet
from django.utils import timezone
from persistence.models import (
    ArchitectureElement,
    Artifact,
    AuditLogEntry,
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

# Sentinel distinguishing "field omitted" from an explicit ``None`` in PATCH.
_UNSET: object = object()


class WorkspaceService(ServiceBase):
    """COMP-AS-WS — Workspace queries + create scoped to the active tenant."""

    # ---------- Read API ----------

    def list_workspaces(self, ctx: AuthContext) -> QuerySet[Workspace]:
        """Return all workspaces visible to *ctx*'s tenant.

        Tenant scoping is enforced by ``TenantContext`` via the default
        ``objects`` manager. Order: most recently modified first.

        REQ-088: Returns a lazy ``QuerySet`` so the paginating ViewSet
        (REQ-034) slices with LIMIT/OFFSET instead of materialising all rows.
        """
        self._set_tenant_context(ctx)
        return Workspace.objects.all().order_by("-modified_at")

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

    @atomic_transaction
    def clone_workspace(
        self,
        ctx: AuthContext,
        source_id: UUID,
        target_name: str,
    ) -> Workspace:
        """Create a sandbox clone of a workspace (SN-33)."""
        self._set_tenant_context(ctx)
        self._assert_write_permission(ctx)

        source = Workspace.objects.filter(id=source_id, tenant_id=ctx.tenant_id).first()
        if not source:
            raise NotFoundError(f"Workspace {source_id} not found")
        
        target_name_clean = (target_name or "").strip()
        if not target_name_clean:
            raise ValidationError("target_name is required")

        source_config = WorkspacePresetConfig.objects.filter(workspace=source).first()
        active_tier = source_config.active_tier if source_config else "standard"
        terminology = source_config.terminology_profile if source_config else "se_mode"

        # 1. Create target Workspace
        target = Workspace.objects.create(
            tenant_id=ctx.tenant_id,
            name=target_name_clean,
            preset=source.preset,
            parent_workspace=source,
        )
        WorkspacePresetConfig.objects.create(
            tenant_id=ctx.tenant_id,
            workspace=target,
            active_tier=active_tier,
            terminology_profile=terminology,
        )

        # 2. Deep copy artifacts
        old_to_new_artifact = {}
        old_to_new_arch = {}

        # Copy Artifacts
        artifacts = list(Artifact.objects.filter(workspace=source))
        for a in artifacts:
            new_a = Artifact.objects.create(
                tenant_id=ctx.tenant_id,
                workspace=target,
                artifact_type=a.artifact_type,
            )
            old_to_new_artifact[a.id] = new_a

        # Fix parent FKs on Artifacts
        for a in artifacts:
            if a.parent_id:
                new_a = old_to_new_artifact[a.id]
                new_a.parent_id = old_to_new_artifact[a.parent_id].id
                new_a.save(update_fields=['parent_id'])

        # Copy Requirements
        reqs = list(Requirement.objects.filter(artifact__workspace=source))
        for r in reqs:
            r.pk = None
            r.artifact = old_to_new_artifact[r.artifact_id]
            r.save()

        # Copy ArchitectureElements (self-referential parent FK).
        # Two-pass to preserve the hierarchy across ≥2 levels:
        #   1. create every element with parent=None and record
        #      old_id -> new instance,
        #   2. remap each parent reference to the CLONED parent instance.
        # Mutating ``arch.pk`` in-place loses the old id, so the old id
        # and old parent id are captured BEFORE the insert.
        archs = list(ArchitectureElement.objects.filter(artifact__workspace=source))
        old_parent_of: dict[UUID, Optional[UUID]] = {}
        for arch in archs:
            old_id = arch.id
            old_parent_of[old_id] = arch.parent_id
            arch.pk = None
            arch.parent = None  # remapped in the second pass below
            arch.artifact = old_to_new_artifact[arch.artifact_id]
            arch.save()
            old_to_new_arch[old_id] = arch

        # Second pass: point each cloned element at its cloned parent.
        for old_id, old_parent_id in old_parent_of.items():
            if old_parent_id is not None:
                new_arch = old_to_new_arch[old_id]
                new_arch.parent = old_to_new_arch[old_parent_id]
                new_arch.save(update_fields=["parent"])

        # Copy TestCases
        tests = list(TestCase.objects.filter(artifact__workspace=source))
        for t in tests:
            t.pk = None
            t.artifact = old_to_new_artifact[t.artifact_id]
            t.save()

        # Copy TraceLinks
        # Using TraceLink directly instead of engine to clone within same tenant easily
        links = list(TraceLink.objects.filter(source__workspace=source))
        for link in links:
            link.pk = None
            link.source_id = old_to_new_artifact[link.source_id].id
            link.target_id = old_to_new_artifact[link.target_id].id
            link.save()

        self._audit(
            ctx=ctx,
            operation="clone",
            entity_type="Workspace",
            entity_id=target.id,
            details={"source_id": str(source.id)},
        )

        return target

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
            # 2. BaselineSnapshot rows (via workspace_id or artifact FK)
            from baseline.models import BaselineSnapshot
            BaselineSnapshot.unscoped.filter(workspace_id=workspace_pk).delete()
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


    # ---------- Metadata + preset orchestration (REQ-066, REQ-L2-RF-012) ----------

    @atomic_transaction
    def update_metadata(
        self,
        ctx: AuthContext,
        workspace_id: UUID,
        *,
        name: object = _UNSET,
        language: object = _UNSET,
        decomposition_link_type: object = _UNSET,
        default_link_type: object = _UNSET,
        terminology_profile: object = _UNSET,
    ) -> Workspace:
        """Update workspace metadata + optional terminology-profile switch (REQ-066).

        Only fields passed explicitly (i.e. not ``_UNSET``) are touched, mirroring
        the PATCH semantics of the former view. ``language`` and
        ``terminology_profile`` are stored on the ``preset`` JSON blob; switching
        the terminology profile also runs the ``presets`` orchestration.

        Raises:
            NotFoundError: workspace does not exist in the active tenant.
            ValidationError: empty name or invalid terminology_profile.
        """
        self._set_tenant_context(ctx)
        ws = Workspace.objects.filter(id=workspace_id).first()
        if ws is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        update_fields: list[str] = []
        preset_blob = dict(ws.preset or {})

        if name is not _UNSET:
            new_name = str(name or "").strip()
            if not new_name:
                raise ValidationError("name must not be empty")
            ws.name = new_name
            update_fields.append("name")

        if language is not _UNSET:
            preset_blob["language"] = str(language)
            ws.preset = preset_blob
            if "preset" not in update_fields:
                update_fields.append("preset")

        if decomposition_link_type is not _UNSET:
            ws.decomposition_link_type = str(decomposition_link_type)
            if "decomposition_link_type" not in update_fields:
                update_fields.append("decomposition_link_type")

        if default_link_type is not _UNSET:
            ws.default_link_type = str(default_link_type)
            if "default_link_type" not in update_fields:
                update_fields.append("default_link_type")

        if terminology_profile is not _UNSET:
            target_profile = str(terminology_profile)
            if target_profile not in ("dev_mode", "se_mode"):
                raise ValidationError(
                    "terminology_profile must be dev_mode or se_mode"
                )
            from presets.services import switch_terminology_profile
            switch_terminology_profile(
                workspace_id=str(workspace_id), target_profile=target_profile
            )
            preset_blob["terminology_profile"] = target_profile
            ws.preset = preset_blob
            if "preset" not in update_fields:
                update_fields.append("preset")

        if update_fields:
            ws.save(update_fields=update_fields)
        return ws

    @atomic_transaction
    def switch_preset_tier(
        self, ctx: AuthContext, workspace_id: UUID, target_tier: str
    ) -> Workspace:
        """Switch the active preset tier and mirror it onto the preset blob (REQ-066).

        Raises:
            ValidationError: target_tier is not minimal/standard/extended.
            NotFoundError: workspace does not exist in the active tenant.
        """
        if not target_tier or target_tier not in ("minimal", "standard", "extended"):
            raise ValidationError("preset must be minimal, standard or extended")

        from presets.services import switch_preset
        switch_preset(workspace_id=str(workspace_id), target_preset=str(target_tier))

        self._set_tenant_context(ctx)
        ws = Workspace.objects.filter(id=workspace_id).first()
        if ws is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        preset_blob = dict(ws.preset or {})
        preset_blob["tier"] = target_tier
        preset_blob["name"] = target_tier
        ws.preset = preset_blob
        ws.save(update_fields=["preset"])
        return ws


__all__ = ["WorkspaceService"]
