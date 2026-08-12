"""
ARCH-L1-015 SeMetrics — MetricsCacheManager (COMP-SM-008).

leaf_id: COMP-SM-008
req_id: REQ-L1-031, REQ-L2-SM-007, REQ-L2-SM-009, REQ-L2-SM-013

Manages:
  - Metric result cache (MetricCache model, IF-L1-048)
  - ThresholdConfig persistence (WorkspaceThresholdConfig model, IF-L1-048)

Cache design:
  - Cache-hit: returns MetricsResult from JSON if within TTL
  - Cache-miss: returns None; caller triggers live computation
  - Cache-failure: returns None (Fallback to live computation, no HTTP 5xx)
  - Thundering Herd Prevention: in-process threading.Lock per workspace_key
    (in-process substitute for Redis Lock; satisfies REQ-L2-SM-013 for
    single-process deployments; Redis lock upgrade path documented below)
  - Invalidation: explicit invalidate() call + TTL-based expiry

Redis Lock note (ADR-SM-05):
  The architecture specifies a Redis distributed lock for multi-process
  Thundering Herd Prevention. This implementation provides in-process locking
  via threading.Lock, which is correct for single-worker deployments.
  For multi-worker production, replace _get_or_create_lock() with a
  django-redis or redis-py distributed lock (e.g. redis.lock.Lock).
  The interface contract (get_or_lock, release_lock) is stable.

Architecture:
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from se_metrics.types import MetricsResult, ThresholdConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-process lock registry for Thundering Herd Prevention (REQ-L2-SM-013)
# ---------------------------------------------------------------------------

_lock_registry: Dict[str, threading.Lock] = {}
_lock_registry_mutex = threading.Lock()


def _get_or_create_lock(cache_key: str) -> threading.Lock:
    """Return (or create) a per-cache-key lock.

    This implements Thundering Herd Prevention within a single process.
    For multi-process deployments, replace with a Redis-backed distributed lock.
    """
    with _lock_registry_mutex:
        if cache_key not in _lock_registry:
            _lock_registry[cache_key] = threading.Lock()
        return _lock_registry[cache_key]


# ---------------------------------------------------------------------------
# MetricsCacheManager — COMP-SM-008
# ---------------------------------------------------------------------------


class MetricsCacheManager:
    """COMP-SM-008 — Metric Cache and ThresholdConfig Manager.

    Provides:
      IF-SM-INT-008: get_cached(workspace_id, timeframe) -> MetricsResult | None
      IF-SM-INT-008: put_cached(workspace_id, timeframe, result)
      IF-SM-INT-007: get_threshold_config(workspace_id) -> ThresholdConfig | None
      IF-SM-INT-010 (Celery path): put_cached() — same method, Celery worker context

    leaf_id: COMP-SM-008
    req_id: REQ-L2-SM-007, REQ-L2-SM-009, REQ-L2-SM-013
    """

    DEFAULT_TTL_SECONDS = 300  # 5 minutes (REQ-L2-SM-009)
    DEFAULT_LOCK_TIMEOUT_SECONDS = 30  # REQ-L2-SM-013

    def _make_cache_key(self, workspace_id: str, timeframe: str) -> str:
        """Construct cache lookup key."""
        return f"{workspace_id}:{timeframe}"

    # ------------------------------------------------------------------
    # IF-SM-INT-008: Cache read/write
    # ------------------------------------------------------------------

    def get_cached(
        self, workspace_id: str, timeframe: str
    ) -> Optional[MetricsResult]:
        """Fetch cached MetricsResult if present and within TTL.

        IF-SM-INT-008 contract (cache read path).

        Returns None on cache-miss, cache-stale, or any DB error.
        Cache-failure always falls back to live computation — no HTTP 5xx.

        Args:
            workspace_id: Workspace UUID string.
            timeframe: ISO-8601 period string (e.g. "P30D").

        Returns:
            MetricsResult if cache hit, None otherwise.
        """
        try:
            from se_metrics.models import MetricCache  # lazy import

            entry = MetricCache.objects.filter(
                workspace_id=workspace_id,
                timeframe_key=timeframe,
            ).first()

            if entry is None:
                return None

            # TTL check
            now = datetime.now(tz=timezone.utc)
            computed_at = entry.computed_at
            if computed_at.tzinfo is None:
                computed_at = computed_at.replace(tzinfo=timezone.utc)

            age_seconds = (now - computed_at).total_seconds()
            if age_seconds > entry.cache_ttl_seconds:
                logger.debug(
                    "MetricsCacheManager: cache stale for ws=%s tf=%s age=%ds",
                    workspace_id,
                    timeframe,
                    age_seconds,
                )
                return None

            result = self._deserialize(entry.result_json)
            logger.debug(
                "MetricsCacheManager: cache hit for ws=%s tf=%s", workspace_id, timeframe
            )
            return result

        except Exception:
            logger.warning(
                "MetricsCacheManager: cache read failed for ws=%s tf=%s, falling back to live",
                workspace_id,
                timeframe,
                exc_info=True,
            )
            return None

    def put_cached(
        self,
        workspace_id: str,
        timeframe: str,
        result: MetricsResult,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Persist MetricsResult to cache.

        IF-SM-INT-008 (cache write path) and IF-SM-INT-010 (Celery beat path).

        Cache-write failures are logged and swallowed — they must not produce
        HTTP 5xx (REQ-L2-SM-009 "Cache-Fehler → Fallback").

        Args:
            workspace_id: Workspace UUID string.
            timeframe: ISO-8601 period string.
            result: Computed MetricsResult to cache.
            ttl_seconds: Cache TTL in seconds (default 300).
        """
        try:
            from se_metrics.models import MetricCache  # lazy import

            result_json = result.to_dict()
            now = datetime.now(tz=timezone.utc)

            MetricCache.objects.update_or_create(
                workspace_id=workspace_id,
                timeframe_key=timeframe,
                defaults={
                    "tenant_id": result.workspace_id,  # use workspace_id as tenant proxy
                    "result_json": result_json,
                    "computed_at": now,
                    "cache_ttl_seconds": ttl_seconds,
                },
            )
            logger.debug(
                "MetricsCacheManager: cached result for ws=%s tf=%s ttl=%ds",
                workspace_id,
                timeframe,
                ttl_seconds,
            )
        except Exception:
            logger.warning(
                "MetricsCacheManager: cache write failed for ws=%s tf=%s",
                workspace_id,
                timeframe,
                exc_info=True,
            )

    def invalidate(self, workspace_id: str, timeframe: Optional[str] = None) -> None:
        """Invalidate cache entries for a workspace.

        Called on AuditLog change events to ensure stale data is not served.

        Args:
            workspace_id: Workspace UUID string.
            timeframe: If provided, invalidate only this timeframe entry.
                       If None, invalidate all entries for the workspace.
        """
        try:
            from se_metrics.models import MetricCache  # lazy import

            qs = MetricCache.objects.filter(workspace_id=workspace_id)
            if timeframe is not None:
                qs = qs.filter(timeframe_key=timeframe)
            deleted_count, _ = qs.delete()
            logger.debug(
                "MetricsCacheManager: invalidated %d cache entries for ws=%s",
                deleted_count,
                workspace_id,
            )
        except Exception:
            logger.warning(
                "MetricsCacheManager: cache invalidation failed for ws=%s",
                workspace_id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # IF-SM-INT-007: ThresholdConfig access
    # ------------------------------------------------------------------

    def get_threshold_config(self, workspace_id: str) -> Optional[ThresholdConfig]:
        """Load workspace threshold configuration from DB.

        IF-SM-INT-007 contract (ThresholdEvaluator → MetricsCacheManager).

        Returns None if no ThresholdConfig is configured for this workspace.
        DB errors are caught and logged; caller should treat None as "no config".

        Args:
            workspace_id: Workspace UUID string.

        Returns:
            ThresholdConfig dataclass or None if not configured.
        """
        try:
            from se_metrics.models import WorkspaceThresholdConfig  # lazy import

            row = WorkspaceThresholdConfig.objects.filter(
                workspace_id=workspace_id
            ).first()

            if row is None:
                return None

            return ThresholdConfig(
                workspace_id=workspace_id,
                traceability_coverage_min=row.traceability_coverage_min,
                volatility_max_avg=row.volatility_max_avg,
                workflow_gaps_max=row.workflow_gaps_max,
                open_risks_max_critical=row.open_risks_max_critical,
            )
        except Exception:
            logger.warning(
                "MetricsCacheManager: threshold config load failed for ws=%s",
                workspace_id,
                exc_info=True,
            )
            return None

    def save_threshold_config(
        self,
        workspace_id: str,
        tenant_id: str,
        traceability_coverage_min: Optional[float] = None,
        volatility_max_avg: Optional[float] = None,
        workflow_gaps_max: Optional[int] = None,
        open_risks_max_critical: Optional[int] = None,
    ) -> ThresholdConfig:
        """Persist threshold configuration for a workspace (REQ-L2-SM-007 CRUD).

        Args:
            workspace_id: Workspace UUID string.
            tenant_id: Tenant UUID string.
            traceability_coverage_min: Minimum coverage percent (warn if below).
            volatility_max_avg: Maximum avg changes per req (warn if above).
            workflow_gaps_max: Maximum workflow gaps (warn if above).
            open_risks_max_critical: Maximum critical risks (warn if above).

        Returns:
            Saved ThresholdConfig dataclass.
        """
        from se_metrics.models import WorkspaceThresholdConfig  # lazy import

        row, _ = WorkspaceThresholdConfig.objects.update_or_create(
            workspace_id=workspace_id,
            defaults={
                "tenant_id": tenant_id,
                "traceability_coverage_min": traceability_coverage_min,
                "volatility_max_avg": volatility_max_avg,
                "workflow_gaps_max": workflow_gaps_max,
                "open_risks_max_critical": open_risks_max_critical,
            },
        )
        return ThresholdConfig(
            workspace_id=workspace_id,
            traceability_coverage_min=row.traceability_coverage_min,
            volatility_max_avg=row.volatility_max_avg,
            workflow_gaps_max=row.workflow_gaps_max,
            open_risks_max_critical=row.open_risks_max_critical,
        )

    # ------------------------------------------------------------------
    # Thundering Herd Prevention (REQ-L2-SM-013)
    # ------------------------------------------------------------------

    def acquire_compute_lock(
        self,
        workspace_id: str,
        timeframe: str,
        timeout_seconds: int = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> bool:
        """Try to acquire the computation lock for a workspace/timeframe key.

        Implements Thundering Herd Prevention (REQ-L2-SM-013):
        Only one computation runs at a time per cache key.

        Returns:
            True if lock was acquired (caller should compute and call put_cached).
            False if lock could not be acquired within timeout_seconds
            (caller should fall back to direct live computation).
        """
        cache_key = self._make_cache_key(workspace_id, timeframe)
        lock = _get_or_create_lock(cache_key)
        acquired = lock.acquire(timeout=timeout_seconds)
        if not acquired:
            logger.debug(
                "MetricsCacheManager: lock timeout for ws=%s tf=%s, falling back",
                workspace_id,
                timeframe,
            )
        return acquired

    def release_compute_lock(self, workspace_id: str, timeframe: str) -> None:
        """Release the computation lock after cache write.

        Waiting threads will re-check the cache after lock release.
        """
        cache_key = self._make_cache_key(workspace_id, timeframe)
        lock = _get_or_create_lock(cache_key)
        try:
            lock.release()
        except RuntimeError:
            # Lock was not held — log and continue (defensive)
            logger.debug(
                "MetricsCacheManager: attempted to release unheld lock for key=%s",
                cache_key,
            )

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    def _deserialize(self, result_json: Dict) -> Optional[MetricsResult]:
        """Reconstruct a MetricsResult from cached JSON dict.

        Returns None if deserialization fails.
        """
        try:
            from se_metrics.types import (
                CoverageResult,
                RiskResult,
                VolatileRequirement,
                VolatilityResult,
                WorkflowGap,
                WorkflowGapResult,
                ThresholdWarning,
                MetricsResult,
            )

            computed_at = datetime.fromisoformat(result_json["computed_at"])
            if computed_at.tzinfo is None:
                computed_at = computed_at.replace(tzinfo=timezone.utc)

            vol_raw = result_json.get("volatility", {})
            volatility = VolatilityResult(
                total_changes=vol_raw.get("total_changes", 0),
                total_requirements=vol_raw.get("total_requirements", 0),
                avg_changes_per_req=vol_raw.get("avg_changes_per_req", 0.0),
                top10_volatile=[
                    VolatileRequirement(
                        requirement_id=r["requirement_id"],
                        change_count=r["change_count"],
                        # .get() with fallback: cache entries written before
                        # the "title" field was introduced must still load
                        # cleanly on a warm cache (no crash on first deploy).
                        title=r.get("title", ""),
                    )
                    for r in vol_raw.get("top10_volatile", [])
                ],
            )

            cov_raw = result_json.get("traceability_coverage", {})
            coverage = CoverageResult(
                total=cov_raw.get("total", 0),
                covered=cov_raw.get("covered", 0),
                coverage_percent=cov_raw.get("coverage_percent", 0.0),
                uncovered_ids=cov_raw.get("uncovered_ids", []),
            )

            gap_raw = result_json.get("workflow_gaps", {})
            gaps = WorkflowGapResult(
                total_incomplete=gap_raw.get("total_incomplete", 0),
                items=[
                    WorkflowGap(
                        item_id=g["item_id"],
                        item_type=g["item_type"],
                        missing_state=g["missing_state"],
                    )
                    for g in gap_raw.get("items", [])
                ],
            )

            risk_raw = result_json.get("open_risks", {})
            risks = RiskResult(
                total=risk_raw.get("total", 0),
                by_severity=risk_raw.get(
                    "by_severity", {"critical": 0, "high": 0, "medium": 0, "low": 0}
                ),
            )

            warnings = [
                ThresholdWarning(
                    metric=w["metric"],
                    actual=w["actual"],
                    threshold=w["threshold"],
                    description=w["description"],
                )
                for w in result_json.get("warnings", [])
            ]

            return MetricsResult(
                workspace_id=result_json["workspace_id"],
                computed_at=computed_at,
                timeframe=result_json.get("timeframe", "P30D"),
                volatility=volatility,
                traceability_coverage=coverage,
                workflow_gaps=gaps,
                open_risks=risks,
                warnings=warnings,
            )
        except Exception:
            logger.warning(
                "MetricsCacheManager: deserialization failed", exc_info=True
            )
            return None


__all__ = ["MetricsCacheManager"]
