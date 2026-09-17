/**
 * ARCH-L1-001 ReactFrontend — InterviewList (plan Task 6).
 *
 * Left-panel navigation for interview sessions, mirroring `AdrList`: flat
 * list (no hierarchy), `<ArtifactRow>` rows via `<WorkspaceTree>`'s
 * `renderRow` slot, `<EmptyState>` for the "nothing at all" vs. "nothing
 * matches the filter" split. Rows carry no title of their own (an
 * `InterviewSummary` has `artifact_type`/`status`, not a `title`) -- the
 * artifact type stands in as the row's identity.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { ListToolbar } from "../shared/ListToolbar";
import { ArtifactRow } from "../shared/ArtifactRow";
import { EmptyState } from "../shared/EmptyState";
import { WorkspaceTree } from "../shared/WorkspaceTree";
import type { WorkspaceTreeNode } from "../shared/WorkspaceTree";
import type { InterviewSummary } from "../../api/interviews";
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from "../../utils/workflowStatus";

interface InterviewListProps {
  items: InterviewSummary[];
  selectedId?: string;
  onSelect: (id: string) => void;
}

type SortKey = "default" | "type" | "status";

function sortItems(list: InterviewSummary[], sortKey: SortKey): InterviewSummary[] {
  const sorted = [...list];
  switch (sortKey) {
    case "type":
      sorted.sort((a, b) => a.artifact_type.localeCompare(b.artifact_type));
      break;
    case "status":
      sorted.sort(
        (a, b) => compareWorkflowStatus(a.status, b.status) || a.artifact_type.localeCompare(b.artifact_type),
      );
      break;
  }
  return sorted;
}

function interviewToNode(session: InterviewSummary, typeLabel: string): WorkspaceTreeNode {
  return { id: session.id, name: typeLabel, parentId: null };
}

export function InterviewList({ items, selectedId, onSelect }: InterviewListProps): JSX.Element {
  const { t } = useTranslation();
  const [listSearch, setListSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("default");

  const visible = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = items.filter((it) => {
      if (q && !it.artifact_type.toLowerCase().includes(q) && !it.id.toLowerCase().includes(q)) {
        return false;
      }
      if (statusFilter && it.status !== statusFilter) return false;
      return true;
    });
    return sortItems(filtered, sortKey);
  }, [items, listSearch, statusFilter, sortKey]);

  const treeNodes = useMemo(
    () => visible.map((it) => interviewToNode(it, t(`interviews.forType.${it.artifact_type}`, it.artifact_type))),
    [visible, t],
  );

  const byId = useMemo(() => {
    const map = new Map<string, InterviewSummary>();
    for (const it of visible) map.set(it.id, it);
    return map;
  }, [visible]);

  const statusOptions = useMemo(() => buildStatusFilterOptions(items, statusFilter), [items, statusFilter]);

  const hasActiveListControls = Boolean(listSearch || statusFilter);

  const resetFilters = (): void => {
    setListSearch("");
    setStatusFilter("");
  };

  return (
    <div data-testid="interview-list">
      <ListToolbar
        testIdPrefix="interview-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t("editor.searchPlaceholder", "Search...")}
        filters={[
          {
            id: "status",
            allLabel: t("editor.allStatuses", "All Statuses"),
            value: statusFilter,
            options: statusOptions,
            onChange: setStatusFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: "default", label: t("editor.sortDefault", "Default") },
          { value: "type", label: t("interviews.sortType", "Artifact type") },
          { value: "status", label: t("editor.sortStatus", "Status") },
        ]}
        onSortChange={(v) => setSortKey(v as SortKey)}
        sortLabel={t("editor.sortLabel", "Sort by")}
        countLabel={
          hasActiveListControls
            ? t("editor.filteredCount", { shown: visible.length, total: items.length })
            : String(items.length)
        }
      />

      {items.length === 0 ? (
        <EmptyState
          variant="empty"
          testId="interview-list-empty"
          title={t("interviews.emptyTitle", "No interviews yet")}
          description={t(
            "interviews.emptyDescription",
            "Interviews walk a user through brainstorming a new artifact conversationally instead of a blank form. Start one from the chat button.",
          )}
        />
      ) : visible.length === 0 ? (
        <EmptyState variant="no-match" testId="interview-list-no-match" onResetFilters={resetFilters} />
      ) : (
        <WorkspaceTree
          data-testid="interview-list-rows"
          nodes={treeNodes}
          selectedId={selectedId}
          onSelect={onSelect}
          showSearch={false}
          virtualize
          virtualRowHeight={64}
          emptyLabel={t("editor.empty", "No items.")}
          noMatchesLabel={t("editor.noMatches", "No matches found.")}
          renderRow={(node, { isSelected }) => {
            const session = byId.get(node.id);
            if (!session) return null;
            return (
              <ArtifactRow
                idFallback={session.id.slice(0, 8)}
                title={t(`interviews.forType.${session.artifact_type}`, session.artifact_type)}
                status={session.status}
                statusLabel={getWorkflowStatusLabel(session.status)}
                selected={isSelected}
                testId={`interview-row-${session.id}`}
              />
            );
          }}
        />
      )}
    </div>
  );
}

InterviewList.displayName = "InterviewList";
