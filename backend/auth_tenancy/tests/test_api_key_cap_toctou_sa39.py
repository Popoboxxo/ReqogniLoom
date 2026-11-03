"""SA-39 regression: the API-key cap must not be a TOCTOU window.

Systemaudit 2026-08-27 §4.1 #11. ``AuthenticationService.create_api_key``
counted the user's active keys and then created a new one with nothing in
between — N parallel requests all read ``max_active - 1`` and all proceed, so
the cap is exceeded by exactly the concurrency. Rated cosmetic in the audit, but
the cap exists to bound credential sprawl per identity, so "exceeded under
concurrency" is the one condition it was written for.

The fix serialises on the owning ``User`` row. That choice is load-bearing:
locking the existing ``ApiKey`` rows would lock nothing when the user has none
yet — precisely the case where two requests could both create the first key.

Concurrency is exercised with two real threads and real connections, so the test
observes the database's behaviour rather than a mocked interleaving.

req_id : REQ-L3-AT001-003
"""
from __future__ import annotations

import threading

import pytest
from django.db import connection, connections

from auth_tenancy.models import ApiKey
from auth_tenancy.services.authentication import AuthenticationService

pytestmark = pytest.mark.django_db(transaction=True)

_IS_POSTGRES = connection.vendor == "postgresql"


def _service() -> AuthenticationService:
    return AuthenticationService(
        jwt_secret="test-secret", jwt_issuer="test", jwt_audience="test"
    )


def test_cap_still_enforced_sequentially(user_a, settings) -> None:
    """Baseline: the lock must not change the single-threaded contract."""
    settings.MAX_ACTIVE_API_KEYS_PER_USER = 2
    svc = _service()
    svc.create_api_key(user_id=user_a.id, tenant_id=user_a.tenant_id, name="k1")
    svc.create_api_key(user_id=user_a.id, tenant_id=user_a.tenant_id, name="k2")
    with pytest.raises(ValueError, match="maximum of 2"):
        svc.create_api_key(user_id=user_a.id, tenant_id=user_a.tenant_id, name="k3")


@pytest.mark.skipif(not _IS_POSTGRES, reason="row locking is PostgreSQL-specific")
def test_concurrent_creates_cannot_exceed_the_cap(user_a, settings) -> None:
    """Two simultaneous creates at ``max - 1`` must yield exactly one new key.

    Before the fix both threads read the same count, both passed the check and
    both inserted, leaving the user one key over the cap.
    """
    settings.MAX_ACTIVE_API_KEYS_PER_USER = 2
    svc = _service()
    svc.create_api_key(user_id=user_a.id, tenant_id=user_a.tenant_id, name="existing")

    both_ready = threading.Barrier(2, timeout=10)
    outcomes: list[object] = []
    outcomes_lock = threading.Lock()

    def _create(name: str) -> None:
        try:
            # Release both threads into the critical section together, so the
            # count-then-create windows genuinely overlap.
            both_ready.wait()
            result = _service().create_api_key(
                user_id=user_a.id, tenant_id=user_a.tenant_id, name=name
            )
            with outcomes_lock:
                outcomes.append(result)
        except Exception as exc:  # noqa: BLE001 - recorded and asserted below
            with outcomes_lock:
                outcomes.append(exc)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=_create, args=(f"race-{i}",)) for i in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive(), (
            "a create_api_key thread deadlocked — the user-row lock is held too long"
        )

    active_keys = ApiKey.unscoped.filter(
        user_id=user_a.id, revoked_at__isnull=True
    ).count()
    assert active_keys == 2, (
        f"SA-39: the cap (2) was exceeded under concurrency — {active_keys} "
        "active keys exist, so count-then-create is still racing"
    )

    successes = [o for o in outcomes if not isinstance(o, Exception)]
    rejections = [o for o in outcomes if isinstance(o, ValueError)]
    unexpected = [
        o for o in outcomes if isinstance(o, Exception) and not isinstance(o, ValueError)
    ]
    assert not unexpected, f"unexpected error from a racing create: {unexpected}"
    assert len(successes) == 1, "exactly one of the two creates must win"
    assert len(rejections) == 1, (
        "the loser must be rejected with the documented ValueError, not a 500"
    )
