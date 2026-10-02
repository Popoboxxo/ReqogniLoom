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
