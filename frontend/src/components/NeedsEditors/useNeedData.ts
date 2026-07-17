/**
 * ARCH-L1-001 ReactFrontend — Stakeholder Need Data Hook.
 *
 * req_id: REQ-049 (TanStack Query migration)
 *
 * TanStack Query replacement for the hand-rolled fetch/loading/error state.
 * The return shape is preserved so NeedsEditors is unchanged.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { stakeholderNeedApi } from "../../api/stakeholder-need";
import { useWorkspace } from "../../context/WorkspaceContext";
import { asError } from "../../queries/query-error";
import type { StakeholderNeed } from "../../types";

export const needKeys = {
  all: ["needs"] as const,
  list: (workspaceId: string) => ["needs", "list", workspaceId] as const,
  detail: (id: string) => ["needs", "detail", id] as const,
};

export interface NeedData {
  needs: StakeholderNeed[];
  need: StakeholderNeed | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

export function useNeedData(selectedId?: string): NeedData {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: needKeys.list(workspaceId ?? ""),
    queryFn: async () =>
      (await stakeholderNeedApi.listByWorkspace(workspaceId as string)).results ?? [],
    enabled: !!workspaceId && !isLoadingWorkspace,
  });

  const detailQuery = useQuery({
    queryKey: needKeys.detail(selectedId ?? ""),
    queryFn: () => stakeholderNeedApi.get(selectedId as string),
    enabled: !!selectedId,
  });

  const refresh = (): void => {
    if (workspaceId) {
      void queryClient.invalidateQueries({ queryKey: needKeys.list(workspaceId) });
    }
    if (selectedId) {
      void queryClient.invalidateQueries({ queryKey: needKeys.detail(selectedId) });
    }
  };

  const rawError = detailQuery.error ?? listQuery.error;

  return {
    needs: listQuery.data ?? [],
    need: selectedId ? detailQuery.data ?? null : null,
    isLoading: isLoadingWorkspace || listQuery.isLoading || detailQuery.isLoading,
    error: rawError ? asError(rawError) : null,
    refresh,
  };
}
