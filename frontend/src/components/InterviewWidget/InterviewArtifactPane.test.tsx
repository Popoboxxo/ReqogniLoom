/**
 * Interview-management web widget — artifact panel pane (plan Task 7).
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { InterviewArtifactPane } from "./InterviewArtifactPane";
import type { InterviewState } from "../../api/interviews";

vi.mock("../../api/interviews", () => ({
  interviewsApi: { formalize: vi.fn() },
}));
import { interviewsApi } from "../../api/interviews";

function makeInterview(overrides: Partial<InterviewState> = {}): InterviewState {
  return {
    id: "s-1",
    status: "in_progress",
    phase: "elicitation",
    collected_fields: {},
    missing_fields: [],
    grounding_snapshot: { candidates: [] },
    transcript: [],
    ...overrides,
  } as InterviewState;
}

describe("InterviewArtifactPane", () => {
  it("shows grounding candidates as hints", () => {
    const interview = makeInterview({
      grounding_snapshot: { candidates: [{ artifact_id: "a-1", title: "Similar req", score: null }] },
    });
    render(<InterviewArtifactPane interview={interview} onFormalized={vi.fn()} />);

    expect(screen.getByText(/Similar req/i)).toBeInTheDocument();
  });

  it("does not crash when grounding_snapshot has no candidates yet (real shape returned by start())", () => {
    const interview = makeInterview({
      grounding_snapshot: {} as InterviewState["grounding_snapshot"],
    });

    expect(() =>
      render(<InterviewArtifactPane interview={interview} onFormalized={vi.fn()} />)
    ).not.toThrow();
    expect(screen.getByTestId("interview-artifact-formalize")).toBeInTheDocument();
  });

  it("disables Formalize while fields are missing", () => {
    const interview = makeInterview({
      missing_fields: [{ name: "title", type: "text", choices: null }],
    });
    render(<InterviewArtifactPane interview={interview} onFormalized={vi.fn()} />);

    expect(screen.getByTestId("interview-artifact-formalize")).toBeDisabled();
  });

  it("formalizes and reports the resulting artifact ids", async () => {
    vi.mocked(interviewsApi.formalize).mockResolvedValue({
      resulting_artifact_ids: ["art-1"],
      status: "completed",
    });
    const onFormalized = vi.fn();
    render(<InterviewArtifactPane interview={makeInterview()} onFormalized={onFormalized} />);

    fireEvent.click(screen.getByTestId("interview-artifact-formalize"));

    await waitFor(() => expect(onFormalized).toHaveBeenCalledWith({ resulting_artifact_ids: ["art-1"] }));
    expect(screen.getByText(/art-1/i)).toBeInTheDocument();
  });
});
