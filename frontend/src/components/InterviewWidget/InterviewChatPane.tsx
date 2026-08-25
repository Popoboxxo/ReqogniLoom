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
import {
  interviewsApi,
  type InterviewState,
  type MultiFormalizeResult,
  type ProposalItem,
} from "../../api/interviews";
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
    if (!pendingProposal) return;
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
    }
  };

  return (
    <div className={styles.pane}>
      <div className={styles.transcript}>
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
        <div className="interview-proposal-card">
          <h3>{t("interview.multi.proposalHeading")}</h3>
          <ProposalPreviewGraph proposal={pendingProposal} />
          <button
            type="button"
            data-testid="interview-multi-confirm"
            onClick={() => void confirmProposal()}
          >
            {t("interview.multi.confirm")}
          </button>
        </div>
      )}
      {createdArtifacts && (
        <div data-testid="interview-multi-result" className="interview-result-summary">
          <h3>{t("interview.multi.resultHeading")}</h3>
          <ul>
            {createdArtifacts.map((ref) => (
              <li key={ref.artifact_id}>
                <span className="badge">{ref.artifact_type}</span>
                <a href={`/artifacts/${ref.artifact_id}`}>{ref.artifact_id}</a>
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
          disabled={sending}
        />
        <button
          type="button"
          data-testid="interview-chat-send"
          onClick={() => void send()}
          disabled={sending}
        >
          {sending ? <Spinner label="Sending" /> : "Send"}
        </button>
      </div>
    </div>
  );
}
