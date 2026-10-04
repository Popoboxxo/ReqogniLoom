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

Fingerprint (ADR-014 §7, decision D2a): the request fingerprint is a **keyed
HMAC-SHA-256** over (method, path, payload, dry_run). The key is
``IMPORT_FINGERPRINT_SECRET`` when set; otherwise a domain-separated key is
derived from ``SECRET_KEY`` (see :func:`_fingerprint_secret`) and
``manage.py check`` warns (``application.W001``) that an explicit secret should
be configured in production. The digest is 64 hex chars, so the stored column
needs no widening/migration.

Migration/compat strategy (D2a): fingerprints written before this change are
plain SHA-256 values and no longer match the keyed digest. A replay of an *old*
key within its TTL window can therefore answer ``409 IDEMPOTENCY_KEY_REUSED``
instead of a cached replay. The mismatch is confined to the
``(tenant_id, user_id, endpoint, key)`` scope and self-heals after
``IMPORT_IDEMPOTENCY_TTL_HOURS`` (24 h); rotating ``SECRET_KEY`` (or
``IMPORT_FINGERPRINT_SECRET``) has the same bounded effect. No schema/data
migration is performed.

Concurrency (ADR-014 §3/§7): on PostgreSQL the per-tenant key cap is enforced
under a transaction-scoped, tenant-keyed advisory lock
(:func:`_acquire_tenant_lock`) so the count → evict → insert sequence cannot
race past the cap; other vendors keep the pre-existing best-effort behaviour
(see the helper's docstring).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, connection, transaction
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


def _tenant_limit() -> int:
    """Maximum number of idempotency keys a single tenant may hold (ADR-014 §3/§7)."""
    return getattr(settings, "IMPORT_IDEMPOTENCY_MAX_KEYS_PER_TENANT", 10000)


def _acquire_tenant_lock(tenant_id: UUID) -> None:
    """Serialize new-key admission per tenant (ADR-014 §3/§7).

    A per-tenant *count* cap cannot be expressed as a database constraint, so
    the count → evict → insert sequence in :func:`begin` is made atomic with a
    transaction-scoped, tenant-keyed advisory lock. PostgreSQL's
    ``pg_advisory_xact_lock`` is released automatically when the enclosing
    ``transaction.atomic()`` commits or rolls back — which happens before the
    import itself runs (:func:`begin` only claims the key).

    Guarded by ``connection.vendor``: on non-PostgreSQL vendors (SQLite in some
    test configurations) there is no advisory-lock primitive, so the
    pre-existing best-effort behaviour is retained (documented, not silently
    changed). The unique constraint still guarantees key uniqueness on every
    vendor; only the *count* cap is best-effort there.
    """
    if connection.vendor != "postgresql":
        return
    # ``hashtext`` maps the tenant UUID to the 32-bit advisory-lock key space.
    # A hash collision between two tenants only over-serializes them; it cannot
    # let a tenant exceed its cap.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))", [str(tenant_id)]
        )


def _enforce_tenant_limit(*, tenant_id: UUID, now: Any) -> None:
    """Reject a new key once *tenant_id* holds its key cap (ADR-014 §3/§7).

    Deletes the tenant's oldest records first so an active tenant is never
    locked out permanently; only reached on the *new-key* path, so an existing
    key's replay/takeover is untouched. Raises the same request-level conflict
    code as an in-flight key (409 + ``Retry-After``), since the client can
    retry once cleanup/TTL has freed a slot.

    Callers hold the tenant-scoped advisory lock (:func:`_acquire_tenant_lock`),
    so the count and the following insert are atomic with respect to other
    new-key admissions for the same tenant.
    """
    from application.models import ImportIdempotencyRecord

    limit = _tenant_limit()
    if limit <= 0:  # limit disabled
        return
    # Count only live records; expired ones are removed opportunistically.
    queryset = ImportIdempotencyRecord.objects.filter(tenant_id=tenant_id)
    existing = queryset.count()
    if existing < limit:
        return

    ImportIdempotencyRecord.objects.filter(
        tenant_id=tenant_id, expires_at__lt=now
    ).delete()
    existing = queryset.count()
    if existing < limit:
        return

    # Evict oldest-expiring rows to admit the new key rather than refusing a
    # working tenant outright: the store stays bounded and the oldest replay
    # window is sacrificed first.
    excess = existing - limit + 1
    doomed = list(queryset.order_by("expires_at").values_list("id", flat=True)[:excess])
    ImportIdempotencyRecord.objects.filter(id__in=doomed).delete()

    if queryset.count() >= limit:
        # Nothing evictable (race with a peer holding the same slots).
        raise IdempotencyConflict(
            CODE_IN_FLIGHT,
            "Too many concurrent Idempotency-Keys for this tenant; retry later.",
            retry_after=60,
        )


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


def _fingerprint_secret() -> bytes:
    """Return the HMAC key for the request fingerprint (ADR-014 §7, D2a).

    Prefers the explicit ``IMPORT_FINGERPRINT_SECRET``. When it is empty — or
    only whitespace, which is stripped so a whitespace-only value cannot
    silently defeat the check below — a domain-separated key is derived from
    ``SECRET_KEY`` so the fingerprint is *always* keyed (never a plain SHA-256)
    without inventing a new secret. The derived fallback is a documented
    limitation surfaced at ``manage.py check`` time by
    ``application.checks.check_import_fingerprint_secret``. The strip matches
    that check exactly, so ``application.W001`` fires whenever this fallback is
    taken (``IMPORT_FINGERPRINT_SECRET="   "`` included).
    """
    explicit = (getattr(settings, "IMPORT_FINGERPRINT_SECRET", "") or "").strip()
    if explicit:
        return explicit.encode("utf-8")
    secret_key = getattr(settings, "SECRET_KEY", "") or ""
    return hashlib.sha256(
        b"import-fingerprint:" + secret_key.encode("utf-8")
    ).digest()


def compute_fingerprint(
    *,
    method: str,
    path: str,
    payload: bytes,
    extra: str = "",
) -> str:
    """Return the request fingerprint for the idempotency scope.

    Keyed HMAC-SHA-256 over method + path + payload bytes + ``extra`` (the
    caller passes ``dry_run``/``entity_type``) so a replay of a semantically
    different request is detected as a key reuse. No plaintext payload is
    stored. The return value is the 64-char hex digest (unchanged length, so no
    column migration).
    """
    digest = hmac.new(_fingerprint_secret(), digestmod=hashlib.sha256)
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
            # Serialize new-key admission for this tenant: the count → evict →
            # insert sequence below must be atomic or concurrent distinct keys
            # could each observe a free slot and push the store past the cap.
            _acquire_tenant_lock(tenant_id)
            # Opportunistic cleanup: expired successes and abandoned in-flight
            # claims do not accumulate unboundedly (ADR-014 §3/§7).
            ImportIdempotencyRecord.objects.filter(expires_at__lt=now).delete()
            # Admission control (ADR-014 §3/§7): reject a *new* key once the
            # tenant already holds its maximum number of keys, instead of
            # letting many unique keys exhaust the store. Existing keys are
            # never affected (replay/takeover keep working).
            _enforce_tenant_limit(tenant_id=tenant_id, now=now)
            try:
                # The INSERT runs in its own savepoint: a raised IntegrityError
                # would otherwise abort the *outer* transaction, so the
                # requery below would hit "current transaction is aborted" and
                # surface as an unhandled 500 instead of a 409 (F1, same
                # pattern as reqif_import_service.py's create retry).
                with transaction.atomic():
                    ImportIdempotencyRecord.objects.create(
                        **scope,
                        request_fingerprint=fingerprint,
                        state=STATE_IN_FLIGHT,
                        claimed_at=now,
                        expires_at=now + _ttl(),
                    )
                    return None
            except IntegrityError:
                # Lost the create race; the savepoint rolled the failed INSERT
                # back, so this requery runs on a healthy connection and reads
                # the peer's committed row (or sees nothing if it is not yet
                # visible, in which case we surface the conflict below).
                record = (
                    ImportIdempotencyRecord.objects.select_for_update()
                    .filter(**scope)
                    .first()
                )
                if record is None:
                    raise IdempotencyConflict(
                        CODE_IN_FLIGHT,
                        "A request with this Idempotency-Key is still in progress.",
                        retry_after=1,
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
