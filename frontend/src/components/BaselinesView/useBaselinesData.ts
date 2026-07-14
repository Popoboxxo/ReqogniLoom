/**
 * ARCH-L1-001 ReactFrontend — Baselines Data Hook.
 *
 * leaf_id: COMP-RF-002 (BaselinesView)
 * req_id:  REQ-L2-BL-012 (baseline detail), REQ-L1-049 (scope preview),
 *          REQ-L2-BL-003 (field-level diff), REQ-049 (TanStack Query migration),
 *          REQ-050 (Container/Presenter decomposition — data-fetching extraction)
 *
 * TanStack Query replacement for the hand-rolled loaders that used to live in
 * BaselinesView: the baseline + artifact lists, the scope preview, the selected
 * baseline detail, and the create / delete / compare operations. The container
 * keeps only UI + form state and the compare-panel's local diff state.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  baselinesApi,
  type Baseline,
  type BaselineDiff,
  type BaselineScope,
  type ScopePreview,
} from "../../api/baselines";
import { artifactsApi } from "../../api/artifacts";
import type { Artifact } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";

export const baselineKeys = {
  all: ["baselines"] as const,
  list: (workspaceId: string) => ["baselines", "list", workspaceId] as const,
  artifacts: (workspaceId: string) =>
    ["baselines", "artifacts", workspaceId] as const,
  detail: (id: string) => ["baselines", "detail", id] as const,
  scopePreview: (workspaceId: string, scope: string, artifactId: string) =>
    ["baselines", "scopePreview", workspaceId, scope, artifactId] as const,
};

function apiErrorMessage(err: unknown): string {
  return (
    (err as { error?: { message?: string } })?.error?.message ?? String(err)
  );
}

export interface CreateBaselinePayload {
  scope: BaselineScope;
  artifactId: string | null;
}

export interface UseBaselinesDataParams {
  showForm: boolean;
  formScope: BaselineScope;
  formArtifactId: string;
  selectedId: string | null;
}

export interface BaselinesData {
  baselines: Baseline[];
  artifacts: Artifact[];
  isLoading: boolean;
  error: string | null;
  scopePreview: ScopePreview | null;
  scopePreviewLoading: boolean;
  scopePreviewError: string | null;
  detail: Baseline | null;
  detailLoading: boolean;
  detailError: string | null;
  refreshList: () => Promise<void>;
  createBaseline: (payload: CreateBaselinePayload) => Promise<Baseline>;
  deleteBaseline: (id: string) => Promise<void>;
  compareBaselines: (aId: string, bId: string) => Promise<BaselineDiff>;
}

export function useBaselinesData(
  params: UseBaselinesDataParams,
): BaselinesData {
  const { showForm, formScope, formArtifactId, selectedId } = params;
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const baselinesQuery = useQuery({
    queryKey: baselineKeys.list(workspaceId ?? ""),
    queryFn: async () =>
      (await baselinesApi.list(workspaceId as string)).results,
    enabled: !!workspaceId,
  });

  const artifactsQuery = useQuery({
    queryKey: baselineKeys.artifacts(workspaceId ?? ""),
    queryFn: async () =>
      (await artifactsApi.list(workspaceId as string)).results,
    enabled: !!workspaceId,
  });

  // REQ-L1-049: the scope preview only runs while the create form is open, and
  // ``document`` scope additionally requires a chosen artifact.
  const scopePreviewEnabled =
    showForm &&
    !!workspaceId &&
    !(formScope === "document" && !formArtifactId);

  const scopePreviewQuery = useQuery({
    queryKey: baselineKeys.scopePreview(
      workspaceId ?? "",
      formScope,
      formScope === "document" ? formArtifactId : "",
    ),
    queryFn: () =>
      baselinesApi.previewScope({
        scope: formScope,
        workspaceId: workspaceId as string,
        artifactId: formScope === "document" ? formArtifactId : null,
      }),
    enabled: scopePreviewEnabled,
  });

  // REQ-L2-BL-012: load full baseline detail when one is selected and the
  // create form is closed.
  const detailEnabled = !!selectedId && !showForm;
  const detailQuery = useQuery({
    queryKey: baselineKeys.detail(selectedId ?? ""),
    queryFn: () => baselinesApi.get(selectedId as string),
    enabled: detailEnabled,
  });

  const refreshList = async (): Promise<void> => {
    if (!workspaceId) return;
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: baselineKeys.list(workspaceId),
      }),
      queryClient.invalidateQueries({
        queryKey: baselineKeys.artifacts(workspaceId),
      }),
    ]);
  };

  const createMutation = useMutation({
    mutationFn: (payload: CreateBaselinePayload) => {
      if (!workspaceId) {
        return Promise.reject(new Error("no active workspace"));
      }
      return baselinesApi.create({
        workspace_id: workspaceId,
        // ``project`` / ``global`` scopes send ``artifact_id: null``; the
        // backend requires the value only for ``document``.
        artifact_id: payload.scope === "document" ? payload.artifactId : null,
        scope: payload.scope,
      });
    },
    onSuccess: () => void refreshList(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => baselinesApi.delete(id),
    onSuccess: () => void refreshList(),
  });

  const compareMutation = useMutation({
    mutationFn: ({ aId, bId }: { aId: string; bId: string }) =>
      baselinesApi.compare(aId, bId),
  });

  return {
    baselines: baselinesQuery.data ?? [],
    artifacts: artifactsQuery.data ?? [],
    isLoading:
      !!workspaceId &&
      (baselinesQuery.isLoading || artifactsQuery.isLoading),
    error: baselinesQuery.error
      ? apiErrorMessage(baselinesQuery.error)
      : artifactsQuery.error
        ? apiErrorMessage(artifactsQuery.error)
        : deleteMutation.error
          ? apiErrorMessage(deleteMutation.error)
          : null,
    scopePreview: scopePreviewEnabled ? scopePreviewQuery.data ?? null : null,
    scopePreviewLoading: scopePreviewEnabled && scopePreviewQuery.isFetching,
    scopePreviewError: scopePreviewQuery.error
      ? apiErrorMessage(scopePreviewQuery.error)
      : null,
    detail: detailEnabled ? detailQuery.data ?? null : null,
    detailLoading: detailEnabled && detailQuery.isLoading,
    detailError: detailQuery.error
      ? apiErrorMessage(detailQuery.error)
      : null,
    refreshList,
    createBaseline: (payload) => createMutation.mutateAsync(payload),
    deleteBaseline: (id) => deleteMutation.mutateAsync(id),
    compareBaselines: (aId, bId) =>
      compareMutation.mutateAsync({ aId, bId }),
  };
}
