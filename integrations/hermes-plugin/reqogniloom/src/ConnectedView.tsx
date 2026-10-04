import * as React from "react";
import type { AppState } from "./state";
import { disconnect, openInBrowser, openInterviews } from "./state";
import { buttonStyle, ErrorBanner } from "./uiKit";

export function ConnectedView({ state }: { state: AppState }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Connected to</span>
        <span style={{ fontSize: "var(--text-sm)" }}>{state.workspaceName}</span>
      </div>
      {/* AUD-117: openInterviews() leaves view==="connected" on failure and
          only sets interviewError; without this banner the button silently
          did nothing. InterviewListView already renders the same banner. */}
      <ErrorBanner message={state.interviewError} />
      <button data-testid="open-in-browser-button" style={buttonStyle} onClick={() => void openInBrowser()}>
        Open ReqogniLoom
      </button>
      <button data-testid="open-interviews-button" style={buttonStyle} onClick={() => void openInterviews()}>
        Interviews
      </button>
      <button data-testid="disconnect-button" style={buttonStyle} onClick={() => void disconnect()}>
        Disconnect
      </button>
    </div>
  );
}
