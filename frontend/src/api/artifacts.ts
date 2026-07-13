/**
 * ARCH-L1-001 ReactFrontend — Artifacts API.
 *
 * leaf_id: COMP-RF-001 (SidebarNavigation / ArtifactTree)
 * req_id:  REQ-L2-RF-005 (Artefakt-Navigation)
 *
 * Wraps /api/v1/artifacts/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Artifact, PaginatedResponse, UUID } from "../types";

export const artifactsApi = {
  list(workspaceId: UUID, parentId?: UUID): Promise<PaginatedResponse<Artifact>> {
    const params: Record<string, string> = { workspace_id: workspaceId };
    if (parentId) params["parent_id"] = parentId;
    return getList<Artifact>("/artifacts/", params);
  },

  get(id: UUID): Promise<Artifact> {
    return apiClient.get<Artifact>(`/artifacts/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    artifact_type: string;
    parent_id?: UUID;
  }): Promise<Artifact> {
    return apiClient.post<Artifact>("/artifacts/", data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/artifacts/${id}/`);
  },
};
