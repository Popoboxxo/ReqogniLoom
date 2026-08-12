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
}

export function useRequirementData(
  selectedId?: string,
  options?: UseRequirementDataOptions,
): RequirementData {
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useRequirementsList(workspaceId, options?.includeDeleted ?? false);
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
    error: detailQuery.error ? extractErrorMessage(detailQuery.error) : null,
    refresh,
  };
}
