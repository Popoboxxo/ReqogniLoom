"""TOTP second factor for staff accounts (#1308, Plan E / WP E3.2).

Single entry point for every operation on a user's TOTP authenticator: enroll,
confirm, verify, regenerate recovery codes, disable, break-glass reset, and the
signed login challenge that carries "password step passed" from the login view to
the second-factor view.

Why a service and not view helpers: the second factor is a credential. Every
caller (REST login, Django admin login, management commands) must go through the
same six security rules, or the weakest caller defines the security level:

1. **Secret storage.** The TOTP secret exists in the database only as a Fernet
   ciphertext (``persistence.encryption.encrypt_secret``, ``FIELD_ENCRYPTION_KEY``).
   Decryption is *strict*: a missing Fernet prefix or an ``InvalidToken`` raises
   :class:`MfaUnavailableError` and therefore refuses the login (fail-closed).
   ``persistence.encryption.decrypt_secret``'s deliberate plaintext pass-through
   is **not** used for this column — see :meth:`MfaService._decrypt_totp_secret`.
2. **Replay.** An accepted code's TOTP time step must be strictly greater than
   ``UserTotpDevice.last_used_step``; the update happens under
   ``select_for_update()`` so two concurrent requests carrying the same code
   cannot both succeed.
3. **Brute force.** The accepted window is ±``MFA_TOTP_VALID_WINDOW`` steps
   (capped at 2, so at most 5 codes out of 1e6; the default of 1 gives 3). Every
   *wrong* code — including a wrong recovery code — increments
   ``failed_attempts``; at ``MFA_MAX_FAILED_ATTEMPTS`` the device is locked for
   ``MFA_LOCKOUT_SECONDS``. A success resets both, and a **replay** is rejected
   without counting: it can never grant access, and counting it would let a
   double-click or a client retry lock a legitimate user out.
4. **Comparison.** TOTP candidates are compared with ``hmac.compare_digest``, and
   the recovery-code lookup is always user-bound (``user=…, code_hash=…``), never
   a global lookup by hash — otherwise one user's code could authenticate another
   user.
4a. **Single-use challenge.** A challenge nonce is burned in the cache after a
   successful second factor; a second success with the same challenge is
   rejected. A cache outage raises :class:`MfaUnavailableError` (fail-closed):
   without the cache the nonce cannot be burned, so the single-use guarantee
   cannot be honoured.
5. **Recovery codes.** Ten codes, 80 bits each, ``XXXX-XXXX-XXXX-XXXX``, stored as
   ``hash_api_key(normalize(code))`` — HMAC-SHA256 with the configured
   ``API_KEY_PEPPER``; an empty pepper makes it an unkeyed SHA-256 (80-bit codes
   keep offline brute force impractical either way). Single-use via ``used_at``
   under ``select_for_update()``; regeneration deletes the previous set so an old
   code can never be replayed, all under the device row lock.
6. **Audit.** Enroll / disable / recovery use / regenerate / reset / grant are
   written as ``AuditEntry`` rows when the user has a tenant, and *always*
   additionally to the ``reqogniloom.security`` logger. Neither ever receives a
   secret or a code.

Framework-neutral on purpose: exceptions carry machine-readable codes that the
DRF layer (WP E3.4/E3.6) maps to HTTP status codes, so this module has no import
edge into ``rest_api``.

Requirements: #1308 (E3), ADR-021.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

import pyotp
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from audit.models import AuditEntry
from audit.services import log_write
from persistence.encryption import ENCRYPTED_PREFIX, decrypt_secret, encrypt_secret
from persistence.models import User
from persistence.tenancy import TenantContext

from ..models import UserMfaEnrollmentGrant, UserRecoveryCode, UserTotpDevice
from .authentication import hash_api_key

logger = logging.getLogger("reqogniloom.security")

#: TOTP parameters. Fixed (not configurable) on purpose: every authenticator app
#: defaults to these, and a mismatch between the enrollment URI and the verifier
#: would lock users out with a code that looks right.
TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30

#: Number and shape of the minted recovery codes. 16 characters over the RFC 4648
#: Base32 alphabet is 80 bits — far beyond guessable, and short enough to type.
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 16
_RECOVERY_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

#: Signing salt for the login challenge. Versioned: rotating the payload shape
#: means bumping this, which invalidates every outstanding challenge at once.
#: v2 binds the challenge to the credential epoch (security review F5), so a
#: challenge issued before a forced password change can never be completed
#: afterwards — v1 tokens simply stop verifying, which is the intended fail-
#: closed behaviour rather than a compatibility concern.
CHALLENGE_SALT = "reqlo.mfa.challenge.v2"
_CHALLENGE_CACHE_PREFIX = "mfa:challenge:used:"

_MODE_OFF = "off"
_MODE_OPTIONAL = "optional"
_MODE_REQUIRED = "required"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MfaError(Exception):
    """Base class for every second-factor rejection.

    Subclasses are deliberately specific enough that the REST layer maps each to
    one HTTP status without re-deriving the cause (WP E3.4).
    """


class MfaNotAllowedError(MfaError):
    """The account may not use a second factor (not staff/superuser)."""


class MfaAlreadyEnrolledError(MfaError):
    """A *confirmed* device already exists; disable it before re-enrolling."""


class MfaNotEnrolledError(MfaError):
    """No device exists for this user."""


class MfaInvalidCodeError(MfaError):
    """The presented TOTP or recovery code is wrong, replayed, or unknown."""


class MfaInvalidCredentialsError(MfaError):
    """The secondary credential (password on disable) is wrong."""


class MfaLockedError(MfaError):
    """Too many failed attempts; the device is temporarily locked."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(int(retry_after), 1)
        super().__init__(f"MFA device locked for {self.retry_after}s")


class MfaRequiredError(MfaError):
    """Policy forbids removing the second factor (``MFA_STAFF_ENFORCEMENT``)."""


class MfaEnrollmentGrantConflictError(MfaError):
    """A concurrent request already replaced this user's enrollment grant.

    The backstop behind the per-user row lock in
    :meth:`MfaService.grant_enrollment`: if the partial unique constraint
    ``uq_mfa_grant_user_unused`` fires anyway, the caller gets a domain error
    (409-able) instead of an ``IntegrityError`` escaping as a 500.
    """


class MfaEnrollmentRequiresGrantError(MfaError):
    """``MFA_STAFF_ENFORCEMENT=required`` and no valid enrollment grant exists.

    Binding decision ENT-E7 = A / QR-S01: under ``required`` a staff account
    without a confirmed device must not self-enroll from a password-only session
    — an attacker holding a stolen password would otherwise register *their*
    authenticator and lock the real owner out. Only an administrator-issued grant
    (``manage.py mfa_reset``) unlocks enrollment. Mapped to HTTP 403 in WP E3.4.
    """


class MfaChallengeInvalidError(MfaError):
    """The signed challenge is malformed, expired, already used, or foreign."""


class MfaUnavailableError(MfaError):
    """The second factor cannot be evaluated right now — fail closed."""


@dataclass(frozen=True)
class EnrollmentData:
    """What ``begin_enrollment`` returns to the caller (shown exactly once).

    Both payload fields are ``repr=False`` (security review F1): the default
    dataclass ``__repr__`` would put the live TOTP secret — and the
    ``otpauth://`` URI that embeds it — into every log line, traceback,
    exception-reporter payload and debugger dump that happens to stringify this
    object. Rendering it must stay an explicit attribute access.
    """

    secret_b32: str = field(repr=False)
    otpauth_uri: str = field(repr=False)
    digits: int = TOTP_DIGITS
    period: int = TOTP_PERIOD_SECONDS


# ---------------------------------------------------------------------------
# Setting accessors — read per call so ``override_settings`` works
# ---------------------------------------------------------------------------


def _int_setting(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except (TypeError, ValueError):  # pragma: no cover - misconfiguration
        return default


def enforcement_mode() -> str:
    """Return the active ``MFA_STAFF_ENFORCEMENT`` value (``off|optional|required``)."""
    mode = str(getattr(settings, "MFA_STAFF_ENFORCEMENT", _MODE_OPTIONAL)).strip().lower()
    if mode not in (_MODE_OFF, _MODE_OPTIONAL, _MODE_REQUIRED):
        raise ImproperlyConfigured(
            f"MFA_STAFF_ENFORCEMENT={mode!r} is not one of "
            f"off/optional/required."
        )
    return mode


def enroll_grant_ttl_seconds() -> int:
    """Return the enrollment-grant lifetime, refusing anything above 24 h.

    Checked here as well as at settings import: the plan's binding decision
    (ENT-E7 = A) makes "≤ 24 h" a property of the *grant*, not of a particular
    entry point, so a test or an operator overriding the setting cannot widen it.
    """
    ttl = _int_setting("MFA_ENROLL_GRANT_TTL_SECONDS", 86400)
    max_ttl = _int_setting("MFA_ENROLL_GRANT_MAX_TTL_SECONDS", 86400)
    if ttl > max_ttl:
        raise ImproperlyConfigured(
            f"MFA_ENROLL_GRANT_TTL_SECONDS must not exceed {max_ttl}s (24 h), "
            f"got {ttl}s."
        )
    if ttl <= 0:
        raise ImproperlyConfigured(
            f"MFA_ENROLL_GRANT_TTL_SECONDS must be positive, got {ttl}s."
        )
    return ttl


def challenge_ttl_seconds() -> int:
    """Return the challenge lifetime, refusing anything above 15 minutes.

    Security review F6: ``MFA_CHALLENGE_TTL_SECONDS`` was the only MFA setting
    without a ceiling, so a misconfigured deployment (or an
    ``override_settings`` in a test) could turn a "password step passed" proof
    into a long-lived bearer credential. 900 s matches the lockout window and
    is comfortably above any human's two-step login. Checked at import time in
    ``settings`` *and* here, so an override cannot widen it silently.
    """
    ttl = _int_setting("MFA_CHALLENGE_TTL_SECONDS", 300)
    max_ttl = _int_setting("MFA_CHALLENGE_TTL_MAX_SECONDS", 900)
    if ttl <= 0:
        raise ImproperlyConfigured(
            f"MFA_CHALLENGE_TTL_SECONDS must be positive, got {ttl}s."
        )
    if ttl > max_ttl:
        raise ImproperlyConfigured(
            f"MFA_CHALLENGE_TTL_SECONDS must not exceed {max_ttl}s, got {ttl}s."
        )
    return ttl


def totp_valid_window() -> int:
    """Return ``MFA_TOTP_VALID_WINDOW``, refusing anything above 2 steps.

    The window is the *only* knob that widens the guessable space: at
    ``2 * window + 1`` accepted codes per 30 s, a window of 2 already means 5
    codes out of 1e6 per attempt. Enforced here as well as at settings import so
    an ``override_settings`` in a test (or a future caller) cannot widen it
    silently.
    """
    window = _int_setting("MFA_TOTP_VALID_WINDOW", 1)
    if window < 0 or window > 2:
        raise ImproperlyConfigured(
            "MFA_TOTP_VALID_WINDOW must be between 0 and 2, got "
            f"{window}."
        )
    return window


# ---------------------------------------------------------------------------
# Recovery-code helpers
# ---------------------------------------------------------------------------


def normalize_recovery_code(code: str) -> str:
    """Return the canonical form of a user-entered recovery code.

    Upper-cases and drops every hyphen and whitespace character, so
    ``"abcd-efgh ijkl-mnop"`` and ``"ABCDEFGHIJKLMNOP"`` hash identically. Both
    minting and lookup go through this function, so the two can never drift.

    Non-string input (an ``int`` or ``null`` straight out of a JSON body) is
    coerced to ``""``: the caller then sees the normal "invalid code" rejection
    instead of an ``AttributeError`` surfacing as a 500 (security review F8).
    """
    text = code if isinstance(code, str) else ""
    return "".join(text.upper().split()).replace("-", "")


def _generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Mint ``count`` fresh recovery codes in ``XXXX-XXXX-XXXX-XXXX`` form."""
    codes: list[str] = []
    for _ in range(count):
        body = "".join(
            secrets.choice(_RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH)
        )
        groups = "-".join(
            body[index : index + 4] for index in range(0, RECOVERY_CODE_LENGTH, 4)
        )
        codes.append(groups)
    return codes


def _hash_recovery_code(code: str) -> str:
    """Return the stored hash for a recovery code (SA-34 helper).

    ``hash_api_key`` is HMAC-SHA256 keyed with the configured ``API_KEY_PEPPER``;
    with an empty pepper it degenerates to an unkeyed SHA-256. Either way the
    input is an 80-bit code, so an offline attacker holding a database dump still
    faces 2^80 work — the pepper is defence in depth, not the load-bearing part.
    """
    return hash_api_key(normalize_recovery_code(code))


def _credential_digest(user: User) -> str:
    """Return a truncated HMAC of the user's *current* password hash (F5).

    The signed challenge carries this value and every read compares it against
    the user row. A forced password change (or any other password rotation)
    therefore invalidates every outstanding challenge at once: a challenge is a
    proof of "this session already passed the password step", and that proof is
    only valid for the credential that produced it. Deliberately derived from
    the already-salted hash rather than ``password_changed_at`` (which the model
    does not carry) — it needs no schema change and cannot leak the hash itself.

    Security review follow-up #2: HMAC-SHA256 keyed with ``SECRET_KEY`` rather
    than a bare SHA-256. The input is already a salted PBKDF2 hash, so a plain
    digest is not reversible either — but a keyed MAC means an attacker who can
    read both the challenge payload and a stolen password hash cannot compute
    the expected value offline without the server key. Rotating ``SECRET_KEY``
    invalidates outstanding challenges (fail-closed, same as a password change).
    """
    key = str(getattr(settings, "SECRET_KEY", "")).encode("utf-8")
    return hmac.new(
        key, (user.password or "").encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


def _current_step() -> int:
    """Return the current TOTP time step (unix seconds // period).

    A module-level function rather than an inline ``int(time.time()) // 30`` so
    the window/replay tests can pin the step deterministically instead of racing
    the 30-second boundary.
    """
    return int(time.time()) // TOTP_PERIOD_SECONDS


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MfaService:
    """Stateless TOTP second-factor service (COMP-AT-001 extension)."""

    # -- policy -----------------------------------------------------------

    def mfa_required(self, user: User) -> bool:
        """Return whether ``user`` must present a second factor.

        ``off``      → never. The feature is entirely disabled.
        ``optional`` → only accounts that already confirmed a device, so an
                       upgrade never locks anybody out and enrollment stays
                       voluntary.
        ``required`` → every staff/superuser account (enrolled or not — the
                       login view decides between challenge and
                       enrollment-grant), plus anyone who confirmed a device.
        """
        mode = enforcement_mode()
        if mode == _MODE_OFF:
            return False
        confirmed = self._has_confirmed_device(user)
        if mode == _MODE_REQUIRED:
            return bool(user.is_staff or user.is_superuser) or confirmed
        return confirmed

    def is_enrolled(self, user: User) -> bool:
        """Alias of the device predicate, for the status endpoint (WP E3.6)."""
        return self._has_confirmed_device(user)

    def status(self, user: User) -> dict[str, Any]:
        """Return the caller's second-factor state for ``GET /auth/mfa/status/``.

        One service call rather than three model queries in the view: the DRF
        layer stays free of persistence imports (project layering rule) and the
        "what does the UI need to know" shape has exactly one definition.
        """
        device = UserTotpDevice.objects.filter(user=user).first()
        confirmed_at = device.confirmed_at if device is not None else None
        return {
            "enrolled": confirmed_at is not None,
            "confirmed_at": confirmed_at,
            "recovery_codes_remaining": UserRecoveryCode.objects.filter(
                user=user, used_at__isnull=True
            ).count(),
            "enforcement": enforcement_mode(),
            "required": self.mfa_required(user),
        }

    @staticmethod
    def _has_confirmed_device(user: User) -> bool:
        return UserTotpDevice.objects.filter(
            user=user, confirmed_at__isnull=False
        ).exists()

    @staticmethod
    def _require_active(user: User) -> None:
        """Refuse a deactivated account, mirroring ``_load_challenge_user``.

        A deactivated account must not get a factor accepted (or be able to
        enroll a new one): the login view and the admin form both reject such
        users later anyway, but a second factor accepted here for an account
        that is already disabled is an unnecessary oracle, and an enrollment
        grant could otherwise be burned on a dead account.
        """
        if not getattr(user, "is_active", False):
            raise MfaNotEnrolledError("This account is not active.")

    def _second_factor_is_mandatory(self, user: User) -> bool:
        """True when policy forbids removing ``user``'s second factor.

        ``off``/``optional`` never forbid removal — enrolment there is the
        user's own choice, so un-enrolling must stay possible. Under
        ``required`` it is exactly :meth:`mfa_required`: every staff/superuser
        account *and* any confirmed non-staff account. The previous
        ``is_staff``-only check let a confirmed non-staff account under
        ``required`` remove its factor (security review F12).
        """
        return enforcement_mode() == _MODE_REQUIRED and self.mfa_required(user)

    def step_up_required(self, user: User, amr: tuple[str, ...] | None) -> bool:
        """Whether ``amr`` fails the second-factor gate for ``user`` (WP E3.6).

        The single predicate behind the "a password-only session must not
        perform this action" rule. Coverage is exactly
        :meth:`mfa_required`'s under ``MFA_STAFF_ENFORCEMENT=required`` — every
        staff/superuser account *plus* any non-staff account that confirmed a
        device — and no one at all under ``off``/``optional``:

        * under ``required`` a staff/superuser account always needs ``"otp"``
          in the request's authentication-method references (RFC 8176), enrolled
          or not;
        * a confirmed non-staff account is covered too, because ``required``
          already challenges it at login — excluding it here would let a
          half-protected account mint a key that outlives its factor
          (security review follow-up #4: no silent non-staff gap);
        * an API key carries ``()`` by construction, so it always fails — which
          is exactly the property that stops a leaked key from creating a
          long-lived sibling credential;
        * ``off``/``optional`` never require a step-up: key creation stays
          available to everyone exactly as before.

        Note the gate keys on *enforcement* as well as ``mfa_required``: under
        ``optional`` a confirmed user is challenged at login but is not forced
        into a step-up to manage their own keys (the factor is voluntary there).
        """
        if enforcement_mode() != _MODE_REQUIRED:
            return False
        if not self.mfa_required(user):
            return False
        return "otp" not in tuple(amr or ())

    @staticmethod
    def _require_staff(user: User) -> None:
        if not (user.is_staff or user.is_superuser):
            raise MfaNotAllowedError(
                "A second factor can only be enrolled for a staff account."
            )

    # -- enrollment -------------------------------------------------------

    def begin_enrollment(self, user: User) -> EnrollmentData:
        """Issue a fresh, unconfirmed TOTP secret for ``user``.

        A pending (unconfirmed) device is replaced, so an abandoned enrollment
        does not block a retry. A *confirmed* device raises
        :class:`MfaAlreadyEnrolledError` — silently replacing it would let anyone
        with a live session swap the owner's authenticator.

        Under ``MFA_STAFF_ENFORCEMENT=required`` a valid enrollment grant is
        mandatory (:class:`MfaEnrollmentRequiresGrantError`); under ``optional``
        the already-authenticated session is sufficient. A locked device is
        never re-seeded: issuing a new secret would otherwise reset the
        brute-force counter and hand the attacker a fresh lockout budget
        (security review F2).
        """
        self._require_staff(user)
        self._require_active(user)
        if enforcement_mode() == _MODE_REQUIRED and not self.has_valid_enrollment_grant(
            user
        ):
            raise MfaEnrollmentRequiresGrantError(
                "A second factor is required. Ask an administrator for an "
                "enrollment grant."
            )
        secret = pyotp.random_base32(length=32)  # 160 bit
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.username,
            issuer_name=str(getattr(settings, "MFA_TOTP_ISSUER", "ReqogniLoom")),
        )
        with transaction.atomic():
            # F5: the device row does not exist yet on a first enrollment, so
            # the user row is the only lock that can serialise two concurrent
            # ``begin_enrollment`` calls (same shape as ``grant_enrollment``).
            self._lock_user(user)
            device = (
                UserTotpDevice.objects.select_for_update().filter(user=user).first()
            )
            if device is not None and device.confirmed_at is not None:
                raise MfaAlreadyEnrolledError(
                    "This account already has a confirmed second factor."
                )
            if device is not None:
                # Refuse to re-seed a locked device: the update below resets the
                # counter, which would be a lockout bypass (F2). An expired lock
                # is cleared here, so a legitimate retry still works.
                self._assert_not_locked(device)
            if device is None:
                try:
                    UserTotpDevice.objects.create(
                        user=user, secret_ciphertext=encrypt_secret(secret)
                    )
                except IntegrityError as exc:  # backstop: OneToOne race
                    raise MfaAlreadyEnrolledError(
                        "This account already has a second factor."
                    ) from exc
            else:
                UserTotpDevice.objects.filter(pk=device.pk).update(
                    secret_ciphertext=encrypt_secret(secret),
                    last_used_step=None,
                    failed_attempts=0,
                    locked_until=None,
                    version=F("version") + 1,
                )
        logger.info(
            "mfa enrollment started user_id=%s username=%s", user.id, user.username
        )
        return EnrollmentData(secret_b32=secret, otpauth_uri=uri)

    def confirm_enrollment(
        self,
        user: User,
        code: str,
        *,
        source: Literal["session", "challenge"] = "session",
    ) -> list[str]:
        """Confirm the pending device with a first code; return recovery codes.

        The returned recovery codes are the only time the plaintext exists — they
        are not recoverable afterwards.

        ``source`` names the entry point that confirmed the device
        (``"session"`` or ``"challenge"``) and is written to the ``user.mfa_enroll``
        audit row. WP E3.6 needs it: enrollment is reachable both from an
        already-authenticated session and from the login challenge flow, and an
        auditor must be able to tell which one created the credential.

        Under ``MFA_STAFF_ENFORCEMENT=required`` the confirmation *consumes* the
        enrollment grant (ENT-E7 = A) and fails with
        :class:`MfaEnrollmentRequiresGrantError` when none can be consumed —
        the check happens after the code proved correct but before anything is
        written, so a wrong code never burns a grant the real owner still needs.
        """
        self._require_staff(user)
        self._require_active(user)
        requires_grant = enforcement_mode() == _MODE_REQUIRED
        now = timezone.now()
        codes: list[str] = []
        error: MfaError | None = None
        with transaction.atomic():
            device = (
                UserTotpDevice.objects.select_for_update()
                .filter(user=user)
                .first()
            )
            if device is None:
                error = MfaNotEnrolledError("No pending enrollment for this user.")
            elif device.confirmed_at is not None:
                error = MfaAlreadyEnrolledError(
                    "This account already has a confirmed second factor."
                )
            else:
                try:
                    self._assert_not_locked(device)
                except MfaLockedError as exc:
                    error = exc
                if error is None:
                    secret = self._decrypt_totp_secret(device)
                    matched_step = self._match_step(secret, code)
                    if matched_step is None:
                        # Returned, not raised: leaving the block normally commits
                        # the failure counter (same reason as in ``verify``).
                        self._register_failure(device)
                        error = MfaInvalidCodeError(
                            "The confirmation code is invalid."
                        )
                    elif requires_grant and not self._consume_grant(user, now):
                        # Nothing written yet, so returning (and committing the
                        # no-op) is enough — the device stays pending.
                        error = MfaEnrollmentRequiresGrantError(
                            "A second factor is required. Ask an administrator "
                            "for an enrollment grant."
                        )
                    else:
                        UserTotpDevice.objects.filter(pk=device.pk).update(
                            confirmed_at=now,
                            last_used_step=matched_step,
                            failed_attempts=0,
                            locked_until=None,
                            version=F("version") + 1,
                        )
                        if not requires_grant:
                            self._consume_grant(user, now)
                        codes = self._replace_recovery_codes(user)
                        self._audit(
                            user,
                            AuditEntry.OP_USER_MFA_ENROLL,
                            change_reason="TOTP device confirmed",
                            details={
                                "recovery_codes_issued": len(codes),
                                "source": source,
                            },
                        )
        if error is not None:
            logger.warning(
                "mfa enrollment rejected user_id=%s reason=%s",
                user.id,
                type(error).__name__,
            )
            raise error
        logger.info("mfa enrolled user_id=%s username=%s", user.id, user.username)
        return codes

    # -- verification -----------------------------------------------------

    def verify(
        self,
        user: User,
        *,
        code: str | None = None,
        recovery_code: str | None = None,
    ) -> Literal["totp", "recovery"]:
        """Accept exactly one second factor; return which kind was used.

        Bookkeeping (failure counter, ``last_used_step``, ``used_at``) is
        committed *before* the error is raised: the caller's exception must not
        roll back the brute-force counter, or five wrong guesses per request
        would leave no trace.
        """
        if (code is None) == (recovery_code is None):
            raise ValueError("Pass exactly one of 'code' or 'recovery_code'.")
        # F8: a JSON ``int``/``null`` must degrade to "invalid code", not to an
        # ``AttributeError`` surfacing as a 500.
        if code is not None and not isinstance(code, str):
            code = ""
        if recovery_code is not None and not isinstance(recovery_code, str):
            recovery_code = ""
        self._require_active(user)

        now = timezone.now()
        outcome: Literal["totp", "recovery"] | None = None
        error: MfaError | None = None
        with transaction.atomic():
            device = UserTotpDevice.objects.select_for_update().filter(user=user).first()
            if device is None or device.confirmed_at is None:
                error = MfaNotEnrolledError(
                    "This account has no confirmed second factor."
                )
            else:
                try:
                    self._assert_not_locked(device)
                except MfaLockedError as exc:
                    error = exc
                if error is None:
                    if code is not None:
                        outcome, error = self._verify_totp(device, code)
                    else:
                        outcome, error = self._verify_recovery_code(
                            user, device, recovery_code or "", now
                        )
            # The rejection is returned, never raised inside the block: leaving
            # it normally commits the failure counter written above, whereas
            # raising would roll it back — exactly what an attacker wants.
        if error is not None:
            logger.warning(
                "mfa rejection user_id=%s kind=%s reason=%s",
                user.id,
                "totp" if code is not None else "recovery",
                type(error).__name__,
            )
            raise error
        if outcome is None:  # pragma: no cover - both branches set one or the other
            raise MfaUnavailableError("The second factor could not be evaluated.")
        logger.info("mfa success user_id=%s kind=%s", user.id, outcome)
        return outcome

    def _verify_totp(
        self, device: UserTotpDevice, code: str
    ) -> tuple[Literal["totp"] | None, MfaError | None]:
        secret = self._decrypt_totp_secret(device)
        matched_step = self._match_step(secret, code)
        if matched_step is None:
            self._register_failure(device)
            return None, MfaInvalidCodeError("The code is invalid.")
        if device.last_used_step is not None and matched_step <= device.last_used_step:
            # Replay of an already-spent code (security review F4). Deliberately
            # NOT counted as a failure: a replay can never grant access, so there
            # is nothing to throttle — while counting it would let a double-click
            # or an automatic client retry lock a legitimate user out after five
            # attempts. Logged instead, so the event stays observable.
            logger.warning(
                "mfa replay rejected user_id=%s step=%s last_used_step=%s",
                device.user_id,
                matched_step,
                device.last_used_step,
            )
            return None, MfaInvalidCodeError("The code has already been used.")
        UserTotpDevice.objects.filter(pk=device.pk).update(
            last_used_step=matched_step,
            failed_attempts=0,
            locked_until=None,
            version=F("version") + 1,
        )
        return "totp", None

    def _verify_recovery_code(
        self, user: User, device: UserTotpDevice, recovery_code: str, now: datetime
    ) -> tuple[Literal["recovery"] | None, MfaError | None]:
        normalized = normalize_recovery_code(recovery_code)
        if not normalized:
            self._register_failure(device)
            return None, MfaInvalidCodeError("The recovery code is invalid.")
        # User-bound lookup (rule 4): a global lookup by hash would let one
        # user's code authenticate another user.
        row = (
            UserRecoveryCode.objects.select_for_update()
            .filter(user=user, code_hash=_hash_recovery_code(normalized))
            .first()
        )
        if row is None or row.used_at is not None:
            self._register_failure(device)
            return None, MfaInvalidCodeError("The recovery code is invalid.")
        UserRecoveryCode.objects.filter(pk=row.pk).update(
            used_at=now, version=F("version") + 1
        )
        UserTotpDevice.objects.filter(pk=device.pk).update(
            failed_attempts=0, locked_until=None, version=F("version") + 1
        )
        self._audit(
            user,
            AuditEntry.OP_USER_MFA_RECOVERY_USED,
            change_reason="Recovery code consumed",
        )
        return "recovery", None

    def regenerate_recovery_codes(self, user: User, code: str) -> list[str]:
        """Replace every recovery code after proving a current TOTP code.

        Verification *and* replacement run in ONE transaction under the device
        row lock (security review F10). Two concurrent regenerations used to
        interleave between ``verify`` (its own transaction) and the replace, so
        the response of one caller could list codes the other had already
        deleted — the user would save ten codes of which none worked.
        """
        self._require_active(user)
        now = timezone.now()
        codes: list[str] = []
        error: MfaError | None = None
        with transaction.atomic():
            device = (
                UserTotpDevice.objects.select_for_update().filter(user=user).first()
            )
            if device is None or device.confirmed_at is None:
                error = MfaNotEnrolledError(
                    "This account has no confirmed second factor."
                )
            else:
                try:
                    self._assert_not_locked(device)
                except MfaLockedError as exc:
                    error = exc
                if error is None:
                    _outcome, error = self._verify_totp(device, code)
            if error is None:
                codes = self._replace_recovery_codes(user)
                self._audit(
                    user,
                    AuditEntry.OP_USER_MFA_RECOVERY_REGENERATE,
                    change_reason="Recovery codes regenerated",
                    details={"recovery_codes_issued": len(codes)},
                )
        if error is not None:
            logger.warning(
                "mfa recovery regeneration rejected user_id=%s reason=%s",
                user.id,
                type(error).__name__,
            )
            raise error
        logger.info("mfa recovery codes regenerated user_id=%s", user.id)
        return codes

    # -- lifecycle --------------------------------------------------------

    def disable(self, user: User, *, password: str, code: str) -> None:
        """Remove the device and all recovery codes (password + code required)."""
        if self._second_factor_is_mandatory(user):
            raise MfaRequiredError(
                "Removing the second factor is forbidden while "
                "MFA_STAFF_ENFORCEMENT=required."
            )
        # Password first: a wrong password must not burn a TOTP step.
        if not password or not user.check_password(password):
            raise MfaInvalidCredentialsError("The password is invalid.")
        self.verify(user, code=code)
        with transaction.atomic():
            UserRecoveryCode.objects.filter(user=user).delete()
            UserTotpDevice.objects.filter(user=user).delete()
            self._audit(
                user, AuditEntry.OP_USER_MFA_DISABLE, change_reason="Second factor disabled"
            )
        logger.warning("mfa disabled user_id=%s username=%s", user.id, user.username)

    def reset(self, user: User, *, actor: str) -> None:
        """Break-glass removal of the second factor (``manage.py mfa_reset``).

        **Operator/system surface only — deliberately never reachable from REST
        or MCP.** It takes no TOTP code and no password (the whole point is a
        lost device), so exposing it over an API would let any caller strip a
        victim's second factor. The only entry point is the management command
        (WP E3.7), which runs with operator privileges.

        ``actor`` is a free-form audit label, not a resolvable identity: the
        caller's command layer is responsible for filling it (e.g.
        ``"cli:${USER}"``) so the audit row answers "who ran the reset". It is
        stored truncated to the 150-char column and never interpreted here.

        Deletes device *and* recovery codes and audits the act. Issuing an
        enrollment grant is the caller's job (WP E3.7), so the two governed acts
        — "remove the credential" and "permit a new enrollment" — stay separately
        auditable.
        """
        actor = (actor or "").strip() or "unknown"
        with transaction.atomic():
            UserRecoveryCode.objects.filter(user=user).delete()
            UserTotpDevice.objects.filter(user=user).delete()
            self._audit(
                user,
                AuditEntry.OP_USER_MFA_RESET,
                change_reason="Second factor reset by administrator",
                details={"actor": actor[:150]},
            )
        logger.warning("mfa reset user_id=%s by=%s", user.id, actor)

    # -- enrollment grants (ENT-E7 = A) -----------------------------------

    def grant_enrollment(
        self, user: User, *, actor: str, reason: str
    ) -> UserMfaEnrollmentGrant:
        """Issue a single-use enrollment grant valid for at most 24 h.

        **Operator/system surface only — deliberately never reachable from REST
        or MCP.** Minting this grant is what authorises enrollment under
        ``MFA_STAFF_ENFORCEMENT=required``, so an API caller who could mint one
        could bootstrap their own authenticator from a stolen password — exactly
        the hole ENT-E7 = A closes (QR-S01). Only the break-glass command
        (``manage.py mfa_reset``, WP E3.7) calls it.

        ``actor`` is a free-form audit label, not a resolvable identity: the
        calling command layer must set it (e.g. ``"cli:${USER}"``) so the audit
        row is attributable. ``reason`` is mandatory and operator-written; both
        are stored as-is (``actor`` truncated to 150 chars).

        Marks every older unused grant ``used_at`` first, so "at most one valid
        grant per user" holds both in the service and in the database (partial
        unique constraint ``uq_mfa_grant_user_unused``).
        """
        ttl = enroll_grant_ttl_seconds()
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("An enrollment grant requires a written reason.")
        actor = (actor or "").strip() or "unknown"
        now = timezone.now()
        with transaction.atomic():
            # F5: ``filter(used_at__isnull=True).update(...)`` locks nothing when
            # no unused grant exists, so two concurrent calls would both reach
            # the INSERT. Locking the (always present) user row serialises them;
            # the partial unique constraint stays as the fail-closed backstop.
            self._lock_user(user)
            UserMfaEnrollmentGrant.objects.select_for_update().filter(
                user=user, used_at__isnull=True
            ).update(used_at=now, version=F("version") + 1)
            try:
                grant = UserMfaEnrollmentGrant.objects.create(
                    user=user,
                    expires_at=now + timedelta(seconds=ttl),
                    granted_by=actor[:150],
                    reason=reason,
                )
            except IntegrityError as exc:  # uq_mfa_grant_user_unused
                raise MfaEnrollmentGrantConflictError(
                    "An enrollment grant was issued concurrently for this user; "
                    "retry and use the existing grant."
                ) from exc
            self._audit(
                user,
                AuditEntry.OP_USER_MFA_ENROLL_GRANT,
                change_reason=reason,
                details={
                    "actor": actor[:150],
                    "grant_id": str(grant.id),
                    "expires_at": grant.expires_at.isoformat(),
                    "ttl_seconds": ttl,
                },
            )
        logger.info(
            "mfa enrollment grant issued user_id=%s by=%s ttl=%ss",
            user.id,
            actor,
            ttl,
        )
        return grant

    def has_valid_enrollment_grant(self, user: User) -> bool:
        """True iff an unused, unexpired grant exists (``used_at`` NULL, future)."""
        return UserMfaEnrollmentGrant.objects.filter(
            user=user, used_at__isnull=True, expires_at__gt=timezone.now()
        ).exists()

    def _consume_grant(self, user: User, now: datetime) -> bool:
        """Mark the user's current valid grant used; report whether one was found.

        The boolean is what lets ``confirm_enrollment`` enforce ENT-E7 = A
        without a time-of-check/time-of-use gap: the caller asks "consume it",
        and a ``False`` means there was nothing to consume *at consume time*
        (F2).
        """
        grant = (
            UserMfaEnrollmentGrant.objects.select_for_update()
            .filter(user=user, used_at__isnull=True, expires_at__gt=now)
            .order_by("-created_at")
            .first()
        )
        if grant is None:
            return False
        UserMfaEnrollmentGrant.objects.filter(pk=grant.pk).update(
            used_at=now, version=F("version") + 1
        )
        return True

    # -- signed challenge -------------------------------------------------

    def issue_challenge(
        self, user: User, *, purpose: Literal["verify", "enroll"]
    ) -> str:
        """Return a signed, expiring challenge for the second login step.

        The payload binds the challenge to the credential epoch (security review
        F5): ``pwd`` is a digest of the current password hash, so a forced
        password change invalidates every challenge issued before it. Without
        that binding a stolen challenge would survive the very remediation it is
        supposed to trigger.
        """
        if purpose not in ("verify", "enroll"):
            raise ValueError("purpose must be 'verify' or 'enroll'.")
        payload = {
            "uid": str(user.id),
            "purpose": purpose,
            "n": secrets.token_urlsafe(16),
            "pwd": _credential_digest(user),
        }
        return TimestampSigner(salt=CHALLENGE_SALT).sign_object(payload)

    def challenge_subject(self, token: str) -> str | None:
        """Return the challenge's user id (``uid``) *without* loading the user.

        Used by the login-MFA throttle (security review F1) to key the
        second-step brute-force budget on the account instead of the (shared)
        client IP: the ``uid`` is inside the signed payload, so a caller cannot
        choose their bucket, and an unsigned/expired/garbage token simply
        returns ``None`` (the per-IP throttle still applies).

        No database access and no error: the throttle must never raise.
        """
        try:
            payload = self._unsign(token)
        except MfaError:
            return None
        return str(payload["uid"])

    def read_challenge(self, token: str) -> tuple[User, str]:
        """Verify signature and age; return ``(user, purpose)``."""
        payload = self._unsign(token)
        user = self._load_challenge_user(payload)
        return user, str(payload["purpose"])

    def consume_challenge(self, token: str) -> tuple[User, str]:
        """Read the challenge and burn its nonce (single use, rule 4a).

        Call this only *after* the second factor succeeded — an attacker who
        cannot pass the factor must not be able to burn a victim's challenge.
        """
        user, purpose = self.read_challenge(token)
        payload = self._unsign(token)
        nonce = str(payload["n"])
        ttl = challenge_ttl_seconds()
        try:
            first_use = cache.add(
                f"{_CHALLENGE_CACHE_PREFIX}{nonce}", 1, timeout=ttl
            )
        except Exception as exc:  # noqa: BLE001 - any cache failure is fail-closed
            raise MfaUnavailableError(
                "The challenge store is unavailable; refusing to continue."
            ) from exc
        if not first_use:
            raise MfaChallengeInvalidError("This challenge has already been used.")
        return user, purpose

    def _unsign(self, token: str) -> dict[str, Any]:
        ttl = challenge_ttl_seconds()
        signer = TimestampSigner(salt=CHALLENGE_SALT)
        try:
            payload = signer.unsign_object(token, max_age=ttl)
        except SignatureExpired as exc:
            raise MfaChallengeInvalidError("The challenge has expired.") from exc
        except (BadSignature, ValueError, TypeError) as exc:
            raise MfaChallengeInvalidError("The challenge is invalid.") from exc
        if not isinstance(payload, dict):
            raise MfaChallengeInvalidError("The challenge is invalid.")
        for key in ("uid", "purpose", "n", "pwd"):
            if not isinstance(payload.get(key), str):
                raise MfaChallengeInvalidError("The challenge is invalid.")
        if payload["purpose"] not in ("verify", "enroll"):
            raise MfaChallengeInvalidError("The challenge is invalid.")
        return payload

    @staticmethod
    def _load_challenge_user(payload: dict[str, Any]) -> User:
        try:
            user = User.objects.get(id=payload["uid"])
        except (User.DoesNotExist, ValueError, TypeError) as exc:
            raise MfaChallengeInvalidError("The challenge is invalid.") from exc
        if not user.is_active:
            raise MfaChallengeInvalidError("The challenge is invalid.")
        # F5: the challenge belongs to the credential that authenticated step 1.
        # A password change since issuance invalidates it (constant-time compare
        # for consistency with the other credential comparisons in this module).
        if not hmac.compare_digest(str(payload["pwd"]), _credential_digest(user)):
            raise MfaChallengeInvalidError("The challenge is invalid.")
        return user

    # -- internals --------------------------------------------------------

    @staticmethod
    def _lock_user(user: User) -> None:
        """Serialise the "create if absent" paths per user (F5, #1308).

        ``select_for_update()`` on the *rows being replaced* is useless when
        there is no such row yet: an empty ``filter(...).update(...)`` locks
        nothing, so two concurrent first-time callers both proceed to the
        ``INSERT`` and the loser dies on the unique constraint with a 500. The
        user row always exists, so locking it gives every
        read-then-insert path a real serialisation point.

        Lock order, stated precisely (security review F11 — the earlier
        "user -> child everywhere" claim was wrong):

        * only the two *read-then-INSERT* paths take this lock —
          :meth:`begin_enrollment` (``user -> device``) and
          :meth:`grant_enrollment` (``user -> grant``);
        * the *update* paths lock only the row they mutate —
          :meth:`verify` / :meth:`regenerate_recovery_codes` (device),
          ``confirm_enrollment`` (device, then grant via ``_consume_grant``).

        That is deadlock-free because a path holding a child lock never asks for
        the user lock, and no path takes the two child locks in the opposite
        order.
        """
        User.objects.select_for_update().get(pk=user.pk)

    def _decrypt_totp_secret(self, device: UserTotpDevice) -> str:
        """Strictly decrypt the stored secret (rule 1).

        ``persistence.encryption.decrypt_secret`` returns a value *unchanged* when
        it lacks the Fernet prefix (its legacy/plaintext compatibility rule). For
        a TOTP secret that is exactly the wrong behaviour: a plaintext column
        would silently be accepted as the secret. Here a missing prefix is
        treated as corrupt state, not as legacy data.
        """
        ciphertext = device.secret_ciphertext or ""
        if not ciphertext.startswith(ENCRYPTED_PREFIX):
            raise MfaUnavailableError(
                "The stored second-factor secret is not encrypted; refusing "
                "to verify."
            )
        try:
            secret = decrypt_secret(ciphertext)
        except (InvalidToken, ValueError, TypeError) as exc:
            raise MfaUnavailableError(
                "The stored second-factor secret cannot be decrypted."
            ) from exc
        if not secret:
            raise MfaUnavailableError("The stored second-factor secret is empty.")
        return secret

    def _match_step(self, secret: str, code: str) -> int | None:
        """Return the matching TOTP time step, or ``None`` (rule 4).

        Every step in the window is evaluated — no early exit — and the
        comparison is constant-time.
        """
        # F8: a non-string code degrades to "invalid", never to AttributeError.
        raw = code if isinstance(code, str) else ""
        candidate = raw.strip().replace(" ", "")
        if len(candidate) != TOTP_DIGITS or not candidate.isdigit():
            return None
        window = totp_valid_window()
        now_step = _current_step()
        # F7: parameters are passed explicitly rather than inherited from
        # pyotp's defaults, so the verifier and the provisioning URI can never
        # drift apart on a library default change.
        totp = pyotp.TOTP(
            secret, digits=TOTP_DIGITS, interval=TOTP_PERIOD_SECONDS
        )
        matched: int | None = None
        for step in range(now_step - window, now_step + window + 1):
            if step < 0:
                continue
            if hmac.compare_digest(totp.generate_otp(step), candidate) and (
                matched is None
            ):
                matched = step
        return matched

    def _assert_not_locked(self, device: UserTotpDevice) -> None:
        """Raise while the device is locked; clear an *expired* lock on the way out.

        Security review F3: returning on an expired lock while leaving
        ``failed_attempts`` at the threshold meant the very next wrong code
        re-locked the device for the full window — with any clock drift between
        writer and reader, a permanently locked account. Expiry is therefore
        persisted as a full reset, both in the row and on the in-memory instance
        the caller keeps using.
        """
        locked_until = device.locked_until
        if locked_until is None:
            return
        now = timezone.now()
        if locked_until > now:
            raise MfaLockedError(int((locked_until - now).total_seconds()))
        UserTotpDevice.objects.filter(pk=device.pk).update(
            failed_attempts=0, locked_until=None, version=F("version") + 1
        )
        device.failed_attempts = 0
        device.locked_until = None

    def _register_failure(self, device: UserTotpDevice) -> None:
        """Count one rejected attempt, locking the device at the threshold."""
        max_attempts = max(_int_setting("MFA_MAX_FAILED_ATTEMPTS", 5), 1)
        lockout = max(_int_setting("MFA_LOCKOUT_SECONDS", 900), 1)
        attempts = device.failed_attempts + 1
        fields: dict[str, Any] = {
            "failed_attempts": attempts,
            "version": F("version") + 1,
        }
        if attempts >= max_attempts:
            fields["locked_until"] = timezone.now() + timedelta(seconds=lockout)
        UserTotpDevice.objects.filter(pk=device.pk).update(**fields)

    def _replace_recovery_codes(self, user: User) -> list[str]:
        """Delete the user's recovery codes and mint a fresh set (rule 5)."""
        UserRecoveryCode.objects.filter(user=user).delete()
        plaintext = _generate_recovery_codes()
        UserRecoveryCode.objects.bulk_create(
            [
                UserRecoveryCode(user=user, code_hash=_hash_recovery_code(code))
                for code in plaintext
            ]
        )
        return plaintext

    def _audit(
        self,
        user: User,
        operation: str,
        *,
        change_reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write one AuditEntry in the caller's transaction (rule 6).

        A user without a tenant gets no row: ``AuditEntry`` is
        ``TenantScopedModel`` and its writer refuses to write without a tenant
        (REQ-L2-AL-006). The ``reqogniloom.security`` log line is emitted by the
        caller in every case, so the act is never completely invisible.
        """
        if user.tenant_id is None:
            return
        previous = TenantContext.get_tenant() if TenantContext.is_set() else None
        try:
            # Inside the try on purpose: arming the tenant context is part of the
            # write, so a failure here (e.g. an unparsable tenant id) must be
            # reported as unavailability like any other audit failure rather than
            # escaping as a bare ValueError. ``finally`` still restores whatever
            # was armed before, including when the arming itself threw.
            TenantContext.set_tenant(user.tenant_id)
            log_write(
                actor=str(user.id),
                actor_type=AuditEntry.ACTOR_TYPE_USER,
                operation=operation,
                entity_type="User",
                entity_id=user.id,
                change_reason=change_reason,
                details=details,
                ctx={"source": "rest"},
            )
        except MfaUnavailableError:
            raise
        except Exception as exc:
            # Security review F5: an audit outage must surface as 503-style
            # unavailability, not as a bare RuntimeError/500 — and it must stay
            # fail-closed, so the mutation in the caller's transaction rolls back.
            raise MfaUnavailableError("audit unavailable") from exc
        finally:
            if previous is None:
                TenantContext.clear_tenant()
            else:
                TenantContext.set_tenant(previous)


__all__ = [
    "CHALLENGE_SALT",
    "EnrollmentData",
    "MfaAlreadyEnrolledError",
    "MfaChallengeInvalidError",
    "MfaEnrollmentGrantConflictError",
    "MfaEnrollmentRequiresGrantError",
    "MfaError",
    "MfaInvalidCodeError",
    "MfaInvalidCredentialsError",
    "MfaLockedError",
    "MfaNotAllowedError",
    "MfaNotEnrolledError",
    "MfaRequiredError",
    "MfaService",
    "MfaUnavailableError",
    "RECOVERY_CODE_COUNT",
    "challenge_ttl_seconds",
    "enforcement_mode",
    "enroll_grant_ttl_seconds",
    "normalize_recovery_code",
]
