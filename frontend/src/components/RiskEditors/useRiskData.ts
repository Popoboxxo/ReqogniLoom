/**
 * ARCH-L1-001 ReactFrontend — Risk Data Hook.
 *
 * req_id: REQ-049 (TanStack Query migration)
 *
 * TanStack Query replacement for the hand-rolled fetch/loading/error state.
 * The return shape is preserved so RiskEditors is unchanged.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { risksApi } from "../../api/risks";
import { useWorkspace } from "../../context/WorkspaceContext";
import { asError } from "../../queries/query-error";
import type { Risk } from "../../types";

export const riskKeys = {
  all: ["risks"] as const,
  list: (workspaceId: string) => ["risks", "list", workspaceId] as const,
  detail: (id: string) => ["risks", "detail", id] as const,
};

export interface RiskData {
  items: Risk[];
  item: Risk | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

export function useRiskData(selectedId?: string): RiskData {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: riskKeys.list(workspaceId ?? ""),
    queryFn: async () => (await risksApi.list(workspaceId as string)).results ?? [],
    enabled: !!workspaceId && !isLoadingWorkspace,
  });

  const detailQuery = useQuery({
    queryKey: riskKeys.detail(selectedId ?? ""),
    queryFn: () => risksApi.get(selectedId as string),
    enabled: !!selectedId,
  });

  const refresh = (): void => {
    if (workspaceId) {
      void queryClient.invalidateQueries({ queryKey: riskKeys.list(workspaceId) });
    }
    if (selectedId) {
      void queryClient.invalidateQueries({ queryKey: riskKeys.detail(selectedId) });
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
