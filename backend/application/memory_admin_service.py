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

from auth_tenancy.context import AuthContext
from auth_tenancy.models import UserRole
from auth_tenancy.services import AuthorizationService
from memory.models import UserTenantMemory, WorkspaceMemory, WorkspaceMemorySettings
from persistence.models import Workspace

from .base import NotFoundError, PermissionDeniedError, ServiceBase


class MemoryAdminService(ServiceBase):
    """System-Admin-only read/delete operations over workspace + user memory."""

    @staticmethod
    def _assert_system_admin(ctx: AuthContext) -> None:
        """Same System-Admin check as ``memory.memory_rest._is_system_admin``."""
        if ctx.has_role("admin") or AuthorizationService().is_tenant_admin(
            user_id=ctx.user_id, tenant_id=ctx.tenant_id
        ):
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
            ws_qs = WorkspaceMemory.objects.filter(workspace_id=ws.id)
            ws_count = ws_qs.count()
            last_ws = ws_qs.order_by("-created_at").values_list("created_at", flat=True).first()

            member_ids = self._member_ids(ws.id)
            if member_ids:
                user_qs = UserTenantMemory.objects.filter(user_id__in=member_ids)
                user_count = user_qs.count()
                last_user = user_qs.order_by("-created_at").values_list("created_at", flat=True).first()
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

        return {
            "workspace_id": workspace_id,
            "workspace_memory_deleted": ws_deleted,
            "user_memory_deleted": user_deleted,
        }


__all__ = ["MemoryAdminService"]
