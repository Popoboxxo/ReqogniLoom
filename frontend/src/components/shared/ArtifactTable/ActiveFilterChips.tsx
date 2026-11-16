/**
 * Task 4.4 — removable chips for active filters
 * (plan 2026-11-04-tabellenansicht-s4).
 *
 * One chip per constraint, so removing one half of a `gte`/`lte` range keeps
 * the other. Every chip's remove control is a labelled native button.
 */

import { useTranslation } from "react-i18next";

import type { FilterConstraint, TableFilters } from "../../../api/table-views";
import type { TableColumn } from "./columnModel";
import { withConstraints } from "./filters";
import styles from "./ArtifactTable.module.css";

export interface ActiveFilterChipsProps {
  columns: TableColumn[];
  filters: TableFilters;
  onChange(next: TableFilters): void;
}

function constraintText(constraint: FilterConstraint): string {
  const { op, value } = constraint;
  if (Array.isArray(value)) return `${op}: ${value.join(", ")}`;
  return `${op}: ${String(value)}`;
}

export function ActiveFilterChips({
  columns,
  filters,
  onChange,
}: ActiveFilterChipsProps): JSX.Element | null {
  const { t } = useTranslation();
  const labels = new Map(columns.map((column) => [column.name, column.label]));

  const entries: { field: string; index: number; constraint: FilterConstraint }[] = [];
  for (const [field, raw] of Object.entries(filters)) {
    const list = Array.isArray(raw) ? raw : [raw];
    list.forEach((constraint, index) =>
      entries.push({ field, index, constraint })
    );
  }

  if (entries.length === 0) return null;

  return (
    <ul className={styles.chipList} data-testid="active-filter-chips">
      {entries.map(({ field, index, constraint }) => (
        <li key={`${field}-${index}`} className={styles.chip}>
          <span>
            {labels.get(field) ?? field}: {constraintText(constraint)}
          </span>
          <button
            type="button"
            className={`btn btn-ghost ${styles.chipRemove}`}
            data-testid={`filter-chip-remove-${field}-${index}`}
            aria-label={t("table.removeFilter", {
              column: labels.get(field) ?? field,
            })}
            onClick={() => {
              const raw = filters[field];
              const list = Array.isArray(raw) ? raw : [raw];
              const next = list.filter((_, i) => i !== index);
              onChange(withConstraints(filters, field, next));
            }}
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}
