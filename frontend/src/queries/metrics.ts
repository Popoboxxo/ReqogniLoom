/**
 * ARCH-L1-001 ReactFrontend — SeMetrics query hooks (#598 S3).
 *
 * The dashboard used to own its own `useState`/`useEffect` load cycle
 * (`MetricsDashboard.tsx`), including a hand-rolled `isStale` flag. This module
 * puts the read on the same cache the rest of the app uses (see
 * `queries/preferences.ts` for the pattern) and keeps the dashboard's
 * observable contract:
 *
 * - one cache entry per (workspace, type) pair, so switching either never
 *   paints the previous context's numbers — there is no `placeholderData`;
 * - `staleTime: 0`: opening the dashboard always asks the server (the
 *   endpoint caches its own computation, REQ-L2-SM-012);
 * - no retry and no focus/reconnect refetch: the pre-react-query dashboard
 *   loaded on mount and on the explicit Refresh button only.
 *
 * Error semantics stay with the caller: react-query keeps the last successful
 * `data` on a failed refetch, which is exactly what the dashboard's "stale
 * values" banner needs (`isError && data !== undefined`).
 */

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { metricsApi, type MetricsResult } from "../api/metrics";
import type { UUID } from "../types";

export interface MetricsFilterOptions {
  /** Optional type filter forwarded to the backend (`MetricsQueryOptions.type`). */
  type?: string;
}

export const metricsKeys = {
  /** Prefix for every metrics cache entry. */
  all: ["metrics"] as const,
  /**
   * One dashboard read. `type` is part of the key so a filter change starts a
   * fresh query instead of reusing the unfiltered payload.
   */
  list: (workspaceId: UUID | undefined, type?: string) =>
    ["metrics", "list", workspaceId ?? null, type ?? null] as const,
};

/**
 * The workspace's SeMetrics report, optionally narrowed by the dashboard's
 * type filter.
 *
 * Without a workspace the query stays idle (`enabled: false`) and the
 * dashboard renders its "select a workspace" empty state.
 */
export function useMetricsQuery(
  workspaceId: UUID | undefined,
  options: MetricsFilterOptions = {},
): UseQueryResult<MetricsResult> {
  return useQuery<MetricsResult>({
    queryKey: metricsKeys.list(workspaceId, options.type),
    // `workspaceId` is guaranteed by `enabled`; the assertion only satisfies
    // the wrapper's non-optional parameter.
    queryFn: () => metricsApi.list(workspaceId as UUID, options),
    enabled: Boolean(workspaceId),
    staleTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}
