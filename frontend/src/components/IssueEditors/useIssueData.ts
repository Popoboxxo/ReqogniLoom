/**
 * ARCH-L1-001 ReactFrontend — Issue Data Hook.
 *
 * req_id: REQ-049 (TanStack Query migration)
 *
 * TanStack Query replacement for the hand-rolled fetch/loading/error state.
 * The return shape is preserved so IssueEditors is unchanged.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { issuesApi } from "../../api/issues";
import { useWorkspace } from "../../context/WorkspaceContext";
import { asError } from "../../queries/query-error";
import type { Issue } from "../../types";

export const issueKeys = {
  all: ["issues"] as const,
  list: (workspaceId: string) => ["issues", "list", workspaceId] as const,
  detail: (id: string) => ["issues", "detail", id] as const,
};

export interface IssueData {
  items: Issue[];
  item: Issue | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

export function useIssueData(selectedId?: string): IssueData {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: issueKeys.list(workspaceId ?? ""),
    // Issue C: list() only returned page 1 (PAGE_SIZE=25) — listAll()
    // follows pagination until exhaustion.
    queryFn: async () => issuesApi.listAll(workspaceId as string),
    // Issue B: activeWorkspace starts as the DEFAULT_WORKSPACE placeholder
    // (truthy fake UUID), so !!workspaceId alone fires this query before the
    // real workspace has loaded, hitting the backend with a bogus id (401).
    enabled: !!workspaceId && !isLoadingWorkspace,
  });

  const detailQuery = useQuery({
    queryKey: issueKeys.detail(selectedId ?? ""),
    queryFn: () => issuesApi.get(selectedId as string),
    enabled: !!selectedId,
  });

  const refresh = (): void => {
    if (workspaceId) {
      void queryClient.invalidateQueries({ queryKey: issueKeys.list(workspaceId) });
    }
    if (selectedId) {
      void queryClient.invalidateQueries({ queryKey: issueKeys.detail(selectedId) });
    }
  };

  const rawError = detailQuery.error ?? listQuery.error;

  return {
    items: listQuery.data ?? [],
    item: selectedId ? detailQuery.data ?? null : null,
    isLoading: isLoadingWorkspace || listQuery.isLoading || detailQuery.isLoading,
    error: rawError ? asError(rawError) : null,
    refresh,
  };
}
