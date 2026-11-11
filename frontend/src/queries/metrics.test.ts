/**
 * SeMetrics query hooks (#598 S3).
 *
 * Pins the contract the dashboard now relies on:
 *
 *   - the read goes through `metricsApi.list` with the workspace and the
 *     caller's type filter, and is cached under `metricsKeys.list`;
 *   - without a workspace the query stays idle and never reaches the API;
 *   - a failed refetch keeps the last successful payload (`data`) while
 *     setting `isError` — the dashboard turns that pair into its stale banner.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

import { metricsApi, type MetricsResult } from "../api/metrics";
import { metricsKeys, useMetricsQuery } from "./metrics";

vi.mock("../api/metrics", () => ({
  metricsApi: { list: vi.fn(), catalog: vi.fn(), values: vi.fn() },
}));

const WS = "ws-1";

const RESULT: MetricsResult = {
  workspace_id: WS,
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
    coverage_percent: 80,
    uncovered_ids: ["REQ-1", "REQ-2"],
  },
  workflow_gaps: { total_incomplete: 3, items: [] },
  open_risks: {
    total: 4,
    by_severity: { critical: 1, high: 1, medium: 1, low: 1 },
  },
  warnings: [],
};

function newQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

function wrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("metricsKeys", () => {
  it("includes the workspace and filter so a context switch cannot reuse a payload", () => {
    expect(metricsKeys.list(WS, "requirement")).toEqual([
      "metrics",
      "list",
      WS,
      "requirement",
    ]);
    expect(metricsKeys.list(WS)).toEqual(["metrics", "list", WS, null]);
    expect(metricsKeys.list(undefined, "requirement")).toEqual([
      "metrics",
      "list",
      null,
      "requirement",
    ]);
  });
});

describe("useMetricsQuery", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetches metrics for the workspace and type", async () => {
    vi.mocked(metricsApi.list).mockResolvedValue(RESULT);
    const queryClient = newQueryClient();

    const { result } = renderHook(
      () => useMetricsQuery(WS, { type: "requirement" }),
      { wrapper: wrapper(queryClient) }
    );

    await waitFor(() => expect(result.current.data).toEqual(RESULT));
    expect(metricsApi.list).toHaveBeenCalledWith(WS, { type: "requirement" });
    expect(queryClient.getQueryData(metricsKeys.list(WS, "requirement"))).toEqual(
      RESULT
    );
  });

  it("is disabled without a workspace", () => {
    const queryClient = newQueryClient();

    const { result } = renderHook(() => useMetricsQuery(undefined, {}), {
      wrapper: wrapper(queryClient),
    });

    expect(result.current.fetchStatus).toBe("idle");
    expect(metricsApi.list).not.toHaveBeenCalled();
  });

  it("keeps previous data and flags error when a refetch fails", async () => {
    vi.mocked(metricsApi.list).mockResolvedValueOnce(RESULT);
    const queryClient = newQueryClient();

    const { result } = renderHook(() => useMetricsQuery(WS, {}), {
      wrapper: wrapper(queryClient),
    });

    await waitFor(() => expect(result.current.data).toEqual(RESULT));
    // Read `isError` once so react-query's property tracking includes it.
    // The real consumer (the dashboard) reads it during render; a test that
    // only reads `data` would not be re-rendered by an error-only change.
    expect(result.current.isError).toBe(false);

    vi.mocked(metricsApi.list).mockRejectedValueOnce(new Error("offline"));
    await act(async () => {
      await result.current.refetch();
      // query-core notifies subscribers on a `setTimeout(0)` (notifyManager
      // scheduler); flush that macrotask inside `act`.
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // The last successful payload stays available — that is what the
    // dashboard's stale banner renders.
    expect(result.current.data).toEqual(RESULT);
  });
});
