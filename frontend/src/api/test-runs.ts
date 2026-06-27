/**
 * ARCH-L1-001 ReactFrontend — Test Runs API.
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L2-AS-030 (Test-Run-Protokollierung)
 *
 * Wraps /api/v1/test-runs/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { PaginatedResponse, TestRun, TestRunResult, UUID } from "../types";

export const testRunsApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<TestRun>> {
    return getList<TestRun>("/test-runs/", {
      workspace_id: workspaceId,
    });
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
