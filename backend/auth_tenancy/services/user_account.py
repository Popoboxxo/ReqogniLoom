"""Account-level user lifecycle: create, activate, deactivate.

The last-admin invariant's connecting case: deactivating a User's account
(``is_active=False``) implicitly removes every admin role that user holds
— at both workspace and tenant scope — in one action. This service is the
ONLY place that flips ``User.is_active``; REST and MCP both call it, so
no code path can bypass the check (multi-user management design spec).
"""
from __future__ import annotations

from uuid import UUID

from django.db import transaction

from .authorization import AuthorizationService
from ..errors import PermissionDenied
from ..models import ROLE_ADMIN, TenantRole, UserRole
from persistence.models import Tenant, User


class UserAccountService:
    """Tenant-admin-guarded account lifecycle: create / activate / deactivate."""

    def create(
        self,
        *,
        actor_is_tenant_admin: bool,
        tenant_id: UUID,
        username: str,
        email: str,
        password: str,
    ) -> User:
        """Create a new user with an initial password (tenant-admin-guarded).

        Mirrors the pattern ``mcp_server/tools/users.py::_handle_user_create``
        used inline before this service existed: ``User.objects.create`` +
        ``set_password`` + ``save``, the only user-creation path in the
        codebase (confirmed at the time that handler was written).
        """
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")
        tenant = Tenant.objects.get(id=tenant_id)
        user = User.objects.create(
            username=username, email=email, tenant=tenant, is_active=True
        )
        user.set_password(password)
        user.save(update_fields=["password", "modified_at", "version"])
        return user

    def activate(self, *, actor_is_tenant_admin: bool, target_user_id: UUID) -> None:
        """Set ``is_active=True`` (tenant-admin-guarded, no last-admin check —
        activating never removes an admin)."""
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")
        User.objects.filter(id=target_user_id).update(is_active=True)

    def deactivate(
        self, *, actor_is_tenant_admin: bool, target_user_id: UUID
    ) -> None:
        """Set ``is_active=False`` (tenant-admin-guarded, last-admin protected
        at BOTH workspace and tenant scope).

        Raises :class:`LastAdminError` naming the first blocking workspace or
        tenant found if deactivating this user would drop any of them to
        zero active admins.

        Reuses :meth:`AuthorizationService._assert_not_last_workspace_admin`
        and :meth:`AuthorizationService._assert_not_last_tenant_admin` rather
        than re-implementing the count-then-mutate logic a third time. Both
        helpers lock ALL active admin rows of the scope first via
        ``select_for_update()`` and only exclude the target in Python
        afterwards — so a concurrent per-role revoke (``revoke_role`` /
        ``revoke_tenant_admin``) and a full-account deactivate contend on the
        same row set and cannot race each other into a zero-admin state.
        """
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")

        with transaction.atomic():
            admin_workspace_ids = list(
                UserRole.objects.filter(
                    user_id=target_user_id,
                    role=ROLE_ADMIN,
                    suspended_at__isnull=True,
                ).values_list("workspace_id", flat=True)
            )
            for workspace_id in admin_workspace_ids:
                AuthorizationService._assert_not_last_workspace_admin(
                    workspace_id=workspace_id, excluding_user_id=target_user_id
                )

            admin_tenant_ids = list(
                TenantRole.objects.filter(
                    user_id=target_user_id,
                    role=TenantRole.ROLE_ADMIN,
                    suspended_at__isnull=True,
                ).values_list("tenant_id", flat=True)
            )
            for tenant_id in admin_tenant_ids:
                AuthorizationService._assert_not_last_tenant_admin(
                    tenant_id=tenant_id, excluding_user_id=target_user_id
                )

            User.objects.filter(id=target_user_id).update(is_active=False)


__all__ = ["UserAccountService"]
