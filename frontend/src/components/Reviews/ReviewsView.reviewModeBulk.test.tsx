/**
 * Bulk approve/reject in the REGULAR review queue (issue #1196).
 *
 * Before this change the review queue had no multi-select at all: the only
 * bulk affordance lived in the AI-proposals mode, where a row checkbox plus a
 * single "Confirm selected" button called `confirmProposal` per item. Clearing
 * a queue of 30 pending approvals meant 30 detail-pane round trips.
 *
 * What these tests pin, driven the way a human drives it (tick rows, type one
 * reason, click a button — with NOTHING selected for detail):
 *   - every review-mode row exposes a checkbox (`review-item-checkbox`)
 *   - a selection reveals the review-mode bulk controls
 *   - one click approves (or rejects) every selected item, resolving the
 *     target from the item itself
 *   - a partial failure never aborts the run: the report still carries both
 *     counts, the items that worked are done, the failed one is named
 *   - the reason-gated targets behave: a missing reason fails that item only
 *   - the proposals mode keeps its historical DOM and behaviour
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

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
// Same stub as the other Reviews suites: unmocked it points the module at the
// real axios client in jsdom.
vi.mock("../../api/reviews", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/reviews")>();
  return { ...actual, reviewsApi: { listPendingCount: vi.fn() } };
});

// A `t` that resolves the German labels this change introduces (plus the
// existing ones it reuses) and interpolates `{{count}}`. The report sentence
// is asserted verbatim, so the stub must produce real text rather than keys.
const LABELS: Record<string, string> = {
  "reviews.approve": "Freigeben",
  "reviews.reject": "Ablehnen",
  "reviews.changeReasonLabel": "Begründung",
  "reviews.changeReasonPlaceholder": "Begründung eingeben",
  "reviews.changeReasonRequired":
    "Für diesen Übergang ist eine Begründung erforderlich.",
  "reviews.transitionUnavailable":
    "Dieser Übergang ist nicht verfügbar (Rolle oder Workflow-Konfiguration).",
  "reviews.bulkApproveDone": "{{count}} freigegeben",
  "reviews.bulkRejectDone": "{{count}} abgelehnt",
  "reviews.bulkFailed": "{{count}} fehlgeschlagen",
  "workflow.proposal.bulkConfirm": "Auswahl bestätigen",
  "workflow.proposal.bulkConfirmDone": "{{count}} Vorschläge bestätigt",
  "workflow.proposal.bulkConfirmFailed": "{{count}} Vorschläge nicht bestätigt",
};
vi.mock("react-i18next", () => {
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string => {
    if (typeof fallbackOrOptions === "string") return fallbackOrOptions;
    let value = LABELS[key] ?? key;
    if (fallbackOrOptions && typeof fallbackOrOptions === "object") {
      for (const [name, raw] of Object.entries(fallbackOrOptions)) {
        value = value.split(`{{${name}}}`).join(String(raw));
      }
    }
    return value;
  };
  return { useTranslation: () => ({ t }) };
});

import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";
import { workflowTransitionsApi } from "../../api/workflow-transitions";

import ReviewsView from "./ReviewsView";

const WS = { id: "ws-rev-1196", name: "Review WS", preset: "standard" };

const IN_REVIEW_REQUIREMENTS = [
  {
    id: "req-r1",
    workspace_id: WS.id,
    title: "Brake-by-wire latency budget",
    description: "The system shall ...",
    category: "functional",
    status: "in_review",
    version: 2,
    uid: "SyReq-R1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "req-r2",
    workspace_id: WS.id,
    title: "Sensor fusion accuracy",
    description: "The system shall ...",
    category: "functional",
    status: "in_review",
    version: 1,
    uid: "SyReq-R2",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
];

/**
 * What the backend returns for a requirement sitting in `in_review`: the
 * review queue's real shape, where BOTH moves out of the state are
 * reason-gated (the fixture the REQ-144 smoke suite already uses). This is
 * why the bulk targets resolve through `REVIEW_ACTION_CONFIG` and not through
 * "the transition that needs no reason".
 */
const REVIEW_TRANSITIONS = {
  current_state: "in_review",
  states: ["draft", "in_review", "approved", "deprecated"],
  allowed_transitions: [
    { target_state: "approved", requires_change_reason: true, signature_gate: false },
    { target_state: "draft", requires_change_reason: true, signature_gate: false },
  ],
};

/** The proposals-queue fixture, unchanged from the #1193 suites. */
const PROPOSED_REQUIREMENTS = [
  {
    id: "req-p1",
    workspace_id: WS.id,
    title: "Agent-proposed requirement",
    description: "The system shall ...",
    category: "functional",
    status: "proposed",
    version: 1,
    uid: "SyReq-P1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
];
const PROPOSED_TRANSITIONS = {
  current_state: "proposed",
  states: ["draft", "proposed", "in_review", "approved"],
  allowed_transitions: [
    { target_state: "draft", requires_change_reason: false, signature_gate: false },
    { target_state: "rejected", requires_change_reason: true, signature_gate: false },
  ],
};

const page = (results: unknown[]): unknown => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

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

/** Both queues are served from one mock, keyed by the status the queue asks for. */
const serveBothQueues = (): void => {
  vi.mocked(requirementsModule.requirementsApi.list).mockImplementation(
    async (_workspaceId: string, status: string) =>
      (status === "proposed" ? page(PROPOSED_REQUIREMENTS) : page(IN_REVIEW_REQUIREMENTS)) as never,
  );
};

const tickRows = async (user: ReturnType<typeof userEvent.setup>, count: number): Promise<void> => {
  const boxes = await screen.findAllByTestId("review-item-checkbox");
  for (let i = 0; i < count && i < boxes.length; i += 1) {
    await user.click(boxes[i]);
  }
};

describe("bulk approve/reject in the review queue (#1196)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: WS,
    } as never);
    serveBothQueues();
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue(
      REVIEW_TRANSITIONS as never,
    );
    vi.mocked(workflowTransitionsApi.transition).mockResolvedValue({} as never);
  });

  it("renders a selection checkbox for every row in review mode", async () => {
    renderView();

    await waitFor(() => {
      expect(screen.getByText("Brake-by-wire latency budget")).toBeInTheDocument();
    });

    expect(screen.getAllByTestId("review-item-checkbox")).toHaveLength(
      IN_REVIEW_REQUIREMENTS.length,
    );
    // No bulk control before anything is selected.
    expect(screen.queryByTestId("reviews-bulk-confirm-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reviews-bulk-reject-btn")).not.toBeInTheDocument();
  });

  it("a selection in review mode reveals both bulk actions", async () => {
    const user = userEvent.setup();
    renderView();

    await tickRows(user, 1);

    expect(await screen.findByTestId("reviews-bulk-confirm-btn")).toHaveTextContent(
      "Freigeben (1)",
    );
    expect(screen.getByTestId("reviews-bulk-reject-btn")).toHaveTextContent(
      "Ablehnen (1)",
    );
    // One reason field for the whole batch, not one per item.
    expect(screen.getByTestId("reviews-bulk-reason-input")).toBeInTheDocument();
  });

  it("approves every selected item in one click", async () => {
    const user = userEvent.setup();
    renderView();

    await tickRows(user, 2);
    await user.type(screen.getByTestId("reviews-bulk-reason-input"), "gate passed");
    await user.click(screen.getByTestId("reviews-bulk-confirm-btn"));

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledTimes(2);
    });

    // The target is resolved per item, not from the (empty) detail pane.
    expect(workflowTransitionsApi.getTransitions).toHaveBeenCalledWith(
      "requirement",
      "req-r1",
    );
    expect(workflowTransitionsApi.getTransitions).toHaveBeenCalledWith(
      "requirement",
      "req-r2",
    );
    for (const id of ["req-r1", "req-r2"]) {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledWith(
        "requirement",
        id,
        "approved",
        "gate passed",
      );
    }
    expect(screen.getByTestId("reviews-bulk-confirm-result")).toHaveTextContent(
      "2 freigegeben",
    );
    expect(
      screen.queryByTestId("reviews-bulk-confirm-error"),
    ).not.toBeInTheDocument();
  });

  it("rejects the selection to the configured reject target with the same reason", async () => {
    const user = userEvent.setup();
    renderView();

    await tickRows(user, 2);
    await user.type(screen.getByTestId("reviews-bulk-reason-input"), "incomplete");
    await user.click(screen.getByTestId("reviews-bulk-reject-btn"));

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledTimes(2);
    });
    for (const id of ["req-r1", "req-r2"]) {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledWith(
        "requirement",
        id,
        "draft",
        "incomplete",
      );
    }
    expect(screen.getByTestId("reviews-bulk-confirm-result")).toHaveTextContent(
      "2 abgelehnt",
    );
  });

  it("keeps the run going on a partial failure and reports both counts", async () => {
    const user = userEvent.setup();
    vi.mocked(workflowTransitionsApi.transition)
      .mockResolvedValueOnce({} as never)
      .mockRejectedValueOnce(new Error("409 conflict") as never);

    renderView();

    await tickRows(user, 2);
    await user.type(screen.getByTestId("reviews-bulk-reason-input"), "gate passed");
    await user.click(screen.getByTestId("reviews-bulk-confirm-btn"));

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledTimes(2);
    });

    const result = screen.getByTestId("reviews-bulk-confirm-result");
    expect(result).toHaveTextContent("1 freigegeben, 1 fehlgeschlagen");
    // The cause of the failed item is surfaced, not swallowed.
    expect(screen.getByTestId("reviews-bulk-confirm-error")).toHaveTextContent(
      "409 conflict",
    );
    // The selection is consumed either way; a second click cannot re-run it.
    expect(screen.queryByTestId("reviews-bulk-confirm-btn")).not.toBeInTheDocument();
  });

  it("fails an item whose target is not offered, without aborting the run", async () => {
    const user = userEvent.setup();
    // The second item is no longer in a state that can be approved.
    vi.mocked(workflowTransitionsApi.getTransitions).mockImplementation(
      async (_type: string, id: string) =>
        (id === "req-r2"
          ? { ...REVIEW_TRANSITIONS, allowed_transitions: [] }
          : REVIEW_TRANSITIONS) as never,
    );

    renderView();

    await tickRows(user, 2);
    await user.type(screen.getByTestId("reviews-bulk-reason-input"), "gate passed");
    await user.click(screen.getByTestId("reviews-bulk-confirm-btn"));

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledTimes(1);
    });
    expect(workflowTransitionsApi.transition).toHaveBeenCalledWith(
      "requirement",
      "req-r1",
      "approved",
      "gate passed",
    );
    expect(workflowTransitionsApi.transition).not.toHaveBeenCalledWith(
      "requirement",
      "req-r2",
      "approved",
      "gate passed",
    );
    expect(screen.getByTestId("reviews-bulk-confirm-result")).toHaveTextContent(
      "1 freigegeben, 1 fehlgeschlagen",
    );
    expect(screen.getByTestId("reviews-bulk-confirm-error")).toHaveTextContent(
      "Dieser Übergang ist nicht verfügbar",
    );
  });

  it("rejects nothing when the batch reason is missing but the target needs one", async () => {
    const user = userEvent.setup();
    renderView();

    await tickRows(user, 2);
    // No reason typed: both targets are reason-gated in this graph.
    await user.click(screen.getByTestId("reviews-bulk-reject-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("reviews-bulk-confirm-result")).toBeInTheDocument();
    });

    // Nothing was POSTed — the gate is client-side, per item, before any call.
    expect(workflowTransitionsApi.transition).not.toHaveBeenCalled();
    expect(screen.getByTestId("reviews-bulk-confirm-result")).toHaveTextContent(
      "0 abgelehnt, 2 fehlgeschlagen",
    );
    expect(screen.getByTestId("reviews-bulk-confirm-error")).toHaveTextContent(
      "Für diesen Übergang ist eine Begründung erforderlich.",
    );
  });

  it("keeps the review-mode row click out of the checkbox", async () => {
    const user = userEvent.setup();
    renderView();

    await tickRows(user, 1);

    // A tick selects for bulk; it must not open the detail pane.
    expect(screen.queryByTestId("review-detail")).not.toBeInTheDocument();
    expect(screen.getByTestId("review-detail-empty")).toBeInTheDocument();
  });

  it("keeps the typed batch reason when a row is opened for detail", async () => {
    const user = userEvent.setup();
    renderView();

    await tickRows(user, 1);
    await user.type(screen.getByTestId("reviews-bulk-reason-input"), "gate passed");
    // `handleSelect` resets the detail pane's own reason field — the batch
    // reason must survive that, or inspecting a row mid-selection silently
    // drops the reviewer's text.
    await user.click(screen.getByTestId("review-list-item-req-r1"));

    expect(screen.getByTestId("review-detail")).toBeInTheDocument();
    expect(screen.getByTestId("reviews-bulk-reason-input")).toHaveValue(
      "gate passed",
    );
    expect(screen.getByTestId("reviews-bulk-confirm-btn")).toBeInTheDocument();
  });
});

describe("proposals bulk confirm stays unchanged (#1196 regression guard)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: WS,
    } as never);
    serveBothQueues();
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue(
      PROPOSED_TRANSITIONS as never,
    );
    vi.mocked(workflowTransitionsApi.transition).mockResolvedValue({} as never);
  });

  it("keeps the proposals test ids, the single button and the reason-free target", async () => {
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByTestId("reviews-queue-mode-checkbox"));

    // The review-mode affordance is not rendered in proposals mode.
    expect(screen.queryByTestId("review-item-checkbox")).not.toBeInTheDocument();
    const proposalBoxes = await screen.findAllByTestId(/^review-select-/);
    expect(proposalBoxes).toHaveLength(1);

    await user.click(proposalBoxes[0]);
    const bulkButton = await screen.findByTestId("reviews-bulk-confirm-btn");
    // One button only, labelled as before, and no batch reason input.
    expect(bulkButton).toHaveTextContent("Auswahl bestätigen (1)");
    expect(screen.queryByTestId("reviews-bulk-reject-btn")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("reviews-bulk-reason-input"),
    ).not.toBeInTheDocument();

    await user.click(bulkButton);

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledWith(
        "requirement",
        "req-p1",
        "draft",
      );
    });
    expect(workflowTransitionsApi.transition).toHaveBeenCalledTimes(1);
    // The historical report sentence is untouched.
    expect(screen.getByTestId("reviews-bulk-confirm-result")).toHaveTextContent(
      "1 Vorschläge bestätigt",
    );
  });
});
