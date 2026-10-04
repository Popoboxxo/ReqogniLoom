"""DB-backed brute-force lockout for the Django admin login (issue #1135).

Policy note (ADR-style)
=======================

**Context.** ``/admin/login/`` is a public endpoint that accepted unlimited
password guesses. The REST login endpoint already has a cache-backed failure
throttle (:mod:`rest_api.throttling`, #72/#269), but the admin shares none of
it. Issue **#1135** records the binding decision: implement a small *custom,
DB-backed* lockout instead of adopting ``django-axes``.

**Mechanism.** On every failed admin credential check one row keyed by
``(client_ip, username_digest)`` is incremented; once ``failure_count`` reaches
the configured threshold the pair is locked for a cool-down window.

**Key.** ``(client_ip, username_digest)`` — the same pair the REST throttle
uses, and for the same reason: a per-IP-only key is a trivial auth-DoS behind a
NAT, a per-username-only key lets a botnet lock a known admin out. The username
is stored only as a truncated SHA-256 digest, never verbatim.

**Defaults / configurability.** Threshold 5 failures within a 900 s window,
900 s cool-down. All three are environment-overridable via the
``ADMIN_LOGIN_LOCKOUT_*`` settings (see ``reqogniloom/settings.py``); the whole
feature is gated by ``ADMIN_LOGIN_LOCKOUT_ENABLED``.

**Expiry strategy.** No Celery/cron. Expiry is evaluated by the *query window*:
failures older than the window do not count toward the threshold, and a
``locked_until`` in the past means unlocked. Stale rows are deleted
opportunistically on write (:func:`_delete_stale_rows`), so the table stays
bounded without a background job.

**Out of scope.** This module never touches REST throttling state
(``rest_api.throttling``) and never authenticates anyone; it only answers "is
this (IP, username) pair currently locked?" and records/reset counters. The
admin-only signal and form wiring lives in :mod:`auth_tenancy.admin_login`.

Tracking location: GitHub issue #1135.
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import random
from datetime import datetime, timedelta

from django.conf import settings
from django.db import DataError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from auth_tenancy.models import AdminLoginLockout

logger = logging.getLogger(__name__)

__all__ = [
    "is_locked",
    "register_failure",
    "reset",
    "resolve_client_ip",
    "username_digest",
]

#: Fallback defaults, used only if a setting is somehow absent (it is always
#: present via settings.py — this keeps the module importable in isolation and
#: makes the intended values explicit next to the code that consumes them).
_DEFAULT_THRESHOLD = 5
_DEFAULT_WINDOW_SECONDS = 900
_DEFAULT_DURATION_SECONDS = 900

#: A row is stale once its last failure is older than this multiple of the
#: window and it is not (or no longer) locked. Purely a housekeeping margin so
#: the opportunistic cleanup never races an explicit reset of an active window.
_STALE_MARGIN_FACTOR = 1


# ---------------------------------------------------------------------------
# Clock & IP resolution seams (overridable in tests)
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """Return the current timezone-aware time.

    Single overridable seam: tests monkeypatch this to travel through the
    lockout window and cool-down deterministically (``freezegun`` is not
    available in this project).
    """
    return timezone.now()


def resolve_client_ip(request) -> str:
    """Resolve the client IP for *request*.

    DELIBERATE ANTI-SPOOFING DEVIATION from DRF's
    ``SimpleRateThrottle.get_ident`` (used by ``rest_api.throttling``), which
    combines the ``X-Forwarded-For`` header and the peer address behind a
    ``NUM_PROXIES`` depth. That header is fully client-controlled when no proxy
    rewrites it, so a caller could rotate it per request and dodge the counter
    entirely. This lockout instead keys on the transport-level peer
    ``REMOTE_ADDR``, which a client cannot forge, and only consults
    ``X-Forwarded-For`` when the operator has explicitly configured
    ``NUM_PROXIES`` (the same setting DRF reads, from
    ``REST_FRAMEWORK['NUM_PROXIES']`` / ``api_settings.NUM_PROXIES``).

    Trade-off: with ``NUM_PROXIES`` unset (the project default — see
    ``settings.py`` and ``mcp_server/throttling.py``) a reverse proxy that does
    not rewrite ``REMOTE_ADDR`` puts every admin behind one bucket, so one
    attacker can lock all of them out. That is the documented project-wide proxy
    caveat; operators fronting the admin with a proxy should set ``NUM_PROXIES``.

    Every candidate is validated and NORMALISED with
    :func:`ipaddress.ip_address` before it is returned, because the value is
    written to a PostgreSQL ``inet`` column. Two failure modes are closed here:

    * a non-IP token (e.g. ``"not-an-ip"``) would otherwise raise a ``DataError``
      (and a 500) deep in the ORM;
    * an IPv6 **scope ID** such as ``"fe80::1%eth0"`` is accepted by
      :mod:`ipaddress` but REJECTED by PostgreSQL ``inet`` — a submitted scope ID
      must not silently disable the counter, so such a candidate is rejected and
      the caller falls back to the validated ``REMOTE_ADDR``. Accepted addresses
      are returned in their normalised textual form via
      ``str(ipaddress.ip_address(...))``.

    A non-IP or scope-ID candidate falls back to the validated ``REMOTE_ADDR``,
    and a missing/blank final value degrades to ``"0.0.0.0"`` — malformed input
    can never silently turn the counter off.
    """
    meta = getattr(request, "META", None) or {}

    def _valid(candidate: object) -> str | None:
        """Return a PostgreSQL-``inet``-safe IP string, or None."""
        if not isinstance(candidate, str) or not candidate.strip():
            return None
        text = candidate.strip()
        # Reject IPv6 scope IDs explicitly: ipaddress would accept "fe80::1%eth0"
        # but PostgreSQL inet would not, which (under a configured NUM_PROXIES
        # with an attacker-controlled XFF element) would let the counter be
        # skipped. Reject rather than strip, so the caller falls back to the
        # unforgeable REMOTE_ADDR instead of keying on an attacker-shaped value.
        if "%" in text:
            return None
        try:
            return str(ipaddress.ip_address(text))
        except ValueError:
            return None

    # Only trust XFF when the operator declares a proxy depth; otherwise the
    # header is attacker-controlled and must be ignored.
    num_proxies = _num_proxies()
    if num_proxies:
        xff = meta.get("HTTP_X_FORWARDED_FOR")
        if isinstance(xff, str):
            parts = [part.strip() for part in xff.split(",") if part.strip()]
            if parts:
                index = min(num_proxies, len(parts))
                trusted = _valid(parts[-index])
                if trusted:
                    return trusted

    return _valid(meta.get("REMOTE_ADDR")) or "0.0.0.0"


def _num_proxies() -> int:
    """Return the configured ``NUM_PROXIES`` depth, or 0 when unset/invalid.

    Reads the same source DRF does (``REST_FRAMEWORK['NUM_PROXIES']`` via
    ``api_settings``), falling back to the bare ``settings.NUM_PROXIES`` for
    callers that set it directly, so the lockout and the REST throttle agree.
    """
    candidates: list[object] = []
    try:
        from rest_framework.settings import api_settings

        candidates.append(getattr(api_settings, "NUM_PROXIES", None))
    except Exception:  # noqa: BLE001 - DRF import/settings must not break the path
        pass
    candidates.append(getattr(settings, "NUM_PROXIES", None))
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def username_digest(username: object) -> str:
    """Stable, storage-safe digest of the submitted username.

    Identical shape to ``rest_api.throttling._username_digest``: SHA-256 of the
    stripped, lower-cased username truncated to 32 hex chars. Hashed so a dump
    of this table does not read like a user directory; lower-cased because
    usernames are matched case-insensitively at login.
    """
    value = username if isinstance(username, str) else ""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Settings accessors
# ---------------------------------------------------------------------------


def _enabled() -> bool:
    return bool(getattr(settings, "ADMIN_LOGIN_LOCKOUT_ENABLED", True))


def _threshold() -> int:
    return int(getattr(settings, "ADMIN_LOGIN_LOCKOUT_THRESHOLD", _DEFAULT_THRESHOLD))


def _window() -> timedelta:
    return timedelta(
        seconds=int(
            getattr(
                settings,
                "ADMIN_LOGIN_LOCKOUT_WINDOW_SECONDS",
                _DEFAULT_WINDOW_SECONDS,
            )
        )
    )


def _duration() -> timedelta:
    return timedelta(
        seconds=int(
            getattr(
                settings,
                "ADMIN_LOGIN_LOCKOUT_DURATION_SECONDS",
                _DEFAULT_DURATION_SECONDS,
            )
        )
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

#: Probability (1-in-N) that a given ``register_failure`` also runs the stale-row
#: cleanup. Every failure doing two synchronous DELETEs is wasteful and adds
#: write pressure to the very path under attack; sampling keeps the table bounded
#: without turning each login attempt into a maintenance job.
_CLEANUP_SAMPLE_1_IN = 50


def _cleanup_cutoff(now: datetime) -> datetime:
    """Timestamp before which an unlocked row can no longer affect a decision."""
    return now - _window() * _STALE_MARGIN_FACTOR


def _delete_stale_rows(now: datetime) -> None:
    """Opportunistically delete rows that can no longer affect a decision.

    A row is stale when it is not locked and its last failure is older than the
    window (times the safety margin); separately, a lock row whose ``locked_until``
    is long past is also dead. Both predicates are indexed
    (``idx_admin_lockout_last`` on ``last_failure_at`` and
    ``idx_admin_lockout_locked_until`` on ``locked_until``) so a sampled run stays
    cheap. Best-effort: housekeeping must never break an authentication request,
    so any failure is logged and swallowed.
    """
    if random.randint(1, _CLEANUP_SAMPLE_1_IN) != 1:
        return
    cutoff = _cleanup_cutoff(now)
    try:
        AdminLoginLockout.objects.filter(
            locked_until__isnull=True,
            last_failure_at__lt=cutoff,
        ).delete()
        AdminLoginLockout.objects.filter(locked_until__lt=cutoff).delete()
    except Exception:  # noqa: BLE001 - housekeeping must not break login
        logger.warning(
            "admin login lockout: stale-row cleanup failed (non-fatal)",
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _log_fail_open(operation: str, exc: Exception) -> None:
    """Log a fail-open DB error, calling out a ``DataError`` distinctly.

    A ``DataError`` means a value reached the ORM that PostgreSQL rejected (e.g.
    a malformed address that slipped past validation). That is a correctness bug
    in IP handling, NOT a transient connectivity failure, so it is logged at a
    higher-signal level with an explicit pointer — the fail-open policy still
    applies (a login attempt must never 500), but the operator gets a clear
    signal instead of a generic "db unavailable" line.
    """
    if isinstance(exc, DataError):
        logger.error(
            "admin login lockout: %s rejected a malformed value (DataError); "
            "the counter was skipped for this attempt — check IP validation "
            "(issue #1135)",
            operation,
            exc_info=True,
        )
    else:
        logger.warning(
            "admin login lockout: %s failed (fail-open) — issue #1135",
            operation,
            exc_info=True,
        )


def is_locked(client_ip: str, username: object) -> bool:
    """Return whether ``(client_ip, username)`` is currently locked out.

    Clock-driven: a ``locked_until`` in the past returns ``False`` even if the
    row still exists (no proactive delete is required to lift the lock).
    Returns ``False`` immediately when the feature is disabled.

    FAIL-OPEN on a database error: this is a DoS *mitigation*, not an
    authorization boundary (authentication and RBAC are enforced independently),
    so an unreadable table must let the attempt proceed rather than turning every
    admin login into a 500. The failure is logged (a ``DataError`` distinctly).
    """
    if not _enabled():
        return False
    now = _now()
    digest = username_digest(username)
    try:
        locked_until = (
            AdminLoginLockout.objects.filter(
                client_ip=client_ip, username_digest=digest
            )
            .values_list("locked_until", flat=True)
            .first()
        )
    except Exception as exc:  # noqa: BLE001 - documented fail-open policy
        _log_fail_open("read lock state", exc)
        return False
    return locked_until is not None and locked_until > now


def _locked_or_create(client_ip: str, username_digest_value: str, now: datetime):
    """Return this key's row locked ``FOR UPDATE``, creating it if absent.

    Concurrency (F1): ``select_for_update`` serialises concurrent
    ``register_failure`` calls **once the row exists**, but cannot serialise the
    *first* failure — there is no row to lock yet, so two concurrent POSTs both
    fall through to the INSERT and the unique constraint on
    ``(client_ip, username_digest)`` turns the loser into an ``IntegrityError``.
    Because Django's ``authenticate()`` sends ``user_login_failed`` without a
    try/except, that would surface as an HTTP 500 on the login page and lose the
    count. The create is therefore wrapped in its own savepoint (nested
    ``atomic``), and the loser simply re-reads the winner's committed row — the
    exact SA-18 shape used by ``resilience.circuit_breaker._locked_or_create``.

    Returns ``None`` only if the row is still not visible after losing the race
    (a defensive impossibility on READ COMMITTED; the caller fails open).
    """
    row = _select_locked(client_ip, username_digest_value)
    if row is not None:
        return row

    try:
        with transaction.atomic():
            created = AdminLoginLockout.objects.create(
                client_ip=client_ip,
                username_digest=username_digest_value,
                failure_count=0,
                first_failure_at=now,
                last_failure_at=now,
                locked_until=None,
            )
    except IntegrityError:
        # Lost the create race: the concurrent winner's row is committed.
        return _select_locked(client_ip, username_digest_value)

    # Re-fetch under lock for consistent concurrent semantics.
    return _select_locked(client_ip, username_digest_value) or created


def _select_locked(client_ip: str, username_digest_value: str):
    """Return this key's row locked ``FOR UPDATE``, or None if absent."""
    return (
        AdminLoginLockout.objects.select_for_update()
        .filter(client_ip=client_ip, username_digest=username_digest_value)
        .first()
    )


def register_failure(client_ip: str, username: object) -> bool:
    """Record one failed admin login attempt; return whether it locked the pair.

    Window semantics: the streak is anchored on ``first_failure_at`` and lapses
    once ``now - first_failure_at > window``. A lapsed streak (or an expired
    lock) restarts at 1 and clears ``locked_until`` back to NULL, preserving the
    model invariant "NULL while unlocked" — otherwise ``__str__`` would report a
    stale "locked" state for an unlocked row. Reaching the threshold stamps
    ``locked_until = now + duration`` and logs a WARNING (IP + digest prefix
    only — no raw username).

    FAIL-OPEN on a database error: a DB fault must never turn a login attempt
    into a 500 (consistent with ``rest_api.throttling``'s fail-open policy). A
    write failure is logged and the call returns ``False``. This does **not**
    weaken the lock: a pair that is already locked is rejected by
    :func:`is_locked` / the form gate before this runs, so failing open here only
    means "this counter increment was lost", never "a locked pair authenticated".
    """
    if not _enabled():
        return False

    now = _now()
    digest = username_digest(username)
    window = _window()
    threshold = _threshold()

    try:
        with transaction.atomic():
            row = _locked_or_create(client_ip, digest, now)
            if row is None:  # pragma: no cover - defensive
                return False

            streak_expired = now - row.first_failure_at > window
            lock_expired = row.locked_until is not None and row.locked_until <= now
            if streak_expired or lock_expired:
                # New burst: reset the window anchor and clear the stale lock.
                count = 1
                row.first_failure_at = now
                row.locked_until = None
            else:
                count = row.failure_count + 1

            row.failure_count = count
            row.last_failure_at = now
            row.version = F("version") + 1
            if count >= threshold:
                row.locked_until = now + _duration()

            row.save(
                update_fields=[
                    "failure_count",
                    "first_failure_at",
                    "last_failure_at",
                    "locked_until",
                    "modified_at",
                    "version",
                ]
            )
    except Exception as exc:  # noqa: BLE001 - documented fail-open policy
        _log_fail_open("record failure", exc)
        return False

    locked = count >= threshold
    if locked:
        logger.warning(
            "admin login lockout triggered for ip=%s digest=%s (threshold=%d, "
            "duration_s=%d) — issue #1135",
            client_ip,
            digest[:8],
            threshold,
            int(_duration().total_seconds()),
        )

    _delete_stale_rows(now)
    return locked


def reset(client_ip: str, username: object) -> None:
    """Clear the counter/lock for ``(client_ip, username)`` after a success.

    A successful admin login must not leave a stale lock for a legitimate user.
    Best-effort and fail-open: a DB error here is logged, never raised.
    """
    if not _enabled():
        return
    digest = username_digest(username)
    try:
        AdminLoginLockout.objects.filter(
            client_ip=client_ip, username_digest=digest
        ).delete()
    except Exception as exc:  # noqa: BLE001 - documented fail-open policy
        _log_fail_open("reset lock state", exc)
