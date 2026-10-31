"""``manage.py mfa_enforce_cutover`` — enforcement cutover command (#1308, E3.9).

The command is the bridge between "MFA available" and "MFA required": it burns
every staff session so each account re-authenticates once with its second factor.
The properties pinned here are the ones a future refactor could silently drop:

* staff refresh families are revoked with the ``mfa_cutover`` reason, staff
  Django-admin sessions are deleted, and non-staff rows are left untouched;
* staff API keys are *listed*, never revoked, and no key material reaches the
  output;
* ``--dry-run`` reports counters but writes nothing (no revocation, no delete,
  no audit row);
* the tenant context that was armed before the command is restored afterwards;
* ``--format json`` is machine-readable and an unsupported format is a
  ``CommandError``.
"""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from uuid import uuid4

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from audit.models import AuditEntry
from auth_tenancy.management.commands.mfa_enforce_cutover import Command
from auth_tenancy.models import ApiKey, RefreshToken, UserTotpDevice
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import User
from persistence.tenancy import TenantContext

pytestmark = pytest.mark.django_db

_STAFF_PASSWORD = "s3cret-staff-pw"


def _user(tenant, username: str, *, staff: bool) -> User:
    user = User.objects.create(
        username=username,
        email=f"{username}@cutover.test",
        tenant=tenant,
        is_staff=staff,
        is_superuser=False,
    )
    user.set_password(_STAFF_PASSWORD)
    user.save(update_fields=["password"])
    return user


def _refresh_row(user: User, *, session_id=None) -> RefreshToken:
    """Create one live (unrevoked) refresh-token row for ``user``."""
    return RefreshToken.unscoped.create(
        tenant=user.tenant,
        user=user,
        jti=uuid4(),
        session_id=session_id or uuid4(),
        expires_at=timezone.now() + timedelta(days=1),
    )


def _admin_session(user: User) -> str:
    """Create a Django-admin session row for ``user``; return its session key."""
    store = SessionStore()
    store["_auth_user_id"] = str(user.id)
    store.create()
    return store.session_key


def _run(*args: str) -> str:
    out = StringIO()
    call_command("mfa_enforce_cutover", *args, stdout=out)
    return out.getvalue()


def _audited(user: User) -> bool:
    return AuditEntry.unscoped.filter(
        entity_id=user.id,
        entity_type="User",
        op=AuditEntry.OP_USER_MFA_CUTOVER,
    ).exists()


def _enroll(user: User) -> UserTotpDevice:
    """Give ``user`` a confirmed TOTP device (secret content is irrelevant here)."""
    return UserTotpDevice.objects.create(
        user=user, secret_ciphertext="not-a-real-ciphertext", confirmed_at=timezone.now()
    )


class TestCutoverRevokesStaffSessions:
    def test_cutover_revokes_staff_sessions(self, tenant_a) -> None:
        staff = _user(tenant_a, "cut-staff", staff=True)
        other = _user(tenant_a, "cut-other", staff=False)
        staff_row = _refresh_row(staff)
        other_row = _refresh_row(other)
        staff_session = _admin_session(staff)
        other_session = _admin_session(other)

        output = _run()

        staff_row.refresh_from_db()
        other_row.refresh_from_db()
        assert staff_row.revoked_at is not None
        assert staff_row.revoked_reason == "mfa_cutover"
        assert other_row.revoked_at is None, "non-staff family must stay live"
        assert not Session.objects.filter(pk=staff_session).exists()
        assert Session.objects.filter(pk=other_session).exists(), (
            "non-staff admin session must survive"
        )
        assert _audited(staff)
        assert not _audited(other)
        assert "Refresh families revoked: 1" in output
        assert "Django admin sessions deleted: 1" in output


class TestCutoverListsStaffApiKeys:
    def test_cutover_lists_staff_api_keys(self, tenant_a) -> None:
        staff = _user(tenant_a, "cut-key-staff", staff=True)
        other = _user(tenant_a, "cut-key-other", staff=False)
        staff_hash = "sha256p1:" + "a" * 64
        other_hash = "sha256p1:" + "b" * 64
        ApiKey.unscoped.create(
            tenant=tenant_a, user=staff, name="staff-agent-key", key_hash=staff_hash
        )
        ApiKey.unscoped.create(
            tenant=tenant_a, user=other, name="other-agent-key", key_hash=other_hash
        )

        output = _run()

        assert "staff-agent-key" in output
        assert "other-agent-key" not in output
        # Secret discipline: neither the hash nor any meaningful fragment of it
        # may reach the report.
        assert staff_hash not in output
        assert staff_hash[-16:] not in output
        assert "sha256p1" not in output
        assert ApiKey.unscoped.get(key_hash=staff_hash).revoked_at is None, (
            "ENT-E8 = A: the cutover inventories staff keys, it does not revoke them"
        )


class TestCutoverDryRun:
    def test_cutover_dry_run_changes_nothing(self, tenant_a) -> None:
        staff = _user(tenant_a, "cut-dry", staff=True)
        row = _refresh_row(staff)
        session_key = _admin_session(staff)
        key = ApiKey.unscoped.create(
            tenant=tenant_a,
            user=staff,
            name="dry-run-key",
            key_hash="sha256p1:" + "c" * 64,
        )

        output = _run("--dry-run")

        row.refresh_from_db()
        key.refresh_from_db()
        assert row.revoked_at is None
        assert key.revoked_at is None
        assert Session.objects.filter(pk=session_key).exists()
        assert not _audited(staff)
        assert "DRY RUN" in output
        assert "would be revoked" in output
        assert "would be deleted" in output


class TestCutoverTenantContext:
    def test_cutover_restores_tenant_context(self, tenant_a, tenant_b) -> None:
        staff = _user(tenant_a, "cut-context", staff=True)
        row = _refresh_row(staff)

        set_request_tenant(tenant_b.id)
        try:
            assert TenantContext.get_tenant() == tenant_b.id
            _run()
            assert TenantContext.get_tenant() == tenant_b.id, (
                "the command must restore the previously armed tenant"
            )
        finally:
            clear_request_tenant()

        row.refresh_from_db()
        assert row.revoked_at is not None


class TestCutoverEnrollmentReport:
    def test_reports_enrollment_per_staff(self, tenant_a) -> None:
        enrolled = _user(tenant_a, "enrolled-staff", staff=True)
        _user(tenant_a, "unenrolled-staff", staff=True)
        _enroll(enrolled)

        payload = json.loads(_run("--dry-run", "--format", "json"))
        records = {record["username"]: record for record in payload["staff"]}

        assert records["enrolled-staff"]["mfa_enrolled"] is True
        assert records["enrolled-staff"]["confirmed_at"] is not None
        assert records["unenrolled-staff"]["mfa_enrolled"] is False
        assert records["unenrolled-staff"]["confirmed_at"] is None
        assert payload["unenrolled_staff"] == 1
        assert payload["enforcement"] == "optional"

    @override_settings(MFA_STAFF_ENFORCEMENT="required")
    def test_required_with_unenrolled_staff_is_loud(self, tenant_a) -> None:
        _user(tenant_a, "needs-totp", staff=True)
        _enroll(_user(tenant_a, "has-totp", staff=True))

        payload = json.loads(_run("--dry-run", "--format", "json"))
        warnings = "\n".join(payload["warnings"])

        assert payload["enforcement"] == "required"
        assert payload["unenrolled_staff"] == 1
        assert "needs-totp" in warnings
        assert "has-totp" not in warnings
        assert "needs-totp: NOT ENROLLED" in _run("--dry-run")


class TestCutoverFailureHandling:
    def test_audit_failure_rolls_back_that_users_revocation(self, tenant_a, monkeypatch) -> None:
        staff = _user(tenant_a, "audit-down", staff=True)
        row = _refresh_row(staff)

        def _boom(*args, **kwargs) -> None:
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(Command, "_audit_cutover", staticmethod(_boom))

        with pytest.raises(CommandError):
            _run()

        row.refresh_from_db()
        assert row.revoked_at is None, "the failed audit must roll the revocation back"

    def test_failing_tenant_does_not_stop_the_next(self, tenant_a, tenant_b, monkeypatch) -> None:
        failing = _user(tenant_a, "tenant-a-staff", staff=True)
        succeeding = _user(tenant_b, "tenant-b-staff", staff=True)
        failing_row = _refresh_row(failing)
        succeeding_row = _refresh_row(succeeding)
        original = Command._audit_cutover

        def _selective(user, **kwargs) -> None:
            if user.username == "tenant-a-staff":
                raise RuntimeError("audit down")
            original(user, **kwargs)

        monkeypatch.setattr(Command, "_audit_cutover", staticmethod(_selective))
        out = StringIO()
        with pytest.raises(CommandError) as excinfo:
            call_command("mfa_enforce_cutover", "--format", "json", stdout=out)

        payload = json.loads(out.getvalue())
        failing_row.refresh_from_db()
        succeeding_row.refresh_from_db()
        assert payload["failures"] == [
            {"tenant_slug": "tenant-a", "error": "RuntimeError: audit down"}
        ]
        assert "tenant-a" in str(excinfo.value)
        assert failing_row.revoked_at is None
        assert succeeding_row.revoked_at is not None, "a failed tenant must not stop the next one"

    def test_second_run_does_not_duplicate_audit(self, tenant_a) -> None:
        staff = _user(tenant_a, "rerun", staff=True)
        _refresh_row(staff)

        _run()
        _run()

        assert (
            AuditEntry.unscoped.filter(
                entity_id=staff.id, op=AuditEntry.OP_USER_MFA_CUTOVER
            ).count()
            == 1
        )

    def test_other_tenant_staff_without_sessions_and_non_staff_untouched(
        self, tenant_a, tenant_b
    ) -> None:
        staff_a = _user(tenant_a, "iso-staff-a", staff=True)
        staff_b = _user(tenant_b, "iso-staff-b", staff=True)
        other_b = _user(tenant_b, "iso-other-b", staff=False)
        staff_a_row = _refresh_row(staff_a)
        other_b_row = _refresh_row(other_b)
        other_b_session = _admin_session(other_b)

        _run()

        staff_a_row.refresh_from_db()
        other_b_row.refresh_from_db()
        assert staff_a_row.revoked_at is not None
        assert other_b_row.revoked_at is None
        assert Session.objects.filter(pk=other_b_session).exists()
        assert not _audited(staff_b), "a staff user with no sessions has nothing to cut over"


class TestCutoverOutput:
    def test_cutover_json_format_is_machine_readable(self, tenant_a) -> None:
        _user(tenant_a, "cut-json", staff=True)

        output = _run("--format", "json")
        payload = json.loads(output)

        assert set(payload) >= {
            "dry_run",
            "generated_at",
            "staff_users",
            "refresh_families",
            "refresh_tokens",
            "admin_sessions",
            "audited_users",
            "staff_api_keys",
            "warnings",
        }
        assert payload["dry_run"] is False
        assert payload["staff_users"] == 1
        assert isinstance(payload["staff_api_keys"], list)
        assert payload["warnings"], "the required-before-cutover warning must ship"

    def test_cutover_rejects_unknown_format(self) -> None:
        with pytest.raises(CommandError):
            call_command("mfa_enforce_cutover", "--format", "xml")
