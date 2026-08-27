/**
 * ARCH-L1-001 ReactFrontend — Memory Visualization API (Memory Admin UI Phase 5).
 *
 * Wraps the System-Admin-only, read-only visualization endpoints:
 *   GET /api/v1/system/memory/entries/     — paginated, full-text-filterable entry list
 *   GET /api/v1/system/memory/projection/  — 2D PCA projection + threshold-based clustering
 *
 * Both endpoints are gated server-side via `MemoryAdminService._assert_system_admin`
 * (see `backend/application/memory_admin_service.py`); this wrapper does no client-side
 * gating of its own, matching `memoryAdmin.ts`'s existing convention for this feature area.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export type MemoryVizScope = "workspace" | "global";
export type MemoryOwnerType = "workspace" | "user";

export interface MemoryEntryRow {
  id: string;
  content: string;
  created_at: string;
  confidence: number;
  owner_type: MemoryOwnerType;
  owner_id: string;
  owner_label: string;
}

export interface MemoryEntriesPage {
  results: MemoryEntryRow[];
  count: number;
  page: number;
  page_size: number;
}

export interface MemoryProjectionPoint {
  id: string;
  x: number;
  y: number;
  cluster_id: number;
  owner_type: MemoryOwnerType;
  owner_id: string;
  owner_label: string;
}

export interface MemoryProjection {
  points: MemoryProjectionPoint[];
  sampled: boolean;
  sample_size: number;
  total_size: number;
  excluded_no_embedding: number;
}

export interface MemoryEntriesQuery {
  scope: MemoryVizScope;
  workspaceId?: UUID;
  page?: number;
  pageSize?: number;
  q?: string;
}

export interface MemoryProjectionQuery {
  scope: MemoryVizScope;
  workspaceId?: UUID;
}

/** Build a `?a=b&c=d` query string, dropping `undefined`/empty-string params. */
function buildQueryString(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      usp.set(key, String(value));
    }
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export const memoryVisualizationApi = {
  /** GET /api/v1/system/memory/entries/ — paginated, full-text-filterable entry list. */
  listEntries(query: MemoryEntriesQuery): Promise<MemoryEntriesPage> {
    const qs = buildQueryString({
      scope: query.scope,
      workspace_id: query.workspaceId,
      page: query.page,
      page_size: query.pageSize,
      q: query.q,
    });
    return apiClient.get<MemoryEntriesPage>(`/system/memory/entries/${qs}`);
  },

  /** GET /api/v1/system/memory/projection/ — 2D PCA projection + clustering. */
  getProjection(query: MemoryProjectionQuery): Promise<MemoryProjection> {
    const qs = buildQueryString({
      scope: query.scope,
      workspace_id: query.workspaceId,
    });
    return apiClient.get<MemoryProjection>(`/system/memory/projection/${qs}`);
  },
};
