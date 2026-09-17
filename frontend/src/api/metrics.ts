/**
 * ARCH-L1-001 ReactFrontend — Metrics API.
 *
 * leaf_id: COMP-RF-006 (MetricsDashboard)
 * req_id:  REQ-L0-020 (Metrikbasiertes Steuern des SE-Prozesses),
 *          REQ-L2-SM-001 (SeMetrics REST API),
 *          REQ-L2-SM-012 (Stable JSON format contract)
 *
 * Wraps GET /api/v1/metrics/?workspace_id=...&type=...&timeframe=...
 * The endpoint proxies to backend.se_metrics.services.compute_metrics
 * and returns a stable MetricsResult (REQ-L2-SM-012).
 *
 * Single workspace model: dashboard picks the active workspace from
 * WorkspaceContext; the optional `type` filter is forwarded to the backend
 * which currently treats it as an accepted but not-applied parameter
 * (reserved for v2 per backend/views.py).
 */

import { apiClient } from "./client";
import type { ISODateTime, UUID } from "../types";

// ---------------------------------------------------------------------------
// Public types — mirror of backend.se_metrics.types.MetricsResult.to_dict()
// (REQ-L2-SM-012 stable JSON contract)
// ---------------------------------------------------------------------------

export type MetricType =
  | "volatility"
  | "traceability_coverage"
  | "workflow_gaps"
  | "open_risks"
  | "coverage"
  | "all";

export interface VolatileRequirement {
  requirement_id: string;
  change_count: number;
  /**
   * Requirement title, resolved server-side (backend.se_metrics.aggregator).
   * Falls back to the first 8 characters of requirement_id when the
   * requirement no longer exists or has no title — never empty.
   */
  title: string;
}

export interface VolatilityMetric {
  total_changes: number;
  total_requirements: number;
  avg_changes_per_req: number;
  top10_volatile: VolatileRequirement[];
}

export interface TraceabilityCoverageMetric {
  total: number;
  covered: number;
  coverage_percent: number;
  uncovered_ids: string[];
}

export interface WorkflowGapItem {
  item_id: string;
  item_type: string;
  missing_state: string;
}

export interface WorkflowGapMetric {
  total_incomplete: number;
  items: WorkflowGapItem[];
}

export type RiskSeverity = "critical" | "high" | "medium" | "low";

export interface RiskMetric {
  total: number;
  by_severity: Record<RiskSeverity, number>;
}

export interface ThresholdWarning {
  metric: string;
  actual: number;
  threshold: number;
  description: string;
}

export interface MetricsResult {
  workspace_id: UUID;
  computed_at: ISODateTime;
  timeframe: string;
  volatility: VolatilityMetric;
  traceability_coverage: TraceabilityCoverageMetric;
  workflow_gaps: WorkflowGapMetric;
  open_risks: RiskMetric;
  warnings: ThresholdWarning[];
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

export interface MetricsQueryOptions {
  /** ISO-8601 duration like "P30D". Backend default if omitted. */
  timeframe?: string;
  /** Optional type filter. Backend currently accepts but does not apply it. */
  type?: string;
}

export const metricsApi = {
  /**
   * GET /api/v1/metrics/?workspace_id=...&type=...&timeframe=...
   * Returns the full MetricsResult for the workspace.
   */
  list(
    workspaceId: UUID,
    options: MetricsQueryOptions = {},
  ): Promise<MetricsResult> {
    const params = new URLSearchParams();
    params.set("workspace_id", workspaceId);
    if (options.type) params.set("type", options.type);
    if (options.timeframe) params.set("timeframe", options.timeframe);
    return apiClient.get<MetricsResult>(`/metrics/?${params.toString()}`);
  },
};

export type {
  // re-export for consumers that prefer importing from the metrics module
  VolatileRequirement as MetricVolatileRequirement,
  ThresholdWarning as MetricThresholdWarning,
};
