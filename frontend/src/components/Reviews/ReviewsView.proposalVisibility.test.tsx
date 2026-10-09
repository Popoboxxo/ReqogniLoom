/**
 * Issue #1089 — the AI-proposals queue must be visible and self-explanatory.
 *
 * The queue mode and its confirm/discard mechanics already existed (spec
 * §4.4). What was missing is the two things that make an AI proposal
 * *reviewable* rather than merely listed:
 *
 *   1. the toggle said "AI proposals only" without saying whether anything is
 *      waiting — the same "created but never presented" gap the backend fix
 *      closes, one layer up. A bare number was not enough: a reviewer landing
 *      on /reviews in the DEFAULT (review) mode had nothing that told them
 *      what the number counted, so the queue stayed undiscovered. The toggle
 *      now carries a full sentence (`workflow.proposal.pendingCount`) while
 *      the review queue is on screen;
 *   2. nothing in the queue or the detail pane said the content came from the
 *      AI, or who proposed it.
 *
 * Both are asserted here against the real component, not the hook alone.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Module mocks (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("../../api/requirements");
vi.mock("../../context/WorkspaceContext");
vi.mock("../../api/workflow-transitions", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../api/workflow-transitions")>();
  return {
    ...actual,
    workflowTransitionsApi: {
      listByStatus: vi.fn(),
      getTransitions: vi.fn(),
      transition: vi.fn(),
      getWorkflowHistory: vi.fn(),
      diff: vi.fn(),
      versions: vi.fn(),
    },
  };
});
// Stub the aggregate count wrapper (#1193): unmocked it calls the real axios
// client, which makes an unwanted network request in jsdom. A bare vi.fn()
// leaves the badge hidden, which is irrelevant to these tests.
vi.mock("../../api/reviews", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/reviews")>();
  return { ...actual, reviewsApi: { listPendingCount: vi.fn() } };
});
// A `t` that interpolates, so "Vorschlag von {{agent}}" is observable.
vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>
  ): string => {
    if (typeof fallbackOrOptions === "string") return fallbackOrOptions;
    const opts = (fallbackOrOptions ?? {}) as Record<string, unknown>;
    return `${key}:${Object.values(opts).join(",")}`;
  };
  return { useTranslation: () => ({ t }) };
});

import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";
import { workflowTransitionsApi } from "../../api/workflow-transitions";

import ReviewsView from "./ReviewsView";

const MOCK_WORKSPACE = {
  id: "ws-prop-001",
  name: "Proposal WS",
  preset: "extended",
};

const PROPOSAL_ITEMS = [
  {
    id: "req-prop-1",
    workspace_id: "ws-prop-001",
    title: "System shall show throughput",
    description: "AI generated.",
    status: "proposed",
    version: 1,
    uid: "SyReq-101",
  },
  {
    id: "req-prop-2",
    workspace_id: "ws-prop-001",
    title: "System shall log every decision",
    description: "AI generated.",
    status: "proposed",
    version: 1,
    uid: "SyReq-102",
  },
];

const IN_REVIEW_ITEMS = [
  {
    id: "req-rev-1",
    workspace_id: "ws-prop-001",
    title: "Brake-by-wire latency budget",
    description: "A colleague's work.",
    status: "in_review",
    version: 3,
    uid: "SyReq-001",
  },
];

/** The transitions contract, as the backend sends it: `proposed_by` is
 * null-or-string by contract, so the fixture type has to say so. */
interface TransitionsContract {
  current_state: string | null;
  states: string[];
  allowed_transitions: Array<{
    target_state: string;
    requires_change_reason: boolean;
    signature_gate: boolean;
  }>;
  proposed_by: string | null;
}

const PROPOSAL_TRANSITIONS: TransitionsContract = {
  current_state: "proposed",
  states: ["draft", "proposed", "rejected"],
  allowed_transitions: [
    { target_state: "draft", requires_change_reason: false, signature_gate: false },
    { target_state: "rejected", requires_change_reason: true, signature_gate: false },
  ],
  proposed_by: "ai-derivation",
};

const IN_REVIEW_TRANSITIONS: TransitionsContract = {
  current_state: "in_review",
  states: ["draft", "in_review", "approved"],
  allowed_transitions: [
    { target_state: "approved", requires_change_reason: true, signature_gate: false },
    { target_state: "draft", requires_change_reason: true, signature_gate: false },
  ],
  proposed_by: null,
};

const renderReviewsView = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReviewsView />
    </QueryClientProvider>
  );
};

/**
 * Route the status-filtered list query the way the backend answers it.
 *
 * The default artifact type is `requirement`, whose resolver
 * (`reviewsResolver.requirementResolver`) deliberately delegates to
 * `requirementsApi.list` rather than the generic
 * `workflowTransitionsApi.listByStatus` — so that is the one to stub here.
 * Both are stubbed so a future default-type change cannot silently make these
 * assertions vacuous.
 */
function routeListByStatus(
  inReview: unknown[],
  proposals: unknown[]
): void {
  vi.mocked(requirementsModule.requirementsApi.list).mockImplementation(
    async (_workspaceId: unknown, status?: string) =>
      ({
        count: (status === "proposed" ? proposals : inReview).length,
        next: null,
        previous: null,
        page_size: 25,
        max_page_size: 100,
        results: status === "proposed" ? proposals : inReview,
      }) as never
  );
  vi.mocked(workflowTransitionsApi.listByStatus).mockImplementation(
    async (_type, _workspaceId, status) =>
      (status === "proposed" ? proposals : inReview) as never
  );
}

describe("ReviewsView — AI proposals queue (#1089)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as unknown as ReturnType<typeof workspaceContext.useWorkspace>);
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue(
      IN_REVIEW_TRANSITIONS as never
    );
    // The requirement resolver (the default artifact type) reads the same
    // contract through `requirementsApi.getTransitions`.
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue(
      IN_REVIEW_TRANSITIONS as never
    );
    vi.mocked(workflowTransitionsApi.getWorkflowHistory).mockResolvedValue([]);
  });

  /** Point both transitions readers at the same contract. */
  const routeTransitions = (contract: TransitionsContract): void => {
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue(
      contract as never
    );
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue(
      contract as never
    );
  };

  it("tells the reviewer how many AI proposals are waiting while the review queue is shown", async () => {
    // The default mode is "review" — this is the state the user lands in, and
    // before this the switch looked like an empty filter.
    routeListByStatus(IN_REVIEW_ITEMS, PROPOSAL_ITEMS);

    renderReviewsView();

    await waitFor(() => {
      expect(
        screen.getByTestId("reviews-proposal-count-hint")
      ).toHaveTextContent("workflow.proposal.pendingCount:2");
    });
    // The review queue itself is unaffected.
    expect(
      screen.getByTestId("review-list-item-req-rev-1")
    ).toBeInTheDocument();
  });

  it("hides the count when nothing is waiting", async () => {
    routeListByStatus(IN_REVIEW_ITEMS, []);

    renderReviewsView();

    await waitFor(() => {
      expect(
        screen.getByTestId("review-list-item-req-rev-1")
      ).toBeInTheDocument();
    });
    expect(screen.queryByTestId("reviews-proposal-count-hint")).toBeNull();
  });

  it("advertises no number while the proposals count is still in flight", async () => {
    // The proposals count is its own always-on query (#1089). While it is
    // unresolved the toggle must not name a number: the query function has not
    // produced data yet, so "N proposals awaiting review" would be a guess.
    // (Note this is the only state the `proposalCountLoading` guard can ever
    // see on its own — TanStack Query's `isLoading` means "pending AND no
    // data", so the loading and zero-count branches are mutually exclusive by
    // construction. The assertion below is the observable contract; the guard
    // is its belt-and-braces.)
    routeListByStatus(
      IN_REVIEW_ITEMS,
      new Promise(() => {}) as unknown as unknown[]
    );

    renderReviewsView();

    await waitFor(() => {
      expect(
        screen.getByTestId("review-list-item-req-rev-1")
      ).toBeInTheDocument();
    });
    expect(screen.queryByTestId("reviews-proposal-count-hint")).toBeNull();
  });

  it("marks every row of the proposals queue as AI-authored", async () => {
    routeListByStatus([], PROPOSAL_ITEMS);

    renderReviewsView();

    await userEvent.click(
      screen.getByTestId("reviews-queue-mode-checkbox")
    );

    for (const item of PROPOSAL_ITEMS) {
      await waitFor(() => {
        expect(
          screen.getByTestId(`review-proposal-badge-${item.id}`)
        ).toBeInTheDocument();
      });
    }
  });

  it("shows no proposal badge in the ordinary review queue", async () => {
    routeListByStatus(IN_REVIEW_ITEMS, PROPOSAL_ITEMS);

    renderReviewsView();

    await waitFor(() => {
      expect(
        screen.getByTestId("review-list-item-req-rev-1")
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("review-proposal-badge-req-rev-1")
    ).toBeNull();
  });

  it("names the proposer in the detail pane", async () => {
    routeListByStatus([], PROPOSAL_ITEMS);
    routeTransitions(PROPOSAL_TRANSITIONS);

    renderReviewsView();

    await userEvent.click(
      screen.getByTestId("reviews-queue-mode-checkbox")
    );
    await userEvent.click(
      await screen.findByTestId("review-list-item-req-prop-1")
    );

    await waitFor(() => {
      const origin = screen.getByTestId("review-proposal-origin");
      expect(origin).toHaveTextContent("workflow.proposal.hint");
      expect(origin).toHaveTextContent("ai-derivation");
    });
  });

  it("falls back to a generic AI label when no proposer was recorded", async () => {
    routeListByStatus([], PROPOSAL_ITEMS);
    routeTransitions({ ...PROPOSAL_TRANSITIONS, proposed_by: null });

    renderReviewsView();

    await userEvent.click(
      screen.getByTestId("reviews-queue-mode-checkbox")
    );
    await userEvent.click(
      await screen.findByTestId("review-list-item-req-prop-1")
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("review-proposal-origin")
      ).toHaveTextContent("workflow.proposal.hintUnknown");
    });
  });

  it("shows no origin line for an ordinary in_review item", async () => {
    routeListByStatus(IN_REVIEW_ITEMS, PROPOSAL_ITEMS);

    renderReviewsView();

    await userEvent.click(
      await screen.findByTestId("review-list-item-req-rev-1")
    );

    await waitFor(() => {
      expect(screen.getByTestId("review-detail")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("review-proposal-origin")).toBeNull();
  });
});
