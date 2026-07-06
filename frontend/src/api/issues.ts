/**
 * ARCH-L1-001 ReactFrontend — Issues API.
 *
 * leaf_id: COMP-RF-003 (Issue editors)
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Wraps /api/v1/issues/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Issue, ArtifactDiffResult, ArtifactVersion, PaginatedResponse, UUID } from "../types";

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

  // -----------------------------------------------------------------------
  // Diff / Versions — stubs (UI standards §4.5 / §11 Backend gaps)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Issue versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   * TODO(backend): wire to GET /api/v1/issues/{id}/diff/ (not exposed yet).
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return Promise.reject(
      new Error(
        `Not Implemented: Issue /diff/ endpoint for ${id} (from v${fromVersion} to v${toVersion}) — see UI standards §11.`
      )
    );
  },

  /**
   * Version list for an Issue. The backend does not expose a `/versions/`
   * endpoint for Issues. DiffPanel will short-circuit to its empty state
   * for Issues in the meantime.
   * TODO(backend): wire to GET /api/v1/issues/{id}/versions/.
   */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return Promise.reject(
      new Error(
        `Not Implemented: Issue /versions/ endpoint for ${id} — see UI standards §11.`
      )
    );
  },
};
