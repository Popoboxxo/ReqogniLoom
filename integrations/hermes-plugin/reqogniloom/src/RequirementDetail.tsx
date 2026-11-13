import * as React from "react";
import type { AppState } from "./state";
import { backToList, openEditForm } from "./state";
import { buttonStyle, ErrorBanner } from "./uiKit";

const rowStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: "2px" };
const labelStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };
const mutedStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };

function ReadOnlyRow({
  label,
  value,
  testId,
}: {
  label: string;
  value: React.ReactNode;
  testId: string;
}): JSX.Element {
  return (
    <div style={rowStyle}>
      <span style={labelStyle}>{label}</span>
      <span data-testid={testId}>{value}</span>
    </div>
  );
}

// Read-only detail of the selected requirement. `level`, `tier_name`,
// `level_source` and `suspect` are rendered but never editable: level is
// derived from the hierarchy (ADR-005/027) and suspect is propagated by the
// trace engine -- the form deliberately owns neither (see RequirementForm).
export function RequirementDetail({ state }: { state: AppState }): JSX.Element {
  const requirement = state.activeRequirement;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <div style={{ display: "flex", gap: "8px" }}>
        <button
          type="button"
          data-testid="requirements-back-button"
          style={buttonStyle}
          onClick={backToList}
        >
          Back
        </button>
        <button
          type="button"
          data-testid="requirement-edit-button"
          style={buttonStyle}
          disabled={!requirement}
          onClick={openEditForm}
        >
          Edit
        </button>
      </div>

      <ErrorBanner message={state.requirementError} testId="requirement-error" />

      {state.requirementBusy && !requirement && <span style={mutedStyle}>Loading…</span>}

      {!state.requirementBusy && !requirement && !state.requirementError && (
        <p style={mutedStyle}>No requirement selected.</p>
      )}

      {requirement && (
        <>
          <ReadOnlyRow label="ID" value={requirement.uid ?? requirement.id} testId="requirement-detail-uid" />
          <ReadOnlyRow label="Title" value={requirement.title} testId="requirement-detail-title" />
          <ReadOnlyRow label="Status" value={requirement.status} testId="requirement-detail-status" />
          <ReadOnlyRow label="Type" value={requirement.type} testId="requirement-detail-type" />
          <ReadOnlyRow
            label="Level"
            value={requirement.level ?? "—"}
            testId="requirement-detail-level"
          />
          <ReadOnlyRow
            label="Tier"
            value={requirement.tier_name ?? "—"}
            testId="requirement-detail-tier"
          />
          <ReadOnlyRow
            label="Level Source"
            value={requirement.level_source}
            testId="requirement-detail-level-source"
          />
          <ReadOnlyRow
            label="Suspect"
            value={requirement.suspect ? "Yes" : "No"}
            testId="requirement-detail-suspect"
          />
          <ReadOnlyRow
            label="Description"
            value={requirement.description || "—"}
            testId="requirement-detail-description"
          />
          <ReadOnlyRow
            label="Acceptance Criteria"
            value={requirement.acceptance_criteria || "—"}
            testId="requirement-detail-acceptance"
          />
          <ReadOnlyRow
            label="Category"
            value={requirement.category || "—"}
            testId="requirement-detail-category"
          />
        </>
      )}
    </div>
  );
}
