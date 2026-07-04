/**
 * ARCH-L1-001 ReactFrontend — Risks API.
 *
 * leaf_id: COMP-RF-003 (Risk editors)
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Wraps /api/v1/risks/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Risk, PaginatedResponse, UUID } from "../types";

export const risksApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Risk>> {
    return getList<Risk>("/risks/", {
      workspace_id: workspaceId,
    });
  },

  get(id: UUID): Promise<Risk> {
    return apiClient.get<Risk>(`/risks/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    probability?: string;
    impact?: string;
    severity?: string;
    description?: string;
    category?: string;
    owner?: string;
    mitigation_strategy?: string;
    status?: string;
  }): Promise<Risk> {
    return apiClient.post<Risk>("/risks/", data);
  },

  update(
    id: UUID,
    data: Partial<
      Pick<
        Risk,
        | "title"
        | "description"
        | "probability"
        | "impact"
        | "category"
        | "owner"
        | "mitigation_strategy"
        | "severity"
        | "status"
      >
    >
  ): Promise<Risk> {
    return apiClient.patch<Risk>(`/risks/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/risks/${id}/`);
  },
};
