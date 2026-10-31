"""``manage.py mfa_reset`` — break-glass reset command (#1308, WP E3.7).

The command is the only entry point for ``MfaService.reset`` + ``grant_enrollment``
and therefore the only legitimate way to recover a staff account whose
authenticator is gone (or whose stored secret became undecryptable after a
``FIELD_ENCRYPTION_KEY`` rotation). The properties pinned here are the ones a
future refactor could silently drop:

* the credential really is gone (device *and* recovery codes) and both governed
  acts are audited (``user.mfa_reset``, ``user.mfa_enroll_grant``);
* exactly one spendable grant remains, and it is single-use — consuming it by
  enrolling again leaves nothing spendable behind;
* a never-enrolled account still gets a grant instead of an error;
* an unknown username, a missing ``--reason`` and an empty ``--reason`` are
  rejected *before* anything is written;
* neither stdout/stderr nor the ``reqogniloom.security`` log ever carries a TOTP
  secret, a recovery code or an ``otpauth://`` URI.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from io import StringIO

import pyotp
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from audit.models import AuditEntry
from auth_tenancy.management.commands.mfa_reset import ACTOR
from auth_tenancy.models import (
    UserMfaEnrollmentGrant,
    UserRecoveryCode,
    UserTotpDevice,
)
from auth_tenancy.services.mfa import MfaService
from persistence.models import User

_STAFF_PASSWORD = "s3cret-staff-pw"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _staff_user(tenant, username: str = "mfa-cli", **extra) -> User:
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


def _enroll(user: User) -> tuple[str, list[str]]:
    """Run the real two-step enrollment; return ``(secret, recovery_codes)``."""
    service = MfaService()
    data = service.begin_enrollment(user)
    codes = service.confirm_enrollment(user, pyotp.TOTP(data.secret_b32).now())
    return data.secret_b32, codes


def _run(*args: str) -> tuple[str, str]:
    """Invoke the command; return ``(stdout, stderr)``."""
    stdout, stderr = StringIO(), StringIO()
    call_command("mfa_reset", *args, stdout=stdout, stderr=stderr)
    return stdout.getvalue(), stderr.getvalue()


def _audited(user: User, operation: str) -> bool:
    return AuditEntry.unscoped.filter(
        entity_id=user.id, entity_type="User", op=operation
    ).exists()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMfaResetCommand:
    def test_reset_removes_device_and_codes_and_audits(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "reset-full")
        _enroll(user)
        assert UserTotpDevice.objects.filter(user=user).exists()
        assert UserRecoveryCode.objects.filter(user=user).count() == 10

        _run(user.username, "--reason", "phone lost")

        assert not UserTotpDevice.objects.filter(user=user).exists()
        assert not UserRecoveryCode.objects.filter(user=user).exists()
        assert _audited(user, AuditEntry.OP_USER_MFA_RESET)
        assert _audited(user, AuditEntry.OP_USER_MFA_ENROLL_GRANT)

    def test_reset_creates_single_use_grant(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "reset-grant")
        _enroll(user)

        _run(user.username, "--reason", "device replaced")

        grants = list(UserMfaEnrollmentGrant.objects.filter(user=user))
        assert len(grants) == 1
        grant = grants[0]
        assert grant.used_at is None
        assert grant.granted_by == ACTOR
        assert grant.reason == "device replaced"
        now = timezone.now()
        assert grant.expires_at > now
        assert grant.expires_at <= now + timedelta(seconds=86_400)

        # Single use: the very next successful enrollment spends it, and no
        # second spendable grant exists afterwards.
        _enroll(user)
        grant.refresh_from_db()
        assert grant.used_at is not None
        assert MfaService().has_valid_enrollment_grant(user) is False
        assert (
            UserMfaEnrollmentGrant.objects.filter(
                user=user, used_at__isnull=True
            ).count()
            == 0
        )

    def test_reset_for_never_enrolled_staff_creates_grant(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "reset-never-enrolled")
        assert not UserTotpDevice.objects.filter(user=user).exists()

        stdout, _stderr = _run(user.username, "--reason", "new staff account")

        assert "device removed=False" in stdout
        assert not UserTotpDevice.objects.filter(user=user).exists()
        assert not UserRecoveryCode.objects.filter(user=user).exists()
        assert MfaService().has_valid_enrollment_grant(user) is True


# ---------------------------------------------------------------------------
# Rejections — nothing may be written
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMfaResetCommandRejections:
    def test_unknown_username_raises_and_writes_nothing(self, tenant_a) -> None:
        _staff_user(tenant_a, "known")

        with pytest.raises(CommandError):
            _run("ghost", "--reason", "whatever")

        assert not UserMfaEnrollmentGrant.objects.exists()
        assert not UserTotpDevice.objects.exists()
        assert not UserRecoveryCode.objects.exists()
        assert not AuditEntry.unscoped.exists()

    def test_missing_reason_is_rejected(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "reset-no-reason")
        _enroll(user)

        with pytest.raises(CommandError):
            _run(user.username)

        # The credential survives — nothing was written or removed.
        assert UserTotpDevice.objects.filter(user=user).exists()
        assert not UserMfaEnrollmentGrant.objects.filter(user=user).exists()

    def test_blank_reason_is_rejected(self, tenant_a) -> None:
        user = _staff_user(tenant_a, "reset-blank-reason")
        _enroll(user)

        with pytest.raises(CommandError):
            _run(user.username, "--reason", "   ")

        assert UserTotpDevice.objects.filter(user=user).exists()
        assert not UserMfaEnrollmentGrant.objects.filter(user=user).exists()


# ---------------------------------------------------------------------------
# No secret material anywhere
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_no_secret_or_code_in_stdout_stderr_or_log(tenant_a, caplog) -> None:
    user = _staff_user(tenant_a, "reset-secret-free")
    secret, recovery_codes = _enroll(user)

    with caplog.at_level(logging.DEBUG, logger="reqogniloom.security"):
        stdout, stderr = _run(user.username, "--reason", "lost device")

    combined = stdout + stderr
    assert secret not in combined
    assert "otpauth" not in combined
    # The operator sees the subject and the counters — no credential material.
    assert user.username in stdout

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in logged
    assert "otpauth" not in logged
    for code in recovery_codes:
        # Hyphenated form, as shown to the user.
        assert code not in combined
        assert code not in logged
        # Normalised form, in case a future change prints it without hyphens.
        assert code.replace("-", "") not in combined
        assert code.replace("-", "") not in logged
    # The command's own line names username + actor, nothing else secret.
    assert any(
        "mfa_reset command" in record.getMessage()
        and user.username in record.getMessage()
        and ACTOR in record.getMessage()
        for record in caplog.records
    )
