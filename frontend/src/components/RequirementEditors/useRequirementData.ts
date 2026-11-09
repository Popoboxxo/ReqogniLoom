/**
 * ARCH-L1-001 ReactFrontend — Requirement Data Hook.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id: REQ-L3-RF003-001 (Inline-Editing),
 *         REQ-L3-RF003-004 (Editor-Performance < 500ms)
 *
 * Thin adapter over the TanStack Query hooks in ../../queries/requirements,
 * preserving the RequirementData shape so existing call sites (e.g.
 * RequirementEditors.tsx) don't need to change.
 */

import { useQueryClient } from "@tanstack/react-query";
import { extractErrorMessage } from "../../api/client";
import type { Requirement, TraceLink } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";
import {
  requirementKeys,
  useRequirementsList,
  useRequirementDetail,
} from "../../queries/requirements";

export interface RequirementData {
  requirements: Requirement[];
  requirement: Requirement | null;
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
  linkedTitles: Record<string, string>;
  linkedRoutes: Record<string, string>;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

export interface UseRequirementDataOptions {
  /**
   * GH-443: include soft-deleted (`status === "outdated"`) requirements in the
   * list. Off by default — DELETE is a soft-delete, so without the opt-in the
   * list would keep showing records the user just deleted.
   */
  includeDeleted?: boolean;
  /**
   * #1668: allocation filter, applied **server-side** (`?allocated=`).
   * ``all`` sends nothing; ``allocated``/``unallocated`` map onto
   * ``allocated=true|false``.
   */
  allocation?: RequirementAllocationFilter;
}

/**
 * #1668: UI filter over the `allocated-to` TraceLink. `allocated` requires at
 * least one allocation link, `unallocated` requires none. The value is a
 * persisted list filter, so it is a string union rather than a boolean.
 */
export type RequirementAllocationFilter = "all" | "allocated" | "unallocated";

/** Shape guard for {@link RequirementAllocationFilter} (persisted state). */
export function isRequirementAllocationFilter(
  value: unknown,
): value is RequirementAllocationFilter {
  return value === "all" || value === "allocated" || value === "unallocated";
}

/**
 * Translate the UI filter onto the API's tri-state `allocated` parameter.
 * `all` becomes `undefined` (the parameter is omitted, not sent as an empty
 * string — the backend parses it as a boolean).
 */
export function allocationToQueryParam(
  allocation: RequirementAllocationFilter | undefined,
): boolean | undefined {
  if (allocation === "allocated") return true;
  if (allocation === "unallocated") return false;
  return undefined;
}

/**
 * sessionStorage key of the persisted allocation filter.
 *
 * Per-workspace on purpose (review finding F-02 on the sibling list filters):
 * a shared key would carry one workspace's selection onto the next, making a
 * freshly opened workspace look filtered/empty for no visible reason.
 */
export function requirementAllocationStorageKey(
  workspaceId: string | undefined,
): string {
  return `reqlo:list-state:requirements:${workspaceId ?? "no-workspace"}:allocation`;
}

export function useRequirementData(
  selectedId?: string,
  options?: UseRequirementDataOptions,
): RequirementData {
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useRequirementsList(
    workspaceId,
    options?.includeDeleted ?? false,
    allocationToQueryParam(options?.allocation),
  );
  const detailQuery = useRequirementDetail(workspaceId, selectedId);

  const refresh = (): void => {
    if (workspaceId) {
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.list(workspaceId),
      });
    }
    if (selectedId) {
      void queryClient.invalidateQueries({
        queryKey: requirementKeys.detail(selectedId),
      });
    }
  };

  return {
    requirements: listQuery.data ?? [],
    requirement: selectedId ? detailQuery.data?.requirement ?? null : null,
    upstreamLinks: detailQuery.data?.upstreamLinks ?? [],
    downstreamLinks: detailQuery.data?.downstreamLinks ?? [],
    linkedTitles: detailQuery.data?.linkedTitles ?? {},
    linkedRoutes: detailQuery.data?.linkedRoutes ?? {},
    isLoading: listQuery.isLoading,
    // UI-31: previously only detailQuery.error was surfaced, so a failed list
    // fetch silently looked like an empty list instead of an error. Mirror
    // useNeedData's pattern and propagate whichever query failed.
    error: detailQuery.error
      ? extractErrorMessage(detailQuery.error)
      : listQuery.error
        ? extractErrorMessage(listQuery.error)
        : null,
    refresh,
  };
}
