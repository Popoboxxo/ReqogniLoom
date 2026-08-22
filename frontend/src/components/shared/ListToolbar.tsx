/**
 * ARCH-L1-001 ReactFrontend — ListToolbar (shared).
 *
 * req_id: REQ-003 (Skalierbare Listen-Toolbar — Suche/Filter/Sortierung)
 *
 * Reusable toolbar for left-hand artifact list panels (Requirements,
 * Architecture). Renders a free-text search input plus an optional row of
 * filter dropdowns and a sort dropdown. The component is i18n-agnostic:
 * callers pass translated labels/placeholders so it stays decoupled from
 * any specific namespace.
 *
 * All filtering/sorting itself happens in the caller (client-side via
 * useMemo) — this component only owns the controls.
 */


export interface ListToolbarFilterOption {
  value: string;
  label: string;
}

export interface ListToolbarFilter {
  /** Stable id, used for data-testid and React keys. */
  id: string;
  /** Label of the "no filter" option (e.g. "All categories"). */
  allLabel: string;
  /** Current value; empty string = filter inactive. */
  value: string;
  options: ListToolbarFilterOption[];
  onChange: (value: string) => void;
}

export interface ListToolbarSortOption {
  value: string;
  label: string;
}

export interface ListToolbarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder: string;
  filters?: ListToolbarFilter[];
  sortValue?: string;
  sortOptions?: ListToolbarSortOption[];
  onSortChange?: (value: string) => void;
  /** Accessible label for the sort dropdown. */
  sortLabel?: string;
  /**
   * Preformatted result count (e.g. "12 of 240" while filtered, "240"
   * otherwise). Per UI_KONZEPT.md ch. 12.1 the count must always be
   * visible, not only while a filter/search is active — callers should
   * pass the plain total when no control is active rather than `null`.
   * `null` is still accepted for routes without a meaningful count.
   */
  countLabel?: string | null;
  /** Prefix for data-testid attributes, e.g. "req-list" / "arch-tree". */
  testIdPrefix: string;
  /**
   * Optional actions rendered at the right end of the toolbar.
   * Note: UI_KONZEPT.md ch. 12.2 recommends no primary actions in toolbar,
   * but this is a deliberate override per user request for improved UX.
   */
  actions?: React.ReactNode;
}

const controlStyle: React.CSSProperties = {
  height: "32px",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--color-border)",
  padding: "0 var(--space-2)",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  boxSizing: "border-box",
  outline: "none",
};

/*
 * GESAMTTEST_BERICHT_2026-08-21.md §6 item 2: the native <select>'s caret
 * icon needs extra reserved space on the right beyond the symmetric
 * controlStyle padding, otherwise long option labels run underneath the
 * browser-drawn arrow once the select shrinks (flex: 1 1 0, minWidth: 0)
 * below its content width. Applied only to <select> elements (filters +
 * sort), not the free-text search input, which has no caret.
 */
const selectStyle: React.CSSProperties = {
  ...controlStyle,
  paddingRight: "calc(var(--space-2) + 16px)",
  textOverflow: "ellipsis",
};

export function ListToolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder,
  filters,
  sortValue,
  sortOptions,
  onSortChange,
  sortLabel,
  countLabel,
  testIdPrefix,
  actions,
}: ListToolbarProps): JSX.Element {
  const hasFilterRow =
    (filters && filters.length > 0) ||
    (sortOptions && sortOptions.length > 0 && onSortChange);

  return (
    <div
      data-testid={`${testIdPrefix}-toolbar`}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
        marginBottom: "var(--space-2)",
      }}
    >
      <input
        type="search"
        data-testid={`${testIdPrefix}-search-input`}
        value={searchValue}
        onChange={(e) => onSearchChange(e.target.value)}
        placeholder={searchPlaceholder}
        aria-label={searchPlaceholder}
        style={{ ...controlStyle, width: "100%" }}
      />

      {hasFilterRow && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "var(--space-2)",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", alignItems: "center", flex: "1 1 auto" }}>
            {(filters ?? []).map((filter) => (
              <select
                key={filter.id}
                data-testid={`${testIdPrefix}-filter-${filter.id}`}
                value={filter.value}
                onChange={(e) => filter.onChange(e.target.value)}
                aria-label={filter.allLabel}
                style={{ ...selectStyle, flex: "1 1 0", minWidth: 0 }}
              >
                <option value="">{filter.allLabel}</option>
                {filter.options.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            ))}

            {sortOptions && sortOptions.length > 0 && onSortChange && (
              <select
                data-testid={`${testIdPrefix}-sort-select`}
                value={sortValue ?? ""}
                onChange={(e) => onSortChange(e.target.value)}
                aria-label={sortLabel ?? "Sort"}
                style={{ ...selectStyle, flex: "1 1 0", minWidth: 0 }}
              >
                {sortOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            )}
          </div>

          {actions && (
            <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexShrink: 0 }}>
              {actions}
            </div>
          )}
        </div>
      )}

      {countLabel != null && (
        <span
          data-testid={`${testIdPrefix}-count`}
          style={{
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
          }}
        >
          {countLabel}
        </span>
      )}
    </div>
  );
}
