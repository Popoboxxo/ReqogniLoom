"""App configuration for ARCH-L1-015 SeMetrics."""
from django.apps import AppConfig


class SeMetricsConfig(AppConfig):
    """ARCH-L1-015 SeMetrics — SE Process Metrics Module.

    Responsibilities:
    - Computes SE process metrics across all artifact types and subsystems:
      * Requirements Volatility (change rate per requirement, configurable timeframe)
      * Traceability Coverage (% of linked requirements)
      * Workflow Gaps (items without complete workflow history)
      * Open Risks by severity
    - Aggregates from: AuditLog (volatility, IF-L1-044), TraceabilityEngine
      (coverage, IF-L1-045), WorkflowEngine (gaps, IF-L1-046),
      ApplicationService (risks, IF-L1-047).
    - Serves dashboard data and REST endpoint GET /metrics/workspace/{id} (IF-L1-042).
    - Configurable threshold warnings.
    - Optional metric cache entity for materialized aggregations (IF-L1-048).

    See: docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
    REQ-L1: REQ-L1-031 (SE process metrics)
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "se_metrics"
    verbose_name = "ARCH-L1-015 SeMetrics"
