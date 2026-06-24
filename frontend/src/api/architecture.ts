/**
 * ARCH-L1-001 ReactFrontend — ArchitectureElements API.
 *
 * leaf_id: COMP-RF-004 (ArchitectureEditors)
 * req_id:  REQ-L2-RF-004 (Architecture-Editor)
 *
 * Wraps /api/v1/architecture/ endpoints.
 * NOTE: Backend route is /api/v1/architecture/ (not /architecture-elements/).
 */

import { apiClient, getList } from "./client";
import type { ArchitectureElement, PaginatedResponse, UUID } from "../types";

export const architectureApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<ArchitectureElement>> {
    return getList<ArchitectureElement>("/architecture/", {
      workspace_id: workspaceId,
    });
  },

  get(id: UUID): Promise<ArchitectureElement> {
    return apiClient.get<ArchitectureElement>(`/architecture/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    description?: string;
    element_type?: string;
  }): Promise<ArchitectureElement> {
    return apiClient.post<ArchitectureElement>("/architecture/", data);
  },

  update(
    id: UUID,
    data: Partial<
      Pick<ArchitectureElement, "title" | "description" | "element_type">
    >
  ): Promise<ArchitectureElement> {
    return apiClient.patch<ArchitectureElement>(`/architecture/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/architecture/${id}/`);
  },
};
