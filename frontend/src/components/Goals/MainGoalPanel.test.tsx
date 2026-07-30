/**
 * Tests for MainGoalPanel (REQ-L2-TE-020).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MainGoalPanel } from "./MainGoalPanel";
import * as mainGoalModule from "../../api/main-goal";
import type { MainGoal } from "../../types";

vi.mock("../../api/main-goal");

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
});
