import * as React from "react";
import type { AppState } from "./state";
import { resumeInterview, startNewInterview } from "./state";

// Mirrors the engine's IN_SCOPE_ARTIFACT_TYPES (Spec 1 plan,
// application/interview_protocol.py) -- fixed at design time, not fetched.
const IN_SCOPE_ARTIFACT_TYPES = [
  "Requirement", "ArchitectureElement", "StakeholderNeed", "Risk",
  "TestCase", "Adr", "Issue", "Goal",
] as const;

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "6px 12px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

export function InterviewListView({ state }: { state: AppState }): JSX.Element {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {state.interviewError && (
        <span style={{ color: "var(--danger, red)", fontSize: "var(--text-xs)" }}>
          {state.interviewError}
        </span>
      )}

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
          {IN_SCOPE_ARTIFACT_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              data-testid={`interview-start-${type}`}
              style={buttonStyle}
              onClick={() => void startNewInterview(type)}
              disabled={state.interviewBusy}
            >
              {type}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
