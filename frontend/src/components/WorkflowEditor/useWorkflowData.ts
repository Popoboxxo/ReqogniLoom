/**
 * REQ-176 — Workflow Editor data hook (TanStack Query).
 *
 * Loads the full workflow graph for one entity type and derives the editor
 * model (state classification, edge counts, transition labels). Follows the
 * project's per-view data-hook convention (see useNeedData.ts).
 *
 * REQ-178/179 — the hook is scope-aware: the default ``workspace`` scope reads
 * the per-workspace definition (unchanged behaviour); the ``global`` scope reads
 * the tenant-wide default for a given preset (System Settings → Workflow
 * Defaults). Callers that pass no scope keep the original workspace behaviour.
 */

import { useQuery } from "@tanstack/react-query";
import { workflowsApi } from "../../api/workflows";
import { workflowDefaultsApi } from "../../api/workflow-defaults";
import type { WorkflowEntityType, WorkflowGraph } from "../../api/workflows";
import { useWorkspace } from "../../context/WorkspaceContext";
import { asError } from "../../queries/query-error";
import type { WorkflowScope } from "./constants";

export const workflowKeys = {
  all: ["workflow-graph"] as const,
  workspace: (workspaceId: string) =>
    ["workflow-graph", "workspace", workspaceId] as const,
  graph: (scope: WorkflowScope, entityType: WorkflowEntityType) =>
    scope.kind === "global"
      ? (["workflow-graph", "global", scope.preset, entityType] as const)
      : ([
          "workflow-graph",
          "workspace",
          scope.workspaceId ?? "",
          scope.preset ?? "",
          entityType,
        ] as const),
};

export interface WorkflowData {
  graph: WorkflowGraph | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

/**
 * Fetch and derive the workflow graph for ``entityType``. When no ``scope`` is
 * given, the active workspace scope is used (the query stays disabled until the
 * real workspace has loaded — the context seeds a placeholder UUID first).
 */
export function useWorkflowData(
  entityType: WorkflowEntityType,
  scope?: WorkflowScope
): WorkflowData {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const effectiveScope: WorkflowScope =
    scope ?? {
      kind: "workspace",
      workspaceId: activeWorkspace?.id,
      preset: activeWorkspace?.preset,
    };

  const isGlobal = effectiveScope.kind === "global";
  const workspaceId =
    effectiveScope.kind === "workspace" ? effectiveScope.workspaceId : undefined;

  const query = useQuery({
    queryKey: workflowKeys.graph(effectiveScope, entityType),
    queryFn: () =>
      isGlobal
        ? workflowDefaultsApi.getGraph(entityType, effectiveScope.preset)
        : workflowsApi.getGraph(entityType, workspaceId as string),
    enabled: isGlobal ? true : !!workspaceId && !isLoadingWorkspace,
    // Workspace graphs are provisioned from the active rigor tier. A preset
    // change can happen outside this editor (Workspace Settings), so never
    // serve a cached workspace graph without revalidating it on remount.
    staleTime: isGlobal ? 30_000 : 0,
  });

  return {
    graph: query.data ?? null,
    isLoading: query.isLoading || (!isGlobal && isLoadingWorkspace),
    error: query.error ? asError(query.error) : null,
    refresh: () => void query.refetch(),
  };
}
