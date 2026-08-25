/**
 * Interview-management web widget — chat pane (plan Task 6).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { InterviewChatPane, type MultiModeInterview } from "./InterviewChatPane";
import type { InterviewState, ProposalItem, SingleFormalizeResult } from "../../api/interviews";

vi.mock("../../api/interviews", () => ({
  interviewsApi: { chat: vi.fn(), propose: vi.fn(), formalize: vi.fn() },
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

describe("InterviewChatPane", () => {
  it("renders existing transcript messages", () => {
    const interview = makeInterview({
      transcript: [
        { role: "user", text: "Hi", timestamp: "t1" },
        { role: "assistant", text: "Hello", timestamp: "t2" },
      ],
    });
    render(<InterviewChatPane interview={interview} onStateChange={vi.fn()} />);

    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("sends a message and calls onStateChange with the refreshed state", async () => {
    const onStateChange = vi.fn();
    vi.mocked(interviewsApi.chat).mockResolvedValue({
      reply: "Got it.",
      state: makeInterview({ collected_fields: { title: "x" } }),
    });
    render(<InterviewChatPane interview={makeInterview()} onStateChange={onStateChange} />);

    fireEvent.change(screen.getByTestId("interview-chat-input"), { target: { value: "We need SSO" } });
    fireEvent.click(screen.getByTestId("interview-chat-send"));

    await waitFor(() => expect(onStateChange).toHaveBeenCalled());
    expect(interviewsApi.chat).toHaveBeenCalledWith("s-1", "We need SSO");
  });

  it("keeps the input text and shows an error if chat fails", async () => {
    vi.mocked(interviewsApi.chat).mockRejectedValue(new Error("no provider"));
    render(<InterviewChatPane interview={makeInterview()} onStateChange={vi.fn()} />);

    const input = screen.getByTestId("interview-chat-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByTestId("interview-chat-send"));

    await screen.findByText("no provider");
    expect(input.value).toBe("hello");
  });
});

// ---------------------------------------------------------------------------
// Multi-mode (plan Task 12): proposal card + result summary
// ---------------------------------------------------------------------------

describe("InterviewChatPane multi-mode", () => {
  const proposal: ProposalItem[] = [
    { type: "StakeholderNeed", title: "Need A", fields: { title: "Need A" }, links: [] },
  ];

  // Multi-aware state shape (see MultiModeInterview in InterviewChatPane.tsx):
  // backend get_state() doesn't carry session_kind yet, so the pane's prop
  // type keeps it optional.
  function makeMultiInterview(
    overrides: Partial<MultiModeInterview> = {}
  ): MultiModeInterview {
    return { ...makeInterview(), ...overrides } as MultiModeInterview;
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the proposal preview and a confirm button when a proposal is pending", async () => {
    vi.mocked(interviewsApi.propose).mockResolvedValue({ proposal });
    render(
      <InterviewChatPane
        interview={makeMultiInterview({ id: "s1", session_kind: "multi" })}
        onStateChange={vi.fn()}
        onFormalized={vi.fn()}
      />
    );

    expect(await screen.findByTestId("proposal-preview-graph")).toBeInTheDocument();
    expect(screen.getByTestId("interview-multi-confirm")).toBeInTheDocument();
  });

  it("confirming calls formalize with the proposal and shows the result summary", async () => {
    const onFormalized = vi.fn();
    vi.mocked(interviewsApi.propose).mockResolvedValue({ proposal });
    // Runtime contract (api/interviews.ts): a multi-kind formalize() responds
    // with MultiFormalizeResult even though its declared return type predates
    // multi-mode -- hence the cast here and inside the component.
    vi.mocked(interviewsApi.formalize).mockResolvedValue({
      created: [{ artifact_id: "a1", artifact_type: "StakeholderNeed" }],
      status: "completed",
    } as unknown as SingleFormalizeResult);
    render(
      <InterviewChatPane
        interview={makeMultiInterview({ id: "s1", session_kind: "multi" })}
        onStateChange={vi.fn()}
        onFormalized={onFormalized}
      />
    );

    fireEvent.click(await screen.findByTestId("interview-multi-confirm"));

    expect(await screen.findByTestId("interview-multi-result")).toBeInTheDocument();
    expect(interviewsApi.formalize).toHaveBeenCalledWith("s1", proposal);
    expect(onFormalized).toHaveBeenCalledWith([
      { artifact_id: "a1", artifact_type: "StakeholderNeed" },
    ]);
  });
});
