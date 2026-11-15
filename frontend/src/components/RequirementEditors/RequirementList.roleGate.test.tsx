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
import userEvent from "@testing-library/user-event";
import { RequirementList } from "./RequirementList";
import * as authModule from "../../context/AuthContext";
import type { Requirement } from "../../types";

vi.mock("../../context/AuthContext");
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-a" } }),
  useOptionalWorkspace: () => ({ activeWorkspace: { id: "ws-a" } }),
}));
// P4.4: this focused role-gate spec never exercises locks. Stubbing the batch
// read keeps the async state update out of the network / out of act() noise.
vi.mock("../shared/WorkspaceTree/useWorkspaceLocks", () => ({
  useWorkspaceLocks: () => ({}),
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

function renderList(requirements: Requirement[] = REQUIREMENTS) {
  return render(
    <RequirementList
      requirements={requirements}
      onSelect={vi.fn()}
      onDelete={vi.fn()}
      onCreateNew={vi.fn()}
      allocation="all"
      onAllocationChange={vi.fn()}
      level="all"
      onLevelChange={vi.fn()}
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

/**
 * Final review: the empty-state "New Requirement" action (`onCreateNew`) was
 * the last ungated write trigger left in this component — a viewer on an
 * empty workspace was offered a create action the server rejects.
 */
describe("RequirementList — role-gated create trigger (R2/T1)", () => {
  it("does not render the empty-state create action for a viewer", () => {
    mockRoles(["viewer"]);
    renderList([]);
    expect(screen.queryByTestId("req-list-empty-create")).not.toBeInTheDocument();
  });

  it("renders the empty-state create action for an editor", () => {
    mockRoles(["editor"]);
    renderList([]);
    expect(screen.getByTestId("req-list-empty-create")).toBeInTheDocument();
  });

  it("renders the empty-state create action for an admin", () => {
    mockRoles(["admin"]);
    renderList([]);
    expect(screen.getByTestId("req-list-empty-create")).toBeInTheDocument();
  });
});

/**
 * G2 (spec 2026-11-08 §4.5.3/§4.5.5, plan 2026-11-15 G2.1): the row action
 * "Zu Gruppe hinzufügen…" is a write path, so it follows the same gate as the
 * delete trigger — absent for a viewer, not merely disabled. It announces the
 * dialog it opens, and it hands the row's requirement id to the container
 * (which owns the dialog, outside this panel's clipped column).
 */
describe("RequirementList — row action 'add to group' (G2)", () => {
  function renderWithGroupAction(onAddToGroup = vi.fn()) {
    return render(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
        onAddToGroup={onAddToGroup}
        allocation="all"
        onAllocationChange={vi.fn()}
        level="all"
        onLevelChange={vi.fn()}
      />
    );
  }

  it("does not render the row action for a viewer", () => {
    mockRoles(["viewer"]);
    renderWithGroupAction();
    expect(
      screen.queryByTestId(`req-row-group-${REQUIREMENTS[0].id}`)
    ).not.toBeInTheDocument();
  });

  it("opens the group dialog for an editor", async () => {
    const user = userEvent.setup();
    const onAddToGroup = vi.fn();
    mockRoles(["editor"]);
    renderWithGroupAction(onAddToGroup);

    const trigger = screen.getByTestId(`req-row-group-${REQUIREMENTS[0].id}`);
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");

    await user.click(trigger);

    expect(onAddToGroup).toHaveBeenCalledWith(REQUIREMENTS[0].id);
    // The click must not also select the row (the <li> owns onSelect).
    expect(screen.getByTestId(`req-row-${REQUIREMENTS[0].id}`)).toBeInTheDocument();
  });

  it("renders no row action when the container provides none", () => {
    mockRoles(["editor"]);
    renderList();
    expect(
      screen.queryByTestId(`req-row-group-${REQUIREMENTS[0].id}`)
    ).not.toBeInTheDocument();
  });
});
