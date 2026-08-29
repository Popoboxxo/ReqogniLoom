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
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from django.conf import settings
from django.db import transaction

from ..context import AuthMethod, IdentityClaims
from ..errors import AuthenticationFailed
from ..jwt_tokens import decode_jwt
from ..models import MAX_ACTIVE_API_KEYS_PER_USER as _DEFAULT_MAX_ACTIVE_API_KEYS_PER_USER
from ..models import ApiKey, RefreshToken

logger = logging.getLogger(__name__)

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


def _api_key_pepper() -> str:
    """Return the configured server-side pepper, or ``""`` when unset."""
    return (getattr(settings, "API_KEY_PEPPER", "") or "").strip()


def _reuse_grace_seconds() -> float:
    """Return the refresh-token replay grace window in seconds (SA-32).

    ``0`` (the default) means strict reuse detection. Read per call rather than
    cached at import so ``override_settings`` works in tests and an operator can
    change it without a code change.
    """
    try:
        return float(getattr(settings, "AUTH_REFRESH_REUSE_GRACE_SECONDS", 0) or 0)
    except (TypeError, ValueError):  # pragma: no cover - misconfiguration
        return 0.0


def hash_api_key(plaintext: str) -> str:
    """Return the canonical stored hash for ``plaintext`` (REQ-L3-AT001-002).

    Two formats exist, distinguished by their prefix:

    * ``"sha256p1:<hex>"`` — HMAC-SHA256 keyed with ``settings.API_KEY_PEPPER``.
      Produced for every new key once a pepper is configured.
    * ``"sha256:<hex>"`` — the original bare digest. Still produced when no
      pepper is configured, and still *accepted* on lookup either way.

    SA-34 (SYSTEMAUDIT-2026-08-27 §4.6 F11): a bare SHA-256 of a 40-character
    random key is not brute-forceable, but it is also not defence in depth — an
    attacker with a database dump can test candidate keys entirely offline. A
    pepper stored outside the database (env/secret manager, never in a column)
    means a stolen dump alone is not enough.

    The version prefix is what makes the rollout non-breaking: see
    :func:`verify_api_key_hash_candidates` and the note on
    :meth:`AuthenticationService.validate_api_key`.
    """
    pepper = _api_key_pepper()
    if not pepper:
        return f"sha256:{hashlib.sha256(plaintext.encode('utf-8')).hexdigest()}"
    digest = hmac.new(
        pepper.encode("utf-8"), plaintext.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"sha256p1:{digest}"


def hash_api_key_legacy(plaintext: str) -> str:
    """Return the pre-SA-34 unpeppered hash ``"sha256:<hex>"``.

    Kept as an explicit function (rather than an inline branch) because it is
    only ever used to *recognise* keys issued before a pepper was configured —
    never to create new ones.
    """
    return f"sha256:{hashlib.sha256(plaintext.encode('utf-8')).hexdigest()}"


def api_key_hash_candidates(plaintext: str) -> tuple[str, ...]:
    """Return every stored-hash form ``plaintext`` could legitimately match.

    With a pepper configured this is ``(peppered, legacy)``: keys minted before
    the pepper was introduced are stored unpeppered and CANNOT be re-hashed
    (the plaintext is not recoverable), so they must keep authenticating until
    they are rotated. Without a pepper it is just the legacy form.

    ROLLOUT (SA-34): configuring ``API_KEY_PEPPER`` peppers new keys only.
    Existing keys stay valid in their old form and are only upgraded by being
    revoked and re-created. Until every key has been rotated the fleet is
    mixed, and the old rows carry exactly the pre-fix risk. Operators who want
    the guarantee immediately must force a key rotation; ``manage.py
    cleanup_revoked_api_keys`` helps clean up afterwards.
    """
    peppered = hash_api_key(plaintext)
    legacy = hash_api_key_legacy(plaintext)
    if peppered == legacy:
        return (legacy,)
    return (peppered, legacy)


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

        Signature/expiry/``typ`` checks only — it does **not** consult the
        server-side rotation state. Callers that exchange the token must
        additionally call :meth:`rotate_refresh_token`, which is where SA-32's
        reuse detection lives. Kept separate so the two concerns (is this JWT
        authentic? has this JWT already been spent?) stay independently
        testable, and so existing callers of this method keep their contract.

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

    # -- Refresh-token rotation with reuse detection (SA-32) ---------------

    def rotate_refresh_token(self, token: str) -> UUID:
        """Spend the refresh token in *token* and return its family id.

        SYSTEMAUDIT-2026-08-27 §4.6 F7. Implements the OAuth 2.0 BCP §4.13.2
        refresh-token-rotation scheme:

        * a token may be exchanged **exactly once**;
        * presenting an already-spent token means two parties hold it — the
          legitimate client and whoever stole it. Since the server cannot tell
          them apart, the entire family (this login and every token rotated out
          of it) is revoked and both are forced to re-authenticate.

        The row is claimed under ``select_for_update`` inside a transaction, so
        two concurrent exchanges of the same token cannot both succeed: the
        loser sees ``used_at`` already set and trips reuse detection.

        KNOWN FALSE-POSITIVE — multiple browser tabs
        ---------------------------------------------
        Cookies are shared across tabs but the SPA's single-flight refresh guard
        (``frontend/src/api/client.ts``) is per JS context. Two tabs hitting a
        401 at the same moment therefore issue two refreshes with the *same*
        cookie; one wins and the other is indistinguishable from a replay, so
        strict detection logs both tabs out.

        ``AUTH_REFRESH_REUSE_GRACE_SECONDS`` (default ``0`` = strict, the
        behaviour this finding asked for) tolerates a replay that arrives within
        N seconds of the legitimate rotation: the family survives and the caller
        gets a fresh token in it. Setting it trades a narrow detection window —
        a thief replaying within N seconds of the real user goes unnoticed, and
        they already held a usable token — for not logging multi-tab users out.
        Deploy strict first and only raise it if the false positive is observed.

        Args:
            token: The raw refresh JWT. Must already have passed
                :meth:`validate_refresh_token`.

        Returns:
            The ``session_id`` (family) the caller should mint the replacement
            token into, so the chain stays linked.

        Raises:
            AuthenticationFailed: ``invalid_token`` if the token carries no
                rotation claims, has no matching row, or was already
                spent/revoked. The code is deliberately the same in all cases —
                the caller clears the cookies and the client re-authenticates,
                and a distinct "you are being replayed" code would only tell an
                attacker that their theft was noticed.
        """
        if not self._jwt_secret:
            raise AuthenticationFailed("invalid_token")

        claims = decode_jwt(
            token,
            secret=self._jwt_secret,
            issuer=self._jwt_issuer,
            audience=self._jwt_audience,
        )
        try:
            jti = UUID(str(claims["jti"]))
        except (KeyError, ValueError) as exc:
            # Pre-SA-32 tokens carry no ``jti``. They cannot be reuse-checked,
            # and silently accepting them would keep the vulnerability alive
            # for the whole 30-day refresh TTL after deploy. Rejecting forces
            # one re-login per active session at rollout — see the migration
            # note in auth_tenancy/migrations for the operational impact.
            raise AuthenticationFailed("invalid_token") from exc

        # The rejection is raised *after* the transaction commits, never inside
        # it: raising within ``atomic()`` rolls the block back, which would undo
        # the very family revocation that reuse detection just performed and
        # leave the leaked session alive. The outcome is therefore recorded
        # here and acted on below.
        reuse_detected: tuple[UUID, UUID] | None = None
        session_id: UUID | None = None

        with transaction.atomic():
            # unscoped + select_for_update: this runs on the public
            # /auth/refresh/ endpoint, before any tenant context exists. The row
            # lock serialises concurrent exchanges of the same token, so the
            # loser of a race observes ``used_at`` and trips detection rather
            # than both sides succeeding.
            record = (
                RefreshToken.unscoped.select_for_update()
                .filter(jti=jti)
                .first()
            )
            if record is None:
                # Signature was valid, so we issued this token — but its row is
                # gone (purged after expiry, or the family was hard-deleted).
                # Treat as unusable rather than trusting the stateless claim.
                pass
            elif record.revoked_at is not None:
                # Family already burned (earlier reuse, or logout). Checked
                # FIRST: a revoked row usually also carries ``used_at``, and the
                # grace branch below must never resurrect a burned family.
                pass
            elif record.used_at is not None and self._within_reuse_grace(record):
                # Concurrent refresh from a second browser tab sharing the same
                # cookie jar, not a theft — see the multi-tab note above. Hand
                # out a fresh token in the same family instead of burning it.
                logger.info(
                    "Refresh-token replay within the %.1fs grace window "
                    "(user=%s session=%s) — treated as a concurrent client, "
                    "not as reuse.",
                    _reuse_grace_seconds(),
                    record.user_id,
                    record.session_id,
                )
                session_id = record.session_id
            elif record.used_at is not None:
                # === Reuse detected === Burn the whole family, inside this same
                # transaction so no concurrent rotation can slip a fresh token
                # into the family between detection and revocation.
                self._revoke_refresh_family(
                    record.session_id, reason="reuse_detected"
                )
                reuse_detected = (record.user_id, record.session_id)
            else:
                record.used_at = datetime.now(tz=timezone.utc)
                record.save(update_fields=["used_at"])
                session_id = record.session_id

        if reuse_detected is not None:
            logger.warning(
                "Refresh-token reuse detected — revoked session family "
                "(user=%s session=%s). Both the legitimate client and the "
                "holder of the replayed token must re-authenticate.",
                reuse_detected[0],
                reuse_detected[1],
            )
        if session_id is None:
            raise AuthenticationFailed("invalid_token")
        return session_id

    @staticmethod
    def _within_reuse_grace(record: RefreshToken) -> bool:
        """Return whether *record* was spent inside the concurrency grace window.

        Zero (the default) disables the window entirely, which is the strict
        reuse-detection behaviour. See :meth:`rotate_refresh_token` for why the
        window exists and what it costs.
        """
        grace = _reuse_grace_seconds()
        if grace <= 0 or record.used_at is None:
            return False
        age = (datetime.now(tz=timezone.utc) - record.used_at).total_seconds()
        return 0 <= age <= grace

    @staticmethod
    def _revoke_refresh_family(session_id: UUID, *, reason: str) -> int:
        """Revoke every still-live token in *session_id*. Returns the count."""
        return RefreshToken.unscoped.filter(
            session_id=session_id, revoked_at__isnull=True
        ).update(revoked_at=datetime.now(tz=timezone.utc), revoked_reason=reason)

    def revoke_refresh_token(self, token: str) -> None:
        """Revoke the family of *token* — best effort, used on logout.

        Logout is a client-initiated end of session, so the family must die with
        it; otherwise a refresh token captured before logout would outlive the
        session it belonged to. Never raises: a logout must succeed even when
        the presented cookie is malformed, expired or already revoked.

        Args:
            token: The raw refresh JWT from the request cookie.
        """
        if not self._jwt_secret or not token:
            return
        try:
            claims = decode_jwt(
                token,
                secret=self._jwt_secret,
                issuer=self._jwt_issuer,
                audience=self._jwt_audience,
            )
            session_id = UUID(str(claims["sid"]))
        except Exception:
            # Expired/forged/legacy cookie — nothing to revoke.
            return
        self._revoke_refresh_family(session_id, reason="logout")

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
        # SA-34: a key may be stored peppered (new) or unpeppered (issued
        # before API_KEY_PEPPER was configured). Both forms are looked up in one
        # indexed query; only ``hash_api_key`` decides which form new keys get.
        candidates = api_key_hash_candidates(plaintext)
        api_key = (
            ApiKey.unscoped.select_related("user")
            .filter(key_hash__in=candidates)
            .first()
        )
        if api_key is None:
            raise AuthenticationFailed("invalid_api_key")

        # Defensive re-verification in constant time (REQ-L3-AT001-002). Every
        # candidate is compared so the loop does not exit early on the first
        # mismatch, preserving the constant-time property across both forms.
        matched = False
        for candidate in candidates:
            matched |= hmac.compare_digest(api_key.key_hash, candidate)
        if not matched:
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

        SA-39 (Systemaudit 2026-08-27 §4.1 #11): count-then-create is a
        time-of-check/time-of-use window — N parallel requests all read
        ``max_active - 1`` and all create, so the cap is exceeded by exactly the
        concurrency. The owning ``User`` row is therefore locked for the whole
        check-and-create span. Locking the *user* rather than the existing keys
        is deliberate: a ``SELECT ... FOR UPDATE`` over the ApiKey rows locks
        nothing when the user has no keys yet, which is precisely the case where
        two requests could both create the first key. The lock is held only for
        two statements and is per user, so it serialises nothing else.
        """
        # #606: configurable via settings (env var) so CI/CD environments that
        # provision a key per agent/QA-run aren't stuck with the fixed default.
        max_active = getattr(
            settings,
            "MAX_ACTIVE_API_KEYS_PER_USER",
            _DEFAULT_MAX_ACTIVE_API_KEYS_PER_USER,
        )

        # Deferred import: this module keeps ``persistence.models`` out of its
        # import graph (see the TYPE_CHECKING block above).
        from persistence.models import User

        with transaction.atomic():
            # Serialise concurrent creations for this user. ``User`` is not a
            # TenantScopedModel (it is an identity root, like ``Tenant``), so
            # ``objects`` carries no tenant filter and needs none here: the pk
            # is the authenticated caller's own user id.
            User.objects.select_for_update().filter(pk=user_id).first()

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
    "api_key_hash_candidates",
    "hash_api_key",
    "hash_api_key_legacy",
    "generate_api_key_plaintext",
]
