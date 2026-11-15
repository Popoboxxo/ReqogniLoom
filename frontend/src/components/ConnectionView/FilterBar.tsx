/**
 * ARCH-L1-001 ReactFrontend — connection view filter bar (P3 Task 3.2, V.4).
 *
 * V.4 splits the bar into two rows (design §5.5):
 *
 * - **Row 1, always visible**: the four quick filters, the free-text search,
 *   the "Weitere Filter" trigger and the counters. These are the filters a
 *   reader reaches for on every visit.
 * - **Row 2, a popover** (`filter-more`): tier, type, category, state, element
 *   subtree, group and the saved views. The trigger carries the number of
 *   *active* popover filters, so a collapsed row cannot silently hide a filter.
 *
 * The open/closed state is **not** URL state. The URL stays the source of truth
 * for a filter *value*; the preference `ui.connection_view.filters_expanded`
 * (owned by `ConnectionView`) is the source of truth for the row's visibility.
 * That is why this component is presentational: it renders `expanded` and
 * reports the toggle upwards instead of keeping its own copy.
 *
 * A failed preference write is reported here — inside the popover, next to the
 * controls it belongs to — and never closes it: the local state stays
 * authoritative while the message explains that it was not persisted.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { AllocationRow, WorkspaceTier } from "../../api/allocation-view";
import type { SavedConnectionView } from "../../api/connection-views";
import type {
  ConnectionFilters,
  ConnectionGroupOption,
} from "./useAllocationView";
import styles from "./ConnectionView.module.css";

const REQUIREMENT_TYPES = ["SyReq", "UseCase", "FeatureReq"] as const;

/** Id of the popover, so the trigger's `aria-controls` resolves. */
const MORE_FILTERS_ID = "connection-filter-more";

export interface ConnectionMeta {
  total: number;
  unallocated: number;
  locked: number;
  findings: number;
}

export interface FilterBarProps {
  filters: ConnectionFilters;
  meta: ConnectionMeta;
  tiers: WorkspaceTier[];
  elements: AllocationRow[];
  /** P6 Task 6.3: visual groups for the `group` filter (empty hides it). */
  groups: ConnectionGroupOption[];
  states: string[];
  categories: string[];
  savedViews: SavedConnectionView[];
  /** Whether the "Weitere Filter" popover is open (preference-backed). */
  expanded: boolean;
  onToggleExpanded: () => void;
  /** A rejected expand-state write; the popover stays open and shows it. */
  expandedError?: string | null;
  onChange: (patch: Partial<ConnectionFilters>) => void;
  onReset: () => void;
  onSaveView: (name: string) => void;
  onApplyView: (view: SavedConnectionView) => void;
  onDeleteView: (id: string) => void;
}

/** The popover's filter fields — the ones the badge counts. */
function countActiveMoreFilters(filters: ConnectionFilters): number {
  return [
    filters.tier,
    filters.type,
    filters.category,
    filters.state,
    filters.elementSubtree,
    filters.group,
  ].filter(Boolean).length;
}

export function FilterBar({
  filters,
  meta,
  tiers,
  elements,
  groups,
  states,
  categories,
  savedViews,
  expanded,
  onToggleExpanded,
  expandedError = null,
  onChange,
  onReset,
  onSaveView,
  onApplyView,
  onDeleteView,
}: FilterBarProps): JSX.Element {
  const { t } = useTranslation();
  const [savedViewName, setSavedViewName] = useState("");

  const activeMoreFilters = countActiveMoreFilters(filters);
  const moreLabel =
    activeMoreFilters > 0
      ? `${t("connectionView.filters.more")} (${activeMoreFilters})`
      : t("connectionView.filters.more");

  const chipClass = (active: boolean): string =>
    [styles.chip, active ? styles.chipActive : ""].filter(Boolean).join(" ");

  return (
    <div className={styles.filterBar} data-testid="connection-filter-bar">
      <div className={styles.filterRow}>
        <div className={styles.quickFilters}>
          <button
            type="button"
            className={`btn-ghost ${chipClass(filters.open === true)}`}
            aria-pressed={filters.open === true}
            data-testid="quick-open"
            onClick={() =>
              onChange({ open: filters.open === true ? undefined : true })
            }
          >
            {t("connectionView.quick.open")}
          </button>
          <button
            type="button"
            className={`btn-ghost ${chipClass(filters.allocated === false)}`}
            aria-pressed={filters.allocated === false}
            data-testid="quick-unallocated"
            onClick={() =>
              onChange({
                allocated: filters.allocated === false ? undefined : false,
              })
            }
          >
            {t("connectionView.quick.unallocated")}
          </button>
          <button
            type="button"
            className={`btn-ghost ${chipClass(filters.locked === true)}`}
            aria-pressed={filters.locked === true}
            data-testid="quick-locked"
            onClick={() =>
              onChange({ locked: filters.locked === true ? undefined : true })
            }
          >
            {t("connectionView.quick.locked")}
          </button>
          <button
            type="button"
            className={`btn-ghost ${chipClass(filters.hasFindings === true)}`}
            aria-pressed={filters.hasFindings === true}
            data-testid="quick-findings"
            onClick={() =>
              onChange({
                hasFindings: filters.hasFindings === true ? undefined : true,
              })
            }
          >
            {t("connectionView.quick.findings")}
          </button>
        </div>

        <label className={`${styles.field} ${styles.searchField}`}>
          {t("connectionView.filters.search")}
          <input
            type="search"
            className={styles.input}
            data-testid="filter-q"
            value={filters.q ?? ""}
            placeholder={t("connectionView.filters.searchPlaceholder")}
            onChange={(event) =>
              onChange({ q: event.target.value || undefined })
            }
          />
        </label>

        <button
          type="button"
          className={`btn-ghost ${styles.actionButton} ${styles.moreToggle}`}
          data-testid="filter-more-toggle"
          aria-expanded={expanded}
          aria-controls={expanded ? MORE_FILTERS_ID : undefined}
          onClick={onToggleExpanded}
        >
          {moreLabel}
          <span className={styles.moreCaret} aria-hidden="true">
            ▾
          </span>
        </button>

        <button
          type="button"
          className={`btn-ghost ${styles.actionButton}`}
          data-testid="filter-reset"
          onClick={onReset}
        >
          {t("connectionView.reset")}
        </button>

        <div className={styles.counterRow} data-testid="connection-counters">
          <span className={styles.counter}>
            {t("connectionView.counters.total")}:{" "}
            <strong data-testid="counter-total">{meta.total}</strong>
          </span>
          <span className={styles.counter}>
            {t("connectionView.counters.unallocated")}:{" "}
            <strong data-testid="counter-unallocated">{meta.unallocated}</strong>
          </span>
          <span className={styles.counter}>
            {t("connectionView.counters.locked")}:{" "}
            <strong data-testid="counter-locked">{meta.locked}</strong>
          </span>
          <span className={styles.counter}>
            {t("connectionView.counters.findings")}:{" "}
            <strong data-testid="counter-findings">{meta.findings}</strong>
          </span>
        </div>
      </div>

      {expanded && (
        <div
          id={MORE_FILTERS_ID}
          className={styles.moreFilters}
          data-testid="filter-more"
          role="group"
          aria-label={t("connectionView.filters.more")}
        >
          {expandedError && (
            <p
              role="alert"
              className={styles.error}
              data-testid="filter-more-error"
            >
              {expandedError}
            </p>
          )}

          <div className={styles.freeFilters}>
            <label className={styles.field}>
              {t("connectionView.filters.tier")}
              <select
                className={styles.select}
                data-testid="filter-tier"
                value={filters.tier ?? ""}
                onChange={(event) =>
                  onChange({ tier: event.target.value || undefined })
                }
              >
                <option value="">{t("connectionView.all")}</option>
                {tiers.map((tier) => (
                  <option key={tier.tier_key} value={tier.tier_key}>
                    {tier.name?.["de"] ?? tier.name?.["en"] ?? tier.tier_key}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.field}>
              {t("connectionView.filters.type")}
              <select
                className={styles.select}
                data-testid="filter-type"
                value={filters.type ?? ""}
                onChange={(event) =>
                  onChange({ type: event.target.value || undefined })
                }
              >
                <option value="">{t("connectionView.all")}</option>
                {REQUIREMENT_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {t(`connectionView.type.${type}`, type)}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.field}>
              {t("connectionView.filters.category")}
              <select
                className={styles.select}
                data-testid="filter-category"
                value={filters.category ?? ""}
                onChange={(event) =>
                  onChange({ category: event.target.value || undefined })
                }
              >
                <option value="">{t("connectionView.all")}</option>
                {categories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.field}>
              {t("connectionView.filters.state")}
              <select
                className={styles.select}
                data-testid="filter-state"
                value={filters.state ?? ""}
                onChange={(event) =>
                  onChange({ state: event.target.value || undefined })
                }
              >
                <option value="">{t("connectionView.all")}</option>
                {states.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
            </label>

            <label className={styles.field}>
              {t("connectionView.filters.elementSubtree")}
              <select
                className={styles.select}
                data-testid="filter-element-subtree"
                value={filters.elementSubtree ?? ""}
                onChange={(event) =>
                  onChange({ elementSubtree: event.target.value || undefined })
                }
              >
                <option value="">{t("connectionView.all")}</option>
                {elements.map((element) => (
                  <option key={element.id} value={element.id}>
                    {element.title}
                  </option>
                ))}
              </select>
            </label>

            {groups.length > 0 && (
              <label className={styles.field}>
                {t("connectionView.filters.group")}
                <select
                  className={styles.select}
                  data-testid="filter-group"
                  value={filters.group ?? ""}
                  onChange={(event) =>
                    onChange({ group: event.target.value || undefined })
                  }
                >
                  <option value="">{t("connectionView.all")}</option>
                  {groups.map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.title}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          <div className={styles.savedViews}>
            <label className={styles.field}>
              {t("connectionView.savedViews.name")}
              <input
                type="text"
                className={styles.input}
                data-testid="saved-view-name"
                value={savedViewName}
                onChange={(event) => setSavedViewName(event.target.value)}
              />
            </label>
            <button
              type="button"
              className={`btn-ghost ${styles.actionButton}`}
              data-testid="saved-view-save"
              disabled={savedViewName.trim().length === 0}
              onClick={() => {
                onSaveView(savedViewName.trim());
                setSavedViewName("");
              }}
            >
              {t("connectionView.savedViews.save")}
            </button>
            {savedViews.length > 0 && (
              <ul className={styles.savedViewList} data-testid="saved-view-list">
                {savedViews.map((view) => (
                  <li key={view.id} className={styles.savedViewItem}>
                    <button
                      type="button"
                      className={`btn-ghost ${styles.savedViewName}`}
                      data-testid={`saved-view-apply-${view.id}`}
                      onClick={() => onApplyView(view)}
                    >
                      {view.name}
                    </button>
                    <button
                      type="button"
                      className={`btn-ghost ${styles.savedViewDelete}`}
                      data-testid={`saved-view-delete-${view.id}`}
                      aria-label={t("connectionView.savedViews.delete", {
                        name: view.name,
                      })}
                      onClick={() => onDeleteView(view.id)}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
