/**
 * ARCH-L1-001 ReactFrontend — InterviewDetail, multi-kind session path.
 *
 * Regression cover for the two blockers the final whole-branch review found,
 * both of which shipped invisibly past 88 green tests because every existing
 * suite verified one slice in isolation:
 *
 *   B1 — `/interviews/{id}` threw `undefined.length` for a multi session
 *        (`get_state()` omits `phase`/`missing_fields` by design), taking the
 *        whole route down via the ErrorBoundary.
 *   B2 — `get_state()` never returned `session_kind`, so the chat pane gated
 *        the entire proposal/confirm flow away: a multi session opened at
 *        `/interviews` could chat but could never formalise anything.
 *
 * Deliberately NOT mocked at the `api/interviews` module boundary (the way
 * InterviewEditors.test.tsx / InterviewChatPane.test.tsx do): the mock seam
 * here is one level lower, at `api/client`, so the real `interviewsApi`
 * wrappers run and the fixtures below are the literal REST payloads the
 * backend emits (`interview_views._state_dict` / `InterviewService.
 * _generate_multi_chat_turn` / `_formalize_multi`). A mock of the wrong shape
 * -- exactly what let B1/B2 through -- therefore cannot pass here.
 *
 * This is as close to end-to-end as jsdom gets: real component tree
 * (InterviewDetail -> InterviewChatPane -> ProposalPreviewGraph), real user
 * events (typing + submitting a chat turn, confirming a proposal), real
 * routing/i18n. It does not cover layout or a real HTTP round-trip.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import "../../i18n/index";

vi.mock("../../api/client", () => ({
  extractErrorMessage: vi.fn().mockReturnValue("Error"),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  getList: vi.fn().mockResolvedValue({ results: [], count: 0 }),
  getAllPages: vi.fn().mockResolvedValue([]),
}));

import { apiClient } from "../../api/client";
import type { InterviewState } from "../../api/interviews";
import { InterviewDetail } from "./InterviewDetail";

const SESSION_ID = "s-multi";

/**
 * Literal `GET /interviews/{id}/state/` body for a MULTI session --
 * `InterviewService.get_state()`'s multi branch, normalised to `id` by
 * `interview_views._state_dict`. No `phase`, no `missing_fields`: a multi
 * session is bound to no protocol, so neither concept exists for it.
 */
const MULTI_STATE = {
  id: SESSION_ID,
  status: "in_progress",
  session_kind: "multi",
  collected_fields: {},
  grounding_snapshot: {},
  transcript: [],
} as unknown as InterviewState;

/** Literal `POST /interviews/{id}/chat/` body for a multi session. */
const MULTI_CHAT_RESPONSE = {
  reply: "Sounds like a need and a requirement.",
  proposal: [
    { type: "StakeholderNeed", title: "Need A", fields: { title: "Need A" }, links: [] },
  ],
  state: {
    id: SESSION_ID,
    status: "in_progress",
    session_kind: "multi",
    collected_fields: {},
    grounding_snapshot: {},
    transcript: [
      { role: "user", content: "I need faster onboarding", timestamp: "t1" },
      { role: "assistant", content: "Sounds like a need and a requirement.", timestamp: "t2" },
    ],
  },
};

const PROPOSAL = MULTI_CHAT_RESPONSE.proposal;

function renderDetail(state: InterviewState, onChanged = vi.fn()) {
  return {
    onChanged,
    ...render(
      <MemoryRouter>
        <InterviewDetail interview={state} onChanged={onChanged} />
      </MemoryRouter>
    ),
  };
}

describe("InterviewDetail — multi-kind session", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // No proposal until the first chat turn has produced one.
    vi.mocked(apiClient.get).mockResolvedValue({ proposal: null });
    vi.mocked(apiClient.post).mockResolvedValue({});
  });

  // B1: the crash was `current.missing_fields.length` on a payload that has
  // no such key. Rendering at all is the assertion.
  it("renders a multi session without crashing and shows no missing-field list", async () => {
    renderDetail(MULTI_STATE);

    expect(await screen.findByTestId("interview-detail")).toBeInTheDocument();
    expect(screen.getByTestId("interview-detail-status")).toHaveTextContent("In Progress");
    expect(screen.queryByTestId("interview-missing-fields")).not.toBeInTheDocument();
    // The chat surface is there -- /interviews is the full interview surface.
    expect(screen.getByTestId("interview-chat-input")).toBeInTheDocument();
  });

  // The single-mode Formalize button posts without a confirmed proposal,
  // which `_formalize_multi` rejects with a 400 -- it must not be offered.
  it("does not offer the single-mode formalize button for a multi session", async () => {
    renderDetail(MULTI_STATE);

    await screen.findByTestId("interview-detail");
    expect(screen.queryByTestId("interview-artifact-formalize")).not.toBeInTheDocument();
  });

  // B2, end to end: chat turn -> proposal card -> confirm -> created artifacts.
  it("chats, renders the resulting proposal and creates the artifacts on confirm", async () => {
    const onChanged = vi.fn();
    const user = userEvent.setup();
    vi.mocked(apiClient.post).mockImplementation(async (url: string) => {
      if (url.endsWith("/chat/")) return MULTI_CHAT_RESPONSE as never;
      if (url.endsWith("/formalize/")) {
        return {
          created: [{ artifact_id: "a1", artifact_type: "StakeholderNeed" }],
          status: "completed",
        } as never;
      }
      return {} as never;
    });

    renderDetail(MULTI_STATE, onChanged);
    await screen.findByTestId("interview-detail");

    // 1. A real chat turn, typed and submitted.
    await user.type(screen.getByTestId("interview-chat-input"), "I need faster onboarding");
    // The proposal for the NEXT state fetch exists only after this turn.
    vi.mocked(apiClient.get).mockResolvedValue({ proposal: PROPOSAL });
    await user.click(screen.getByTestId("interview-chat-send"));

    expect(apiClient.post).toHaveBeenCalledWith(`/interviews/${SESSION_ID}/chat/`, {
      message: "I need faster onboarding",
    });
    // Both sides of the exchange are rendered from the returned state.
    expect(await screen.findByText("I need faster onboarding")).toBeInTheDocument();
    expect(screen.getByText("Sounds like a need and a requirement.")).toBeInTheDocument();

    // 2. The proposal card appears -- only reachable because the chat state
    //    still carries session_kind: "multi" (B2's second half).
    expect(await screen.findByTestId("proposal-preview-graph")).toBeInTheDocument();
    const confirm = await screen.findByTestId("interview-multi-confirm");

    // 3. Confirming posts the proposal and shows the created artifacts.
    await user.click(confirm);

    expect(await screen.findByTestId("interview-multi-result")).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith(`/interviews/${SESSION_ID}/formalize/`, {
      confirmed_proposal: PROPOSAL,
    });
    expect(screen.getByRole("link", { name: "a1" })).toHaveAttribute("href", "/needs/a1");
    // The session is completed now, so the list/status upstream must refetch.
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  // The single-mode path must keep working unchanged next to all of the above.
  it("still renders phase/missing fields and the formalize pane for a single session", async () => {
    const singleState = {
      id: "s-single",
      status: "in_progress",
      session_kind: "single",
      phase: "elicitation",
      collected_fields: {},
      missing_fields: [{ name: "title", type: "text", choices: null }],
      grounding_snapshot: {},
      transcript: [],
      transcript_summary: "",
    } as unknown as InterviewState;

    renderDetail(singleState);

    expect(await screen.findByTestId("interview-missing-fields")).toHaveTextContent("title");
    expect(screen.getByTestId("interview-artifact-formalize")).toBeInTheDocument();
    // No propose() polling for a single session.
    expect(apiClient.get).not.toHaveBeenCalled();
  });
});
