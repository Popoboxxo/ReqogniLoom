/**
 * ARCH-L1-001 ReactFrontend — Dashboard Data Hook.
 *
 * leaf_id: COMP-RF-002 (DashboardViews)
 * req_id:  REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken),
 *          REQ-L2-RF-002 (Dashboard)
 *
 * ESCALATION NOTE:
 *   GET /api/v1/workspaces/ is NOT implemented in the backend.
 *   The backend URLs only register: artifacts, requirements, architecture,
 *   testcases, tracelinks, baselines, workflows.
 *   WorkspaceWithMetrics data is simulated from the default workspace context.
 *   See dev-result-v1 escalation section.
 *
 * Once /api/v1/workspaces/ is added, replace the mock with:
 *   apiClient.get<PaginatedResponse<WorkspaceWithMetrics>>('/workspaces/')
 */

import { useState, useEffect } from "react";
import type { WorkspaceWithMetrics } from "../../types";
import { requirementsApi } from "../../api/requirements";
import { useWorkspace } from "../../context/WorkspaceContext";

export interface DashboardData {
  workspaces: WorkspaceWithMetrics[];
  isLoading: boolean;
  error: string | null;
}

export function useDashboardData(): DashboardData {
  const { activeWorkspace } = useWorkspace();
  const [data, setData] = useState<DashboardData>({
    workspaces: [],
    isLoading: true,
    error: null,
  });

  useEffect(() => {
    if (!activeWorkspace) {
      setData({ workspaces: [], isLoading: false, error: null });
      return;
    }

    let cancelled = false;

    async function load(): Promise<void> {
      if (!activeWorkspace) return;
      try {
        // Load requirements to compute counts (fallback until /workspaces/ exists)
        const reqResp = await requirementsApi.list(activeWorkspace.id);
        if (cancelled) return;

        const requirements = reqResp.results;
        const openItemCount = requirements.filter(
          (r) => r.status === "draft"
        ).length;

        const workspace: WorkspaceWithMetrics = {
          ...activeWorkspace,
          requirement_count: reqResp.count,
          open_item_count: openItemCount,
        };

        setData({ workspaces: [workspace], isLoading: false, error: null });
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setData({ workspaces: [], isLoading: false, error: msg });
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace]);

  return data;
}
