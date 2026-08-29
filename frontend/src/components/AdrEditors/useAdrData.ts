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
  /**
   * Re-syncs both queries. When the caller already holds the fresh entity
   * (e.g. a mutation's own response body), pass it as `updated` so the
   * detail query's cache is written synchronously via `setQueryData` instead
   * of only being marked stale — UI-LOW-3 (Systemaudit, LOW finding): a
   * plain `invalidateQueries()` still triggers a real network refetch, and
   * until that round trip lands the UI keeps rendering the pre-mutation
   * value (e.g. the ADR-Supersede status badge showing "Approved" for the
   * length of that refetch instead of "Superseded" immediately).
   */
  refresh: (updated?: Adr) => void;
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

  const refresh = (updated?: Adr): void => {
    if (selectedId && updated) {
      // Immediate, synchronous cache write — see the `refresh` doc comment
      // above for why this exists alongside the invalidation below.
      queryClient.setQueryData(adrKeys.detail(selectedId), updated);
    }
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
