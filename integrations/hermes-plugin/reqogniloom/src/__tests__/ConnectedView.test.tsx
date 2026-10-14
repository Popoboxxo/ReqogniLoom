import * as React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConnectedView } from "../ConnectedView";
import { makeAppState } from "./testHelpers";

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
});
