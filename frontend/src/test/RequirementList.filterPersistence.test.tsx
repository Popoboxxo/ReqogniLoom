/**
 * ARCH-L1-001 ReactFrontend — RequirementList filter/sort persistence.
 *
 * leaf_id: COMP-RF-003-RequirementList
 * req_id:  REQ-L3-RF003-005 (RequirementList Component)
 *
 * BUG-19 regression (docs/SYSTEMAUDIT_2026-08-18.md §4): search/filter/sort
 * selections used to live in plain `useState`, which is discarded on
 * unmount — i.e. every time the user navigates away from and back to the
 * requirements list. Verifies that a category filter selection survives an
 * unmount/remount cycle (simulating a route change) via
 * `usePersistedListState` (sessionStorage-backed).
 *
 * Review finding F-02 regression: the persistence key MUST be scoped by the
 * active workspace ID — otherwise switching workspaces carries the PREVIOUS
 * workspace's filter/search/sort selection over onto the newly-active one,
 * making it look filtered/empty for no visible reason (worse than the
 * original BUG-19 symptom). `useWorkspace` is mocked here so a single test
 * can simulate a workspace switch without a full WorkspaceProvider/API
 * bootstrap.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { RequirementList } from "../components/RequirementEditors/RequirementList";
import type { Requirement } from "../types";

// Mutable across a single test via `setMockActiveWorkspaceId` — lets the
// F-02 test simulate switching the active workspace between rerenders.
let mockActiveWorkspaceId = "ws-a";
function setMockActiveWorkspaceId(id: string): void {
  mockActiveWorkspaceId = id;
}

vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: mockActiveWorkspaceId } }),
}));

// R2/T1 (systemaudit 2026-09-02): RequirementList now reads roles via
// useHasRole/useAuth to gate the per-row Delete trigger — this test is about
// filter persistence, not role gating, so it stays on an editor session
// (role gating itself is covered by RequirementList.roleGate.test.tsx).
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ roles: ["editor"] }),
}));

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

const REQUIREMENTS: Requirement[] = [
  makeRequirement({ id: "req-1", title: "Functional one", category: "functional" }),
  makeRequirement({ id: "req-2", title: "Data one", category: "data" }),
];

describe("RequirementList filter persistence (BUG-19)", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    setMockActiveWorkspaceId("ws-a");
  });

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

  it("keeps the category filter selection across an unmount/remount cycle", () => {
    renderList();

    const categorySelect = screen.getByTestId(
      "req-list-filter-category"
    ) as HTMLSelectElement;
    fireEvent.change(categorySelect, { target: { value: "data" } });
    expect(categorySelect.value).toBe("data");

    // Simulate a route change: unmount the view entirely, then come back.
    cleanup();
    renderList();

    const categorySelectAfterRemount = screen.getByTestId(
      "req-list-filter-category"
    ) as HTMLSelectElement;
    expect(categorySelectAfterRemount.value).toBe("data");
  });

  it("keeps the sort selection across an unmount/remount cycle", () => {
    renderList();

    const sortSelect = screen.getByTestId(
      "req-list-sort-select"
    ) as HTMLSelectElement;
    fireEvent.change(sortSelect, { target: { value: "title" } });
    expect(sortSelect.value).toBe("title");

    cleanup();
    renderList();

    const sortSelectAfterRemount = screen.getByTestId(
      "req-list-sort-select"
    ) as HTMLSelectElement;
    expect(sortSelectAfterRemount.value).toBe("title");
  });

  it("does not leak the filter selection to a different workspace (F-02)", () => {
    const { rerender } = renderList();

    const categorySelect = screen.getByTestId(
      "req-list-filter-category"
    ) as HTMLSelectElement;
    fireEvent.change(categorySelect, { target: { value: "data" } });
    expect(categorySelect.value).toBe("data");

    // Switch the active workspace (no unmount — same component instance,
    // just like a real workspace switch via the sidebar) and rerender.
    setMockActiveWorkspaceId("ws-b");
    rerender(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
      />
    );

    // The new workspace must start from the default, not "data" — leaking
    // ws-a's filter here is exactly the F-02 regression.
    const categorySelectOtherWorkspace = screen.getByTestId(
      "req-list-filter-category"
    ) as HTMLSelectElement;
    expect(categorySelectOtherWorkspace.value).toBe("");

    // Switching back to ws-a must restore ITS OWN selection — proving the
    // value is scoped per workspace, not just cleared on every switch.
    setMockActiveWorkspaceId("ws-a");
    rerender(
      <RequirementList
        requirements={REQUIREMENTS}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onCreateNew={vi.fn()}
      />
    );
    const categorySelectBackOnA = screen.getByTestId(
      "req-list-filter-category"
    ) as HTMLSelectElement;
    expect(categorySelectBackOnA.value).toBe("data");
  });
});
