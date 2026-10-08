/**
 * ReviewsView — ADR-019 / WP6 integration test.
 *
 * O6 chose an extra mode on the existing ReviewsView over a dedicated page.
 * This test pins that integration: toggling the suggestions mode swaps the
 * review queue for the persisted suggestion inbox, and switching back restores
 * the historical queue. The queue data fetches are stubbed exactly like the
 * existing ReviewsView component tests.
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
vi.mock("../../api/reviews", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/reviews")>();
  return { ...actual, reviewsApi: { listPendingCount: vi.fn(async () => 0) } };
});
vi.mock("../../api/suggestions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/suggestions")>();
  return {
    ...actual,
    listSuggestions: vi.fn(),
    acceptSuggestion: vi.fn(),
    rejectSuggestion: vi.fn(),
  };
});
vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";
import { listSuggestions } from "../../api/suggestions";
import ReviewsView from "./ReviewsView";

const WS = { id: "ws-mix-001", name: "Mixed WS", preset: "standard" };

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

describe("ReviewsView — suggestions mode (O6)", () => {
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
    vi.mocked(listSuggestions).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: "sug-i1",
          kind: "artifact_create",
          status: "open",
          producer: "AiDerivationService",
          proposed_by: "BenchAgent",
          proposed_at: "2026-10-08T09:00:00Z",
          decided_by: null,
          decided_at: null,
          target_item_type: "Requirement",
          target_item_id: null,
          payload: {},
          workspace_id: WS.id,
          created_at: "2026-10-08T09:00:00Z",
        },
      ],
    } as never);
  });

  it("swaps the review queue for the suggestion inbox and back", async () => {
    const user = userEvent.setup();
    renderView();

    // Historical queue is the default surface.
    await screen.findByTestId("reviews-type-select");

    await user.click(screen.getByTestId("reviews-suggestions-mode-checkbox"));

    const inbox = await screen.findByTestId("suggestions-inbox");
    expect(inbox).toBeInTheDocument();
    expect(await screen.findByTestId("suggestion-row-sug-i1")).toBeInTheDocument();
    // The review-specific type filter is gone while the inbox is shown.
    expect(screen.queryByTestId("reviews-type-select")).not.toBeInTheDocument();
    expect(listSuggestions).toHaveBeenCalled();

    // Switching the mode back restores the queue.
    await user.click(screen.getByTestId("reviews-suggestions-mode-checkbox"));
    await waitFor(() => {
      expect(screen.queryByTestId("suggestions-inbox")).not.toBeInTheDocument();
    });
    expect(await screen.findByTestId("reviews-type-select")).toBeInTheDocument();
  });
});
