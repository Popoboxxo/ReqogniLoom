"""Account-level user lifecycle: create, activate, deactivate.

The last-admin invariant's connecting case: deactivating a User's account
(``is_active=False``) implicitly removes every admin role that user holds
— at both workspace and tenant scope — in one action. This service is the
ONLY place that flips ``User.is_active``; REST and MCP both call it, so
no code path can bypass the check (multi-user management design spec).
"""
from __future__ import annotations

from uuid import UUID

from django.db import IntegrityError, transaction

from .authorization import AuthorizationService
from ..errors import PermissionDenied
from ..models import ROLE_ADMIN, TenantRole, UserRole
from persistence.models import Tenant, User

# Minimum password length. Mirrors ``mcp_server/tools/users.py``'s
# ``_PASSWORD_MIN_LENGTH`` — the user-creation path is privileged and must
# enforce sane defaults regardless of which caller (REST/MCP) reaches it.
_PASSWORD_MIN_LENGTH: int = 8

# Mirrors ``persistence.models.User.username``'s ``max_length=150`` and
# ``.email``'s (an ``EmailField``, whose default ``max_length`` is 254).
# Without this check, an overlong value passes the empty-check above
# unharmed and reaches ``User.objects.create(...)`` below, where Postgres
# raises an uncaught ``django.db.utils.DataError`` on insert (500) instead
# of the clean 400 every other validation failure in this method produces
# (fix round 2 / Fix 1).
_USERNAME_MAX_LENGTH: int = 150
_EMAIL_MAX_LENGTH: int = 254


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

        Ports the validation ``mcp_server/tools/users.py::_handle_user_create``
        already performs inline, so this service is a strict superset (Task 6
        rewires that MCP handler to call this instead):

        - ``username``/``email`` are stripped and rejected if empty.
        - ``password`` must be at least :data:`_PASSWORD_MIN_LENGTH` chars.
        - uniqueness is pre-checked case-insensitively (clear error instead
          of a raw ``IntegrityError``), and the actual
          ``User.objects.create`` is still wrapped to catch the TOCTOU race
          between the pre-check and the insert (issue #125 in the MCP tool's
          own comments) and translate it to the same clear error.

        The whole body runs inside ``transaction.atomic()`` so a failure
        between ``User.objects.create(...)`` and ``user.save()`` (setting
        the password) can never leave an orphaned user row with no usable
        password.
        """
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")

        username = (username or "").strip()
        if not username:
            raise ValueError("Parameter 'username' must be a non-empty string.")
        if len(username) > _USERNAME_MAX_LENGTH:
            raise ValueError(
                f"Parameter 'username' must be at most {_USERNAME_MAX_LENGTH} "
                "characters."
            )

        email = (email or "").strip()
        if not email:
            raise ValueError("Parameter 'email' must be a non-empty string.")
        if len(email) > _EMAIL_MAX_LENGTH:
            raise ValueError(
                f"Parameter 'email' must be at most {_EMAIL_MAX_LENGTH} characters."
            )

        if not password or len(password) < _PASSWORD_MIN_LENGTH:
            raise ValueError(
                f"Parameter 'password' must be at least {_PASSWORD_MIN_LENGTH} "
                "characters."
            )

        with transaction.atomic():
            tenant = Tenant.objects.get(id=tenant_id)

            if User.objects.filter(username__iexact=username).exists():
                raise ValueError(f"Username {username!r} is already taken.")
            if User.objects.filter(email__iexact=email).exists():
                raise ValueError(f"Email {email!r} is already in use.")

            try:
                user = User.objects.create(
                    username=username, email=email, tenant=tenant, is_active=True
                )
                user.set_password(password)
                user.save(update_fields=["password", "modified_at", "version"])
            except IntegrityError:
                # Closes the TOCTOU race between the exists() pre-checks
                # above and this create() call — mirrors the handling in
                # mcp_server/tools/users.py::_handle_user_create (#125).
                raise ValueError(
                    f"Username {username!r} or email {email!r} is already in use."
                ) from None

        return user

    def activate(
        self,
        *,
        actor_is_tenant_admin: bool,
        actor_tenant_id: UUID,
        target_user_id: UUID,
    ) -> None:
        """Set ``is_active=True`` (tenant-admin-guarded, no last-admin check —
        activating never removes an admin).

        Raises :class:`PermissionDenied` if the actor is not a tenant-admin,
        or if the target user does not belong to the actor's tenant (cross-
        tenant IDOR guard — ``User`` has no RLS of its own).
        """
        if not actor_is_tenant_admin:
            raise PermissionDenied(required_role="tenant-admin")

        target = User.objects.get(id=target_user_id)
        if target.tenant_id != actor_tenant_id:
            raise PermissionDenied(required_role="tenant-admin")

        User.objects.filter(id=target_user_id).update(is_active=True)

    def deactivate(
        self,
        *,
        actor_is_tenant_admin: bool,
        actor_tenant_id: UUID,
        target_user_id: UUID,
    ) -> None:
        """Set ``is_active=False`` (tenant-admin-guarded, last-admin protected
        at BOTH workspace and tenant scope).

        Raises :class:`LastAdminError` naming the first blocking workspace or
        tenant found if deactivating this user would drop any of them to
        zero active admins. Raises :class:`PermissionDenied` if the actor is
        not a tenant-admin, or if the target does not belong to the actor's
        tenant (cross-tenant IDOR guard).

        Deactivating an already-inactive user is a harmless no-op (returns
        immediately, before any lock/transaction is opened) — this is
        required once the last-admin helpers below also filter on
        ``user__is_active=True``: without this early return, re-deactivating
        an already-inactive last admin would spuriously raise
        ``LastAdminError`` (their own role row would already be excluded
        from the "remaining active admins" count, making it look like
        deactivating them removes the last admin, when in fact nothing
        would change).

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

        target = User.objects.get(id=target_user_id)
        if target.tenant_id != actor_tenant_id:
            raise PermissionDenied(required_role="tenant-admin")

        if not target.is_active:
            return

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

    def get(self, *, user_id: UUID) -> User:
        """Return the user by id.

        Read-only lookup seam for callers (REST/MCP) that need a fresh
        ``User`` row without reaching for the ORM directly (ADR-01 /
        REQ-066) — e.g. building a response body after ``activate``/
        ``deactivate`` has already mutated the row.

        Raises:
            User.DoesNotExist: No user with this id exists.
        """
        return User.objects.get(id=user_id)

    def list_for_tenant(self, *, tenant_id: UUID) -> list[User]:
        """Return every user of ``tenant_id``, ordered by username.

        Read-only listing seam (ADR-01 / REQ-066) backing the tenant-admin
        user directory (``GET /api/v1/users/``).
        """
        return list(User.objects.filter(tenant_id=tenant_id).order_by("username"))


__all__ = ["UserAccountService"]
