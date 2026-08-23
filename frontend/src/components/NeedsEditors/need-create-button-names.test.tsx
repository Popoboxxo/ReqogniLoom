/**
 * Issue #678 (a11y, HIGH) — ambiguous duplicate "create need" button names.
 *
 * NeedsEditors' <PageHeader> primary action and NeedList's empty-state
 * "create" action both call the same create-flow trigger and share the
 * exact same visible wording ("Neuer Bedarf" / "New Need") — they are
 * simultaneously present in the DOM whenever the list is empty. The
 * create form's own submit button ("Erstellen" / "Create") can also be
 * open at the same time. Before the fix, `getByRole("button", { name: ... })`
 * queries targeting any one of these were ambiguous or relied on
 * translation strings happening to differ.
 *
 * This test renders the real <PageHeader> + <NeedList> composition (the
 * same pairing NeedsEditors.tsx uses) with an empty needs list and the
 * create form open — the worst case where all three "create" controls
 * coexist — and asserts each has a distinct, individually queryable
 * accessible name.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { PageHeader } from "../shared/PageHeader";
import { NeedList } from "./NeedList";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

function renderNeedsPage() {
  return render(
    <MemoryRouter>
      <PageHeader
        title="Bedarfe"
        primaryAction={{
          label: "Neuer Bedarf",
          ariaLabel: "Bedarf-Formular öffnen",
          onClick: vi.fn(),
          testId: "create-need-btn",
        }}
      />
      <NeedList
        needs={[]}
        showCreateForm
        setShowCreateForm={vi.fn()}
        newTitle=""
        setNewTitle={vi.fn()}
        newDescription=""
        setNewDescription={vi.fn()}
        newCategory=""
        setNewCategory={vi.fn()}
        onSubmitCreate={vi.fn()}
        createError={null}
        onCreateClick={vi.fn()}
      />
    </MemoryRouter>,
  );
}

describe("NeedsEditors — create-trigger accessible names (issue #678)", () => {
  it("gives the header, empty-state and form-submit create controls distinct accessible names", () => {
    renderNeedsPage();

    // Each of the three "create need" controls must be uniquely queryable
    // by role + accessible name — no `getByRole` call here may throw
    // "Found multiple elements".
    const headerBtn = screen.getByRole("button", { name: "Bedarf-Formular öffnen" });
    const emptyStateBtn = screen.getByRole("button", { name: "Ersten Bedarf anlegen" });
    const submitBtn = screen.getByRole("button", { name: "Bedarf jetzt erstellen" });

    expect(headerBtn).toBeInTheDocument();
    expect(emptyStateBtn).toBeInTheDocument();
    expect(submitBtn).toBeInTheDocument();

    // Pairwise distinct — the actual defect (identical accessible names).
    const names = [
      headerBtn.getAttribute("aria-label"),
      emptyStateBtn.getAttribute("aria-label"),
      submitBtn.getAttribute("aria-label"),
    ];
    expect(new Set(names).size).toBe(3);

    // The header and empty-state buttons still visually read "Neuer
    // Bedarf" for sighted users (only the accessible name is disambiguated).
    expect(headerBtn).toHaveTextContent("Neuer Bedarf");
    expect(emptyStateBtn).toHaveTextContent("Neuer Bedarf");
    expect(submitBtn).toHaveTextContent("Create");
  });

  it("no longer matches multiple buttons for a loose /create|erstellen/i role query", () => {
    renderNeedsPage();

    // The literal regex query from the bug report against each button's
    // accessible name (not the raw visible text) — must resolve to exactly
    // the form's submit button now that the other two carry distinct
    // aria-labels.
    expect(
      screen.getByRole("button", { name: /create|erstellen/i }),
    ).toBe(screen.getByTestId("need-create-submit-btn"));
  });
});
