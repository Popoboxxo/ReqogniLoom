/**
 * Issue #1193 — a rejected approval must say why.
 *
 * The review queue had two silent failure paths:
 *
 *   1. `bulkConfirm` swallowed every rejection (`catch {}`) and reported only
 *      a bare "N failed" count;
 *   2. `confirmProposal` never forwarded a `change_reason`, so a server 400 on
 *      the proposals bulk path was invisible.
 *
 * These tests drive the real component and assert the cause reaches the user
 * (single Approve inline alert; bulk confirm inline alert) and that a typed
 * reason is actually sent.
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
  return {
    ...actual,
    reviewsApi: { listPendingCount: vi.fn(async () => 0) },
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
import { workflowTransitionsApi } from "../../api/workflow-transitions";

import ReviewsView, { bulkConfirm } from "./ReviewsView";

const WS = { id: "ws-gate-001", name: "Gate WS", preset: "extended" };

const IN_REVIEW_REQ = {
  id: "req-g1",
  workspace_id: WS.id,
  title: "Brake-by-wire latency budget",
  description: "The system shall...",
  status: "in_review",
  version: 2,
  uid: "SyReq-G1",
};

const TRANSITIONS_APPROVE_AND_REJECT = {
  current_state: "in_review",
  states: ["draft", "in_review", "approved"],
  allowed_transitions: [
    { target_state: "approved", requires_change_reason: true, signature_gate: false },
    { target_state: "draft", requires_change_reason: true, signature_gate: false },
  ],
};

const PROPOSED_REQ = {
  id: "req-p1",
  workspace_id: WS.id,
  title: "Agent-proposed requirement",
  description: "AI generated.",
  status: "proposed",
  version: 1,
  uid: "SyReq-P1",
};

const PROPOSED_TRANSITIONS = {
  current_state: "proposed",
  states: ["draft", "proposed", "rejected"],
  allowed_transitions: [
    { target_state: "draft", requires_change_reason: false, signature_gate: false },
    { target_state: "rejected", requires_change_reason: true, signature_gate: false },
  ],
};

/** A canonical DRF 400 envelope, as `apiFetch` throws it. */
const CHANGE_REASON_400 = {
  error: {
    code: "VALIDATION_ERROR",
    message: "Validation failed",
    details: [
      {
        field: "change_reason",
        errors: ["A reason is required for this transition."],
      },
    ],
  },
};

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

describe("ReviewsView — reason gate / error surfacing (#1193)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: WS,
    } as never);
    vi.mocked(requirementsModule.requirementsApi.getTransitions).mockResolvedValue(
      TRANSITIONS_APPROVE_AND_REJECT as never,
    );
  });

  it("surfaces a server 400 (change_reason) from single Approve as an inline alert", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [IN_REVIEW_REQ],
    } as never);
    vi.mocked(requirementsModule.requirementsApi.transition).mockRejectedValue(
      CHANGE_REASON_400,
    );
    const user = userEvent.setup();

    renderView();

    await user.click(await screen.findByTestId("review-list-item-req-g1"));
    await waitFor(() => {
      expect(screen.getByTestId("review-approve-btn")).not.toBeDisabled();
    });

    await user.type(screen.getByTestId("review-change-reason-input"), "looks good");
    await user.click(screen.getByTestId("review-approve-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("review-action-error")).toHaveTextContent(
        "A reason is required for this transition.",
      );
    });
    expect(requirementsModule.requirementsApi.transition).toHaveBeenCalled();
  });

  it("surfaces the cause of a failed bulk confirmation instead of swallowing it", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockImplementation(
      async (_workspaceId, status) =>
        ({
          count: status === "proposed" ? 1 : 0,
          next: null,
          previous: null,
          results: status === "proposed" ? [PROPOSED_REQ] : [],
        }) as never,
    );
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue(
      PROPOSED_TRANSITIONS as never,
    );
    vi.mocked(workflowTransitionsApi.transition).mockRejectedValue(
      CHANGE_REASON_400,
    );
    const user = userEvent.setup();

    renderView();

    await user.click(await screen.findByTestId("reviews-queue-mode-checkbox"));
    await user.click(await screen.findByTestId("review-select-req-p1"));
    await user.click(await screen.findByTestId("reviews-bulk-confirm-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("reviews-bulk-confirm-error")).toHaveTextContent(
        "A reason is required for this transition.",
      );
    });
    // The summary count is still reported alongside the cause.
    expect(screen.getByTestId("reviews-bulk-confirm-result")).toBeInTheDocument();
  });

  it("forwards a typed reason to the bulk confirmation instead of dropping it", async () => {
    vi.mocked(requirementsModule.requirementsApi.list).mockImplementation(
      async (_workspaceId, status) =>
        ({
          count: status === "proposed" ? 1 : 0,
          next: null,
          previous: null,
          results: status === "proposed" ? [PROPOSED_REQ] : [],
        }) as never,
    );
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue(
      PROPOSED_TRANSITIONS as never,
    );
    vi.mocked(workflowTransitionsApi.transition).mockResolvedValue({} as never);
    const user = userEvent.setup();

    renderView();

    await user.click(await screen.findByTestId("reviews-queue-mode-checkbox"));
    // Open the detail pane so the reason textarea is available, type a reason
    // (handleSelect resets the field, so this must come after the click)...
    await user.click(await screen.findByTestId("review-list-item-req-p1"));
    await user.type(
      await screen.findByTestId("review-change-reason-input"),
      "reviewed and ok",
    );
    // ...then tick the row and confirm the selection.
    await user.click(screen.getByTestId("review-select-req-p1"));
    await user.click(screen.getByTestId("reviews-bulk-confirm-btn"));

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledWith(
        "requirement",
        "req-p1",
        "draft",
        "reviewed and ok",
      );
    });
  });
});

describe("bulkConfirm (#1193)", () => {
  it("reports each failure's cause via the optional onError callback", async () => {
    const errors: Array<[string, string]> = [];
    const confirmOne = vi
      .fn()
      .mockRejectedValueOnce(new Error("400 bad request"))
      .mockResolvedValueOnce(undefined);

    const result = await bulkConfirm(["a", "b"], confirmOne, (id, error) => {
      errors.push([id, String(error)]);
    });

    expect(result).toEqual({ confirmed: ["b"], failed: ["a"] });
    expect(errors).toEqual([["a", "Error: 400 bad request"]]);
  });

  it("stays backward compatible without the callback", async () => {
    const confirmOne = vi.fn().mockRejectedValueOnce(new Error("nope"));

    const result = await bulkConfirm(["a"], confirmOne);

    expect(result).toEqual({ confirmed: [], failed: ["a"] });
  });
});
