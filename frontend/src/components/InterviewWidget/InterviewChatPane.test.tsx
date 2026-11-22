/**
 * Interview-management web widget — chat pane (plan Task 6).
 *
 * Review-fix coverage: result-summary links route via getArtifactRoute
 * (F1), interview.multi.* i18n keys are consumed (F2), and the proposal
 * confirm button has a double-submit guard (F3).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { StrictMode, type ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { InterviewChatPane, type CreatedArtifactRef } from "./InterviewChatPane";
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

  // L2.4 review fix F5: `transcript` is only the sliding window once the
  // backend compresses older turns, so a live conversation would appear to
  // lose its own earlier messages without this collapsed digest.
  it("renders the collapsed earlier-conversation block when a summary exists", () => {
    const interview = makeInterview({
      transcript: [{ role: "user", text: "Latest", timestamp: "t9" }],
      transcript_summary: "We agreed on the login scope.",
    });
    renderPane(<InterviewChatPane interview={interview} onStateChange={vi.fn()} />);

    const block = screen.getByTestId("interview-earlier-summary");
    expect(block).toBeInTheDocument();
    // Collapsed by default -- context, not part of the live exchange.
    expect(block).not.toHaveAttribute("open");
    expect(
      screen.getByText(resolveLocaleKey("interview.multi.earlierConversation") ?? "")
    ).toBeInTheDocument();
    expect(screen.getByText("We agreed on the login scope.")).toBeInTheDocument();
    // The live window still renders alongside it.
    expect(screen.getByText("Latest")).toBeInTheDocument();
  });

  it("omits the earlier-conversation block when there is no summary", () => {
    const interview = makeInterview({
      transcript: [{ role: "user", text: "Latest", timestamp: "t9" }],
      transcript_summary: "",
    });
    renderPane(<InterviewChatPane interview={interview} onStateChange={vi.fn()} />);

    expect(screen.queryByTestId("interview-earlier-summary")).not.toBeInTheDocument();
  });

  it("omits the earlier-conversation block when the key is absent (multi mode)", () => {
    const interview = makeInterview({
      transcript: [{ role: "user", text: "Latest", timestamp: "t9" }],
    });
    renderPane(<InterviewChatPane interview={interview} onStateChange={vi.fn()} />);

    expect(screen.queryByTestId("interview-earlier-summary")).not.toBeInTheDocument();
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
// Issue #1967: guided first question on mount
// ---------------------------------------------------------------------------

describe("InterviewChatPane guided first question", () => {
  const openField = { name: "rationale", type: "textarea" };

  beforeEach(() => {
    vi.clearAllMocks();
    // Multi-mode sessions still run the proposal effect on mount; a default
    // resolution keeps that effect harmless while this suite focuses on chat.
    vi.mocked(interviewsApi.propose).mockResolvedValue({ proposal: null });
  });

  it("asks the first protocol question on mount for a fresh single-kind session", async () => {
    const onStateChange = vi.fn();
    const greeted = makeInterview({
      id: "s-fresh",
      missing_fields: [openField],
      transcript: [],
    });
    vi.mocked(interviewsApi.chat).mockResolvedValue({
      reply: "Why does this requirement exist?",
      state: greeted,
    });

    renderPane(<InterviewChatPane interview={greeted} onStateChange={onStateChange} />);

    await waitFor(() =>
      expect(interviewsApi.chat).toHaveBeenCalledWith("s-fresh", "")
    );
    expect(onStateChange).toHaveBeenCalledWith(greeted);
  });

  it("fires one chat call AND applies the first reply under React StrictMode", async () => {
    const greeted = makeInterview({ id: "s-strict", missing_fields: [openField] });
    vi.mocked(interviewsApi.chat).mockResolvedValue({
      reply: "First question",
      state: greeted,
    });
    const onStateChange = vi.fn();

    renderPane(
      <StrictMode>
        <InterviewChatPane interview={greeted} onStateChange={onStateChange} />
      </StrictMode>
    );

    await waitFor(() =>
      expect(interviewsApi.chat).toHaveBeenCalledWith("s-strict", "")
    );
    expect(interviewsApi.chat).toHaveBeenCalledTimes(1);
    // Regression for F1: the first setup's cleanup used to cancel the only
    // reply, so the count passed while the question never reached the UI.
    await waitFor(() => expect(onStateChange).toHaveBeenCalledWith(greeted));
  });

  it("does not greet a multi-kind session", () => {
    const multi = makeInterview({
      id: "s-multi",
      session_kind: "multi",
      missing_fields: [openField],
    });
    renderPane(<InterviewChatPane interview={multi} onStateChange={vi.fn()} />);
    expect(interviewsApi.chat).not.toHaveBeenCalled();
  });

  it("does not greet a session that already has a transcript", () => {
    const used = makeInterview({
      id: "s-used",
      missing_fields: [openField],
      transcript: [{ role: "user", text: "hi", timestamp: "t1" }],
    });
    renderPane(<InterviewChatPane interview={used} onStateChange={vi.fn()} />);
    expect(interviewsApi.chat).not.toHaveBeenCalled();
  });

  it("does not block the page when the first chat call fails", async () => {
    vi.mocked(interviewsApi.chat).mockRejectedValue(new Error("no provider"));
    const fresh = makeInterview({ id: "s-fail", missing_fields: [openField] });
    const onStateChange = vi.fn();
    renderPane(<InterviewChatPane interview={fresh} onStateChange={onStateChange} />);

    await waitFor(() =>
      expect(interviewsApi.chat).toHaveBeenCalledWith("s-fail", "")
    );
    expect(onStateChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByTestId("interview-chat-input")).not.toBeDisabled();
  });

  it("does not crash when the first chat call returns undefined", async () => {
    // A stubbed/absent transport can hand back `undefined` instead of a
    // Promise. `Promise.resolve` must normalise that without a synchronous
    // `.then`-on-undefined throw, and the empty catch must swallow the
    // destructuring rejection so the page stays usable.
    vi.mocked(interviewsApi.chat).mockReturnValue(
      undefined as unknown as ReturnType<typeof interviewsApi.chat>
    );
    const fresh = makeInterview({ id: "s-undefined", missing_fields: [openField] });
    const onStateChange = vi.fn();
    renderPane(<InterviewChatPane interview={fresh} onStateChange={onStateChange} />);

    await waitFor(() =>
      expect(interviewsApi.chat).toHaveBeenCalledWith("s-undefined", "")
    );
    expect(onStateChange).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByTestId("interview-chat-input")).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Multi-mode (plan Task 12): proposal card + result summary
// ---------------------------------------------------------------------------

describe("InterviewChatPane multi-mode", () => {
  const proposal: ProposalItem[] = [
    { type: "StakeholderNeed", title: "Need A", fields: { title: "Need A" }, links: [] },
  ];

  // Multi-aware state shape: `session_kind` now lives on the shared
  // InterviewState (backend get_state()/chat()/start() all emit it), so no
  // locally widened type is needed any more.
  function makeMultiInterview(
    overrides: Partial<InterviewState> = {}
  ): InterviewState {
    return { ...makeInterview(), ...overrides } as InterviewState;
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
