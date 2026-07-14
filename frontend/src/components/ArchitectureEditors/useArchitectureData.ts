/**
 * ARCH-L1-001 ReactFrontend — Architecture Data Hook.
 *
 * leaf_id: COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L3-RF004-001 (CRUD-Operationen),
 *          REQ-L3-RF004-003 (Verknüpfte Requirements in Seitenleiste),
 *          REQ-049 (TanStack Query migration)
 *
 * TanStack Query replacement for the hand-rolled fetch/loading/error state.
 * The list is fetched exhaustively (listAll) so the decomposition tree can
 * resolve parent_id chains (REQ-001). List errors stay non-fatal — only a
 * failed detail fetch surfaces as `error`, matching the legacy behaviour.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { architectureApi } from "../../api/architecture";
import { tracelinksApi } from "../../api/tracelinks";
import { extractErrorMessage } from "../../api/client";
import type { ArchitectureElement, TraceLink } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";

export const architectureKeys = {
  all: ["architecture"] as const,
  list: (workspaceId: string) => ["architecture", "list", workspaceId] as const,
  detail: (workspaceId: string, id: string) =>
    ["architecture", "detail", workspaceId, id] as const,
};

export interface ArchitectureData {
  elements: ArchitectureElement[];
  element: ArchitectureElement | null;
  linkedTraceLinks: TraceLink[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

interface ArchitectureDetail {
  element: ArchitectureElement;
  linkedTraceLinks: TraceLink[];
}

export function useArchitectureData(selectedId?: string): ArchitectureData {
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: architectureKeys.list(workspaceId ?? ""),
    queryFn: () => architectureApi.listAll(workspaceId as string),
    enabled: !!workspaceId,
  });

  const detailQuery = useQuery<ArchitectureDetail>({
    queryKey: architectureKeys.detail(workspaceId ?? "", selectedId ?? ""),
    queryFn: async () => {
      const element = await architectureApi.get(selectedId as string);
      const links = await tracelinksApi.listForArtifact(
        workspaceId as string,
        element.id
      );
      return { element, linkedTraceLinks: links.results };
    },
    enabled: !!workspaceId && !!selectedId,
  });

  const refresh = (): void => {
    if (workspaceId) {
      void queryClient.invalidateQueries({
        queryKey: architectureKeys.list(workspaceId),
      });
      if (selectedId) {
        void queryClient.invalidateQueries({
          queryKey: architectureKeys.detail(workspaceId, selectedId),
        });
      }
    }
  };

  return {
    elements: listQuery.data ?? [],
    element: selectedId ? detailQuery.data?.element ?? null : null,
    linkedTraceLinks: detailQuery.data?.linkedTraceLinks ?? [],
    // Loading until the workspace is known and the list has resolved.
    isLoading: !workspaceId || listQuery.isLoading,
    // List errors are non-fatal; only detail failures surface.
    error: detailQuery.error ? extractErrorMessage(detailQuery.error) : null,
    refresh,
  };
}
