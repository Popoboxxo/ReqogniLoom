/**
 * ARCH-L1-001 ReactFrontend — Interview Data Hook (plan Task 6).
 *
 * TanStack Query data source for the Interview list/detail pages, mirroring
 * `useAdrData`/`useRiskData`: list via `listAll` (pagination-following),
 * detail via `getState` (the richer `InterviewState` shape the detail page
 * needs for the chat transcript / missing fields / grounding, not the bare
 * `InterviewSummary` the list rows use).
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { interviewsApi, type InterviewState, type InterviewSummary } from "../../api/interviews";
import { useWorkspace } from "../../context/WorkspaceContext";
import { asError } from "../../queries/query-error";

export const interviewKeys = {
  all: ["interviews"] as const,
  list: (workspaceId: string) => ["interviews", "list", workspaceId] as const,
  detail: (id: string) => ["interviews", "detail", id] as const,
};

export interface InterviewData {
  items: InterviewSummary[];
  item: InterviewState | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

export function useInterviewData(selectedId?: string): InterviewData {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: interviewKeys.list(workspaceId ?? ""),
    queryFn: async () => interviewsApi.listAll(workspaceId as string),
    enabled: !!workspaceId && !isLoadingWorkspace,
  });

  const detailQuery = useQuery({
    queryKey: interviewKeys.detail(selectedId ?? ""),
    queryFn: () => interviewsApi.getState(selectedId as string),
    enabled: !!selectedId,
  });

  const refresh = (): void => {
    if (workspaceId) {
      void queryClient.invalidateQueries({ queryKey: interviewKeys.list(workspaceId) });
    }
    if (selectedId) {
      void queryClient.invalidateQueries({ queryKey: interviewKeys.detail(selectedId) });
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
