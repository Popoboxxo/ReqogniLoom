/**
 * ARCH-L1-001 ReactFrontend — Risks API.
 *
 * leaf_id: COMP-RF-003 (Risk editors)
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Wraps /api/v1/risks/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Risk, ArtifactDiffResult, ArtifactVersion, PaginatedResponse, UUID } from "../types";

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

  // -----------------------------------------------------------------------
  // Diff / Versions — stubs (UI standards §4.5 / §11 Backend gaps)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Risk versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   * TODO(backend): wire to GET /api/v1/risks/{id}/diff/ (not exposed yet).
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return Promise.reject(
      new Error(
        `Not Implemented: Risk /diff/ endpoint for ${id} (from v${fromVersion} to v${toVersion}) — see UI standards §11.`
      )
    );
  },

  /**
   * Version list for a Risk. The backend does not expose a `/versions/`
   * endpoint for Risks. DiffPanel will short-circuit to its empty state
   * for Risks in the meantime.
   * TODO(backend): wire to GET /api/v1/risks/{id}/versions/.
   */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return Promise.reject(
      new Error(
        `Not Implemented: Risk /versions/ endpoint for ${id} — see UI standards §11.`
      )
    );
  },
};
