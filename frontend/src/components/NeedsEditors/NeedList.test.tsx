/**
 * BUG-11 (Systemaudit 2026-08-18, §4, Mittel) — the create-need form only had
 * a title input; `description`/`category` are ordinary
 * stakeholderNeedApi.create() fields the backend already accepts (see
 * StakeholderNeed in types/index.ts) but had no editor here, forcing an
 * immediate follow-up edit to fill them in.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { NeedList } from "./NeedList";
import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown, options?: Record<string, string>) => {
      const fallbackStr = typeof fallback === "string" ? fallback : undefined;
      const params = typeof fallback === "object" && fallback !== null ? (fallback as Record<string, string>) : options;
      const resolved = resolveLocaleKey(key) ?? fallbackStr ?? key;
      if (!params) return resolved;
      return Object.entries(params).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
  }),
}));

function renderList(overrides: Partial<Parameters<typeof NeedList>[0]> = {}) {
  const props = {
    needs: [],
    showCreateForm: true,
    setShowCreateForm: vi.fn(),
    newTitle: "",
    setNewTitle: vi.fn(),
    newDescription: "",
    setNewDescription: vi.fn(),
    newCategory: "",
    setNewCategory: vi.fn(),
    onSubmitCreate: vi.fn(),
    createError: null,
    onCreateClick: vi.fn(),
    ...overrides,
  };
  return render(
    <MemoryRouter>
      <NeedList {...props} />
    </MemoryRouter>
  );
}

describe("NeedList — create form has description/category fields (BUG-11)", () => {
  it("renders description and category inputs alongside the title", () => {
    renderList();

    expect(screen.getByTestId("need-new-description-input")).toBeInTheDocument();
    expect(screen.getByTestId("need-new-category-input")).toBeInTheDocument();
  });

  it("forwards typed description/category to the setters", async () => {
    const setNewDescription = vi.fn();
    const setNewCategory = vi.fn();
    const user = userEvent.setup();
    renderList({ setNewDescription, setNewCategory });

    await user.type(screen.getByTestId("need-new-description-input"), "d");
    await user.type(screen.getByTestId("need-new-category-input"), "c");

    expect(setNewDescription).toHaveBeenCalledWith("d");
    expect(setNewCategory).toHaveBeenCalledWith("c");
  });

  it("uses the unified + New Need trigger label instead of bare Erstellen", () => {
    renderList({ needs: [], showCreateForm: false });

    expect(screen.getByTestId("need-list-empty-create")).toHaveTextContent("+ Neuer Bedarf");
    expect(screen.queryByText("Erstellen")).not.toBeInTheDocument();
  });
});

describe("NeedList — title field has an accessible label and a localized placeholder (#805)", () => {
  it("associates the visible label with the title input via htmlFor/id", () => {
    renderList();

    // getByLabelText only succeeds when label and input are programmatically
    // associated (htmlFor === id) — an unassociated <label> next to the
    // input (the pre-fix state) would fail this lookup even though both
    // elements are visually present.
    const titleInput = screen.getByLabelText("Titel");
    expect(titleInput).toBe(screen.getByTestId("need-new-title-input"));
  });

  it("shows a German placeholder instead of the English literal fallback", () => {
    renderList();

    const titleInput = screen.getByTestId("need-new-title-input") as HTMLInputElement;
    expect(titleInput.placeholder).not.toMatch(/as a user, i need/i);
    expect(titleInput.placeholder).toBe("z. B. Als Nutzer benötige ich ...");
  });
});

/**
 * #802 — Need/Glossary used to create via an inline form while the other five
 * entities used the shared <Dialog>. The create flow now renders through that
 * primitive, so it gets a real `role="dialog"`, an overlay, a focus trap and
 * Escape-to-close instead of sharing one DOM scope with the list's own
 * search/status/sort controls.
 */
describe("NeedList — create form uses the shared Dialog (#802)", () => {
  it("mounts the create form in a modal dialog labelled by the create action", () => {
    renderList();

    const dialog = screen.getByTestId("need-new-dialog");
    expect(dialog).toHaveAttribute("role", "dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("Neuer Bedarf");
    // The form itself (and its E2E testids) is unchanged.
    expect(dialog).toContainElement(screen.getByTestId("need-create-form"));
    expect(dialog).toContainElement(screen.getByTestId("need-new-title-input"));
  });

  it("portals the dialog out of the list/toolbar DOM scope", () => {
    const { container } = renderList();

    const overlay = screen.getByTestId("need-new-dialog-overlay");
    expect(overlay.parentElement).toBe(document.body);
    expect(container.contains(overlay)).toBe(false);
  });

  it("closes on Escape — the former inline form could not be dismissed this way", async () => {
    const setShowCreateForm = vi.fn();
    const user = userEvent.setup();
    renderList({ setShowCreateForm });

    await user.keyboard("{Escape}");

    expect(setShowCreateForm).toHaveBeenCalledWith(false);
  });

  it("closes via the cancel button", async () => {
    const setShowCreateForm = vi.fn();
    const user = userEvent.setup();
    renderList({ setShowCreateForm });

    await user.click(screen.getByTestId("need-create-cancel-btn"));

    expect(setShowCreateForm).toHaveBeenCalledWith(false);
  });

  it("moves the initial focus into the title field, not the dialog chrome", () => {
    renderList();

    expect(document.activeElement).toBe(screen.getByTestId("need-new-title-input"));
  });

  it("renders no dialog while the create form is closed", () => {
    renderList({ showCreateForm: false });

    expect(screen.queryByTestId("need-new-dialog")).not.toBeInTheDocument();
  });
});
