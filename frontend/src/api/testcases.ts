/**
 * ARCH-L1-001 ReactFrontend — TestCases API (A.6, REQ-L1-035).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-035
 *
 * Wraps /api/v1/testcases/ endpoints. Used by the RequirementEditors
 * ``otherRequirements`` dropdown (test cases + requirements share the
 * TraceLink target slot) and by the TestRuns detail view (verifies-chain
 * title resolution).
 */

import { apiClient, getList } from "./client";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  CustomFields,
  ISODateTime,
  PaginatedResponse,
  UUID,
} from "../types";

/** Mirror of the backend TestCaseSerializer (REQ-L2-RA-001). */
export interface TestCase {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
  status: string;
  version: number;
  uid?: string;
  custom_fields?: CustomFields;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

export const testcasesApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<TestCase>> {
    return getList<TestCase>("/testcases/", { workspace_id: workspaceId });
  },

  get(id: UUID): Promise<TestCase> {
    return apiClient.get<TestCase>(`/testcases/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    title: string;
    description?: string;
    status?: string;
  }): Promise<TestCase> {
    return apiClient.post<TestCase>("/testcases/", data);
  },

  update(
    id: UUID,
    data: Partial<Pick<TestCase, "title" | "description" | "status" | "custom_fields">>
  ): Promise<TestCase> {
    return apiClient.patch<TestCase>(`/testcases/${id}/`, data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/testcases/${id}/`);
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/testcases/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two TestCase versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/testcases/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for a TestCase. */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/testcases/${id}/versions/`);
  },
};
