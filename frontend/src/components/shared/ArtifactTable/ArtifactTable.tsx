/**
 * Task 4.3 — `ArtifactTable` grid (plan 2026-11-04-tabellenansicht-s4).
 *
 * Semantics: native `<table>` (implicit `role="table"`) with `<th scope="col">`
 * headers and real `<button>` sort controls — the project has no `role="grid"`
 * convention and a native table is the stronger accessibility baseline for a
 * read-mostly data grid. Large result sets are windowed with
 * `@tanstack/react-virtual` through two spacer rows (top/bottom), the same
 * library and threshold idea as `WorkspaceTree/tree-virtualization.tsx`.
 *
 * Status is read-only here: the cell renders `<StatusBadge>` and a separate
 * "Change status" button outside the inline-edit path. A locked row shows a
 * lock marker and exposes no editor.
 */

import { useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Lock } from "lucide-react";

import type { SortTerm, TableRow } from "../../../api/table-views";
import { StatusBadge } from "../StatusBadge";
import type { TableColumn } from "./columnModel";
import styles from "./ArtifactTable.module.css";

export const SORT_LIMIT = 5;
export const VIRTUALIZE_THRESHOLD = 100;
const ROW_HEIGHT = 40;

export interface ArtifactTableProps {
  columns: TableColumn[];
  rows: TableRow[];
  sort: SortTerm[];
  onSortChange(next: SortTerm[]): void;
  selectedIds: ReadonlySet<string>;
  onSelectionChange(next: ReadonlySet<string>): void;
  renderCellEditor?(column: TableColumn, row: TableRow): React.ReactNode;
  onStartInlineEdit?(rowId: string, column: string): void;
  /** Opens the filter popover for a column (rendered only when filterable). */
  onFilterClick?(column: TableColumn): void;
  /** Columns that currently carry at least one constraint. */
  activeFilterFields?: ReadonlySet<string>;
  loading: boolean;
}

/**
 * Click cycles asc → desc → off; shift-click adds (or cycles) a secondary
 * term. At most {@link SORT_LIMIT} terms are kept.
 */
export function toggleSort(
  sort: SortTerm[],
  field: string,
  additive: boolean
): SortTerm[] {
  const index = sort.findIndex((term) => term.field === field);
  const current = index === -1 ? null : sort[index];
  const nextDir = current === null ? "asc" : current.dir === "asc" ? "desc" : null;

  if (!additive && index === -1) {
    return [{ field, dir: "asc" as const }];
  }

  if (nextDir === null) {
    if (!additive) return [];
    return sort.filter((term) => term.field !== field);
  }

  const nextTerm: SortTerm = { field, dir: nextDir };
  if (index === -1) {
    if (!additive) return [nextTerm];
    if (sort.length >= SORT_LIMIT) return sort;
    return [...sort, nextTerm];
  }
  const next = [...sort];
  next[index] = nextTerm;
  return next;
}

function ariaSortFor(column: string, sort: SortTerm[]): "ascending" | "descending" | "none" {
  const term = sort.find((entry) => entry.field === column);
  if (!term) return "none";
  return term.dir === "asc" ? "ascending" : "descending";
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.map(formatValue).join(", ");
  if (typeof value === "object") return "";
  return String(value);
}

export function ArtifactTable({
  columns,
  rows,
  sort,
  onSortChange,
  selectedIds,
  onSelectionChange,
  renderCellEditor,
  onStartInlineEdit,
  onFilterClick,
  activeFilterFields,
  loading,
}: ArtifactTableProps): JSX.Element {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualize = rows.length > VIRTUALIZE_THRESHOLD;

  const rowVirtualizer = useVirtualizer({
    count: virtualize ? rows.length : 0,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 10,
  });

  const virtualItems = rowVirtualizer.getVirtualItems();
  const totalSize = rowVirtualizer.getTotalSize();
  const topPad = virtualize ? virtualItems[0]?.start ?? 0 : 0;
  const bottomPad = virtualize
    ? Math.max(totalSize - (virtualItems[virtualItems.length - 1]?.end ?? 0), 0)
    : 0;

  const topSpacerStyle = useMemo<React.CSSProperties>(
    () => ({ height: `${topPad}px` }),
    [topPad]
  );
  const bottomSpacerStyle = useMemo<React.CSSProperties>(
    () => ({ height: `${bottomPad}px` }),
    [bottomPad]
  );

  const visibleRows = virtualize
    ? virtualItems.map((item) => rows[item.index]).filter(Boolean)
    : rows;

  const allSelected =
    rows.length > 0 && rows.every((row) => selectedIds.has(row.id));
  const someSelected = rows.some((row) => selectedIds.has(row.id));
  const selectAllRef = useRef<HTMLInputElement>(null);
  if (selectAllRef.current) {
    selectAllRef.current.indeterminate = someSelected && !allSelected;
  }

  function toggleRow(id: string): void {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectionChange(next);
  }

  function toggleAll(): void {
    if (allSelected) {
      onSelectionChange(new Set());
      return;
    }
    onSelectionChange(new Set(rows.map((row) => row.id)));
  }

  const columnCount = columns.length + 1;

  function renderCell(column: TableColumn, row: TableRow): React.ReactNode {
    if (column.name === "status") {
      const status = formatValue(row.values[column.name]);
      return (
        <span className={styles.statusCell}>
          <StatusBadge
            status={status || "—"}
            testId={`status-badge-${row.id}`}
          />
          <button
            type="button"
            className={`btn btn-icon ${styles.iconButton}`}
            data-testid={`status-change-${row.id}`}
            aria-label={t("table.changeStatus")}
            title={t("table.changeStatus")}
            onClick={() => onStartInlineEdit?.(row.id, column.name)}
          >
            ↻
          </button>
        </span>
      );
    }

    if (!row.locked && column.inlineEditable) {
      if (renderCellEditor) return renderCellEditor(column, row);
      return (
        <button
          type="button"
          className={`btn btn-ghost ${styles.cellButton}`}
          data-testid={`cell-${row.id}-${column.name}`}
          onClick={() => onStartInlineEdit?.(row.id, column.name)}
        >
          {formatValue(row.values[column.name]) || t("table.emptyCell")}
        </button>
      );
    }

    return (
      <span className={styles.cellText}>
        {formatValue(row.values[column.name])}
      </span>
    );
  }

  return (
    <div ref={scrollRef} className={styles.scroll} data-testid="artifact-table-scroll">
      <table className={styles.table} data-testid="artifact-table">
        <thead>
          <tr>
            <th scope="col" className={styles.checkboxCell}>
              <input
                ref={selectAllRef}
                type="checkbox"
                data-testid="artifact-table-select-all"
                aria-label={t("table.selectAll")}
                checked={allSelected}
                onChange={toggleAll}
              />
            </th>
            {columns.map((column) => (
              <th
                key={column.name}
                scope="col"
                className={styles.headerCell}
                aria-sort={column.sortable ? ariaSortFor(column.name, sort) : undefined}
              >
                {column.sortable ? (
                  <button
                    type="button"
                    className={`btn btn-ghost ${styles.sortButton}`}
                    data-testid={`sort-${column.name}`}
                    aria-label={t("table.sortBy", { column: column.label })}
                    onClick={(event) =>
                      onSortChange(toggleSort(sort, column.name, event.shiftKey))
                    }
                  >
                    {column.label}
                    <span className={styles.sortIndicator} aria-hidden="true">
                      {sort.find((term) => term.field === column.name)?.dir === "asc"
                        ? "▲"
                        : sort.find((term) => term.field === column.name)?.dir === "desc"
                          ? "▼"
                          : ""}
                    </span>
                  </button>
                ) : (
                  <span>{column.label}</span>
                )}
                {onFilterClick && column.filterable && (
                  <button
                    type="button"
                    className={`btn btn-ghost ${styles.filterTrigger} ${activeFilterFields?.has(column.name) ? styles.filterTriggerActive : ""}`}
                    data-testid={`filter-trigger-${column.name}`}
                    aria-label={t("table.filterBy", { column: column.label })}
                    onClick={() => onFilterClick(column)}
                  >
                    ⏷
                  </button>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={columnCount} className={styles.stateCell}>
                <span role="status">{t("table.loading")}</span>
              </td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={columnCount} className={styles.stateCell}>
                {t("table.empty")}
              </td>
            </tr>
          )}
          {virtualize && topPad > 0 && (
            <tr aria-hidden="true" className={styles.spacerRow}>
              <td colSpan={columnCount} style={topSpacerStyle} />
            </tr>
          )}
          {!loading &&
            visibleRows.map((row) => (
              <tr
                key={row.id}
                className={row.locked ? styles.lockedRow : undefined}
                data-testid={`table-row-${row.id}`}
              >
                <td className={styles.checkboxCell}>
                  <input
                    type="checkbox"
                    data-testid={`row-select-${row.id}`}
                    aria-label={t("table.selectRowNamed", {
                      title: row.values.title ?? row.artifact_id ?? row.id,
                    })}
                    checked={selectedIds.has(row.id)}
                    onChange={() => toggleRow(row.id)}
                  />
                  {row.locked && (
                    <span
                      role="img"
                      aria-label={t("table.lockedRow", { state: row.locked.state })}
                      data-testid={`row-lock-${row.id}`}
                    >
                      <Lock size={14} aria-hidden="true" />
                    </span>
                  )}
                </td>
                {columns.map((column) => (
                  <td key={column.name} className={styles.bodyCell}>
                    {renderCell(column, row)}
                  </td>
                ))}
              </tr>
            ))}
          {virtualize && bottomPad > 0 && (
            <tr aria-hidden="true" className={styles.spacerRow}>
              <td colSpan={columnCount} style={bottomSpacerStyle} />
            </tr>
          )}
        </tbody>
      </table>
      {rows.some((row) => row.locked) && (
        <p className={styles.lockLegend} data-testid="artifact-table-lock-legend">
          <Lock size={14} aria-hidden="true" />
          {t("table.lockedLegend")}
        </p>
      )}
    </div>
  );
}
