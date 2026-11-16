/**
 * Task 4.2 — derive the table column model from the resolved attribute
 * definition (plan 2026-11-04-tabellenansicht-s4).
 *
 * Pure module, no React: the grid, the filter popover and the inline editor
 * all read their capabilities (filterable/sortable/inlineEditable) from here,
 * so the "what may this column do" answer exists exactly once.
 */

import type {
  AttributeOption,
  AttributeSpec,
  AttributeType,
} from "../../../api/attribute-definitions";
import type {
  FilterOperator,
  SortTerm,
  TableViewState,
} from "../../../api/table-views";

export interface TableColumn {
  name: string;
  type: AttributeType;
  kind: "core" | "extended";
  label: string;
  editable: boolean | "workflow" | "system" | "automation";
  options?: AttributeOption[];
  filterable: boolean;
  sortable: boolean;
  inlineEditable: boolean;
}

/**
 * Mirrors the backend `FILTER_OPERATORS_BY_TYPE`: which operators are legal
 * for a type. An empty list means "not filterable in the UI".
 */
const FILTER_OPERATORS_BY_TYPE: Record<AttributeType, FilterOperator[]> = {
  text: ["contains"],
  textarea: ["contains"],
  number: ["eq", "gte", "lte"],
  boolean: ["eq"],
  enum: ["in"],
  "multi-enum": ["in"],
  date: ["gte", "lte"],
  reference: ["in"],
  user: ["in"],
  actor: ["in"],
  "criteria-list": [],
  widget: [],
};

/** `workflow`/`system`/`automation` are owned by the server, never bulk-writable. */
export function isWorkflowOwned(attr: AttributeSpec): boolean {
  return (
    attr.editable === "workflow" ||
    attr.editable === "system" ||
    attr.editable === "automation"
  );
}

export function operatorsForColumn(column: {
  type: AttributeType;
  kind: "core" | "extended";
}): FilterOperator[] {
  if (column.kind === "extended") return [];
  return FILTER_OPERATORS_BY_TYPE[column.type] ?? [];
}

/**
 * The localized label, with the field name as the last fallback (the table
 * header must always show something).
 */
export function columnLabel(attr: AttributeSpec, language: string): string {
  const localized = language.startsWith("de")
    ? attr.label?.de
    : attr.label?.en;
  return localized || attr.label?.en || attr.name;
}

function toColumn(attr: AttributeSpec, language: string): TableColumn {
  const operators = operatorsForColumn(attr);
  return {
    name: attr.name,
    type: attr.type,
    kind: attr.kind,
    label: columnLabel(attr, language),
    editable: attr.editable,
    options: attr.options?.length ? attr.options : undefined,
    filterable: operators.length > 0,
    sortable: attr.kind === "core" && attr.type !== "criteria-list" && attr.type !== "widget",
    inlineEditable:
      attr.editable === true && attr.kind === "core" && attr.type !== "widget",
  };
}

/**
 * Build the ordered column list: the state's stored order first (only fields
 * that still exist in the definition), then the definition order for every
 * remaining visible attribute.
 */
export function buildColumns(
  attributes: AttributeSpec[],
  state: Pick<TableViewState, "columns">,
  language: string
): TableColumn[] {
  const visible = attributes.filter((attr) => attr.visible !== false);
  const byName = new Map(visible.map((attr) => [attr.name, attr]));
  const ordered: TableColumn[] = [];
  const seen = new Set<string>();

  const stateColumns = [...(state.columns ?? [])]
    .filter((entry) => typeof entry?.field === "string")
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

  for (const entry of stateColumns) {
    const attr = byName.get(entry.field);
    if (!attr || seen.has(attr.name)) continue;
    seen.add(attr.name);
    ordered.push(toColumn(attr, language));
  }

  const rest = [...visible].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  for (const attr of rest) {
    if (seen.has(attr.name)) continue;
    seen.add(attr.name);
    ordered.push(toColumn(attr, language));
  }

  return ordered;
}

/** Sort terms for the columns a table can actually order by. */
export function sortableColumns(columns: TableColumn[]): TableColumn[] {
  return columns.filter((column) => column.sortable);
}

/** Normalise a stored sort list, dropping terms for unknown/non-sortable fields. */
export function normaliseSort(
  sort: SortTerm[] | undefined,
  columns: TableColumn[]
): SortTerm[] {
  if (!sort) return [];
  const sortable = new Set(sortableColumns(columns).map((c) => c.name));
  return sort.filter(
    (term) => sortable.has(term.field) && (term.dir === "asc" || term.dir === "desc")
  );
}
