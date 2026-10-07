/**
 * Issue #1193 — aggregate pending count + "other types" transparency.
 *
 * Regression: the Reviews page defaulted its type filter to `requirement`. On a
 * workspace whose 68 open approvals were spread across other types, the queue
 * rendered "No requirements pending review" with no indication that anything
 * was waiting anywhere. The fix consumes the existing backend aggregate
 * (`GET /api/v1/reviews/`, `ReviewsPendingView`) and surfaces both the total
 * and how many of those sit outside the selected type.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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
// The aggregate wrapper is the unit under test at the component level: stub it
// so the badge/hint behaviour is deterministic without a live backend.
vi.mock("../../api/reviews", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/reviews")>();
  return {
    ...actual,
    reviewsApi: { listPendingCount: vi.fn() },
  };
});
vi.mock("react-i18next", () => {
  // Interpolate `count` so the badge/hint text carries the number under test.
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string => {
    if (typeof fallbackOrOptions === "string") return fallbackOrOptions;
    const count = (fallbackOrOptions ?? {}).count;
    return count === undefined ? key : `${key}:${String(count)}`;
  };
  return { useTranslation: () => ({ t }) };
});

import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";
import { reviewsApi } from "../../api/reviews";

import ReviewsView from "./ReviewsView";

const WS = { id: "ws-agg-001", name: "Aggregate WS", preset: "extended" };

const renderView = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReviewsView />
    </QueryClientProvider>,
  );
};

/**
 * Route the aggregate count the way the backend answers it: the workspace-wide
 * call (no artifact type) returns `total`, the type-narrowed call returns
 * `perType`.
 */
function routeCounts(total: number, perType: number): void {
  vi.mocked(reviewsApi.listPendingCount).mockImplementation(
    async (_workspaceId: string, artifactType?: string) =>
      artifactType === undefined ? total : perType,
  );
}

/** Calls to the workspace-wide aggregate (no artifact type). */
function workspaceWideCalls(): number {
  return vi
    .mocked(reviewsApi.listPendingCount)
    .mock.calls.filter((call) => call.length === 1).length;
}

describe("ReviewsView — aggregate pending count (#1193)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: WS,
    } as never);
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as never);
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue(
      { current_state: null, states: [], allowed_transitions: [] } as never,
    );
  });

  it("shows the workspace-wide total and the other-types hint when the default type is empty", async () => {
    // The exact reported scenario: 68 open approvals, none of them requirements.
    routeCounts(68, 0);

    renderView();

    await waitFor(() => {
      expect(screen.getByTestId("reviews-total-pending")).toHaveTextContent(
        "68",
      );
    });
    // The queue is genuinely empty for the selected type...
    expect(screen.getByTestId("reviews-empty")).toBeInTheDocument();
    // ...but no longer looks like the workspace has nothing to approve.
    expect(screen.getByTestId("reviews-other-types-hint")).toHaveTextContent(
      "otherTypesHint",
    );
  });

  it("still shows the total when the selected type has hits (hint reports the remainder)", async () => {
    routeCounts(68, 1);
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: "req-agg-1",
          workspace_id: WS.id,
          title: "Requirement in review",
          description: "",
          status: "in_review",
          version: 1,
          uid: "SyReq-A1",
        },
      ],
    } as never);

    renderView();

    await waitFor(() => {
      expect(screen.getByTestId("reviews-total-pending")).toHaveTextContent(
        "68",
      );
    });
    expect(screen.getByTestId("reviews-other-types-hint")).toBeInTheDocument();
    expect(screen.queryByTestId("reviews-empty")).toBeNull();
  });

  it("hides the badge and hint when nothing is pending anywhere", async () => {
    routeCounts(0, 0);

    renderView();

    await waitFor(() => {
      expect(screen.getByTestId("reviews-empty")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("reviews-total-pending")).toBeNull();
    expect(screen.queryByTestId("reviews-other-types-hint")).toBeNull();
  });

  it("degrades quietly when the aggregate count fails (no error banner for a badge)", async () => {
    vi.mocked(reviewsApi.listPendingCount).mockRejectedValue(
      new Error("aggregate unavailable"),
    );

    renderView();

    await waitFor(() => {
      expect(screen.getByTestId("reviews-empty")).toBeInTheDocument();
    });
    // The queue's own error state stays clean; the optional badge just vanishes.
    expect(screen.queryByTestId("reviews-list-error")).toBeNull();
    expect(screen.queryByTestId("reviews-total-pending")).toBeNull();
  });

  it("refetches the aggregate count after a successful approve (#1193)", async () => {
    // The badge and the "other types" hint are counts over the very queue a
    // transition just changed. `refreshList()` must invalidate both aggregate
    // keys — otherwise an approval leaves the badge advertising a decision that
    // is already made.
    routeCounts(1, 1);
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: "req-agg-approve",
          workspace_id: WS.id,
          title: "Approve me",
          description: "",
          status: "in_review",
          version: 1,
          uid: "SyReq-A1",
        },
      ],
    } as never);
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue({
      current_state: "in_review",
      states: ["draft", "in_review", "approved"],
      allowed_transitions: [
        {
          target_state: "approved",
          requires_change_reason: false,
          signature_gate: false,
        },
        {
          target_state: "draft",
          requires_change_reason: false,
          signature_gate: false,
        },
      ],
    } as never);
    vi.mocked(requirementsModule.requirementsApi.transition).mockResolvedValue({
      id: "req-agg-approve",
      previous_state: "in_review",
      new_state: "approved",
      requirement: {},
    } as never);

    const user = userEvent.setup();
    renderView();

    const item = await screen.findByTestId("review-list-item-req-agg-approve");
    // Settle the initial aggregate fetch before acting, so the post-action
    // count cannot be mistaken for the first one.
    await waitFor(() => expect(workspaceWideCalls()).toBe(1));

    await user.click(item);
    const approve = await screen.findByTestId("review-approve-btn");
    await waitFor(() => expect(approve).not.toBeDisabled());
    await user.click(approve);

    await waitFor(() =>
      expect(requirementsModule.requirementsApi.transition).toHaveBeenCalled(),
    );
    await waitFor(() => expect(workspaceWideCalls()).toBeGreaterThanOrEqual(2));
  });
});
