/**
 * ARCH-L1-001 ReactFrontend — ICD Data Hook.
 *
 * leaf_id: COMP-RF-001 (IcdView)
 * req_id:  REQ-L2-ICD-001 (ICD CRUD + immutable versioning),
 *          REQ-014 (two-phase load — ICD tree before architecture elements),
 *          REQ-049 (TanStack Query migration),
 *          REQ-050 (Container/Presenter decomposition — data-fetching extraction)
 *
 * TanStack Query replacement for the hand-rolled loaders that used to live in
 * IcdView. The ICD list and the architecture-element list are independent
 * queries, so the ICD tree renders as soon as its query resolves while the
 * (slower) architecture list keeps loading in the background (REQ-014).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  icdsApi,
  type CreateIcdPayload,
  type Icd,
  type IcdDetail,
  type NewVersionPayload,
} from "../../api/icds";
import { architectureApi } from "../../api/architecture";
import type { ArchitectureElement } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";
import { extractErrorMessage } from "./icd-view-shared";

export const icdKeys = {
  all: ["icds"] as const,
  list: (workspaceId: string) => ["icds", "list", workspaceId] as const,
  architecture: (workspaceId: string) =>
    ["icds", "architecture", workspaceId] as const,
  detail: (id: string) => ["icds", "detail", id] as const,
};

export interface IcdData {
  icds: Icd[];
  architectureElements: ArchitectureElement[];
  isLoading: boolean;
  isLoadingArch: boolean;
  isLoadingDetail: boolean;
  error: string | null;
  selectedDetail: IcdDetail | null;
  refreshList: () => Promise<void>;
  refreshDetail: () => Promise<void>;
  createIcd: (
    payload: Omit<CreateIcdPayload, "workspace_id">,
  ) => Promise<IcdDetail>;
  createVersion: (
    id: string,
    payload: NewVersionPayload,
  ) => Promise<IcdDetail>;
}

export function useIcdData(routeId?: string): IcdData {
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  // Phase 1 (REQ-014): ICDs load fast so the tree appears immediately.
  const listQuery = useQuery({
    queryKey: icdKeys.list(workspaceId ?? ""),
    queryFn: async () => (await icdsApi.list(workspaceId as string)).results,
    enabled: !!workspaceId,
  });

  // Phase 2 (REQ-014): architecture elements load in the background and feed
  // the source/target dropdowns. Fetched exhaustively via listAll (B-ICD-004).
  const archQuery = useQuery({
    queryKey: icdKeys.architecture(workspaceId ?? ""),
    queryFn: () => architectureApi.listAll(workspaceId as string),
    enabled: !!workspaceId,
  });

  const detailQuery = useQuery({
    queryKey: icdKeys.detail(routeId ?? ""),
    queryFn: () => icdsApi.get(routeId as string),
    enabled: !!routeId,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Omit<CreateIcdPayload, "workspace_id">) => {
      if (!workspaceId) {
        return Promise.reject(new Error("no active workspace"));
      }
      return icdsApi.create({ ...payload, workspace_id: workspaceId });
    },
    onSuccess: () => {
      if (workspaceId) {
        void queryClient.invalidateQueries({
          queryKey: icdKeys.list(workspaceId),
        });
      }
    },
  });

  const versionMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: NewVersionPayload }) =>
      icdsApi.createVersion(id, payload),
    onSuccess: (_data, { id }) => {
      if (workspaceId) {
        void queryClient.invalidateQueries({
          queryKey: icdKeys.list(workspaceId),
        });
      }
      void queryClient.invalidateQueries({ queryKey: icdKeys.detail(id) });
    },
  });

  const refreshList = async (): Promise<void> => {
    if (workspaceId) {
      await queryClient.invalidateQueries({
        queryKey: icdKeys.list(workspaceId),
      });
    }
  };

  const refreshDetail = async (): Promise<void> => {
    if (routeId) {
      await queryClient.invalidateQueries({
        queryKey: icdKeys.detail(routeId),
      });
    }
  };

  const failedQuery = listQuery.error ?? detailQuery.error;

  return {
    icds: listQuery.data ?? [],
    architectureElements: archQuery.data ?? [],
    // Loading until the workspace is known and the ICD list has resolved.
    isLoading: !workspaceId || listQuery.isLoading,
    isLoadingArch: archQuery.isFetching,
    isLoadingDetail: !!routeId && detailQuery.isLoading,
    error: failedQuery ? extractErrorMessage(failedQuery, "Load failed") : null,
    selectedDetail: routeId ? detailQuery.data ?? null : null,
    refreshList,
    refreshDetail,
    createIcd: (payload) => createMutation.mutateAsync(payload),
    createVersion: (id, payload) =>
      versionMutation.mutateAsync({ id, payload }),
  };
}
