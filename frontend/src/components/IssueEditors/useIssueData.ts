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
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: issueKeys.list(workspaceId ?? ""),
    queryFn: async () => (await issuesApi.list(workspaceId as string)).results ?? [],
    enabled: !!workspaceId,
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
    isLoading: listQuery.isLoading || detailQuery.isLoading,
    error: rawError ? asError(rawError) : null,
    refresh,
  };
}
