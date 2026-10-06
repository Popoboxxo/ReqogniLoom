import * as React from "react";
import { useState } from "react";
import type { AppState } from "./state";
import {
  askMemory,
  cancelCapture,
  confirmCapture,
  disconnect,
  loadMemoryContext,
  openInBrowser,
  openInterviews,
  requestCapture,
  setCaptureEnabled,
} from "./state";
import { buttonStyle, ErrorBanner } from "./uiKit";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "4px 6px",
  background: "var(--bg-2, transparent)",
  border: "1px solid var(--border, #444)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text-1)",
  fontSize: "var(--text-sm)",
};

const sectionLabelStyle: React.CSSProperties = {
  fontSize: "var(--text-xs)",
  color: "var(--text-2)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const mutedStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };

export function ConnectedView({ state }: { state: AppState }) {
  const [askQuery, setAskQuery] = useState("");
  const [captureDraft, setCaptureDraft] = useState("");
  const workspaceId = state.connection?.workspaceId ?? "";

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

      {/* Memory read: entries + digest, with degraded/unavailable shown
          distinctly from a genuine empty result. */}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        <span style={sectionLabelStyle}>Memory</span>
        <button
          type="button"
          data-testid="memory-load-button"
          style={buttonStyle}
          disabled={state.memoryLoading}
          onClick={() => void loadMemoryContext(workspaceId)}
        >
          Load memory context
        </button>
        {state.memoryLoading && (
          <span data-testid="memory-loading" style={mutedStyle}>
            Loading…
          </span>
        )}
        <ErrorBanner message={state.memoryError} />
        {state.memoryDegraded && (
          <span data-testid="memory-degraded" style={{ fontSize: "var(--text-xs)", color: "var(--danger, red)" }}>
            Memory backend degraded{state.memoryDetail ? `: ${state.memoryDetail}` : "."}
          </span>
        )}
        {state.memoryDigest !== null && (
          <p data-testid="memory-digest" style={mutedStyle}>
            {state.memoryDigest}
          </p>
        )}
        {state.memoryLoaded && !state.memoryLoading && state.memoryEntries.length === 0 && !state.memoryDegraded && (
          <p data-testid="memory-empty" style={mutedStyle}>
            No memory entries.
          </p>
        )}
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "4px" }}>
          {state.memoryEntries.map((entry) => (
            <li key={entry.entry_id} data-testid={`memory-entry-${entry.entry_id}`} style={mutedStyle}>
              {entry.content}
            </li>
          ))}
        </ul>
        <div style={{ display: "flex", gap: "6px" }}>
          <input
            data-testid="memory-ask-input"
            style={inputStyle}
            value={askQuery}
            placeholder="Ask memory…"
            onChange={(e) => setAskQuery(e.target.value)}
          />
          <button
            type="button"
            data-testid="memory-ask-button"
            style={buttonStyle}
            disabled={state.memoryLoading || askQuery.trim() === ""}
            onClick={() => void askMemory(workspaceId, askQuery)}
          >
            Ask
          </button>
        </div>
        {state.memoryAnswer !== null && (
          <p data-testid="memory-answer" style={mutedStyle}>
            {state.memoryAnswer}
          </p>
        )}
      </div>

      {/* Gated capture: the toggle enables the surface, Review stages a draft
          (no network), Confirm is the only path to memory.write. */}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        <span style={sectionLabelStyle}>Capture</span>
        <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "var(--text-xs)" }}>
          <input
            type="checkbox"
            data-testid="capture-toggle"
            checked={state.captureEnabled}
            onChange={(e) => setCaptureEnabled(e.target.checked)}
          />
          Capture to memory
        </label>
        {/* The Capture section owns its own error: a failed memory.write must
            not surface under the Memory read section's banner. */}
        <div data-testid="capture-error-banner">
          <ErrorBanner message={state.captureError} />
        </div>
        {!state.captureEnabled ? (
          <span data-testid="capture-disabled" style={mutedStyle}>
            Capture is off.
          </span>
        ) : state.pendingCapture !== null ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <span data-testid="capture-pending" style={mutedStyle}>
              Review: {state.pendingCapture}
            </span>
            <div style={{ display: "flex", gap: "6px" }}>
              <button
                type="button"
                data-testid="capture-confirm-button"
                style={buttonStyle}
                disabled={state.captureBusy}
                onClick={() => void confirmCapture()}
              >
                Confirm
              </button>
              <button type="button" data-testid="capture-cancel-button" style={buttonStyle} onClick={cancelCapture}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <input
              data-testid="capture-input"
              style={inputStyle}
              value={captureDraft}
              placeholder="Fact to remember…"
              onChange={(e) => setCaptureDraft(e.target.value)}
            />
            <button
              type="button"
              data-testid="capture-review-button"
              style={buttonStyle}
              disabled={captureDraft.trim() === ""}
              onClick={() => {
                requestCapture(captureDraft);
                setCaptureDraft("");
              }}
            >
              Review
            </button>
          </div>
        )}
      </div>

      <button data-testid="disconnect-button" style={buttonStyle} onClick={() => void disconnect()}>
        Disconnect
      </button>
    </div>
  );
}
