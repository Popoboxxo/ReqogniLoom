/**
 * Task 4.4 — filter state helpers (plan 2026-11-04-tabellenansicht-s4).
 *
 * The wire shape allows one constraint or a list per field; the UI always
 * wants a list. These two functions are the single conversion seam.
 */

import type { FilterConstraint, TableFilters } from "../../../api/table-views";

/** All constraints of one field, always as a list. */
export function constraintsFor(
  filters: TableFilters,
  field: string
): FilterConstraint[] {
  const value = filters[field];
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

/** Replace a field's constraints; an empty list removes the key entirely. */
export function withConstraints(
  filters: TableFilters,
  field: string,
  constraints: FilterConstraint[]
): TableFilters {
  const next: TableFilters = { ...filters };
  if (constraints.length === 0) {
    delete next[field];
  } else {
    next[field] = constraints.length === 1 ? constraints[0] : constraints;
  }
  return next;
}

/** Number of active constraints across all fields (for a chip counter). */
export function countConstraints(filters: TableFilters): number {
  return Object.keys(filters).reduce(
    (total, field) => total + constraintsFor(filters, field).length,
    0
  );
}
