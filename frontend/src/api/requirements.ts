/**
 * ARCH-L1-001 ReactFrontend — Requirements API.
 *
 * leaf_id: COMP-RF-003 (RequirementEditors)
 * req_id:  REQ-L2-RF-003 (Requirements-Editor)
 *
 * Wraps /api/v1/requirements/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Requirement, PaginatedResponse, UUID } from "../types";

export const requirementsApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Requirement>> {
    return getList<Requirement>("/requirements/", {
      workspace_id: workspaceId,
    });
  },

  get(id: UUID): Promise<Requirement> {
    return apiClient.get<Requirement>(`/requirements/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    description?: string;
    category?: string;
  }): Promise<Requirement> {
    return apiClient.post<Requirement>("/requirements/", data);
  },

  update(
    id: UUID,
    data: Partial<Pick<Requirement, "title" | "description" | "category" | "change_reason">>
  ): Promise<Requirement> {
    return apiClient.patch<Requirement>(`/requirements/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/requirements/${id}/`);
  },
};
