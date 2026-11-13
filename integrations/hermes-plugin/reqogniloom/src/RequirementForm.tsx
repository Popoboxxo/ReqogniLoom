import * as React from "react";
import type { AppState } from "./state";
import { backToList, submitForm, updateFormField } from "./state";
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

const labelStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };
const errorStyle: React.CSSProperties = { color: "var(--danger, red)", fontSize: "var(--text-xs)" };
const mutedStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };

// Only the three server-accepted requirement types; `type` is a ChoiceField
// backend-side, so a free-text value would be a guaranteed 400.
const REQUIREMENT_TYPES = ["SyReq", "UseCase", "FeatureReq"] as const;

function FieldError({ field, message }: { field: string; message?: string }): JSX.Element | null {
  if (!message) return null;
  return (
    <span data-testid={`requirement-form-error-${field}`} style={errorStyle}>
      {message}
    </span>
  );
}

// Unsaved input only exists in the draft, so leaving without a prompt would
// silently discard it. A form that still matches the loaded requirement (or an
// untouched create form) is not dirty and leaves without a dialog.
function isDirty(state: AppState): boolean {
  const form = state.requirementForm;
  if (!form) return false;
  if (form.changeReason.trim() !== "") return true;
  const loaded = state.activeRequirement;
  const baseline =
    form.mode === "edit" && loaded
      ? {
          title: loaded.title,
          description: loaded.description ?? "",
          acceptance_criteria: loaded.acceptance_criteria ?? "",
          category: loaded.category ?? "",
          type: loaded.type,
        }
      : { title: "", description: "", acceptance_criteria: "", category: "", type: "SyReq" };
  return (
    form.values.title !== baseline.title ||
    form.values.description !== baseline.description ||
    form.values.acceptance_criteria !== baseline.acceptance_criteria ||
    form.values.category !== baseline.category ||
    form.values.type !== baseline.type
  );
}

// Deliberately has no level/tier/level-source/suspect field: level is derived
// (ADR-005/027) and the other three are engine-owned, so a control here could
// only produce a 400 or silently lose the user's input. `change_reason` is the
// one conditional field: the standard/extended presets refuse an update without
// it, and the store turns that 400 into `fieldErrors.change_reason` -- from then
// on the field is a required one (see state.ts::applyRequirementFormError).
export function RequirementForm({ state }: { state: AppState }): JSX.Element | null {
  const form = state.requirementForm;
  if (!form) return null;

  const changeReasonRequired = Boolean(form.fieldErrors.change_reason);

  const cancel = () => {
    // The Hermes panel host is not guaranteed to expose window.confirm; without
    // it, navigating is still safe -- backToList() keeps the draft -- rather
    // than trapping the user in the form.
    if (typeof window.confirm === "function" && isDirty(state) && !window.confirm("Discard unsaved changes?")) {
      return;
    }
    backToList();
  };

  return (
    <form
      style={{ display: "flex", flexDirection: "column", gap: "10px" }}
      onSubmit={(e) => {
        e.preventDefault();
        void submitForm();
      }}
    >
      <span style={mutedStyle}>{form.mode === "create" ? "New Requirement" : "Edit Requirement"}</span>

      <label style={labelStyle}>
        Title
        <input
          type="text"
          data-testid="requirement-form-title"
          style={inputStyle}
          value={form.values.title}
          onChange={(e) => updateFormField("title", e.target.value)}
        />
        <FieldError field="title" message={form.fieldErrors.title} />
      </label>

      <label style={labelStyle}>
        Description
        <textarea
          data-testid="requirement-form-description"
          style={{ ...inputStyle, minHeight: "60px" }}
          value={form.values.description}
          onChange={(e) => updateFormField("description", e.target.value)}
        />
        <FieldError field="description" message={form.fieldErrors.description} />
      </label>

      <label style={labelStyle}>
        Acceptance Criteria
        <textarea
          data-testid="requirement-form-acceptance"
          style={{ ...inputStyle, minHeight: "60px" }}
          value={form.values.acceptance_criteria}
          onChange={(e) => updateFormField("acceptance_criteria", e.target.value)}
        />
        <FieldError field="acceptance_criteria" message={form.fieldErrors.acceptance_criteria} />
      </label>

      <label style={labelStyle}>
        Category
        <input
          type="text"
          data-testid="requirement-form-category"
          style={inputStyle}
          value={form.values.category}
          onChange={(e) => updateFormField("category", e.target.value)}
        />
        <FieldError field="category" message={form.fieldErrors.category} />
      </label>

      <label style={labelStyle}>
        Type
        <select
          data-testid="requirement-form-type"
          style={inputStyle}
          value={form.values.type}
          onChange={(e) => updateFormField("type", e.target.value)}
        >
          {REQUIREMENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <FieldError field="type" message={form.fieldErrors.type} />
      </label>

      {form.mode === "edit" && (
        <label style={labelStyle}>
          Change Reason{changeReasonRequired ? " (required)" : ""}
          <input
            type="text"
            data-testid="requirement-form-change-reason"
            style={inputStyle}
            value={form.changeReason}
            placeholder="Why is this requirement changing?"
            required={changeReasonRequired}
            aria-required={changeReasonRequired}
            onChange={(e) => updateFormField("change_reason", e.target.value)}
          />
          <FieldError field="change_reason" message={form.fieldErrors.change_reason} />
        </label>
      )}

      <ErrorBanner message={state.requirementError} testId="requirement-error" />

      <div style={{ display: "flex", gap: "8px" }}>
        <button
          type="submit"
          data-testid="requirement-form-submit"
          style={buttonStyle}
          disabled={state.requirementBusy}
        >
          {state.requirementBusy ? "Saving…" : "Save"}
        </button>
        <button type="button" data-testid="requirement-form-cancel" style={buttonStyle} onClick={cancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
