/**
 * ARCH-L1-001 ReactFrontend — Workspace Context Graph settings API (Issue #377, Task 9).
 *
 * Wraps the workspace-scoped backend endpoints:
 *   GET  /api/v1/workspaces/<id>/context-graph-settings/          -> current status
 *   PUT  /api/v1/workspaces/<id>/context-graph-settings/          -> enable/disable
 *   POST /api/v1/workspaces/<id>/context-graph-settings/rebuild/  -> manual rebuild (async)
 *
 * A workspace with no settings row yet returns defaults (enabled: false) —
 * GET never creates a row (see backend ContextGraphSettingsView docstring).
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export interface ContextGraphSettings {
  enabled: boolean;
  enabled_generators: string[];
  provider: string;
  last_projected_at: string | null;
  last_refresh_at: string | null;
  last_error: string;
  node_count: number;
  edge_count: number;
}

export interface ContextGraphSettingsUpdate {
  enabled: boolean;
  enabled_generators?: string[];
}

export const contextGraphSettingsApi = {
  async get(workspaceId: UUID): Promise<ContextGraphSettings> {
    return apiClient.get<ContextGraphSettings>(
      `/workspaces/${workspaceId}/context-graph-settings/`
    );
  },

  async update(
    workspaceId: UUID,
    payload: ContextGraphSettingsUpdate
  ): Promise<ContextGraphSettings> {
    return apiClient.put<ContextGraphSettings>(
      `/workspaces/${workspaceId}/context-graph-settings/`,
      payload
    );
  },

  /** Manually trigger a rebuild (async — 202, does not touch `enabled`). */
  async rebuild(workspaceId: UUID): Promise<void> {
    await apiClient.post<void>(
      `/workspaces/${workspaceId}/context-graph-settings/rebuild/`,
      {}
    );
  },
};
