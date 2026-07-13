"""
COMP-AT-004 CredentialAuthenticationService — password login (REQ-L1-010).

Password-login extension to the AuthAndTenancy authentication component. Provides
the credential -> token flow that backs ``POST /api/v1/auth/login/``:

* :meth:`PasswordAuthenticationService.authenticate_credentials` — verify a
  username/password pair in (near) constant time and return the matching active
  :class:`~persistence.models.User`.
* :meth:`PasswordAuthenticationService.issue_token` — mint an HS256 JWT whose
  claims EXACTLY match what :meth:`AuthenticationService.validate_bearer_token`
  expects (``user_id``, ``tenant_id``, ``roles``, ``exp``, ``iat``, ``iss``,
  ``aud``), so the issued token round-trips through ``BearerTokenAuthentication``.

Secret / issuer / audience / TTL are read from Django settings (``AUTH_JWT_*``);
no secret is embedded in code. The issuer side and the validator side read the
same settings, which is what guarantees the round-trip.

Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-004_CredentialAuthenticationService/
  L3_COMP-AT-004_CredentialAuthenticationService_Architecture.md
"""
from __future__ import annotations

import time
from uuid import UUID

from django.conf import settings

from persistence.models import User

from ..errors import AuthenticationFailed
from ..jwt_tokens import encode_hs256
from ..models import UserRole

def _dummy_password_hash() -> str:
    """Return a valid throwaway password hash for constant-time dummy checks.

    Built via Django's configured hasher so :func:`check_password` follows the
    same code path (and cost) as a real verification. Computed lazily and cached
    so the (deliberately expensive) hashing runs at most once per process.
    """
    global _DUMMY_PASSWORD_HASH_CACHE
    if _DUMMY_PASSWORD_HASH_CACHE is None:
        from django.contrib.auth.hashers import make_password

        _DUMMY_PASSWORD_HASH_CACHE = make_password(
            "reqflow-constant-time-dummy-value"
        )
    return _DUMMY_PASSWORD_HASH_CACHE


_DUMMY_PASSWORD_HASH_CACHE: str | None = None


class PasswordAuthenticationService:
    """Username/password authentication and access-token issuance (COMP-AT-004).

    Stateless across calls; the only state is the database and the JWT settings.
    """

    def __init__(
        self,
        *,
        jwt_secret: str | None = None,
        jwt_issuer: str | None = None,
        jwt_audience: str | None = None,
        token_ttl_seconds: int | None = None,
    ) -> None:
        # Fall back to settings; never embed a default secret in code.
        self._jwt_secret = (
            jwt_secret
            if jwt_secret is not None
            else getattr(settings, "AUTH_JWT_SECRET", None)
        )
        self._jwt_issuer = (
            jwt_issuer
            if jwt_issuer is not None
            else getattr(settings, "AUTH_JWT_ISSUER", None)
        )
        self._jwt_audience = (
            jwt_audience
            if jwt_audience is not None
            else getattr(settings, "AUTH_JWT_AUDIENCE", None)
        )
        self._ttl_seconds = (
            token_ttl_seconds
            if token_ttl_seconds is not None
            else int(getattr(settings, "AUTH_JWT_TTL_SECONDS", 43200))
        )

    # -- Credential verification ------------------------------------------

    def authenticate_credentials(self, username: str, password: str) -> User:
        """Verify ``username``/``password`` and return the active user.

        The verification is (near) constant-time: when the user does not exist a
        dummy password check is still performed, so the timing of "unknown user"
        and "known user, wrong password" are comparable.

        Args:
            username: The login username.
            password: The raw password to verify.

        Returns:
            The authenticated, active :class:`~persistence.models.User`.

        Raises:
            AuthenticationFailed: ``invalid_token`` if the credentials do not
                match or the user is inactive. A single error code is used for
                every failure mode so the boundary cannot leak which factor
                failed (no user-enumeration).
        """
        # ``User`` is not tenant-scoped, so a plain lookup is correct here and runs
        # before any tenant context exists (mirrors API-key validation).
        user = User.objects.filter(username=username).first()

        if user is None:
            # Constant-time dummy verification to flatten the timing curve.
            from django.contrib.auth.hashers import check_password as _check

            _check(password, _dummy_password_hash())
            raise AuthenticationFailed("invalid_token")

        if not user.check_password(password):
            raise AuthenticationFailed("invalid_token")

        if not user.is_active:
            raise AuthenticationFailed("invalid_token")

        return user

    # -- Token issuance ----------------------------------------------------

    def resolve_roles(self, user: User) -> tuple[str, ...]:
        """Return the user's active (non-suspended) role names, lower-cased.

        Read via the ``unscoped`` manager: token issuance happens before a tenant
        context is active, and the user's tenant is the natural scope. Roles are
        de-duplicated across workspaces for the token claim.
        """
        roles = (
            UserRole.unscoped.filter(user_id=user.id, suspended_at__isnull=True)
            .values_list("role", flat=True)
        )
        return tuple(sorted({str(r).lower() for r in roles}))

    def issue_token(self, user: User, roles: tuple[str, ...] | None = None) -> str:
        """Mint a signed HS256 JWT for ``user`` (REQ-L1-010).

        The claim set is exactly what ``AuthenticationService.validate_bearer_token``
        consumes, so the token round-trips through ``BearerTokenAuthentication``:
        ``user_id``, ``tenant_id``, ``roles`` plus standard ``iat``/``exp`` and the
        configured ``iss``/``aud``.

        Args:
            user: The user to mint a token for; must have a tenant.
            roles: Explicit role list; resolved from ``UserRole`` when ``None``.

        Returns:
            The compact JWT string (without the ``Bearer `` prefix).

        Raises:
            AuthenticationFailed: ``invalid_token`` if the JWT secret is not
                configured or the user has no tenant (the token would be
                unusable downstream).
        """
        if not self._jwt_secret:
            raise AuthenticationFailed("invalid_token")
        if user.tenant_id is None:
            raise AuthenticationFailed("invalid_token")

        effective_roles = self.resolve_roles(user) if roles is None else tuple(roles)

        issued_at = int(time.time())
        claims: dict[str, object] = {
            "user_id": str(user.id),
            "tenant_id": str(user.tenant_id),
            "roles": list(effective_roles),
            "iat": issued_at,
            "exp": issued_at + self._ttl_seconds,
        }
        if self._jwt_issuer is not None:
            claims["iss"] = self._jwt_issuer
        if self._jwt_audience is not None:
            claims["aud"] = self._jwt_audience

        return encode_hs256(claims, self._jwt_secret)


def _coerce_uuid(value: str) -> UUID:
    """Parse ``value`` into a UUID (helper for callers handling raw ids)."""
    return UUID(str(value))


__all__ = ["PasswordAuthenticationService"]
