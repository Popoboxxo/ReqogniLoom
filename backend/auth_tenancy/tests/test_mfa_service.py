"""``MfaService`` behaviour and security rules (#1308, Plan E / WP E3.2).

The six binding security rules of the plan each have a dedicated section here,
because each one is a property that a future refactor could silently drop:

1. Fernet-only secret, strict decrypt (``TestStrictDecrypt``)
2. replay via ``last_used_step`` (``TestVerifyTotp``, ``TestParallelDoubleVerify``)
3. brute-force lockout (``TestVerifyTotp::test_locks_after_max_attempts``)
4. ``hmac.compare_digest`` + user-bound recovery lookup (``TestVerifyRecovery``)
4a. single-use challenge (``TestChallenge``)
5. single-use recovery codes, regeneration invalidates (``TestRegenerateRecoveryCodes``)
6. audit + ``reqogniloom.security`` logger (asserted throughout)

TOTP codes are real: they are produced by ``pyotp`` from the very secret the
service minted, so a change to the digest/period/window parameters fails here
instead of in production. The current time step is pinned via
``auth_tenancy.services.mfa._current_step`` so no test can race the 30-second
boundary.
"""
from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from unittest import mock

import pyotp
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.utils import timezone

from audit.models import AuditEntry
from auth_tenancy.models import (
    UserMfaEnrollmentGrant,
    UserRecoveryCode,
    UserTotpDevice,
)
from auth_tenancy.services import mfa as mfa_module
from auth_tenancy.services.mfa import (
    MfaAlreadyEnrolledError,
    MfaChallengeInvalidError,
    MfaEnrollmentGrantConflictError,
    MfaEnrollmentRequiresGrantError,
    MfaError,
    MfaInvalidCodeError,
    MfaInvalidCredentialsError,
    MfaLockedError,
    MfaNotAllowedError,
    MfaNotEnrolledError,
    MfaRequiredError,
    MfaService,
    MfaUnavailableError,
    normalize_recovery_code,
)
from persistence.models import User

#: Fixed, whole-second origin so ``.at()`` and ``generate_otp`` agree exactly.
BASE_TS = 1_700_000_000
STEP_SECONDS = 30
BASE_STEP = BASE_TS // STEP_SECONDS

_STAFF_PASSWORD = "s3cret-staff-pw"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def frozen_step(monkeypatch: pytest.MonkeyPatch) -> int:
    """Pin the TOTP time step for every test in this module."""
    monkeypatch.setattr(mfa_module, "_current_step", lambda: BASE_STEP)
    return BASE_STEP


def _code(secret: str, *, offset: int = 0) -> str:
    """Return the code for ``BASE_STEP + offset`` (real pyotp computation)."""
    return pyotp.TOTP(secret).generate_otp(BASE_STEP + offset)


def _code_at(secret: str, moment: datetime) -> str:
    """Return the code an authenticator app would show at ``moment``."""
    return pyotp.TOTP(secret).at(moment)


def _staff_user(tenant, username: str = "mfa-staff", **extra) -> User:
    user = User.objects.create(
        username=username,
        email=f"{username}@mfa.test",
        tenant=tenant,
        is_staff=True,
        **extra,
    )
    user.set_password(_STAFF_PASSWORD)
    user.save(update_fields=["password"])
    return user


def _enroll(service: MfaService, user: User) -> tuple[str, list[str]]:
    """Run the real two-step enrollment and return ``(secret, recovery_codes)``."""
    data = service.begin_enrollment(user)
    codes = service.confirm_enrollment(user, _code(data.secret_b32))
    return data.secret_b32, codes


def _audited(user: User, operation: str) -> bool:
    """Return whether an audit row with ``operation`` exists for ``user``."""
    return AuditEntry.unscoped.filter(
        entity_id=user.id, entity_type="User", op=operation
    ).exists()


# ---------------------------------------------------------------------------
# mfa_required
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMfaRequired:
    """The three-value enforcement dial."""

    def test_off_never_requires_a_second_factor(self, tenant_a, settings) -> None:
        settings.MFA_STAFF_ENFORCEMENT = "off"
        user = _staff_user(tenant_a)
        service = MfaService()
        _enroll(service, user)

        assert service.mfa_required(user) is False

    def test_optional_requires_it_only_once_enrolled(self, tenant_a) -> None:
        user = _staff_user(tenant_a)
        service = MfaService()
        assert service.mfa_required(user) is False

        _enroll(service, user)

        assert service.mfa_required(user) is True

    def test_required_covers_staff_without_a_device(self, tenant_a, settings) -> None:
        """``required`` is about the account class, not about enrollment state."""
        settings.MFA_STAFF_ENFORCEMENT = "required"
        staff = _staff_user(tenant_a, "staff-required")
        plain = User.objects.create(
            username="plain-required", email="pr@mfa.test", tenant=tenant_a
        )
        service = MfaService()

        assert service.mfa_required(staff) is True
        assert service.mfa_required(plain) is False

    def test_unknown_mode_is_a_configuration_error(self, tenant_a, settings) -> None:
        settings.MFA_STAFF_ENFORCEMENT = "sometimes"
        user = _staff_user(tenant_a)

        with pytest.raises(ImproperlyConfigured):
            MfaService().mfa_required(user)


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBeginEnrollment:
    """Secret issuance (no QR in v1, ENT-E5 = A)."""

    def test_returns_a_160_bit_secret_and_a_provisioning_uri(
        self, tenant_a, settings
    ) -> None:
        settings.MFA_STAFF_ENFORCEMENT = "optional"
        user = _staff_user(tenant_a, "enroll-uri")
        data = MfaService().begin_enrollment(user)

        assert len(data.secret_b32) == 32
        assert data.digits == 6
        assert data.period == 30
        assert data.otpauth_uri.startswith("otpauth://totp/")
        assert "issuer=ReqogniLoom" in data.otpauth_uri
        assert "enroll-uri" in data.otpauth_uri

    def test_secret_is_persisted_only_as_ciphertext(self, tenant_a) -> None:
        """Rule 1: the plaintext secret never reaches the database."""
        user = _staff_user(tenant_a, "enroll-cipher")
        data = MfaService().begin_enrollment(user)

        device = UserTotpDevice.objects.get(user=user)
        assert device.secret_ciphertext != data.secret_b32
        assert device.secret_ciphertext.startswith("gAAAA")
        assert device.confirmed_at is None

    def test_repr_never_contains_the_secret(self, tenant_a) -> None:
        """F1: the default dataclass repr would leak the live secret into logs."""
        user = _staff_user(tenant_a, "enroll-repr")
        data = MfaService().begin_enrollment(user)

        rendered = repr(data)
        assert "secret" not in rendered
        assert data.secret_b32 not in rendered
        assert data.otpauth_uri not in rendered
        # The shape is still visible for debugging.
        assert "digits=6" in rendered and "period=30" in rendered

    def test_non_staff_may_not_enroll(self, tenant_a) -> None:
        plain = User.objects.create(
            username="enroll-plain", email="ep@mfa.test", tenant=tenant_a
        )

        with pytest.raises(MfaNotAllowedError):
            MfaService().begin_enrollment(plain)

    def test_a_pending_device_is_replaced(self, tenant_a) -> None:
        """An abandoned enrollment must not block a retry."""
        user = _staff_user(tenant_a, "enroll-retry")
        service = MfaService()
        first = service.begin_enrollment(user)
        second = service.begin_enrollment(user)

        assert first.secret_b32 != second.secret_b32
        assert UserTotpDevice.objects.filter(user=user).count() == 1

    def test_begin_enrollment_refuses_a_locked_device(self, tenant_a) -> None:
        """F2 (lockout half): a locked device must not be re-seeded.

        Re-issuing the secret resets ``failed_attempts``/``locked_until``, which
        would hand an attacker who is mid-guess a fresh lockout budget. The
        existing ciphertext must also survive untouched, i.e. the refusal happens
        before any write.

        A *pending* device is used on purpose: on a confirmed one the
        ``MfaAlreadyEnrolledError`` guard fires first, so it could never reach
        the lock check.
        """
        user = _staff_user(tenant_a, "enroll-locked")
        service = MfaService()
        first = service.begin_enrollment(user)
        UserTotpDevice.objects.filter(user=user).update(
            failed_attempts=5, locked_until=timezone.now() + timedelta(seconds=600)
        )
        before = UserTotpDevice.objects.get(user=user).secret_ciphertext

        with pytest.raises(MfaLockedError):
            service.begin_enrollment(user)

        device = UserTotpDevice.objects.get(user=user)
        assert device.secret_ciphertext == before
        assert device.secret_ciphertext != first.secret_b32
        assert device.failed_attempts == 5
        assert device.locked_until is not None

    def test_begin_enrollment_clears_an_expired_lock(self, tenant_a) -> None:
        """F2 (lockout half): an expired lock is a fresh start, not a bypass.

        ``_assert_not_locked`` clears the expired state first, so the re-seed is
        allowed and the counters land at 0/None instead of carrying the old
        threshold forward.
        """
        user = _staff_user(tenant_a, "enroll-expired-lock")
        service = MfaService()
        first = service.begin_enrollment(user)
        UserTotpDevice.objects.filter(user=user).update(
            failed_attempts=5, locked_until=timezone.now() - timedelta(seconds=1)
        )
        before = UserTotpDevice.objects.get(user=user).secret_ciphertext

        second = service.begin_enrollment(user)

        device = UserTotpDevice.objects.get(user=user)
        assert second.secret_b32 != first.secret_b32
        assert device.secret_ciphertext != before
        assert device.secret_ciphertext.startswith("gAAAA")
        assert device.failed_attempts == 0
        assert device.locked_until is None

    def test_a_confirmed_device_blocks_re_enrollment(self, tenant_a) -> None:
        """Silently swapping a live authenticator would be an account takeover."""
        user = _staff_user(tenant_a, "enroll-twice")
        service = MfaService()
        _enroll(service, user)

        with pytest.raises(MfaAlreadyEnrolledError):
            service.begin_enrollment(user)


@pytest.mark.django_db
class TestConfirmEnrollment:
    """Confirmation + recovery-code minting."""

    def test_confirm_returns_ten_formatted_recovery_codes(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "confirm-codes")
        service = MfaService()
        data = service.begin_enrollment(user)

        codes = service.confirm_enrollment(user, _code(data.secret_b32))

        assert len(codes) == 10
        assert len(set(codes)) == 10
        for code in codes:
            groups = code.split("-")
            assert len(groups) == 4
            assert all(len(group) == 4 for group in groups)
            assert code.upper() == code

        device = UserTotpDevice.objects.get(user=user)
        assert device.confirmed_at is not None
        assert device.last_used_step == BASE_STEP
        assert UserRecoveryCode.objects.filter(user=user).count() == 10

    def test_recovery_codes_are_stored_only_as_hashes(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "confirm-hash")
        service = MfaService()
        data = service.begin_enrollment(user)
        codes = service.confirm_enrollment(user, _code(data.secret_b32))

        stored = set(
            UserRecoveryCode.objects.filter(user=user).values_list(
                "code_hash", flat=True
            )
        )
        assert not (set(codes) & stored)
        assert all(len(value) <= 80 for value in stored)

    def test_confirm_with_a_wrong_code_leaves_the_device_pending(
        self, tenant_a
    ) -> None:
        user = _staff_user(tenant_a, "confirm-wrong")
        service = MfaService()
        service.begin_enrollment(user)

        with pytest.raises(MfaInvalidCodeError):
            service.confirm_enrollment(user, "000000")

        device = UserTotpDevice.objects.get(user=user)
        assert device.confirmed_at is None
        assert device.failed_attempts == 1

    def test_confirm_without_a_pending_device_is_rejected(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "confirm-none")

        with pytest.raises(MfaNotEnrolledError):
            MfaService().confirm_enrollment(user, "123456")

    def test_enrollment_is_audited(self, tenant_a) -> None:
        """Rule 6."""
        user = _staff_user(tenant_a, "confirm-audit")
        _enroll(MfaService(), user)

        assert _audited(user, AuditEntry.OP_USER_MFA_ENROLL)


# ---------------------------------------------------------------------------
# Rule 2/3 — TOTP verification, replay, lockout
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestVerifyTotp:
    """Code acceptance window, replay protection and the lockout counter."""

    def test_accepts_a_code_from_a_real_authenticator_app(self, tenant_a) -> None:
        """The code a phone would show one step later is accepted verbatim."""
        user = _staff_user(tenant_a, "verify-ok")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        # One step later, so the enrollment step is not itself replayed.
        code = _code_at(secret, datetime.fromtimestamp(BASE_TS + STEP_SECONDS, UTC))

        assert service.verify(user, code=code) == "totp"

    def test_a_used_code_cannot_be_replayed(self, tenant_a) -> None:
        """Rule 2: the accepted step must be strictly greater than the last one.

        F4: a replay must NOT touch ``failed_attempts``. It can never grant
        access, so there is nothing to throttle — counting it would let a
        double-click or a client retry lock the legitimate user out.
        """
        user = _staff_user(tenant_a, "verify-replay")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        code = _code(secret, offset=1)
        service.verify(user, code=code)
        before = UserTotpDevice.objects.get(user=user)
        assert before.failed_attempts == 0

        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, code=code)

        after = UserTotpDevice.objects.get(user=user)
        assert after.failed_attempts == 0, "a replay must not count as a failure"
        assert after.last_used_step == before.last_used_step

    def test_five_replays_do_not_lock_the_device(self, tenant_a) -> None:
        """F4 end-to-end: the double-submit storm that used to lock a user."""
        user = _staff_user(tenant_a, "verify-replay-storm")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        code = _code(secret, offset=1)
        service.verify(user, code=code)

        for _attempt in range(5):
            with pytest.raises(MfaInvalidCodeError):
                service.verify(user, code=code)

        device = UserTotpDevice.objects.get(user=user)
        assert device.failed_attempts == 0
        assert device.locked_until is None

    @pytest.mark.parametrize("offset", [-1, 1])
    def test_accepts_the_neighbouring_steps(self, tenant_a, offset: int) -> None:
        """``MFA_TOTP_VALID_WINDOW=1`` absorbs one step of clock drift.

        ``last_used_step`` is cleared first so this test measures the *window*
        only; the replay guard has its own test above.
        """
        user = _staff_user(tenant_a, f"verify-window-{offset}")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        UserTotpDevice.objects.filter(user=user).update(last_used_step=None)

        assert service.verify(user, code=_code(secret, offset=offset)) == "totp"

    @pytest.mark.parametrize("offset", [-3, 3])
    def test_rejects_codes_outside_the_window(self, tenant_a, offset: int) -> None:
        user = _staff_user(tenant_a, f"verify-outside-{offset}")
        service = MfaService()
        secret, _codes = _enroll(service, user)

        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, code=_code(secret, offset=offset))

    def test_locks_after_max_attempts(self, tenant_a) -> None:
        """Rule 3: 5 wrong codes lock the device for ``MFA_LOCKOUT_SECONDS``."""
        user = _staff_user(tenant_a, "verify-lockout")
        service = MfaService()
        secret, _codes = _enroll(service, user)

        for _attempt in range(5):
            with pytest.raises(MfaInvalidCodeError):
                service.verify(user, code="000000")

        device = UserTotpDevice.objects.get(user=user)
        assert device.failed_attempts == 5
        assert device.locked_until is not None

        # Even the correct code is refused while locked.
        with pytest.raises(MfaLockedError) as excinfo:
            service.verify(user, code=_code(secret, offset=1))
        assert 1 <= excinfo.value.retry_after <= 900

    def test_expired_lockout_lets_the_user_back_in(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "verify-unlock")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        UserTotpDevice.objects.filter(user=user).update(
            failed_attempts=5, locked_until=timezone.now() - timedelta(seconds=1)
        )

        assert service.verify(user, code=_code(secret, offset=1)) == "totp"
        device = UserTotpDevice.objects.get(user=user)
        assert device.failed_attempts == 0
        assert device.locked_until is None

    def test_one_wrong_code_after_lock_expiry_does_not_re_lock(self, tenant_a) -> None:
        """F3: expiry must persist the counter reset, not just return.

        Before the fix, ``_assert_not_locked`` returned on an expired lock while
        leaving ``failed_attempts`` at the threshold, so the *first* wrong code
        afterwards tripped the lock again for the full window — with any clock
        skew that is a permanently locked account.
        """
        user = _staff_user(tenant_a, "verify-unlock-one-failure")
        service = MfaService()
        _secret, _codes = _enroll(service, user)
        UserTotpDevice.objects.filter(user=user).update(
            failed_attempts=5, locked_until=timezone.now() - timedelta(seconds=1)
        )

        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, code="000000")

        device = UserTotpDevice.objects.get(user=user)
        assert device.failed_attempts == 1
        assert device.locked_until is None

    def test_success_resets_the_failure_counter(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "verify-reset")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, code="000000")

        service.verify(user, code=_code(secret, offset=1))

        assert UserTotpDevice.objects.get(user=user).failed_attempts == 0

    @pytest.mark.parametrize("payload", [123456, 0, None, [], {}])
    def test_non_string_code_is_a_plain_rejection(self, tenant_a, payload) -> None:
        """F8: JSON ``int``/``null``/list must not become an AttributeError/500."""
        user = _staff_user(tenant_a, f"verify-nonstr-{type(payload).__name__}")
        service = MfaService()
        _enroll(service, user)

        if payload is None:
            with pytest.raises(ValueError):
                service.verify(user, code=payload)
            return
        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, code=payload)

    @pytest.mark.parametrize("payload", [123456, [], {}])
    def test_non_string_recovery_code_is_a_plain_rejection(
        self, tenant_a, payload
    ) -> None:
        user = _staff_user(tenant_a, f"recovery-nonstr-{type(payload).__name__}")
        service = MfaService()
        _enroll(service, user)

        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, recovery_code=payload)

    def test_inactive_user_gets_no_factor_accepted(self, tenant_a) -> None:
        """Mirrors ``_load_challenge_user``: a disabled account accepts nothing."""
        user = _staff_user(tenant_a, "verify-inactive")
        service = MfaService()
        secret, codes = _enroll(service, user)
        User.objects.filter(pk=user.pk).update(is_active=False)
        user.refresh_from_db()

        with pytest.raises(MfaNotEnrolledError):
            service.verify(user, code=_code(secret, offset=1))
        with pytest.raises(MfaNotEnrolledError):
            service.verify(user, recovery_code=codes[0])
        # Neither the code nor a recovery code may be burned by the attempt.
        assert not UserRecoveryCode.objects.filter(
            user_id=user.pk, used_at__isnull=False
        ).exists()

    def test_verify_requires_exactly_one_factor(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "verify-both")

        with pytest.raises(ValueError):
            MfaService().verify(user)
        with pytest.raises(ValueError):
            MfaService().verify(user, code="123456", recovery_code="AAAA-BBBB")


# ---------------------------------------------------------------------------
# Rule 4/5 — recovery codes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestVerifyRecovery:
    """Single-use, user-bound recovery codes."""

    def test_accepts_a_recovery_code_once(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "recovery-once")
        service = MfaService()
        _secret, codes = _enroll(service, user)

        assert service.verify(user, recovery_code=codes[0]) == "recovery"
        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, recovery_code=codes[0])

        row = UserRecoveryCode.objects.get(user=user, used_at__isnull=False)
        assert row.used_at is not None

    def test_normalises_case_and_separators(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "recovery-normalise")
        service = MfaService()
        _secret, codes = _enroll(service, user)
        mangled = " " + codes[1].lower().replace("-", " ") + " "

        assert normalize_recovery_code(mangled) == normalize_recovery_code(codes[1])
        assert service.verify(user, recovery_code=mangled) == "recovery"

    def test_a_code_of_another_user_is_rejected(self, tenant_a, tenant_b) -> None:
        """Rule 4: the lookup is user-bound, never global by hash."""
        first = _staff_user(tenant_a, "recovery-first")
        second = _staff_user(tenant_b, "recovery-second")
        service = MfaService()
        _secret, first_codes = _enroll(service, first)
        _enroll(service, second)

        with pytest.raises(MfaInvalidCodeError):
            service.verify(second, recovery_code=first_codes[0])

        # ... and the code is still valid for its actual owner.
        assert service.verify(first, recovery_code=first_codes[0]) == "recovery"

    def test_a_recovery_code_is_rejected_while_locked(self, tenant_a) -> None:
        """The lockout covers recovery codes too (rule 3)."""
        user = _staff_user(tenant_a, "recovery-locked")
        service = MfaService()
        _secret, codes = _enroll(service, user)
        UserTotpDevice.objects.filter(user=user).update(
            failed_attempts=5, locked_until=timezone.now() + timedelta(seconds=600)
        )

        with pytest.raises(MfaLockedError):
            service.verify(user, recovery_code=codes[0])

        # The code must not be burned by an attempt made while locked.
        assert not UserRecoveryCode.objects.filter(
            user=user, used_at__isnull=False
        ).exists()

    def test_a_wrong_recovery_code_counts_as_a_failure(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "recovery-fail")
        service = MfaService()
        _enroll(service, user)

        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, recovery_code="AAAA-BBBB-CCCC-DDDD")

        assert UserTotpDevice.objects.get(user=user).failed_attempts == 1

    def test_recovery_use_is_audited(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "recovery-audit")
        service = MfaService()
        _secret, codes = _enroll(service, user)
        service.verify(user, recovery_code=codes[0])

        assert _audited(user, AuditEntry.OP_USER_MFA_RECOVERY_USED)


@pytest.mark.django_db
class TestStrictDecrypt:
    """Rule 1: an unusable secret refuses the login instead of guessing."""

    def test_plaintext_secret_is_not_accepted(self, tenant_a) -> None:
        """``decrypt_secret``'s plaintext pass-through must not apply here."""
        user = _staff_user(tenant_a, "decrypt-plain")
        service = MfaService()
        data = service.begin_enrollment(user)
        device = UserTotpDevice.objects.get(user=user)
        device.secret_ciphertext = data.secret_b32  # simulate a legacy row
        device.confirmed_at = timezone.now()
        device.save()

        with pytest.raises(MfaUnavailableError):
            service.verify(user, code=_code(data.secret_b32, offset=1))

    def test_tampered_ciphertext_raises_unavailable(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "decrypt-tampered")
        service = MfaService()
        data = service.begin_enrollment(user)
        device = UserTotpDevice.objects.get(user=user)
        device.secret_ciphertext = "gAAAA" + "A" * 40
        device.confirmed_at = timezone.now()
        device.save()

        with pytest.raises(MfaUnavailableError):
            service.verify(user, code=_code(data.secret_b32, offset=1))

    def test_missing_secret_raises_unavailable(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "decrypt-empty")
        service = MfaService()
        _enroll(service, user)
        UserTotpDevice.objects.filter(user=user).update(secret_ciphertext="")

        with pytest.raises(MfaUnavailableError):
            service.verify(user, code="123456")


@pytest.mark.django_db
class TestRegenerateRecoveryCodes:
    """Rule 5: regeneration invalidates the previous set."""

    def test_old_codes_stop_working_and_new_ones_work(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "regenerate")
        service = MfaService()
        secret, old_codes = _enroll(service, user)

        new_codes = service.regenerate_recovery_codes(
            user, _code(secret, offset=1)
        )

        assert len(new_codes) == 10
        assert not set(new_codes) & set(old_codes)
        with pytest.raises(MfaInvalidCodeError):
            service.verify(user, recovery_code=old_codes[0])
        assert service.verify(user, recovery_code=new_codes[0]) == "recovery"

    def test_requires_a_valid_current_code(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "regenerate-badcode")
        service = MfaService()
        _enroll(service, user)

        with pytest.raises(MfaInvalidCodeError):
            service.regenerate_recovery_codes(user, "000000")

    def test_a_window_above_two_is_a_configuration_error(
        self, tenant_a, settings
    ) -> None:
        """F7: the drift window is the only knob widening the guessable space."""
        user = _staff_user(tenant_a, "regenerate-window")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        settings.MFA_TOTP_VALID_WINDOW = 3

        with pytest.raises(ImproperlyConfigured):
            service.verify(user, code=_code(secret, offset=1))

    def test_a_failing_regeneration_keeps_the_previous_codes(self, tenant_a) -> None:
        """F10: verify + replace run in one transaction, so a failure rolls back."""
        user = _staff_user(tenant_a, "regenerate-atomic")
        service = MfaService()
        secret, codes = _enroll(service, user)

        with pytest.raises(MfaInvalidCodeError):
            service.regenerate_recovery_codes(user, "000000")

        assert UserRecoveryCode.objects.filter(user=user).count() == 10
        assert service.verify(user, recovery_code=codes[0]) == "recovery"

    def test_an_audit_outage_fails_closed(self, tenant_a) -> None:
        """F5: an audit failure surfaces as unavailability, not as a bare 500."""
        user = _staff_user(tenant_a, "audit-outage")
        service = MfaService()
        _secret, codes = _enroll(service, user)

        with mock.patch(
            "auth_tenancy.services.mfa.log_write",
            side_effect=RuntimeError("audit table unavailable"),
        ):
            with pytest.raises(MfaUnavailableError):
                service.verify(user, recovery_code=codes[0])

        # Fail-closed: the code was NOT consumed by the failed attempt.
        assert not UserRecoveryCode.objects.filter(
            user=user, used_at__isnull=False
        ).exists()

    def test_regeneration_is_audited(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "regenerate-audit")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        service.regenerate_recovery_codes(user, _code(secret, offset=1))

        assert _audited(user, AuditEntry.OP_USER_MFA_RECOVERY_REGENERATE)


# ---------------------------------------------------------------------------
# Disable / reset
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDisable:
    """Password *and* current code are required; policy can forbid it."""

    def test_requires_the_password(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "disable-pw")
        service = MfaService()
        secret, _codes = _enroll(service, user)

        with pytest.raises(MfaInvalidCredentialsError):
            service.disable(user, password="wrong", code=_code(secret, offset=1))

        assert UserTotpDevice.objects.filter(user=user).exists()

    def test_requires_a_code(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "disable-code")
        service = MfaService()
        _enroll(service, user)

        with pytest.raises(MfaInvalidCodeError):
            service.disable(user, password=_STAFF_PASSWORD, code="000000")

        assert UserTotpDevice.objects.filter(user=user).exists()

    def test_removes_device_and_codes_and_audits(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "disable-ok")
        service = MfaService()
        secret, _codes = _enroll(service, user)

        service.disable(user, password=_STAFF_PASSWORD, code=_code(secret, offset=1))

        assert not UserTotpDevice.objects.filter(user=user).exists()
        assert not UserRecoveryCode.objects.filter(user=user).exists()
        assert _audited(user, AuditEntry.OP_USER_MFA_DISABLE)

    def test_confirmed_non_staff_cannot_disable_under_required(
        self, tenant_a, settings
    ) -> None:
        """F12: policy is ``mfa_required``, not ``is_staff``.

        A confirmed non-staff account under ``required`` is covered by the
        policy too; the old ``is_staff or is_superuser`` check let it strip its
        own second factor.
        """
        user = _staff_user(tenant_a, "disable-confirmed-nonstaff")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        User.objects.filter(pk=user.pk).update(is_staff=False, is_superuser=False)
        user.refresh_from_db()
        settings.MFA_STAFF_ENFORCEMENT = "required"

        with pytest.raises(MfaRequiredError):
            service.disable(
                user, password=_STAFF_PASSWORD, code=_code(secret, offset=1)
            )

        assert UserTotpDevice.objects.filter(user=user).exists()

    def test_confirmed_non_staff_may_disable_under_optional(
        self, tenant_a, settings
    ) -> None:
        """No regression: under ``optional`` un-enrolling is the user's choice."""
        user = _staff_user(tenant_a, "disable-nonstaff-optional")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        User.objects.filter(pk=user.pk).update(is_staff=False, is_superuser=False)
        user.refresh_from_db()
        settings.MFA_STAFF_ENFORCEMENT = "optional"

        service.disable(user, password=_STAFF_PASSWORD, code=_code(secret, offset=1))

        assert not UserTotpDevice.objects.filter(user=user).exists()

    def test_forbidden_when_enforcement_is_required(self, tenant_a, settings) -> None:
        user = _staff_user(tenant_a, "disable-required")
        service = MfaService()
        secret, _codes = _enroll(service, user)
        settings.MFA_STAFF_ENFORCEMENT = "required"

        with pytest.raises(MfaRequiredError):
            service.disable(
                user, password=_STAFF_PASSWORD, code=_code(secret, offset=1)
            )

        assert UserTotpDevice.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestReset:
    """Break-glass removal (WP E3.7 surface)."""

    def test_deletes_everything_and_audits(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "reset")
        service = MfaService()
        _enroll(service, user)

        service.reset(user, actor="cli:admin")

        assert not UserTotpDevice.objects.filter(user=user).exists()
        assert not UserRecoveryCode.objects.filter(user=user).exists()
        assert _audited(user, AuditEntry.OP_USER_MFA_RESET)

    def test_reset_without_a_device_is_harmless(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "reset-none")

        MfaService().reset(user, actor="cli:admin")

        assert not UserTotpDevice.objects.filter(user=user).exists()


# ---------------------------------------------------------------------------
# Rule 4a — signed challenge
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestChallenge:
    """Signed, expiring, single-use login challenge."""

    def test_roundtrip_returns_the_user_and_purpose(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "challenge-roundtrip")
        service = MfaService()

        token = service.issue_challenge(user, purpose="verify")
        recovered, purpose = service.read_challenge(token)

        assert recovered.id == user.id
        assert purpose == "verify"

    def test_a_challenge_can_only_be_consumed_once(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "challenge-once")
        service = MfaService()
        token = service.issue_challenge(user, purpose="verify")

        service.consume_challenge(token)
        with pytest.raises(MfaChallengeInvalidError):
            service.consume_challenge(token)

    def test_two_challenges_are_independent(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "challenge-independent")
        service = MfaService()
        first = service.issue_challenge(user, purpose="verify")
        second = service.issue_challenge(user, purpose="enroll")

        service.consume_challenge(first)

        assert service.consume_challenge(second)[1] == "enroll"

    def test_an_expired_challenge_is_rejected(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "challenge-expired")
        service = MfaService()
        signer = mfa_module.TimestampSigner(salt=mfa_module.CHALLENGE_SALT)
        payload = {"uid": str(user.id), "purpose": "verify", "n": "nonce-expired"}
        with mock.patch(
            "django.core.signing.time.time",
            lambda: datetime.now(UTC).timestamp() - 10_000,
        ):
            stale = signer.sign_object(payload)

        with pytest.raises(MfaChallengeInvalidError):
            service.read_challenge(stale)

    def test_a_tampered_challenge_is_rejected(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "challenge-tampered")
        service = MfaService()
        token = service.issue_challenge(user, purpose="verify")

        with pytest.raises(MfaChallengeInvalidError):
            service.read_challenge(token + "x")

    def test_an_unknown_user_is_rejected(self, tenant_a) -> None:
        service = MfaService()
        signer = mfa_module.TimestampSigner(salt=mfa_module.CHALLENGE_SALT)
        token = signer.sign_object(
            {
                "uid": "00000000-0000-0000-0000-000000000000",
                "purpose": "verify",
                "n": "nonce-ghost",
            }
        )

        with pytest.raises(MfaChallengeInvalidError):
            service.read_challenge(token)

    def test_an_unknown_purpose_is_rejected(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "challenge-purpose")
        service = MfaService()

        with pytest.raises(ValueError):
            service.issue_challenge(user, purpose="reset")

    def test_a_cache_outage_fails_closed(self, tenant_a, monkeypatch) -> None:
        """Rule 4a: without the cache the nonce cannot be burned."""
        user = _staff_user(tenant_a, "challenge-cache")
        service = MfaService()
        token = service.issue_challenge(user, purpose="verify")

        def _broken_add(*_args, **_kwargs):
            raise ConnectionError("cache down")

        monkeypatch.setattr(mfa_module.cache, "add", _broken_add)

        with pytest.raises(MfaUnavailableError):
            service.consume_challenge(token)


# ---------------------------------------------------------------------------
# ENT-E7 = A — enrollment grants
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestEnrollmentGrant:
    """Single-use, ≤ 24 h, one valid grant per user."""

    def test_grant_is_consumed_by_a_successful_enrollment(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "grant-consume")
        service = MfaService()
        service.grant_enrollment(user, actor="cli:admin", reason="lost device")
        assert service.has_valid_enrollment_grant(user) is True

        _enroll(service, user)

        assert service.has_valid_enrollment_grant(user) is False
        grant = UserMfaEnrollmentGrant.objects.get(user=user)
        assert grant.used_at is not None

    def test_an_expired_grant_is_not_valid(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "grant-expired")
        service = MfaService()
        grant = service.grant_enrollment(user, actor="cli:admin", reason="x")
        UserMfaEnrollmentGrant.objects.filter(pk=grant.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        assert service.has_valid_enrollment_grant(user) is False

    def test_a_new_grant_invalidates_the_older_one(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "grant-supersede")
        service = MfaService()
        first = service.grant_enrollment(user, actor="cli:admin", reason="one")
        second = service.grant_enrollment(user, actor="cli:admin", reason="two")

        first.refresh_from_db()
        assert first.used_at is not None
        assert second.used_at is None
        assert (
            UserMfaEnrollmentGrant.objects.filter(
                user=user, used_at__isnull=True
            ).count()
            == 1
        )

    def test_grant_ttl_is_capped_at_24_hours(self, tenant_a, settings) -> None:
        user = _staff_user(tenant_a, "grant-ttl")
        settings.MFA_ENROLL_GRANT_MAX_TTL_SECONDS = 86_400
        settings.MFA_ENROLL_GRANT_TTL_SECONDS = 86_401

        with pytest.raises(ImproperlyConfigured):
            MfaService().grant_enrollment(
                user, actor="cli:admin", reason="too long"
            )

        assert not UserMfaEnrollmentGrant.objects.filter(user=user).exists()

    def test_a_grant_requires_a_reason(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "grant-noreason")

        with pytest.raises(ValueError):
            MfaService().grant_enrollment(user, actor="cli:admin", reason="   ")

    def test_required_without_grant_refuses_begin_enrollment(
        self, tenant_a, settings
    ) -> None:
        """F2 / ENT-E7 = A: no grant, no self-enrollment under ``required``."""
        user = _staff_user(tenant_a, "grant-gate-begin")
        settings.MFA_STAFF_ENFORCEMENT = "required"

        with pytest.raises(MfaEnrollmentRequiresGrantError):
            MfaService().begin_enrollment(user)

        assert not UserTotpDevice.objects.filter(user=user).exists()

    def test_required_with_grant_allows_enrollment_and_consumes_it(
        self, tenant_a, settings
    ) -> None:
        user = _staff_user(tenant_a, "grant-gate-happy")
        settings.MFA_STAFF_ENFORCEMENT = "required"
        service = MfaService()
        service.grant_enrollment(user, actor="cli:admin", reason="new staff")

        data = service.begin_enrollment(user)
        codes = service.confirm_enrollment(user, _code(data.secret_b32))

        assert len(codes) == 10
        assert UserTotpDevice.objects.get(user=user).confirmed_at is not None
        assert service.has_valid_enrollment_grant(user) is False
        grant = UserMfaEnrollmentGrant.objects.get(user=user)
        assert grant.used_at is not None

    def test_confirm_without_a_spendable_grant_is_refused(
        self, tenant_a, settings
    ) -> None:
        """F2: the gate is re-checked at confirm time, so an expired grant blocks.

        Also proves a *failed* confirm does not burn the grant: it is consumed
        only after the code proved correct.
        """
        user = _staff_user(tenant_a, "grant-gate-confirm")
        settings.MFA_STAFF_ENFORCEMENT = "required"
        service = MfaService()
        grant = service.grant_enrollment(user, actor="cli:admin", reason="bootstrap")
        data = service.begin_enrollment(user)

        UserMfaEnrollmentGrant.objects.filter(pk=grant.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with pytest.raises(MfaEnrollmentRequiresGrantError):
            service.confirm_enrollment(user, _code(data.secret_b32))

        assert UserTotpDevice.objects.get(user=user).confirmed_at is None
        assert not UserRecoveryCode.objects.filter(user=user).exists()

    def test_wrong_code_under_required_keeps_the_grant(
        self, tenant_a, settings
    ) -> None:
        """A wrong code counts as a failure and must not burn the grant."""
        user = _staff_user(tenant_a, "grant-gate-wrong-code")
        settings.MFA_STAFF_ENFORCEMENT = "required"
        service = MfaService()
        service.grant_enrollment(user, actor="cli:admin", reason="bootstrap")
        service.begin_enrollment(user)

        with pytest.raises(MfaInvalidCodeError):
            service.confirm_enrollment(user, "000000")

        device = UserTotpDevice.objects.get(user=user)
        assert device.failed_attempts == 1
        # The grant survives a wrong code, so the legitimate owner can retry.
        assert service.has_valid_enrollment_grant(user) is True

    def test_grant_issuance_is_audited(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "grant-audit")
        MfaService().grant_enrollment(user, actor="cli:admin", reason="audit")

        assert _audited(user, AuditEntry.OP_USER_MFA_ENROLL_GRANT)


# ---------------------------------------------------------------------------
# Rule 2 — parallel double verify
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_parallel_double_verify_lets_exactly_one_request_win(tenant_a) -> None:
    """Rule 2: ``select_for_update`` makes the replay check race-free.

    Two threads present the *same* valid code at the same time. The row lock
    serialises them, the second one re-reads the committed ``last_used_step`` and
    is rejected — so a code can never be spent twice, even under concurrency.
    """
    user = _staff_user(tenant_a, "parallel-verify")
    service = MfaService()
    secret, _codes = _enroll(service, user)
    code = _code(secret, offset=1)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def _attempt() -> None:
        result = "error"
        try:
            barrier.wait(timeout=10)
            MfaService().verify(user, code=code)
            result = "accepted"
        except MfaInvalidCodeError:
            result = "rejected"
        finally:
            connection.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=_attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes) == ["accepted", "rejected"], outcomes


# ---------------------------------------------------------------------------
# F5 — grant issuance is serialised per user
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_parallel_grant_enrollment_escapes_no_integrity_error(tenant_a) -> None:
    """F5: two concurrent grants leave exactly one *valid* grant, no 500.

    ``select_for_update().filter(used_at__isnull=True).update(...)`` locks
    nothing when no unused grant exists, so both threads used to pass that
    statement, both INSERTed, and the loser died on
    ``uq_mfa_grant_user_unused`` with an unhandled ``IntegrityError`` (a 500 out
    of a credentials endpoint). ``_lock_user`` gives the read-then-insert path a
    real serialisation point; the partial unique constraint remains the
    fail-closed backstop and is additionally mapped to
    :class:`MfaEnrollmentGrantConflictError`.

    Asserted on behaviour, not on which thread wins: both may report success
    (the second marks the first's grant used before creating its own), or the
    loser may report the domain error. What must never happen is an escaped
    ``IntegrityError``, or more than one spendable grant afterwards.
    """
    user = _staff_user(tenant_a, "grant-parallel")

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def _attempt() -> None:
        result = "error"
        try:
            barrier.wait(timeout=10)
            MfaService().grant_enrollment(user, actor="cli:admin", reason="race")
            result = "created"
        except MfaEnrollmentGrantConflictError:
            result = "conflict"
        except MfaError:
            result = "domain-error"
        finally:
            connection.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=_attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(outcomes) == 2, outcomes
    assert "error" not in outcomes, f"a non-domain error escaped: {outcomes}"
    assert (
        UserMfaEnrollmentGrant.objects.filter(
            user=user, used_at__isnull=True
        ).count()
        <= 1
    ), "the partial unique constraint must leave at most one unused grant"
    assert MfaService().has_valid_enrollment_grant(user) is True


# ---------------------------------------------------------------------------
# Observability — the security log must never carry credential material
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_security_log_never_contains_secrets_or_recovery_codes(
    tenant_a, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 6 / security review: the log is auditable *without* being a leak.

    Exercises the full lifecycle (enroll -> confirm -> verify -> regenerate) with
    the ``reqogniloom.security`` logger at DEBUG and asserts that neither the
    TOTP secret, nor the provisioning URI that embeds it, nor any recovery code
    ever reaches a log record.
    """
    caplog.set_level(logging.DEBUG, logger="reqogniloom.security")
    user = _staff_user(tenant_a, "log-hygiene")
    service = MfaService()

    data = service.begin_enrollment(user)
    codes = service.confirm_enrollment(user, _code(data.secret_b32))
    service.verify(user, code=_code(data.secret_b32, offset=1))
    service.verify(user, recovery_code=codes[0])
    # Move the pinned clock on so the next code is both fresh and in-window.
    monkeypatch.setattr(mfa_module, "_current_step", lambda: BASE_STEP + 2)
    regenerated = service.regenerate_recovery_codes(
        user, _code(data.secret_b32, offset=2)
    )

    text = caplog.text
    assert text, "the security logger produced no records — assertion is vacuous"
    assert data.secret_b32 not in text
    assert data.otpauth_uri not in text
    for code in list(codes) + list(regenerated):
        assert code not in text, "a recovery code was written to the log"
        assert normalize_recovery_code(code) not in text.replace("-", "")


# ---------------------------------------------------------------------------
# F10 — regeneration is a single transaction under the device lock
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_parallel_regeneration_leaves_exactly_one_code_set(tenant_a) -> None:
    """F10: two concurrent regenerations must not interleave their row sets.

    Verification and replacement now share one transaction under the device row
    lock, so the two regenerations serialise: the second deletes the first's set
    before writing its own. The invariant asserted here is the observable one —
    exactly one complete 10-code set survives, never an orphaned remainder of
    the loser's set (and never a partially deleted set).

    A full interleaving fault-injection is deliberately not attempted: it would
    need a seam inside ``_replace_recovery_codes``, which is more test machinery
    than the property is worth. The lock is what provides the guarantee.
    """
    user = _staff_user(tenant_a, "regenerate-parallel")
    service = MfaService()
    secret, _codes = _enroll(service, user)

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def _attempt(offset: int) -> None:
        result = "error"
        try:
            barrier.wait(timeout=10)
            MfaService().regenerate_recovery_codes(user, _code(secret, offset=offset))
            result = "regenerated"
        except MfaError:
            result = "domain-error"
        finally:
            connection.close()
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=_attempt, args=(1,)),
               threading.Thread(target=_attempt, args=(2,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert "error" not in outcomes, f"a non-domain error escaped: {outcomes}"
    # The loser's TOTP step is spent by the winner's lock ordering, so a
    # domain-error outcome is a legitimate result; both must still be accounted
    # for.
    assert len(outcomes) == 2, outcomes
    assert UserRecoveryCode.objects.filter(user=user).count() == 10
    assert (
        UserRecoveryCode.objects.filter(user=user, used_at__isnull=True).count() == 10
    )
