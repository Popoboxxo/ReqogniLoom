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
import { MemoryRouter } from "react-router-dom";
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

/**
 * Issue #220: the lifecycle buttons render from the WorkflowEngine's
 * allowed_transitions, so every test that touches them has to state what the
 * server would allow. `requiresReason` mirrors the `goal_default` preset,
 * where only `Entwurf -> Freigegeben` demands a change reason.
 */
const mockTransitions = (
  ...allowed: { target_state: string; requires_change_reason?: boolean }[]
): void => {
  vi.mocked(goalsModule.goalsApi.getTransitions).mockResolvedValue({
    current_state: "Entwurf",
    states: ["Entwurf", "Freigegeben", "Archiviert"],
    allowed_transitions: allowed.map((a) => ({
      target_state: a.target_state,
      requires_change_reason: a.requires_change_reason ?? false,
      signature_gate: false,
    })),
  });
};

describe("GoalsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
    mockTransitions();
  });

  it("renders the two tree roots and shows the main goal by default", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([]);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

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

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

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

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    expect(await screen.findByTestId("goal-status")).toHaveTextContent("Freigegeben");
  });

  it("approves a draft goal via the workflow transitions endpoint", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    mockTransitions({ target_state: "Freigegeben", requires_change_reason: true });
    vi.mocked(goalsModule.goalsApi.transition).mockResolvedValue({
      id: "g1",
      previous_state: "Entwurf",
      new_state: "Freigegeben",
    });

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    fireEvent.click(await screen.findByTestId("goal-transition-Freigegeben"));

    await waitFor(() =>
      expect(goalsModule.goalsApi.transition).toHaveBeenCalledWith(
        "g1",
        "Freigegeben",
        expect.any(String)
      )
    );
    // The preset requires a non-empty reason for this move.
    expect(
      vi.mocked(goalsModule.goalsApi.transition).mock.calls[0][2]
    ).toBeTruthy();
  });

  it("hides the approve control when the workflow does not allow it", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      makeGoal({ status: "Freigegeben" }),
    ]);
    // From "Freigegeben" the goal_default preset offers archive / rework,
    // never another approval.
    mockTransitions(
      { target_state: "Archiviert" },
      { target_state: "Entwurf" }
    );

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    await screen.findByTestId("goal-detail");
    expect(
      screen.queryByTestId("goal-transition-Freigegeben")
    ).not.toBeInTheDocument();
    expect(
      await screen.findByTestId("goal-transition-Archiviert")
    ).toBeInTheDocument();
  });

  it("renders lifecycle buttons from allowed_transitions, not from the status name", async () => {
    // A workspace with a customised Goal state machine (ADR-06): neither the
    // state names nor the moves match the stock German preset. The button
    // must still appear, labelled with the server's target state.
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      makeGoal({ status: "Proposed" }),
    ]);
    mockTransitions({ target_state: "Ratified", requires_change_reason: true });
    vi.mocked(goalsModule.goalsApi.transition).mockResolvedValue({
      id: "g1",
      previous_state: "Proposed",
      new_state: "Ratified",
    });

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    const button = await screen.findByTestId("goal-transition-Ratified");
    expect(button).toHaveTextContent("Ratified");

    fireEvent.click(button);
    await waitFor(() =>
      expect(goalsModule.goalsApi.transition).toHaveBeenCalledWith(
        "g1",
        "Ratified",
        expect.any(String)
      )
    );
  });

  it("omits the change reason for a transition that does not require one", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      makeGoal({ status: "Freigegeben" }),
    ]);
    mockTransitions({ target_state: "Archiviert", requires_change_reason: false });
    vi.mocked(goalsModule.goalsApi.transition).mockResolvedValue({
      id: "g1",
      previous_state: "Freigegeben",
      new_state: "Archiviert",
    });

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    fireEvent.click(await screen.findByTestId("goal-transition-Archiviert"));

    await waitFor(() =>
      expect(goalsModule.goalsApi.transition).toHaveBeenCalledWith(
        "g1",
        "Archiviert",
        ""
      )
    );
  });

  it("renders no lifecycle button when the transitions endpoint fails", async () => {
    // 404 = no workflow configured for this workspace/type. The detail pane
    // degrades to read-only instead of showing a control that cannot work.
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.getTransitions).mockRejectedValue(
      new Error("Not found")
    );

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    await screen.findByTestId("goal-detail");
    expect(
      screen.queryByTestId("goal-transition-Freigegeben")
    ).not.toBeInTheDocument();
    // ...and no error banner: the goal itself loaded fine.
    expect(screen.queryByTestId("goals-error")).not.toBeInTheDocument();
  });

  it("edits a goal by creating a new version in the same lineage", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.createVersion).mockResolvedValue(
      makeGoal({ id: "g1-v2", sequence_number: 2, title: "Existing Goal, revised" })
    );

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
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

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

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
    mockTransitions({ target_state: "Freigegeben", requires_change_reason: true });
    vi.mocked(goalsModule.goalsApi.transition).mockRejectedValue(
      new Error("Role not allowed")
    );

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    fireEvent.click(await screen.findByTestId("goal-transition-Freigegeben"));

    expect(await screen.findByTestId("goals-error")).toHaveTextContent(/Role not allowed/);
  });
});
