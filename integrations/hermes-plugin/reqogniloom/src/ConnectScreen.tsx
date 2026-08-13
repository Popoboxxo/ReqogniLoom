import * as React from "react";
import { useState } from "react";
import type { AppState } from "./state";
import { connectWithCredentials, chooseWorkspace } from "./state";

const inputStyle: React.CSSProperties = {
  background: "var(--bg-2)",
  color: "var(--text-1)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "6px 8px",
  fontSize: "var(--text-sm)",
  fontFamily: "var(--font-mono)",
};

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "6px 12px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

export function ConnectScreen({ state }: { state: AppState }) {
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");

  if (state.pendingWorkspaces.length > 0) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <p style={{ color: "var(--text-2)", fontSize: "var(--text-xs)" }}>Choose a workspace:</p>
        {state.pendingWorkspaces.map((w) => (
          <button key={w.id} style={{ ...buttonStyle, textAlign: "left" }} onClick={() => void chooseWorkspace(w)}>
            {w.name}
          </button>
        ))}
      </div>
    );
  }

  return (
    <form
      style={{ display: "flex", flexDirection: "column", gap: "8px" }}
      onSubmit={(e) => {
        e.preventDefault();
        void connectWithCredentials(baseUrl, apiKey);
      }}
    >
      <label style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>
        Workspace URL
        <input
          style={{ ...inputStyle, width: "100%", marginTop: "4px" }}
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://reqogniloom.example.com"
        />
      </label>
      <label style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>
        API Key
        <input
          style={{ ...inputStyle, width: "100%", marginTop: "4px" }}
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="reqlo_..."
        />
      </label>
      {state.connectError && <p style={{ color: "var(--red)", fontSize: "var(--text-xs)" }}>{state.connectError}</p>}
      <button type="submit" style={buttonStyle} disabled={state.connecting || !baseUrl || !apiKey}>
        {state.connecting ? "Connecting…" : "Connect"}
      </button>
    </form>
  );
}
