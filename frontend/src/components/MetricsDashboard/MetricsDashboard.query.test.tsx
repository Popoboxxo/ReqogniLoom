/**
 * MetricsDashboard — react-query migration (#598 S3).
 *
 * Separate from `MetricsDashboard.test.tsx` on purpose: that file pins the
 * rendered contract and stays unchanged, this one pins the data-context
 * behaviour the migration introduces:
 *
 *   - changing the type filter resets the sparkline history (no sample from the
 *     previous filter is carried over);
 *   - a failed refresh keeps the last values visible and surfaces the error.
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import MetricsDashboard from "./MetricsDashboard";
import { metricsApi, type MetricsResult } from "../../api/metrics";
import { displayPreferencesApi } from "../../api/display-preferences";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "test-workspace-id", name: "Test Workspace" },
  }),
  useOptionalWorkspace: () => ({
    activeWorkspace: { id: "test-workspace-id", name: "Test Workspace" },
  }),
}));

vi.mock("../../api/metrics", async () => {
  const { buildMetricCatalog: build } = await import("./metric-catalog.fixture");
  return {
    metricsApi: {
      list: vi.fn(),
      catalog: vi.fn().mockResolvedValue(build()),
      values: vi.fn(),
    },
  };
});

vi.mock("../../api/display-preferences", () => ({
  displayPreferencesApi: { get: vi.fn(), update: vi.fn() },
}));

function metricResult(coveragePercent: number): MetricsResult {
  return {
    workspace_id: "test-workspace-id",
    computed_at: "2026-11-10T10:00:00Z",
    timeframe: "P30D",
    volatility: {
      total_changes: 12,
      total_requirements: 10,
      avg_changes_per_req: 1.2,
      top10_volatile: [],
    },
    traceability_coverage: {
      total: 10,
      covered: 8,
      coverage_percent: coveragePercent,
      uncovered_ids: [],
    },
    workflow_gaps: { total_incomplete: 3, items: [] },
    open_risks: {
      total: 4,
      by_severity: { critical: 1, high: 1, medium: 1, low: 1 },
    },
    warnings: [],
  };
}

function renderDashboard(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MetricsDashboard />
    </QueryClientProvider>
  );
}

/** The sparkline's path: one `M` for a single sample, `M … L …` for two or more. */
function sparklinePath(): string {
  return (
    screen
      .getByTestId("metric-sparkline-coverage")
      .querySelector("path")
      ?.getAttribute("d") ?? ""
  );
}

describe("MetricsDashboard data context (#598 S3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(displayPreferencesApi.get).mockResolvedValue({
      show_readable_ids: true,
      visible_metrics: null,
    });
    vi.mocked(displayPreferencesApi.update).mockImplementation(async (changes) => ({
      show_readable_ids: true,
      visible_metrics: changes.visible_metrics ?? null,
    }));
  });

  it("resets the history when the type filter changes", async () => {
    vi.mocked(metricsApi.list)
      .mockResolvedValueOnce(metricResult(85.5))
      .mockResolvedValueOnce(metricResult(10));

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByTestId("metric-value-coverage").textContent).toBe("85.5")
    );
    // One successful fetch -> one sample -> no line segment yet.
    expect(sparklinePath()).not.toContain("L");

    fireEvent.change(screen.getByTestId("metrics-filter-select"), {
      target: { value: "coverage" },
    });

    await waitFor(() =>
      expect(metricsApi.list).toHaveBeenLastCalledWith("test-workspace-id", {
        type: "coverage",
      })
    );
    await waitFor(() =>
      expect(screen.getByTestId("metric-value-coverage").textContent).toBe("10.0")
    );

    // The previous filter's sample must be gone: a carried-over history would
    // draw a second point and produce an `L` segment.
    expect(sparklinePath()).not.toContain("L");
  });

  it("keeps the last values visible and flags the error when a refresh fails", async () => {
    vi.mocked(metricsApi.list)
      .mockResolvedValueOnce(metricResult(85.5))
      .mockRejectedValueOnce(new Error("offline"));

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByTestId("metric-value-coverage").textContent).toBe("85.5")
    );

    fireEvent.click(screen.getByTestId("metrics-refresh-btn"));

    const banner = await screen.findByTestId("metrics-error");
    expect(banner.textContent).toContain("offline");
    // The stale payload stays on screen (the pre-migration `isStale` contract).
    expect(screen.getByTestId("metric-value-coverage").textContent).toBe("85.5");
    expect(screen.getByTestId("metric-tile-coverage")).toBeInTheDocument();
  });
});
