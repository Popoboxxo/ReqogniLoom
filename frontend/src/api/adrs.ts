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
  // Diff / Versions — stubs (UI standards §4.5 / §11 Backend gaps)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two ADR versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   * TODO(backend): wire to GET /api/v1/adrs/{id}/diff/ (not exposed yet).
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return Promise.reject(
      new Error(
        `Not Implemented: ADR /diff/ endpoint for ${id} (from v${fromVersion} to v${toVersion}) — see UI standards §11.`
      )
    );
  },

  /**
   * Version list for an ADR. The backend does not expose a `/versions/`
   * endpoint for ADRs. DiffPanel will short-circuit to its empty state
   * for ADRs in the meantime.
   * TODO(backend): wire to GET /api/v1/adrs/{id}/versions/.
   */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return Promise.reject(
      new Error(
        `Not Implemented: ADR /versions/ endpoint for ${id} — see UI standards §11.`
      )
    );
  },
};
