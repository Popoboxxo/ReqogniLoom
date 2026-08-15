import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReqogniLoomPanel } from "../ReqogniLoomPanel";
import * as state from "../state";

describe("ReqogniLoomPanel — interviews routing", () => {
  it("renders InterviewListView when view is interviews and no activeInterview is set", () => {
    vi.spyOn(state, "getState").mockReturnValue({
      view: "interviews", connection: { baseUrl: "x", apiKey: "k", workspaceId: "ws-1" },
      workspaceName: "WS", pendingCredentials: null, pendingWorkspaces: [],
      connectError: null, connecting: false, activeInterview: null,
      interviewList: [], interviewError: null, interviewBusy: false,
    });
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByText(/Start new/i)).toBeInTheDocument();
  });

  it("renders InterviewFormView when an activeInterview is set", () => {
    vi.spyOn(state, "getState").mockReturnValue({
      view: "interviews", connection: { baseUrl: "x", apiKey: "k", workspaceId: "ws-1" },
      workspaceName: "WS", pendingCredentials: null, pendingWorkspaces: [],
      connectError: null, connecting: false,
      activeInterview: {
        session_id: "s-1", status: "in_progress", phase: "elicitation",
        collected_fields: {}, missing_fields: [{ name: "title", type: "text", choices: null }],
        grounding_snapshot: { candidates: [] },
      },
      interviewList: [], interviewError: null, interviewBusy: false,
    });
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByTestId("interview-field-title")).toBeInTheDocument();
  });
});
