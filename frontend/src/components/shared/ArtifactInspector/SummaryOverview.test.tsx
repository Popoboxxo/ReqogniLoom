/**
 * SummaryOverview — the stored type stand above the Summary tab (S8, #1793).
 *
 * Pinned here:
 *
 *  1. **no workspace (or no roster type) -> no request at all** — an unscoped
 *     read is the one thing this block must never do;
 *  2. `text`, "Stand vom …", `stale` and the E11 reason are all visible, not
 *     a silent empty state;
 *  3. refresh is a write: the button only exists for callers with a write
 *     role, and a click posts the manual run.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/artifact-summary", () => ({
  fetchTypeSummary: vi.fn(),
  refreshTypeSummary: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown): string => {
      if (typeof second === "string") return second;
      if (second && typeof second === "object" && "defaultValue" in second) {
        let text = String((second as { defaultValue: unknown }).defaultValue);
        for (const [name, value] of Object.entries(second)) {
          if (name === "defaultValue") continue;
          text = text.replaceAll(`{{${name}}}`, String(value));
        }
        return text;
      }
      return key;
    },
  }),
}));

import {
  fetchTypeSummary,
  refreshTypeSummary,
  type StoredSummary,
} from "../../../api/artifact-summary";
import { SummaryOverview } from "./SummaryOverview";

const WORKSPACE_ID = "0b6a1a52-2f0b-4a6e-9a3c-7f1f3d2c8e11";

const STORED: StoredSummary = {
  workspaceId: WORKSPACE_ID,
  summaryKind: "type_roster",
  artifactType: "Requirement",
  artifactId: null,
  text: "Twelve requirements cover export, import and the audit trail.",
  reason: null,
  stale: false,
  itemCount: 12,
  status: "ok",
  provider: "anthropic",
  model: "claude",
  tokenUsage: 900,
  trigger: "periodic",
  generatedAt: "2026-11-15T09:30:00Z",
  updatedAt: "2026-11-15T09:30:00Z",
};

function renderOverview(
  overrides: Partial<React.ComponentProps<typeof SummaryOverview>> = {},
): ReturnType<typeof render> {
  return render(
    <SummaryOverview
      workspaceId={WORKSPACE_ID}
      artifactType="Requirement"
      {...overrides}
    />,
  );
}

describe("SummaryOverview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchTypeSummary).mockResolvedValue(STORED);
  });

  it("shows the stored text, the item count and the timestamp", async () => {
    renderOverview();

    expect(await screen.findByTestId("summary-overview-text")).toHaveTextContent(
      "Twelve requirements cover export",
    );
    const meta = screen.getByTestId("summary-overview-meta");
    expect(meta).toHaveTextContent("12 artifacts");
    expect(meta).toHaveTextContent("2026");
    expect(screen.queryByTestId("summary-overview-stale")).toBeNull();
    expect(screen.queryByTestId("summary-overview-reason")).toBeNull();
  });

  it("requests exactly the workspace/type scope", async () => {
    renderOverview();

    await waitFor(() =>
      expect(fetchTypeSummary).toHaveBeenCalledWith(WORKSPACE_ID, "Requirement"),
    );
    expect(fetchTypeSummary).toHaveBeenCalledTimes(1);
  });

  it.each([null, undefined])(
    "renders nothing and requests nothing when the workspace is %s",
    async (workspaceId) => {
      const { container } = renderOverview({ workspaceId });

      expect(container).toBeEmptyDOMElement();
      expect(fetchTypeSummary).not.toHaveBeenCalled();
    },
  );

  it("requests nothing for a kind without a type roster", () => {
    const { container } = renderOverview({ artifactType: undefined });

    expect(container).toBeEmptyDOMElement();
    expect(fetchTypeSummary).not.toHaveBeenCalled();
  });

  it("marks a stale stand as out of date and shows the reason", async () => {
    vi.mocked(fetchTypeSummary).mockResolvedValue({
      ...STORED,
      stale: true,
      reason: "stale",
    });

    renderOverview();

    expect(await screen.findByTestId("summary-overview-stale")).toHaveTextContent(
      "Out of date",
    );
    expect(screen.getByTestId("summary-overview-reason")).toHaveTextContent(
      "The stored summary is out of date.",
    );
  });

  it("keeps a provider degradation visible with its reason", async () => {
    vi.mocked(fetchTypeSummary).mockResolvedValue({
      ...STORED,
      status: "failed",
      reason: "provider_unavailable",
    });

    renderOverview();

    expect(await screen.findByTestId("summary-overview-reason")).toHaveTextContent(
      "The AI provider is currently unavailable.",
    );
  });

  it("says 'no stand yet' for an empty scope instead of inventing a reason", async () => {
    vi.mocked(fetchTypeSummary).mockResolvedValue({
      ...STORED,
      text: null,
      itemCount: 0,
      status: null,
      generatedAt: null,
      updatedAt: null,
    });

    renderOverview();

    expect(await screen.findByTestId("summary-overview-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("summary-overview-reason")).toBeNull();
  });

  it("hides the refresh button from read-only callers", async () => {
    renderOverview({ canRefresh: false });

    await screen.findByTestId("summary-overview-text");
    expect(screen.queryByTestId("summary-overview-refresh")).toBeNull();
    expect(refreshTypeSummary).not.toHaveBeenCalled();
  });

  it("refreshes on demand for a write role and shows the new stand", async () => {
    const user = userEvent.setup();
    vi.mocked(refreshTypeSummary).mockResolvedValue({
      ...STORED,
      text: "Freshly regenerated roster.",
      generatedAt: "2026-11-15T11:00:00Z",
      outcome: "summarized",
    });

    renderOverview({ canRefresh: true });

    await screen.findByTestId("summary-overview-text");
    await user.click(screen.getByTestId("summary-overview-refresh"));

    expect(refreshTypeSummary).toHaveBeenCalledWith(WORKSPACE_ID, "Requirement");
    await waitFor(() =>
      expect(screen.getByTestId("summary-overview-text")).toHaveTextContent(
        "Freshly regenerated roster.",
      ),
    );
  });

  it("shows a load error without crashing the tab", async () => {
    vi.mocked(fetchTypeSummary).mockRejectedValue(new Error("boom"));

    renderOverview();

    expect(await screen.findByTestId("summary-overview-error")).toHaveTextContent(
      "The type summary could not be loaded.",
    );
  });
});
