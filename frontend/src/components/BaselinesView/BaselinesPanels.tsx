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
import styles from "./BaselinesPanels.module.css";

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
    <h3 className={styles.heading}>
      {t("baselines.capturedItems", "Captured items")}
      {entries ? ` (${entries.length})` : ""}
    </h3>
  );

  if (loading) {
    return (
      <section data-testid="baseline-entries" className={styles.section}>
        {heading}
        <p className={styles.mutedText}>{t("loading", "Loading…")}</p>
      </section>
    );
  }

  if (error) {
    return (
      <section data-testid="baseline-entries" className={styles.section}>
        {heading}
        <p role="alert" className={`${styles.mutedText} ${styles.mutedTextDanger}`}>
          {error}
        </p>
      </section>
    );
  }

  if (!entries || entries.length === 0) {
    return (
      <section data-testid="baseline-entries" className={styles.section}>
        {heading}
        <p data-testid="baseline-entries-empty" className={styles.mutedText}>
          {t("baselines.noCapturedItems", "No captured items.")}
        </p>
      </section>
    );
  }

  return (
    <section data-testid="baseline-entries" className={styles.section}>
      {heading}
      <ul className={styles.entriesList}>
        {entries.map((entry) => (
          <li
            key={entry.item_id}
            data-testid="baseline-entry-item"
            className={styles.entryItem}
          >
            <div
              className={styles.entryHeaderRow}
              style={{ marginBottom: entry.state ? "var(--space-2)" : 0 }}
            >
              <span
                data-testid="baseline-entry-type"
                className={styles.entryType}
              >
                {entry.entity_type}
              </span>
              <strong className={styles.entryLabel}>
                {entryLabel(entry)}
              </strong>
              <span className={styles.entryVersion}>
                v{entry.version}
              </span>
            </div>

            {entry.state ? (
              <dl
                data-testid="baseline-entry-state"
                className={styles.entryState}
              >
                {Object.entries(entry.state).map(([key, value]) => (
                  <div key={key} className={styles.entryStateRow}>
                    <dt className={styles.entryStateKey}>
                      {key}
                    </dt>
                    <dd className={styles.entryStateValue}>
                      {formatStateValue(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p
                data-testid="baseline-entry-legacy"
                className={`${styles.mutedText} ${styles.entryLegacy}`}
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
    <div data-testid="baseline-compare-panel" className={styles.comparePanel}>
      <h3 className={styles.compareHeading}>
        {t("baselines.compareTitle", "Compare baselines")}
      </h3>

      <div className={styles.compareRow}>
        <label className={styles.compareField}>
          <span>{t("baselines.compareA", "Baseline A (from)")}</span>
          <select
            data-testid="compare-select-a"
            value={aId}
            onChange={(e) => onChangeA(e.target.value)}
            className={styles.compareSelect}
          >
            <option value="">—</option>
            {baselines.map((bl) => (
              <option key={bl.id} value={bl.id}>
                {baselineOptionLabel(bl)}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.compareField}>
          <span>{t("baselines.compareB", "Baseline B (to)")}</span>
          <select
            data-testid="compare-select-b"
            value={bId}
            onChange={(e) => onChangeB(e.target.value)}
            className={styles.compareSelect}
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
          className={`${styles.compareRunBtn} ${disabled ? styles.compareRunBtnDisabled : styles.compareRunBtnEnabled}`}
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
          className={styles.compareError}
        >
          {error}
        </p>
      )}

      {diff && !loading && (
        <div data-testid="compare-result">
          <div
            data-testid="compare-summary"
            className={styles.compareSummary}
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
            <p data-testid="compare-empty" className={styles.mutedText}>
              {t("baselines.compareNoChanges", "No differences between the baselines.")}
            </p>
          ) : (
            <ul className={styles.diffList}>
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
      className={styles.summaryBadge}
      style={{ border: `1px solid ${color}` }}
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
        className={styles.diffStatus}
        style={{ color: statusColor(item.status) }}
      >
        {item.status}
      </span>
      <span className={styles.diffEntityType}>
        {item.entity_type}
      </span>
      {item.artifact_name ? (
        <span
          data-testid="diff-item-name"
          className={styles.diffName}
        >
          {item.artifact_name}
        </span>
      ) : (
        <code
          data-testid="diff-item-name"
          className={styles.diffNameCode}
        >
          {item.item_id.slice(0, 8)}…
        </code>
      )}
    </>
  );

  if (!hasFieldChanges) {
    return (
      <li data-testid="diff-item" data-status={item.status} className={styles.diffRow}>
        <div className={styles.diffHeaderRow}>
          {header}
        </div>
      </li>
    );
  }

  return (
    <li data-testid="diff-item" data-status={item.status} className={styles.diffRow}>
      <details>
        <summary
          data-testid="diff-item-toggle"
          className={styles.diffSummaryToggle}
        >
          {header}
          <span className={`${styles.mutedText} ${styles.diffFieldCount}`}>
            {t("baselines.fieldChangesCount", {
              count: item.field_changes?.length ?? 0,
              defaultValue: "{{count}} field(s)",
            })}
          </span>
        </summary>
        <table
          data-testid="diff-field-table"
          className={styles.diffTable}
        >
          <thead>
            <tr>
              <th className={styles.diffTh}>{t("baselines.field", "Field")}</th>
              <th className={styles.diffTh}>{t("baselines.before", "Before")}</th>
              <th className={styles.diffTh}>{t("baselines.after", "After")}</th>
            </tr>
          </thead>
          <tbody>
            {(item.field_changes ?? []).map((fc) => (
              <tr key={fc.field_name} data-testid="diff-field-row">
                <td className={styles.diffTd}>{fc.field_name}</td>
                <td
                  className={`${styles.diffTd} ${styles.diffTdOld}`}
                  data-testid="diff-field-old"
                >
                  {formatStateValue(fc.old_value)}
                </td>
                <td
                  className={`${styles.diffTd} ${styles.diffTdNew}`}
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
