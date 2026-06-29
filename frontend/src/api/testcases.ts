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
import type { ISODateTime, PaginatedResponse, UUID } from "../types";

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
};
