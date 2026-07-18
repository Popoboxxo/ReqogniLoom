"""Global/Workspace permission-definition service (REQ-181/182/183/186/187).

Business logic for the role->capability matrix governance layer that mirrors the
workflow global-default / override / reset model:

* :class:`GlobalPermissionDefinition` — one per tenant (source-of-truth matrix +
  ``enforcement_mode`` rollout phase).
* :class:`WorkspacePermissionDefinition` — one per workspace, inherited from the
  tenant global and flagged ``is_customized`` once it diverges.

All decision-changing enforcement lives elsewhere (the shadow comparator in
:mod:`auth_tenancy.services.permission_shadow`); this module only reads/writes
the definition rows, propagates global edits to non-customized derived rows, and
implements the guarded ``enforcement_mode`` flip (REQ-187).
"""
from __future__ import annotations

import copy
from datetime import timedelta
from typing import Optional
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from application.base import ServiceBase
from auth_tenancy.context import AuthContext
from auth_tenancy.models import (
    GlobalPermissionDefinition,
    PermissionDecisionMismatch,
    WorkspacePermissionDefinition,
)

from .permission_matrix import (
    default_permission_matrix,
    merge_matrix,
    validate_matrix,
)

# Trailing window (days) used to compute the pending mismatch count that gates
# the shadow -> authoritative flip. Kept in one place so the GET status endpoint
# and the flip guard use an identical window (REQ-187).
DEFAULT_MISMATCH_WINDOW_DAYS = 30


class NoGlobalSourceError(Exception):
    """Reset requested but ``source_global`` is null (nothing to reset to)."""


class MismatchCountStaleError(Exception):
    """Confirmed mismatch count did not match the current server-side count."""

    def __init__(self, current_count: int) -> None:
        self.current_count = current_count
        super().__init__(
            f"Confirmed count does not match current pending mismatch count "
            f"({current_count})."
        )


class PermissionDefinitionService(ServiceBase):
    """CRUD + inheritance + rollout control for permission definitions."""

    # ---------- Global (tenant-wide singleton) ----------

    def get_or_create_global(
        self, tenant_id: UUID | str
    ) -> GlobalPermissionDefinition:
        """Return the tenant's global definition, seeding it if absent.

        Seeds ``permission_json`` from :func:`default_permission_matrix` (the
        live RBAC matrix) and ``enforcement_mode='shadow'`` so a first access
        never changes any access decision.
        """
        obj, _created = GlobalPermissionDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            defaults={
                "permission_json": default_permission_matrix(),
                "enforcement_mode": GlobalPermissionDefinition.ENFORCEMENT_SHADOW,
            },
        )
        return obj

    def replace_global(
        self, ctx: AuthContext, matrix: object
    ) -> tuple[GlobalPermissionDefinition, int]:
        """Replace the tenant global matrix and propagate to non-customized rows.

        Returns the updated global plus the number of workspace definitions the
        change propagated into (``is_customized=False`` derived rows).
        """
        self._set_tenant_context(ctx)
        normalised = validate_matrix(matrix)
        with transaction.atomic():
            obj = self.get_or_create_global(ctx.tenant_id)
            obj.permission_json = normalised
            obj.save(update_fields=["permission_json", "modified_at"])
            propagated = self._propagate_global(ctx.tenant_id, obj, normalised)
            self._audit(
                ctx,
                operation="update",
                entity_type="GlobalPermissionDefinition",
                entity_id=obj.id,
                details={
                    "action": "replace_matrix",
                    "propagated_workspace_count": propagated,
                },
            )
        return obj, propagated

    def patch_global(
        self, ctx: AuthContext, partial: object
    ) -> tuple[GlobalPermissionDefinition, int]:
        """Deep-merge a partial matrix into the global, then full-revalidate."""
        self._set_tenant_context(ctx)
        with transaction.atomic():
            obj = self.get_or_create_global(ctx.tenant_id)
            merged = merge_matrix(obj.permission_json, partial)
            normalised = validate_matrix(merged)
            obj.permission_json = normalised
            obj.save(update_fields=["permission_json", "modified_at"])
            propagated = self._propagate_global(ctx.tenant_id, obj, normalised)
            self._audit(
                ctx,
                operation="update",
                entity_type="GlobalPermissionDefinition",
                entity_id=obj.id,
                details={
                    "action": "patch_matrix",
                    "propagated_workspace_count": propagated,
                },
            )
        return obj, propagated

    def _propagate_global(
        self,
        tenant_id: UUID | str,
        global_def: GlobalPermissionDefinition,
        matrix: dict,
        *,
        exclude_workspace_id: Optional[UUID] = None,
    ) -> int:
        """Copy ``matrix`` into every non-customized derived workspace row."""
        qs = WorkspacePermissionDefinition.unscoped.filter(
            tenant_id=tenant_id,
            source_global_id=global_def.id,
            is_customized=False,
        )
        if exclude_workspace_id is not None:
            qs = qs.exclude(workspace_id=exclude_workspace_id)
        return qs.update(permission_json=copy.deepcopy(matrix))

    # ---------- Enforcement rollout (REQ-186/187) ----------

    def pending_mismatch_count(
        self,
        tenant_id: UUID | str,
        *,
        window_days: int = DEFAULT_MISMATCH_WINDOW_DAYS,
    ) -> tuple[int, Optional[object]]:
        """Return (count, last_mismatch_at) for the trailing window."""
        since = timezone.now() - timedelta(days=window_days)
        qs = PermissionDecisionMismatch.unscoped.filter(
            tenant_id=tenant_id, created_at__gte=since
        )
        count = qs.count()
        last = (
            qs.order_by("-created_at").values_list("created_at", flat=True).first()
        )
        return count, last

    def flip_enforcement(
        self,
        ctx: AuthContext,
        *,
        target_mode: str,
        confirm_pending_mismatch_count: Optional[int],
    ) -> GlobalPermissionDefinition:
        """Guarded transition of the tenant's ``enforcement_mode`` (REQ-187).

        ``shadow -> authoritative`` requires ``confirm_pending_mismatch_count``
        to exactly equal the current server-side count (default window);
        otherwise :class:`MismatchCountStaleError` is raised with the fresh
        count. ``authoritative -> shadow`` (rollback) needs no confirmation.
        """
        self._set_tenant_context(ctx)
        with transaction.atomic():
            obj = self.get_or_create_global(ctx.tenant_id)
            old_mode = obj.enforcement_mode
            if (
                old_mode == GlobalPermissionDefinition.ENFORCEMENT_SHADOW
                and target_mode
                == GlobalPermissionDefinition.ENFORCEMENT_AUTHORITATIVE
            ):
                current, _last = self.pending_mismatch_count(ctx.tenant_id)
                if confirm_pending_mismatch_count != current:
                    raise MismatchCountStaleError(current)
            obj.enforcement_mode = target_mode
            obj.save(update_fields=["enforcement_mode", "modified_at"])
            self._audit(
                ctx,
                operation="update",
                entity_type="GlobalPermissionDefinition",
                entity_id=obj.id,
                details={
                    "action": "flip_enforcement_mode",
                    "old_mode": old_mode,
                    "new_mode": target_mode,
                    "confirm_pending_mismatch_count": confirm_pending_mismatch_count,
                },
            )
        return obj

    # ---------- Workspace (per-workspace override) ----------

    def get_or_create_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> WorkspacePermissionDefinition:
        """Return the workspace definition, inheriting from the global if absent."""
        existing = WorkspacePermissionDefinition.unscoped.filter(
            tenant_id=tenant_id, workspace_id=workspace_id
        ).first()
        if existing is not None:
            return existing
        global_def = self.get_or_create_global(tenant_id)
        obj, _created = WorkspacePermissionDefinition.unscoped.get_or_create(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            defaults={
                "permission_json": copy.deepcopy(global_def.permission_json),
                "source_global_id": global_def.id,
                "is_customized": False,
            },
        )
        return obj

    def replace_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str, matrix: object
    ) -> WorkspacePermissionDefinition:
        """Override a workspace matrix (sets ``is_customized=True``)."""
        self._set_tenant_context(ctx)
        normalised = validate_matrix(matrix)
        with transaction.atomic():
            obj = self.get_or_create_workspace(ctx.tenant_id, workspace_id)
            obj.permission_json = normalised
            obj.is_customized = True
            obj.save(
                update_fields=["permission_json", "is_customized", "modified_at"]
            )
            self._audit(
                ctx,
                operation="update",
                entity_type="WorkspacePermissionDefinition",
                entity_id=obj.id,
                details={"action": "replace_matrix", "workspace_id": str(workspace_id)},
            )
        return obj

    def patch_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str, partial: object
    ) -> WorkspacePermissionDefinition:
        """Deep-merge a partial workspace override (sets ``is_customized=True``)."""
        self._set_tenant_context(ctx)
        with transaction.atomic():
            obj = self.get_or_create_workspace(ctx.tenant_id, workspace_id)
            merged = merge_matrix(obj.permission_json, partial)
            normalised = validate_matrix(merged)
            obj.permission_json = normalised
            obj.is_customized = True
            obj.save(
                update_fields=["permission_json", "is_customized", "modified_at"]
            )
            self._audit(
                ctx,
                operation="update",
                entity_type="WorkspacePermissionDefinition",
                entity_id=obj.id,
                details={"action": "patch_matrix", "workspace_id": str(workspace_id)},
            )
        return obj

    def reset_workspace(
        self, ctx: AuthContext, workspace_id: UUID | str
    ) -> WorkspacePermissionDefinition:
        """Reset a workspace matrix to its global default (REQ-183).

        Raises:
            NoGlobalSourceError: ``source_global`` is null (pre-REQ-181 workspace
                or the global row was deleted).
        """
        self._set_tenant_context(ctx)
        with transaction.atomic():
            obj = self.get_or_create_workspace(ctx.tenant_id, workspace_id)
            if obj.source_global_id is None:
                raise NoGlobalSourceError(
                    "Workspace permission definition has no linked global "
                    "default to reset to."
                )
            global_def = GlobalPermissionDefinition.unscoped.filter(
                id=obj.source_global_id
            ).first()
            if global_def is None:
                raise NoGlobalSourceError(
                    "Workspace permission definition has no linked global "
                    "default to reset to."
                )
            obj.permission_json = copy.deepcopy(global_def.permission_json)
            obj.is_customized = False
            obj.save(
                update_fields=["permission_json", "is_customized", "modified_at"]
            )
            self._audit(
                ctx,
                operation="update",
                entity_type="WorkspacePermissionDefinition",
                entity_id=obj.id,
                details={"action": "reset_to_default", "workspace_id": str(workspace_id)},
            )
        return obj

    # ---------- Provisioning (workspace creation) ----------

    # ---------- Mismatch review (REQ-187, read-only) ----------

    def list_mismatches(
        self,
        tenant_id: UUID | str,
        *,
        workspace_id: Optional[UUID | str] = None,
        capability: Optional[str] = None,
        subject_type: Optional[str] = None,
        subject_identifier: Optional[str] = None,
        since=None,
        until=None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[int, list[PermissionDecisionMismatch]]:
        """Return (total_count, page_rows) of shadow-phase mismatches (REQ-187).

        Read-only; the underlying table is append-only. Ordered newest-first.
        ``subject_type`` is a prefix filter ("user"/"apikey"/"agent") on
        ``subject_identifier``.
        """
        qs = PermissionDecisionMismatch.unscoped.filter(tenant_id=tenant_id)
        if workspace_id is not None:
            qs = qs.filter(workspace_id=workspace_id)
        if capability:
            qs = qs.filter(capability=capability)
        if subject_type:
            qs = qs.filter(subject_identifier__startswith=f"{subject_type}:")
        if subject_identifier:
            qs = qs.filter(subject_identifier=subject_identifier)
        if since is not None:
            qs = qs.filter(created_at__gte=since)
        if until is not None:
            qs = qs.filter(created_at__lte=until)
        qs = qs.order_by("-created_at")

        total = qs.count()
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        start = (page - 1) * page_size
        rows = list(qs[start : start + page_size])
        return total, rows

    # ---------- Provisioning (workspace creation) ----------

    def provision_workspace(
        self, tenant_id: UUID | str, workspace_id: UUID | str
    ) -> WorkspacePermissionDefinition:
        """Link a newly created workspace to the tenant permission global.

        Idempotent — used by ``WorkspaceService.create_workspace`` /
        ``clone_workspace``. Creates the tenant global on first use and a
        ``WorkspacePermissionDefinition`` with ``is_customized=False`` mirroring
        it, so the new workspace starts "on-default".
        """
        return self.get_or_create_workspace(tenant_id, workspace_id)


__all__ = [
    "PermissionDefinitionService",
    "NoGlobalSourceError",
    "MismatchCountStaleError",
    "DEFAULT_MISMATCH_WINDOW_DAYS",
]
