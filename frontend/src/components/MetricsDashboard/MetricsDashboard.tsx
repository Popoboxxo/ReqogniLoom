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
import styles from "./MetricsDashboard.module.css";

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
  /**
   * UI-35: returns true when the metric has no meaningful basis to compute
   * from (e.g. zero requirements to cover, zero requirements to average
   * volatility over) — the tile should show a "not calculated" empty state
   * instead of a misleading 0/0-derived value with a healthy-looking color.
   */
  notComputed?: (m: MetricsResult) => boolean;
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
    notComputed: (m) => m.traceability_coverage.total === 0,
  },
  {
    name: "volatility",
    titleKey: "metrics.volatility",
    unit: "/req",
    format: (n) => n.toFixed(2),
    value: (m) => m.volatility.avg_changes_per_req,
    direction: "higher-bad",
    thresholds: { warning: 2, critical: 5 },
    notComputed: (m) => m.volatility.total_requirements === 0,
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
//
// BUG-10 (SYSTEMAUDIT_2026-08-18 §4): these values are only the `t()`
// fallback default now (see the `helpText={t(...)}` call site below) — they
// used to be rendered directly via `METRIC_HELP[spec.name]` with no i18n
// key at all, so the tile's "Show help" text was always German regardless
// of the active UI language. Real translations live under `metrics.help.*`
// in `frontend/src/i18n/locales/{de,en}.json`.
// ---------------------------------------------------------------------------

const METRIC_HELP: Record<MetricTileSpec["name"], string> = {
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

// Issue #876 (Etappe 5): the per-status fg colour is still read here for the
// sparkline's SVG stroke/fill (an SVG attribute, not a CSS property), while the
// status dot's fg + translucent halo moved onto one CSS class per status —
// composed at the call site instead of a computed inline `background`/
// `boxShadow` (see MetricsDashboard.module.css).
const STATUS_COLORS: Record<Status, { fg: string; labelKey: string }> = {
  healthy: { fg: "var(--color-metric-healthy)", labelKey: "metrics.status.healthy" },
  warning: { fg: "var(--color-metric-warning)", labelKey: "metrics.status.warning" },
  critical: { fg: "var(--color-metric-critical)", labelKey: "metrics.status.critical" },
  neutral: { fg: "var(--color-metric-neutral)", labelKey: "metrics.status.neutral" },
};

const STATUS_DOT_CLASS: Record<Status, string> = {
  healthy: styles.statusDotHealthy,
  warning: styles.statusDotWarning,
  critical: styles.statusDotCritical,
  neutral: styles.statusDotNeutral,
};

// ---------------------------------------------------------------------------
// Sparkline — inline SVG path (no external library)
// ---------------------------------------------------------------------------

interface SparklineProps {
  values: number[];
  color: string;
  width?: number;
  height?: number;
  /** UI-35: unique data-testid — 5 tiles previously shared "metric-sparkline". */
  testId: string;
  /** UI-35: unique accessible name — 5 tiles previously shared aria-label="trend". */
  label: string;
}

function Sparkline({
  values,
  color,
  width = 120,
  height = 32,
  testId,
  label,
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
      aria-label={label}
      data-testid={testId}
      className={styles.sparkline}
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
  /** UI-35: true when the current metric has no basis to compute a value from. */
  notComputed?: boolean;
}

function MetricTile({
  spec,
  history,
  computedAt,
  isStale,
  helpMode = false,
  helpText,
  notComputed = false,
}: MetricTileProps): JSX.Element {
  const { t } = useTranslation();
  const current = history.length > 0 ? history[history.length - 1] : 0;
  const status = notComputed ? "neutral" : classify(spec, current);
  const palette = STATUS_COLORS[status];
  const tileTitle = t(spec.titleKey, spec.name);

  return (
    <div
      data-testid={`metric-tile-${spec.name}`}
      className={styles.tile + (isStale ? ' ' + styles.tileStale : '')}
    >
      <div className={styles.tileHeader}>
        <span className={styles.tileTitle}>
          {tileTitle}
        </span>
        <span
          data-testid={`metric-status-${spec.name}`}
          title={t(palette.labelKey, status)}
          className={styles.statusDot + ' ' + STATUS_DOT_CLASS[status]}
          // GESAMTTEST_BERICHT_2026-08-21.md §5 finding 7: aria-label on a
          // roleless <span> is not reliably exposed by all screen readers.
          // This is a purely visual status-dot icon (color-coded ok/warning/
          // critical), not a live-updating ARIA live region — role="img"
          // (with the existing aria-label as its accessible name) is the
          // correct semantic role, matching the icon-like status pattern.
          role="img"
          aria-label={t(palette.labelKey, status)}
        />
      </div>

      <div className={styles.valueRow}>
        {notComputed ? (
          <span
            data-testid={`metric-value-${spec.name}`}
            className={styles.notComputedValue}
          >
            {t("metrics.notComputed", "Not calculated")}
          </span>
        ) : (
          <>
            <span
              data-testid={`metric-value-${spec.name}`}
              className={styles.currentValue}
            >
              {spec.format(current)}
            </span>
            {spec.unit && (
              <span className={styles.unit}>
                {spec.unit}
              </span>
            )}
          </>
        )}
      </div>

      {spec.direction !== "info" && (
        <span
          data-testid={`metric-thresholds-${spec.name}`}
          className={styles.thresholds}
        >
          {spec.direction === "lower-bad"
            ? t("metrics.thresholdLowerBad", "Warning < {{warning}}{{unit}} · Critical < {{critical}}{{unit}}", {
                warning: spec.thresholds.warning,
                critical: spec.thresholds.critical,
                unit: spec.unit,
              })
            : t("metrics.thresholdHigherBad", "Warning ≥ {{warning}}{{unit}} · Critical ≥ {{critical}}{{unit}}", {
                warning: spec.thresholds.warning,
                critical: spec.thresholds.critical,
                unit: spec.unit,
              })}
        </span>
      )}

      {helpMode && helpText && (
        <p
          data-testid={`metric-help-${spec.name}`}
          className={styles.helpText}
        >
          {helpText}
        </p>
      )}

      <div className={styles.tileFooter}>
        <Sparkline
          values={history}
          color={palette.fg}
          testId={`metric-sparkline-${spec.name}`}
          label={t("metrics.trendLabel", "{{metric}} trend", { metric: tileTitle })}
        />
        <span
          data-testid="metric-last-update"
          className={styles.lastUpdate}
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

  // Issue #876 (Etappe 5) — FINDING: the help toggle's on/off fill stays on the
  // `style` prop as a computed identifier instead of a `...Active`/`...Inactive`
  // class pair. A pre-existing test pins this exact inline contract
  // (`MetricsDashboard.test.tsx`: `toHaveStyle("background: transparent")` /
  // `toHaveStyle("background: var(--color-primary)")`), and jsdom does not load
  // CSS modules, so a class-based fill cannot satisfy it. Migrating it needs the
  // test updated in the same change; that file is outside this etappe's
  // file scope, so it is reported rather than silently rebuilt.
  const helpToggleStyle = {
    background: helpMode ? "var(--color-primary)" : "transparent",
    color: helpMode ? "var(--color-on-primary)" : "var(--color-text-muted)",
  } as const;

  return (
    <div data-testid="metrics-dashboard">
      <PageHeader
        title={t("metrics.title", "SE Process Metrics")}
        summary={t(
          "metrics.pageSummary",
          "SE-Prozess-Kennzahlen: Traceability-Coverage, Volatilität, Workflow-Lücken und Risiken auf einen Blick.",
        )}
      />

      <div className={styles.controlsRow}>
        <label className={styles.filterLabel}>
          {t("metrics.filter", "Filter")}
          <select
            data-testid="metrics-filter-select"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className={styles.filterSelect}
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
          title={
            helpMode
              ? t("metrics.hideHelp", "Hide help")
              : t("metrics.showHelp", "Show help")
          }
          aria-label={
            helpMode
              ? t("metrics.hideHelp", "Hide help")
              : t("metrics.showHelp", "Show help")
          }
          aria-pressed={helpMode}
          className={styles.helpToggle}
          style={helpToggleStyle}
        >
          ?
        </button>

        <button
          type="button"
          data-testid="metrics-refresh-btn"
          onClick={() => void load()}
          disabled={isLoading}
          className={
            styles.refreshButton +
            ' ' +
            (isLoading ? styles.refreshDisabled : styles.refreshEnabled)
          }
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
          className={styles.errorBanner}
        >
          {error}
        </div>
      )}

      {warningCount > 0 && metrics && (
        <ul
          data-testid="metrics-warnings"
          className={styles.warningsList}
        >
          {metrics.warnings.map((w, i) => (
            <li key={`${w.metric}-${i}`}>
              <strong>{w.metric}:</strong> {w.description}
            </li>
          ))}
        </ul>
      )}

      {!activeWorkspace ? (
        <p className={styles.mutedText}>
          {t("metrics.noWorkspace", "Select a workspace to view metrics.")}
        </p>
      ) : isLoading && !metrics ? (
        <p data-testid="metrics-loading">{t("loading", "Loading...")}</p>
      ) : (
        /* #809/#806: the tile grid's responsive column contract (1/3/5
           columns — never a lone tile on a short row, always a full-width
           row) lives in MetricsDashboard.module.css. An inline capped
           `repeat(auto-fit, minmax(260px, 320px))` template left the fifth
           tile alone on a second row at the viewport widths that fit exactly
           four tracks. */
        <div className={styles.tileGrid} data-testid="metrics-tile-grid">
          {TILES.map((spec) => (
            <MetricTile
              key={spec.name}
              spec={spec}
              history={history[spec.name] ?? []}
              computedAt={computedAt}
              isStale={isStale}
              helpMode={helpMode}
              helpText={t(`metrics.help.${spec.name}`, METRIC_HELP[spec.name])}
              notComputed={metrics ? (spec.notComputed?.(metrics) ?? false) : false}
            />
          ))}
        </div>
      )}

      {metrics && (
        <div
          data-testid="metrics-scope-footer"
          className={styles.scopeFooter}
        >
          {t("metrics.timeframe", "Timeframe")}: <strong>{metrics.timeframe}</strong>
          {" · "}
          {t("metrics.workspace", "Workspace")}: <code>{metrics.workspace_id}</code>
        </div>
      )}
    </div>
  );
}
