/**
 * IcdList — left-panel navigation for ICDs (REQ-L2-ICD-001).
 *
 * Task 5.1 remodel: rows are <ArtifactRow> (ch. 12.3 — id/title, no level
 * badge since Icd has no level concept) instead of a bare <li>, and the
 * empty list vs. empty filter result render through <EmptyState> with
 * distinct text and actions (ch. 12.7/13.3). The page title, always-visible
 * summary and "New ICD" primary action live in <PageHeader> at the IcdView
 * level (ch. 12.1/12.2) — this component only owns search/sort and the row
 * list.
 *
 * Note: the Icd list-fetch type carries no `status` field (the WorkflowEngine
 * mirror only appears on IcdDetail, fetched per-artifact) — rows render
 * without a status badge, which <ArtifactRow> supports since Task 5.1.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ListToolbar } from "../shared/ListToolbar";
import { ArtifactRow } from "../shared/ArtifactRow";
import { EmptyState } from "../shared/EmptyState";
import type { Icd } from "../../api/icds";
import { shortId } from "./icd-view-shared";
import styles from "./IcdList.module.css";

interface IcdListProps {
  items: Icd[];
  selectedId?: string;
  onSelect: (icd: Icd) => void;
  onCreateNew: () => void;
}

type SortKey = "default" | "title" | "created";

function sortItems(list: Icd[], sortKey: SortKey): Icd[] {
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

export function IcdList({ items, selectedId, onSelect, onCreateNew }: IcdListProps): JSX.Element {
  const { t } = useTranslation();
  const [listSearch, setListSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("default");

  const visible = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = items.filter((it) => !q || it.name.toLowerCase().includes(q));
    return sortItems(filtered, sortKey);
  }, [items, listSearch, sortKey]);

  const hasActiveListControls = Boolean(listSearch);

  const resetFilters = (): void => {
    setListSearch("");
  };

  return (
    <div data-testid="icd-list">
      <ListToolbar
        testIdPrefix="icd-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t("editor.searchPlaceholder", "Search...")}
        sortValue={sortKey}
        sortOptions={[
          { value: "default", label: t("editor.sortDefault", "Default") },
          { value: "title", label: t("editor.sortTitleAsc", "Title (A-Z)") },
          { value: "created", label: t("editor.sortUpdatedDesc", "Recently Updated") },
        ]}
        onSortChange={(v) => setSortKey(v as SortKey)}
        sortLabel={t("editor.sortLabel", "Sort by")}
        countLabel={hasActiveListControls ? t("editor.filteredCount", { shown: visible.length, total: items.length }) : null}
      />

      {items.length === 0 ? (
        <EmptyState
          variant="empty"
          testId="icd-list-empty"
          title={t("icds.emptyTitle", "No ICDs yet")}
          description={t(
            "icds.emptyDescription",
            "Interface Control Documents capture the contract between two architecture elements.",
          )}
          actions={[{ label: t("icds.create", "New ICD"), onClick: onCreateNew, testId: "icd-list-empty-create" }]}
        />
      ) : visible.length === 0 ? (
        <EmptyState variant="no-match" testId="icd-list-no-match" onResetFilters={resetFilters} />
      ) : (
        <div className={styles.rows} data-testid="icds-list">
          {visible.map((icd) => {
            const isSelected = icd.id === selectedId;
            return (
              <ArtifactRow
                key={icd.id}
                idFallback={shortId(icd.id)}
                title={icd.name}
                selected={isSelected}
                onClick={() => onSelect(icd)}
                testId={`icd-item-${icd.id}`}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

IcdList.displayName = "IcdList";
