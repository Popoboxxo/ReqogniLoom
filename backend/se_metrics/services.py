"""
ARCH-L1-015 SeMetrics — Service stubs.

TODO(COMP-SM-001): Implement MetricsService:
  - compute_metrics(workspace_id, timeframe, scope_filter) -> MetricsDashboard
    Aggregates from:
    - audit.services.query_changes(workspace_id, timeframe)  → Volatility (IF-L1-044)
    - traceability.services.coverage(workspace_id)           → Coverage (IF-L1-045)
    - workflow.services.find_incomplete_states(workspace_id) → Gaps (IF-L1-046)
    - application.services.query_risks_by_severity(workspace_id) → Risks (IF-L1-047)
  - check_thresholds(metrics, config) -> list[ThresholdWarning]

Reference: docs/se/L1/Gesamtsystem/L2/SeMetricsSystem/L2_SeMetricsSystem_Architecture.md
"""
