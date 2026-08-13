// integrations/hermes-plugin/reqogniloom/src/RequirementForm.tsx
import * as React from "react";
import type { AppState } from "./state";
import { backToList, updateFormField, submitForm } from "./state";

const inputStyle: React.CSSProperties = {
  background: "var(--bg-2)",
  color: "var(--text-1)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "6px 8px",
  fontSize: "var(--text-sm)",
  fontFamily: "var(--font-mono)",
  width: "100%",
  marginTop: "4px",
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

const labelStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };
const errorStyle: React.CSSProperties = { color: "var(--red)", fontSize: "var(--text-xs)", marginTop: "2px" };

export function RequirementForm({ state }: { state: AppState }) {
  const form = state.form;
  if (!form) return null;

  return (
    <form
      style={{ display: "flex", flexDirection: "column", gap: "10px" }}
      onSubmit={(e) => {
        e.preventDefault();
        void submitForm();
      }}
    >
      <h3 style={{ margin: 0, fontSize: "var(--text-sm)" }}>
        {form.mode === "create" ? "New Requirement" : "Edit Requirement"}
      </h3>

      <label style={labelStyle}>
        Title
        <input
          style={inputStyle}
          value={form.values.title ?? ""}
          onChange={(e) => updateFormField("title", e.target.value)}
        />
        {form.fieldErrors.title && <div style={errorStyle}>{form.fieldErrors.title.join(" ")}</div>}
      </label>

      <label style={labelStyle}>
        Description
        <textarea
          style={{ ...inputStyle, minHeight: "60px" }}
          value={form.values.description ?? ""}
          onChange={(e) => updateFormField("description", e.target.value)}
        />
        {form.fieldErrors.description && <div style={errorStyle}>{form.fieldErrors.description.join(" ")}</div>}
      </label>

      <label style={labelStyle}>
        Acceptance Criteria
        <textarea
          style={{ ...inputStyle, minHeight: "60px" }}
          value={form.values.acceptance_criteria ?? ""}
          onChange={(e) => updateFormField("acceptance_criteria", e.target.value)}
        />
        {form.fieldErrors.acceptance_criteria && (
          <div style={errorStyle}>{form.fieldErrors.acceptance_criteria.join(" ")}</div>
        )}
      </label>

      <label style={labelStyle}>
        Category
        <input
          style={inputStyle}
          value={form.values.category ?? ""}
          onChange={(e) => updateFormField("category", e.target.value)}
        />
      </label>

      <label style={labelStyle}>
        Level (0-4)
        <input
          style={inputStyle}
          type="number"
          min={0}
          max={4}
          value={form.values.level ?? ""}
          onChange={(e) => updateFormField("level", e.target.value === "" ? undefined : Number(e.target.value))}
        />
        {form.fieldErrors.level && <div style={errorStyle}>{form.fieldErrors.level.join(" ")}</div>}
      </label>

      {form.mode === "edit" && (
        <label style={labelStyle}>
          Change Reason
          <input
            style={inputStyle}
            value={form.values.change_reason ?? ""}
            placeholder="required on extended-rigor workspaces"
            onChange={(e) => updateFormField("change_reason", e.target.value)}
          />
          {form.fieldErrors.change_reason && (
            <div style={errorStyle}>{form.fieldErrors.change_reason.join(" ")}</div>
          )}
        </label>
      )}

      {form.submitError && <p style={errorStyle}>{form.submitError}</p>}

      <div style={{ display: "flex", gap: "8px" }}>
        <button type="submit" style={buttonStyle} disabled={form.submitting || !form.values.title}>
          {form.submitting ? "Saving…" : "Save"}
        </button>
        <button type="button" style={buttonStyle} onClick={() => backToList()}>
          Cancel
        </button>
      </div>
    </form>
  );
}
