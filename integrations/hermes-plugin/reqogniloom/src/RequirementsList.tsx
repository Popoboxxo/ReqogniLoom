import * as React from "react";
import { useState } from "react";
import type { AppState } from "./state";
import {
  backToConnected,
  openCreateForm,
  openRequirements,
  requirementsPageNext,
  requirementsPagePrevious,
  searchRequirements,
  selectRequirement,
} from "./state";
import { buttonStyle, ErrorBanner } from "./uiKit";

const searchInputStyle: React.CSSProperties = {
  flex: 1,
  padding: "4px 6px",
  background: "var(--bg-2, transparent)",
  border: "1px solid var(--border, #444)",
  borderRadius: "var(--radius-sm)",
  color: "var(--text-1)",
  fontSize: "var(--text-sm)",
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "2px",
  width: "100%",
  textAlign: "left",
  background: "var(--bg-2, transparent)",
  border: "1px solid var(--border, #444)",
  borderRadius: "var(--radius-sm)",
  padding: "6px 8px",
  cursor: "pointer",
  color: "var(--text-1)",
  fontSize: "var(--text-sm)",
};

const mutedStyle: React.CSSProperties = { fontSize: "var(--text-xs)", color: "var(--text-2)" };

// Paginated list of the connected workspace's requirements (Phase H / #1701).
// The list is the section's landing view: every load failure is reported here,
// with a retry, because openRequirements() switches the view before the request
// resolves (see state.ts) -- the hub would have nothing to show the error on.
export function RequirementsList({ state }: { state: AppState }): JSX.Element {
  // The input is local until committed (Enter/blur): a debounced remote search
  // would fire a request per keystroke, and each one invalidates the page chain.
  const [term, setTerm] = useState(state.requirementsSearch);

  const submitSearch = () => {
    // An unchanged term must not restart the page chain on every blur (the
    // click on New/Back blurs this input first).
    if (term === state.requirementsSearch) return;
    void searchRequirements(term);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      <button
        type="button"
        data-testid="requirements-back-button"
        style={buttonStyle}
        onClick={backToConnected}
      >
        Back
      </button>

      <input
        type="search"
        data-testid="requirements-search-input"
        aria-label="Search requirements"
        placeholder="Search requirements…"
        style={searchInputStyle}
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        onBlur={submitSearch}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            submitSearch();
          }
        }}
      />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={mutedStyle}>
          {state.requirementsCount} total · page {state.requirementsPage}
        </span>
        <button
          type="button"
          data-testid="requirements-new-button"
          style={buttonStyle}
          onClick={openCreateForm}
        >
          New
        </button>
      </div>

      <ErrorBanner message={state.requirementError} testId="requirement-error" />

      {state.requirementError && (
        <button
          type="button"
          data-testid="requirements-retry-button"
          style={buttonStyle}
          onClick={() => void openRequirements()}
        >
          Retry
        </button>
      )}

      {state.requirementBusy && <span style={mutedStyle}>Loading…</span>}

      {!state.requirementBusy && !state.requirementError && state.requirements.length === 0 && (
        <p style={mutedStyle}>No requirements yet. Create the first one with New.</p>
      )}

      <ul
        data-testid="requirements-list"
        style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "4px" }}
      >
        {state.requirements.map((requirement) => (
          <li key={requirement.id}>
            <button
              type="button"
              data-testid={`requirement-row-${requirement.id}`}
              style={rowStyle}
              onClick={() => void selectRequirement(requirement.id)}
            >
              <span>{requirement.title}</span>
              <span style={mutedStyle}>
                {requirement.uid ?? requirement.id} · {requirement.status} ·{" "}
                {requirement.tier_name ?? "—"}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <div style={{ display: "flex", justifyContent: "space-between", gap: "8px" }}>
        <button
          type="button"
          data-testid="requirements-previous-button"
          style={buttonStyle}
          disabled={!state.requirementsPrevious}
          onClick={() => void requirementsPagePrevious()}
        >
          Previous
        </button>
        <button
          type="button"
          data-testid="requirements-next-button"
          style={buttonStyle}
          disabled={!state.requirementsNext}
          onClick={() => void requirementsPageNext()}
        >
          Next
        </button>
      </div>
    </div>
  );
}
