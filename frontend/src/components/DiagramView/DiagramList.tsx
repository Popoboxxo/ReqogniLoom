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
          options: DIAGRAM_TYPES.map((tp: DiagramType) => ({ value: tp, label: t(`diagrams.type.${tp}`, tp) })),
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
          {visible.map((item) => {
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
        </div>
      )}
    </div>
  );
}

DiagramList.displayName = "DiagramList";
