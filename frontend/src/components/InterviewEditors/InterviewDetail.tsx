/**
 * ARCH-L1-001 ReactFrontend — InterviewDetail (plan Task 6).
 *
 * Right-panel detail view for a selected interview session: status badge
 * (workflow mirror -- no `<WorkflowStatusEditor/>` here, the interview's
 * only two meaningful transitions are the domain actions Formalize/Abandon
 * below, not a free-form state picker), missing-field checklist, the
 * existing chat pane (`InterviewChatPane`) and artifact pane
 * (`InterviewArtifactPane`, formalize), plus a new Abandon action -- the
 * `interview.abandon` REST/MCP tool this plan added had no UI consumer yet.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { InterviewState } from "../../api/interviews";
import { interviewsApi } from "../../api/interviews";
import { extractErrorMessage } from "../../api/client";
import { StatusBadge } from "../shared/StatusBadge";
import { Spinner } from "../shared/Spinner/Spinner";
import { getWorkflowStatusLabel } from "../../utils/workflowStatus";
import { InterviewChatPane } from "../InterviewWidget/InterviewChatPane";
import { InterviewArtifactPane } from "../InterviewWidget/InterviewArtifactPane";
import styles from "./InterviewDetail.module.css";

interface InterviewDetailProps {
  interview: InterviewState | null;
  /** From the selected row's `InterviewSummary` -- `InterviewState` itself carries no `artifact_type`. */
  artifactType?: string;
  onChanged: () => void;
}

export function InterviewDetail({ interview, artifactType, onChanged }: InterviewDetailProps): JSX.Element {
  const { t } = useTranslation();
  const [session, setSession] = useState<InterviewState | null>(interview);
  const [isAbandoning, setIsAbandoning] = useState(false);
  const [abandonError, setAbandonError] = useState<string | null>(null);
  const [confirmAbandon, setConfirmAbandon] = useState(false);

  // Keep local (chat-pane-mutated) state in sync when a different session is
  // selected or the parent's query refetches.
  useEffect(() => {
    setSession(interview);
    setConfirmAbandon(false);
    setAbandonError(null);
  }, [interview]);

  if (!interview) {
    return <p className={styles.placeholder}>{t("interviews.selectInterview", "Select an interview session")}</p>;
  }

  const current = session ?? interview;
  const canAbandon = current.status === "in_progress";

  const handleAbandon = async (): Promise<void> => {
    setIsAbandoning(true);
    setAbandonError(null);
    try {
      await interviewsApi.abandon(current.id);
      setConfirmAbandon(false);
      onChanged();
    } catch (err) {
      setAbandonError(extractErrorMessage(err));
    } finally {
      setIsAbandoning(false);
    }
  };

  return (
    <div className={styles.detail} data-testid="interview-detail">
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h2 className={styles.headerTitle}>
            {artifactType
              ? t(`interviews.forType.${artifactType}`, artifactType)
              : t("interviews.detailTitle", "Interview")}
          </h2>
          <StatusBadge
            status={current.status}
            label={getWorkflowStatusLabel(current.status)}
            testId="interview-detail-status"
          />
        </div>
        {canAbandon && (
          <div className={styles.headerActions}>
            {confirmAbandon ? (
              <>
                <span>{t("interviews.confirmAbandon", "Abandon this interview?")}</span>
                <button
                  type="button"
                  className="btn-secondary"
                  data-testid="interview-abandon-confirm"
                  disabled={isAbandoning}
                  onClick={() => void handleAbandon()}
                >
                  {isAbandoning ? <Spinner label={t("actions.confirm", "Confirm")} /> : t("actions.confirm", "Confirm")}
                </button>
                <button
                  type="button"
                  className="btn-ghost"
                  data-testid="interview-abandon-cancel"
                  disabled={isAbandoning}
                  onClick={() => setConfirmAbandon(false)}
                >
                  {t("actions.cancel", "Cancel")}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn-secondary"
                data-testid="interview-abandon-btn"
                onClick={() => setConfirmAbandon(true)}
              >
                {t("interviews.abandon", "Abandon")}
              </button>
            )}
          </div>
        )}
      </div>

      {abandonError && (
        <p role="alert" data-testid="interview-abandon-error" className={styles.abandonError}>
          {abandonError}
        </p>
      )}

      {current.missing_fields.length > 0 && (
        <div className={styles.section}>
          <h3 className={styles.sectionTitle}>{t("interviews.missingFields", "Still missing")}</h3>
          <ul className={styles.missingFieldList} data-testid="interview-missing-fields">
            {current.missing_fields.map((f) => (
              <li key={f.name}>{f.name}</li>
            ))}
          </ul>
        </div>
      )}

      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>{t("interviews.chat", "Conversation")}</h3>
        <InterviewChatPane interview={current} onStateChange={setSession} />
      </div>

      <div className={styles.section}>
        <InterviewArtifactPane
          interview={current}
          onFormalized={() => {
            void interviewsApi.getState(current.id).then((s) => {
              setSession(s);
              onChanged();
            });
          }}
        />
      </div>
    </div>
  );
}

InterviewDetail.displayName = "InterviewDetail";
