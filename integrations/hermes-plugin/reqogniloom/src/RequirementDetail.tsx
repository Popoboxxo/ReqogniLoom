// integrations/hermes-plugin/reqogniloom/src/RequirementDetail.tsx
import * as React from "react";
import type { AppState } from "./state";
import { backToList, openEditForm } from "./state";

const buttonStyle: React.CSSProperties = {
  background: "var(--accent)",
  color: "var(--bg-1)",
  border: "none",
  borderRadius: "var(--radius-sm)",
  padding: "4px 10px",
  cursor: "pointer",
  fontSize: "var(--text-xs)",
};

const rowStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: "2px" };
const labelStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };

export function RequirementDetail({ state }: { state: AppState }) {
  if (state.detailLoading) return <p style={{ fontSize: "var(--text-xs)", color: "var(--text-2)" }}>Loading…</p>;
  if (state.detailError) return <p style={{ color: "var(--red)", fontSize: "var(--text-xs)" }}>{state.detailError}</p>;
  const r = state.selectedRequirement;
  if (!r) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
      <button style={buttonStyle} onClick={() => backToList()}>
        ← Back
      </button>
      <h3 style={{ margin: 0, fontSize: "var(--text-sm)" }}>{r.title}</h3>

      <div style={rowStyle}>
        <span style={labelStyle}>ID</span>
        <span>{r.uid ?? r.id}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>Status</span>
        <span>{r.status}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>Type</span>
        <span>{r.type}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>Level</span>
        <span>{r.level ?? "—"}</span>
      </div>
      {r.verification_method && (
        <div style={rowStyle}>
          <span style={labelStyle}>Verification Method</span>
          <span>{r.verification_method}</span>
        </div>
      )}
      <div style={rowStyle}>
        <span style={labelStyle}>Description</span>
        <span>{r.description || "—"}</span>
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>Acceptance Criteria</span>
        <span>{r.acceptance_criteria || "—"}</span>
      </div>

      <button style={buttonStyle} onClick={() => openEditForm(r)}>
        Edit
      </button>
    </div>
  );
}
