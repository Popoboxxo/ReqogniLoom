/**
 * Tests for GoalsPanel (REQ-L2-TE-020).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { GoalsPanel } from "./GoalsPanel";
import * as goalsModule from "../../api/goals";
import type { Goal } from "../../types";

vi.mock("../../api/goals");

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

describe("GoalsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists existing goals and creates a new one", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.create).mockResolvedValue(
      makeGoal({ id: "g2", lineage_id: "l2", title: "New Goal" })
    );

    render(<GoalsPanel workspaceId="w1" />);

    expect(await screen.findByText("Existing Goal")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("goal-title-input"), { target: { value: "New Goal" } });
    fireEvent.click(screen.getByTestId("goal-create-button"));

    await waitFor(() =>
      expect(goalsModule.goalsApi.create).toHaveBeenCalledWith("w1", {
        title: "New Goal",
        description: "",
      })
    );
  });

  it("displays the workflow status of each goal", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      makeGoal({ status: "Freigegeben" }),
    ]);

    render(<GoalsPanel workspaceId="w1" />);

    expect(await screen.findByTestId("goal-status")).toHaveTextContent("Freigegeben");
  });

  it("approves a draft goal via the workflow transitions endpoint", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.transition).mockResolvedValue({
      id: "g1",
      previous_state: "Entwurf",
      new_state: "Freigegeben",
    });

    render(<GoalsPanel workspaceId="w1" />);

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

    render(<GoalsPanel workspaceId="w1" />);

    await screen.findByTestId("goal-list-item");
    expect(screen.queryByTestId("goal-approve-button")).not.toBeInTheDocument();
  });

  it("edits a goal by creating a new version in the same lineage", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.createVersion).mockResolvedValue(
      makeGoal({ id: "g1-v2", sequence_number: 2, title: "Existing Goal, revised" })
    );

    render(<GoalsPanel workspaceId="w1" />);

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

    render(<GoalsPanel workspaceId="w1" />);

    fireEvent.change(screen.getByTestId("goal-title-input"), { target: { value: "X" } });
    fireEvent.click(screen.getByTestId("goal-create-button"));

    expect(await screen.findByTestId("goals-error")).toHaveTextContent(
      /Goals are not enabled/
    );
  });

  it("surfaces a rejected approval (role gate)", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([makeGoal()]);
    vi.mocked(goalsModule.goalsApi.transition).mockRejectedValue(
      new Error("Role not allowed")
    );

    render(<GoalsPanel workspaceId="w1" />);

    fireEvent.click(await screen.findByTestId("goal-approve-button"));

    expect(await screen.findByTestId("goals-error")).toHaveTextContent(/Role not allowed/);
  });
});
