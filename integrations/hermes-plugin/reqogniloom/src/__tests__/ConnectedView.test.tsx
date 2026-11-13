import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ConnectedView } from "../ConnectedView";
import { makeAppState } from "./testHelpers";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return { ...actual, openRequirements: vi.fn() };
});
import { openRequirements } from "../state";

// AUD-117: openInterviews() sets interviewError but leaves view==="connected"
// on failure; InterviewListView renders ErrorBanner, ConnectedView did not --
// so a failed `openInterviews` was a silent no-op on the connected panel.
describe("ConnectedView", () => {
  it("shows the interview error so a failed openInterviews is visible", () => {
    render(
      <ConnectedView
        state={makeAppState({ view: "connected", interviewError: "Failed to load interviews." })}
      />
    );

    expect(screen.getByText("Failed to load interviews.")).toBeInTheDocument();
  });

  it("renders no error banner while there is no error", () => {
    render(<ConnectedView state={makeAppState({ view: "connected", interviewError: null })} />);

    expect(screen.queryByText("Failed to load interviews.")).not.toBeInTheDocument();
  });

  it("offers a Requirements entry before the Interviews entry", () => {
    render(<ConnectedView state={makeAppState({ view: "connected" })} />);

    const testIds = screen.getAllByRole("button").map((button) => button.getAttribute("data-testid"));

    expect(testIds).toContain("open-requirements-button");
    expect(testIds.indexOf("open-requirements-button")).toBeLessThan(
      testIds.indexOf("open-interviews-button")
    );
  });

  it("opens the requirements section from the Requirements button", () => {
    render(<ConnectedView state={makeAppState({ view: "connected" })} />);

    fireEvent.click(screen.getByTestId("open-requirements-button"));

    expect(openRequirements).toHaveBeenCalledTimes(1);
  });
});
