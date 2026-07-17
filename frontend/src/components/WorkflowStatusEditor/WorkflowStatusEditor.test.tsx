import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

/**
 * REQ-161: WorkflowStatusEditor unit tests.
 *
 * Covers the unified lifecycle control: badge rendering, transition menu,
 * immediate transition, mandatory change-reason flow, the "not initialized"
 * read-only state, and error handling.
 */

vi.mock("../../api/workflow-transitions", () => ({
  workflowTransitionsApi: {
    getTransitions: vi.fn(),
    transition: vi.fn(),
  },
}));

vi.mock("../../api/client", () => ({
  extractErrorMessage: (e: unknown) => (e as Error).message ?? "error",
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k: string, d?: string | Record<string, unknown>) =>
      typeof d === "string"
        ? d
        : typeof d === "object" && d && "defaultValue" in d
          ? String((d as { defaultValue: unknown }).defaultValue)
          : k,
  }),
}));

import { WorkflowStatusEditor } from "./WorkflowStatusEditor";
import { workflowTransitionsApi } from "../../api/workflow-transitions";

const getTransitions = workflowTransitionsApi.getTransitions as ReturnType<
  typeof vi.fn
>;
const transition = workflowTransitionsApi.transition as ReturnType<typeof vi.fn>;

const renderEditor = (props?: Partial<Parameters<typeof WorkflowStatusEditor>[0]>) =>
  render(
    <WorkflowStatusEditor
      artifactType="requirement"
      artifactId="req-1"
      currentStatus="draft"
      {...props}
    />
  );

describe("WorkflowStatusEditor (REQ-161)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the current state badge and allowed transitions", async () => {
    getTransitions.mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved", "deprecated"],
      allowed_transitions: [
        { target_state: "approved", requires_change_reason: false, signature_gate: false },
      ],
    });

    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("workflow-current-status")).toHaveTextContent("draft")
    );
    fireEvent.click(screen.getByTestId("workflow-transition-trigger"));
    expect(
      screen.getByTestId("workflow-transition-option-approved")
    ).toBeInTheDocument();
  });

  it("performs a transition without a reason and reports the new status", async () => {
    getTransitions.mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved"],
      allowed_transitions: [
        { target_state: "approved", requires_change_reason: false, signature_gate: false },
      ],
    });
    transition.mockResolvedValue({
      id: "req-1",
      previous_state: "draft",
      new_state: "approved",
    });
    const onComplete = vi.fn();

    renderEditor({ onTransitionComplete: onComplete });
    await waitFor(() =>
      expect(screen.getByTestId("workflow-transition-trigger")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("workflow-transition-trigger"));
    fireEvent.click(screen.getByTestId("workflow-transition-option-approved"));

    await waitFor(() =>
      expect(transition).toHaveBeenCalledWith("requirement", "req-1", "approved", "")
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledWith("approved"));
  });

  it("prompts for a mandatory change reason before transitioning", async () => {
    getTransitions.mockResolvedValue({
      current_state: "draft",
      states: ["draft", "in_review"],
      allowed_transitions: [
        { target_state: "in_review", requires_change_reason: true, signature_gate: false },
      ],
    });
    transition.mockResolvedValue({
      id: "req-1",
      previous_state: "draft",
      new_state: "in_review",
    });

    renderEditor();
    await waitFor(() =>
      expect(screen.getByTestId("workflow-transition-trigger")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("workflow-transition-trigger"));
    fireEvent.click(screen.getByTestId("workflow-transition-option-in_review"));

    // No POST yet — the reason prompt must appear first.
    expect(transition).not.toHaveBeenCalled();
    const input = await screen.findByTestId("workflow-reason-input");
    fireEvent.change(input, { target: { value: "ready for review" } });
    fireEvent.click(screen.getByTestId("workflow-reason-confirm"));

    await waitFor(() =>
      expect(transition).toHaveBeenCalledWith(
        "requirement",
        "req-1",
        "in_review",
        "ready for review"
      )
    );
  });

  it("shows a read-only 'not initialized' hint when no workflow exists", async () => {
    getTransitions.mockResolvedValue({
      current_state: null,
      states: [],
      allowed_transitions: [],
    });

    renderEditor();

    await waitFor(() =>
      expect(screen.getByTestId("workflow-not-initialized")).toBeInTheDocument()
    );
    expect(
      screen.queryByTestId("workflow-transition-trigger")
    ).not.toBeInTheDocument();
  });

  it("surfaces an error when the transition fails", async () => {
    getTransitions.mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved"],
      allowed_transitions: [
        { target_state: "approved", requires_change_reason: false, signature_gate: false },
      ],
    });
    transition.mockRejectedValue(new Error("Role not allowed"));

    renderEditor();
    await waitFor(() =>
      expect(screen.getByTestId("workflow-transition-trigger")).toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("workflow-transition-trigger"));
    fireEvent.click(screen.getByTestId("workflow-transition-option-approved"));

    await waitFor(() =>
      expect(screen.getByTestId("workflow-error")).toHaveTextContent("Role not allowed")
    );
  });

  it("renders read-only when disabled", async () => {
    getTransitions.mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved"],
      allowed_transitions: [
        { target_state: "approved", requires_change_reason: false, signature_gate: false },
      ],
    });

    renderEditor({ disabled: true });
    await waitFor(() =>
      expect(screen.getByTestId("workflow-current-status")).toHaveTextContent("draft")
    );
    expect(
      screen.queryByTestId("workflow-transition-trigger")
    ).not.toBeInTheDocument();
  });
});
