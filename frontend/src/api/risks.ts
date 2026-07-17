/**
 * ARCH-L1-001 ReactFrontend — Risks API.
 *
 * leaf_id: COMP-RF-003 (Risk editors)
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Wraps /api/v1/risks/ endpoints.
 */

import { apiClient, getAllPages, getList } from "./client";
import type { Risk, ArtifactDiffResult, ArtifactVersion, PaginatedResponse, UUID } from "../types";

export const risksApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Risk>> {
    return getList<Risk>("/risks/", {
      workspace_id: workspaceId,
    });
  },

  /**
   * Fetch all Risks for a workspace, following pagination links until
   * exhaustion (issue C — list() only returned the first page, capped at
   * PAGE_SIZE=25).
   */
  async listAll(workspaceId: UUID): Promise<Risk[]> {
    return getAllPages<Risk>("/risks/", { workspace_id: workspaceId });
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

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/risks/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Risk versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/risks/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for a Risk. */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/risks/${id}/versions/`);
  },
};
