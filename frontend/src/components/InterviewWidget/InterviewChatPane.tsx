/**
 * Interview-management web widget — chat pane (plan Task 6).
 *
 * Renders `interview.transcript` and a send box that drives server-generated
 * conversational turns via `interviewsApi.chat`. The web app has no AI agent
 * of its own (unlike Claude Code/Opencode/Antigravity/Hermes), so the
 * backend generates both sides of the exchange -- this component only owns
 * the draft text and the loading/error UI state around one request.
 */
import { useState } from "react";
import { interviewsApi, type InterviewState } from "../../api/interviews";
import { Spinner } from "../shared/Spinner/Spinner";
import styles from "./InterviewChatPane.module.css";

export function InterviewChatPane({
  interview,
  onStateChange,
}: {
  interview: InterviewState;
  onStateChange: (s: InterviewState) => void;
}): JSX.Element {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
