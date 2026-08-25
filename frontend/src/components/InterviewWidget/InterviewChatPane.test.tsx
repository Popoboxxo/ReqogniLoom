/**
 * Interview-management web widget — chat pane (plan Task 6).
 *
 * Review-fix coverage: result-summary links route via getArtifactRoute
 * (F1), interview.multi.* i18n keys are consumed (F2), and the proposal
 * confirm button has a double-submit guard (F3).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { InterviewChatPane, type CreatedArtifactRef, type MultiModeInterview } from "./InterviewChatPane";
import type { InterviewState, MultiFormalizeResult, ProposalItem, SingleFormalizeResult } from "../../api/interviews";
import { getArtifactRoute } from "../../utils/artifactRoutes";
import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("../../api/interviews", () => ({
  interviewsApi: { chat: vi.fn(), propose: vi.fn(), formalize: vi.fn() },
}));
import { interviewsApi } from "../../api/interviews";

// F2: the pane consumes interview.multi.* keys (placeholder, send label,
// badge title), so resolve keys against de.json like specs asserting German
// copy (same convention as NeedList.test.tsx via i18n-test-helpers).
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => resolveLocaleKey(key) ?? key,
  }),
}));

// Resolved German copy under test (de/en parity itself is guarded by
// src/test/i18n-parity.test.ts).
const CHAT_PLACEHOLDER = resolveLocaleKey("interview.multi.chatPlaceholder") ?? "";
const SEND_LABEL = resolveLocaleKey("interview.multi.send") ?? "";
const CREATED_BADGE_TITLE = resolveLocaleKey("interview.multi.createdBadge") ?? "";

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

// The result summary renders a react-router <Link>, which requires a Router
// context (same MemoryRouter convention as NeedList.test.tsx). Wrapped for
// every render so the pane stays router-safe regardless of branch.
function renderPane(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("InterviewChatPane", () => {
  it("renders existing transcript messages", () => {
    const interview = makeInterview({
      transcript: [
        { role: "user", text: "Hi", timestamp: "t1" },
        { role: "assistant", text: "Hello", timestamp: "t2" },
      ],
    });
    renderPane(<InterviewChatPane interview={interview} onStateChange={vi.fn()} />);

    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("sends a message and calls onStateChange with the refreshed state", async () => {
    const onStateChange = vi.fn();
    vi.mocked(interviewsApi.chat).mockResolvedValue({
      reply: "Got it.",
      state: makeInterview({ collected_fields: { title: "x" } }),
    });
    renderPane(<InterviewChatPane interview={makeInterview()} onStateChange={onStateChange} />);

    fireEvent.change(screen.getByTestId("interview-chat-input"), { target: { value: "We need SSO" } });
    fireEvent.click(screen.getByTestId("interview-chat-send"));

    await waitFor(() => expect(onStateChange).toHaveBeenCalled());
    expect(interviewsApi.chat).toHaveBeenCalledWith("s-1", "We need SSO");
  });

  it("keeps the input text and shows an error if chat fails", async () => {
    vi.mocked(interviewsApi.chat).mockRejectedValue(new Error("no provider"));
    renderPane(<InterviewChatPane interview={makeInterview()} onStateChange={vi.fn()} />);

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
    renderPane(
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
    renderPane(
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

  // F1 review fix: the old markup linked to the non-existent
  // /artifacts/<id> route. Links must resolve through getArtifactRoute
  // (StakeholderNeed -> /needs/<id>, verified against NavigationShell).
  it("links each created artifact to its getArtifactRoute SPA route", async () => {
    vi.mocked(interviewsApi.propose).mockResolvedValue({ proposal });
    vi.mocked(interviewsApi.formalize).mockResolvedValue({
      created: [
        { artifact_id: "a1", artifact_type: "StakeholderNeed" },
        { artifact_id: "a2", artifact_type: "Requirement" },
      ] satisfies CreatedArtifactRef[],
      status: "completed",
    } as unknown as SingleFormalizeResult);
    renderPane(
      <InterviewChatPane
        interview={makeMultiInterview({ id: "s1", session_kind: "multi" })}
        onStateChange={vi.fn()}
        onFormalized={vi.fn()}
      />
    );

    fireEvent.click(await screen.findByTestId("interview-multi-confirm"));
    await screen.findByTestId("interview-multi-result");

    const needLink = screen.getByRole("link", { name: "a1" });
    expect(needLink).toHaveAttribute(
      "href",
      getArtifactRoute("StakeholderNeed", "a1")
    );
    expect(getArtifactRoute("StakeholderNeed", "a1")).toBe("/needs/a1");
    expect(screen.getByRole("link", { name: "a2" })).toHaveAttribute(
      "href",
      "/requirements/a2"
    );
  });

  // F2 review fix: interview.multi.createdBadge must be consumed, not dead
  // copy -- rendered as the badge title in the result summary.
  it("shows the createdBadge i18n copy as badge title", async () => {
    vi.mocked(interviewsApi.propose).mockResolvedValue({ proposal });
    vi.mocked(interviewsApi.formalize).mockResolvedValue({
      created: [{ artifact_id: "a1", artifact_type: "StakeholderNeed" }],
      status: "completed",
    } as unknown as SingleFormalizeResult);
    renderPane(
      <InterviewChatPane
        interview={makeMultiInterview({ id: "s1", session_kind: "multi" })}
        onStateChange={vi.fn()}
        onFormalized={vi.fn()}
      />
    );

    fireEvent.click(await screen.findByTestId("interview-multi-confirm"));
    await screen.findByTestId("interview-multi-result");

    expect(screen.getByTitle(CREATED_BADGE_TITLE)).toHaveTextContent(
      "StakeholderNeed"
    );
  });

  // F3 review fix: two fast confirm clicks must fire exactly one formalize
  // POST (disabled button + creating guard while the first call is pending).
  it("ignores double submit: formalize is called once for rapid double click", async () => {
    let resolveFormalize!: (value: MultiFormalizeResult) => void;
    vi.mocked(interviewsApi.propose).mockResolvedValue({ proposal });
    vi.mocked(interviewsApi.formalize).mockImplementation(
      () =>
        new Promise<MultiFormalizeResult>((resolve) => {
          resolveFormalize = resolve;
        }) as unknown as Promise<SingleFormalizeResult>
    );
    renderPane(
      <InterviewChatPane
        interview={makeMultiInterview({ id: "s1", session_kind: "multi" })}
        onStateChange={vi.fn()}
        onFormalized={vi.fn()}
      />
    );

    const confirm = await screen.findByTestId("interview-multi-confirm");
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    expect(interviewsApi.formalize).toHaveBeenCalledTimes(1);

    resolveFormalize({ status: "completed", created: [{ artifact_id: "a1", artifact_type: "StakeholderNeed" }] });
    expect(await screen.findByTestId("interview-multi-result")).toBeInTheDocument();
    expect(interviewsApi.formalize).toHaveBeenCalledTimes(1);
  });

  // F2 review fix: the chat input gets its placeholder from i18n and the
  // send button label comes from interview.multi.send (was hardcoded "Send").
  it("uses i18n copy for input placeholder and send label", async () => {
    renderPane(<InterviewChatPane interview={makeMultiInterview()} onStateChange={vi.fn()} />);

    expect(screen.getByPlaceholderText(CHAT_PLACEHOLDER)).toBeInTheDocument();
    expect(screen.getByTestId("interview-chat-send")).toHaveTextContent(SEND_LABEL);
    expect(screen.queryByText("Send")).not.toBeInTheDocument();
  });
});
