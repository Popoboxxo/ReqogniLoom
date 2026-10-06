/**
 * GH-1200 — the diff panel must never hang silently.
 *
 * The reported Goal defect was a dead end: the "View Diff" button fetched the
 * version list, no `/diff/` route existed, and a failing or never-resolving
 * diff request left the panel with no visible reaction. These tests lock in
 * the three guarantees added alongside the backend `diff` route:
 *
 *   1. a rejected diff fetch shows a localized "Diff nicht verfügbar" message
 *      (plus the server detail) and leaves the loading state;
 *   2. a never-resolving diff fetch is bounded by a timeout, so the same
 *      message appears instead of an infinite spinner;
 *   3. an artifact with a single version (from === to) renders an explicit
 *      "no two versions to compare" message rather than an empty body.
 */

import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ArtifactDiff } from "./ArtifactDiff";
import type { ArtifactVersion } from "../../types";

vi.mock("react-i18next", () => {
  // The component references these keys without an inline default (the
  // i18n-parity ratchet forbids new `t(key, "default")` sites), so the mock
  // resolves them from the real locale strings.
  const translations: Record<string, string> = {
    "diff.unavailable": "Diff nicht verfügbar",
    "diff.noComparison":
      "Diff nicht verfügbar — für dieses Element gibt es keine zwei Versionen zum Vergleichen.",
  };
  const t = (key: string, fallback?: string | Record<string, unknown>): string =>
    translations[key] ?? (typeof fallback === "string" ? fallback : key);
  return { useTranslation: () => ({ t }) };
});

const ENTITY_ID = "goal-diff-gh1200";

const TWO_VERSIONS: ArtifactVersion[] = [
  { version: 1, label: "v1", modified_at: "2026-01-01T00:00:00Z" },
  { version: 2, label: "v2", modified_at: "2026-01-02T00:00:00Z" },
];

/** The component's own guard — keep in sync with DIFF_FETCH_TIMEOUT_MS. */
const DIFF_FETCH_TIMEOUT_MS = 15_000;

afterEach(() => {
  vi.useRealTimers();
});

describe("ArtifactDiff — GH-1200 visible diff feedback", () => {
  it("shows a localized message and leaves loading when the diff fetch rejects", async () => {
    const diffFetcher = vi
      .fn()
      .mockRejectedValue({ error: { message: "Diff route missing" } });
    const versionsFetcher = vi.fn().mockResolvedValue(TWO_VERSIONS);

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="goal"
        currentVersion={2}
        diffFetcher={diffFetcher as never}
        versionsFetcher={versionsFetcher as never}
        onClose={vi.fn()}
      />,
    );

    const error = await screen.findByTestId("diff-error");
    expect(error).toHaveTextContent("Diff nicht verfügbar");
    expect(error).toHaveTextContent("Diff route missing");
    expect(screen.queryByTestId("diff-loading")).not.toBeInTheDocument();
  });

  it("times out a never-resolving diff fetch instead of hanging", async () => {
    vi.useFakeTimers();
    const diffFetcher = vi.fn().mockReturnValue(new Promise<never>(() => {}));
    const versionsFetcher = vi.fn().mockResolvedValue(TWO_VERSIONS);

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="goal"
        currentVersion={2}
        diffFetcher={diffFetcher as never}
        versionsFetcher={versionsFetcher as never}
        onClose={vi.fn()}
      />,
    );

    // Let the version list resolve and the diff effect run.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(diffFetcher).toHaveBeenCalledWith(ENTITY_ID, 1, 2);
    expect(screen.getByTestId("diff-loading")).toBeInTheDocument();

    // Advance past the component's fetch timeout.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(DIFF_FETCH_TIMEOUT_MS);
    });

    expect(screen.getByTestId("diff-error")).toHaveTextContent("Diff nicht verfügbar");
    expect(screen.queryByTestId("diff-loading")).not.toBeInTheDocument();
  });

  it("renders an explicit no-comparison message for a single-version artifact", async () => {
    const diffFetcher = vi.fn();
    const versionsFetcher = vi
      .fn()
      .mockResolvedValue([{ version: 1, label: "v1", modified_at: null }]);

    render(
      <ArtifactDiff
        entityId={ENTITY_ID}
        entityType="goal"
        currentVersion={1}
        diffFetcher={diffFetcher as never}
        versionsFetcher={versionsFetcher as never}
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByTestId("diff-unavailable")).toBeInTheDocument();
    expect(diffFetcher).not.toHaveBeenCalled();
    expect(screen.queryByTestId("diff-loading")).not.toBeInTheDocument();
  });
});
