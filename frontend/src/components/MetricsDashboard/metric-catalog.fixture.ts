/**
 * Shared test fixture for the central statistics registry catalogue
 * (Issue #1265).
 *
 * Mirrors `se_metrics.registry.catalog_payload()` closely enough to exercise
 * the dashboard's catalogue-driven widget configuration: snake_case keys, an
 * i18n `title_key`, and one metric (`verification_coverage`) that is registered
 * but opted out of the default set (`default_visible: false`).
 */

import type { MetricCatalog } from "../../api/metrics";

export function buildMetricCatalog(): MetricCatalog {
  const metrics = [
    {
      key: "traceability_coverage",
      title: "Traceability Coverage",
      title_key: "metrics.catalog.traceability_coverage.title",
      unit: "%",
      scope: "workspace",
      description: "Share of Requirements with an outgoing trace link.",
      expensive: true,
      default_visible: true,
      source: "traceability.services.coverage",
      params: ["workspace_id"],
    },
    {
      key: "verification_coverage",
      title: "Verification Coverage",
      title_key: "metrics.catalog.verification_coverage.title",
      unit: "%",
      scope: "workspace",
      description: "Share of active Requirements with verification evidence.",
      expensive: true,
      default_visible: false,
      source: "persistence.Requirement",
      params: ["workspace_id"],
    },
    {
      key: "volatility",
      title: "Requirement Volatility",
      title_key: "metrics.catalog.volatility.title",
      unit: "changes/req",
      scope: "workspace",
      description: "Average change events per Requirement.",
      expensive: false,
      default_visible: true,
      source: "audit.services.query",
      params: ["workspace_id", "timeframe"],
    },
    {
      key: "workflow_gaps",
      title: "Workflow Gaps",
      title_key: "metrics.catalog.workflow_gaps.title",
      unit: "",
      scope: "workspace",
      description: "Items missing a mandatory workflow state.",
      expensive: false,
      default_visible: true,
      source: "workflow.models",
      params: ["workspace_id"],
    },
    {
      key: "open_risks",
      title: "Open Risks",
      title_key: "metrics.catalog.open_risks.title",
      unit: "",
      scope: "workspace",
      description: "Open Risks.",
      expensive: false,
      default_visible: true,
      source: "application.risk_service",
      params: ["workspace_id"],
    },
    {
      key: "open_risks_critical",
      title: "Critical Open Risks",
      title_key: "metrics.catalog.open_risks_critical.title",
      unit: "",
      scope: "workspace",
      description: "Open Risks at maximum severity.",
      expensive: false,
      default_visible: true,
      source: "application.risk_service",
      params: ["workspace_id"],
    },
  ];

  return {
    metrics,
    default_keys: metrics
      .filter((entry) => entry.default_visible)
      .map((entry) => entry.key),
    all_keys: metrics.map((entry) => entry.key),
  };
}

/** The metric keys rendered when the caller has no explicit selection. */
export const DEFAULT_METRIC_KEYS: readonly string[] = [
  "traceability_coverage",
  "volatility",
  "workflow_gaps",
  "open_risks",
  "open_risks_critical",
];
