/**
 * Tests for GoalsPanel (REQ-L2-TE-020).
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { GoalsPanel } from "./GoalsPanel";
import * as goalsModule from "../../api/goals";

vi.mock("../../api/goals");

describe("GoalsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists existing goals and creates a new one", async () => {
    vi.mocked(goalsModule.goalsApi.list).mockResolvedValue([
      {
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
      },
    ]);
    vi.mocked(goalsModule.goalsApi.create).mockResolvedValue({
      id: "g2",
      workspace_id: "w1",
      lineage_id: "l2",
      sequence_number: 1,
      title: "New Goal",
      description: "",
      status: "Entwurf",
      version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

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
});
