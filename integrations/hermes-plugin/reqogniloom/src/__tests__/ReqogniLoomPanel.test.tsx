import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReqogniLoomPanel } from "../ReqogniLoomPanel";
import * as state from "../state";
import { makeAppState } from "./testHelpers";

describe("ReqogniLoomPanel — interviews routing", () => {
  it("renders InterviewListView when view is interviews and no activeInterview is set", () => {
    vi.spyOn(state, "getState").mockReturnValue(makeAppState());
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByText(/Start new/i)).toBeInTheDocument();
  });

  it("renders InterviewFormView when an activeInterview is set", () => {
    vi.spyOn(state, "getState").mockReturnValue(
      makeAppState({
        activeInterview: {
          session_id: "s-1", status: "in_progress", phase: "elicitation",
          collected_fields: {}, missing_fields: [{ name: "title", type: "text", choices: null }],
          grounding_snapshot: { candidates: [] },
        },
      })
    );
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByTestId("interview-field-title")).toBeInTheDocument();
  });
});
