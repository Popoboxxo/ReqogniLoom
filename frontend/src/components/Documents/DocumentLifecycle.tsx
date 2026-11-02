/**
 * ARCH-L1-001 ReactFrontend — Document lifecycle control (Plan F F2-T8).
 *
 * Fetches `GET /documents/{id}/transitions/` and renders the allowed moves for
 * the current state. A move that requires a change reason (e.g.
 * `In Prüfung → Freigegeben`, `Freigegeben → In Prüfung`) reveals a reason
 * field and keeps the execute action disabled until it is filled, so the UI
 * cannot POST a request the server would reject. `expected_version` is the
 * document's own optimistic-lock revision (ADR-026 §9) — a concurrent edit
 * therefore answers 412/409 instead of silently overwriting the winner.
 *
 * This is deliberately Document-specific instead of the generic
 * `<WorkflowStatusEditor>`: the generic control posts `expected_version`
 * against the WorkflowItemState revision, while Document's route guards the
 * entity revision. Reusing it would send the wrong precondition value.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusBadge } from "../shared/StatusBadge";
import { getWorkflowStatusLabel } from "../../utils/workflowStatus";
import { extractApiErrorMessage } from "../../api/client";
import {
  useDocumentTransitions,
  useTransitionDocument,
} from "../../queries/documents";
import type { Document } from "../../types";
import styles from "./Documents.module.css";

export interface DocumentLifecycleProps {
  document: Document;
  canWrite: boolean;
  onTransitionComplete: () => void;
  workspaceId?: string;
}

export function DocumentLifecycle({
  document,
  canWrite,
  onTransitionComplete,
  workspaceId,
}: DocumentLifecycleProps): JSX.Element {
  const { t } = useTranslation();
  const transitionsQuery = useDocumentTransitions(document.id);
  const transitionMutation = useTransitionDocument(workspaceId);

  const allowed = useMemo(
    () => transitionsQuery.data?.allowed_transitions ?? [],
    [transitionsQuery.data]
  );
  const currentState =
    transitionsQuery.data?.current_state ?? document.status;

  const [targetState, setTargetState] = useState("");
  const [reason, setReason] = useState("");
  const [credential, setCredential] = useState("");

  // A refresh can remove the previously selected move (another user advanced
  // the document); clearing it prevents posting a stale transition.
  useEffect(() => {
    if (targetState && !allowed.some((item) => item.target_state === targetState)) {
      setTargetState("");
      setReason("");
      setCredential("");
    }
  }, [allowed, targetState]);

  const selected = allowed.find(
    (item) => item.target_state === targetState
  );
  const needsReason = Boolean(selected?.requires_change_reason);
  const needsCredential = Boolean(selected?.signature_gate);
  const canExecute =
    canWrite &&
    Boolean(selected) &&
    (!needsReason || reason.trim().length > 0) &&
    (!needsCredential || credential.length > 0) &&
    !transitionMutation.isPending;

  const execute = (): void => {
    if (!selected || !canExecute) return;
    transitionMutation.mutate(
      {
        id: document.id,
        targetState: selected.target_state,
        options: {
          changeReason: reason.trim(),
          credential,
          expectedVersion: document.version,
        },
      },
      {
        onSuccess: () => {
          setTargetState("");
          setReason("");
          setCredential("");
          onTransitionComplete();
        },
      }
    );
  };

  return (
    <div className={styles.lifecycle} data-testid="document-lifecycle">
      <StatusBadge
        status={currentState}
        label={getWorkflowStatusLabel(currentState)}
        testId="document-lifecycle-status"
      />

      {transitionsQuery.isLoading && (
        <span role="status" data-testid="document-lifecycle-loading">
          {t("documents.transitionLoading")}
        </span>
      )}

      {transitionsQuery.error && (
        <span role="alert" data-testid="document-lifecycle-error">
          {t("documents.transitionError")}
          <button
            type="button"
            className="btn-secondary"
            data-testid="document-lifecycle-retry"
            onClick={() => {
              void transitionsQuery.refetch();
            }}
          >
            {t("documents.retry")}
          </button>
        </span>
      )}

      {!transitionsQuery.isLoading &&
        !transitionsQuery.error &&
        allowed.length === 0 && (
          <span data-testid="document-lifecycle-none">
            {t("documents.transitionNone")}
          </span>
        )}

      {canWrite && allowed.length > 0 && (
        <div className={styles.transitionControls}>
          <label
            className={styles.label}
            htmlFor="document-transition-select"
          >
            {t("documents.transitionLabel")}
          </label>
          <select
            id="document-transition-select"
            data-testid="document-transition-select"
            className={styles.select}
            value={targetState}
            disabled={transitionMutation.isPending}
            onChange={(event) => setTargetState(event.target.value)}
          >
            <option value="">{t("documents.transitionPlaceholder")}</option>
            {allowed.map((item) => (
              <option key={item.target_state} value={item.target_state}>
                {getWorkflowStatusLabel(item.target_state)}
              </option>
            ))}
          </select>

          {needsReason && (
            <>
              <label
                className={styles.label}
                htmlFor="document-transition-reason"
              >
                {t("documents.transitionReason")}
              </label>
              <textarea
                id="document-transition-reason"
                data-testid="document-transition-reason"
                className={styles.textarea}
                value={reason}
                rows={2}
                maxLength={2000}
                disabled={transitionMutation.isPending}
                onChange={(event) => setReason(event.target.value)}
              />
            </>
          )}

          {needsCredential && (
            <>
              <label
                className={styles.label}
                htmlFor="document-transition-credential"
              >
                {t("documents.transitionCredential")}
              </label>
              <input
                id="document-transition-credential"
                data-testid="document-transition-credential"
                className={styles.input}
                type="password"
                autoComplete="current-password"
                value={credential}
                disabled={transitionMutation.isPending}
                onChange={(event) => setCredential(event.target.value)}
              />
            </>
          )}

          <button
            type="button"
            className="btn-primary"
            data-testid="document-transition-execute"
            disabled={!canExecute}
            onClick={execute}
          >
            {transitionMutation.isPending
              ? t("documents.transitionSaving")
              : t("documents.transitionExecute")}
          </button>
        </div>
      )}

      {transitionMutation.error && (
        <p role="alert" className={styles.error} data-testid="document-transition-error">
          {extractApiErrorMessage(transitionMutation.error) ??
            t("documents.transitionError")}
        </p>
      )}
    </div>
  );
}

DocumentLifecycle.displayName = "DocumentLifecycle";
