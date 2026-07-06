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
    data: Partial<Pick<TestCase, "title" | "description" | "status">>
  ): Promise<TestCase> {
    return apiClient.patch<TestCase>(`/testcases/${id}/`, data);
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — stubs (UI standards §4.5 / §11 Backend gaps)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two TestCase versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   * TODO(backend): wire to GET /api/v1/testcases/{id}/diff/ (not exposed yet).
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return Promise.reject(
      new Error(
        `Not Implemented: TestCase /diff/ endpoint for ${id} (from v${fromVersion} to v${toVersion}) — see UI standards §11.`
      )
    );
  },

  /**
   * Version list for a TestCase. The backend does not expose a
   * `/versions/` endpoint for test cases. DiffPanel will short-circuit
   * to its empty state for TestCase in the meantime.
   * TODO(backend): wire to GET /api/v1/testcases/{id}/versions/.
   */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return Promise.reject(
      new Error(
        `Not Implemented: TestCase /versions/ endpoint for ${id} — see UI standards §11.`
      )
    );
  },
};
