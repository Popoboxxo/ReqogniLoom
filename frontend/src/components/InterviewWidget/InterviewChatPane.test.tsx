/**
 * Interview-management web widget — chat pane (plan Task 6).
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { InterviewChatPane } from "./InterviewChatPane";
import type { InterviewState } from "../../api/interviews";

vi.mock("../../api/interviews", () => ({
  interviewsApi: { chat: vi.fn() },
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
