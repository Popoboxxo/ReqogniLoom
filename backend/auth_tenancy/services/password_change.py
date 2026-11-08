"""Self-service password change (GitHub #1739, beta.29 C2-T1).

Three surfaces share this one service:

* ``POST /api/v1/auth/password/change/`` (interactive session),
* nothing else today — the CLI reset (``bootstrap_admin --reset-password``)
  reuses :func:`auth_tenancy.provisioning.provision_admin` for the password
  write and only borrows :func:`revoke_refresh_families_for_user`, because the
  operator path must keep working with a short out-of-band ``SYSTEM_ADMIN_
  PASSWORD`` (see ``auth_tenancy/provisioning.py``).

What a change must guarantee
----------------------------
1. The current password is verified with Django's constant-time
   ``check_password`` — a wrong one answers 400, never 401, and never leaks
   whether the account, the password or something else was the problem.
2. The new password passes the same policy as user creation
   (:func:`auth_tenancy.services.password_policy.validate_new_password`).
3. **Every other refresh family of the account is revoked**, so a token
   captured before the change cannot mint a new access token afterwards. The
   session that performed the change is exempt — its ``sid`` comes from the
   ``reqogniloom_refresh`` cookie, *never* from the request body (a caller
   could otherwise exempt a foreign session).
4. The act is audited (``user.password_change``) in the same transaction.

Bearer-only callers
-------------------
A caller with a bare ``Authorization: Bearer`` header (no refresh cookie) has
no ``sid`` to exempt, so ``current_session_id`` is ``None`` and **all**
families are revoked. The access token presented with that request stays
valid until its own ``exp`` (≤ ``AUTH_JWT_TTL_SECONDS``, 3600 s by default);
there is simply no refresh token left to extend it. That is the documented
trade-off: the credential being changed is the password, and the caller proved
knowledge of it.

leaf_id : COMP-AT-001 / COMP-AT-004
req_id  : REQ-L2-AT-001, REQ-L2-AT-003, Issue #1739
"""
from __future__ import annotations

import logging
from uuid import UUID

from django.db import transaction

from audit.models import AuditEntry
from audit.services import log_write
from persistence.models import User
from persistence.tenancy import TenantContext

from ..errors import AuthenticationFailed
from .password_policy import PasswordPolicyError, validate_new_password
from .refresh_token_store import revoke_refresh_families_for_user

__all__ = [
    "INVALID_CURRENT_PASSWORD",
    "PASSWORD_POLICY_VIOLATION",
    "PasswordChangeRejected",
    "change_password",
]

logger = logging.getLogger(__name__)

#: Error codes of :class:`PasswordChangeRejected`. Both map to HTTP 400 at the
#: REST boundary and are declared in ``auth_tenancy.errors._ERROR_CATALOG`` and
#: ``rest_api.serializers._ERROR_MESSAGES``.
INVALID_CURRENT_PASSWORD = "INVALID_CURRENT_PASSWORD"
PASSWORD_POLICY_VIOLATION = "PASSWORD_POLICY_VIOLATION"


class PasswordChangeRejected(Exception):
    """A password change was refused for a caller-correctable reason.

    Attributes:
        code: ``INVALID_CURRENT_PASSWORD`` or ``PASSWORD_POLICY_VIOLATION``.
        messages: Validator sentences for a policy violation; empty for a
            wrong current password (nothing about the stored password may be
            echoed, not even its length rules).
    """

    def __init__(
        self, code: str, *, messages: list[str] | tuple[str, ...] = ()
    ) -> None:
        self.code = code
        self.messages: tuple[str, ...] = tuple(messages)
        super().__init__(code)


def change_password(
    *,
    user_id: UUID,
    current_password: str,
    new_password: str,
    current_session_id: UUID | None = None,
) -> int:
    """Change one user's password and revoke their other refresh families.

    Args:
        user_id: The authenticated caller. Resolved tenant-scoped through the
            active :class:`~persistence.tenancy.TenantContext` (the REST
            middleware arms it; a cross-tenant id therefore cannot match).
        current_password: The caller's current (old) password in cleartext.
        new_password: The desired new password in cleartext.
        current_session_id: ``sid`` of the refresh family that must survive —
            read from the ``reqogniloom_refresh`` cookie, **never** from the
            request body. ``None`` (bearer-only caller) revokes all families.

    Returns:
        The number of refresh-token rows revoked by this change (``0`` when the
        account had no other live session).

    Raises:
        AuthenticationFailed: The user is gone or inactive.
        PasswordChangeRejected: ``INVALID_CURRENT_PASSWORD`` when the current
            password does not match; ``PASSWORD_POLICY_VIOLATION`` when the new
            one fails Django's validators.
    """
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is None:
        raise AuthenticationFailed("authentication_required")

    # Constant-time comparison inside Django's hasher (PBKDF2 ``check_password``
    # uses ``hmac.compare_digest``). A wrong password is a 400, not a 401:
    # the caller *is* authenticated, the submitted proof is what failed.
    if not user.check_password(current_password):
        raise PasswordChangeRejected(INVALID_CURRENT_PASSWORD)

    try:
        validate_new_password(new_password, username=user.username, email=user.email)
    except PasswordPolicyError as exc:
        raise PasswordChangeRejected(
            PASSWORD_POLICY_VIOLATION, messages=exc.messages
        ) from exc

    previous_tenant = TenantContext.get_tenant() if TenantContext.is_set() else None
    with transaction.atomic():
        # Both statements share one transaction: a failure while revoking must
        # not leave the account with a new password but live old sessions.
        user.set_password(new_password)
        user.save(update_fields=["password", "modified_at"])

        revoked = revoke_refresh_families_for_user(
            user.id, "password_change", current_session_id
        )

        try:
            if user.tenant_id is not None:
                TenantContext.set_tenant(user.tenant_id)
            log_write(
                actor=str(user.id),
                actor_type=AuditEntry.ACTOR_TYPE_USER,
                operation=AuditEntry.OP_USER_PASSWORD_CHANGE,
                entity_type="User",
                entity_id=user.id,
                change_reason="Self-service password change",
                details={"other_sessions_revoked": revoked},
                ctx={"source": "rest"},
            )
        except Exception:  # noqa: BLE001 - documented fail-closed audit rule
            # REQ-L2-AL-004: the mutation and its audit entry are one unit. An
            # audit outage must roll the password change back rather than
            # leave an unaudited credential change behind.
            logger.exception(
                "password change audit write failed user_id=%s; rolling back",
                user.id,
            )
            raise
        finally:
            if previous_tenant is None:
                TenantContext.clear_tenant()
            else:
                TenantContext.set_tenant(previous_tenant)

    logger.info(
        "password changed user_id=%s other_sessions_revoked=%s", user.id, revoked
    )
    return revoked
