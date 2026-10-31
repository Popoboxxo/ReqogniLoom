"""Schema contract of the TOTP second factor (#1308, Plan E / WP E3.1).

These tests pin the invariants the service layer is allowed to *rely on*, so it
does not have to re-check them on every call:

* one device per user (``OneToOneField``) — TOTP is a second factor, not a
  multi-device registry;
* one recovery-code hash worldwide (``unique``) — the same code can never be
  issued twice;
* deleting a user removes device, recovery codes and grants (``CASCADE``); a
  deleted account must not leave a usable credential behind;
* at most one *unused* enrollment grant per user, enforced by the partial unique
  constraint ``uq_mfa_grant_user_unused`` — the DB backstop behind ENT-E7 = A.

Real database, no mocks: every assertion is made by PostgreSQL, not by
application code. The backward probe runs the migration through the real
``MigrationExecutor`` and addresses targets by migration *name* (never a bare
number), so appending a migration cannot silently retarget it.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from auth_tenancy.models import (
    UserMfaEnrollmentGrant,
    UserRecoveryCode,
    UserTotpDevice,
)
from persistence.models import User

#: Predecessor of ``0032_user_mfa`` — Plan C's backfill, which is the latest
#: ``auth_tenancy`` migration on ``main`` when this one lands.
PRE_TARGET = ("auth_tenancy", "0031_backfill_show_readable_ids")
TARGET = ("auth_tenancy", "0032_user_mfa")

_MFA_TABLES = (
    "at_user_totp_device",
    "at_user_recovery_code",
    "at_user_mfa_enrollment_grant",
)


def _make_staff(username: str, tenant) -> User:
    """Return a staff user (the only kind allowed to hold a device)."""
    return User.objects.create(
        username=username,
        email=f"{username}@mfa.test",
        tenant=tenant,
        is_staff=True,
    )


@pytest.mark.django_db
class TestUserTotpDevice:
    """``at_user_totp_device`` — one row per user."""

    def test_second_device_for_the_same_user_is_rejected(self, tenant_a) -> None:
        """The ``OneToOneField`` makes a second device impossible at the DB level."""
        user = _make_staff("dev-one", tenant_a)
        UserTotpDevice.objects.create(user=user, secret_ciphertext="gAAAA-cipher")

        with transaction.atomic():
            with pytest.raises(IntegrityError):
                UserTotpDevice.objects.create(
                    user=user, secret_ciphertext="gAAAA-other"
                )

    def test_two_users_may_each_have_a_device(self, tenant_a, tenant_b) -> None:
        """The constraint is per user, not global."""
        first = _make_staff("dev-a", tenant_a)
        second = _make_staff("dev-b", tenant_b)
        UserTotpDevice.objects.create(user=first, secret_ciphertext="gAAAA-a")
        UserTotpDevice.objects.create(user=second, secret_ciphertext="gAAAA-b")

        assert UserTotpDevice.objects.count() == 2


@pytest.mark.django_db
class TestUserRecoveryCode:
    """``at_user_recovery_code`` — globally unique hashes."""

    def test_code_hash_is_unique_across_users(self, tenant_a, tenant_b) -> None:
        """Two users can never share a code hash (a global lookup would be unsafe)."""
        first = _make_staff("code-a", tenant_a)
        second = _make_staff("code-b", tenant_b)
        digest = "sha256p1:" + "a" * 64
        UserRecoveryCode.objects.create(user=first, code_hash=digest)

        with transaction.atomic():
            with pytest.raises(IntegrityError):
                UserRecoveryCode.objects.create(user=second, code_hash=digest)

    def test_a_user_may_hold_many_codes(self, tenant_a) -> None:
        """Ten codes per enrollment — the FK is what ties them to the user."""
        user = _make_staff("code-many", tenant_a)
        for index in range(10):
            UserRecoveryCode.objects.create(
                user=user, code_hash=f"sha256p1:{index:064d}"
            )

        assert UserRecoveryCode.objects.filter(user=user).count() == 10


@pytest.mark.django_db
class TestCascadeOnUserDelete:
    """Deleting a user leaves no usable second-factor material behind."""

    def test_device_codes_and_grants_are_all_cascaded(self, tenant_a) -> None:
        user = _make_staff("cascade", tenant_a)
        UserTotpDevice.objects.create(user=user, secret_ciphertext="gAAAA-cipher")
        UserRecoveryCode.objects.create(user=user, code_hash="sha256p1:" + "b" * 64)
        UserMfaEnrollmentGrant.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
            granted_by="test",
            reason="cascade",
        )

        user.delete()

        assert not UserTotpDevice.objects.filter(user_id=user.id).exists()
        assert not UserRecoveryCode.objects.filter(user_id=user.id).exists()
        assert not UserMfaEnrollmentGrant.objects.filter(user_id=user.id).exists()


@pytest.mark.django_db
class TestEnrollmentGrantUniqueness:
    """At most one unused grant per user (``uq_mfa_grant_user_unused``)."""

    @staticmethod
    def _grant(user: User, *, hours: int = 1, used: bool = False):
        now = timezone.now()
        return UserMfaEnrollmentGrant.objects.create(
            user=user,
            expires_at=now + timedelta(hours=hours),
            used_at=now if used else None,
            granted_by="test",
            reason="grant",
        )

    def test_second_unused_grant_for_the_same_user_is_rejected(self, tenant_a) -> None:
        user = _make_staff("grant-one", tenant_a)
        self._grant(user)

        with transaction.atomic():
            with pytest.raises(IntegrityError):
                self._grant(user)

    def test_new_grant_is_allowed_once_the_old_one_is_used(self, tenant_a) -> None:
        """A used grant frees the slot — the service marks older grants used."""
        user = _make_staff("grant-used", tenant_a)
        self._grant(user, used=True)

        fresh = self._grant(user)

        assert UserMfaEnrollmentGrant.objects.filter(user=user).count() == 2
        assert fresh.used_at is None

    def test_many_used_grants_are_allowed_alongside_one_unused(self, tenant_a) -> None:
        """The partial predicate is ``used_at IS NULL``, not merely ``user``.

        Without the ``condition=`` on the constraint this would be a plain unique
        index on ``user`` and the *second* used grant would already collide —
        i.e. history could never be kept. Two used grants plus one unused must
        therefore coexist, while a second *unused* one still fails.
        """
        user = _make_staff("grant-history", tenant_a)
        self._grant(user, used=True)
        self._grant(user, used=True)
        unused = self._grant(user)

        assert UserMfaEnrollmentGrant.objects.filter(user=user).count() == 3
        assert (
            UserMfaEnrollmentGrant.objects.filter(
                user=user, used_at__isnull=True
            ).count()
            == 1
        )
        assert unused.used_at is None

        with transaction.atomic():
            with pytest.raises(IntegrityError):
                self._grant(user)

    def test_expired_but_unused_grant_still_occupies_the_slot(self, tenant_a) -> None:
        """Documents WHY ``grant_enrollment`` marks expired grants used.

        The partial index is on ``used_at`` alone (a ``now()`` predicate is not
        expressible in a partial index), so an expired-but-unused grant still
        blocks a second one. That is exactly the state the service clears before
        issuing a new grant — this test is the reason that step cannot be
        dropped.
        """
        user = _make_staff("grant-expired", tenant_a)
        self._grant(user, hours=-1)

        with transaction.atomic():
            with pytest.raises(IntegrityError):
                self._grant(user)


class TestNotRegisteredInAdmin:
    """The three credential tables stay OUT of the Django admin (#1135 precedent).

    ``AdminLoginLockout`` is deliberately unregistered for the same reason
    (``test_admin_login_lockout.py::test_lockout_model_is_not_registered_in_admin``):
    the admin's change form is a plain ``ModelForm``, so it would render the raw
    ``secret_ciphertext``/``code_hash`` columns and — worse — allow a hand-typed
    secret that no authenticator app ever minted, while bypassing every rule in
    ``MfaService`` (no audit entry, no recovery-code regeneration, no
    confirmation step). All TOTP state is changed through the service (or
    ``manage.py mfa_reset``), never through a generic admin form.
    """

    @pytest.mark.parametrize(
        "model",
        [UserTotpDevice, UserRecoveryCode, UserMfaEnrollmentGrant],
        ids=["totp-device", "recovery-code", "enrollment-grant"],
    )
    def test_model_is_not_registered(self, model) -> None:
        from django.contrib import admin as django_admin

        assert model not in django_admin.site._registry


@pytest.mark.django_db(transaction=True)
class TestMigrationBackwardProbe:
    """``0032_user_mfa`` reverses cleanly and re-applies (expand-only).

    F2: the probe migrates down to :data:`PRE_TARGET` and back up to
    ``loader.graph.leaf_nodes()``, so a *future* ``auth_tenancy`` migration that
    lands after this one is reversed and re-applied as a side effect of running
    this test. Today that is harmless (this is the app leaf, and the assertions
    below only name the three MFA tables), but a later migration with an
    irreversible or expensive reverse step would make this test the first place
    that hurts.
    """

    @staticmethod
    def _latest():
        return MigrationExecutor(connection).loader.graph.leaf_nodes()

    def test_backward_drops_the_three_tables_and_forward_recreates_them(self) -> None:
        latest = self._latest()
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([PRE_TARGET])
            executor.loader.build_graph()

            rolled_back = set(connection.introspection.table_names())
            assert not (_MFA_TABLES[0] in rolled_back), "at_user_totp_device still exists"
            assert not (_MFA_TABLES[1] in rolled_back)
            assert not (_MFA_TABLES[2] in rolled_back)

            executor = MigrationExecutor(connection)
            executor.migrate([TARGET])
            executor.loader.build_graph()

            restored = set(connection.introspection.table_names())
            for table in _MFA_TABLES:
                assert table in restored, f"{table} was not recreated"
        finally:
            MigrationExecutor(connection).migrate(latest)
