/**
 * ARCH-L1-001 ReactFrontend — work state of one document (Plan F F3-T9).
 *
 * Composition only: the list owns filtering/selection, the detail owns the
 * read/edit/transition surface, the resume panel owns `work_item.resume`.
 * TanStack hooks provide the loading / error / empty / success states for
 * every data-bound surface — no panel renders as if data were always present.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractApiErrorMessage } from "../../api/client";
import {
  useCreateWorkItem,
  useWorkItemResume,
  useWorkItems,
} from "../../queries/workItems";
import type { WorkItemCreatePayload } from "../../api/workItems";
import { WorkItemCreateForm } from "./WorkItemCreateForm";
import { WorkItemDetail } from "./WorkItemDetail";
import { WorkItemList } from "./WorkItemList";
import { ResumePanel } from "./ResumePanel";
import styles from "./WorkItems.module.css";

export interface WorkItemsPanelProps {
  documentId: string;
  workspaceId?: string;
  canWrite: boolean;
}

export function WorkItemsPanel({
  documentId,
  workspaceId,
  canWrite,
}: WorkItemsPanelProps): JSX.Element {
  const { t } = useTranslation();
  const listQuery = useWorkItems(workspaceId, documentId);
  const resumeQuery = useWorkItemResume(workspaceId, documentId);
  const createMutation = useCreateWorkItem(workspaceId, documentId);

  const [selectedId, setSelectedId] = useState<string | undefined>(undefined);
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const items = useMemo(() => listQuery.data ?? [], [listQuery.data]);

  // Keep the selection valid when the list refreshes; an empty document has no
  // selected item, so the detail pane can show its select prompt.
  useEffect(() => {
    if (items.length === 0) {
      if (selectedId !== undefined) setSelectedId(undefined);
      return;
    }
    if (!selectedId || !items.some((item) => item.id === selectedId)) {
      setSelectedId(items[0].id);
    }
  }, [items, selectedId]);

  const selected = items.find((item) => item.id === selectedId);

  const openCreate = useCallback((): void => {
    setCreateError(null);
    setCreateOpen(true);
  }, []);

  const submitCreate = useCallback(
    (payload: WorkItemCreatePayload): void => {
      setCreateError(null);
      createMutation.mutate(
        { payload },
        {
          onSuccess: (created) => {
            setCreateOpen(false);
            setSelectedId(created.id);
          },
          onError: (error) => {
            setCreateError(
              extractApiErrorMessage(error) ?? t("work_items.createFailed")
            );
          },
        }
      );
    },
    [createMutation, t]
  );

  return (
    <section className={styles.panel} data-testid="work-items-panel">
      <header className={styles.header}>
        <div>
          <h3 className={styles.title}>{t("work_items.title")}</h3>
          <p className={styles.subtitle}>
            {t("work_items.summary", { value: items.length })}
          </p>
        </div>
      </header>

      <ResumePanel
        resume={resumeQuery.data}
        isLoading={resumeQuery.isLoading}
        error={resumeQuery.error}
        onRetry={() => {
          void resumeQuery.refetch();
        }}
        onSelect={setSelectedId}
      />

      {createOpen && workspaceId && (
        <WorkItemCreateForm
          workspaceId={workspaceId}
          documentId={documentId}
          isSaving={createMutation.isPending}
          error={createError}
          onCreate={submitCreate}
          onCancel={() => {
            if (!createMutation.isPending) setCreateOpen(false);
          }}
        />
      )}

      <WorkItemList
        items={items}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onCreateNew={openCreate}
        canCreate={canWrite}
        isLoading={listQuery.isLoading}
        error={listQuery.error}
        onRetry={() => {
          void listQuery.refetch();
        }}
      />

      {selected ? (
        <WorkItemDetail
          key={`${selected.id}-${selected.version}`}
          item={selected}
          canWrite={canWrite}
          workspaceId={workspaceId}
          documentId={documentId}
        />
      ) : (
        <p className={styles.hint} data-testid="work-item-select-prompt">
          {t("work_items.selectPrompt")}
        </p>
      )}
    </section>
  );
}
