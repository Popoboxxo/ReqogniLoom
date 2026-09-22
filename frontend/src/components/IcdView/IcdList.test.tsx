/**
 * #27 — the ICD list's empty state must not only say *what* an ICD is, it
 * must tell the user *how* to create the first one. The empty branch already
 * rendered <EmptyState> with a create action; this locks in the explicit
 * guidance that was added to `icds.emptyDescription` (resolved against the
 * real German locale, not a mocked string) plus the stable `icds-empty`
 * testId the E2E specs already depend on.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { IcdList } from "./IcdList";
import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: unknown, options?: Record<string, string>) => {
      const fallbackStr = typeof fallback === "string" ? fallback : undefined;
      const params =
        typeof fallback === "object" && fallback !== null
          ? (fallback as Record<string, string>)
          : options;
      const resolved = resolveLocaleKey(key) ?? fallbackStr ?? key;
      if (!params) return resolved;
      return Object.entries(params).reduce(
        (acc, [name, value]) => acc.replace(`{{${name}}}`, String(value)),
        resolved
      );
    },
  }),
}));

function renderList(overrides: Partial<Parameters<typeof IcdList>[0]> = {}) {
  const props = {
    items: [],
    onSelect: vi.fn(),
    onCreateNew: vi.fn(),
    ...overrides,
  };
  return render(
    <MemoryRouter>
      <IcdList {...props} />
    </MemoryRouter>
  );
}

describe("IcdList — empty-state guidance (#27)", () => {
  it("renders the empty state with its stable testId", () => {
    renderList();
    expect(screen.getByTestId("icds-empty")).toBeInTheDocument();
  });

  it("explicitly tells the user to create the first ICD, not just what one is", () => {
    renderList();
    // Resolved from de.json — the guidance sentence must be present.
    expect(screen.getByText(/Erstelle dein erstes ICD/)).toBeInTheDocument();
  });

  it("offers the inline create action, wired to onCreateNew", () => {
    const onCreateNew = vi.fn();
    renderList({ onCreateNew });

    fireEvent.click(screen.getByTestId("icd-list-empty-create"));
    expect(onCreateNew).toHaveBeenCalledTimes(1);
  });
});
