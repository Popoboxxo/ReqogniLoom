/**
 * GoalsTree unit tests — Task 4.4 (Virtualisierung überall).
 *
 * `GoalsTree` is a thin WorkspaceTree consumer (search/filter/sort +
 * WorkspaceTreeNode mapping). Virtualization mechanics themselves are
 * covered exhaustively by `workspace-tree.test.tsx`; this test verifies the
 * page-level wiring: `virtualize` is actually passed through, so a large
 * goal list does not mount one DOM row per goal.
 *
 * jsdom does not run layout, so the scroll container's `offsetHeight` is
 * always 0 and @tanstack/react-virtual would compute an empty visible
 * range. We patch `offsetHeight`/`offsetWidth` to a realistic size here —
 * the same technique `workspace-tree.test.tsx` uses for its "real container
 * size" virtualization tests — so the assertions exercise an actual
 * windowed render instead of a vacuous all-zero one.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { GoalsTree, MAIN_GOAL_NODE_ID, GOALS_ROOT_NODE_ID } from "./GoalsTree";
import type { Goal } from "../../types";

function makeGoal(i: number): Goal {
  return {
    id: `g${i}`,
    workspace_id: "w1",
    lineage_id: `l${i}`,
    sequence_number: 1,
    title: `Goal ${i}`,
    description: "",
    status: "Entwurf",
    version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("GoalsTree — virtualization (Task 4.4)", () => {
  let offsetHeightSpy: ReturnType<typeof vi.spyOn>;
  let offsetWidthSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    offsetHeightSpy = vi
      .spyOn(HTMLElement.prototype, "offsetHeight", "get")
      .mockReturnValue(340);
    offsetWidthSpy = vi
      .spyOn(HTMLElement.prototype, "offsetWidth", "get")
      .mockReturnValue(800);
  });

  afterEach(() => {
    offsetHeightSpy.mockRestore();
    offsetWidthSpy.mockRestore();
  });

  it("mounts far fewer DOM rows than goals when the list is large", () => {
    const goals = Array.from({ length: 500 }, (_, i) => makeGoal(i));

    render(
      <GoalsTree goals={goals} selectedId={MAIN_GOAL_NODE_ID} onSelect={vi.fn()} />,
    );

    // 500 goals + 2 static roots = 502 possible rows. The virtualizer must
    // window this down to a small on-screen subset, not mount all of them.
    const rows = screen.queryAllByRole("treeitem");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(goals.length);
  });

  it("does not mount the last goal in the initial window", () => {
    const goals = Array.from({ length: 500 }, (_, i) => makeGoal(i));

    render(
      <GoalsTree goals={goals} selectedId={MAIN_GOAL_NODE_ID} onSelect={vi.fn()} />,
    );

    expect(screen.queryByTestId("goals-tree-node-g499")).not.toBeInTheDocument();
  });

  it("still renders the main-goal root alongside a large goal list", () => {
    const goals = Array.from({ length: 500 }, (_, i) => makeGoal(i));

    render(
      <GoalsTree goals={goals} selectedId={MAIN_GOAL_NODE_ID} onSelect={vi.fn()} />,
    );

    // The static roots sit first in the flattened row list, so they stay
    // inside the virtualizer's initial window.
    expect(
      screen.getByTestId(`goals-tree-node-${MAIN_GOAL_NODE_ID}`),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(`goals-tree-node-${GOALS_ROOT_NODE_ID}`),
    ).toBeInTheDocument();
  });

  it("does not virtualize when the goal list is small", () => {
    const goals = [makeGoal(0), makeGoal(1)];

    render(
      <GoalsTree goals={goals} selectedId={MAIN_GOAL_NODE_ID} onSelect={vi.fn()} />,
    );

    expect(screen.queryByTestId("goals-tree-scroll")).not.toBeInTheDocument();
    // All rows (2 roots + 2 goals) mount directly, no windowing needed.
    expect(screen.getAllByRole("treeitem")).toHaveLength(4);
  });
});
