"""
COMP-LA-006 TokenUsageTracker — Per-tenant token accounting and daily limits.

REQ-106: The LLM adapter logs token usage (COMP-LA-004) but does not persist it
queryably. This module records every successful LLM call as a
``TokenUsageRecord`` row, aggregates consumption per tenant over a time window,
and enforces a configurable daily limit
(``settings.TENANT_TOKEN_LIMIT_PER_DAY``).

Design principles:
    - Fault-tolerant: recording and limit checks never raise into the LLM call
      path. A DB failure degrades to "not recorded" / "fail-open" so a broken
      accounting layer can never take down the AI features. Every DB access
      here runs in its own ``transaction.atomic()`` savepoint — swallowing the
      exception is not enough on Postgres, where a failed statement leaves the
      caller's ambient transaction aborted and breaks every query it runs
      afterwards (#444, extended to the read paths per the #522 review).
    - Tenant-scoped: records are written and queried through the tenant-isolating
      default manager, so the active ``TenantContext`` scopes every query.
    - No provider SDK imports; this module is a thin persistence + aggregation
      layer over ``persistence.models.TokenUsageRecord``.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Error code surfaced when a tenant exceeds its configured daily token budget.
LLM_TOKEN_LIMIT_EXCEEDED = "LLM_TOKEN_LIMIT_EXCEEDED"


def record_token_usage(
    provider: str,
    capability: str,
    input_tokens: int,
    output_tokens: int = 0,
    workspace_id: Optional[str] = None,
) -> None:
    """Persist one token-usage record for the active tenant (REQ-106).

    Best-effort: any failure (no tenant context, DB unavailable, RLS rejection)
    is swallowed so token accounting never affects the LLM result. The tenant is
    injected automatically by the tenant-scoped default manager from the active
    ``TenantContext``.

    Args:
        provider: Provider name that served the call.
        capability: Capability invoked (e.g. "validate_artifact").
        input_tokens: Prompt/input token count (or the combined total when a
            provider only exposes a single number).
        output_tokens: Completion/output token count (0 when only a total known).
        workspace_id: Optional workspace UUID string to attribute the call to.
    """
    if input_tokens is None:
        input_tokens = 0
    try:
        from django.db import transaction  # noqa: PLC0415

        from persistence.models import TokenUsageRecord  # noqa: PLC0415

        # #444 follow-up: a bare TokenUsageRecord.objects.create() call left a
        # failed INSERT's Postgres transaction "aborted" for whoever called
        # record_token_usage() from inside their own ambient transaction —
        # every query the caller ran afterward (this module's own or theirs)
        # then raised TransactionManagementError, even though the INSERT
        # failure itself was caught and logged here. That defeats this
        # function's "never affects the caller" contract as badly as letting
        # the original exception propagate would have. atomic() gives the
        # INSERT its own savepoint, so a failure rolls back only that
        # savepoint and the caller's transaction stays usable.
        with transaction.atomic():
            TokenUsageRecord.objects.create(
                provider=provider,
                capability=capability,
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
                workspace_id=workspace_id,
            )
    except Exception as exc:  # noqa: BLE001 — accounting must never break LLM calls
        logger.warning(
            "TokenUsageTracker: failed to record usage for %s via %s: %s",
            capability,
            provider,
            exc,
        )


def get_daily_usage(days: int = 1) -> int:
    """Return the active tenant's total tokens consumed in the last ``days`` days.

    Best-effort: returns 0 when no tenant context is set or the query fails.

    Args:
        days: Rolling window size in days (default 1 = last 24 hours).

    Returns:
        Sum of ``input_tokens + output_tokens`` over the window, or 0.
    """
    try:
        from django.db import transaction  # noqa: PLC0415
        from django.db.models import Sum  # noqa: PLC0415
        from django.utils import timezone  # noqa: PLC0415

        from persistence.models import TokenUsageRecord  # noqa: PLC0415

        since = timezone.now() - timedelta(days=days)
        # #522 review follow-up (F4): savepoint for the same reason the INSERT
        # in record_token_usage has one. A failing SELECT aborts an ambient
        # Postgres transaction exactly as a failing INSERT does, so without
        # this the "never affects the caller" contract held on one of four
        # paths only. This one matters most: is_over_daily_limit() calls it
        # before *every* LLM request, in-request, from seven services.
        with transaction.atomic():
            agg = TokenUsageRecord.objects.filter(created_at__gte=since).aggregate(
                total=Sum("input_tokens") + Sum("output_tokens")
            )
        return int(agg["total"] or 0)
    except Exception as exc:  # noqa: BLE001 — fail-open aggregation
        logger.warning("TokenUsageTracker: get_daily_usage failed: %s", exc)
        return 0


def aggregate_usage(days: int = 30) -> Dict[str, Any]:
    """Aggregate the active tenant's usage over ``days`` days (REQ-106 query API).

    Returns a structured summary: overall total plus a per-provider breakdown.

    Args:
        days: Rolling window size in days (default 30).

    Returns:
        {
            "days": <int>,
            "total_tokens": <int>,
            "by_provider": {"<provider>": <int>, ...},
        }
    """
    result: Dict[str, Any] = {"days": days, "total_tokens": 0, "by_provider": {}}
    try:
        from django.db import transaction  # noqa: PLC0415
        from django.db.models import Sum  # noqa: PLC0415
        from django.utils import timezone  # noqa: PLC0415

        from persistence.models import TokenUsageRecord  # noqa: PLC0415

        since = timezone.now() - timedelta(days=days)
        # #522 review follow-up (F4): savepoint — see get_daily_usage. The
        # queryset is materialised inside the block on purpose; a lazy
        # QuerySet would execute after the savepoint was released.
        with transaction.atomic():
            rows = list(
                TokenUsageRecord.objects.filter(created_at__gte=since)
                .values("provider")
                .annotate(total=Sum("input_tokens") + Sum("output_tokens"))
            )
        total = 0
        for row in rows:
            provider_total = int(row["total"] or 0)
            result["by_provider"][row["provider"]] = provider_total
            total += provider_total
        result["total_tokens"] = total
    except Exception as exc:  # noqa: BLE001 — fail-open aggregation
        logger.warning("TokenUsageTracker: aggregate_usage failed: %s", exc)
    return result


def get_daily_token_limit() -> Optional[int]:
    """Return the configured per-tenant daily token limit, or None if unlimited.

    Reads ``settings.TENANT_TOKEN_LIMIT_PER_DAY``. ``None`` (default) means no
    limit is enforced. Falls back to ``None`` when Django settings are not
    configured (isolated unit tests).
    """
    try:
        from django.conf import settings  # noqa: PLC0415

        limit = getattr(settings, "TENANT_TOKEN_LIMIT_PER_DAY", None)
    except Exception:  # noqa: BLE001 — settings unavailable outside Django
        return None
    if limit is None:
        return None
    try:
        limit_int = int(limit)
    except (TypeError, ValueError):
        return None
    return limit_int if limit_int > 0 else None


def is_over_daily_limit() -> bool:
    """Return True when the active tenant has exceeded its daily token limit.

    Fail-open: returns False when no limit is configured, no tenant context is
    set, or the usage query fails — a broken accounting layer must never block
    LLM calls silently for every tenant.
    """
    limit = get_daily_token_limit()
    if limit is None:
        return False
    return get_daily_usage(days=1) >= limit


__all__ = [
    "LLM_TOKEN_LIMIT_EXCEEDED",
    "record_token_usage",
    "get_daily_usage",
    "aggregate_usage",
    "get_daily_token_limit",
    "is_over_daily_limit",
]
