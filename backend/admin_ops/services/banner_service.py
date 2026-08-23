"""
admin_ops — BannerService (System & Workspace Banners).

Stateless service owning the single-row-per-scope lifecycle of
:class:`~admin_ops.models.Banner`. Authorization is a caller-supplied
boolean (``is_system_admin`` / ``is_authorized``) rather than
``ServiceBase._assert_permission`` — the tenant-admin check
(:meth:`AuthorizationService.is_tenant_admin`) is not a role in
``ctx.active_roles``, so it must be resolved by the REST view (which has
the ``AuthorizationService`` call already, mirroring
``AuthorizationService.assign_role``'s ``actor_is_tenant_admin`` parameter)
and forwarded here as a plain flag. This is the same shape used by
``WorkspaceMembersView.post`` / ``rest_workspace_members.py``.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from django.db import transaction

from application.base import NotFoundError, PermissionDeniedError, ServiceBase
from auth_tenancy.context import AuthContext
from persistence.models import Workspace
from persistence.tenancy import TenantContext

from admin_ops.models import Banner, BannerLevel, BannerScope

logger = logging.getLogger(__name__)


class BannerService:
    """Get/upsert the single global banner and the single per-workspace banner."""

    # -- Global banner -----------------------------------------------------

    def get_global_banner(self, ctx: AuthContext) -> Optional[Banner]:
        """Return the tenant's global banner row, or ``None`` if never configured."""
        ServiceBase._set_tenant_context(ctx)
        return Banner.objects.filter(scope=BannerScope.GLOBAL).first()

    def upsert_global_banner(
        self,
        ctx: AuthContext,
        *,
        is_system_admin: bool,
        level: str,
        message: str,
        enabled: bool,
        dismissible: bool,
        show_on_login_page: bool,
    ) -> Banner:
        """Create or overwrite the tenant's single global banner row.

        Raises:
            PermissionDeniedError: ``is_system_admin`` is ``False``.
        """
        if not is_system_admin:
            raise PermissionDeniedError(
                "Permission denied: tenant-admin (System-Admin) role required."
            )
        ServiceBase._set_tenant_context(ctx)
        with transaction.atomic():
            # update_or_create()/get_or_create() do NOT get TenantManager.create()'s
            # tenant auto-injection (that only fires on a bare .create() call) — the
            # tenant_id must be passed explicitly here or the insert 500s on the
            # NOT NULL constraint (see context_graph/projector.py's identical note).
            tenant_id = TenantContext.get_tenant()
            banner, created = Banner.objects.update_or_create(
                scope=BannerScope.GLOBAL,
                defaults={
                    "tenant_id": tenant_id,
                    "level": level,
                    "message": message,
                    "enabled": enabled,
                    "dismissible": dismissible,
                    "show_on_login_page": show_on_login_page,
                    "modified_by_id": ctx.user_id,
                },
            )
            ServiceBase._audit(
                ctx,
                operation="create" if created else "update",
                entity_type="Banner",
                entity_id=banner.id,
                change_reason=f"banner.upsert scope=global level={level} enabled={enabled}",
                details={"scope": "global", "level": level, "enabled": enabled},
            )
        return banner

    # -- Workspace banner ----------------------------------------------------

    def get_workspace_banner(self, ctx: AuthContext, *, workspace_id: UUID) -> Optional[Banner]:
        """Return the workspace's banner row, or ``None`` if never configured."""
        ServiceBase._set_tenant_context(ctx)
        return Banner.objects.filter(
            scope=BannerScope.WORKSPACE, workspace_id=workspace_id
        ).first()

    def upsert_workspace_banner(
        self,
        ctx: AuthContext,
        *,
        workspace_id: UUID,
        is_authorized: bool,
        level: str,
        message: str,
        enabled: bool,
        dismissible: bool,
    ) -> Banner:
        """Create or overwrite a workspace's single banner row.

        Raises:
            PermissionDeniedError: ``is_authorized`` is ``False``.
            NotFoundError: ``workspace_id`` does not belong to the caller's
                tenant (self-enforced here rather than trusted from the
                caller, mirroring ``AuthorizationService.assign_role``).
        """
        if not is_authorized:
            raise PermissionDeniedError(
                "Permission denied: workspace-admin or System-Admin role required."
            )
        ServiceBase._set_tenant_context(ctx)
        if not Workspace.objects.filter(id=workspace_id).exists():
            raise NotFoundError(f"Workspace {workspace_id} not found.")

        with transaction.atomic():
            tenant_id = TenantContext.get_tenant()
            banner, created = Banner.objects.update_or_create(
                scope=BannerScope.WORKSPACE,
                workspace_id=workspace_id,
                defaults={
                    "tenant_id": tenant_id,
                    "level": level,
                    "message": message,
                    "enabled": enabled,
                    "dismissible": dismissible,
                    "modified_by_id": ctx.user_id,
                },
            )
            ServiceBase._audit(
                ctx,
                operation="create" if created else "update",
                entity_type="Banner",
                entity_id=banner.id,
                change_reason=f"banner.upsert scope=workspace level={level} enabled={enabled}",
                details={
                    "scope": "workspace",
                    "workspace_id": str(workspace_id),
                    "level": level,
                    "enabled": enabled,
                },
            )
        return banner

    # -- Public (unauthenticated) login-page banner --------------------------

    def get_login_banner(self, tenant_id: UUID) -> Optional[Banner]:
        """Return the enabled, login-page-visible global banner for *tenant_id*.

        No :class:`AuthContext` — called from the unauthenticated
        ``PublicLoginBannerView``. Uses ``Banner.unscoped`` (the
        tenant-filter escape hatch, REQ-L3-PL001-004) with an explicit
        ``tenant_id=`` filter instead of the thread-local
        :class:`TenantContext`, because no request-scoped tenant exists
        before login.
        """
        return Banner.unscoped.filter(
            tenant_id=tenant_id,
            scope=BannerScope.GLOBAL,
            enabled=True,
            show_on_login_page=True,
        ).first()


__all__ = ["BannerService"]
