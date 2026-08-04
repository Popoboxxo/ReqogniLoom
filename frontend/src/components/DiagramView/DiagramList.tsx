/**
 * DiagramList — left-panel navigation for Diagrams (REQ-L2-DS-001).
 *
 * Task 5.1 remodel: rows are <ArtifactRow> (ch. 12.3 — id/title, no level
 * badge since Diagram has no parent relationship, per the plan's notes)
 * instead of a bare <li>, and the empty list vs. empty filter result render
 * through <EmptyState> with distinct text and actions (ch. 12.7/13.3). The
 * page title, always-visible summary and "New" primary action live in
 * <PageHeader> at the DiagramView level (ch. 12.1/12.2) — this component
 * only owns search/filter/sort, the row list and the per-row delete action
 * (a DiagramView-specific affordance that predates this remodel).
 *
 * Note: the Diagram list-fetch type carries no `status` field (the
 * WorkflowEngine mirror only appears on DiagramDetail, fetched per-artifact)
 * — rows render without a status badge, which <ArtifactRow> supports since
 * Task 5.1.
 *
 * Phase 6 / decision E2-D1: rows are grouped by `diagram_type` into flat
 * sections with a heading each. `diagram_type` is the only real ordering in
 * the data — Diagram has NO parent relationship. The grouping is deliberately
 * NOT rendered through <WorkspaceTree> (option D2, explicitly rejected in the
 * plan): a synthetic type level would invent a hierarchy the data model does
 * not have, the very trap ch. 5.1 warns about for the Spine. Sections are
 * plain <section>/<h2> + rows, with no expand/collapse and no indentation, so
 * the list stays flat both semantically and visually.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ListToolbar } from "../shared/ListToolbar";
import { ArtifactRow } from "../shared/ArtifactRow";
import { EmptyState } from "../shared/EmptyState";
import type { Diagram, DiagramType } from "../../types";
import { DIAGRAM_TYPES } from "./diagram-view-shared";
import styles from "./DiagramList.module.css";

interface DiagramListProps {
  items: Diagram[];
  selectedId?: string;
  onSelect: (item: Diagram) => void;
  onCreateNew: () => void;
  onDelete: (id: string) => void;
}

type SortKey = "default" | "title" | "created";

/** Fallback bucket for rows whose `diagram_type` is absent or unknown. */
const UNGROUPED_KEY = "__ungrouped__";

interface DiagramGroup {
  /** `diagram_type` value, or UNGROUPED_KEY for rows without a usable type. */
  key: string;
  items: Diagram[];
}

function sortItems(list: Diagram[], sortKey: SortKey): Diagram[] {
  const sorted = [...list];
  switch (sortKey) {
    case "title":
      sorted.sort((a, b) => a.name.localeCompare(b.name));
      break;
    case "created":
      sorted.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
      break;
  }
  return sorted;
}

/**
 * Bucket an already-filtered/sorted list into `diagram_type` sections.
 *
 * Section order follows DIAGRAM_TYPES (the canonical order also used by the
 * type filter), so it stays stable regardless of which types happen to be
 * present. Types outside that list — and rows with a missing type, which the
 * REST list endpoint should not produce but which fixtures and older records
 * do — are appended in a trailing bucket rather than dropped: a row that
 * cannot be grouped must still be reachable. Empty sections are omitted.
 */
function groupByType(list: Diagram[]): DiagramGroup[] {
  const buckets = new Map<string, Diagram[]>();
  for (const item of list) {
    const key = item.diagram_type ? String(item.diagram_type) : UNGROUPED_KEY;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(item);
    else buckets.set(key, [item]);
  }

  const known = DIAGRAM_TYPES.map((tp) => String(tp));
  const extras = [...buckets.keys()]
    .filter((k) => !known.includes(k) && k !== UNGROUPED_KEY)
    .sort((a, b) => a.localeCompare(b));

  return [...known, ...extras, UNGROUPED_KEY]
    .map((key) => ({ key, items: buckets.get(key) ?? [] }))
    .filter((group) => group.items.length > 0);
}

export function DiagramList({
  items,
  selectedId,
  onSelect,
  onCreateNew,
  onDelete,
}: DiagramListProps): JSX.Element {
  const { t } = useTranslation();
  const [listSearch, setListSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("default");

  const visible = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = items.filter((it) => {
      if (q && !it.name.toLowerCase().includes(q)) return false;
      if (typeFilter && it.diagram_type !== typeFilter) return false;
      return true;
    });
    return sortItems(filtered, sortKey);
  }, [items, listSearch, typeFilter, sortKey]);

  const groups = useMemo(() => groupByType(visible), [visible]);

  const hasActiveListControls = Boolean(listSearch || typeFilter);

  const resetFilters = (): void => {
    setListSearch("");
    setTypeFilter("");
  };

  return (
    <div data-testid="diagram-list">
      <ListToolbar
        testIdPrefix="diagram-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t("editor.searchPlaceholder", "Search...")}
        filters={[{
          id: "type",
          allLabel: t("diagrams.allTypes", "All Types"),
          value: typeFilter,
          options: DIAGRAM_TYPES.map((tp: DiagramType) => ({ value: tp, label: t(`diagrams.typeLabels.${tp}`, tp) })),
          onChange: setTypeFilter,
        }]}
        sortValue={sortKey}
        sortOptions={[
          { value: "default", label: t("editor.sortDefault", "Default") },
          { value: "title", label: t("editor.sortTitleAsc", "Title (A-Z)") },
          { value: "created", label: t("editor.sortUpdatedDesc", "Recently Updated") },
        ]}
        onSortChange={(v) => setSortKey(v as SortKey)}
        sortLabel={t("editor.sortLabel", "Sort by")}
        countLabel={hasActiveListControls ? t("editor.filteredCount", { shown: visible.length, total: items.length }) : String(items.length)}
      />

      {items.length === 0 ? (
        <EmptyState
          variant="empty"
          testId="diagrams-empty"
          title={t("diagrams.emptyTitle", "No diagrams yet")}
          description={t(
            "diagrams.emptyDescription",
            "Diagrams visualize architecture, flows and state machines.",
          )}
          actions={[{ label: t("diagrams.create", "New Diagram"), onClick: onCreateNew, testId: "diagram-list-empty-create" }]}
        />
      ) : visible.length === 0 ? (
        <EmptyState variant="no-match" testId="diagram-list-no-match" onResetFilters={resetFilters} />
      ) : (
        <div className={styles.rows} data-testid="diagrams-list">
          {groups.map((group) => {
            const label =
              group.key === UNGROUPED_KEY
                ? t("diagrams.typeUnknown", "Other")
                : t(`diagrams.typeLabels.${group.key}`, group.key);
            return (
              <section
                key={group.key}
                className={styles.group}
                aria-label={label}
                data-testid={`diagram-group-${group.key}`}
              >
                <h2 className={styles.groupHeading}>
                  <span>{label}</span>
                  <span className={styles.groupCount}>{group.items.length}</span>
                </h2>
                {group.items.map((item) => {
                  const isSelected = item.id === selectedId;
                  return (
                    <div key={item.id} className={styles.rowWrapper}>
                      <div className={styles.rowContent}>
                        <ArtifactRow
                          idFallback={item.id.slice(0, 8)}
                          title={item.name}
                          version={item.version_count}
                          selected={isSelected}
                          onClick={() => onSelect(item)}
                          testId={`diagram-item-${item.id}`}
                        />
                      </div>
                      <button
                        type="button"
                        className={styles.deleteButton}
                        data-testid={`diagram-delete-${item.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(item.id);
                        }}
                        title={t("diagrams.delete", "Delete")}
                        aria-label={t("diagrams.delete", "Delete")}
                      >
                        ×
                      </button>
                    </div>
                  );
                })}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

DiagramList.displayName = "DiagramList";
