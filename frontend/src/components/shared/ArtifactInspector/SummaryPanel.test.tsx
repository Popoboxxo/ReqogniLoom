/**
 * SummaryPanel — the inspector's Summary tab (Issue #1792, S2).
 *
 * The three product rules this file pins:
 *
 *  1. no request on mount (a summary is one paid provider call),
 *  2. exactly one request per click, disabled while it runs,
 *  3. a degraded answer is shown **with** its translated reason (spec §9/E11).
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/artifact-summary", () => ({
  fetchArtifactSummary: vi.fn(),
}));

// S8 mounts the read-only type overview inside the summary tab. It reads the
// workspace through the non-throwing `useOptionalWorkspace` (null here) and
// gates its refresh on a role, so neither provider needs to be real.
vi.mock("../../../hooks/useHasRole", () => ({
  useHasRole: () => (): boolean => false,
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

import { fetchArtifactSummary, type ArtifactSummary } from "../../../api/artifact-summary";
import { SummaryPanel } from "./SummaryPanel";

const ARTIFACT_ID = "8f14e45f-ceea-467a-9e4b-3a1c1f0d9b77";

const OK_SUMMARY: ArtifactSummary = {
  artifactId: ARTIFACT_ID,
  artifactType: "Requirement",
  summary: "The export stays deterministic because ordering is pinned.",
  degraded: false,
  degradedReason: null,
  cacheHit: false,
  traceDepth: 1,
  neighbourCount: 3,
  omittedNeighbours: 0,
  generatedAt: "2026-11-15T09:30:00Z",
};

const DEGRADED_SUMMARY: ArtifactSummary = {
  ...OK_SUMMARY,
  summary: null,
  degraded: true,
  degradedReason: "provider_unavailable",
  neighbourCount: 0,
};

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function renderPanel(
  overrides: Partial<React.ComponentProps<typeof SummaryPanel>> = {},
): ReturnType<typeof render> {
  return render(
    <SummaryPanel artifactId={ARTIFACT_ID} artifactType="requirement" {...overrides} />,
  );
}

describe("SummaryPanel (#1792 S2)", () => {
  beforeEach(() => {
    vi.mocked(fetchArtifactSummary).mockReset();
  });

  it("renders in the idle state without any network request", () => {
    renderPanel();

    expect(fetchArtifactSummary).not.toHaveBeenCalled();
    expect(screen.getByTestId("summary-panel")).toBeInTheDocument();
    expect(screen.getByTestId("summary-empty")).toHaveTextContent("Not summarized yet.");
    expect(screen.getByTestId("summary-trigger")).toHaveTextContent("Summarize");
    expect(screen.queryByTestId("summary-text")).not.toBeInTheDocument();
    expect(screen.queryByTestId("summary-degraded")).not.toBeInTheDocument();
  });

  it("fires exactly one request on click and disables the button while it runs", async () => {
    const pending = deferred<ArtifactSummary>();
    vi.mocked(fetchArtifactSummary).mockReturnValue(pending.promise);
    const user = userEvent.setup();
    renderPanel();

    const button = screen.getByTestId("summary-trigger");
    await user.click(button);

    expect(fetchArtifactSummary).toHaveBeenCalledTimes(1);
    expect(fetchArtifactSummary).toHaveBeenCalledWith(ARTIFACT_ID, { refresh: false });
    expect(button).toBeDisabled();
    // Focus stays on the action button (spec §5.2 — no jump into the panel).
    expect(button).toHaveFocus();
    expect(screen.getByTestId("summary-loading")).toHaveAttribute("role", "status");

    await act(async () => {
      pending.resolve(OK_SUMMARY);
    });

    expect(await screen.findByTestId("summary-text")).toHaveTextContent(
      OK_SUMMARY.summary ?? "",
    );
    expect(button).toBeEnabled();
    expect(button).toHaveTextContent("Refresh");
    expect(button).toHaveFocus();
  });

  it("renders the summary text, neighbour meta and generated-at line", async () => {
    vi.mocked(fetchArtifactSummary).mockResolvedValue(OK_SUMMARY);
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("summary-trigger"));

    expect(await screen.findByTestId("summary-text")).toHaveTextContent(
      "The export stays deterministic because ordering is pinned.",
    );
    const meta = screen.getByTestId("summary-meta");
    expect(meta).toHaveTextContent("Neighbours: 3 · depth 1");
    expect(meta).toHaveTextContent("Generated:");
    expect(screen.queryByTestId("summary-empty")).not.toBeInTheDocument();
  });

  it("sends refresh=true on a second click and replaces the text", async () => {
    vi.mocked(fetchArtifactSummary)
      .mockResolvedValueOnce(OK_SUMMARY)
      .mockResolvedValueOnce({ ...OK_SUMMARY, summary: "Second answer.", cacheHit: true });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("summary-trigger"));
    await screen.findByText(OK_SUMMARY.summary ?? "");

    await user.click(screen.getByTestId("summary-trigger"));

    await waitFor(() => {
      expect(fetchArtifactSummary).toHaveBeenLastCalledWith(ARTIFACT_ID, { refresh: true });
    });
    expect(await screen.findByText("Second answer.")).toBeInTheDocument();
    expect(screen.getByTestId("summary-meta")).toHaveTextContent("from cache");
  });

  it.each([
    ["budget_exhausted", "The AI budget for this period is exhausted."],
    ["provider_unavailable", "The AI provider is currently unavailable."],
    ["stale", "The stored summary is out of date."],
    ["disabled", "AI summaries are disabled for this workspace."],
  ] as const)("shows the degradation hint and reason for %s", async (reason, label) => {
    vi.mocked(fetchArtifactSummary).mockResolvedValue({
      ...DEGRADED_SUMMARY,
      degradedReason: reason,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("summary-trigger"));

    const hint = await screen.findByTestId("summary-degraded");
    expect(hint).toHaveTextContent("No AI summary available.");
    expect(screen.getByTestId("summary-degraded-reason")).toHaveTextContent(label);
    expect(screen.queryByTestId("summary-text")).not.toBeInTheDocument();
  });

  it("falls back to a generic reason when the backend omits the enum value", async () => {
    vi.mocked(fetchArtifactSummary).mockResolvedValue({
      ...DEGRADED_SUMMARY,
      degradedReason: null,
    });
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("summary-trigger"));

    expect(await screen.findByTestId("summary-degraded-reason")).toHaveTextContent(
      "No reason given.",
    );
  });

  it("shows a transport error and retries on the same button", async () => {
    vi.mocked(fetchArtifactSummary)
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce(OK_SUMMARY);
    const user = userEvent.setup();
    renderPanel();

    const button = screen.getByTestId("summary-trigger");
    await user.click(button);

    expect(await screen.findByTestId("summary-error")).toHaveTextContent(
      "The summary could not be loaded.",
    );
    expect(button).toHaveTextContent("Try again");
    expect(button).toBeEnabled();

    await user.click(button);

    expect(await screen.findByTestId("summary-text")).toBeInTheDocument();
    expect(fetchArtifactSummary).toHaveBeenCalledTimes(2);
  });

  it("keeps the previous text visible when a refresh fails", async () => {
    vi.mocked(fetchArtifactSummary)
      .mockResolvedValueOnce(OK_SUMMARY)
      .mockRejectedValueOnce(new Error("provider down"));
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByTestId("summary-trigger"));
    await screen.findByTestId("summary-text");

    await user.click(screen.getByTestId("summary-trigger"));

    expect(await screen.findByTestId("summary-error")).toBeInTheDocument();
    expect(screen.getByTestId("summary-text")).toHaveTextContent(OK_SUMMARY.summary ?? "");
  });

  it("never requests anything without an Artifact UUID", async () => {
    const user = userEvent.setup();
    renderPanel({ artifactId: "" });

    const button = screen.getByTestId("summary-trigger");
    expect(button).toBeDisabled();

    await user.click(button);
    expect(fetchArtifactSummary).not.toHaveBeenCalled();
  });

  it("drops the previous summary and ignores late answers when the artifact changes", async () => {
    const pending = deferred<ArtifactSummary>();
    vi.mocked(fetchArtifactSummary).mockReturnValueOnce(pending.promise);
    const user = userEvent.setup();
    const view = renderPanel();

    await user.click(screen.getByTestId("summary-trigger"));

    view.rerender(<SummaryPanel artifactId="another-uuid" artifactType="requirement" />);

    expect(screen.getByTestId("summary-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("summary-text")).not.toBeInTheDocument();

    await act(async () => {
      pending.resolve(OK_SUMMARY);
    });

    // The late answer belonged to the previous artifact.
    expect(screen.queryByTestId("summary-text")).not.toBeInTheDocument();
    expect(screen.getByTestId("summary-empty")).toBeInTheDocument();
    expect(fetchArtifactSummary).toHaveBeenCalledTimes(1);
  });

  it("exposes the artifact type for diagnostics", () => {
    renderPanel({ artifactType: "architecture" });

    expect(screen.getByTestId("summary-panel")).toHaveAttribute(
      "data-artifact-type",
      "architecture",
    );
  });
});
