/**
 * ARCH-L1-001 ReactFrontend — Dashboard Data Hook.
 *
 * leaf_id: COMP-RF-002 (DashboardViews)
 * req_id:  REQ-L3-RF002-001 (Workspace-Kartenliste mit Metriken),
 *          REQ-L2-RF-002 (Dashboard),
 *          REQ-L2-RF-012 (Workspace-Konfigurations-UI)
 *
 * Loads the workspace list from WorkspaceContext (sourced from
 * GET /api/v1/workspaces/) and augments each workspace with
 * requirement counts via GET /api/v1/requirements/?workspace_id=...
 *
 * If no workspaces are available the hook returns an empty list.
 */

import { useState, useEffect } from "react";
import type { Workspace, WorkspaceWithMetrics } from "../../types";
import { requirementsApi } from "../../api/requirements";
import { useWorkspace } from "../../context/WorkspaceContext";

export interface DashboardData {
  workspaces: WorkspaceWithMetrics[];
  isLoading: boolean;
  error: string | null;
}

export function useDashboardData(): DashboardData {
  const { workspaces, activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const [data, setData] = useState<DashboardData>({
    workspaces: [],
    isLoading: true,
    error: null,
  });

  useEffect(() => {
    if (isLoadingWorkspace) {
      setData((prev) => ({ ...prev, isLoading: true }));
      return;
    }

    // Use real workspaces when available, otherwise fall back to the
    // single activeWorkspace (legacy / offline mode).
    const source: Workspace[] =
      workspaces.length > 0
        ? workspaces
        : activeWorkspace
        ? [activeWorkspace]
        : [];

    if (source.length === 0) {
      setData({ workspaces: [], isLoading: false, error: null });
      return;
    }

    let cancelled = false;

    async function load(): Promise<void> {
      try {
        const enriched = await Promise.all(
          source.map(async (ws): Promise<WorkspaceWithMetrics> => {
            try {
              const reqResp = await requirementsApi.list(ws.id);
              const openItemCount = reqResp.results.filter(
                (r) => r.status === "draft"
              ).length;
              return {
                ...ws,
                requirement_count: reqResp.count,
                open_item_count: openItemCount,
              };
            } catch {
              // Per-workspace failure → zero metrics, don't break the dashboard
              return {
                ...ws,
                requirement_count: 0,
                open_item_count: 0,
              };
            }
          })
        );

        if (cancelled) return;
        setData({ workspaces: enriched, isLoading: false, error: null });
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaces, activeWorkspace, isLoadingWorkspace]);

  return data;
}
