/**
 * ARCH-L1-001 ReactFrontend — Baselines API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L1-018 (Baselines), REQ-L2-RF-007 (Preset-gated visibility)
 *
 * Wraps /api/v1/baselines/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { PaginatedResponse, UUID, ISODateTime } from "../types";

export interface Baseline {
  id: UUID;
  workspace_id: UUID;
  artifact_id: UUID;
  scope: string;
  version: number;
  created_at: ISODateTime;
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
    artifact_id: UUID;
    scope?: string;
  }): Promise<Baseline> {
    return apiClient.post<Baseline>("/baselines/", data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/baselines/${id}/`);
  },
};
