"""Idempotency-Key replay store for import endpoints (ADR-014 §3).

The store is deliberately small and DB-backed (not cache-backed): the
correctness requirement is that a replay over the scope
``(tenant_id, user_id, endpoint, key)`` is concurrency-safe across workers, and
the unique constraint plus ``SELECT ... FOR UPDATE`` give exactly that. A cache
backend would depend on a shared Redis and could not enforce the scope's
uniqueness atomically under the project's current multi-worker cache caveat
(REQ-040 / BE-9).

Contract (ADR-014 §3):

* The first request claims the key (``state=in_flight``).
* A replay of the *same* payload after a terminal success returns the cached
  body/status (the caller sets ``idempotent_replay=true``).
* A different payload on the same key -> ``409`` ``IDEMPOTENCY_KEY_REUSED``.
* A concurrent request while the first is in flight -> ``409``
  ``IDEMPOTENCY_IN_FLIGHT`` with ``Retry-After``.
* Only terminal **successes** are cached. A failed/partial run deletes the
  claim so a retry with the same key can succeed.
* TTL 24 h (configurable); :func:`purge_expired` is the cleanup seam
  (scheduled as a Celery-beat task).

Residual (documented, not a silent fail-open): the fingerprint is a plain
SHA-256 over (method, path, payload, dry_run), not an HMAC, because the stored
value is never returned to a client and is scoped per tenant/user; the ADR's
HMAC recommendation (§7) is a hardening follow-up, not a correctness gap.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

STATE_IN_FLIGHT = "in_flight"
STATE_SUCCEEDED = "succeeded"

CODE_KEY_REUSED = "IDEMPOTENCY_KEY_REUSED"
CODE_IN_FLIGHT = "IDEMPOTENCY_IN_FLIGHT"

#: An in-flight claim older than this may be taken over by a new request: a
#: worker that died mid-import must not lock a key until TTL expiry.
IN_FLIGHT_STALE_SECONDS = 600


def _ttl() -> timedelta:
    hours = getattr(settings, "IMPORT_IDEMPOTENCY_TTL_HOURS", 24)
    return timedelta(hours=hours)


class IdempotencyConflict(Exception):
    """Request-level idempotency conflict (ADR-014 §3).

    ``code`` is a stable cause code (``IDEMPOTENCY_KEY_REUSED`` or
    ``IDEMPOTENCY_IN_FLIGHT``); ``retry_after`` (seconds) is only set for the
    in-flight case and feeds the ``Retry-After`` response header.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@dataclass
class CachedImportResult:
    """A terminal success stored under an idempotency key."""

    status_code: int
    body: Dict[str, Any]


def compute_fingerprint(
    *,
    method: str,
    path: str,
    payload: bytes,
    extra: str = "",
) -> str:
    """Return the request fingerprint for the idempotency scope.

    Covers method + path + payload bytes + ``extra`` (the caller passes the
    ``dry_run`` flag) so a replay of a semantically different request is
    detected as a key reuse. No plaintext payload is stored.
    """
    digest = hashlib.sha256()
    digest.update(method.upper().encode("utf-8"))
    digest.update(b"\x00")
    digest.update(path.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(extra.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(payload)
    return digest.hexdigest()


def begin(
    *,
    tenant_id: UUID,
    user_id: UUID,
    endpoint: str,
    key: str,
    fingerprint: str,
) -> Optional[CachedImportResult]:
    """Claim *key* or return a cached replay.

    Returns ``None`` when the caller owns the claim and must run the import;
    returns a :class:`CachedImportResult` for a true replay. Raises
    :class:`IdempotencyConflict` for a reused key with a different payload or
    for a concurrent in-flight request.
    """
    from application.models import ImportIdempotencyRecord

    now = timezone.now()
    scope = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "endpoint": endpoint,
        "key": key,
    }

    with transaction.atomic():
        record = (
            ImportIdempotencyRecord.objects.select_for_update()
            .filter(**scope)
            .first()
        )
        if record is None:
            # Opportunistic cleanup: expired successes and abandoned in-flight
            # claims do not accumulate unboundedly (ADR-014 §3/§7).
            ImportIdempotencyRecord.objects.filter(expires_at__lt=now).delete()
            try:
                ImportIdempotencyRecord.objects.create(
                    **scope,
                    request_fingerprint=fingerprint,
                    state=STATE_IN_FLIGHT,
                    claimed_at=now,
                    expires_at=now + _ttl(),
                )
                return None
            except IntegrityError:
                # Lost the create race; fall through to the peer's row.
                record = (
                    ImportIdempotencyRecord.objects.select_for_update()
                    .filter(**scope)
                    .first()
                )

        if record is None:  # pragma: no cover — peer deleted it immediately
            return None

        if record.state == STATE_SUCCEEDED and record.expires_at > now:
            if record.request_fingerprint != fingerprint:
                raise IdempotencyConflict(
                    CODE_KEY_REUSED,
                    "Idempotency-Key was already used with a different request payload.",
                )
            return CachedImportResult(
                status_code=record.status_code or 200,
                body=record.response_body or {},
            )

        if record.state == STATE_IN_FLIGHT:
            age = (now - record.claimed_at).total_seconds()
            if age < IN_FLIGHT_STALE_SECONDS:
                raise IdempotencyConflict(
                    CODE_IN_FLIGHT,
                    "A request with this Idempotency-Key is still in progress.",
                    retry_after=max(1, int(IN_FLIGHT_STALE_SECONDS - age)),
                )
            # Stale claim (crashed worker): take it over.
            record.request_fingerprint = fingerprint
            record.claimed_at = now
            record.expires_at = now + _ttl()
            record.save(
                update_fields=["request_fingerprint", "claimed_at", "expires_at"]
            )
            return None

        # Expired success: refresh as a fresh claim.
        record.state = STATE_IN_FLIGHT
        record.request_fingerprint = fingerprint
        record.status_code = None
        record.response_body = None
        record.claimed_at = now
        record.expires_at = now + _ttl()
        record.save(
            update_fields=[
                "state",
                "request_fingerprint",
                "status_code",
                "response_body",
                "claimed_at",
                "expires_at",
            ]
        )
        return None


def finalize_success(
    *,
    tenant_id: UUID,
    user_id: UUID,
    endpoint: str,
    key: str,
    fingerprint: str,
    status_code: int,
    body: Dict[str, Any],
) -> None:
    """Persist a terminal success so subsequent replays are served from the store.

    Only successes are cached (ADR-014 §3). A mismatch between the stored claim
    fingerprint and *fingerprint* is ignored (a stale takeover won the race) —
    never overwrite a fresh claim by another worker.
    """
    from application.models import ImportIdempotencyRecord

    now = timezone.now()
    with transaction.atomic():
        record = (
            ImportIdempotencyRecord.objects.select_for_update()
            .filter(
                tenant_id=tenant_id,
                user_id=user_id,
                endpoint=endpoint,
                key=key,
            )
            .first()
        )
        if record is None or record.request_fingerprint != fingerprint:
            return
        record.state = STATE_SUCCEEDED
        record.status_code = status_code
        record.response_body = body
        record.expires_at = now + _ttl()
        record.save(
            update_fields=[
                "state",
                "status_code",
                "response_body",
                "expires_at",
            ]
        )


def abort(
    *,
    tenant_id: UUID,
    user_id: UUID,
    endpoint: str,
    key: str,
) -> None:
    """Drop an in-flight claim after a non-cached outcome (failure/partial).

    Deleting (rather than marking failed) is what lets a retry with the same
    key run again — a transient failure must not become a cached death
    sentence. A terminal success is never touched.
    """
    from application.models import ImportIdempotencyRecord

    ImportIdempotencyRecord.objects.filter(
        tenant_id=tenant_id,
        user_id=user_id,
        endpoint=endpoint,
        key=key,
        state=STATE_IN_FLIGHT,
    ).delete()


def purge_expired() -> int:
    """Delete expired records; returns the number of rows removed.

    Called by the periodic Celery-beat cleanup task and opportunistically from
    :func:`begin`.
    """
    from application.models import ImportIdempotencyRecord

    deleted, _ = ImportIdempotencyRecord.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()
    return deleted


__all__ = [
    "CODE_IN_FLIGHT",
    "CODE_KEY_REUSED",
    "CachedImportResult",
    "IdempotencyConflict",
    "abort",
    "begin",
    "compute_fingerprint",
    "finalize_success",
    "purge_expired",
]
