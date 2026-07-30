/**
 * Tests for MainGoalPanel (REQ-L2-TE-020).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MainGoalPanel } from "./MainGoalPanel";
import * as mainGoalModule from "../../api/main-goal";

vi.mock("../../api/main-goal");

describe("MainGoalPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows current main goal and approves a draft", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue({
      id: "mg1",
      workspace_id: "w1",
      sequence_number: 1,
      content: "Current main goal.",
      source: "manual",
      status: "Freigegeben",
      version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    render(<MainGoalPanel workspaceId="w1" aiEnabled={true} />);

    expect(await screen.findByText("Current main goal.")).toBeInTheDocument();
  });

  it("generates a new draft via AI when enabled", async () => {
    vi.mocked(mainGoalModule.mainGoalApi.current).mockResolvedValue(null);
    vi.mocked(mainGoalModule.mainGoalApi.generate).mockResolvedValue({
      id: "mg2",
      workspace_id: "w1",
      sequence_number: 2,
      content: "AI draft.",
      source: "ai",
      status: "Entwurf",
      version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    render(<MainGoalPanel workspaceId="w1" aiEnabled={true} />);

    fireEvent.click(await screen.findByTestId("main-goal-generate-button"));

    await waitFor(() =>
      expect(mainGoalModule.mainGoalApi.generate).toHaveBeenCalledWith("w1")
    );
  });
});
