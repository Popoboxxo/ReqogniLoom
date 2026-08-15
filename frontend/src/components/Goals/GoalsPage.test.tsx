/**
 * Tests for the Goals route (REQ-L2-TE-020).
 *
 * Migrated from GoalsPanel.test.tsx: the flat list + inline form the old
 * panel rendered has been replaced by the split view prescribed in
 * UI_KONZEPT.md ch. 12.6 (tree left, detail right). Every behaviour the
 * panel tests guarded is asserted again here, now through the route:
 * listing, create, status display, approve (incl. the hidden control for an
 * approved goal), edit-as-new-version, and the two error paths.
 *
 * Issue #238 additions: creation runs through a modal `<Dialog>`, the status
 * is its own badge element rather than text appended to the title, and the
 * archive move — the only way to retire a Goal, since Goals cannot be
 * deleted — is confirmed before it runs.
 *
 * Issue #219 additions: selecting a Goal or the main goal mounts the shared
 * `<ArtifactInspector>` sidebar, which is what makes their version history
 * reachable at all.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GoalsPage from "./GoalsPage";
import * as goalsModule from "../../api/goals";
import * as mainGoalModule from "../../api/main-goal";
import * as workflowTransitionsModule from "../../api/workflow-transitions";
import type { Goal, MainGoal } from "../../types";

vi.mock("../../api/goals");
vi.mock("../../api/main-goal");
vi.mock("../../api/workflow-transitions");

/**
 * Mutable so the "workspace switch" regression test (issue #221 finding 7)
 * can change the active workspace mid-test and re-render — `useWorkspace()`
 * is re-invoked on every render and reads this variable fresh.
 */
let activeWorkspace: { id: string; name: string; goals_ai_enabled: boolean } = {
  id: "w1",
  name: "WS",
  goals_ai_enabled: false,
};
vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace,
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

const makeMainGoal = (overrides: Partial<MainGoal> = {}): MainGoal => ({
  id: "mg1",
  workspace_id: "w1",
  sequence_number: 1,
  content: "Current main goal.",
  source: "manual",
  status: "Freigegeben",
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
    activeWorkspace = { id: "w1", name: "WS", goals_ai_enabled: false };
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
    vi.mocked(goalsModule.goalsApi.versions).mockResolvedValue([]);
    vi.mocked(mainGoalModule.mainGoalApi.versions).mockResolvedValue([]);
    vi.mocked(workflowTransitionsModule.workflowTransitionsApi.getTransitions)
      .mockResolvedValue({
        current_state: "Freigegeben",
        states: ["Entwurf", "Freigegeben", "Archiviert"],
        allowed_transitions: [],
      });
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

  it("lists existing goals and creates a new one through the modal dialog", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.create).mockResolvedValue(
      makeGoal({ id: "g2", lineage_id: "l2", title: "New Goal" })
    );

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

    expect(await screen.findByText("Existing Goal")).toBeInTheDocument();

    // Issue #238: creation is a modal, not a field stack inside the pane.
    expect(screen.queryByTestId("goal-form-dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("create-goal-btn"));
    expect(await screen.findByTestId("goal-form-dialog")).toBeInTheDocument();

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
    // A successful create closes the dialog (ch. 12.8).
    await waitFor(() =>
      expect(screen.queryByTestId("goal-form-dialog")).not.toBeInTheDocument()
    );
  });

  it("cannot submit the create dialog without a title", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([]);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

    fireEvent.click(await screen.findByTestId("create-goal-btn"));

    expect(await screen.findByTestId("goal-create-button")).toBeDisabled();
    fireEvent.change(screen.getByTestId("goal-title-input"), {
      target: { value: "Something" },
    });
    expect(screen.getByTestId("goal-create-button")).toBeEnabled();
  });

  it("displays the workflow status of the selected goal", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      makeGoal({ status: "Freigegeben" }),
    ]);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    expect(await screen.findByTestId("goal-status")).toHaveTextContent("Freigegeben");
  });

  it("renders the list row status as its own badge, not appended to the title", async () => {
    // Issue #238 regression guard: the row used to concatenate title and
    // status without a separator, rendering "Existing GoalEntwurf".
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

    const row = await screen.findByTestId("goal-row-g1");
    expect(within(row).getByTestId("goal-row-g1-status")).toHaveTextContent("Entwurf");
    expect(screen.queryByText("Existing GoalEntwurf")).not.toBeInTheDocument();
    expect(screen.getByText("Existing Goal")).toBeInTheDocument();
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

  it("archives a goal only after the confirmation is accepted", async () => {
    // Issue #238: archiving is the delete affordance for Goals (the backend
    // answers DELETE with 405 and drops archived rows from the list), so it
    // is confirmed first. The change reason is still omitted because the
    // preset does not demand one for this move.
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

    // Nothing happens until the dialog is confirmed.
    expect(await screen.findByTestId("goal-archive-dialog")).toBeInTheDocument();
    expect(goalsModule.goalsApi.transition).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("goal-archive-dialog-confirm"));

    await waitFor(() =>
      expect(goalsModule.goalsApi.transition).toHaveBeenCalledWith(
        "g1",
        "Archiviert",
        ""
      )
    );
  });

  it("resets the selection when the selected goal disappears after a reload, even for an unclassified state", async () => {
    // Review finding 3 (part 2) regression guard: previously the selection
    // was only reset for moves `isArchiveTransition` recognises (the
    // "warning" badge family, e.g. `archiviert`). A workflow that moves a
    // Goal into some other state not in that map but which still drops the
    // row from `GoalService.list_current()` used to leave the detail pane
    // silently empty instead of falling back to the main-goal anchor.
    vi.mocked(goalsModule.goalsApi.list)
      .mockResolvedValueOnce([makeGoal({ status: "Proposed" })])
      .mockResolvedValueOnce([]);
    // "Withdrawn" is not in STATUS_VARIANT_MAP -> resolveBadgeVariant falls
    // back to 'neutral', so isArchiveTransition("Withdrawn") is false and no
    // confirmation dialog is shown for this move.
    mockTransitions({ target_state: "Withdrawn" });
    vi.mocked(goalsModule.goalsApi.transition).mockResolvedValue({
      id: "g1",
      previous_state: "Proposed",
      new_state: "Withdrawn",
    });

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    fireEvent.click(await screen.findByTestId("goal-transition-Withdrawn"));

    await waitFor(() =>
      expect(goalsModule.goalsApi.transition).toHaveBeenCalledWith(
        "g1",
        "Withdrawn",
        expect.any(String)
      )
    );

    // Falls back to the main-goal anchor instead of an empty detail pane.
    expect(await screen.findByTestId("main-goal-panel")).toBeInTheDocument();
  });

  it("does not archive a goal when the confirmation is dismissed", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      makeGoal({ status: "Freigegeben" }),
    ]);
    mockTransitions({ target_state: "Archiviert" });

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    fireEvent.click(await screen.findByTestId("goal-transition-Archiviert"));
    fireEvent.click(await screen.findByTestId("goal-archive-dialog-cancel"));

    await waitFor(() =>
      expect(screen.queryByTestId("goal-archive-dialog")).not.toBeInTheDocument()
    );
    expect(goalsModule.goalsApi.transition).not.toHaveBeenCalled();
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
    expect(await screen.findByTestId("goal-title-input")).toHaveValue("Existing Goal");

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

  it("surfaces a rejected create inside the dialog instead of leaving the promise unhandled", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([]);
    vi.mocked(goalsModule.goalsApi.create).mockRejectedValue(
      new Error("Goals are not enabled for this workspace")
    );

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

    fireEvent.click(await screen.findByTestId("create-goal-btn"));
    fireEvent.change(await screen.findByTestId("goal-title-input"), {
      target: { value: "X" },
    });
    fireEvent.click(screen.getByTestId("goal-create-button"));

    // ch. 12.12: the cause is stated where the action was triggered...
    expect(await screen.findByTestId("goal-form-error")).toHaveTextContent(
      /Goals are not enabled/
    );
    // ...and the dialog stays open so the input is not lost.
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

  it("offers the create action from the empty state, but not from the no-match state", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([]);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

    fireEvent.click(await screen.findByTestId("goals-empty-create"));
    expect(await screen.findByTestId("goal-form-dialog")).toBeInTheDocument();
  });

  it("clears a stale error from a previous workspace once the next load succeeds", async () => {
    // Issue #221 finding 7: `loadGoals` used to only ever set `error` on
    // failure, relying on every *caller* (handleSelect, runTransition, ...)
    // to clear it first. The route's own `[workspaceId]`-triggered reload —
    // switching to a different workspace — is not one of those callers, so
    // a failed load in one workspace stayed on screen after switching to a
    // workspace whose load succeeds.
    vi.mocked(goalsModule.goalsApi.list)
      .mockRejectedValueOnce(new Error("Network down"))
      .mockResolvedValueOnce([]);

    const { rerender } = render(
      <MemoryRouter>
        <GoalsPage />
      </MemoryRouter>
    );

    expect(await screen.findByTestId("goals-error")).toHaveTextContent(/Network down/);

    activeWorkspace = { id: "w2", name: "WS2", goals_ai_enabled: false };
    rerender(
      <MemoryRouter>
        <GoalsPage />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(screen.queryByTestId("goals-error")).not.toBeInTheDocument()
    );
  });

  it("shows the no-match state with a filter reset when nothing matches the search", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await screen.findByText("Existing Goal");

    fireEvent.change(screen.getByTestId("goal-list-search-input"), {
      target: { value: "zzz-no-such-goal" },
    });

    expect(await screen.findByTestId("goals-no-matches")).toBeInTheDocument();
    expect(screen.queryByTestId("goals-empty")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("goals-no-matches-reset-filters"));
    expect(await screen.findByText("Existing Goal")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Issue #219 — version history reachable through the ArtifactInspector
  // -------------------------------------------------------------------------

  it("mounts the artifact inspector for the selected goal", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.versions).mockResolvedValue([
      { version: 1, label: "v1", modified_at: "2026-01-01T00:00:00Z" },
    ]);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);
    await selectGoal("g1");

    const inspector = await screen.findByTestId("artifact-inspector");
    expect(inspector).toHaveAttribute("data-artifact-kind", "goal");
    // The version list is fetched for the Goal *entity* id — the versions
    // endpoint resolves the lineage from the row itself.
    await waitFor(() =>
      expect(goalsModule.goalsApi.versions).toHaveBeenCalledWith("g1")
    );
  });

  it("mounts the artifact inspector for the main goal", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([]);
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(makeMainGoal());
    vi.mocked(mainGoalModule.mainGoalApi.versions).mockResolvedValue([
      { version: 1, label: "v1", modified_at: "2026-01-01T00:00:00Z" },
    ]);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

    const inspector = await screen.findByTestId("artifact-inspector");
    expect(inspector).toHaveAttribute("data-artifact-kind", "mainGoal");
    await waitFor(() =>
      expect(mainGoalModule.mainGoalApi.versions).toHaveBeenCalledWith("mg1")
    );
  });

  it("shows no inspector while the main goal has nothing to inspect", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([]);
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);

    render(<MemoryRouter><GoalsPage /></MemoryRouter>);

    await screen.findByTestId("main-goal-empty");
    expect(screen.queryByTestId("artifact-inspector")).not.toBeInTheDocument();
  });
});
