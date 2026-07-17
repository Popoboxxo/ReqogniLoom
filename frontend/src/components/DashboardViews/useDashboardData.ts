/**
 * ARCH-L1-001 ReactFrontend — Dashboard Data Hook.
 *
 * leaf_id: COMP-RF-002 (DashboardViews)
 * req_id:  REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken),
 *          REQ-L2-RF-002 (Dashboard),
 *          REQ-L2-RF-012 (Workspace-Konfigurations-UI),
 *          REQ-119 (React-Query-Migration der letzten use*Data-Hooks)
 *
 * Loads the workspace list from WorkspaceContext (sourced from
 * GET /api/v1/workspaces/) and augments each workspace with
 * requirement counts via GET /api/v1/requirements/?workspace_id=...
 *
 * Uses TanStack Query with the same `requirementKeys.list(workspaceId)`
 * cache key that useCreateRequirement/useUpdateRequirement/
 * useDeleteRequirement (queries/requirements.ts) invalidate on success.
 * That makes the dashboard metrics re-fetch automatically whenever a
 * requirement is created, updated, or deleted — no manual refresh needed.
 *
 * If no workspaces are available the hook returns an empty list.
 */

import { useQueries } from "@tanstack/react-query";
import type { Workspace, WorkspaceWithMetrics } from "../../types";
import { requirementsApi } from "../../api/requirements";
import { useWorkspace } from "../../context/WorkspaceContext";
import { requirementKeys } from "../../queries/requirements";

export interface DashboardData {
  workspaces: WorkspaceWithMetrics[];
  isLoading: boolean;
  error: string | null;
}

export function useDashboardData(): DashboardData {
  const { workspaces, activeWorkspace, isLoadingWorkspace } = useWorkspace();

  // Use real workspaces when available, otherwise fall back to the
  // single activeWorkspace (legacy / offline mode).
  const source: Workspace[] =
    workspaces.length > 0
      ? workspaces
      : activeWorkspace
      ? [activeWorkspace]
      : [];

  const requirementQueries = useQueries({
    queries: source.map((ws) => ({
      queryKey: requirementKeys.list(ws.id),
      queryFn: () => requirementsApi.listAll(ws.id),
      enabled: !isLoadingWorkspace,
    })),
  });

  if (isLoadingWorkspace) {
    return { workspaces: [], isLoading: true, error: null };
  }

  if (source.length === 0) {
    return { workspaces: [], isLoading: false, error: null };
  }

  const isLoading = requirementQueries.some((q) => q.isLoading);

  if (isLoading) {
    return { workspaces: [], isLoading: true, error: null };
  }

  const enriched: WorkspaceWithMetrics[] = source.map((ws, index) => {
    const query = requirementQueries[index];
    // Per-workspace failure → zero metrics, don't break the whole dashboard.
    const requirements = query.isError ? [] : query.data ?? [];
    return {
      ...ws,
      requirement_count: requirements.length,
      open_item_count: requirements.filter((r) => r.status === "draft").length,
    };
  });

  return { workspaces: enriched, isLoading, error: null };
}
