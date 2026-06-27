/**
 * ARCH-L1-001 ReactFrontend — Issues API.
 *
 * leaf_id: COMP-RF-003 (Issue editors)
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Wraps /api/v1/issues/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Issue, PaginatedResponse, UUID } from "../types";

export const issuesApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Issue>> {
    return getList<Issue>("/issues/", {
      workspace_id: workspaceId,
    });
  },

  get(id: UUID): Promise<Issue> {
    return apiClient.get<Issue>(`/issues/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    severity?: string;
    description?: string;
    category?: string;
    tags?: string[];
    status?: string;
  }): Promise<Issue> {
    return apiClient.post<Issue>("/issues/", data);
  },

  update(
    id: UUID,
    data: Partial<Pick<Issue, "title" | "description" | "severity" | "category" | "status" | "tags">>
  ): Promise<Issue> {
    return apiClient.patch<Issue>(`/issues/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/issues/${id}/`);
  },
};
