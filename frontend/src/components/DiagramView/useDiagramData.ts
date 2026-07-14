/**
 * ARCH-L1-001 ReactFrontend — Diagram Data Hooks.
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L2-DS-001 (DiagramService REST API),
 *          REQ-049 (TanStack Query migration),
 *          REQ-050 (Container/Presenter decomposition — data-fetching extraction)
 *
 * TanStack Query hooks replacing the hand-rolled fetch/loading state that used
 * to live inline in DiagramView. Split by concern so the container (list),
 * create form (create) and detail presenter (detail + canvas + mutations) each
 * pull only what they need.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  diagramsApi,
  type CreateDiagramPayload,
} from "../../api/diagrams";
import type {
  CanvasStroke,
  Diagram,
  DiagramDetail,
  FabricCanvasJson,
} from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";

export const diagramKeys = {
  all: ["diagrams"] as const,
  list: (workspaceId: string) => ["diagrams", "list", workspaceId] as const,
  detail: (id: string) => ["diagrams", "detail", id] as const,
  canvas: (id: string) => ["diagrams", "canvas", id] as const,
};

function apiErrorMessage(err: unknown): string {
  return (
    (err as { error?: { message?: string } })?.error?.message ?? String(err)
  );
}

export interface DiagramListData {
  items: Diagram[];
  isLoading: boolean;
  refresh: () => Promise<void>;
  deleteDiagram: (id: string) => Promise<void>;
}

/** List query + delete mutation for the DiagramView container. */
export function useDiagramList(): DiagramListData {
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: diagramKeys.list(workspaceId ?? ""),
    queryFn: async () => (await diagramsApi.list(workspaceId as string)).results,
    enabled: !!workspaceId,
  });

  const refresh = async (): Promise<void> => {
    if (workspaceId) {
      await queryClient.invalidateQueries({
        queryKey: diagramKeys.list(workspaceId),
      });
    }
  };

  const deleteMutation = useMutation({
    mutationFn: (id: string) => diagramsApi.delete(id),
    onSuccess: () => void refresh(),
  });

  return {
    items: listQuery.data ?? [],
    isLoading: !workspaceId || listQuery.isLoading,
    refresh,
    deleteDiagram: (id) => deleteMutation.mutateAsync(id),
  };
}

export interface CreateDiagramData {
  createDiagram: (payload: CreateDiagramPayload) => Promise<Diagram>;
  isSaving: boolean;
}

/** Create mutation for the DiagramCreateForm presenter. */
export function useCreateDiagram(): CreateDiagramData {
  const createMutation = useMutation({
    mutationFn: (payload: CreateDiagramPayload) => diagramsApi.create(payload),
  });
  return {
    createDiagram: (payload) => createMutation.mutateAsync(payload),
    isSaving: createMutation.isPending,
  };
}

export interface DiagramDetailData {
  detail: DiagramDetail | null;
  isLoading: boolean;
  canvasJson: FabricCanvasJson | undefined;
  canvasStrokes: CanvasStroke[] | undefined;
  isCanvasLoading: boolean;
  saveContent: (content: string) => Promise<void>;
  deleteDiagram: () => Promise<void>;
  isSaving: boolean;
  saveError: string | null;
  resetSaveError: () => void;
}

/**
 * Detail query + persisted-canvas query + update/delete mutations for the
 * DiagramDetailView presenter. The canvas query only runs for canvas_stroke
 * diagrams; a missing payload is non-fatal (start from an empty surface).
 */
export function useDiagramDetail(diagramId: string): DiagramDetailData {
  const queryClient = useQueryClient();

  const detailQuery = useQuery({
    queryKey: diagramKeys.detail(diagramId),
    queryFn: () => diagramsApi.get(diagramId),
    enabled: !!diagramId,
  });

  const detail = detailQuery.data ?? null;
  const isCanvas = detail?.payload_format === "canvas_stroke";

  const canvasQuery = useQuery({
    queryKey: diagramKeys.canvas(diagramId),
    queryFn: () => diagramsApi.fetchCanvasStrokes(diagramId),
    enabled: !!diagramId && isCanvas,
    // A missing canvas payload is fine — start with an empty surface.
    retry: false,
  });

  const updateMutation = useMutation({
    mutationFn: (content: string) => {
      if (!detail?.payload_format) {
        return Promise.reject(new Error("no payload format"));
      }
      return diagramsApi.update(diagramId, {
        payload_format: detail.payload_format,
        content,
      });
    },
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: diagramKeys.detail(diagramId),
      }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => diagramsApi.delete(diagramId),
  });

  return {
    detail,
    isLoading: !!diagramId && detailQuery.isLoading,
    canvasJson: canvasQuery.data?.canvas_json ?? undefined,
    canvasStrokes: canvasQuery.data?.strokes,
    isCanvasLoading: isCanvas && canvasQuery.isFetching,
    saveContent: async (content) => {
      await updateMutation.mutateAsync(content);
    },
    deleteDiagram: () => deleteMutation.mutateAsync(),
    isSaving: updateMutation.isPending,
    saveError: updateMutation.error ? apiErrorMessage(updateMutation.error) : null,
    resetSaveError: () => updateMutation.reset(),
  };
}
