"""RLS regression proof for ``cleanup_revoked_api_keys`` (issues #1184 / R-3, #1136).

The R-3 inventory (``docs/audit/2026-10/1136-r3-unscoped-inventory.md``) named
this command's ``Command.handle`` the one *dangerous* ``ApiKey.unscoped`` reader:
it is CLI maintenance, so it runs with **no tenant context**, and before the fix
it had no ``SET LOCAL row_security = off`` guard. Under an armed staged policy
(``at_api_key_tenant_isolation``, ``auth_tenancy/0022_rls_hard_enforcement_policy``)
its cross-tenant queryset therefore collapsed to zero rows and the command printed
"Deleted 0 revoked API key(s)" with ``--apply`` — a silent no-op reported as
success. That silent-empty behaviour is the regression these tests pin down; it
must never come back.

What is proven here:

* the guarded CLI path (owner/superuser connection) really deletes, is idempotent,
  and never touches active or too-recent keys — the flag being off must not have
  changed the command's job;
* **the RLS-ON proof**: with the least-privilege app role armed (``SET ROLE
  "reqogniloom_app"`` + ``app.rls_preauth_enforced`` / ``app.rls_as_enforced`` on,
  no tenant context — the pattern of ``auth_tenancy/tests/test_preauth_rls_staged.py``)
  the command does **not** silently report "Deleted 0"; it raises, and the row it
  would have deleted is still there afterwards, so there is no half-run;
* *why*: under the same armed app role the plain unguarded
  ``ApiKey.unscoped.filter(revoked_at__isnull=False)`` queryset returns 0 rows.
  That unguarded read is the documented silent-empty mechanism, and it is the
  baseline the guard has to beat — pinned read-only so a future regression cannot
  quietly reintroduce it behind a green suite.

The role-switching pattern exists because the pytest connection is a superuser,
which bypasses Row-Level Security unconditionally; ``SET ROLE`` is what makes the
app-role branch of the guard reachable at all.
"""
from __future__ import annotations

import io
from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from auth_tenancy.models import ApiKey
from persistence.db_roles import APP_DB_ROLE
from persistence.models import Tenant, User

pytestmark = pytest.mark.django_db

_IS_POSTGRES = connection.vendor == "postgresql"
_pg_only = pytest.mark.skipif(not _IS_POSTGRES, reason="RLS proof needs PostgreSQL")


def _arm_app_role() -> None:
    """Least-privilege app role with both staged-enforcement GUCs armed.

    Mirrors ``test_preauth_rls_staged._arm_app_role``: ``SET ROLE`` switches the
    session identity (superuser would otherwise bypass RLS) and the two GUCs arm
    the staged ``at_api_key`` policy. No tenant context is armed — exactly the
    shape of a CLI maintenance connection.
    """
    with connection.cursor() as cursor:
        cursor.execute(f'SET ROLE "{APP_DB_ROLE}"')
        cursor.execute("SET app.rls_preauth_enforced = 'on'")
        cursor.execute("SET app.rls_as_enforced = 'on'")


def _disarm_app_role() -> None:
    with connection.cursor() as cursor:
        cursor.execute("RESET app.current_tenant")
        cursor.execute("RESET app.rls_preauth_enforced")
        cursor.execute("RESET app.rls_as_enforced")
        cursor.execute("RESET ROLE")


def _seed_tenant_and_user(label: str) -> tuple[Tenant, User]:
    """Create a fresh tenant + user (seeded on the superuser test connection)."""
    suffix = uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"cleanup-rls-{label}", slug=f"cleanup-rls-{suffix}", is_active=True
    )
    user = User.objects.create(
        username=f"cleanup-rls-{suffix}",
        email=f"cleanup-rls-{suffix}@a.test",
        tenant=tenant,
    )
    return tenant, user


def _make_key(
    tenant: Tenant,
    user: User,
    *,
    name: str,
    revoked_days_ago: int | None = None,
) -> ApiKey:
    """Create one ``ApiKey`` through the unscoped manager (cross-tenant by design).

    ``revoked_days_ago=None`` creates an *active* key (``revoked_at`` stays NULL),
    which is how the "never a candidate" cases are seeded.
    """
    revoked_at = (
        timezone.now() - timedelta(days=revoked_days_ago)
        if revoked_days_ago is not None
        else None
    )
    return ApiKey.unscoped.create(
        tenant=tenant,
        user=user,
        name=name,
        key_hash="sha256p1:" + uuid4().hex + uuid4().hex,
        revoked_at=revoked_at,
    )


# ---------------------------------------------------------------------------
# The guarded CLI path (owner/superuser connection): the command still works
# ---------------------------------------------------------------------------


def test_apply_deletes_stale_revoked_keys_across_tenants_and_is_idempotent(capsys):
    """``--apply`` deletes the revoked keys older than the cutoff — across
    tenants, because this is cross-tenant maintenance — and a second run is a
    legitimately empty "Deleted 0", not a silently halted one."""
    tenant_a, user_a = _seed_tenant_and_user("apply-a")
    tenant_b, user_b = _seed_tenant_and_user("apply-b")
    stale_a = _make_key(tenant_a, user_a, name="stale-a", revoked_days_ago=60)
    stale_b = _make_key(tenant_b, user_b, name="stale-b", revoked_days_ago=90)

    call_command("cleanup_revoked_api_keys", "--apply", "--older-than-days=30")

    assert "Deleted 2 revoked API key(s)" in capsys.readouterr().out
    assert not ApiKey.unscoped.filter(pk=stale_a.pk).exists()
    assert not ApiKey.unscoped.filter(pk=stale_b.pk).exists()

    call_command("cleanup_revoked_api_keys", "--apply", "--older-than-days=30")

    out = capsys.readouterr().out
    assert "Deleted 0 revoked API key(s)" in out, (
        "the second run must report a genuinely empty result through the same "
        f"guarded read, got: {out!r}"
    )


def test_dry_run_reports_the_count_and_deletes_nothing(capsys):
    """Default (no ``--apply``) stays a report: the count comes from the guarded
    read, and no row is deleted."""
    tenant, user = _seed_tenant_and_user("dry")
    stale = _make_key(tenant, user, name="stale", revoked_days_ago=60)

    call_command("cleanup_revoked_api_keys", "--older-than-days=30")

    out = capsys.readouterr().out
    assert "Dry run: 1 revoked API key(s) older than 30 day(s)" in out
    assert ApiKey.unscoped.filter(pk=stale.pk).exists(), "dry-run must not delete"


def test_active_and_too_recent_keys_are_never_deleted(capsys):
    """Only revoked-and-old rows are candidates: a non-revoked key and a key
    revoked five days ago survive the 30-day threshold."""
    tenant, user = _seed_tenant_and_user("selectivity")
    active = _make_key(tenant, user, name="active", revoked_days_ago=None)
    recent = _make_key(tenant, user, name="recent", revoked_days_ago=5)

    call_command("cleanup_revoked_api_keys", "--apply", "--older-than-days=30")

    assert "Deleted 0 revoked API key(s)" in capsys.readouterr().out
    assert ApiKey.unscoped.filter(pk=active.pk).exists()
    assert ApiKey.unscoped.filter(pk=recent.pk).exists()


# ---------------------------------------------------------------------------
# The RLS-ON proof: the silent-empty regression must not come back
# ---------------------------------------------------------------------------


@_pg_only
@pytest.mark.django_db(transaction=True)
def test_armed_app_role_fails_loud_instead_of_reporting_deleted_zero():
    """[RLS-ON] With the least-privilege app role armed and no tenant context,
    the command must NOT print "Deleted 0 ...".

    This is the R-3 regression the inventory warned about: before the
    ``SET LOCAL row_security = off`` guard, the armed policy emptied the
    unscoped queryset, ``stale.count()`` said 0, ``stale.delete()`` deleted 0
    and the command reported success while doing nothing. The guard turns that
    into a raised error — any exception type counts, the assertion pins the
    stable Postgres message shape and the untouched data.
    """
    tenant, user = _seed_tenant_and_user("rls-on")
    stale = _make_key(tenant, user, name="stale-rls", revoked_days_ago=60)

    _arm_app_role()
    out = io.StringIO()
    try:
        # ``Exception`` on purpose: the signal that counts is "it did not report
        # a false success", and the concrete DB exception class is an
        # implementation detail of the driver stack.
        with pytest.raises(Exception) as excinfo:
            call_command(
                "cleanup_revoked_api_keys", "--apply", "--older-than-days=30",
                stdout=out,
            )
    finally:
        _disarm_app_role()

    message = str(excinfo.value)
    assert message.strip().startswith(
        "query would be affected by row-level security policy"
    ) and '"at_api_key"' in message, (
        "the loud failure is expected to be the RLS error on at_api_key, not an "
        f"unrelated exception: {message!r}"
    )
    assert "Deleted 0" not in out.getvalue(), (
        "the command reported a false success under RLS — the silent-empty "
        "regression from docs/audit/2026-10/1136-r3-unscoped-inventory.md is back"
    )

    # Read back on the disarmed superuser connection: the data is untouched, so
    # the failure happened before the DELETE, not half-way through it.
    assert ApiKey.unscoped.filter(pk=stale.pk).exists(), (
        "the row must survive a failed run — the guard has to abort the command, "
        "not partially apply it"
    )


@_pg_only
@pytest.mark.django_db(transaction=True)
def test_unguarded_unscoped_read_is_the_silent_empty_mechanism():
    """Control [RLS-ON]: under the same armed app role the *unguarded*
    ``ApiKey.unscoped`` read returns 0 rows while the superuser sees the row.

    This pins the baseline the guard exists to break — and it is deliberately
    read-only, so it cannot delete anything. If this stops returning 0 while the
    command above still fails loudly, the policy itself changed and the R-3
    reasoning needs re-review, so both are asserted together.
    """
    tenant, user = _seed_tenant_and_user("control")
    stale = _make_key(tenant, user, name="control-stale", revoked_days_ago=60)

    _arm_app_role()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            current_user = cursor.fetchone()[0]
        assert current_user == APP_DB_ROLE, (
            f"expected the armed session to run as {APP_DB_ROLE}, got "
            f"{current_user} — without SET ROLE a superuser would bypass RLS and "
            "this control would prove nothing"
        )

        blinded = ApiKey.unscoped.filter(revoked_at__isnull=False).count()
        blinded_exists = ApiKey.unscoped.filter(pk=stale.pk).exists()
    finally:
        _disarm_app_role()

    assert blinded == 0, (
        f"the armed app role saw {blinded} revoked key(s); the unguarded read is "
        "supposed to be the silent-empty mechanism the guard replaces"
    )
    assert blinded_exists is False, "the armed app role must not see the row"
    assert ApiKey.unscoped.filter(pk=stale.pk).exists(), (
        "the row must still be visible on the disarmed superuser connection"
    )
