/**
 * ARCH-L1-001 ReactFrontend — Baselines API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L1-018 (Baselines), REQ-L2-RF-007 (Preset-gated visibility)
 *          REQ-L1-049 (Baseline scope-select with 3 scopes)
 *
 * Wraps /api/v1/baselines/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { PaginatedResponse, UUID, ISODateTime } from "../types";

export type BaselineScope = "document" | "project" | "global";

export interface Baseline {
  id: UUID;
  workspace_id: UUID;
  name: string;
  scope: string;
  description: string;
  artifact_id: UUID | null;
  version: number;
  created_at: ISODateTime;
}

export interface ScopePreviewItem {
  id: string;
  title: string;
  type: string;
  entity_type?: string;
}

export interface ScopePreview {
  scope: BaselineScope | string;
  count: number;
  sample: ScopePreviewItem[];
}

export const baselinesApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Baseline>> {
    return getList<Baseline>("/baselines/", {
      workspace_id: workspaceId,
    });
  },

  get(id: UUID): Promise<Baseline> {
    return apiClient.get<Baseline>(`/baselines/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    name: string;
    scope?: string;
    description?: string;
    artifact_id?: UUID | null;
  }): Promise<Baseline> {
    return apiClient.post<Baseline>("/baselines/", data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/baselines/${id}/`);
  },

  /**
   * REQ-L1-049: read-only preview of items a Baseline of the given scope
   * would include. Returns count + sample (max 10 items, each with
   * id/title/type).
   *
   * - scope="global" requires an admin/staff caller; the API returns 403
   *   otherwise.
   * - scope="document" requires ``artifactId``; the API returns 400 if it
   *   is missing.
   */
  previewScope(params: {
    scope: BaselineScope | string;
    workspaceId: UUID;
    artifactId?: UUID | null;
  }): Promise<ScopePreview> {
    const query: Record<string, string> = {
      scope: String(params.scope),
      workspace_id: String(params.workspaceId),
    };
    if (params.artifactId) {
      query.artifact_id = String(params.artifactId);
    }
    const qs = new URLSearchParams(query).toString();
    return apiClient.get<ScopePreview>(
      `/baselines/scope-preview/${qs ? `?${qs}` : ""}`
    );
  },
};
