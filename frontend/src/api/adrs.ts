/**
 * ARCH-L1-001 ReactFrontend — ADRs API.
 *
 * leaf_id: COMP-RF-003 (ADR editors)
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Wraps /api/v1/adrs/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Adr, ArtifactDiffResult, ArtifactVersion, PaginatedResponse, UUID } from "../types";

export const adrsApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Adr>> {
    return getList<Adr>("/adrs/", {
      workspace_id: workspaceId,
    });
  },

  get(id: UUID): Promise<Adr> {
    return apiClient.get<Adr>(`/adrs/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    description?: string;
    context?: string;
    consequences?: string;
    status?: string;
  }): Promise<Adr> {
    return apiClient.post<Adr>("/adrs/", data);
  },

  update(
    id: UUID,
    data: Partial<Pick<Adr, "title" | "description" | "context" | "consequences" | "status">>
  ): Promise<Adr> {
    return apiClient.patch<Adr>(`/adrs/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/adrs/${id}/`);
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/adrs/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two ADR versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/adrs/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for an ADR. */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/adrs/${id}/versions/`);
  },
};
