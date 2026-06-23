"""
ARCH-L1-015 SeMetrics — Models.

TODO(COMP-SM-001): Implement MetricCache model (optional, for materialized aggregations).
  Fields: id, tenant_id, workspace_id, metric_type, computed_at, value (JSONField),
  timeframe_start, timeframe_end.
  Populated by scheduled Celery tasks; invalidated on relevant write operations.
  Falls back to live computation if cache is stale (IF-L1-048).

Reference: docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
"""
from django.db import models  # noqa: F401
