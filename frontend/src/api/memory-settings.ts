/**
 * ARCH-L1-001 ReactFrontend — AI Long-Term Memory settings API (Spec
 * 2026-08-24, Task 11).
 *
 * Wraps:
 *   GET/PUT /api/v1/workspaces/{workspaceId}/memory-settings/  — any workspace
 *     member may GET; editor+ may PUT.
 *
 * A workspace with no settings row yet returns `{ enabled: true }` (the
 * memory feature defaults ON — see backend `WorkspaceMemorySettingsView`
 * docstring), so callers never have to special-case a missing row.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export interface MemorySettings {
  enabled: boolean;
}

export const memorySettingsApi = {
  /** GET /api/v1/workspaces/{workspaceId}/memory-settings/ — any workspace member. */
  async get(workspaceId: UUID): Promise<MemorySettings> {
    return apiClient.get<MemorySettings>(`/workspaces/${workspaceId}/memory-settings/`);
  },

  /** PUT /api/v1/workspaces/{workspaceId}/memory-settings/ — editor or admin. */
  async update(workspaceId: UUID, enabled: boolean): Promise<MemorySettings> {
    return apiClient.put<MemorySettings>(`/workspaces/${workspaceId}/memory-settings/`, {
      enabled,
    });
  },
};
