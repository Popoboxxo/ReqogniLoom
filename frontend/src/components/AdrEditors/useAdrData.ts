/**
 * ARCH-L1-001 ReactFrontend — ADR Data Hook.
 *
 * req_id: REQ-049 (TanStack Query migration)
 *
 * TanStack Query replacement for the hand-rolled fetch/loading/error state.
 * Query cancellation, error reset on refetch and de-duplication are handled
 * by react-query; the return shape is preserved so AdrEditors is unchanged.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { adrsApi } from "../../api/adrs";
import { useWorkspace } from "../../context/WorkspaceContext";
import { asError } from "../../queries/query-error";
import type { Adr } from "../../types";

export const adrKeys = {
  all: ["adrs"] as const,
  list: (workspaceId: string) => ["adrs", "list", workspaceId] as const,
  detail: (id: string) => ["adrs", "detail", id] as const,
};

export interface AdrData {
  items: Adr[];
  item: Adr | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

export function useAdrData(selectedId?: string): AdrData {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: adrKeys.list(workspaceId ?? ""),
    // Issue C: list() only returned page 1 (PAGE_SIZE=25) — listAll()
    // follows pagination until exhaustion.
    queryFn: async () => adrsApi.listAll(workspaceId as string),
    // Issue B: activeWorkspace starts as the DEFAULT_WORKSPACE placeholder
    // (truthy fake UUID), so !!workspaceId alone fires this query before the
    // real workspace has loaded, hitting the backend with a bogus id (401).
    enabled: !!workspaceId && !isLoadingWorkspace,
  });

  const detailQuery = useQuery({
    queryKey: adrKeys.detail(selectedId ?? ""),
    queryFn: () => adrsApi.get(selectedId as string),
    enabled: !!selectedId,
  });

  const refresh = (): void => {
    if (workspaceId) {
      void queryClient.invalidateQueries({ queryKey: adrKeys.list(workspaceId) });
    }
    if (selectedId) {
      void queryClient.invalidateQueries({ queryKey: adrKeys.detail(selectedId) });
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
