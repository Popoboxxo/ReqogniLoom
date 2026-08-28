/**
 * Interview-management web widget — chat pane (plan Tasks 6 and 12).
 *
 * Renders `interview.transcript` and a send box that drives server-generated
 * conversational turns via `interviewsApi.chat`. The web app has no AI agent
 * of its own (unlike Claude Code/Opencode/Antigravity/Hermes), so the
 * backend generates both sides of the exchange -- this component only owns
 * the draft text and the loading/error UI state around one request.
 *
 * Multi-mode sessions (`session_kind === "multi"`) additionally render a
 * pending LLM proposal as a reviewable card (`interviewsApi.propose`,
 * previewed by ProposalPreviewGraph) and, after confirming, a result summary
 * of the artifacts created via `interviewsApi.formalize`.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  interviewsApi,
  type InterviewState,
  type MultiFormalizeResult,
  type ProposalItem,
} from "../../api/interviews";
import { getArtifactRoute } from "../../utils/artifactRoutes";
import { Spinner } from "../shared/Spinner/Spinner";
import { ProposalPreviewGraph } from "./ProposalPreviewGraph";
import styles from "./InterviewChatPane.module.css";

/**
 * {@link InterviewState} plus the multi-mode discriminator. Kept local to
 * this pane on purpose: backend `get_state()` payloads don't carry
 * `session_kind` yet (see `InterviewService.get_state()`), so widening the
 * shared client type would promise a field not every endpoint honours.
 * Absent/undefined behaves as `"single"` -- matching the backend's
 * normalisation -- which keeps every existing caller compatible.
 */
export type MultiModeInterview = InterviewState & {
  session_kind?: "single" | "multi";
};

/** One entry of a multi-mode result summary (`MultiFormalizeResult.created`). */
export interface CreatedArtifactRef {
  artifact_id: string;
  artifact_type: string;
}

export function InterviewChatPane({
  interview,
  onStateChange,
  onFormalized,
}: {
  interview: MultiModeInterview;
  onStateChange: (s: InterviewState) => void;
  /**
   * Optional by orchestrator decision (documented plan deviation): the plan
   * declares it required, but the existing caller InterviewWidget.tsx wires
   * no handler until Task 13 -- defaulting to a no-op avoids breaking it.
   */
  onFormalized?: (created: CreatedArtifactRef[]) => void;
}): JSX.Element {
  const { t } = useTranslation();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  // Double-submit guard for the proposal confirm button (same pattern as
  // `sending`): a second click while formalize() is in flight must not fire
  // a second POST.
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingProposal, setPendingProposal] = useState<ProposalItem[] | null>(null);
  const [createdArtifacts, setCreatedArtifacts] = useState<CreatedArtifactRef[] | null>(null);

  // Multi-mode: refresh the LLM proposal after every transcript turn. The
  // parent replaces the whole interview object via onStateChange after each
  // chat round-trip, so transcript identity marks a new turn. The cancelled
  // flag drops stale responses (unmount / superseded effect run).
  useEffect(() => {
    if (interview.session_kind !== "multi") return;
    let cancelled = false;
    interviewsApi
      .propose(interview.id)
      .then((r) => {
        if (!cancelled) setPendingProposal(r.proposal);
      })
      .catch(() => {
        // A failed proposal fetch must not wedge the pane; the next
        // transcript turn re-triggers this effect.
        if (!cancelled) setPendingProposal(null);
      });
    return () => {
      cancelled = true;
    };
  }, [interview.id, interview.session_kind, interview.transcript]);

  const send = async () => {
    if (!draft.trim()) return;
    setSending(true);
    setError(null);
    try {
      const { state } = await interviewsApi.chat(interview.id, draft);
      onStateChange(state);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setSending(false);
    }
  };

  const confirmProposal = async (): Promise<void> => {
    if (!pendingProposal || creating) return;
    setCreating(true);
    setError(null);
    try {
      // Declared return type predates multi-mode; at runtime a multi-kind
      // formalize() responds with MultiFormalizeResult (see api/interviews.ts).
      const result = (await interviewsApi.formalize(
        interview.id,
        pendingProposal
      )) as unknown as MultiFormalizeResult;
      setCreatedArtifacts(result.created);
      setPendingProposal(null);
      onFormalized?.(result.created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create artifacts.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className={styles.pane}>
      <div
        className={styles.transcript}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label={t("interview.multi.transcriptLabel", "Chat transcript")}
      >
        {interview.transcript.map((msg, i) => (
          <p
            key={i}
            className={msg.role === "user" ? styles.userMessage : styles.assistantMessage}
          >
            {msg.text}
          </p>
        ))}
      </div>
      {pendingProposal && !createdArtifacts && (
        <div className={styles.proposalCard}>
          <h3>{t("interview.multi.proposalHeading")}</h3>
          <ProposalPreviewGraph proposal={pendingProposal} />
          <button
            type="button"
            data-testid="interview-multi-confirm"
            onClick={() => void confirmProposal()}
            disabled={creating}
            aria-busy={creating}
          >
            {creating ? <Spinner label={t("interview.multi.confirm")} /> : t("interview.multi.confirm")}
          </button>
        </div>
      )}
      {createdArtifacts && (
        <div data-testid="interview-multi-result" className={styles.resultSummary}>
          <h3>{t("interview.multi.resultHeading")}</h3>
          <ul>
            {createdArtifacts.map((ref) => (
              <li key={ref.artifact_id}>
                <span className={styles.createdBadge} title={t("interview.multi.createdBadge")}>
                  {ref.artifact_type}
                </span>
                <Link to={getArtifactRoute(ref.artifact_type, ref.artifact_id)}>
                  {ref.artifact_id}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {error && <p className={styles.error}>{error}</p>}
      <div className={styles.inputRow}>
        <input
          data-testid="interview-chat-input"
          className={styles.input}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t("interview.multi.chatPlaceholder")}
          aria-label={t("interview.multi.chatPlaceholder")}
          disabled={sending}
        />
        <button
          type="button"
          data-testid="interview-chat-send"
          onClick={() => void send()}
          disabled={sending}
        >
          {sending ? <Spinner label={t("interview.multi.send")} /> : t("interview.multi.send")}
        </button>
      </div>
    </div>
  );
}
