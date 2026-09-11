import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowStatusEditor } from "./WorkflowStatusEditor";
import { workflowTransitionsApi } from "../../api/workflow-transitions";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts?.agent ? `${key}:${String(opts.agent)}` : key,
  }),
}));

describe("WorkflowStatusEditor proposal hint", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the proposing agent when the item is proposed", async () => {
    vi.spyOn(workflowTransitionsApi, "getTransitions").mockResolvedValue({
      current_state: "proposed",
      states: ["draft", "proposed"],
      allowed_transitions: [
        { target_state: "draft", requires_change_reason: false, signature_gate: false },
      ],
      proposed_by: "Claude Code",
    });

    render(<WorkflowStatusEditor artifactType="requirement" artifactId="a1" />);

    await waitFor(() =>
      expect(screen.getByTestId("workflow-proposal-hint")).toHaveTextContent(
        "workflow.proposal.hint:Claude Code",
      ),
    );
  });

  it("falls back to a generic hint without an agent label", async () => {
    vi.spyOn(workflowTransitionsApi, "getTransitions").mockResolvedValue({
      current_state: "proposed",
      states: ["draft", "proposed"],
      allowed_transitions: [],
      proposed_by: null,
    });

    render(<WorkflowStatusEditor artifactType="requirement" artifactId="a2" />);

    await waitFor(() =>
      expect(screen.getByTestId("workflow-proposal-hint")).toHaveTextContent(
        "workflow.proposal.hintUnknown",
      ),
    );
  });

  it("renders no hint for a normal state", async () => {
    vi.spyOn(workflowTransitionsApi, "getTransitions").mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved"],
      allowed_transitions: [],
      proposed_by: null,
    });

    render(<WorkflowStatusEditor artifactType="requirement" artifactId="a3" />);

    await waitFor(() =>
      expect(screen.queryByTestId("workflow-proposal-hint")).toBeNull(),
    );
  });
});
