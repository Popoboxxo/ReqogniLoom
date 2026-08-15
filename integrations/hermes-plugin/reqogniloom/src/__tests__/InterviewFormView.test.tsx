import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterviewFormView } from "../InterviewFormView";
import type { AppState } from "../state";
import type { InterviewState } from "../mcpClient";

vi.mock("../state", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state")>();
  return { ...actual, answerInterviewField: vi.fn(), formalizeInterview: vi.fn(), closeInterview: vi.fn() };
});
import { answerInterviewField, closeInterview, formalizeInterview } from "../state";

function makeInterview(overrides: Partial<InterviewState> = {}): InterviewState {
  return {
    session_id: "s-1", status: "in_progress", phase: "elicitation",
    collected_fields: {}, missing_fields: [], grounding_snapshot: { candidates: [] },
    ...overrides,
  };
}

function makeState(activeInterview: InterviewState, overrides: Partial<AppState> = {}): AppState {
  return {
    view: "interviews", connection: { baseUrl: "https://x", apiKey: "k", workspaceId: "ws-1" },
    workspaceName: "WS", pendingCredentials: null, pendingWorkspaces: [],
    connectError: null, connecting: false, activeInterview,
    interviewList: [], interviewError: null, interviewBusy: false,
    ...overrides,
  };
}

describe("InterviewFormView field rendering", () => {
  it("renders a textarea for a textarea field", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "rationale", type: "textarea", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.getByTestId("interview-field-rationale").tagName).toBe("TEXTAREA");
  });

  it("renders a select with the given choices for an enum field", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "element_type", type: "enum", choices: ["component", "system"] }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    const select = screen.getByTestId("interview-field-element_type");
    expect(select.tagName).toBe("SELECT");
    expect(screen.getByText("component")).toBeInTheDocument();
    expect(screen.getByText("system")).toBeInTheDocument();
  });

  it("renders a number input for a number field", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "priority", type: "number", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.getByTestId("interview-field-priority")).toHaveAttribute("type", "number");
  });

  it("calls answerInterviewField on blur with the entered value", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    const input = screen.getByTestId("interview-field-title");
    fireEvent.change(input, { target: { value: "SSO login" } });
    fireEvent.blur(input);

    expect(answerInterviewField).toHaveBeenCalledWith("title", "SSO login");
  });

  it("disables Formalize while any field is still missing", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.getByTestId("interview-formalize-button")).toBeDisabled();
  });

  it("enables Formalize when no fields are missing and calls formalizeInterview + closeInterview on success", async () => {
    vi.mocked(formalizeInterview).mockResolvedValue({ resulting_artifact_ids: ["art-1"] });
    const interview = makeInterview({ missing_fields: [] });
    render(<InterviewFormView state={makeState(interview)} />);

    const button = screen.getByTestId("interview-formalize-button");
    expect(button).not.toBeDisabled();
    fireEvent.click(button);

    await screen.findByText(/art-1/i);
  });

  it("shows grounding candidates as a hint list", () => {
    const interview = makeInterview({
      grounding_snapshot: { candidates: [{ artifact_id: "art-9", title: "Similar existing req", score: null }] },
    });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.getByText(/Similar existing req/i)).toBeInTheDocument();
  });

  it("shows interviewError when present", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview, { interviewError: "boom" })} />);

    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders a Cancel button in the in-progress branch that calls closeInterview", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });
    render(<InterviewFormView state={makeState(interview)} />);

    fireEvent.click(screen.getByTestId("interview-form-cancel-button"));

    expect(closeInterview).toHaveBeenCalled();
  });

  it("renders without throwing when grounding_snapshot has no candidates key (realistic un-grounded backend shape)", () => {
    const interview = makeInterview({
      grounding_snapshot: {},
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });

    expect(() => render(<InterviewFormView state={makeState(interview)} />)).not.toThrow();
    expect(screen.queryByText(/Possibly related/i)).not.toBeInTheDocument();
  });

  it("renders a read-only completed view instead of the form when status is completed", () => {
    const interview = makeInterview({ status: "completed", missing_fields: [] });
    render(<InterviewFormView state={makeState(interview)} />);

    expect(screen.queryByTestId("interview-formalize-button")).not.toBeInTheDocument();
  });
});
