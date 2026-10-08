/**
 * SuggestionsInbox — ADR-019 / WP6 component tests.
 *
 * Covers the four user-visible behaviours the inbox owes the reviewer:
 *   1. each row renders its server-set provenance ("Vorschlag von …"),
 *   2. Annehmen calls the API and refreshes the list,
 *   3. Ablehnen is a two-step action: a confirmation dialog requires a reason
 *      before the reject is sent,
 *   4. a canonical error envelope (409/403/…) is surfaced, not swallowed.
 *
 * Mocking follows the existing ReviewsView tests: the workspace context and
 * the API module are stubbed, TanStack Query runs for real with retries off.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../context/WorkspaceContext");
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
  // Interpolate the options object so provenance/state copy carries the value
  // under test, and honour a string fallback for the Dialog's own labels.
  const t = (
    key: string,
    fallbackOrOptions?: string | Record<string, unknown>,
  ): string => {
    if (typeof fallbackOrOptions === "string") return fallbackOrOptions;
    if (fallbackOrOptions && typeof fallbackOrOptions === "object") {
      const rendered = Object.entries(fallbackOrOptions)
        .map(([k, v]) => `${k}=${String(v)}`)
        .join(" ");
      return rendered ? `${key} ${rendered}` : key;
    }
    return key;
  };
  return { useTranslation: () => ({ t }) };
});

import * as workspaceContext from "../../context/WorkspaceContext";
import {
  acceptSuggestion,
  listSuggestions,
  rejectSuggestion,
} from "../../api/suggestions";
import { SuggestionsInbox } from "./SuggestionsInbox";

const WS = { id: "ws-sug-001", name: "Suggestion WS", preset: "standard" };

const SUGGESTION = {
  id: "sug-1",
  kind: "trace_link" as const,
  status: "open" as const,
  producer: "TraceabilitySuggestService",
  proposed_by: "BenchTraceAgent",
  proposed_at: "2026-10-08T10:00:00Z",
  decided_by: null,
  decided_at: null,
  target_item_type: "TraceLink",
  target_item_id: "req-2",
  payload: { rule_id: "TRACE-P1" },
  workspace_id: WS.id,
  created_at: "2026-10-08T10:00:00Z",
};

const LIST_ONE = {
  count: 1,
  next: null,
  previous: null,
  results: [SUGGESTION],
};

const LIST_EMPTY = { count: 0, next: null, previous: null, results: [] };

const renderInbox = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SuggestionsInbox />
    </QueryClientProvider>,
  );
};

describe("SuggestionsInbox (ADR-019 / WP6)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: WS,
    } as never);
    vi.mocked(listSuggestions).mockResolvedValue(LIST_ONE as never);
  });

  it("renders the server-set provenance for an open suggestion", async () => {
    renderInbox();

    const provenance = await screen.findByTestId("suggestion-provenance-sug-1");
    expect(provenance).toHaveTextContent("source=BenchTraceAgent");
    expect(screen.getByTestId("suggestion-row-sug-1")).toBeInTheDocument();
    // The kind and target are shown too — the reviewer sees what is proposed.
    expect(screen.getByTestId("suggestion-kind-sug-1")).toBeInTheDocument();
    expect(screen.getByTestId("suggestion-target-sug-1")).toHaveTextContent(
      "TraceLink",
    );
  });

  it("annehmen calls the API and refreshes the list", async () => {
    vi.mocked(listSuggestions)
      .mockResolvedValueOnce(LIST_ONE as never)
      .mockResolvedValue(LIST_EMPTY as never);
    vi.mocked(acceptSuggestion).mockResolvedValue({
      ...SUGGESTION,
      status: "accepted",
    } as never);
    const user = userEvent.setup();

    renderInbox();

    await user.click(await screen.findByTestId("suggestion-accept-sug-1"));

    await waitFor(() => {
      expect(acceptSuggestion).toHaveBeenCalledWith("sug-1");
    });
    // The decision invalidates the list, so the decided row drops out.
    await waitFor(() => {
      expect(screen.queryByTestId("suggestion-row-sug-1")).not.toBeInTheDocument();
    });
    expect(listSuggestions).toHaveBeenCalledTimes(2);
  });

  it("ablehnen requires a reason before the reject is recorded", async () => {
    vi.mocked(listSuggestions)
      .mockResolvedValueOnce(LIST_ONE as never)
      .mockResolvedValue(LIST_EMPTY as never);
    vi.mocked(rejectSuggestion).mockResolvedValue({
      ...SUGGESTION,
      status: "rejected",
    } as never);
    const user = userEvent.setup();

    renderInbox();

    await user.click(await screen.findByTestId("suggestion-reject-sug-1"));
    // Confirmation step, not an immediate reject.
    expect(screen.getByTestId("suggestion-reject-confirm")).toBeInTheDocument();

    // Confirming with an empty reason is refused client-side and never sent.
    await user.click(
      screen.getByTestId("suggestion-reject-confirm-confirm"),
    );
    expect(
      await screen.findByTestId("suggestion-reject-error"),
    ).toBeInTheDocument();
    expect(rejectSuggestion).not.toHaveBeenCalled();

    // With a reason, the reject records it and closes the dialog.
    await user.type(
      screen.getByTestId("suggestion-reject-reason"),
      "duplicate of #121",
    );
    await user.click(screen.getByTestId("suggestion-reject-confirm-confirm"));

    await waitFor(() => {
      expect(rejectSuggestion).toHaveBeenCalledWith("sug-1", "duplicate of #121");
    });
    await waitFor(() => {
      expect(
        screen.queryByTestId("suggestion-reject-confirm"),
      ).not.toBeInTheDocument();
    });
  });

  it("surfaces the canonical error envelope of a failed action", async () => {
    vi.mocked(acceptSuggestion).mockRejectedValue({
      error: {
        code: "PERMISSION_DENIED",
        message: "Agent cannot accept its own suggestion.",
        details: [],
      },
    } as never);
    const user = userEvent.setup();

    renderInbox();

    await user.click(await screen.findByTestId("suggestion-accept-sug-1"));

    await waitFor(() => {
      expect(screen.getByTestId("suggestions-action-error")).toHaveTextContent(
        "Agent cannot accept its own suggestion.",
      );
    });
  });

  it("surfaces a list error from the error envelope", async () => {
    vi.mocked(listSuggestions).mockRejectedValue({
      error: {
        code: "NOT_FOUND",
        message: "No such workspace.",
        details: [],
      },
    } as never);

    renderInbox();

    await waitFor(() => {
      expect(screen.getByTestId("suggestions-error")).toHaveTextContent(
        "No such workspace.",
      );
    });
  });

  it("shows an empty state when nothing is waiting", async () => {
    vi.mocked(listSuggestions).mockResolvedValue(LIST_EMPTY as never);

    renderInbox();

    expect(await screen.findByTestId("suggestions-empty")).toBeInTheDocument();
  });

  it("is a labelled region and links the reject reason to its error (review round 2)", async () => {
    const user = userEvent.setup();
    renderInbox();

    // A-F7: the inbox is a labelled region, not an unlabelled list.
    await screen.findByTestId("suggestion-row-sug-1");
    expect(
      screen.getByRole("region", { name: "suggestions.heading" }),
    ).toBeInTheDocument();

    await user.click(screen.getByTestId("suggestion-reject-sug-1"));

    // A-F9: the ConfirmDialog message is the dialog's accessible description.
    const dialog = screen.getByTestId("suggestion-reject-confirm");
    const describedBy = dialog.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)).toHaveTextContent(
      "suggestions.rejectConfirmMessage",
    );

    // F6 + A-F6: functionally required and wired to the error element.
    const textarea = screen.getByTestId("suggestion-reject-reason");
    expect(textarea).toHaveAttribute("required");
    expect(textarea).toHaveAttribute("aria-required", "true");
    expect(textarea).toHaveAttribute("aria-invalid", "false");

    await user.click(screen.getByTestId("suggestion-reject-confirm-confirm"));
    await waitFor(() => {
      expect(textarea).toHaveAttribute("aria-invalid", "true");
    });
    const error = await screen.findByTestId("suggestion-reject-error");
    expect(textarea.getAttribute("aria-describedby")).toBe(error.id);
  });

  it("gives row actions contextual names and announces a decision (review round 2)", async () => {
    vi.mocked(listSuggestions)
      .mockResolvedValueOnce(LIST_ONE as never)
      .mockResolvedValue(LIST_EMPTY as never);
    vi.mocked(acceptSuggestion).mockResolvedValue({
      ...SUGGESTION,
      status: "accepted",
    } as never);
    const user = userEvent.setup();

    renderInbox();

    // A-F4: identical visible labels, contextual accessible names.
    const accept = await screen.findByTestId("suggestion-accept-sug-1");
    expect(accept.getAttribute("aria-label")).toContain("suggestions.acceptLabel");
    expect(
      screen
        .getByTestId("suggestion-reject-sug-1")
        .getAttribute("aria-label"),
    ).toContain("suggestions.rejectLabel");

    await user.click(accept);

    // A-F2: a polite live region announces the outcome.
    await waitFor(() => {
      expect(screen.getByTestId("suggestions-status")).toHaveTextContent(
        "suggestions.accepted",
      );
    });
  });
});
