/**
 * Tests for the Goals route (REQ-L2-TE-020).
 *
 * Migrated from GoalsPanel.test.tsx: the flat list + inline form the old
 * panel rendered has been replaced by the split view prescribed in
 * UI_KONZEPT.md ch. 12.6 (tree left, detail right). Every behaviour the
 * panel tests guarded is asserted again here, now through the route:
 * listing, create, status display, approve (incl. the hidden control for an
 * approved goal), edit-as-new-version, and the two error paths.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import GoalsPage from "./GoalsPage";
import * as goalsModule from "../../api/goals";
import * as mainGoalModule from "../../api/main-goal";
import type { Goal } from "../../types";

vi.mock("../../api/goals");
vi.mock("../../api/main-goal");
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "w1", name: "WS", goals_ai_enabled: false },
    workspaces: [],
    isLoadingWorkspace: false,
  }),
}));

const makeGoal = (overrides: Partial<Goal> = {}): Goal => ({
  id: "g1",
  workspace_id: "w1",
  lineage_id: "l1",
  sequence_number: 1,
  title: "Existing Goal",
  description: "",
  status: "Entwurf",
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...overrides,
});

/** Open a goal in the detail pane by clicking its tree node. */
const selectGoal = async (id: string): Promise<void> => {
  fireEvent.click(await screen.findByTestId(`goals-tree-node-${id}`));
};

describe("GoalsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
  });

  it("renders the two tree roots and shows the main goal by default", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([]);

    render(<GoalsPage />);

    expect(await screen.findByTestId("goals-tree-node-__main-goal__")).toBeInTheDocument();
    expect(screen.getByTestId("goals-tree-node-__goals__")).toBeInTheDocument();
    // Detail pane is never empty (ch. 13.5) — the main goal is the anchor.
    expect(await screen.findByTestId("main-goal-panel")).toBeInTheDocument();
  });

  it("lists existing goals and creates a new one", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.create).mockResolvedValue(
      makeGoal({ id: "g2", lineage_id: "l2", title: "New Goal" })
    );

    render(<GoalsPage />);

    expect(await screen.findByText("Existing Goal")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("create-goal-btn"));
    fireEvent.change(screen.getByTestId("goal-title-input"), {
      target: { value: "New Goal" },
    });
    fireEvent.click(screen.getByTestId("goal-create-button"));

    await waitFor(() =>
      expect(goalsModule.goalsApi.create).toHaveBeenCalledWith("w1", {
        title: "New Goal",
        description: "",
      })
    );
  });

  it("displays the workflow status of the selected goal", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      makeGoal({ status: "Freigegeben" }),
    ]);

    render(<GoalsPage />);
    await selectGoal("g1");

    expect(await screen.findByTestId("goal-status")).toHaveTextContent("Freigegeben");
  });

  it("approves a draft goal via the workflow transitions endpoint", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.transition).mockResolvedValue({
      id: "g1",
      previous_state: "Entwurf",
      new_state: "Freigegeben",
    });

    render(<GoalsPage />);
    await selectGoal("g1");

    fireEvent.click(await screen.findByTestId("goal-approve-button"));

    await waitFor(() =>
      expect(goalsModule.goalsApi.transition).toHaveBeenCalledWith(
        "g1",
        "Freigegeben",
        expect.any(String)
      )
    );
  });

  it("hides the approve control for an already approved goal", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      makeGoal({ status: "Freigegeben" }),
    ]);

    render(<GoalsPage />);
    await selectGoal("g1");

    await screen.findByTestId("goal-detail");
    expect(screen.queryByTestId("goal-approve-button")).not.toBeInTheDocument();
  });

  it("edits a goal by creating a new version in the same lineage", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.createVersion).mockResolvedValue(
      makeGoal({ id: "g1-v2", sequence_number: 2, title: "Existing Goal, revised" })
    );

    render(<GoalsPage />);
    await selectGoal("g1");

    fireEvent.click(await screen.findByTestId("goal-edit-button"));
    // The form is pre-filled with the selected goal.
    expect(screen.getByTestId("goal-title-input")).toHaveValue("Existing Goal");

    fireEvent.change(screen.getByTestId("goal-title-input"), {
      target: { value: "Existing Goal, revised" },
    });
    fireEvent.click(screen.getByTestId("goal-create-button"));

    await waitFor(() =>
      expect(goalsModule.goalsApi.createVersion).toHaveBeenCalledWith("l1", {
        workspace_id: "w1",
        title: "Existing Goal, revised",
        description: "",
      })
    );
  });

  it("surfaces a rejected create instead of leaving the promise unhandled", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([]);
    vi.mocked(goalsModule.goalsApi.create).mockRejectedValue(
      new Error("Goals are not enabled for this workspace")
    );

    render(<GoalsPage />);

    fireEvent.click(await screen.findByTestId("create-goal-btn"));
    fireEvent.change(screen.getByTestId("goal-title-input"), { target: { value: "X" } });
    fireEvent.click(screen.getByTestId("goal-create-button"));

    expect(await screen.findByTestId("goals-error")).toHaveTextContent(
      /Goals are not enabled/
    );
    // ch. 12.12: a failed action keeps the form open.
    expect(screen.getByTestId("goal-form")).toBeInTheDocument();
  });

  it("surfaces a rejected approval (role gate)", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.transition).mockRejectedValue(
      new Error("Role not allowed")
    );

    render(<GoalsPage />);
    await selectGoal("g1");

    fireEvent.click(await screen.findByTestId("goal-approve-button"));

    expect(await screen.findByTestId("goals-error")).toHaveTextContent(/Role not allowed/);
  });
});
