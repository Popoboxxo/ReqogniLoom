"""
ARCH-L1-015 SeMetrics — Public service facade.

leaf_id: COMP-SM-001, COMP-SM-002
req_id: REQ-L1-031 (primary), REQ-L2-SM-001..013

This module is the ONLY public import surface for downstream consumers
(rest_api, mcp_server, future integrations) of the SeMetrics system.

Public import paths:
    from se_metrics.services import compute_metrics
    from se_metrics.services import get_threshold_config, save_threshold_config
    from se_metrics.services import MetricsResult, ThresholdConfig

Interface coverage:
    IF-L1-042 / IF-L1-043: compute_metrics() is the entry point for
        GET /metrics/workspace/{id} — serves both RestApiAdapter and ReactFrontend.
    IF-SM-INT-001: MetricsQueryController → MetricsAggregator delegation.
    IF-SM-INT-008: Cache lookup and write via MetricsCacheManager.

Cache + Thundering Herd flow (COMP-SM-001 responsibility, REQ-L2-SM-013):
    1. Try cache hit (COMP-SM-008.get_cached)
    2. On miss: acquire compute lock (Thundering Herd Prevention)
    3. Re-check cache after lock (another thread may have computed)
    4. Compute via MetricsAggregator
    5. Write result to cache
    6. Release lock

Tenant isolation (REQ-L2-SM-010):
    Tenant context must be set by the caller (REST middleware or test fixture)
    before calling compute_metrics(). The TenantContext propagates automatically
    through audit.services.query(), traceability.services.coverage(), and
    WorkflowEngine ORM queries.

Architecture:
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
"""
from __future__ import annotations

import logging
from typing import Any

from se_metrics.aggregator import DEFAULT_TIMEFRAME, MetricsAggregator
from se_metrics.cache import MetricsCacheManager
from se_metrics.registry import (
    ALL_METRIC_KEYS,
    DEFAULT_METRIC_KEYS,
    catalog_payload,
    get_metric_spec,
    normalize_keys,
    select_values,
)
from se_metrics.types import MetricsResult, ThresholdConfig

logger = logging.getLogger(__name__)

# Module-level singletons (lazy, reused per process)
_aggregator: MetricsAggregator | None = None
_cache_manager: MetricsCacheManager | None = None


def _get_aggregator() -> MetricsAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = MetricsAggregator()
    return _aggregator


def _get_cache_manager() -> MetricsCacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = MetricsCacheManager()
    return _cache_manager


# ---------------------------------------------------------------------------
# Primary public function — IF-L1-042 / IF-L1-043 entry point
# ---------------------------------------------------------------------------


def compute_metrics(
    workspace_id: str,
    timeframe: str | None = None,
    scope_filter: list[str] | None = None,
) -> MetricsResult:
    """Compute (or retrieve from cache) SE process metrics for a workspace.

    This is the public service facade entry point for:
      - GET /metrics/workspace/{id} (IF-L1-042, IF-L1-043)
      - Dashboard data refresh (ReactFrontend via RestApiAdapter)

    Cache + Thundering Herd flow (REQ-L2-SM-009, REQ-L2-SM-013):
      1. Try cache hit.
      2. On miss: acquire compute lock.
      3. Re-check cache after lock acquisition.
      4. If still missing: compute via MetricsAggregator.
      5. Write result to cache.
      6. Release lock.

    Tenant isolation is the CALLER's responsibility (RestApiAdapter must set
    TenantContext before calling this function — REQ-L2-SM-010).

    Args:
        workspace_id: Workspace UUID string.
        timeframe: ISO-8601 period string (e.g. "P30D"). Default: 30 days.
        scope_filter: Optional artifact-type filter list (reserved for v2).

    Returns:
        MetricsResult with all four metric categories and threshold warnings.

    Raises:
        No exceptions — all failures produce safe empty metric values.
        The caller never receives an HTTP 5xx due to metric source failures.
    """
    effective_timeframe = timeframe or DEFAULT_TIMEFRAME
    cache_mgr = _get_cache_manager()
    aggregator = _get_aggregator()

    # Step 1: Cache hit check (fast path, REQ-L2-SM-009)
    cached = cache_mgr.get_cached(workspace_id, effective_timeframe)
    if cached is not None:
        return cached

    # Step 2: Acquire compute lock (Thundering Herd Prevention, REQ-L2-SM-013)
    lock_acquired = cache_mgr.acquire_compute_lock(workspace_id, effective_timeframe)

    try:
        if lock_acquired:
            # Step 3: Re-check cache after acquiring lock
            # (another thread may have computed while we waited)
            cached = cache_mgr.get_cached(workspace_id, effective_timeframe)
            if cached is not None:
                return cached

        # Step 4: Load threshold config for evaluation (IF-SM-INT-007)
        threshold_config = cache_mgr.get_threshold_config(workspace_id)

        # Step 4: Compute via MetricsAggregator (IF-SM-INT-001)
        result = aggregator.compute(
            workspace_id=workspace_id,
            timeframe=effective_timeframe,
            scope_filter=scope_filter,
            threshold_config=threshold_config,
        )

        # Step 5: Write to cache (IF-SM-INT-008 write path)
        if lock_acquired:
            cache_mgr.put_cached(workspace_id, effective_timeframe, result)

        return result

    finally:
        # Step 6: Release lock (whether or not compute succeeded)
        if lock_acquired:
            cache_mgr.release_compute_lock(workspace_id, effective_timeframe)


# ---------------------------------------------------------------------------
# Threshold configuration management (REQ-L2-SM-007)
# ---------------------------------------------------------------------------


def get_threshold_config(workspace_id: str) -> ThresholdConfig | None:
    """Retrieve threshold configuration for a workspace.

    Returns None if no thresholds are configured.

    Args:
        workspace_id: Workspace UUID string.

    Returns:
        ThresholdConfig dataclass or None.
    """
    return _get_cache_manager().get_threshold_config(workspace_id)


def save_threshold_config(
    workspace_id: str,
    tenant_id: str,
    traceability_coverage_min: float | None = None,
    volatility_max_avg: float | None = None,
    workflow_gaps_max: int | None = None,
    open_risks_max_critical: int | None = None,
) -> ThresholdConfig:
    """Create or update threshold configuration for a workspace.

    This is the service entry point for PUT /metrics/workspace/{id}/thresholds
    (REQ-L2-SM-007). Also invalidates the cache for this workspace so the next
    metric computation uses the updated thresholds.

    Args:
        workspace_id: Workspace UUID string.
        tenant_id: Tenant UUID string.
        traceability_coverage_min: Minimum coverage percent. Warn if below.
        volatility_max_avg: Maximum avg changes per requirement. Warn if above.
        workflow_gaps_max: Maximum workflow gaps. Warn if above.
        open_risks_max_critical: Maximum critical open risks. Warn if above.

    Returns:
        Saved ThresholdConfig dataclass.
    """
    cache_mgr = _get_cache_manager()
    config = cache_mgr.save_threshold_config(
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        traceability_coverage_min=traceability_coverage_min,
        volatility_max_avg=volatility_max_avg,
        workflow_gaps_max=workflow_gaps_max,
        open_risks_max_critical=open_risks_max_critical,
    )
    # Invalidate cache so next request applies new thresholds
    cache_mgr.invalidate(workspace_id)
    return config


def invalidate_cache(workspace_id: str, timeframe: str | None = None) -> None:
    """Invalidate cached metrics for a workspace.

    Called by AuditLog change event handlers to ensure stale data is not served.

    Args:
        workspace_id: Workspace UUID string.
        timeframe: If provided, invalidate only this timeframe entry.
    """
    _get_cache_manager().invalidate(workspace_id, timeframe)


# ---------------------------------------------------------------------------
# Central statistics registry facade (Issue #1265) — IF-L1-042 companion
# ---------------------------------------------------------------------------


def get_metric_catalog() -> dict[str, Any]:
    """Return the available statistics catalogue (Issue #1265).

    One payload for the UI, ``GET /api/v1/metrics/catalog/`` and MCP
    ``metrics.catalog``. It is pure registry metadata — no computation, no DB,
    no tenant context required.

    Returns:
        ``{"metrics": [<entry>, ...], "default_keys": [...],
        "all_keys": [...]}``. ``default_keys`` is the set a caller with no
        explicit per-user selection sees.
    """
    return {
        "metrics": catalog_payload(),
        "default_keys": list(DEFAULT_METRIC_KEYS),
        "all_keys": list(ALL_METRIC_KEYS),
    }


def get_metric_values(
    workspace_id: str,
    keys: list[str] | None = None,
    timeframe: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return the selected statistics with their values (Issue #1265).

    Backs ``GET /api/v1/metrics/?workspace_id=…&keys=…`` and MCP
    ``metrics.get``. It reuses :func:`compute_metrics` (so the existing
    cache/TTL and thundering-herd protection apply unchanged) and then
    extracts only the requested scalars.

    Cost contract (Issue #1265 §5): a read is cache-first. ``refresh=True``
    invalidates the workspace's cached entry first, so an expensive coverage
    metric over 1000+ Requirements is recomputed *on demand* and never on every
    read. The responding ``computed_at`` (top level and per metric) tells the
    caller how fresh the value is.

    Args:
        workspace_id: Workspace UUID string.
        keys: Metric keys to return. ``None``/empty means every registered
            metric. Unknown keys are reported in ``unknown_keys``.
        timeframe: ISO-8601 period string for the volatility window.
        refresh: Invalidate the cache before computing.

    Returns:
        ``{"workspace_id", "computed_at", "timeframe",
        "metrics": {key: {...}}, "unknown_keys": [...]}``.
    """
    if refresh:
        # Invalidating before the read is what makes the read a real recompute
        # rather than a cache hit; a timeframe-scoped invalidate leaves the
        # other windows warm.
        invalidate_cache(workspace_id, timeframe)

    result = compute_metrics(workspace_id=workspace_id, timeframe=timeframe)

    known_keys, unknown_keys = normalize_keys(keys)
    values = select_values(result, known_keys)
    computed_at = result.computed_at.isoformat()

    metrics: dict[str, Any] = {}
    for key in known_keys:
        spec = get_metric_spec(key)
        if spec is None:  # defensive: normalize_keys already filtered
            continue
        metrics[key] = {
            "key": key,
            "title": spec.title,
            "title_key": spec.title_key,
            "unit": spec.unit,
            "scope": spec.scope,
            "expensive": spec.expensive,
            "value": values.get(key),
            "computed_at": computed_at,
        }

    return {
        "workspace_id": str(result.workspace_id),
        "computed_at": computed_at,
        "timeframe": result.timeframe,
        "metrics": metrics,
        "unknown_keys": unknown_keys,
    }


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "compute_metrics",
    "get_threshold_config",
    "save_threshold_config",
    "invalidate_cache",
    # Issue #1265 central statistics registry
    "get_metric_catalog",
    "get_metric_values",
    # Re-exports for caller convenience
    "MetricsResult",
    "ThresholdConfig",
]
