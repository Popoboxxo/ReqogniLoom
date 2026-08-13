// integrations/hermes-plugin/reqogniloom/src/RequirementsList.tsx
import * as React from "react";
import type { AppState } from "./state";
import { setSearchTerm, loadRequirements, selectRequirement, openCreateForm, disconnect } from "./state";

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "4px 10px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

export function RequirementsList({ state }: { state: AppState }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px", height: "100%" }}>
      <div style={{ display: "flex", gap: "6px" }}>
        <input
          style={{
            flex: 1,
            background: "var(--bg-2)",
            color: "var(--text-1)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: "6px 8px",
            fontSize: "var(--text-sm)",
          }}
          value={state.searchTerm}
          placeholder="Search requirements…"
          onChange={(e) => setSearchTerm(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void loadRequirements(1);
          }}
        />
        <button style={buttonStyle} onClick={() => void loadRequirements(1)}>
          Search
        </button>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>{state.requirementsCount} total</span>
        <div style={{ display: "flex", gap: "6px" }}>
          <button style={buttonStyle} onClick={() => openCreateForm()}>
            + New
          </button>
          <button style={buttonStyle} onClick={() => void disconnect()}>
            Disconnect
          </button>
        </div>
      </div>

      {state.listError && <p style={{ color: "var(--red)", fontSize: "var(--text-xs)" }}>{state.listError}</p>}

      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "4px" }}>
        {state.listLoading && <p style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Loading…</p>}
        {!state.listLoading &&
          state.requirements.map((r) => (
            <button
              key={r.id}
              style={{
                textAlign: "left",
                background: "var(--bg-2)",
                color: "var(--text-1)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px",
                cursor: "pointer",
                fontSize: "var(--text-sm)",
              }}
              onClick={() => void selectRequirement(r.id)}
            >
              <div>{r.title}</div>
              <div style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>
                {r.uid ?? r.id} · {r.status}
              </div>
            </button>
          ))}
      </div>

      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <button
          style={buttonStyle}
          disabled={state.requirementsPage <= 1}
          onClick={() => void loadRequirements(state.requirementsPage - 1)}
        >
          Prev
        </button>
        <button
          style={buttonStyle}
          disabled={!state.hasMoreRequirements}
          onClick={() => void loadRequirements(state.requirementsPage + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}
