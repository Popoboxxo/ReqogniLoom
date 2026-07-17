/**
 * REQ-176 — Workflow Editor data hook (TanStack Query).
 *
 * Loads the full workflow graph for one entity type and derives the editor
 * model (state classification, edge counts, transition labels). Follows the
 * project's per-view data-hook convention (see useNeedData.ts).
 */

import { useQuery } from "@tanstack/react-query";
import { workflowsApi } from "../../api/workflows";
import type { WorkflowEntityType, WorkflowGraph } from "../../api/workflows";
import { useWorkspace } from "../../context/WorkspaceContext";
import { asError } from "../../queries/query-error";

export const workflowKeys = {
  all: ["workflow-graph"] as const,
  graph: (workspaceId: string, entityType: string) =>
    ["workflow-graph", workspaceId, entityType] as const,
};

export interface WorkflowData {
  graph: WorkflowGraph | null;
  isLoading: boolean;
  error: Error | null;
  refresh: () => void;
}

/**
 * Fetch and derive the workflow graph for ``entityType`` in the active
 * workspace. The query stays disabled until the real workspace has loaded
 * (the context seeds a placeholder UUID first — see useNeedData.ts).
 */
export function useWorkflowData(entityType: WorkflowEntityType): WorkflowData {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;

  const query = useQuery({
    queryKey: workflowKeys.graph(workspaceId ?? "", entityType),
    queryFn: () =>
      workflowsApi.getGraph(entityType, workspaceId as string),
    enabled: !!workspaceId && !isLoadingWorkspace,
  });

  return {
    graph: query.data ?? null,
    isLoading: query.isLoading || isLoadingWorkspace,
    error: query.error ? asError(query.error) : null,
    refresh: () => void query.refetch(),
  };
}
