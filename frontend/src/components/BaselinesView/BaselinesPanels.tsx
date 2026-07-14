/**
 * ARCH-L1-001 ReactFrontend — Baselines panels (Presenters).
 *
 * leaf_id: COMP-RF-002 (BaselinesView)
 * req_id:  REQ-L2-BL-012 (captured entries), REQ-L2-BL-003 (field-level diff),
 *          REQ-006 (diff item rows), REQ-050 (Container/Presenter decomposition)
 *
 * Pure presentational sub-components for BaselinesView: the captured-entries
 * section, the compare panel and the diff-item rows. Extracted verbatim from
 * the former monolithic BaselinesView; all state is driven by props.
 */

import { memo } from "react";
import { useTranslation } from "react-i18next";
import type {
  Baseline,
  BaselineDeltaEntry,
  BaselineDiff,
  DiffItem,
} from "../../api/baselines";

interface BaselineEntriesSectionProps {
  entries: BaselineDeltaEntry[] | null;
  loading: boolean;
  error: string | null;
}

/** Human-readable label for a captured entry, derived from its state. */
function entryLabel(entry: BaselineDeltaEntry): string {
  const s = entry.state;
  if (s && typeof s === "object") {
    const title = (s.title ?? s.term ?? s.name) as string | undefined;
    if (title) return title;
    if (entry.entity_type === "trace_link") {
      const linkType = (s.link_type as string | undefined) ?? "trace";
      return `${linkType} link`;
    }
  }
  return `${entry.item_id.slice(0, 8)}…`;
}

/**
 * Renders the list of captured items for a baseline. When an entry carries a
 * full-state snapshot (REQ-L2-BL-012) its field values are shown; legacy
 * entries with a null state degrade to the version number only.
 */
export function BaselineEntriesSection({
  entries,
  loading,
  error,
}: BaselineEntriesSectionProps): JSX.Element {
  const { t } = useTranslation();

  const heading = (
    <h3
      style={{
        fontSize: "var(--font-size-base)",
        fontWeight: 700,
        color: "var(--color-text)",
        marginTop: 0,
        marginBottom: "var(--space-3)",
      }}
    >
      {t("baselines.capturedItems", "Captured items")}
      {entries ? ` (${entries.length})` : ""}
    </h3>
  );

  if (loading) {
    return (
      <section data-testid="baseline-entries" style={entriesSectionStyle}>
        {heading}
        <p style={mutedTextStyle}>{t("loading", "Loading…")}</p>
      </section>
    );
  }

  if (error) {
    return (
      <section data-testid="baseline-entries" style={entriesSectionStyle}>
        {heading}
        <p role="alert" style={{ ...mutedTextStyle, color: "var(--color-danger)" }}>
          {error}
        </p>
      </section>
    );
  }

  if (!entries || entries.length === 0) {
    return (
      <section data-testid="baseline-entries" style={entriesSectionStyle}>
        {heading}
        <p data-testid="baseline-entries-empty" style={mutedTextStyle}>
          {t("baselines.noCapturedItems", "No captured items.")}
        </p>
      </section>
    );
  }

  return (
    <section data-testid="baseline-entries" style={entriesSectionStyle}>
      {heading}
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {entries.map((entry) => (
          <li
            key={entry.item_id}
            data-testid="baseline-entry-item"
            style={{
              padding: "var(--space-3)",
              marginBottom: "var(--space-2)",
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
                marginBottom: entry.state ? "var(--space-2)" : 0,
              }}
            >
              <span
                data-testid="baseline-entry-type"
                style={{
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                }}
              >
                {entry.entity_type}
              </span>
              <strong
                style={{
                  flex: 1,
                  color: "var(--color-text)",
                  fontSize: "var(--font-size-sm)",
                }}
              >
                {entryLabel(entry)}
              </strong>
              <span
                style={{
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text-muted)",
                }}
              >
                v{entry.version}
              </span>
            </div>

            {entry.state ? (
              <dl
                data-testid="baseline-entry-state"
                style={{
                  display: "grid",
                  gridTemplateColumns: "160px 1fr",
                  rowGap: "var(--space-1)",
                  columnGap: "var(--space-3)",
                  margin: 0,
                }}
              >
                {Object.entries(entry.state).map(([key, value]) => (
                  <div key={key} style={{ display: "contents" }}>
                    <dt
                      style={{
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {key}
                    </dt>
                    <dd
                      style={{
                        margin: 0,
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text)",
                        wordBreak: "break-word",
                      }}
                    >
                      {formatStateValue(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p
                data-testid="baseline-entry-legacy"
                style={{ ...mutedTextStyle, margin: 0 }}
              >
                {t(
                  "baselines.legacyEntry",
                  "No detailed state available (legacy baseline)."
                )}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Render a JSON state value as a compact string. */
function formatStateValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) {
    return value.length === 0 ? "—" : value.map((v) => String(v)).join(", ");
  }
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

const entriesSectionStyle: React.CSSProperties = {
  marginBottom: "var(--space-6)",
};

const mutedTextStyle: React.CSSProperties = {
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text-muted)",
};

// ---------------------------------------------------------------------------
// REQ-L2-BL-003: baseline compare panel (field-level diff)
// ---------------------------------------------------------------------------

interface BaselineComparePanelProps {
  baselines: Baseline[];
  aId: string;
  bId: string;
  onChangeA: (id: string) => void;
  onChangeB: (id: string) => void;
  onCompare: () => void;
  diff: BaselineDiff | null;
  loading: boolean;
  error: string | null;
}

function baselineOptionLabel(bl: Baseline): string {
  const name = bl.name || `${bl.id.slice(0, 8)}…`;
  return `${name} (${bl.scope})`;
}

/** Colour token for a diff status badge. */
function statusColor(status: DiffItem["status"]): string {
  if (status === "added") return "var(--color-success)";
  if (status === "removed") return "var(--color-danger)";
  return "var(--color-warning)";
}

const compareSelectStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-base)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
};

/**
 * Renders the baseline-compare form (pick two baselines) and the resulting
 * field-level diff (REQ-L2-BL-003). Summary counts are always shown; changed
 * items with field-level snapshots expand to a Before/After table.
 */
export function BaselineComparePanel({
  baselines,
  aId,
  bId,
  onChangeA,
  onChangeB,
  onCompare,
  diff,
  loading,
  error,
}: BaselineComparePanelProps): JSX.Element {
  const { t } = useTranslation();
  const disabled = !aId || !bId || aId === bId || loading;

  return (
    <div data-testid="baseline-compare-panel" style={{ maxWidth: "680px" }}>
      <h3
        style={{
          fontSize: "var(--font-size-lg)",
          fontWeight: 700,
          marginTop: 0,
          marginBottom: "var(--space-4)",
          color: "var(--color-text)",
        }}
      >
        {t("baselines.compareTitle", "Compare baselines")}
      </h3>

      <div
        style={{
          display: "flex",
          gap: "var(--space-3)",
          alignItems: "flex-end",
          flexWrap: "wrap",
          marginBottom: "var(--space-4)",
        }}
      >
        <label
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-1)",
            flex: "1 1 220px",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text)",
          }}
        >
          <span>{t("baselines.compareA", "Baseline A (from)")}</span>
          <select
            data-testid="compare-select-a"
            value={aId}
            onChange={(e) => onChangeA(e.target.value)}
            style={compareSelectStyle}
          >
            <option value="">—</option>
            {baselines.map((bl) => (
              <option key={bl.id} value={bl.id}>
                {baselineOptionLabel(bl)}
              </option>
            ))}
          </select>
        </label>

        <label
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-1)",
            flex: "1 1 220px",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text)",
          }}
        >
          <span>{t("baselines.compareB", "Baseline B (to)")}</span>
          <select
            data-testid="compare-select-b"
            value={bId}
            onChange={(e) => onChangeB(e.target.value)}
            style={compareSelectStyle}
          >
            <option value="">—</option>
            {baselines.map((bl) => (
              <option key={bl.id} value={bl.id}>
                {baselineOptionLabel(bl)}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          data-testid="compare-run-btn"
          onClick={onCompare}
          disabled={disabled}
          style={{
            background: "var(--color-primary)",
            color: "white",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-5)",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            cursor: disabled ? "not-allowed" : "pointer",
            opacity: disabled ? 0.6 : 1,
          }}
        >
          {loading
            ? t("baselines.comparing", "Comparing…")
            : t("baselines.compareRun", "Compare")}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          data-testid="compare-error"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
            margin: "0 0 var(--space-3) 0",
          }}
        >
          {error}
        </p>
      )}

      {diff && !loading && (
        <div data-testid="compare-result">
          <div
            data-testid="compare-summary"
            style={{
              display: "flex",
              gap: "var(--space-3)",
              marginBottom: "var(--space-4)",
              flexWrap: "wrap",
            }}
          >
            <SummaryBadge
              label={t("baselines.added", "Added")}
              count={diff.summary.added}
              color="var(--color-success)"
              testid="compare-summary-added"
            />
            <SummaryBadge
              label={t("baselines.removed", "Removed")}
              count={diff.summary.removed}
              color="var(--color-danger)"
              testid="compare-summary-removed"
            />
            <SummaryBadge
              label={t("baselines.changed", "Changed")}
              count={diff.summary.changed}
              color="var(--color-warning)"
              testid="compare-summary-changed"
            />
          </div>

          {diff.items.length === 0 ? (
            <p data-testid="compare-empty" style={mutedTextStyle}>
              {t("baselines.compareNoChanges", "No differences between the baselines.")}
            </p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {diff.items.map((item) => (
                <DiffItemRow key={`${item.status}-${item.item_id}`} item={item} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

interface SummaryBadgeProps {
  label: string;
  count: number;
  color: string;
  testid: string;
}

// REQ-092: memoized for performance — pure presentational badge that only
// receives primitive props, so it never needs to re-render while its parent
// (compare panel) updates unrelated state.
const SummaryBadge = memo(function SummaryBadge({
  label,
  count,
  color,
  testid,
}: SummaryBadgeProps): JSX.Element {
  return (
    <span
      data-testid={testid}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2)",
        padding: "var(--space-2) var(--space-3)",
        borderRadius: "var(--radius-md)",
        border: `1px solid ${color}`,
        fontSize: "var(--font-size-sm)",
        fontWeight: 600,
        color: "var(--color-text)",
      }}
    >
      <span style={{ color }}>{count}</span>
      {label}
    </span>
  );
});

/**
 * A single diff item: added/removed as a row, changed as a collapsible table.
 *
 * REQ-092: memoized for performance — rendered once per diff entry in a list
 * (potentially hundreds of rows). ``item`` is a stable reference from the diff
 * payload, so memo prevents re-rendering every row when the parent re-renders
 * for unrelated reasons (e.g. loading flags, hover state).
 */
export const DiffItemRow = memo(function DiffItemRow({
  item,
}: {
  item: DiffItem;
}): JSX.Element {
  const { t } = useTranslation();
  const hasFieldChanges =
    item.status === "changed" &&
    item.field_changes != null &&
    item.field_changes.length > 0;

  const header = (
    <>
      <span
        data-testid="diff-item-status"
        style={{
          fontSize: "var(--font-size-xs)",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: statusColor(item.status),
        }}
      >
        {item.status}
      </span>
      <span
        style={{
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
        }}
      >
        {item.entity_type}
      </span>
      {item.artifact_name ? (
        <span
          data-testid="diff-item-name"
          style={{
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text)",
            fontWeight: 600,
          }}
        >
          {item.artifact_name}
        </span>
      ) : (
        <code
          data-testid="diff-item-name"
          style={{
            fontFamily: "monospace",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text)",
          }}
        >
          {item.item_id.slice(0, 8)}…
        </code>
      )}
    </>
  );

  const rowStyle: React.CSSProperties = {
    padding: "var(--space-3)",
    marginBottom: "var(--space-2)",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
  };

  if (!hasFieldChanges) {
    return (
      <li data-testid="diff-item" data-status={item.status} style={rowStyle}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
          }}
        >
          {header}
        </div>
      </li>
    );
  }

  return (
    <li data-testid="diff-item" data-status={item.status} style={rowStyle}>
      <details>
        <summary
          data-testid="diff-item-toggle"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
            cursor: "pointer",
          }}
        >
          {header}
          <span style={{ ...mutedTextStyle, marginLeft: "auto" }}>
            {t("baselines.fieldChangesCount", {
              count: item.field_changes?.length ?? 0,
              defaultValue: "{{count}} field(s)",
            })}
          </span>
        </summary>
        <table
          data-testid="diff-field-table"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            marginTop: "var(--space-3)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          <thead>
            <tr>
              <th style={diffThStyle}>{t("baselines.field", "Field")}</th>
              <th style={diffThStyle}>{t("baselines.before", "Before")}</th>
              <th style={diffThStyle}>{t("baselines.after", "After")}</th>
            </tr>
          </thead>
          <tbody>
            {(item.field_changes ?? []).map((fc) => (
              <tr key={fc.field_name} data-testid="diff-field-row">
                <td style={diffTdStyle}>{fc.field_name}</td>
                <td
                  style={{ ...diffTdStyle, color: "var(--color-danger)" }}
                  data-testid="diff-field-old"
                >
                  {formatStateValue(fc.old_value)}
                </td>
                <td
                  style={{ ...diffTdStyle, color: "var(--color-success)" }}
                  data-testid="diff-field-new"
                >
                  {formatStateValue(fc.new_value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </li>
  );
});

const diffThStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "var(--space-2)",
  borderBottom: "1px solid var(--color-border)",
  color: "var(--color-text-muted)",
  fontWeight: 600,
  fontSize: "var(--font-size-xs)",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const diffTdStyle: React.CSSProperties = {
  padding: "var(--space-2)",
  borderBottom: "1px solid var(--color-border)",
  wordBreak: "break-word",
  verticalAlign: "top",
};
