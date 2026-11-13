import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReqogniLoomPanel } from "../ReqogniLoomPanel";
import * as state from "../state";
import { makeAppState, makeRequirement, makeRequirementForm } from "./testHelpers";

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

describe("ReqogniLoomPanel — requirements routing", () => {
  it("renders the requirements list for view 'requirements'", () => {
    vi.spyOn(state, "getState").mockReturnValue(
      makeAppState({ view: "requirements", requirements: [makeRequirement()], requirementsCount: 1 })
    );
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByTestId("requirements-list")).toBeInTheDocument();
    expect(screen.getByTestId("requirement-row-req-1")).toBeInTheDocument();
  });

  it("renders the requirement detail for view 'requirement-detail'", () => {
    vi.spyOn(state, "getState").mockReturnValue(
      makeAppState({ view: "requirement-detail", activeRequirement: makeRequirement() })
    );
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByTestId("requirement-detail-title")).toHaveTextContent("Login must work");
    expect(screen.getByTestId("requirement-edit-button")).toBeInTheDocument();
  });

  it("renders the requirement form for view 'requirement-form'", () => {
    vi.spyOn(state, "getState").mockReturnValue(
      makeAppState({ view: "requirement-form", requirementForm: makeRequirementForm() })
    );
    vi.spyOn(state, "subscribe").mockReturnValue(() => {});

    render(<ReqogniLoomPanel pluginId="p" panelId="reqogniloom" />);

    expect(screen.getByTestId("requirement-form-submit")).toBeInTheDocument();
    expect(screen.getByTestId("requirement-form-title")).toBeInTheDocument();
    expect(screen.queryByTestId("requirements-list")).not.toBeInTheDocument();
  });
});
