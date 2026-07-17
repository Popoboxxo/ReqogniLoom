/**
 * ARCH-L1-001 ReactFrontend — Test Runs API.
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L2-AS-030 (Test-Run-Protokollierung)
 *
 * Wraps /api/v1/test-runs/ endpoints.
 */

import { apiClient, getAllPages, getList } from "./client";
import type { PaginatedResponse, TestRun, TestRunResult, UUID } from "../types";

export const testRunsApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<TestRun>> {
    return getList<TestRun>("/test-runs/", {
      workspace_id: workspaceId,
    });
  },

  /**
   * Fetch all Test Runs for a workspace, following pagination links until
   * exhaustion (issue C — list() only returned the first page, capped at
   * PAGE_SIZE=25).
   */
  async listAll(workspaceId: UUID): Promise<TestRun[]> {
    return getAllPages<TestRun>("/test-runs/", { workspace_id: workspaceId });
  },

  get(id: UUID): Promise<TestRun> {
    return apiClient.get<TestRun>(`/test-runs/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    name: string;
    ci_job_id?: string;
    test_case_ids?: UUID[];
  }): Promise<TestRun> {
    return apiClient.post<TestRun>("/test-runs/", data);
  },

  close(id: UUID): Promise<TestRun> {
    return apiClient.post<TestRun>(`/test-runs/${id}/close/`, {});
  },

  addResult(
    id: UUID,
    data: {
      test_case_id: UUID;
      status: string;
      message?: string;
      duration_ms?: number | null;
    }
  ): Promise<TestRunResult> {
    return apiClient.post<TestRunResult>(`/test-runs/${id}/results/`, data);
  },

  /**
   * GET /api/v1/test-runs/{id}/results/ — list all per-TestCase execution
   * results for the run (A.6, REQ-L1-035). Each item carries the spec'd
   * `testcase` (nested id+title), `result`, `notes`, `executed_at` and
   * `executed_by` fields alongside the legacy flat fields.
   */
  listResults(id: UUID): Promise<TestRunResult[]> {
    return apiClient.get<TestRunResult[]>(`/test-runs/${id}/results/`);
  },

  addResultsBulk(
    id: UUID,
    results: Array<{
      test_case_id: UUID;
      status: string;
      message?: string;
      duration_ms?: number | null;
    }>
  ): Promise<{ results: TestRunResult[]; count: number }> {
    return apiClient.post<{ results: TestRunResult[]; count: number }>(
      `/test-runs/${id}/results/bulk/`,
      { results }
    );
  },
};
