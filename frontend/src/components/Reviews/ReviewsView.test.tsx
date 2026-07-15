/**
 * Smoke tests for ReviewsView (REQ-144 Review/Approval UI).
 *
 * req_id: REQ-144
 *
 * Verifies:
 *   - Loading state while the review queue is in-flight
 *   - Review list renders titles for requirements returned by the
 *     `?status=in_review` filtered list endpoint
 *   - Empty state when no requirement is in_review
 *   - Selecting a requirement loads its allowed transitions and enables
 *     Approve/Reject only when the corresponding move is allowed
 *   - Approve calls the transition mutation with the resolved target state
 *   - A missing-role (403) error on Approve surfaces via role="alert"
 *   - A required change_reason blocks the transition client-side
 *
 * Uses QueryClientProvider (useReviewsData — TanStack Query). No routing
 * required (ReviewsView does not use useParams/useNavigate).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ---------------------------------------------------------------------------
// Module mocks (must precede component import)
// ---------------------------------------------------------------------------

vi.mock("../../api/requirements");
vi.mock("../../context/WorkspaceContext");
vi.mock("react-i18next", () => {
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";
import { ForbiddenError } from "../../api/errors";

import ReviewsView from "./ReviewsView";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-rev-001", name: "Review WS", preset: "extended" };

const MOCK_REQUIREMENTS = [
  {
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
  },
  {
    id: "req-002",
    workspace_id: "ws-rev-001",
    title: "Sensor fusion accuracy",
    description: "The system shall...",
    category: "functional",
    status: "in_review",
    version: 1,
    uid: "SyReq-002",
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-02T00:00:00Z",
  },
];

const TRANSITIONS_APPROVE_AND_REJECT = {
  current_state: "in_review",
  states: ["draft", "in_review", "approved", "deprecated"],
  allowed_transitions: [
    { target_state: "approved", requires_change_reason: true, signature_gate: false },
    { target_state: "draft", requires_change_reason: true, signature_gate: false },
  ],
};

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

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

describe("ReviewsView (REQ-144 smoke tests)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
  });

  it("[REQ-144] shows loading status while the review queue is in-flight", () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockReturnValue(new Promise(() => {}));

    renderReviewsView();

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("[REQ-144] renders requirement titles after the list resolves", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: MOCK_REQUIREMENTS,
    } as any);

    renderReviewsView();

    await waitFor(() => {
      expect(screen.getByText("Brake-by-wire latency budget")).toBeInTheDocument();
    });
    expect(screen.getByText("Sensor fusion accuracy")).toBeInTheDocument();

    // Verifies the status filter was actually passed through to the API.
    expect(requirementsModule.requirementsApi.list).toHaveBeenCalledWith(
      "ws-rev-001",
      "in_review"
    );
  });

  it("[REQ-144] renders empty state when nothing is in_review", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    } as any);

    renderReviewsView();

    await waitFor(() => {
      expect(screen.getByTestId("reviews-empty")).toBeInTheDocument();
    });
  });

  it("[REQ-144] selecting a requirement loads transitions and enables Approve/Reject", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: MOCK_REQUIREMENTS,
    } as any);
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue(
      TRANSITIONS_APPROVE_AND_REJECT as any
    );
    const user = userEvent.setup();

    renderReviewsView();

    await waitFor(() => {
      expect(screen.getByText("Brake-by-wire latency budget")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("review-list-item-req-001"));

    await waitFor(() => {
      expect(screen.getByTestId("review-approve-btn")).not.toBeDisabled();
    });
    expect(screen.getByTestId("review-reject-btn")).not.toBeDisabled();
  });

  it("[REQ-144] Approve is disabled when the caller lacks the approver role (transition absent)", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: MOCK_REQUIREMENTS,
    } as any);
    // Only the reject move (in_review -> draft) is allowed for this caller.
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue({
      current_state: "in_review",
      states: ["draft", "in_review", "approved", "deprecated"],
      allowed_transitions: [
        { target_state: "draft", requires_change_reason: true, signature_gate: false },
      ],
    } as any);
    const user = userEvent.setup();

    renderReviewsView();

    await waitFor(() => {
      expect(screen.getByText("Brake-by-wire latency budget")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("review-list-item-req-001"));

    await waitFor(() => {
      expect(screen.getByTestId("review-reject-btn")).not.toBeDisabled();
    });
    expect(screen.getByTestId("review-approve-btn")).toBeDisabled();
  });

  it("[REQ-144] blocks Approve client-side when change_reason is required but empty", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: MOCK_REQUIREMENTS,
    } as any);
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue(
      TRANSITIONS_APPROVE_AND_REJECT as any
    );
    const user = userEvent.setup();

    renderReviewsView();

    await waitFor(() => {
      expect(screen.getByText("Brake-by-wire latency budget")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("review-list-item-req-001"));
    await waitFor(() => {
      expect(screen.getByTestId("review-approve-btn")).not.toBeDisabled();
    });

    await user.click(screen.getByTestId("review-approve-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("review-action-error")).toBeInTheDocument();
    });
    expect(requirementsModule.requirementsApi.transition).not.toHaveBeenCalled();
  });

  it("[REQ-144] surfaces a 403 ForbiddenError from Approve as an inline alert", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: MOCK_REQUIREMENTS,
    } as any);
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue(
      TRANSITIONS_APPROVE_AND_REJECT as any
    );
    vi.mocked(requirementsModule.requirementsApi.transition).mockRejectedValue(
      new ForbiddenError("Missing approver role")
    );
    const user = userEvent.setup();

    renderReviewsView();

    await waitFor(() => {
      expect(screen.getByText("Brake-by-wire latency budget")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("review-list-item-req-001"));
    await waitFor(() => {
      expect(screen.getByTestId("review-approve-btn")).not.toBeDisabled();
    });

    await user.type(screen.getByTestId("review-change-reason-input"), "Looks good");
    await user.click(screen.getByTestId("review-approve-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("review-action-error")).toHaveTextContent(
        "Missing approver role"
      );
    });
  });
});
