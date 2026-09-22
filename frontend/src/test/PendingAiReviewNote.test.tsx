/**
 * #424 — PendingAiReviewNote unit test.
 *
 * Pins the coverage-surface read-out of `pending_ai_review` and the single
 * authorised opt-in (`include_unreviewed_ai`, spec section 7.4.1): empty and
 * error states render nothing, the count appears only when unreviewed AI test
 * cases are actually excluded, and toggling the raw view re-queries the
 * coverage report.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PendingAiReviewNote } from "../components/TraceabilityView/PendingAiReviewNote";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const coverageReport = vi.fn();
vi.mock("../api/requirements", () => ({
  requirementsApi: {
    coverageReport: (...args: unknown[]) => coverageReport(...args),
  },
}));

function report(pending: number) {
  return {
    summary: { total: 3, covered: 2, percentage: 66.7, pending_ai_review: pending },
    requirements: [],
  };
}

describe("PendingAiReviewNote (#424)", () => {
  beforeEach(() => {
    coverageReport.mockReset();
  });

  it("renders the pending-AI-review count when unreviewed AI tests are excluded", async () => {
    coverageReport.mockResolvedValue(report(2));

    render(<PendingAiReviewNote workspaceId="ws-1" />);

    const count = await screen.findByTestId("coverage-pending-ai-review-count");
    expect(count).toHaveTextContent("traceability.pendingAiReview");
    expect(screen.getByTestId("coverage-include-unreviewed-ai")).toBeInTheDocument();
  });

  it("renders nothing when nothing is excluded and the raw view is off", async () => {
    coverageReport.mockResolvedValue(report(0));

    render(<PendingAiReviewNote workspaceId="ws-1" />);

    await waitFor(() => expect(coverageReport).toHaveBeenCalledWith("ws-1", { includeUnreviewedAi: false }));
    expect(screen.queryByTestId("coverage-pending-ai-review")).toBeNull();
  });

  it("fails open (renders nothing) when the coverage report errors", async () => {
    coverageReport.mockRejectedValue(new Error("503"));

    render(<PendingAiReviewNote workspaceId="ws-1" />);

    await waitFor(() => expect(coverageReport).toHaveBeenCalled());
    expect(screen.queryByTestId("coverage-pending-ai-review")).toBeNull();
  });

  it("re-queries with include_unreviewed_ai and keeps the toggle visible", async () => {
    coverageReport.mockResolvedValue(report(2));

    render(<PendingAiReviewNote workspaceId="ws-1" />);

    await userEvent.click(await screen.findByTestId("coverage-include-unreviewed-ai"));

    await waitFor(() =>
      expect(coverageReport).toHaveBeenLastCalledWith("ws-1", { includeUnreviewedAi: true })
    );
    // Raw view reports 0 pending but the note must stay so the toggle can be
    // switched back off.
    expect(screen.getByTestId("coverage-include-unreviewed-ai")).toBeInTheDocument();
  });
});
