"""Tests for the ADR-014 §3 Idempotency-Key replay store.

Covers claim/replay/conflict/abort/TTL semantics directly against the DB store
(the REST-level replay is covered in ``rest_api/tests/test_reqif_import.py``).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from application.import_idempotency import (
    CODE_IN_FLIGHT,
    CODE_KEY_REUSED,
    IN_FLIGHT_STALE_SECONDS,
    IdempotencyConflict,
    abort,
    begin,
    compute_fingerprint,
    finalize_success,
    purge_expired,
)
from application.models import ImportIdempotencyRecord

pytestmark = pytest.mark.django_db

_TENANT = uuid.uuid4()
_USER = uuid.uuid4()
_ENDPOINT = "workspace-reqif-import"


def _fingerprint(payload: bytes = b"body") -> str:
    return compute_fingerprint(method="POST", path="/x/", payload=payload)


def _begin(key: str, fingerprint: str, *, tenant=None, user=None):
    return begin(
        tenant_id=tenant or _TENANT,
        user_id=user or _USER,
        endpoint=_ENDPOINT,
        key=key,
        fingerprint=fingerprint,
    )


def test_first_request_claims_and_second_in_flight_conflicts():
    fp = _fingerprint()
    assert _begin("k1", fp) is None

    with pytest.raises(IdempotencyConflict) as exc:
        _begin("k1", fp)

    assert exc.value.code == CODE_IN_FLIGHT
    assert exc.value.retry_after and exc.value.retry_after > 0


def test_finalize_success_then_replay_returns_cached_result():
    fp = _fingerprint()
    _begin("k2", fp)
    finalize_success(
        tenant_id=_TENANT,
        user_id=_USER,
        endpoint=_ENDPOINT,
        key="k2",
        fingerprint=fp,
        status_code=200,
        body={"success": True},
    )

    cached = _begin("k2", fp)

    assert cached is not None
    assert cached.status_code == 200
    assert cached.body == {"success": True}


def test_same_key_different_payload_conflicts_with_key_reused():
    fp = _fingerprint(b"one")
    _begin("k3", fp)
    finalize_success(
        tenant_id=_TENANT,
        user_id=_USER,
        endpoint=_ENDPOINT,
        key="k3",
        fingerprint=fp,
        status_code=200,
        body={"success": True},
    )

    with pytest.raises(IdempotencyConflict) as exc:
        _begin("k3", _fingerprint(b"two"))

    assert exc.value.code == CODE_KEY_REUSED


def test_abort_removes_claim_so_retry_runs():
    fp = _fingerprint()
    _begin("k4", fp)
    abort(tenant_id=_TENANT, user_id=_USER, endpoint=_ENDPOINT, key="k4")

    assert not ImportIdempotencyRecord.objects.filter(key="k4").exists()
    # A retry claims from scratch.
    assert _begin("k4", fp) is None


def test_failed_run_is_not_replayable_after_abort():
    fp = _fingerprint()
    _begin("k5", fp)
    abort(tenant_id=_TENANT, user_id=_USER, endpoint=_ENDPOINT, key="k5")

    # Same key + same payload after a failure must run again, not replay.
    assert _begin("k5", fp) is None


def test_stale_in_flight_claim_is_taken_over():
    fp = _fingerprint()
    _begin("k6", fp)
    record = ImportIdempotencyRecord.objects.get(key="k6")
    record.claimed_at = timezone.now() - timedelta(
        seconds=IN_FLIGHT_STALE_SECONDS + 5
    )
    record.save(update_fields=["claimed_at"])

    # Not a conflict: the crashed worker's claim is reclaimable.
    assert _begin("k6", fp) is None


def test_purge_expired_deletes_only_expired_records():
    _begin("k7", _fingerprint())
    _begin("k8", _fingerprint())
    ImportIdempotencyRecord.objects.filter(key="k7").update(
        expires_at=timezone.now() - timedelta(hours=1)
    )

    assert purge_expired() == 1
    assert not ImportIdempotencyRecord.objects.filter(key="k7").exists()
    assert ImportIdempotencyRecord.objects.filter(key="k8").exists()


def test_key_is_scoped_per_tenant_and_user():
    fp = _fingerprint()
    assert _begin("same", fp) is None
    # A different tenant/user is an independent key: no cross-scope replay.
    assert _begin("same", fp, tenant=uuid.uuid4()) is None
    assert _begin("same", fp, user=uuid.uuid4()) is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_create_race_returns_conflict_not_500(monkeypatch):
    """F1: a peer that wins the INSERT race must yield 409, not an aborted
    transaction.

    The peer row is committed *before* ``begin`` runs; the initial
    ``select_for_update`` is forced to miss it so execution reaches the INSERT,
    which hits the unique constraint. With the INSERT in its own savepoint the
    failed statement is rolled back, the re-select reads the peer row and the
    in-flight conflict is raised. Without the savepoint the re-select runs on
    an aborted PostgreSQL transaction and raises an unhandled DatabaseError.
    """
    fp = _fingerprint()
    # Committed peer claim (transaction=True => autocommit, not rolled back).
    ImportIdempotencyRecord.objects.create(
        tenant_id=_TENANT,
        user_id=_USER,
        endpoint=_ENDPOINT,
        key="race",
        request_fingerprint=fp,
        state="in_flight",
        claimed_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    real_select_for_update = ImportIdempotencyRecord.objects.select_for_update
    calls = {"n": 0}

    def flaky_select_for_update(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            # Pretend the row was not visible before the peer's commit.
            return ImportIdempotencyRecord.objects.none()
        return real_select_for_update(*args, **kwargs)

    monkeypatch.setattr(
        ImportIdempotencyRecord.objects,
        "select_for_update",
        flaky_select_for_update,
    )

    with pytest.raises(IdempotencyConflict) as exc:
        _begin("race", fp)

    assert exc.value.code == CODE_IN_FLIGHT
    assert exc.value.retry_after is not None


def test_begin_keeps_tenant_store_bounded_by_the_limit(settings):
    """F2 (ADR-014 §3/§7): a tenant's key store never exceeds its cap.

    Admitting a key past the cap evicts the soonest-expiring one, so the store
    stays bounded without refusing an otherwise working tenant.
    """
    settings.IMPORT_IDEMPOTENCY_MAX_KEYS_PER_TENANT = 2
    assert _begin("cap-1", _fingerprint(b"1")) is None
    assert _begin("cap-2", _fingerprint(b"2")) is None

    # A third distinct key is admitted; the store does not grow past the cap.
    assert _begin("cap-3", _fingerprint(b"3")) is None

    assert ImportIdempotencyRecord.objects.filter(tenant_id=_TENANT).count() == 2
    assert ImportIdempotencyRecord.objects.filter(key="cap-3").exists()


def test_begin_evicts_oldest_when_tenant_is_at_the_limit(settings):
    """F2: eviction admits the new key rather than refusing a busy tenant."""
    settings.IMPORT_IDEMPOTENCY_MAX_KEYS_PER_TENANT = 2
    _begin("old-1", _fingerprint(b"1"))
    _begin("old-2", _fingerprint(b"2"))
    # Make old-1 the soonest-expiring so it is evicted first.
    ImportIdempotencyRecord.objects.filter(key="old-1").update(
        expires_at=timezone.now() + timedelta(hours=1)
    )
    ImportIdempotencyRecord.objects.filter(key="old-2").update(
        expires_at=timezone.now() + timedelta(hours=23)
    )

    assert _begin("new", _fingerprint(b"new")) is None

    assert not ImportIdempotencyRecord.objects.filter(key="old-1").exists()
    assert ImportIdempotencyRecord.objects.filter(key="new").exists()


def test_per_tenant_limit_is_disabled_when_zero(settings):
    """F2: a non-positive cap does not block new keys."""
    settings.IMPORT_IDEMPOTENCY_MAX_KEYS_PER_TENANT = 0
    for i in range(5):
        assert _begin(f"nolimit-{i}", _fingerprint(str(i).encode())) is None


# ---------------------------------------------------------------------------
# ADR-014 §7 / D2a: keyed-HMAC fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_is_a_keyed_hmac_not_plain_sha256(settings):
    """The fingerprint is a keyed HMAC; a plain SHA-256 would be forgeable.

    Guards the D2a decision: the digest depends on the configured secret and
    therefore differs from a plain SHA-256 over the same byte sequence.
    """
    import hashlib

    payload = b"body"
    settings.IMPORT_FINGERPRINT_SECRET = "unit-test-fingerprint-secret"
    digest = compute_fingerprint(method="POST", path="/x/", payload=payload)

    assert len(digest) == 64  # hex digest: no column widening needed

    plain = hashlib.sha256()
    plain.update(b"POST\x00/x/\x00\x00")  # method NUL path NUL extra("") NUL
    plain.update(payload)
    assert digest != plain.hexdigest()

    # Rotating the key rotates the fingerprint.
    settings.IMPORT_FINGERPRINT_SECRET = "another-unit-test-secret"
    assert compute_fingerprint(method="POST", path="/x/", payload=payload) != digest


def test_fingerprint_falls_back_to_secret_key_when_no_explicit_secret(settings):
    """An unset ``IMPORT_FINGERPRINT_SECRET`` still yields a *keyed* digest.

    The fallback derives a domain-separated key from ``SECRET_KEY``, so the
    fingerprint changes when that secret rotates (the documented bounded 409
    window) and never degrades to an unkeyed SHA-256.
    """
    settings.IMPORT_FINGERPRINT_SECRET = ""
    settings.SECRET_KEY = "secret-key-a"
    first = compute_fingerprint(method="POST", path="/x/", payload=b"body")
    settings.SECRET_KEY = "secret-key-b"
    second = compute_fingerprint(method="POST", path="/x/", payload=b"body")
    assert first != second


# ---------------------------------------------------------------------------
# ADR-014 §3/§7: hard tenant cap under concurrency
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_concurrent_begin_cannot_exceed_the_tenant_cap(settings):
    """Two concurrent new keys must never push the store past the cap.

    The count → evict → insert sequence is guarded by a tenant-scoped
    PostgreSQL advisory lock (``pg_advisory_xact_lock``). Without it, two
    threads can both observe an empty/under-cap store and each insert, leaving
    ``limit + 1`` rows. Threads run against separate connections; this is
    best-effort race detection — the asserted invariant (never more than the
    cap) holds deterministically under the lock and can only flake in the
    permissive direction if the race does not materialise.
    """
    import threading

    from django.db import connections

    settings.IMPORT_IDEMPOTENCY_MAX_KEYS_PER_TENANT = 1
    tenant = uuid.uuid4()
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def worker(key: str) -> None:
        try:
            barrier.wait(timeout=5)
            _begin(key, _fingerprint(key.encode()), tenant=tenant)
        except BaseException as exc:  # noqa: BLE001 - re-surfaced on the test thread
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(f"cap-race-{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive(), "a concurrent begin() thread did not finish"

    assert not errors, errors
    assert ImportIdempotencyRecord.objects.filter(tenant_id=tenant).count() == 1
