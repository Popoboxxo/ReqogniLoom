import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterviewListView } from "../InterviewListView";
import { makeAppState } from "./testHelpers";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return { ...actual, startNewInterview: vi.fn(), resumeInterview: vi.fn(), closeInterview: vi.fn() };
});
import { closeInterview, resumeInterview, startNewInterview } from "../state";

describe("InterviewListView", () => {
  it("renders existing sessions and calls resumeInterview on click", () => {
    const state = makeAppState({
      interviewList: [{ id: "s-1", workspace_id: "ws-1", artifact_type: "Requirement", status: "in_progress" }],
    });

    render(<InterviewListView state={state} />);
    fireEvent.click(screen.getByText(/Requirement.*in_progress/));

    expect(resumeInterview).toHaveBeenCalledWith("s-1");
  });

  it("renders a start button per in-scope artifact type and calls startNewInterview with it", () => {
    render(<InterviewListView state={makeAppState()} />);

    fireEvent.click(screen.getByTestId("interview-start-Requirement"));

    expect(startNewInterview).toHaveBeenCalledWith("Requirement");
  });

  it("does not offer MainGoal", () => {
    render(<InterviewListView state={makeAppState()} />);

    expect(screen.queryByTestId("interview-start-MainGoal")).not.toBeInTheDocument();
  });

  it("renders an enabled start button for every in-scope artifact type", () => {
    render(<InterviewListView state={makeAppState()} />);

    for (const type of ["Requirement", "ArchitectureElement", "StakeholderNeed", "Risk", "TestCase", "Adr", "Issue", "Goal"]) {
      expect(screen.getByTestId(`interview-start-${type}`)).not.toBeDisabled();
    }
  });

  it.each(["Requirement", "ArchitectureElement", "StakeholderNeed", "Risk", "TestCase", "Adr", "Issue", "Goal"])(
    "starts a %s interview on click",
    (type) => {
      render(<InterviewListView state={makeAppState()} />);

      fireEvent.click(screen.getByTestId(`interview-start-${type}`));

      expect(startNewInterview).toHaveBeenCalledWith(type);
    }
  );

  it("disables every start button while an interview call is in flight", () => {
    render(<InterviewListView state={makeAppState({ interviewBusy: true })} />);

    expect(screen.getByTestId("interview-start-Requirement")).toBeDisabled();
    expect(screen.getByTestId("interview-start-Risk")).toBeDisabled();
  });

  it("renders a Multi-artifact label instead of a raw null for a session without an artifact_type", () => {
    const state = makeAppState({
      interviewList: [{ id: "s-1", workspace_id: "ws-1", artifact_type: null, status: "in_progress" }],
    });

    render(<InterviewListView state={state} />);

    expect(screen.getByText("Multi-artifact — in_progress")).toBeInTheDocument();
    expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  });

  it("shows interviewError when present", () => {
    render(<InterviewListView state={makeAppState({ interviewError: "boom" })} />);

    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders a Back button that calls closeInterview", () => {
    render(<InterviewListView state={makeAppState()} />);

    fireEvent.click(screen.getByTestId("interview-list-back-button"));

    expect(closeInterview).toHaveBeenCalled();
  });
});
