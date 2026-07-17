/**
 * ARCH-L1-001 ReactFrontend — Issues API.
 *
 * leaf_id: COMP-RF-003 (Issue editors)
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API)
 *
 * Wraps /api/v1/issues/ endpoints.
 */

import { apiClient, getAllPages, getList } from "./client";
import type { Issue, ArtifactDiffResult, ArtifactVersion, PaginatedResponse, UUID } from "../types";

export const issuesApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Issue>> {
    return getList<Issue>("/issues/", {
      workspace_id: workspaceId,
    });
  },

  /**
   * Fetch all Issues for a workspace, following pagination links until
   * exhaustion (issue C — list() only returned the first page, capped at
   * PAGE_SIZE=25).
   */
  async listAll(workspaceId: UUID): Promise<Issue[]> {
    return getAllPages<Issue>("/issues/", { workspace_id: workspaceId });
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
    data: Partial<Pick<Issue, "title" | "description" | "severity" | "category" | "status" | "tags">> & {
      /** Extended preset: audit rationale forwarded to the backend audit log. */
      change_reason?: string;
    }
  ): Promise<Issue> {
    return apiClient.patch<Issue>(`/issues/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/issues/${id}/`);
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/issues/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Issue versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/issues/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for an Issue. */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/issues/${id}/versions/`);
  },
};
