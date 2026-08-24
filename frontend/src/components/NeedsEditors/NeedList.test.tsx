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
import deLocale from "../../i18n/locales/de.json";

function resolveLocaleKey(key: string): string | undefined {
  const value = key
    .split(".")
    .reduce<unknown>(
      (node, segment) =>
        node && typeof node === "object" ? (node as Record<string, unknown>)[segment] : undefined,
      deLocale
    );
  return typeof value === "string" ? value : undefined;
}

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
