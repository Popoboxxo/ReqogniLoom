import * as React from "react";
import type { AppState } from "./state";
import { disconnect, openInBrowser } from "./state";

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "6px 12px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

export function ConnectedView({ state }: { state: AppState }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Connected to</span>
        <span style={{ fontSize: "var(--text-sm)" }}>{state.workspaceName}</span>
      </div>
      <button style={buttonStyle} onClick={() => void openInBrowser()}>
        Open ReqogniLoom
      </button>
      <button style={buttonStyle} onClick={() => void disconnect()}>
        Disconnect
      </button>
    </div>
  );
}
