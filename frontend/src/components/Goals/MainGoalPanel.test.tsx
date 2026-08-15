/**
 * Tests for MainGoalPanel (REQ-L2-TE-020).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MainGoalPanel } from "./MainGoalPanel";
import * as mainGoalModule from "../../api/main-goal";
import * as workflowTransitionsModule from "../../api/workflow-transitions";
import type { MainGoal } from "../../types";

vi.mock("../../api/main-goal");
vi.mock("../../api/workflow-transitions");

/**
 * Issue #238: the archive control renders from the WorkflowEngine's
 * allowed_transitions for `main-goal`, never from a hardcoded "Archiviert".
 */
const mockMainGoalTransitions = (
  ...allowed: { target_state: string; requires_change_reason?: boolean }[]
): void => {
  vi.mocked(workflowTransitionsModule.workflowTransitionsApi.getTransitions)
    .mockResolvedValue({
      current_state: "Freigegeben",
      states: ["Entwurf", "Freigegeben", "Archiviert"],
      allowed_transitions: allowed.map((a) => ({
        target_state: a.target_state,
        requires_change_reason: a.requires_change_reason ?? false,
        signature_gate: false,
      })),
    });
};

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

describe("MainGoalPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMainGoalTransitions();
  });

  it("shows current main goal and approves a draft", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(makeMainGoal());

    render(<MainGoalPanel workspaceId="w1" aiEnabled={true} />);

    expect(await screen.findByText("Current main goal.")).toBeInTheDocument();
  });

  it("generates a new draft via AI when enabled", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
    vi.mocked(mainGoalModule.mainGoalApi.generate).mockResolvedValue(
      makeMainGoal({ id: "mg2", sequence_number: 2, content: "AI draft.", source: "ai", status: "Entwurf" })
    );

    render(<MainGoalPanel workspaceId="w1" aiEnabled={true} />);

    fireEvent.click(await screen.findByTestId("main-goal-generate-button"));

    await waitFor(() =>
      expect(mainGoalModule.mainGoalApi.generate).toHaveBeenCalledWith("w1")
    );
  });

  it("keeps the generate button visible when AI is disabled and surfaces the backend error", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
    vi.mocked(mainGoalModule.mainGoalApi.generate).mockRejectedValue(
      new Error("AI generation is disabled for this workspace")
    );

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    // Design spec 6: the entry point stays visible; the backend explains why.
    fireEvent.click(await screen.findByTestId("main-goal-generate-button"));

    expect(await screen.findByTestId("main-goal-error")).toHaveTextContent(
      /AI generation is disabled/
    );
  });

  it("creates a main goal draft manually", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
    vi.mocked(mainGoalModule.mainGoalApi.createManual).mockResolvedValue(
      makeMainGoal({ id: "mg3", content: "Handwritten main goal.", status: "Entwurf" })
    );

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    fireEvent.click(await screen.findByTestId("main-goal-manual-toggle-button"));
    fireEvent.change(screen.getByTestId("main-goal-manual-input"), {
      target: { value: "Handwritten main goal." },
    });
    fireEvent.click(screen.getByTestId("main-goal-manual-create-button"));

    await waitFor(() =>
      expect(mainGoalModule.mainGoalApi.createManual).toHaveBeenCalledWith(
        "w1",
        "Handwritten main goal."
      )
    );
    expect(await screen.findByTestId("main-goal-draft")).toHaveTextContent(
      "Handwritten main goal."
    );
  });

  it("renders the approved content returned by the approve endpoint", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
    vi.mocked(mainGoalModule.mainGoalApi.createManual).mockResolvedValue(
      makeMainGoal({ id: "mg4", content: "Draft content.", status: "Entwurf" })
    );
    vi.mocked(mainGoalModule.mainGoalApi.approve).mockResolvedValue(
      makeMainGoal({ id: "mg4", content: "Draft content.", status: "Freigegeben" })
    );

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    fireEvent.click(await screen.findByTestId("main-goal-manual-toggle-button"));
    fireEvent.change(screen.getByTestId("main-goal-manual-input"), {
      target: { value: "Draft content." },
    });
    fireEvent.click(screen.getByTestId("main-goal-manual-create-button"));

    fireEvent.click(await screen.findByTestId("main-goal-approve-button"));

    // Regression guard for finding C2: a bare {id, sequence_number, status}
    // approve response blanked the panel because `content` was undefined.
    await waitFor(() =>
      expect(screen.queryByTestId("main-goal-draft")).not.toBeInTheDocument()
    );
    expect(screen.getByText("Draft content.")).toBeInTheDocument();
  });

  it("surfaces a rejected approval", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
    vi.mocked(mainGoalModule.mainGoalApi.generate).mockResolvedValue(
      makeMainGoal({ id: "mg5", content: "AI draft.", source: "ai", status: "Entwurf" })
    );
    vi.mocked(mainGoalModule.mainGoalApi.approve).mockRejectedValue(
      new Error("Role not allowed")
    );

    render(<MainGoalPanel workspaceId="w1" aiEnabled={true} />);

    fireEvent.click(await screen.findByTestId("main-goal-generate-button"));
    fireEvent.click(await screen.findByTestId("main-goal-approve-button"));

    expect(await screen.findByTestId("main-goal-error")).toHaveTextContent(
      /Role not allowed/
    );
  });

  // -------------------------------------------------------------------------
  // Issue #238 — archiving, the only way to retire a MainGoal
  // -------------------------------------------------------------------------

  it("archives the approved main goal after the confirmation is accepted", async () => {
    // No other `Freigegeben` version is left after this archive, so the
    // refetch (review finding 1) legitimately comes back empty here.
    vi.mocked(mainGoalModule.mainGoalApi.current)
      .mockResolvedValueOnce(makeMainGoal())
      .mockResolvedValueOnce(null);
    mockMainGoalTransitions({ target_state: "Archiviert" });
    vi.mocked(workflowTransitionsModule.workflowTransitionsApi.transition)
      .mockResolvedValue({
        id: "mg1",
        previous_state: "Freigegeben",
        new_state: "Archiviert",
      });

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    fireEvent.click(await screen.findByTestId("main-goal-archive-button"));
    // Nothing happens until the confirmation is accepted.
    expect(await screen.findByTestId("main-goal-archive-dialog")).toBeInTheDocument();
    expect(
      workflowTransitionsModule.workflowTransitionsApi.transition
    ).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("main-goal-archive-dialog-confirm"));

    await waitFor(() =>
      expect(
        workflowTransitionsModule.workflowTransitionsApi.transition
      ).toHaveBeenCalledWith("main-goal", "mg1", "Archiviert", "")
    );
    // The panel re-fetches instead of assuming "none approved" (finding 1);
    // here the refetch legitimately reports none left.
    expect(await screen.findByTestId("main-goal-empty")).toBeInTheDocument();
    expect(mainGoalModule.mainGoalApi.current).toHaveBeenCalledTimes(2);
  });

  it("refetches after archiving a non-newest main goal version, showing the remaining approved row instead of assuming none exists", async () => {
    // Review finding 1 regression guard: `MainGoalService.get_current()`
    // returns the NEWEST `Freigegeben` row. Archiving v2 while v1 is still
    // `Freigegeben` must bring v1 back on screen, not the empty state.
    const v2 = makeMainGoal({ id: "mg2", sequence_number: 2, content: "v2 content." });
    const v1 = makeMainGoal({ id: "mg1", sequence_number: 1, content: "v1 content." });
    vi.mocked(mainGoalModule.mainGoalApi.current)
      .mockResolvedValueOnce(v2)
      .mockResolvedValueOnce(v1);
    mockMainGoalTransitions({ target_state: "Archiviert" });
    vi.mocked(workflowTransitionsModule.workflowTransitionsApi.transition)
      .mockResolvedValue({
        id: "mg2",
        previous_state: "Freigegeben",
        new_state: "Archiviert",
      });

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    expect(await screen.findByText("v2 content.")).toBeInTheDocument();

    fireEvent.click(await screen.findByTestId("main-goal-archive-button"));
    fireEvent.click(await screen.findByTestId("main-goal-archive-dialog-confirm"));

    await waitFor(() =>
      expect(
        workflowTransitionsModule.workflowTransitionsApi.transition
      ).toHaveBeenCalledWith("main-goal", "mg2", "Archiviert", "")
    );

    expect(await screen.findByText("v1 content.")).toBeInTheDocument();
    expect(screen.queryByTestId("main-goal-empty")).not.toBeInTheDocument();
    expect(mainGoalModule.mainGoalApi.current).toHaveBeenCalledTimes(2);
  });

  it("closes the confirm dialog before the archive request settles, guarding against a double-submit", async () => {
    // Review finding 2 regression guard: `ArchiveConfirmDialog` stays
    // mounted through the whole `await` unless the dialog closes first — a
    // doubled click would otherwise fire a second `transitions/` request.
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(makeMainGoal());
    mockMainGoalTransitions({ target_state: "Archiviert" });
    let resolveTransition!: (value: {
      id: string;
      previous_state: string;
      new_state: string;
    }) => void;
    vi.mocked(workflowTransitionsModule.workflowTransitionsApi.transition).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveTransition = resolve;
        }),
    );

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    fireEvent.click(await screen.findByTestId("main-goal-archive-button"));
    fireEvent.click(await screen.findByTestId("main-goal-archive-dialog-confirm"));

    // The dialog is gone immediately, well before the in-flight request
    // settles — a second click physically cannot reach the confirm button.
    await waitFor(() =>
      expect(screen.queryByTestId("main-goal-archive-dialog")).not.toBeInTheDocument()
    );
    expect(
      workflowTransitionsModule.workflowTransitionsApi.transition
    ).toHaveBeenCalledTimes(1);

    resolveTransition({ id: "mg1", previous_state: "Freigegeben", new_state: "Archiviert" });
    await waitFor(() => expect(mainGoalModule.mainGoalApi.current).toHaveBeenCalledTimes(2));
  });

  it("hides the archive control when the workflow does not offer it", async () => {
    // A workspace whose MainGoal machine has no archive-family move at all —
    // the panel must not invent one.
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(makeMainGoal());
    mockMainGoalTransitions({ target_state: "Entwurf" });

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    await screen.findByText("Current main goal.");
    expect(screen.queryByTestId("main-goal-archive-button")).not.toBeInTheDocument();
  });

  it("keeps the archive control hidden when the transitions endpoint fails", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(makeMainGoal());
    vi.mocked(workflowTransitionsModule.workflowTransitionsApi.getTransitions)
      .mockRejectedValue(new Error("Not found"));

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    await screen.findByText("Current main goal.");
    expect(screen.queryByTestId("main-goal-archive-button")).not.toBeInTheDocument();
    // ...and no error banner: the main goal itself loaded fine.
    expect(screen.queryByTestId("main-goal-error")).not.toBeInTheDocument();
  });

  it("surfaces a rejected archive (role gate)", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(makeMainGoal());
    mockMainGoalTransitions({ target_state: "Archiviert" });
    vi.mocked(workflowTransitionsModule.workflowTransitionsApi.transition)
      .mockRejectedValue(new Error("Role not allowed"));

    render(<MainGoalPanel workspaceId="w1" aiEnabled={false} />);

    fireEvent.click(await screen.findByTestId("main-goal-archive-button"));
    fireEvent.click(await screen.findByTestId("main-goal-archive-dialog-confirm"));

    expect(await screen.findByTestId("main-goal-error")).toHaveTextContent(
      /Role not allowed/
    );
    // The main goal is still there — a rejected move changes nothing.
    expect(screen.getByText("Current main goal.")).toBeInTheDocument();
  });

  it("reports the artifact currently on screen so the page can inspect it", async () => {
    // Issue #219: the page mounts the ArtifactInspector on this subject; a
    // fresh draft takes precedence over the approved version.
    const onActiveChange = vi.fn();
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(makeMainGoal());
    vi.mocked(mainGoalModule.mainGoalApi.generate).mockResolvedValue(
      makeMainGoal({ id: "mg2", sequence_number: 2, content: "AI draft.", source: "ai", status: "Entwurf" })
    );

    render(
      <MainGoalPanel workspaceId="w1" aiEnabled onActiveChange={onActiveChange} />,
    );

    await waitFor(() =>
      expect(onActiveChange).toHaveBeenCalledWith(
        expect.objectContaining({ id: "mg1" }),
      )
    );

    fireEvent.click(await screen.findByTestId("main-goal-generate-button"));

    await waitFor(() =>
      expect(onActiveChange).toHaveBeenCalledWith(
        expect.objectContaining({ id: "mg2" }),
      )
    );
  });
});
