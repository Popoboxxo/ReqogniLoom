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
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, Workspace
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

    @staticmethod
    def resolve_login_tenant_id() -> Optional[UUID]:
        """Return the single deployed tenant's id, or ``None`` if ambiguous.

        The unauthenticated login page carries no tenant signal at all: this
        codebase resolves the tenant *from the username* during
        authentication (``LoginView``), and there is no host/subdomain
        routing. ``settings.DEFAULT_TENANT_ID`` cannot be used either — it is
        declared ``cast=int`` (``reqogniloom/settings.py``), so Django's
        ``UUIDField.to_python`` silently coerces the shipped default ``1``
        into ``uuid.UUID(int=1)``, a value that matches no real tenant and
        that an operator cannot override with a real UUID (decouple would
        raise on a non-integer).

        So the tenant is resolved from the database instead: this product is
        deployed one-tenant-per-installation (self-hosted docker-compose; the
        System-Admin tier already assumes a single administered tenant). If
        exactly one :class:`Tenant` row exists it is unambiguously *the*
        tenant. Zero rows (fresh install) or more than one (a multi-tenant or
        test-seeded database) is ambiguous, and the caller must then behave
        exactly as it does for "no banner configured" — never a distinguishable
        error, so an unauthenticated client cannot fingerprint the
        deployment's tenant configuration.
        """
        tenant_ids = list(Tenant.objects.values_list("id", flat=True)[:2])
        if len(tenant_ids) != 1:
            return None
        return tenant_ids[0]

    def get_login_banner(self) -> Optional[Banner]:
        """Return the enabled, login-page-visible global banner, or ``None``.

        No :class:`AuthContext` and no caller-supplied tenant — this runs on a
        genuinely unauthenticated request, so the tenant is resolved here via
        :meth:`resolve_login_tenant_id`. ``None`` is returned both when the
        tenant is ambiguous and when no matching banner exists; the caller
        maps both to the same 204 response.

        The read is wrapped in an explicit
        :func:`persistence.middleware.set_request_tenant` / ``clear`` pair.
        That is load-bearing, not decorative: ``admin_ops_banner`` carries a
        ``FORCE ROW LEVEL SECURITY`` policy keyed on the PostgreSQL session
        variable ``app.current_tenant``
        (``admin_ops/migrations/0003_banner_rls.py``), and the tenant
        middleware only sets that variable for *authenticated* requests.
        Without the explicit activation below, this read would run with the
        variable unset and RLS would correctly — and silently — return zero
        rows for every deployment. Any prior context on this thread is
        restored in the ``finally`` so the helper is safe to call from inside
        a request that already has a tenant active (e.g. tests).
        """
        tenant_id = self.resolve_login_tenant_id()
        if tenant_id is None:
            return None

        previous_tenant_id = (
            TenantContext.get_tenant() if TenantContext.is_set() else None
        )
        set_request_tenant(tenant_id)
        try:
            return Banner.objects.filter(
                scope=BannerScope.GLOBAL,
                enabled=True,
                show_on_login_page=True,
            ).first()
        finally:
            if previous_tenant_id is not None:
                set_request_tenant(previous_tenant_id)
            else:
                clear_request_tenant()


__all__ = ["BannerService"]
