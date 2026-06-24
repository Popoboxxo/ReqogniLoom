"""
ARCH-L1-015 SeMetrics — ORM models.

leaf_id: COMP-SM-008
req_id: REQ-L1-031 (primary), REQ-L2-SM-007, REQ-L2-SM-009

Models owned by COMP-SM-008 MetricsCacheManager (IF-L1-048 PersistenceLayer):
  - MetricCache: optional materialized metric result per workspace/timeframe
  - WorkspaceThresholdConfig: configurable threshold values per workspace

These are the ONLY write targets for the SeMetrics Read-Model (REQ-L2-SM-008).
No writes to Requirements, TraceLinks, WorkflowStates, or AuditLog entries.

Architecture:
    docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
"""
from __future__ import annotations

import uuid

from django.db import models


class MetricCache(models.Model):
    """Materialized metric aggregation result per workspace and timeframe.

    COMP-SM-008 MetricsCacheManager owns this table via IF-L1-048.

    leaf_id: COMP-SM-008
    req_id: REQ-L2-SM-009

    TTL management: cache_ttl_seconds controls expiry. The cache manager
    checks (computed_at + TTL) against now() to determine staleness.
    Cache-Fehler → Fallback auf Live-Berechnung (kein 5xx).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(db_index=True)
    tenant_id = models.UUIDField(db_index=True)
    # ISO-8601 period key, e.g. "P30D"
    timeframe_key = models.CharField(max_length=32)
    # Full serialized MetricsResult as JSON
    result_json = models.JSONField(default=dict)
    computed_at = models.DateTimeField()
    # TTL in seconds (default: 300 = 5 minutes, REQ-L2-SM-009)
    cache_ttl_seconds = models.IntegerField(default=300)

    class Meta:
        db_table = "sm_metric_cache"
        constraints = [
            models.UniqueConstraint(
                fields=["workspace_id", "tenant_id", "timeframe_key"],
                name="uq_sm_cache_workspace_timeframe",
            )
        ]
        indexes = [
            models.Index(
                fields=["workspace_id", "timeframe_key"],
                name="idx_sm_cache_ws_timeframe",
            ),
            models.Index(
                fields=["tenant_id", "workspace_id"],
                name="idx_sm_cache_tenant_ws",
            ),
        ]

    def __str__(self) -> str:
        return f"MetricCache({self.workspace_id}/{self.timeframe_key} at {self.computed_at})"


class WorkspaceThresholdConfig(models.Model):
    """Per-workspace threshold configuration for metric warnings.

    COMP-SM-008 MetricsCacheManager manages persistence of this entity.

    leaf_id: COMP-SM-008
    req_id: REQ-L2-SM-007

    All threshold fields are nullable — None means "not configured".
    Threshold semantics:
      traceability_coverage_min: warn if coverage_percent < value
      volatility_max_avg:        warn if avg_changes_per_req > value
      workflow_gaps_max:         warn if total_incomplete > value
      open_risks_max_critical:   warn if critical risk count > value
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace_id = models.UUIDField(unique=True, db_index=True)
    tenant_id = models.UUIDField(db_index=True)

    traceability_coverage_min = models.FloatField(null=True, blank=True)
    volatility_max_avg = models.FloatField(null=True, blank=True)
    workflow_gaps_max = models.IntegerField(null=True, blank=True)
    open_risks_max_critical = models.IntegerField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sm_threshold_config"
        indexes = [
            models.Index(
                fields=["tenant_id", "workspace_id"],
                name="idx_sm_threshold_tenant_ws",
            ),
        ]

    def __str__(self) -> str:
        return f"ThresholdConfig({self.workspace_id})"


__all__ = [
    "MetricCache",
    "WorkspaceThresholdConfig",
]
