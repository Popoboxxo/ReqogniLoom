/**
 * Interview-management web widget — floating toggle shell (plan Task 5-7).
 *
 * A `position: fixed` overlay, always mounted (via NavigationShell) on every
 * authenticated route. Toggle state persists in localStorage, same pattern
 * as ThemeContext's preference storage. Owns the single active-session slot
 * (spec §9 explicitly keeps this out of a separate multi-session browser
 * UI): with no session active, shows "start" buttons for the in-scope
 * artifact types; with one active, renders the chat pane (Task 6) and
 * artifact panel pane (Task 7).
 */
import { useEffect, useState } from "react";
import { useWorkspace } from "../../context/WorkspaceContext";
import { interviewsApi, type InterviewState } from "../../api/interviews";
import { InterviewChatPane } from "./InterviewChatPane";
import { InterviewArtifactPane } from "./InterviewArtifactPane";
import styles from "./InterviewWidget.module.css";

const STORAGE_KEY = "reqflow-interview-widget-open";

/** In-scope artifact types for interviews -- fixed at design time, mirrors
 * the Hermes plugin's `InterviewListView` (spec §1 of the engine design).
 * Not fetched from an API. */
const INTERVIEW_ARTIFACT_TYPES = [
  "Requirement",
  "ArchitectureElement",
  "StakeholderNeed",
  "Risk",
  "TestCase",
  "Adr",
  "Issue",
  "Goal",
] as const;

export function InterviewWidget(): JSX.Element {
  const { activeWorkspace } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<InterviewState | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    setOpen(localStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    localStorage.setItem(STORAGE_KEY, String(next));
  };

  const startInterview = async (artifactType: string) => {
    if (!activeWorkspace) return;
    setStarting(true);
    try {
      const state = await interviewsApi.start(activeWorkspace.id, artifactType);
      setSession(state);
    } finally {
      setStarting(false);
    }
  };

  if (!activeWorkspace) return <></>;

  return (
    <>
      <button
        type="button"
        data-testid="interview-widget-toggle"
        className={styles.toggle}
        onClick={toggle}
        aria-label="Interview assistant"
      >
        {"\u{1F4AC}"}
      </button>
      {open && (
        <div data-testid="interview-widget-panel" className={styles.panel}>
          {session ? (
            <>
              <InterviewChatPane interview={session} onStateChange={setSession} />
              <InterviewArtifactPane
                interview={session}
                onFormalized={() => {
                  // Refresh session state so a formalized/completed session
                  // is reflected everywhere in the panel (e.g. Formalize
                  // disables further edits once status !== "in_progress").
                  void interviewsApi.getState(session.id).then(setSession);
                }}
              />
            </>
          ) : (
            <div className={styles.startRow}>
              {INTERVIEW_ARTIFACT_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  data-testid={`interview-widget-start-${type}`}
                  className={styles.startButton}
                  disabled={starting}
                  onClick={() => void startInterview(type)}
                >
                  {type}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
