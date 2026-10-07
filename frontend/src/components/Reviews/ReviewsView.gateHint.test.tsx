/**
 * GitHub #1192 — the approval gate must be explained BEFORE the click.
 *
 * Rule 5 (`workflow.precondition_rules.check_mandatory_fields`) refuses an
 * approval while the active preset's mandatory fields are empty, but the move
 * still appears in `allowed_transitions` — so the "Freigeben" button looked
 * actionable and only a 400 after the click revealed why. ReviewsView now
 * states the gate up front, next to the actions; the ArtifactForm is where the
 * concrete required fields are marked (see ArtifactForm gate-required tests).
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
// Keep the aggregate count query deterministic and offline.
vi.mock("../../api/reviews", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/reviews")>();
  return {
    ...actual,
    reviewsApi: { listPendingCount: vi.fn(async () => 0) },
  };
});
vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>
  ): string =>
    typeof fallbackOrOptions === "string" ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";

import ReviewsView from "./ReviewsView";

const WS = { id: "ws-gate-002", name: "Gate WS", preset: "standard" };

const IN_REVIEW_REQ = {
  id: "req-gate-1",
  workspace_id: WS.id,
  title: "Brake-by-wire latency budget",
  description: "The system shall...",
  status: "in_review",
  version: 2,
  uid: "SyReq-GATE1",
};

const renderView = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ReviewsView />
    </QueryClientProvider>
  );
};

describe("ReviewsView approval gate hint (#1192)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: WS,
    } as never);
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [IN_REVIEW_REQ],
    } as never);
  });

  it("explains the approval gate next to the actions before the click", async () => {
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue({
      current_state: "in_review",
      states: ["draft", "in_review", "approved"],
      allowed_transitions: [
        { target_state: "approved", requires_change_reason: true, signature_gate: false },
        { target_state: "draft", requires_change_reason: true, signature_gate: false },
      ],
    } as never);
    const user = userEvent.setup();

    renderView();

    await user.click(await screen.findByTestId("review-list-item-req-gate-1"));
    await waitFor(() => {
      expect(screen.getByTestId("review-approve-btn")).not.toBeDisabled();
    });

    // Explained up front, before any click can 400: the hint is present and
    // carries copy (the i18n key in this mocked environment).
    const hint = screen.getByTestId("review-gate-hint");
    expect(hint).toBeInTheDocument();
    expect(hint).not.toBeEmptyDOMElement();
    // The action stays offered — the explanation is the mechanism, not a
    // disabled button, because the transition itself is still valid.
    const approve = screen.getByTestId("review-approve-btn");
    expect(approve).not.toBeDisabled();
    // ...and the explanation is programmatically associated with the action,
    // so it reaches assistive tech and not only sighted users.
    expect(approve).toHaveAttribute("aria-describedby", "review-gate-hint");
  });

  it("does not show the gate hint when approval is not offered at all", async () => {
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue({
      current_state: "in_review",
      states: ["draft", "in_review", "approved"],
      allowed_transitions: [
        { target_state: "draft", requires_change_reason: true, signature_gate: false },
      ],
    } as never);
    const user = userEvent.setup();

    renderView();

    await user.click(await screen.findByTestId("review-list-item-req-gate-1"));
    await waitFor(() => {
      expect(screen.getByTestId("review-reject-btn")).not.toBeDisabled();
    });

    expect(screen.queryByTestId("review-gate-hint")).not.toBeInTheDocument();
    expect(screen.getByTestId("review-approve-btn")).toBeDisabled();
  });
});
