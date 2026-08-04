/**
 * ARCH-L1-001 ReactFrontend — MetricsDashboard (COMP-RF-006).
 *
 * leaf_id: COMP-RF-006 (MetricsDashboard)
 * req_id:  REQ-L0-020 (Metrikbasiertes Steuern des SE-Prozesses),
 *          REQ-L2-SM-001 (SeMetrics REST API),
 *          REQ-L2-SM-012 (Stable JSON format contract)
 *
 * Visualizes the SeMetrics report from /api/v1/metrics/.
 * Tiles: coverage, volatility, workflow gap, open risks, critical risks.
 * Each tile shows current value, unit, last-computed timestamp, status
 * color (green/yellow/red) and an inline-SVG sparkline built from the
 * local value history (single-point on first render, builds up across
 * refreshes).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { metricsApi, type MetricsResult } from "../../api/metrics";
import { PageHeader } from "../shared/PageHeader";

// ---------------------------------------------------------------------------
// Tile model
// ---------------------------------------------------------------------------

type Status = "healthy" | "warning" | "critical" | "neutral";

interface MetricTileSpec {
  /** stable identifier used for data-testid suffixes */
  name:
    | "coverage"
    | "volatility"
    | "workflowGap"
    | "openRisks"
    | "openRisksCritical";
  /** i18n key for the title */
  titleKey: string;
  /** unit suffix shown next to the value */
  unit: string;
  /** formatter for the numeric value */
  format: (n: number) => string;
  /** returns the raw value (used for sparkline + status) */
  value: (m: MetricsResult) => number;
  /** higher = worse, lower = worse, or "info" (no threshold) */
  direction: "higher-bad" | "lower-bad" | "info";
  /** thresholds for warning / critical classification */
  thresholds: { warning: number; critical: number };
}

const TILES: MetricTileSpec[] = [
  {
    name: "coverage",
    titleKey: "metrics.coverage",
    unit: "%",
    format: (n) => n.toFixed(1),
    value: (m) => m.traceability_coverage.coverage_percent,
    direction: "lower-bad",
    thresholds: { warning: 80, critical: 50 },
  },
  {
    name: "volatility",
    titleKey: "metrics.volatility",
    unit: "/req",
    format: (n) => n.toFixed(2),
    value: (m) => m.volatility.avg_changes_per_req,
    direction: "higher-bad",
    thresholds: { warning: 2, critical: 5 },
  },
  {
    name: "workflowGap",
    titleKey: "metrics.workflowGap",
    unit: "",
    format: (n) => String(Math.round(n)),
    value: (m) => m.workflow_gaps.total_incomplete,
    direction: "higher-bad",
    thresholds: { warning: 5, critical: 20 },
  },
  {
    name: "openRisks",
    titleKey: "metrics.openRisks",
    unit: "",
    format: (n) => String(Math.round(n)),
    value: (m) => m.open_risks.total,
    direction: "higher-bad",
    thresholds: { warning: 5, critical: 15 },
  },
  {
    name: "openRisksCritical",
    titleKey: "metrics.openRisksCritical",
    unit: "",
    format: (n) => String(Math.round(n)),
    value: (m) => m.open_risks.by_severity.critical ?? 0,
    direction: "higher-bad",
    thresholds: { warning: 1, critical: 3 },
  },
];

const MAX_HISTORY = 30;

// ---------------------------------------------------------------------------
// Help texts for metrics (Hilfsmodus)
// ---------------------------------------------------------------------------

const METRIC_HELP: Record<string, string> = {
  coverage:
    "Prozentsatz der Anforderungen mit mindestens einer Trace-Verbindung zu Testfällen oder Architektur-Elementen.",
  volatility:
    "Durchschnittliche Anzahl von Änderungen pro Anforderung über die Projektlaufzeit. Höhere Werte zeigen unstabile Anforderungen an.",
  workflowGap:
    "Anzahl unvollständiger Workflow-Schritte. Zeigt die Lücken zwischen geplanten und abgeschlossenen Aktivitäten.",
  openRisks:
    "Gesamtzahl der identifizierten offenen Risiken im Workspace, unabhängig vom Schweregrad.",
  openRisksCritical:
    "Anzahl der kritischen Risiken mit höchstem Schweregrad, die sofortige Aufmerksamkeit erfordern.",
};

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

function classify(spec: MetricTileSpec, value: number): Status {
  if (spec.direction === "info") return "neutral";
  if (spec.direction === "lower-bad") {
    if (value < spec.thresholds.critical) return "critical";
    if (value < spec.thresholds.warning) return "warning";
    return "healthy";
  }
  // higher-bad
  if (value >= spec.thresholds.critical) return "critical";
  if (value >= spec.thresholds.warning) return "warning";
  return "healthy";
}

const STATUS_COLORS: Record<Status, { fg: string; bg: string; labelKey: string }> = {
  healthy: { fg: "#10b981", bg: "rgba(16,185,129,0.12)", labelKey: "metrics.status.healthy" },
  warning: { fg: "#f59e0b", bg: "rgba(245,158,11,0.14)", labelKey: "metrics.status.warning" },
  critical: { fg: "#ef4444", bg: "rgba(239,68,68,0.14)", labelKey: "metrics.status.critical" },
  neutral: { fg: "#6b7280", bg: "rgba(107,114,128,0.12)", labelKey: "metrics.status.neutral" },
};

// ---------------------------------------------------------------------------
// Sparkline — inline SVG path (no external library)
// ---------------------------------------------------------------------------

interface SparklineProps {
  values: number[];
  color: string;
  width?: number;
  height?: number;
}

function Sparkline({
  values,
  color,
  width = 120,
  height = 32,
}: SparklineProps): JSX.Element {
  // Guard: empty → render a flat baseline so the layout is stable.
  const points = values.length > 0 ? values : [0];
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;

  // Reserve a few pixels of vertical padding so the line never touches the edge.
  const padY = 3;
  const usableH = height - padY * 2;

  // X is distributed evenly; Y is inverted (SVG origin = top-left).
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  const coords = points.map((v, i) => {
    const x = points.length > 1 ? i * stepX : width / 2;
    const y = padY + usableH - ((v - min) / range) * usableH;
    return { x, y };
  });

  const path = coords
    .map((c, i) => (i === 0 ? `M ${c.x.toFixed(1)} ${c.y.toFixed(1)}` : `L ${c.x.toFixed(1)} ${c.y.toFixed(1)}`))
    .join(" ");

  const last = coords[coords.length - 1];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="trend"
      data-testid="metric-sparkline"
      style={{ display: "block" }}
    >
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {points.length > 0 && last && (
        <circle cx={last.x} cy={last.y} r={2.5} fill={color} />
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Tile
// ---------------------------------------------------------------------------

interface MetricTileProps {
  spec: MetricTileSpec;
  history: number[];
  computedAt: string | null;
  isStale: boolean;
  helpMode?: boolean;
  helpText?: string;
}

function MetricTile({ spec, history, computedAt, isStale, helpMode = false, helpText }: MetricTileProps): JSX.Element {
  const { t } = useTranslation();
  const current = history.length > 0 ? history[history.length - 1] : 0;
  const status = classify(spec, current);
  const palette = STATUS_COLORS[status];

  return (
    <div
      data-testid={`metric-tile-${spec.name}`}
      style={{
        padding: "var(--space-4)",
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-lg)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-3)",
        boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
        opacity: isStale ? 0.6 : 1,
        transition: "var(--transition-fast, 0.15s ease)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-2)",
        }}
      >
        <span
          style={{
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            color: "var(--color-text)",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          {t(spec.titleKey, spec.name)}
        </span>
        <span
          data-testid={`metric-status-${spec.name}`}
          title={t(palette.labelKey, status)}
          style={{
            display: "inline-block",
            width: 12,
            height: 12,
            borderRadius: "50%",
            background: palette.fg,
            boxShadow: `0 0 0 4px ${palette.bg}`,
          }}
          aria-label={t(palette.labelKey, status)}
        />
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: "var(--space-1)",
        }}
      >
        <span
          data-testid={`metric-value-${spec.name}`}
          style={{
            fontSize: "var(--font-size-2xl, 1.5rem)",
            fontWeight: 700,
            color: "var(--color-text)",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {spec.format(current)}
        </span>
        {spec.unit && (
          <span
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
              fontWeight: 500,
            }}
          >
            {spec.unit}
          </span>
        )}
      </div>

      {helpMode && helpText && (
        <p
          data-testid={`metric-help-${spec.name}`}
          style={{
            fontSize: "var(--font-size-xs)",
            color: "var(--color-text-muted)",
            marginTop: "var(--space-1)",
            marginBottom: 0,
            fontStyle: "italic",
            lineHeight: 1.4,
          }}
        >
          {helpText}
        </p>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          gap: "var(--space-2)",
        }}
      >
        <Sparkline values={history} color={palette.fg} />
        <span
          style={{
            fontSize: "0.7rem",
            color: "var(--color-text-muted)",
            textAlign: "right",
            lineHeight: 1.3,
            maxWidth: "55%",
          }}
        >
          {computedAt ? (
            <>
              {t("metrics.lastUpdate", "Last update")}
              <br />
              {new Date(computedAt).toLocaleString()}
            </>
          ) : (
            "—"
          )}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard root
// ---------------------------------------------------------------------------

export default function MetricsDashboard(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();

  const [metrics, setMetrics] = useState<MetricsResult | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>("");
  // Per-tile value history. Keys match MetricTileSpec.name.
  const [history, setHistory] = useState<Record<string, number[]>>({});
  // Last successful fetch timestamp — drives the "isStale" flag after a refresh error.
  const [, setLastSuccessAt] = useState<number | null>(null);
  // Help mode toggle
  const [helpMode, setHelpMode] = useState<boolean>(false);

  const load = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await metricsApi.list(activeWorkspace.id, {
        type: typeFilter || undefined,
      });
      setMetrics(result);
      setLastSuccessAt(Date.now());
      // Append a new sample to each tile's history.
      setHistory((prev) => {
        const next: Record<string, number[]> = { ...prev };
        for (const spec of TILES) {
          const series = next[spec.name] ?? [];
          const updated = [...series, spec.value(result)];
          if (updated.length > MAX_HISTORY) updated.splice(0, updated.length - MAX_HISTORY);
          next[spec.name] = updated;
        }
        return next;
      });
    } catch (err) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, typeFilter]);

  useEffect(() => {
    void load();
    // Reset history when workspace or filter changes.
    setHistory({});
    // load intentionally omitted: we want a fresh load + history reset on filter change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeWorkspace?.id, typeFilter]);

  const isStale = useMemo(
    () => isLoading === false && error !== null && metrics !== null,
    [isLoading, error, metrics],
  );

  const computedAt = metrics?.computed_at ?? null;
  const warningCount = metrics?.warnings.length ?? 0;

  return (
    <div data-testid="metrics-dashboard">
      <PageHeader
        title={t("metrics.title", "SE Process Metrics")}
        summary={t(
          "metrics.pageSummary",
          "SE-Prozess-Kennzahlen: Traceability-Coverage, Volatilität, Workflow-Lücken und Risiken auf einen Blick.",
        )}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          marginBottom: "var(--space-6)",
          gap: "var(--space-2)",
          flexWrap: "wrap",
        }}
      >
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-2)",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
          }}
        >
          {t("metrics.filter", "Filter")}
          <select
            data-testid="metrics-filter-select"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            disabled={isLoading}
            style={{
              padding: "var(--space-1) var(--space-2)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              background: "var(--color-surface)",
              color: "var(--color-text)",
              fontSize: "var(--font-size-sm)",
              fontFamily: "inherit",
            }}
          >
            <option value="">{t("metrics.filterAll", "All")}</option>
            <option value="coverage">{t("metrics.coverage", "Coverage")}</option>
            <option value="volatility">{t("metrics.volatility", "Volatility")}</option>
            <option value="workflow_gaps">
              {t("metrics.workflowGap", "Workflow Gap")}
            </option>
            <option value="open_risks">{t("metrics.openRisks", "Open Risks")}</option>
          </select>
        </label>

        <button
          type="button"
          data-testid="metrics-help-toggle-btn"
          onClick={() => setHelpMode((h) => !h)}
          title={helpMode ? "Hide help" : "Show help"}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 28,
            height: 28,
            background: helpMode ? "var(--color-primary)" : "transparent",
            color: helpMode ? "white" : "var(--color-text-muted)",
            border: "1px solid var(--color-border)",
            borderRadius: "50%",
            cursor: "pointer",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            fontFamily: "inherit",
            padding: 0,
            transition: "var(--transition-fast, 0.15s ease)",
          }}
        >
          ?
        </button>

        <button
          type="button"
          data-testid="metrics-refresh-btn"
          onClick={() => void load()}
          disabled={isLoading}
          style={{
            padding: "var(--space-2) var(--space-4)",
            background: "var(--color-primary)",
            color: "white",
            border: "none",
            borderRadius: "var(--radius-md)",
            cursor: isLoading ? "not-allowed" : "pointer",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            fontFamily: "inherit",
            opacity: isLoading ? 0.6 : 1,
          }}
        >
          {isLoading
            ? t("metrics.refreshing", "Refreshing...")
            : t("metrics.refresh", "Refresh")}
        </button>
      </div>

      {error && (
        <div
          role="alert"
          data-testid="metrics-error"
          style={{
            padding: "var(--space-3) var(--space-4)",
            marginBottom: "var(--space-4)",
            background: "rgba(239,68,68,0.10)",
            border: "1px solid var(--color-danger, #ef4444)",
            borderRadius: "var(--radius-md)",
            color: "var(--color-danger, #ef4444)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {error}
        </div>
      )}

      {warningCount > 0 && metrics && (
        <ul
          data-testid="metrics-warnings"
          style={{
            listStyle: "none",
            padding: "var(--space-3) var(--space-4)",
            marginBottom: "var(--space-4)",
            background: "rgba(245,158,11,0.10)",
            border: "1px solid rgba(245,158,11,0.5)",
            borderRadius: "var(--radius-md)",
            color: "var(--color-text)",
            fontSize: "var(--font-size-sm)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-1)",
          }}
        >
          {metrics.warnings.map((w, i) => (
            <li key={`${w.metric}-${i}`}>
              <strong>{w.metric}:</strong> {w.description}
            </li>
          ))}
        </ul>
      )}

      {!activeWorkspace ? (
        <p style={{ color: "var(--color-text-muted)" }}>
          {t("metrics.noWorkspace", "Select a workspace to view metrics.")}
        </p>
      ) : isLoading && !metrics ? (
        <p data-testid="metrics-loading">{t("loading", "Loading...")}</p>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: "var(--space-4)",
          }}
        >
          {TILES.map((spec) => (
            <MetricTile
              key={spec.name}
              spec={spec}
              history={history[spec.name] ?? []}
              computedAt={computedAt}
              isStale={isStale}
              helpMode={helpMode}
              helpText={METRIC_HELP[spec.name]}
            />
          ))}
        </div>
      )}

      {metrics && (
        <div
          style={{
            marginTop: "var(--space-6)",
            padding: "var(--space-3) var(--space-4)",
            background: "var(--color-surface-raised)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-md)",
            color: "var(--color-text-muted)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {t("metrics.timeframe", "Timeframe")}: <strong>{metrics.timeframe}</strong>
          {" · "}
          {t("metrics.workspace", "Workspace")}: <code>{metrics.workspace_id}</code>
        </div>
      )}
    </div>
  );
}
