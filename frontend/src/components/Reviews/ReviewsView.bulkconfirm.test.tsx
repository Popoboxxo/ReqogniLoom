/**
 * Bulk-confirm from the proposals queue, driven the way a human drives it.
 *
 * Security review M4. `ReviewsView.proposals.test.tsx` unit-tests `bulkConfirm()`
 * with an injected callback, so it never exercised where the target state comes
 * from — which is exactly where the bug was. `APPROVE_TARGET` was derived from
 * the CURRENTLY SELECTED item's `transitions`, but in the real flow (tick
 * checkboxes, click confirm) nothing is selected for detail: `transitions` was
 * `undefined` and the target fell back to the literal `"draft"`, which is not a
 * valid target for most artifact types (adr -> `Draft`, goal/main-goal ->
 * `Entwurf`, risk -> `Identified`, issue -> `Open`). Every bulk-confirm click
 * failed, and no test noticed.
 *
 * These render the component and click the real button with NOTHING selected.
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

import ReviewsView from "./ReviewsView";

const WS = { id: "ws-prop-001", name: "Proposals WS", preset: "extended" };

const PROPOSED_REQUIREMENTS = [
  {
    id: "req-p1",
    workspace_id: WS.id,
    title: "Agent-proposed requirement one",
    description: "The system shall ...",
    category: "functional",
    status: "proposed",
    version: 1,
    uid: "SyReq-P1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "req-p2",
    workspace_id: WS.id,
    title: "Agent-proposed requirement two",
    description: "The system shall ...",
    category: "functional",
    status: "proposed",
    version: 1,
    uid: "SyReq-P2",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
];

/** What the backend returns for an item sitting in `proposed`. */
const PROPOSED_TRANSITIONS = {
  current_state: "proposed",
  states: ["draft", "proposed", "in_review", "approved"],
  allowed_transitions: [
    // confirm -> the graph's own initial state, no change_reason
    {
      target_state: "draft",
      requires_change_reason: false,
      signature_gate: false,
    },
    // discard -> the reject state, change_reason required
    {
      target_state: "rejected",
      requires_change_reason: true,
      signature_gate: false,
    },
  ],
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

describe("bulk-confirm from the proposals queue (M4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: WS,
    } as any);
    vi.mocked(requirementsModule.requirementsApi.list).mockResolvedValue({
      count: PROPOSED_REQUIREMENTS.length,
      next: null,
      previous: null,
      results: PROPOSED_REQUIREMENTS,
    } as any);
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue(
      PROPOSED_TRANSITIONS as any,
    );
    vi.mocked(workflowTransitionsApi.transition).mockResolvedValue({} as any);
  });

  it("resolves the target from each item itself, with nothing selected for detail", async () => {
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByTestId("reviews-queue-mode-checkbox"));

    // Tick both proposals. Deliberately never click a list item — the detail
    // pane stays empty, which is what made `transitions` undefined.
    await user.click(await screen.findByTestId("review-select-req-p1"));
    await user.click(await screen.findByTestId("review-select-req-p2"));
    await user.click(await screen.findByTestId("reviews-bulk-confirm-btn"));

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledTimes(2);
    });

    // Assert the SOURCE, not just the value: the target must be looked up per
    // item. (Asserting only `target_state === "draft"` would pass on the buggy
    // version too, since the old fallback string happened to be "draft".)
    expect(workflowTransitionsApi.getTransitions).toHaveBeenCalledWith(
      "requirement",
      "req-p1",
    );
    expect(workflowTransitionsApi.getTransitions).toHaveBeenCalledWith(
      "requirement",
      "req-p2",
    );
    for (const id of ["req-p1", "req-p2"]) {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledWith(
        "requirement",
        id,
        "draft",
      );
    }
  });

  it("uses a non-draft target when the item's graph says so", async () => {
    // The real M4 failure mode: for adr/goal/risk/issue the confirm target is
    // NOT "draft", so with the old fallback every one of them silently failed.
    vi.mocked(workflowTransitionsApi.getTransitions).mockResolvedValue({
      current_state: "proposed",
      states: ["Entwurf", "proposed", "Freigegeben", "Archiviert"],
      allowed_transitions: [
        {
          target_state: "Entwurf",
          requires_change_reason: false,
          signature_gate: false,
        },
        {
          target_state: "Archiviert",
          requires_change_reason: true,
          signature_gate: false,
        },
      ],
    } as any);

    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByTestId("reviews-queue-mode-checkbox"));
    await user.click(await screen.findByTestId("review-select-req-p1"));
    await user.click(await screen.findByTestId("reviews-bulk-confirm-btn"));

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalledWith(
        "requirement",
        "req-p1",
        "Entwurf",
      );
    });
    expect(workflowTransitionsApi.transition).not.toHaveBeenCalledWith(
      "requirement",
      "req-p1",
      "draft",
    );
  });

  it("never picks the discard transition as the confirm target", async () => {
    // Both moves out of `proposed` come back in the same list; only the one
    // that needs no change_reason is the confirm.
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByTestId("reviews-queue-mode-checkbox"));
    await user.click(await screen.findByTestId("review-select-req-p1"));
    await user.click(await screen.findByTestId("reviews-bulk-confirm-btn"));

    await waitFor(() => {
      expect(workflowTransitionsApi.transition).toHaveBeenCalled();
    });
    expect(workflowTransitionsApi.transition).not.toHaveBeenCalledWith(
      "requirement",
      "req-p1",
      "rejected",
    );
  });

  it("clears a stale bulk result when the queue mode changes", async () => {
    const user = userEvent.setup();
    renderView();

    await user.click(await screen.findByTestId("reviews-queue-mode-checkbox"));
    await user.click(await screen.findByTestId("review-select-req-p1"));
    await user.click(await screen.findByTestId("reviews-bulk-confirm-btn"));

    expect(
      await screen.findByTestId("reviews-bulk-confirm-result"),
    ).toBeInTheDocument();

    // Back to the review queue — the toast now describes a queue that is gone.
    await user.click(screen.getByTestId("reviews-queue-mode-checkbox"));

    await waitFor(() => {
      expect(
        screen.queryByTestId("reviews-bulk-confirm-result"),
      ).not.toBeInTheDocument();
    });
  });
});
