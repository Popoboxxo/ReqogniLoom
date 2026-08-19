/**
 * Regression test — BUG-05 (SYSTEMAUDIT_2026-08-18 §4,
 * e2e/tests/review-workflow.spec.ts).
 *
 * "Requirement-Übergänge draft->in_review->approved aktualisieren die
 * Queue-Liste in der UI nicht." None of the pre-existing ReviewsView tests
 * (ReviewsView.test.tsx) actually assert that the LIST re-renders without
 * the transitioned item after Approve/Reject succeeds — they only assert
 * that `requirementsApi.transition` was called with the right arguments.
 * This test closes that gap by making the mocked `list()` return an
 * updated (filtered) result on its second call, mirroring what the real
 * `?status=in_review` endpoint does once the transition has landed.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../api/requirements");
vi.mock("../../context/WorkspaceContext");
vi.mock("../../api/workflow-transitions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/workflow-transitions")>();
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
vi.mock("react-i18next", () => {
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";
import ReviewsView from "./ReviewsView";

const MOCK_WORKSPACE = { id: "ws-rev-001", name: "Review WS", preset: "extended" };

const REQ_IN_REVIEW = {
  id: "req-001",
  workspace_id: "ws-rev-001",
  title: "Brake-by-wire latency budget",
  description: "The system shall...",
  category: "functional",
  status: "in_review",
  version: 2,
  uid: "SyReq-001",
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-02T00:00:00Z",
};

const TRANSITIONS_APPROVE_AND_REJECT = {
  current_state: "in_review",
  states: ["draft", "in_review", "approved", "deprecated"],
  allowed_transitions: [
    { target_state: "approved", requires_change_reason: true, signature_gate: false },
    { target_state: "draft", requires_change_reason: true, signature_gate: false },
  ],
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

describe("ReviewsView — queue refresh after a transition (BUG-05)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
  });

  it("removes the item from the queue once Approve succeeds (list is refetched, not left stale)", async () => {
    // First call (initial mount): the item is in_review.
    // Second call (after the invalidateQueries triggered by the successful
    // transition): the backend's `?status=in_review` filter no longer
    // returns it, since it moved to "approved".
    vi.mocked(requirementsModule.requirementsApi.list)
      .mockResolvedValueOnce({ count: 1, next: null, previous: null, results: [REQ_IN_REVIEW] } as any)
      .mockResolvedValue({ count: 0, next: null, previous: null, results: [] } as any);
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue(
      TRANSITIONS_APPROVE_AND_REJECT as any
    );
    vi.mocked(requirementsModule.requirementsApi.transition).mockResolvedValue({
      id: "req-001",
      previous_state: "in_review",
      new_state: "approved",
      requirement: { ...REQ_IN_REVIEW, status: "approved" },
    } as any);
    const user = userEvent.setup();

    renderReviewsView();

    await waitFor(() => {
      expect(screen.getByTestId("review-list-item-req-001")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("review-list-item-req-001"));
    await waitFor(() => {
      expect(screen.getByTestId("review-approve-btn")).not.toBeDisabled();
    });

    await user.type(screen.getByTestId("review-change-reason-input"), "looks good to me");
    await user.click(screen.getByTestId("review-approve-btn"));

    // The queue must refetch and no longer show the (now approved) item.
    await waitFor(() => {
      expect(screen.queryByTestId("review-list-item-req-001")).not.toBeInTheDocument();
    });
    // Two calls: the initial mount fetch, and the refetch triggered by
    // useReviewsData's transitionMutation.onSuccess -> refreshList().
    expect(requirementsModule.requirementsApi.list).toHaveBeenCalledTimes(2);
  });
});
