/**
 * R2/T1 (systemaudit 2026-09-02): a live audit found that a "viewer" role
 * saw the per-row Delete ("x") trigger in RequirementList — only the server
 * rejected the actual delete. It must be genuinely absent from the DOM for a
 * viewer (spec: "nicht gerendert, nicht nur deaktiviert"), matching Task 4's
 * SidebarNavigation.tsx / RequirementForm.test.tsx's role-gate contract.
 *
 * leaf_id: COMP-RF-003-RequirementList
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { RequirementList } from "./RequirementList";
import * as authModule from "../../context/AuthContext";
import type { Requirement } from "../../types";

vi.mock("../../context/AuthContext");
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-a" } }),
}));
// Avoids a "NO_I18NEXT_INSTANCE" warning: this focused unit test never
// exercises a translated string, so a real i18next instance is unnecessary
// (same stub react-i18next mock as RequirementForm.test.tsx).
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));

function mockRoles(roles: string[]): void {
  vi.mocked(authModule.useAuth).mockReturnValue({
    roles,
  } as unknown as ReturnType<typeof authModule.useAuth>);
}

function makeRequirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: "req-1",
    workspace_id: "ws-1",
    title: "First requirement",
    description: "",
    category: "functional",
    status: "draft",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

const REQUIREMENTS: Requirement[] = [makeRequirement()];

function renderList() {
  return render(
    <RequirementList
      requirements={REQUIREMENTS}
      onSelect={vi.fn()}
      onDelete={vi.fn()}
      onCreateNew={vi.fn()}
    />
  );
}

describe("RequirementList — role-gated Delete trigger (R2/T1)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("does not render the per-row Delete trigger for a viewer", () => {
    mockRoles(["viewer"]);
    renderList();
    expect(
      screen.queryByTestId(`req-row-delete-${REQUIREMENTS[0].id}`)
    ).not.toBeInTheDocument();
  });

  it("renders the per-row Delete trigger for an editor", () => {
    mockRoles(["editor"]);
    renderList();
    expect(
      screen.getByTestId(`req-row-delete-${REQUIREMENTS[0].id}`)
    ).toBeInTheDocument();
  });

  it("renders the per-row Delete trigger for an admin (superset of editor)", () => {
    mockRoles(["admin"]);
    renderList();
    expect(
      screen.getByTestId(`req-row-delete-${REQUIREMENTS[0].id}`)
    ).toBeInTheDocument();
  });
});
