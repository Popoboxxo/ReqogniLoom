/**
 * ARCH-L1-001 ReactFrontend — Memory Admin API (Memory Admin UI Phase 1).
 *
 * Wraps the System-Admin-only endpoints:
 *   GET    /api/v1/system/memory/workspaces/           — per-workspace overview
 *   DELETE /api/v1/system/memory/workspaces/<uuid>/     — delete both memory tiers
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export interface WorkspaceMemoryOverviewRow {
  workspace_id: UUID;
  workspace_name: string;
  enabled: boolean;
  workspace_entry_count: number;
  user_entry_count: number;
  last_consolidated_at: string | null;
}

export interface WorkspaceMemoryDeleteResult {
  workspace_id: UUID;
  workspace_memory_deleted: number;
  user_memory_deleted: number;
}

export const memoryAdminApi = {
  listWorkspaceOverview(): Promise<{ results: WorkspaceMemoryOverviewRow[] }> {
    return apiClient.get<{ results: WorkspaceMemoryOverviewRow[] }>(
      "/system/memory/workspaces/"
    );
  },

  deleteWorkspaceMemory(workspaceId: UUID): Promise<WorkspaceMemoryDeleteResult> {
    return apiClient.delete<WorkspaceMemoryDeleteResult>(
      `/system/memory/workspaces/${workspaceId}/`
    );
  },
};
