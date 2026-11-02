/**
 * ARCH-L1-001 ReactFrontend — Documents list (Plan F F2-T8).
 *
 * Left panel of the split view. Mirrors `AdrList`: search + kind/status
 * filters come from the loaded rows (never a hardcoded state list), empty and
 * no-match are distinct states, and the rows render through `<WorkspaceTree>`
 * + `<ArtifactRow>` so the list looks and behaves like every other artifact
 * list. Document rows are flat (no hierarchy) — F3 adds WorkItem children.
 */

import { useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useArtifactList, artifactId } from "../../hooks/useArtifactList";
import { ListToolbar } from "../shared/ListToolbar";
import { ArtifactRow } from "../shared/ArtifactRow";
import { EmptyState } from "../shared/EmptyState";
import { WorkspaceTree } from "../shared/WorkspaceTree";
import type { WorkspaceTreeNode } from "../shared/WorkspaceTree";
import { IncludeDeletedToggle } from "../shared/IncludeDeletedToggle/IncludeDeletedToggle";
import type { Document, DocumentKind } from "../../types";
import { DOCUMENT_KINDS } from "../../types";
import {
  buildStatusFilterOptions,
  getWorkflowStatusLabel,
} from "../../utils/workflowStatus";
import { isOutdatedState } from "../../utils/outdatedStates";
import styles from "./Documents.module.css";

const KIND_LABEL_KEY: Record<DocumentKind, string> = {
  Spec: "documents.kinds.spec",
  Plan: "documents.kinds.plan",
  AuditReport: "documents.kinds.auditReport",
  Review: "documents.kinds.review",
  Conclusion: "documents.kinds.conclusion",
  Concept: "documents.kinds.concept",
  Guide: "documents.kinds.guide",
};

export interface DocumentListProps {
  items: Document[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onCreateNew: () => void;
  canCreate: boolean;
  isLoading: boolean;
  error: Error | null;
  onRetry: () => void;
  includeDeleted: boolean;
  onIncludeDeletedChange: (checked: boolean) => void;
  workspaceId?: string | null;
}

type SortKey = "default" | "title" | "kind" | "updated";

function sortItems(list: Document[], sortKey: SortKey): Document[] {
  const sorted = [...list];
  switch (sortKey) {
    case "title":
      sorted.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case "kind":
      sorted.sort(
        (a, b) =>
          a.kind.localeCompare(b.kind) || a.title.localeCompare(b.title)
      );
      break;
    case "updated":
      sorted.sort((a, b) =>
        (b.updated_at || "").localeCompare(a.updated_at || "")
      );
      break;
  }
  return sorted;
}

function documentToNode(document: Document): WorkspaceTreeNode {
  return {
    id: document.id,
    name: document.title || document.uid || document.id,
    parentId: null,
    identifier: document.uid ?? null,
    outdated: isOutdatedState(document.status),
  };
}

export function DocumentList({
  items,
  selectedId,
  onSelect,
  onCreateNew,
  canCreate,
  isLoading,
  error,
  onRetry,
  includeDeleted,
  onIncludeDeletedChange,
  workspaceId,
}: DocumentListProps): JSX.Element {
  const { t } = useTranslation();
  const [listSearch, setListSearch] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("default");

  const filter = useCallback(
    (document: Document, query: string) => {
      if (query) {
        const haystack = `${document.title} ${document.description}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      if (kindFilter && document.kind !== kindFilter) return false;
      if (statusFilter && document.status !== statusFilter) return false;
      return true;
    },
    [kindFilter, statusFilter]
  );

  const {
    visible,
    treeNodes,
    byId: documentById,
  } = useArtifactList({
    items,
    query: listSearch,
    filter,
    sortItems,
    sortKey,
    toNode: documentToNode,
    getKey: artifactId,
  });

  const statusOptions = useMemo(
    () => buildStatusFilterOptions(items, statusFilter),
    [items, statusFilter]
  );

  const kindOptions = useMemo(
    () =>
      DOCUMENT_KINDS.map((kind) => ({
        value: kind,
        label: t(KIND_LABEL_KEY[kind]),
      })),
    [t]
  );

  const hasActiveListControls = Boolean(
    listSearch || kindFilter || statusFilter
  );

  const resetFilters = (): void => {
    setListSearch("");
    setKindFilter("");
    setStatusFilter("");
  };

  if (isLoading) {
    return (
      <EmptyState
        variant="loading"
        testId="documents-list-loading"
        label={t("documents.loading")}
      />
    );
  }

  if (error) {
    return (
      <EmptyState
        variant="error"
        testId="documents-list-error"
        title={t("documents.loadFailed")}
        description={error.message}
        onRetry={onRetry}
        retryLabel={t("documents.retry")}
      />
    );
  }

  return (
    <div className={styles.listRoot} data-testid="documents-list">
      <ListToolbar
        testIdPrefix="documents-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t("documents.searchPlaceholder")}
        filters={[
          {
            id: "kind",
            allLabel: t("documents.allKinds"),
            value: kindFilter,
            options: kindOptions,
            onChange: setKindFilter,
          },
          {
            id: "status",
            allLabel: t("documents.allStatuses"),
            value: statusFilter,
            options: statusOptions,
            onChange: setStatusFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: "default", label: t("documents.sortDefault") },
          { value: "title", label: t("documents.sortTitle") },
          { value: "kind", label: t("documents.sortKind") },
          { value: "updated", label: t("documents.sortUpdated") },
        ]}
        onSortChange={(value) => setSortKey(value as SortKey)}
        sortLabel={t("documents.sortLabel")}
        countLabel={
          hasActiveListControls
            ? t("documents.filteredCount", {
                shown: visible.length,
                total: items.length,
              })
            : String(items.length)
        }
      />

      <div className={styles.listFooter}>
        <IncludeDeletedToggle
          checked={includeDeleted}
          onChange={onIncludeDeletedChange}
          testIdPrefix="documents-list"
        />
      </div>

      {items.length === 0 ? (
        <EmptyState
          variant="empty"
          testId="documents-list-empty"
          title={t("documents.emptyTitle")}
          description={t("documents.emptyDescription")}
          actions={
            canCreate
              ? [
                  {
                    label: t("documents.newDocument"),
                    prefixWithPlus: true,
                    onClick: onCreateNew,
                    testId: "documents-list-empty-create",
                  },
                ]
              : []
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState
          variant="no-match"
          testId="documents-list-no-match"
          onResetFilters={resetFilters}
          resetFiltersLabel={t("documents.resetFilters")}
        />
      ) : (
        <WorkspaceTree
          data-testid="documents-list-rows"
          nodes={treeNodes}
          selectedId={selectedId}
          onSelect={onSelect}
          showSearch={false}
          itemType="Document"
          workspaceId={workspaceId ?? null}
          virtualize
          virtualRowHeight={64}
          emptyLabel={t("documents.emptyLabel")}
          noMatchesLabel={t("documents.noMatches")}
          renderRow={(node, { isSelected }) => {
            const document = documentById?.get(node.id);
            if (!document) return null;
            return (
              <ArtifactRow
                id={document.uid}
                idFallback={document.id.slice(0, 8)}
                title={document.title || t("documents.untitled")}
                status={document.status}
                statusLabel={getWorkflowStatusLabel(document.status)}
                version={document.version}
                outdated={isOutdatedState(document.status)}
                selected={isSelected}
                testId={`document-row-${document.id}`}
              />
            );
          }}
        />
      )}
    </div>
  );
}

DocumentList.displayName = "DocumentList";
