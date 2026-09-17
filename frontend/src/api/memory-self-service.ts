/**
 * ARCH-L1-001 ReactFrontend — Memory self-service API.
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * Wraps /api/v1/memory/me/ (MemorySelfServiceView, Memory Admin UI Phase 4).
 * GDPR-style self-service over the caller's OWN UserTenantMemory rows only —
 * never WorkspaceMemory (team-owned, managed exclusively by the System-Admin
 * "Memory" tab / MemoryAdminService).
 */

import { apiClient } from "./client";

export interface MemorySelfServiceOverview {
  entry_count: number;
  last_updated_at: string | null;
}

export interface MemorySelfServiceDeleteResult {
  deleted: number;
}

export const memorySelfServiceApi = {
  /** GET /api/v1/memory/me/ — the caller's own UserTenantMemory overview. */
  get(): Promise<MemorySelfServiceOverview> {
    return apiClient.get<MemorySelfServiceOverview>("/memory/me/");
  },

  /** DELETE /api/v1/memory/me/ — deletes all of the caller's own memory. */
  deleteAll(): Promise<MemorySelfServiceDeleteResult> {
    return apiClient.delete<MemorySelfServiceDeleteResult>("/memory/me/");
  },
};
