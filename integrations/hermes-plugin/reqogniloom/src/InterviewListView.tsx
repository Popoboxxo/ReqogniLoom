import * as React from "react";
import type { AppState } from "./state";
import { closeInterview, resumeInterview, startNewInterview } from "./state";
import { buttonStyle, ErrorBanner } from "./uiKit";

// Mirrors the engine's IN_SCOPE_ARTIFACT_TYPES (Spec 1 plan,
// application/interview_protocol.py) -- fixed at design time, not fetched.
const IN_SCOPE_ARTIFACT_TYPES = [
  "Requirement", "ArchitectureElement", "StakeholderNeed", "Risk",
  "TestCase", "Adr", "Issue", "Goal",
] as const;

// formalize() only implements the "Requirement" branch so far (backend
// application/interview_service.py:569-574, "the other 7 types follow the
// identical pattern in a later pass") -- offering them here without a
// warning let a user fill in a whole non-Requirement interview and only
// discover it can't be formalized at the very last click.
const FORMALIZABLE_ARTIFACT_TYPES: ReadonlySet<string> = new Set(["Requirement"]);

export function InterviewListView({ state }: { state: AppState }): JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <button
        type="button"
        data-testid="interview-list-back-button"
        style={buttonStyle}
        onClick={closeInterview}
      >
        Back
      </button>

      <ErrorBanner message={state.interviewError} />

      <div>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Active sessions</span>
        {state.interviewList.length === 0 && (
          <p style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>None yet.</p>
        )}
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {state.interviewList.map((session) => (
            <li key={session.id}>
              <button
                type="button"
                data-testid={`interview-resume-${session.id}`}
                style={buttonStyle}
                onClick={() => void resumeInterview(session.id)}
              >
                {session.artifact_type} — {session.status}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Start new</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
          {IN_SCOPE_ARTIFACT_TYPES.map((type) => {
            const formalizable = FORMALIZABLE_ARTIFACT_TYPES.has(type);
            return (
              <button
                key={type}
                type="button"
                data-testid={`interview-start-${type}`}
                style={buttonStyle}
                onClick={() => void startNewInterview(type)}
                disabled={state.interviewBusy || !formalizable}
                title={formalizable ? undefined : "Not formalizable yet — this artifact type is not supported by formalize() yet."}
              >
                {type}
                {!formalizable && " (soon)"}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
