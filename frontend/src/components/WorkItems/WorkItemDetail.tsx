/**
 * ARCH-L1-001 ReactFrontend — work-item detail (Plan F F3-T9).
 *
 * Read view plus two write paths the item owns: content editing (through
 * `<WorkItemEditForm>`, which forwards the entity `version` as `If-Match`) and
 * the tiered workflow transitions. `blocked` requires a reason (rule 10), the
 * extended preset's sign-off is surfaced through `signature_gate`, and a
 * concurrent edit answers 412/409 instead of overwriting the winner.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "../shared/Badge";
import { StatusBadge } from "../shared/StatusBadge";
import { extractApiErrorMessage } from "../../api/client";
import {
  useTransitionWorkItem,
  useUpdateWorkItem,
  useWorkItemTransitions,
} from "../../queries/workItems";
import type { WorkItem } from "../../types";
import type { WorkItemUpdatePayload } from "../../api/workItems";
import { InlineReferenceHints } from "./InlineReferenceHints";
import { WorkItemEditForm } from "./WorkItemEditForm";
import {
  workItemKindLabel,
  workItemKindVariant,
  workItemStatusLabel,
} from "./workItemLabels";
import styles from "./WorkItems.module.css";

export interface WorkItemDetailProps {
  item: WorkItem;
  canWrite: boolean;
  workspaceId?: string;
  documentId: string;
}

function ProgressBar({ value }: { value: number }): JSX.Element {
  const { t } = useTranslation();
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <span
      className={styles.progress}
      data-testid="work-item-detail-progress"
    >
      <progress
        className={styles.progressNative}
        value={clamped}
        max={100}
        aria-label={t("work_items.progressLabel")}
      />
      <span>{t("work_items.progressValue", { value: clamped })}</span>
    </span>
  );
}

export function WorkItemDetail({
  item,
  canWrite,
  workspaceId,
  documentId,
}: WorkItemDetailProps): JSX.Element {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [targetState, setTargetState] = useState("");
  const [reason, setReason] = useState("");
  const [credential, setCredential] = useState("");
  const [blockedReason, setBlockedReason] = useState("");

  const updateMutation = useUpdateWorkItem(workspaceId, documentId);
  const transitionsQuery = useWorkItemTransitions(item.id);
  const transitionMutation = useTransitionWorkItem(workspaceId, documentId);

  const allowed = transitionsQuery.data?.allowed_transitions ?? [];
  const currentState = transitionsQuery.data?.current_state ?? item.status;
  const selected = allowed.find((move) => move.target_state === targetState);
  const needsReason = Boolean(selected?.requires_change_reason);
  const needsCredential = Boolean(selected?.signature_gate);
  const needsBlockedReason = targetState === "blocked";
  const canExecute =
    canWrite &&
    Boolean(selected) &&
    (!needsReason || reason.trim().length > 0) &&
    (!needsCredential || credential.length > 0) &&
    (!needsBlockedReason || blockedReason.trim().length > 0) &&
    !transitionMutation.isPending;

  const save = (payload: WorkItemUpdatePayload): void => {
    setActionError(null);
    updateMutation.mutate(
      { id: item.id, payload, expectedVersion: item.version },
      {
        onSuccess: () => setEditing(false),
        onError: (error) => {
          setActionError(
            extractApiErrorMessage(error) ?? t("work_items.saveFailed")
          );
        },
      }
    );
  };

  const executeTransition = (): void => {
    if (!selected || !canExecute) return;
    setActionError(null);
    transitionMutation.mutate(
      {
        id: item.id,
        targetState: selected.target_state,
        options: {
          changeReason: reason.trim(),
          credential,
          blockedReason: needsBlockedReason
            ? blockedReason.trim()
            : undefined,
          expectedVersion: item.version,
        },
      },
      {
        onSuccess: () => {
          setTargetState("");
          setReason("");
          setCredential("");
          setBlockedReason("");
        },
        onError: (error) => {
          setActionError(
            extractApiErrorMessage(error) ?? t("work_items.transitionError")
          );
        },
      }
    );
  };

  if (editing) {
    return (
      <WorkItemEditForm
        item={item}
        workspaceId={workspaceId}
        isSaving={updateMutation.isPending}
        error={actionError}
        onSave={save}
        onCancel={() => {
          setActionError(null);
          setEditing(false);
        }}
      />
    );
  }

  return (
    <article className={styles.detail} data-testid="work-item-detail">
      <header className={styles.detailHeader}>
        <div>
          <h3 className={styles.detailTitle}>
            {item.title || t("work_items.untitled")}
          </h3>
          <p className={styles.detailMeta}>
            <Badge variant={workItemKindVariant(item.kind)}>
              {workItemKindLabel(t, item.kind)}
            </Badge>
            <span data-testid="work-item-detail-uid">
              {item.uid ?? item.id.slice(0, 8)}
            </span>
            <StatusBadge
              status={currentState}
              label={workItemStatusLabel(t, currentState)}
              testId="work-item-detail-status"
            />
            <span data-testid="work-item-detail-version">
              {t("work_items.versionLabel", { version: item.version })}
            </span>
          </p>
        </div>
        {canWrite && (
          <button
            type="button"
            className="btn-secondary"
            data-testid="work-item-edit"
            onClick={() => {
              setActionError(null);
              setEditing(true);
            }}
          >
            {t("work_items.edit")}
          </button>
        )}
      </header>

      {item.next_action && (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>
            {t("work_items.nextAction")}
          </h4>
          <p data-testid="work-item-detail-next">{item.next_action}</p>
        </section>
      )}

      {item.blocked_reason && (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>
            {t("work_items.blockedReason")}
          </h4>
          <p className={styles.hintWarning} data-testid="work-item-detail-blocked">
            {item.blocked_reason}
          </p>
        </section>
      )}

      {item.progress !== null && (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>
            {t("work_items.progressLabel")}
          </h4>
          <ProgressBar value={item.progress} />
        </section>
      )}

      <section className={styles.section}>
        <h4 className={styles.sectionTitle}>{t("work_items.body")}</h4>
        <div className={styles.bodyText} data-testid="work-item-detail-body">
          {item.body || t("work_items.bodyEmpty")}
        </div>
        <InlineReferenceHints text={item.body} workspaceId={workspaceId} />
      </section>

      {item.evidence_ref && (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>{t("work_items.evidence")}</h4>
          <p data-testid="work-item-detail-evidence">{item.evidence_ref}</p>
        </section>
      )}

      {item.exit_criteria && (
        <section className={styles.section}>
          <h4 className={styles.sectionTitle}>
            {t("work_items.exitCriteria")}
          </h4>
          <p data-testid="work-item-detail-exit">{item.exit_criteria}</p>
        </section>
      )}

      <p className={styles.hint} data-testid="work-item-detail-activity">
        {t("work_items.lastActivity", {
          actor: item.last_actor || t("work_items.unknownActor"),
          date: item.last_activity_at
            ? item.last_activity_at.slice(0, 16).replace("T", " ")
            : t("work_items.never"),
        })}
      </p>

      <section className={styles.section}>
        <h4 className={styles.sectionTitle}>{t("work_items.lifecycle")}</h4>
        {transitionsQuery.isLoading && (
          <span role="status" data-testid="work-item-transition-loading">
            {t("work_items.transitionLoading")}
          </span>
        )}
        {transitionsQuery.error && (
          <span role="alert" data-testid="work-item-transition-error">
            {t("work_items.transitionError")}
            <button
              type="button"
              className="btn-secondary"
              data-testid="work-item-transition-retry"
              onClick={() => {
                void transitionsQuery.refetch();
              }}
            >
              {t("work_items.retry")}
            </button>
          </span>
        )}
        {!transitionsQuery.isLoading &&
          !transitionsQuery.error &&
          allowed.length === 0 && (
            <span data-testid="work-item-transition-none">
              {t("work_items.transitionNone")}
            </span>
          )}

        {canWrite && allowed.length > 0 && (
          <div className={styles.actions}>
            <select
              className={styles.select}
              data-testid="work-item-transition-select"
              aria-label={t("work_items.transitionLabel")}
              value={targetState}
              disabled={transitionMutation.isPending}
              onChange={(event) => setTargetState(event.target.value)}
            >
              <option value="">{t("work_items.transitionPlaceholder")}</option>
              {allowed.map((move) => (
                <option key={move.target_state} value={move.target_state}>
                  {workItemStatusLabel(t, move.target_state)}
                </option>
              ))}
            </select>

            {needsBlockedReason && (
              <input
                className={styles.input}
                data-testid="work-item-transition-blocked-reason"
                type="text"
                value={blockedReason}
                placeholder={t("work_items.fieldBlockedReason")}
                aria-label={t("work_items.fieldBlockedReason")}
                disabled={transitionMutation.isPending}
                onChange={(event) => setBlockedReason(event.target.value)}
              />
            )}

            {needsReason && (
              <input
                className={styles.input}
                data-testid="work-item-transition-reason"
                type="text"
                value={reason}
                placeholder={t("work_items.transitionReason")}
                aria-label={t("work_items.transitionReason")}
                disabled={transitionMutation.isPending}
                onChange={(event) => setReason(event.target.value)}
              />
            )}

            {needsCredential && (
              <input
                className={styles.input}
                data-testid="work-item-transition-credential"
                type="password"
                autoComplete="current-password"
                value={credential}
                placeholder={t("work_items.transitionCredential")}
                aria-label={t("work_items.transitionCredential")}
                disabled={transitionMutation.isPending}
                onChange={(event) => setCredential(event.target.value)}
              />
            )}

            <button
              type="button"
              className="btn-primary"
              data-testid="work-item-transition-execute"
              disabled={!canExecute}
              onClick={executeTransition}
            >
              {transitionMutation.isPending
                ? t("work_items.transitionSaving")
                : t("work_items.transitionExecute")}
            </button>
          </div>
        )}
      </section>

      {actionError && (
        <p role="alert" className={styles.error} data-testid="work-item-action-error">
          {actionError}
        </p>
      )}
    </article>
  );
}
