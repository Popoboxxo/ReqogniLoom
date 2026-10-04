"""DB-backed admin brute-force lockout tests (issue #1135).

Covers the acceptance criteria for the custom lockout on ``/admin/login/``:

* N failed admin logins lock the ``(client IP, username)`` pair and further
  attempts are rejected with a clear message;
* a blocked attempt while locked cannot authenticate;
* expiry lifts the lock (time travelled via ``monkeypatch`` on the service
  ``_now`` — ``freezegun`` is not a project dependency);
* a successful admin login resets the counter;
* the REST ``/auth/login/`` throttle is UNCHANGED in both directions
  (repeated REST failures create no admin lockout rows; an admin lockout does
  not change REST throttle behaviour);
* different ``(IP, username)`` pairs are isolated.

IP resolution note: the tests drive ``REMOTE_ADDR`` through Django's test
``Client``. The lockout keys on ``REMOTE_ADDR`` by design — a DELIBERATE
anti-spoofing deviation from DRF's ``SimpleRateThrottle.get_ident``, which trusts
the client-controlled left-most ``X-Forwarded-For`` entry when ``NUM_PROXIES`` is
unset. ``X-Forwarded-For`` is honored ONLY when ``NUM_PROXIES`` is configured,
and every candidate is validated with ``ipaddress.ip_address`` before it reaches
the PostgreSQL ``inet`` column. The IP-resolution tests below pin both halves:
XFF is ignored without ``NUM_PROXIES`` and honored with it.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_login_failed, user_logged_in
from django.test import Client, override_settings

from auth_tenancy import admin_lockout
from auth_tenancy.admin_login import (
    LOCKOUT_MESSAGE,
    LockoutAdminAuthenticationForm,
    _is_admin_login_request,
    _on_user_login_failed,
    _on_user_logged_in,
)
from auth_tenancy.models import AdminLoginLockout
from persistence.models import Tenant

User = get_user_model()

pytestmark = pytest.mark.django_db

_ADMIN_LOGIN_URL = "/admin/login/"
_IP = "10.113.5.1"
_IP_B = "10.113.5.2"
_PASSWORD = "staffpass123"
_USERNAME = "lockoutadmin"


@pytest.fixture
def staff_user(db) -> User:
    """An active staff+superuser for admin login tests."""
    tenant = Tenant.objects.create(name="Lockout T", slug="lockout-t", is_active=True)
    user = User.objects.create(
        username=_USERNAME,
        email="lockout@admin.test",
        tenant=tenant,
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )
    user.set_password(_PASSWORD)
    user.save(update_fields=["password"])
    return user


def _admin_post(
    *,
    username: str = _USERNAME,
    password: str,
    ip: str = _IP,
    next_url: str = "/admin/",
):
    """POST to the admin login URL from a given client IP (REMOTE_ADDR)."""
    client = Client(REMOTE_ADDR=ip)
    return client.post(
        _ADMIN_LOGIN_URL + f"?next={next_url}",
        {"username": username, "password": password},
    )


def _admin_lockout_row(ip: str = _IP, username: str = _USERNAME) -> AdminLoginLockout | None:
    return AdminLoginLockout.objects.filter(
        client_ip=ip, username_digest=admin_lockout.username_digest(username)
    ).first()


# ---------------------------------------------------------------------------
# a) threshold -> lock, next attempt blocked
# ---------------------------------------------------------------------------


def test_repeated_admin_failures_lock_the_pair(staff_user: User) -> None:
    """Threshold failed admin logins lock (IP, username); next attempt is blocked."""
    threshold = 5
    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=threshold):
        for _ in range(threshold):
            response = _admin_post(password="wrong")
            assert response.status_code == 200  # re-rendered form, not yet blocked

        row = _admin_lockout_row()
        assert row is not None
        assert row.failure_count == threshold
        assert row.locked_until is not None

        blocked = _admin_post(password="wrong")
        assert blocked.status_code == 200
        # Clear message rendered on the page.
        assert b"temporarily locked" in blocked.content

    # The lockout message is a constant and must never contain the username:
    # assert on the constant directly rather than slicing rendered HTML (the
    # admin form legitimately re-populates the username input on redisplay).
    assert _USERNAME not in LOCKOUT_MESSAGE
    assert "lockoutadmin" not in LOCKOUT_MESSAGE


def test_blocked_attempt_does_not_authenticate(staff_user: User) -> None:
    """While locked, even the CORRECT password is refused (pre-auth gate)."""
    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=3):
        for _ in range(3):
            _admin_post(password="wrong")

        assert admin_lockout.is_locked(_IP, _USERNAME)

        response = _admin_post(password=_PASSWORD)
        # Not a 302 redirect to /admin/ -> the session was never established.
        assert response.status_code == 200
        assert b"temporarily locked" in response.content


# ---------------------------------------------------------------------------
# b) the pre-auth gate is scoped and does not leak
# ---------------------------------------------------------------------------


def test_lockout_does_not_store_raw_username(staff_user: User) -> None:
    """The table stores only a digest; the raw username never lands in a row."""
    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=2):
        _admin_post(password="wrong")
        _admin_post(password="wrong")

    row = _admin_lockout_row()
    assert row is not None
    assert row.username_digest != _USERNAME
    assert len(row.username_digest) == 32
    assert row.username_digest == admin_lockout.username_digest(_USERNAME)
    assert not AdminLoginLockout.objects.filter(username_digest=_USERNAME).exists()


# ---------------------------------------------------------------------------
# c) expiry lifts the lock
# ---------------------------------------------------------------------------


def test_expiry_lifts_the_lock(staff_user: User, monkeypatch) -> None:
    """Advancing time past the cool-down unlocks the pair."""
    clock = {"now": admin_lockout._now()}

    def fake_now():
        return clock["now"]

    monkeypatch.setattr(admin_lockout, "_now", fake_now)

    with override_settings(
        ADMIN_LOGIN_LOCKOUT_THRESHOLD=2,
        ADMIN_LOGIN_LOCKOUT_WINDOW_SECONDS=900,
        ADMIN_LOGIN_LOCKOUT_DURATION_SECONDS=900,
    ):
        _admin_post(password="wrong")
        _admin_post(password="wrong")
        assert admin_lockout.is_locked(_IP, _USERNAME)

        # Travel beyond the cool-down.
        clock["now"] = clock["now"] + timedelta(seconds=901)

        assert not admin_lockout.is_locked(_IP, _USERNAME)

        # A correct-password login is now allowed again.
        response = _admin_post(password=_PASSWORD)
        assert response.status_code == 302


def test_window_expiry_restarts_the_streak(staff_user: User, monkeypatch) -> None:
    """Failures older than the window do not count toward the threshold."""
    clock = {"now": admin_lockout._now()}
    monkeypatch.setattr(admin_lockout, "_now", lambda: clock["now"])

    with override_settings(
        ADMIN_LOGIN_LOCKOUT_THRESHOLD=3,
        ADMIN_LOGIN_LOCKOUT_WINDOW_SECONDS=900,
    ):
        _admin_post(password="wrong")  # count 1
        clock["now"] = clock["now"] + timedelta(seconds=901)
        _admin_post(password="wrong")  # window elapsed -> count restarts at 1

        row = _admin_lockout_row()
        assert row is not None
        assert row.failure_count == 1
        assert row.locked_until is None


# ---------------------------------------------------------------------------
# d) successful login resets the counter
# ---------------------------------------------------------------------------


def test_success_resets_the_counter(staff_user: User) -> None:
    """A correct admin login clears the failure streak."""
    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=4):
        for _ in range(3):
            _admin_post(password="wrong")
        assert _admin_lockout_row().failure_count == 3
        # NF1: ``version`` is a real optimistic-concurrency counter, so it must
        # be incremented on each write, not written as a no-op.
        assert _admin_lockout_row().version > 1

        ok = _admin_post(password=_PASSWORD)
        assert ok.status_code == 302

        assert _admin_lockout_row() is None
        assert not admin_lockout.is_locked(_IP, _USERNAME)


# ---------------------------------------------------------------------------
# e) REST /auth/login/ is untouched (both directions)
# ---------------------------------------------------------------------------


def test_rest_login_does_not_increment_admin_lockout(staff_user: User) -> None:
    """Repeated REST failures create/increment NO admin lockout rows."""
    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=1):
        rest_client = Client(REMOTE_ADDR=_IP)
        for _ in range(6):
            rest = rest_client.post(
                "/api/v1/auth/login/",
                {"username": _USERNAME, "password": "wrong"},
            )
            assert rest.status_code == 401

        # A threshold of 1 would have locked after the very first failure if the
        # REST path fed this table.
        assert AdminLoginLockout.objects.count() == 0
        assert not admin_lockout.is_locked(_IP, _USERNAME)


def test_admin_lockout_does_not_change_rest_behaviour(staff_user: User) -> None:
    """An admin lockout does not alter the REST login response."""
    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=2):
        for _ in range(2):
            _admin_post(password="wrong")
        assert admin_lockout.is_locked(_IP, _USERNAME)

        # The REST endpoint on the SAME IP is unaffected: still 401 for wrong
        # credentials (not 429/locked), because the admin lockout is a separate
        # mechanism, not wired into the REST throttle.
        rest = Client(REMOTE_ADDR=_IP).post(
            "/api/v1/auth/login/",
            {"username": _USERNAME, "password": "wrong"},
        )
        assert rest.status_code == 401


def test_admin_login_signals_are_path_scoped() -> None:
    """The signal gate accepts only the admin login POST, nothing else."""
    from django.test import RequestFactory

    rf = RequestFactory()
    assert _is_admin_login_request(rf.post(_ADMIN_LOGIN_URL)) is True
    # GET only renders the form -> not a failure event.
    assert _is_admin_login_request(rf.get(_ADMIN_LOGIN_URL)) is False
    # The REST login path is explicitly excluded.
    assert _is_admin_login_request(rf.post("/api/v1/auth/login/")) is False
    # A different admin route is not the login view.
    assert _is_admin_login_request(rf.post("/admin/")) is False
    # No request at all (defensive).
    assert _is_admin_login_request(None) is False


# ---------------------------------------------------------------------------
# f) pair isolation
# ---------------------------------------------------------------------------


def test_different_pairs_are_isolated(staff_user: User) -> None:
    """Locking one (IP, username) pair leaves other pairs untouched."""
    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=2):
        _admin_post(password="wrong", ip=_IP)
        _admin_post(password="wrong", ip=_IP)
        assert admin_lockout.is_locked(_IP, _USERNAME)

        # Different IP, same username: not locked.
        assert not admin_lockout.is_locked(_IP_B, _USERNAME)
        # Same IP, different username: not locked.
        assert not admin_lockout.is_locked(_IP, "someoneelse")

        # A login from the other IP with correct credentials still works.
        response = _admin_post(password=_PASSWORD, ip=_IP_B)
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# F1 — concurrency: the create race is absorbed, not raised
# ---------------------------------------------------------------------------


def test_create_race_is_absorbed_instead_of_raising(monkeypatch) -> None:
    """A lost INSERT race adopts the winner's row; no IntegrityError, no lost count.

    Mirrors ``resilience/tests/test_circuit_breaker_sa18.py:
    test_create_race_is_absorbed_instead_of_raising``. Reproduces the interleaving
    without threads: a rival worker's row is already committed, but this caller's
    *first* ``select_for_update`` is forced to miss it — exactly what happens when
    the rival commits between the SELECT and the INSERT. The INSERT then hits
    ``uq_admin_lockout_ip_user``; ``register_failure`` must recover by re-reading.

    Before the F1 fix this raised ``IntegrityError`` out of ``register_failure``
    (Django's ``authenticate()`` sends ``user_login_failed`` without try/except →
    HTTP 500 on the login page and an uncounted attempt).
    """
    from django.utils import timezone

    from auth_tenancy.models import AdminLoginLockout as Model

    rival = Model.objects.create(
        client_ip=_IP,
        username_digest=admin_lockout.username_digest(_USERNAME),
        failure_count=0,
        first_failure_at=timezone.now(),
        last_failure_at=timezone.now(),
        locked_until=None,
    )

    real_select_locked = admin_lockout._select_locked
    lookups: list[int] = []

    def _miss_once(client_ip, digest):
        lookups.append(1)
        if len(lookups) == 1:
            return None  # rival's row not visible to us yet
        return real_select_locked(client_ip, digest)

    monkeypatch.setattr(admin_lockout, "_select_locked", _miss_once)

    # Must not raise.
    admin_lockout.register_failure(_IP, _USERNAME)

    assert len(lookups) >= 2, "the loser must re-read after losing the create race"
    rows = list(Model.objects.filter(client_ip=_IP))
    assert len(rows) == 1, "the race must not leave duplicate lockout rows"
    assert rows[0].pk == rival.pk, "the loser must adopt the winner's row"
    assert rows[0].failure_count == 1, "the failure must still be recorded exactly once"


def test_register_failure_is_fail_open_on_db_error(monkeypatch) -> None:
    """A DB error never turns a login attempt into a 500 (fail-open)."""
    def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(admin_lockout, "_locked_or_create", _boom)

    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=1):
        # Must return False, not raise (an exception would 500 the login page).
        assert admin_lockout.register_failure(_IP, _USERNAME) is False


def test_is_locked_is_fail_open_on_db_error(monkeypatch) -> None:
    """An unreadable lock state lets the attempt proceed, never 500s."""
    def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(AdminLoginLockout.objects, "filter", _boom)

    assert admin_lockout.is_locked(_IP, _USERNAME) is False


# ---------------------------------------------------------------------------
# F4 — expired lock then a new failure clears locked_until
# ---------------------------------------------------------------------------


def test_expired_lock_then_restart_clears_locked_until(monkeypatch) -> None:
    """fail -> lock -> travel past expiry -> fail again => locked_until is None.

    Preserves the model invariant "NULL while unlocked": the restart branch must
    clear the stale lock, otherwise ``__str__`` reports "locked" for an unlocked
    row and a later increment could inherit it.
    """
    from django.utils import timezone

    clock = {"now": admin_lockout._now()}
    monkeypatch.setattr(admin_lockout, "_now", lambda: clock["now"])

    with override_settings(
        ADMIN_LOGIN_LOCKOUT_THRESHOLD=2,
        ADMIN_LOGIN_LOCKOUT_WINDOW_SECONDS=900,
        ADMIN_LOGIN_LOCKOUT_DURATION_SECONDS=900,
    ):
        admin_lockout.register_failure(_IP, _USERNAME)
        admin_lockout.register_failure(_IP, _USERNAME)
        assert admin_lockout.is_locked(_IP, _USERNAME)

        # Travel past BOTH the window and the cool-down.
        clock["now"] = clock["now"] + timedelta(seconds=901)

        # A new failure must restart the streak and clear the stale lock.
        admin_lockout.register_failure(_IP, _USERNAME)

        row = _admin_lockout_row()
        assert row is not None
        assert row.failure_count == 1
        assert row.locked_until is None, (
            "an unlocked row must not keep a stale locked_until (invariant)"
        )
        assert "counting" in str(row)
        assert not admin_lockout.is_locked(_IP, _USERNAME)


def test_window_is_anchored_on_first_failure_not_last(monkeypatch) -> None:
    """A slow trickle of attempts cannot extend the window indefinitely (F5)."""
    clock = {"now": admin_lockout._now()}
    monkeypatch.setattr(admin_lockout, "_now", lambda: clock["now"])

    with override_settings(
        ADMIN_LOGIN_LOCKOUT_THRESHOLD=100,
        ADMIN_LOGIN_LOCKOUT_WINDOW_SECONDS=100,
    ):
        admin_lockout.register_failure(_IP, _USERNAME)  # first_failure_at = t0
        # Two more failures 60 s apart each, still inside the 100 s window.
        clock["now"] = clock["now"] + timedelta(seconds=60)
        admin_lockout.register_failure(_IP, _USERNAME)  # count 2
        clock["now"] = clock["now"] + timedelta(seconds=60)  # t0 + 120 > window
        admin_lockout.register_failure(_IP, _USERNAME)

        row = _admin_lockout_row()
        assert row is not None
        # The window is anchored on first_failure_at (t0), so the third failure at
        # t0+120 is a NEW burst -> count restarts at 1. Anchoring on
        # last_failure_at would have made it count 3.
        assert row.failure_count == 1


# ---------------------------------------------------------------------------
# F10 — enable/disable short-circuit, signal dispatch idempotency, IP resolution
# ---------------------------------------------------------------------------


def test_disabled_feature_short_circuits(staff_user: User) -> None:
    """ADMIN_LOGIN_LOCKOUT_ENABLED=False disables counting and blocking entirely."""
    with override_settings(ADMIN_LOGIN_LOCKOUT_ENABLED=False, ADMIN_LOGIN_LOCKOUT_THRESHOLD=1):
        for _ in range(4):
            _admin_post(password="wrong")
        # No rows written, no lock.
        assert AdminLoginLockout.objects.count() == 0
        assert not admin_lockout.is_locked(_IP, _USERNAME)

        # Even correct credentials just work (302 redirect).
        response = _admin_post(password=_PASSWORD)
        assert response.status_code == 302


def test_signal_receivers_resolve_and_are_idempotent(staff_user: User) -> None:
    """Connecting the receivers twice must not double-count (dispatch_uid)."""
    from django.test import RequestFactory

    from auth_tenancy.admin_login import install

    install()  # idempotent: a second ready() must be a no-op

    rf = RequestFactory()
    request = rf.post(
        _ADMIN_LOGIN_URL,
        {"username": _USERNAME, "password": "wrong"},
        REMOTE_ADDR=_IP,
    )

    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=100):
        _on_user_login_failed(
            sender=None, credentials={"username": _USERNAME}, request=request
        )
        row = _admin_lockout_row()
        assert row is not None and row.failure_count == 1

        # The success handler resets.
        _on_user_logged_in(sender=None, request=request, user=staff_user)
        assert _admin_lockout_row() is None

    # A REST-path request is ignored by both receivers.
    rest_request = rf.post(
        "/api/v1/auth/login/", {"username": _USERNAME}, REMOTE_ADDR=_IP
    )
    _on_user_login_failed(
        sender=None, credentials={"username": _USERNAME}, request=rest_request
    )
    assert AdminLoginLockout.objects.count() == 0


def test_signal_receivers_are_connected(staff_user: User) -> None:
    """The auth signals actually reach our receivers (guards dispatch_uid drift)."""
    from django.test import RequestFactory

    from auth_tenancy.admin_login import install

    install()
    rf = RequestFactory()
    request = rf.post(
        _ADMIN_LOGIN_URL,
        {"username": _USERNAME, "password": "wrong"},
        REMOTE_ADDR=_IP,
    )

    with override_settings(ADMIN_LOGIN_LOCKOUT_THRESHOLD=100):
        user_login_failed.send(
            sender=None, credentials={"username": _USERNAME}, request=request
        )
        assert _admin_lockout_row() is not None

        user_logged_in.send(sender=None, request=request, user=staff_user)
        assert _admin_lockout_row() is None


def test_resolve_client_ip_uses_remote_addr_and_ignores_xff_by_default() -> None:
    """X-Forwarded-For is attacker-controlled and ignored when NUM_PROXIES is unset."""
    from django.test import RequestFactory

    rf = RequestFactory()
    request = rf.post(
        _ADMIN_LOGIN_URL,
        REMOTE_ADDR="10.1.2.3",
        HTTP_X_FORWARDED_FOR="203.0.113.99",
    )
    with override_settings(REST_FRAMEWORK={"NUM_PROXIES": None}):
        assert admin_lockout.resolve_client_ip(request) == "10.1.2.3"


def test_resolve_client_ip_honors_xff_with_num_proxies() -> None:
    """With NUM_PROXIES configured, the trusted XFF hop is used (and validated)."""
    from django.test import RequestFactory

    rf = RequestFactory()
    request = rf.post(
        _ADMIN_LOGIN_URL,
        REMOTE_ADDR="10.0.0.1",
        HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
    )
    with override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1}):
        assert admin_lockout.resolve_client_ip(request) == "10.0.0.1"
    with override_settings(REST_FRAMEWORK={"NUM_PROXIES": 2}):
        assert admin_lockout.resolve_client_ip(request) == "203.0.113.7"


def test_resolve_client_ip_rejects_non_ip_xff() -> None:
    """A non-IP XFF token must never reach the inet column (fall back to REMOTE_ADDR)."""
    from django.test import RequestFactory

    rf = RequestFactory()
    request = rf.post(
        _ADMIN_LOGIN_URL,
        REMOTE_ADDR="10.1.2.3",
        HTTP_X_FORWARDED_FOR="not-an-ip",
    )
    with override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1}):
        assert admin_lockout.resolve_client_ip(request) == "10.1.2.3"


def test_resolve_client_ip_rejects_ipv6_scope_id() -> None:
    """NEW-1: an IPv6 scope ID is accepted by ipaddress but REJECTED by inet.

    Under a configured ``NUM_PROXIES`` an attacker controls the trusted XFF
    element; a scope-ID value would otherwise reach PostgreSQL and raise a
    ``DataError`` that the fail-open handler swallows — silently disabling the
    counter. It must be rejected and the unforgeable ``REMOTE_ADDR`` used instead.
    """
    from django.test import RequestFactory

    rf = RequestFactory()
    request = rf.post(
        _ADMIN_LOGIN_URL,
        REMOTE_ADDR="10.1.2.3",
        HTTP_X_FORWARDED_FOR="fe80::1%eth0",
    )
    with override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1}):
        assert admin_lockout.resolve_client_ip(request) == "10.1.2.3"


def test_scope_id_xff_does_not_disable_the_counter(staff_user: User) -> None:
    """NEW-1 regression: a scope-ID XFF still counts/locks on the fallback IP."""
    with override_settings(
        REST_FRAMEWORK={"NUM_PROXIES": 1},
        ADMIN_LOGIN_LOCKOUT_THRESHOLD=2,
    ):
        client = Client(REMOTE_ADDR=_IP)
        for _ in range(2):
            client.post(
                _ADMIN_LOGIN_URL,
                {"username": _USERNAME, "password": "wrong"},
                HTTP_X_FORWARDED_FOR="fe80::1%eth0",
            )
        # The counter must still have locked the validated REMOTE_ADDR bucket.
        assert admin_lockout.is_locked(_IP, _USERNAME)
        row = _admin_lockout_row()
        assert row is not None and row.failure_count == 2


def test_resolve_client_ip_defaults_when_absent() -> None:
    """A missing REMOTE_ADDR degrades to 0.0.0.0 rather than an empty inet."""
    from django.test import RequestFactory

    request = RequestFactory().post(_ADMIN_LOGIN_URL)
    request.META.pop("REMOTE_ADDR", None)
    assert admin_lockout.resolve_client_ip(request) == "0.0.0.0"


def test_lockout_model_is_not_registered_in_admin() -> None:
    """F13: the lockout model stays OUT of the Django admin.

    Registering it would expose raw lockout state (and pull in admin-scope-sweep
    concerns); there is no operator use case that justifies it.
    """
    from django.contrib import admin as django_admin

    assert AdminLoginLockout not in django_admin.site._registry
