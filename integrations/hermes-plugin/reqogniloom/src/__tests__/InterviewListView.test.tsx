import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterviewListView } from "../InterviewListView";
import type { AppState } from "../state";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return { ...actual, startNewInterview: vi.fn(), resumeInterview: vi.fn() };
});
import { resumeInterview, startNewInterview } from "../state";

function makeState(overrides: Partial<AppState> = {}): AppState {
  return {
    view: "interviews", connection: { baseUrl: "https://x", apiKey: "k", workspaceId: "ws-1" },
    workspaceName: "WS", pendingCredentials: null, pendingWorkspaces: [],
    connectError: null, connecting: false, activeInterview: null,
    interviewList: [], interviewError: null, interviewBusy: false,
    ...overrides,
  };
}

describe("InterviewListView", () => {
  it("renders existing sessions and calls resumeInterview on click", () => {
    const state = makeState({
      interviewList: [{ id: "s-1", workspace_id: "ws-1", artifact_type: "Requirement", status: "in_progress" }],
    });

    render(<InterviewListView state={state} />);
    fireEvent.click(screen.getByText(/Requirement.*in_progress/));

    expect(resumeInterview).toHaveBeenCalledWith("s-1");
  });

  it("renders a start button per in-scope artifact type and calls startNewInterview", () => {
    render(<InterviewListView state={makeState()} />);

    fireEvent.click(screen.getByTestId("interview-start-Risk"));

    expect(startNewInterview).toHaveBeenCalledWith("Risk");
  });

  it("does not offer MainGoal", () => {
    render(<InterviewListView state={makeState()} />);

    expect(screen.queryByTestId("interview-start-MainGoal")).not.toBeInTheDocument();
  });

  it("shows interviewError when present", () => {
    render(<InterviewListView state={makeState({ interviewError: "boom" })} />);

    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
