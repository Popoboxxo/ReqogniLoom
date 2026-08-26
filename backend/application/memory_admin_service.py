"""MemoryAdminService — System-Admin operations over consolidated memory
(Memory Admin UI Phase 1, spec 2026-08-26).

Both public methods run only inside an already-active request-scoped tenant
context (reached exclusively via a real HTTP request through
``AuthTenancyAuthentication``, never from Celery) — this mirrors
``memory/memory_rest.py``'s existing views and its module docstring's
explicit warning against a bare ``TenantContext.set_tenant(...)`` call:
that call only satisfies the Django-ORM side and never arms Postgres RLS.
Since this service is never invoked outside a request, no such call is
needed here at all.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db.models import Count, Max

from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserRole
from auth_tenancy.services import AuthorizationService
from memory.models import UserTenantMemory, WorkspaceMemory, WorkspaceMemorySettings
from persistence.models import Workspace
from persistence.transactions import atomic_transaction

from .base import NotFoundError, PermissionDeniedError, ServiceBase


class MemoryAdminService(ServiceBase):
    """System-Admin-only read/delete operations over workspace + user memory."""

    @staticmethod
    def _assert_system_admin(ctx: AuthContext) -> None:
        """System-Admin check: tenant-wide admin only (NOT workspace-scoped
        ``has_role("admin")``, which on an endpoint with a ``workspace_id`` URL
        kwarg means "admin of that one workspace" — see auth_tenancy.workspace_scope).
        """
        if AuthorizationService().is_tenant_admin(user_id=ctx.user_id, tenant_id=ctx.tenant_id):
            return
        raise PermissionDeniedError("System-Admin role required")

    @staticmethod
    def _member_ids(workspace_id: UUID) -> list[UUID]:
        """Current (non-suspended) member user ids of *workspace_id*."""
        return list(
            UserRole.objects.filter(workspace_id=workspace_id, suspended_at__isnull=True)
            .values_list("user_id", flat=True)
            .distinct()
        )

    def list_workspace_overview(self, ctx: AuthContext) -> list[dict[str, Any]]:
        """Return one overview row per workspace in the active tenant.

        Relies on ``Workspace.objects``/``WorkspaceMemorySettings.objects``
        (both ``TenantScopedModel`` managers) already being scoped to the
        active tenant context — no manual ``tenant_id`` filter needed for
        reads (only writes need it explicitly, see
        ``WorkspaceMemorySettingsView.put``'s comment on ``update_or_create``).
        """
        self._assert_system_admin(ctx)

        settings_by_ws = {
            s.workspace_id: s.enabled for s in WorkspaceMemorySettings.objects.all()
        }

        overview: list[dict[str, Any]] = []
        for ws in Workspace.objects.all().order_by("name"):
            ws_agg = WorkspaceMemory.objects.filter(workspace_id=ws.id).aggregate(
                count=Count("id"), last=Max("created_at")
            )
            ws_count = ws_agg["count"]
            last_ws = ws_agg["last"]

            member_ids = self._member_ids(ws.id)
            if member_ids:
                user_agg = UserTenantMemory.objects.filter(user_id__in=member_ids).aggregate(
                    count=Count("id"), last=Max("created_at")
                )
                user_count = user_agg["count"]
                last_user = user_agg["last"]
            else:
                user_count = 0
                last_user = None

            candidates = [d for d in (last_ws, last_user) if d is not None]
            last_consolidated = max(candidates) if candidates else None

            overview.append(
                {
                    "workspace_id": ws.id,
                    "workspace_name": ws.name,
                    "enabled": settings_by_ws.get(ws.id, True),
                    "workspace_entry_count": ws_count,
                    "user_entry_count": user_count,
                    "last_consolidated_at": last_consolidated,
                }
            )
        return overview

    @atomic_transaction
    def delete_workspace_memory(self, ctx: AuthContext, workspace_id: UUID) -> dict[str, Any]:
        """Delete BOTH tiers for *workspace_id*: its own ``WorkspaceMemory``
        rows, and the ``UserTenantMemory`` rows of its CURRENT members.

        Never deletes ``UserTenantMemory`` for a user who is not a current
        member of this workspace, even if that user has other memberships.
        """
        self._assert_system_admin(ctx)

        workspace = Workspace.objects.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")

        member_ids = self._member_ids(workspace_id)

        ws_deleted, _ = WorkspaceMemory.objects.filter(workspace_id=workspace_id).delete()
        user_deleted = 0
        if member_ids:
            user_deleted, _ = UserTenantMemory.objects.filter(user_id__in=member_ids).delete()

        self._audit(
            ctx=ctx,
            operation="delete",
            entity_type="WorkspaceMemory",
            entity_id=workspace_id,
            change_reason=(
                f"workspace_memory_deleted={ws_deleted} "
                f"user_memory_deleted={user_deleted} "
                f"affected_member_ids={[str(uid) for uid in member_ids]}"
            ),
        )

        return {
            "workspace_id": workspace_id,
            "workspace_memory_deleted": ws_deleted,
            "user_memory_deleted": user_deleted,
        }


__all__ = ["MemoryAdminService"]
