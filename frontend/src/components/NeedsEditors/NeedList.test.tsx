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

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
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
});
