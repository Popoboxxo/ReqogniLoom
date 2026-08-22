"""
COMP-AT-001 AuthenticationService — the single entry point for identity validation.

Responsibilities (REQ-L2-AT-001/002/009, REQ-L3-AT001-001/002/003):
- Validate JWT Bearer tokens (signature, exp, iss, aud) -> IdentityClaims.
- Validate API keys against the stored SHA-256 hash using ``hmac.compare_digest``
  (constant-time) -> IdentityClaims.
- API-key lifecycle: create (plaintext once), list (metadata only), revoke
  (effective immediately).

Output contract: :class:`~auth_tenancy.context.IdentityClaims` on IF-AT-INT-001
(to AuthorizationService) and IF-AT-INT-002 (to TenantContextService).

Architecture: docs/se/L1/Gesamtsystem/L2/AuthAndTenancySystem/
  Components/COMP-AT-001_AuthenticationService/
  L3_COMP-AT-001_AuthenticationService_Architecture.md
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from django.conf import settings

from ..context import AuthMethod, IdentityClaims
from ..errors import AuthenticationFailed
from ..jwt_tokens import decode_jwt
from ..models import MAX_ACTIVE_API_KEYS_PER_USER as _DEFAULT_MAX_ACTIVE_API_KEYS_PER_USER
from ..models import ApiKey

if TYPE_CHECKING:  # pragma: no cover - import-time only, avoids a hard app dep
    from persistence.models import User

# API-key plaintext format: "reqlo_" + 40 url-safe-ish chars (REQ-L3-AT001-003).
_API_KEY_PREFIX = "reqlo_"
_API_KEY_RANDOM_LEN = 40
_API_KEY_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


@dataclass(frozen=True)
class ApiKeyCreationResult:
    """Result of creating an API key (REQ-L3-AT001-003).

    ``plaintext`` is present exactly once, here, and must be surfaced to the
    caller and then discarded. It is never persisted (only its hash is).
    """

    api_key_id: UUID
    name: str
    plaintext: str


def hash_api_key(plaintext: str) -> str:
    """Return the canonical stored hash ``"sha256:<hex>"`` for ``plaintext``.

    REQ-L3-AT001-002: keys are compared only via this hash, never in plaintext.
    """
    digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def generate_api_key_plaintext() -> str:
    """Generate a new plaintext key ``reqlo_<40 chars>`` (REQ-L3-AT001-003)."""
    body = "".join(secrets.choice(_API_KEY_ALPHABET) for _ in range(_API_KEY_RANDOM_LEN))
    return f"{_API_KEY_PREFIX}{body}"


class AuthenticationService:
    """Identity validation and API-key lifecycle (COMP-AT-001).

    Stateless across calls; the only state is the database. JWT verification
    parameters (secret/issuer/audience) are read from Django settings so the
    component carries no hard-coded secrets (no secrets in code).
    """

    def __init__(
        self,
        *,
        jwt_secret: str | None = None,
        jwt_issuer: str | None = None,
        jwt_audience: str | None = None,
    ) -> None:
        # Fall back to settings; never embed a default secret in code.
        self._jwt_secret = jwt_secret if jwt_secret is not None else getattr(
            settings, "AUTH_JWT_SECRET", None
        )
        self._jwt_issuer = jwt_issuer if jwt_issuer is not None else getattr(
            settings, "AUTH_JWT_ISSUER", None
        )
        self._jwt_audience = jwt_audience if jwt_audience is not None else getattr(
            settings, "AUTH_JWT_AUDIENCE", None
        )

    # -- Bearer token (IF-AT-EXT-IN-001) ----------------------------------

    def validate_bearer_token(self, token: str) -> IdentityClaims:
        """Validate a JWT and build :class:`IdentityClaims` (REQ-L3-AT001-001).

        Args:
            token: The raw JWT (without the ``Bearer `` prefix).

        Returns:
            Immutable identity claims asserted by the token.

        Raises:
            AuthenticationFailed: ``invalid_token`` / ``invalid_signature`` /
                ``token_expired`` per the decode result, or ``invalid_token`` if
                mandatory claims are missing or the token is a refresh token
                (GitHub #135 — refresh tokens must never authenticate a request,
                only ``POST /auth/refresh/`` accepts them).
        """
        if not self._jwt_secret:
            # Misconfiguration must not silently authenticate anyone.
            raise AuthenticationFailed("invalid_token")

        claims = decode_jwt(
            token,
            secret=self._jwt_secret,
            issuer=self._jwt_issuer,
            audience=self._jwt_audience,
        )

        # Refresh tokens carry typ="refresh" and must be rejected here — they
        # are only valid at the dedicated refresh endpoint (GitHub #135).
        if claims.get("typ") == "refresh":
            raise AuthenticationFailed("invalid_token")

        try:
            user_id = UUID(str(claims["user_id"]))
            tenant_id = UUID(str(claims["tenant_id"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationFailed("invalid_token") from exc

        roles = tuple(str(r).lower() for r in claims.get("roles", []))
        return IdentityClaims(
            user_id=user_id,
            tenant_id=tenant_id,
            roles=roles,
            auth_method=AuthMethod.BEARER_TOKEN,
            api_key_id=None,
        )

    # -- Refresh token (GitHub #135) ---------------------------------------

    def validate_refresh_token(self, token: str) -> tuple[UUID, UUID]:
        """Validate a refresh JWT and return ``(user_id, tenant_id)``.

        Distinct from :meth:`validate_bearer_token`: it *requires* the
        ``typ="refresh"`` claim (an access token must not be usable as a
        refresh token) and deliberately returns no roles/claims payload — the
        caller (``RefreshView``) re-resolves fresh roles from the database
        before minting a new access token, avoiding a stale role snapshot on
        a long-lived refresh token (mirrors the workspace-scoped role
        resolution rationale in ``AuthTenancyAuthentication``, GitHub #103).

        Args:
            token: The raw refresh JWT (without the ``Bearer `` prefix).

        Returns:
            ``(user_id, tenant_id)`` asserted by the token.

        Raises:
            AuthenticationFailed: ``invalid_token`` / ``invalid_signature`` /
                ``token_expired`` per the decode result, or ``invalid_token``
                if mandatory claims are missing or ``typ`` is not ``"refresh"``.
        """
        if not self._jwt_secret:
            raise AuthenticationFailed("invalid_token")

        claims = decode_jwt(
            token,
            secret=self._jwt_secret,
            issuer=self._jwt_issuer,
            audience=self._jwt_audience,
        )

        if claims.get("typ") != "refresh":
            raise AuthenticationFailed("invalid_token")

        try:
            user_id = UUID(str(claims["user_id"]))
            tenant_id = UUID(str(claims["tenant_id"]))
        except (KeyError, ValueError) as exc:
            raise AuthenticationFailed("invalid_token") from exc

        return user_id, tenant_id

    def resolve_active_user(self, user_id: UUID, tenant_id: UUID) -> "User | None":
        """Return the active user identified by ``(user_id, tenant_id)``.

        Used by ``RefreshView`` (GitHub #135) after a refresh token validates,
        to re-check that the account still exists/is active/still belongs to
        that tenant before minting a new access token — keeps the direct
        ``persistence.models`` query out of the view layer (architecture
        convention: no direct ORM access in DRF views).

        Args:
            user_id: The ``user_id`` claim from a validated refresh token.
            tenant_id: The ``tenant_id`` claim from a validated refresh token.

        Returns:
            The matching active :class:`~persistence.models.User`, or ``None``
            if no such active user exists in that tenant.
        """
        from persistence.models import User  # local import avoids circular dep

        return User.objects.filter(
            id=user_id, tenant_id=tenant_id, is_active=True
        ).first()

    # -- API key (IF-AT-EXT-IN-002) ---------------------------------------

    def validate_api_key(self, plaintext: str) -> IdentityClaims:
        """Validate an API key in constant time (REQ-L3-AT001-002).

        The lookup uses the stored hash as the index key, then re-verifies with
        ``hmac.compare_digest`` so the decision never short-circuits on a partial
        match. Lookup uses the ``unscoped`` manager because no tenant context
        exists yet at authentication time.

        Args:
            plaintext: The raw API key (e.g. ``reqlo_...``).

        Returns:
            Immutable identity claims for the key's user and tenant.

        Raises:
            AuthenticationFailed: ``invalid_api_key`` (unknown / not matching) or
                ``api_key_revoked``.
        """
        computed_hash = hash_api_key(plaintext)
        api_key = (
            ApiKey.unscoped.select_related("user")
            .filter(key_hash=computed_hash)
            .first()
        )
        if api_key is None:
            raise AuthenticationFailed("invalid_api_key")

        # Defensive re-verification in constant time (REQ-L3-AT001-002).
        if not hmac.compare_digest(api_key.key_hash, computed_hash):
            raise AuthenticationFailed("invalid_api_key")

        if api_key.revoked_at is not None:
            raise AuthenticationFailed("api_key_revoked")

        if api_key.user.tenant_id is None:
            # Key valid but user has no tenant -> resolution will fail downstream.
            raise AuthenticationFailed("invalid_api_key")

        if not api_key.user.is_active:
            # Fix round 3 (C-2): a deactivated user's API key must stop
            # authenticating immediately, mirroring `resolve_active_user`
            # (bearer-token refresh path) and the login path, both of which
            # already reject inactive users. Without this, deactivation had
            # no effect on MCP access: the key kept validating, and
            # `is_tenant_admin()`/role resolution still (before this same
            # fix round) returned True for the deactivated admin, letting
            # them undo their own deactivation via MCP.
            raise AuthenticationFailed("invalid_api_key")

        return IdentityClaims(
            user_id=api_key.user_id,
            tenant_id=api_key.user.tenant_id,
            roles=(),  # roles are resolved by AuthorizationService from UserRole.
            auth_method=AuthMethod.API_KEY,
            api_key_id=api_key.id,
        )

    # -- Lifecycle (REQ-L3-AT001-003) -------------------------------------

    def create_api_key(
        self, *, user_id: UUID, tenant_id: UUID, name: str
    ) -> ApiKeyCreationResult:
        """Create an API key and return its plaintext exactly once.

        Args:
            user_id: Owner user primary key.
            tenant_id: Tenant the key belongs to.
            name: Human-readable label.

        Returns:
            :class:`ApiKeyCreationResult` containing the one-time plaintext.

        Raises:
            ValueError: If the user already has ``MAX_ACTIVE_API_KEYS_PER_USER``
                active keys.
        """
        # #606: configurable via settings (env var) so CI/CD environments that
        # provision a key per agent/QA-run aren't stuck with the fixed default.
        max_active = getattr(
            settings,
            "MAX_ACTIVE_API_KEYS_PER_USER",
            _DEFAULT_MAX_ACTIVE_API_KEYS_PER_USER,
        )
        active_count = ApiKey.unscoped.filter(
            user_id=user_id, revoked_at__isnull=True
        ).count()
        if active_count >= max_active:
            raise ValueError(
                f"User already has the maximum of {max_active} active API keys."
            )

        plaintext = generate_api_key_plaintext()
        api_key = ApiKey.unscoped.create(
            user_id=user_id,
            tenant_id=tenant_id,
            name=name,
            key_hash=hash_api_key(plaintext),
        )
        return ApiKeyCreationResult(
            api_key_id=api_key.id, name=name, plaintext=plaintext
        )

    def list_api_keys(self, *, user_id: UUID) -> list[dict[str, object]]:
        """List a user's API keys as metadata only — never the plaintext."""
        keys = ApiKey.unscoped.filter(user_id=user_id).order_by("created_at")
        return [
            {
                "id": str(k.id),
                "name": k.name,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "revoked": k.revoked_at is not None,
            }
            for k in keys
        ]

    def revoke_api_key(self, *, api_key_id: UUID, user_id: UUID | None = None) -> None:
        """Revoke a key; effective immediately for subsequent requests.

        Args:
            api_key_id: UUID of the key to revoke.
            user_id: Optional owner user ID; if provided, validates ownership.

        Raises:
            AuthenticationFailed: ``invalid_api_key`` if the key does not exist,
                if user_id is provided and does not match the key's owner.
        """
        api_key = ApiKey.unscoped.filter(id=api_key_id).first()
        if api_key is None:
            raise AuthenticationFailed("invalid_api_key")
        if user_id is not None and api_key.user_id != user_id:
            raise AuthenticationFailed("invalid_api_key")
        if api_key.revoked_at is None:
            api_key.revoked_at = datetime.now(timezone.utc)
            api_key.save(update_fields=["revoked_at", "modified_at"])


__all__ = [
    "AuthenticationService",
    "ApiKeyCreationResult",
    "hash_api_key",
    "generate_api_key_plaintext",
]
