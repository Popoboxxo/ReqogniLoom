/**
 * ARCH-L1-001 ReactFrontend — work-item list inside a document (F3-T9).
 *
 * Mirrors the other artifact lists: filter/search derive their options from
 * the loaded rows, empty and no-match are distinct states, and every row is a
 * button with the shared `btn-ghost` chrome so the design-system ratchet sees
 * a real button. The status/kind chips are the shared `<Badge>` family.
 */

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "../shared/Badge";
import { EmptyState } from "../shared/EmptyState";
import { ListToolbar } from "../shared/ListToolbar";
import { StatusBadge } from "../shared/StatusBadge";
import type { WorkItem } from "../../types";
import { WORK_ITEM_KINDS } from "../../types";
import { buildStatusFilterOptions } from "../../utils/workflowStatus";
import {
  workItemKindLabel,
  workItemKindVariant,
  workItemStatusLabel,
} from "./workItemLabels";
import styles from "./WorkItems.module.css";

export interface WorkItemListProps {
  items: WorkItem[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onCreateNew: () => void;
  canCreate: boolean;
  isLoading: boolean;
  error: Error | null;
  onRetry: () => void;
}

export function WorkItemList({
  items,
  selectedId,
  onSelect,
  onCreateNew,
  canCreate,
  isLoading,
  error,
  onRetry,
}: WorkItemListProps): JSX.Element {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return items.filter((item) => {
      if (kindFilter && item.kind !== kindFilter) return false;
      if (statusFilter && item.status !== statusFilter) return false;
      if (!needle) return true;
      const haystack =
        `${item.title} ${item.uid ?? ""} ${item.next_action} ${item.body}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [items, kindFilter, search, statusFilter]);

  const statusOptions = useMemo(
    () => buildStatusFilterOptions(items, statusFilter),
    [items, statusFilter]
  );

  if (isLoading) {
    return (
      <EmptyState
        variant="loading"
        testId="work-items-list-loading"
        label={t("work_items.loading")}
      />
    );
  }

  if (error) {
    return (
      <EmptyState
        variant="error"
        testId="work-items-list-error"
        title={t("work_items.loadFailed")}
        description={error.message}
        onRetry={onRetry}
        retryLabel={t("work_items.retry")}
      />
    );
  }

  const hasControls = Boolean(search || kindFilter || statusFilter);
  const resetFilters = (): void => {
    setSearch("");
    setKindFilter("");
    setStatusFilter("");
  };

  return (
    <div data-testid="work-items-list">
      <ListToolbar
        testIdPrefix="work-items-list"
        searchValue={search}
        onSearchChange={setSearch}
        searchPlaceholder={t("work_items.searchPlaceholder")}
        filters={[
          {
            id: "kind",
            allLabel: t("work_items.allKinds"),
            value: kindFilter,
            options: WORK_ITEM_KINDS.map((kind) => ({
              value: kind,
              label: workItemKindLabel(t, kind),
            })),
            onChange: setKindFilter,
          },
          {
            id: "status",
            allLabel: t("work_items.allStatuses"),
            value: statusFilter,
            options: statusOptions,
            onChange: setStatusFilter,
          },
        ]}
        countLabel={
          hasControls
            ? t("work_items.filteredCount", {
                shown: visible.length,
                total: items.length,
              })
            : String(items.length)
        }
        actions={
          canCreate ? (
            <button
              type="button"
              className="btn-primary"
              data-testid="work-item-new"
              onClick={onCreateNew}
            >
              {t("work_items.newItem")}
            </button>
          ) : undefined
        }
      />

      {items.length === 0 ? (
        <EmptyState
          variant="empty"
          testId="work-items-list-empty"
          title={t("work_items.emptyTitle")}
          description={t("work_items.emptyDescription")}
          actions={
            canCreate
              ? [
                  {
                    label: t("work_items.newItem"),
                    prefixWithPlus: true,
                    onClick: onCreateNew,
                    testId: "work-items-list-empty-create",
                  },
                ]
              : []
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState
          variant="no-match"
          testId="work-items-list-no-match"
          onResetFilters={resetFilters}
          resetFiltersLabel={t("work_items.resetFilters")}
        />
      ) : (
        <ul className={styles.list} data-testid="work-items-list-rows">
          {visible.map((item) => {
            const selected = item.id === selectedId;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  className={`${styles.rowLayout} ${
                    selected ? styles.rowSelected : ""
                  } btn-ghost`}
                  data-testid={`work-item-row-${item.id}`}
                  aria-current={selected ? "true" : undefined}
                  onClick={() => onSelect(item.id)}
                >
                  <span className={styles.rowMain}>
                    <Badge
                      variant={workItemKindVariant(item.kind)}
                      testId={`work-item-kind-${item.id}`}
                    >
                      {workItemKindLabel(t, item.kind)}
                    </Badge>
                    <span className={styles.rowTitle}>
                      {item.title || t("work_items.untitled")}
                    </span>
                    <StatusBadge
                      status={item.status}
                      label={workItemStatusLabel(t, item.status)}
                      testId={`work-item-status-${item.id}`}
                    />
                  </span>
                  <span className={styles.rowMeta}>
                    <span>{item.uid ?? item.id.slice(0, 8)}</span>
                    {item.progress !== null && (
                      <span data-testid={`work-item-progress-${item.id}`}>
                        {t("work_items.progressValue", { value: item.progress })}
                      </span>
                    )}
                    {item.next_action && (
                      <span data-testid={`work-item-next-${item.id}`}>
                        {item.next_action}
                      </span>
                    )}
                  </span>
                  {item.progress !== null && (
                    <span className={styles.progress}>
                      <progress
                        className={styles.progressNative}
                        value={Math.min(100, Math.max(0, item.progress))}
                        max={100}
                        aria-label={t("work_items.progressLabel")}
                      />
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
