/**
 * ARCH-L1-001 ReactFrontend — TestCases query/mutation hooks (A.6, REQ-L1-035).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-035
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { testcasesApi, type TestCase } from "../api/testcases";
import type { UUID } from "../types";

export const testcaseKeys = {
  all: ["testcases"] as const,
  lists: () => [...testcaseKeys.all, "list"] as const,
  list: (workspaceId: UUID) => [...testcaseKeys.lists(), workspaceId] as const,
};

export function useTestCasesList(workspaceId: UUID | undefined) {
  return useQuery({
    queryKey: testcaseKeys.list(workspaceId ?? ""),
    queryFn: async (): Promise<TestCase[]> => {
      const resp = await testcasesApi.list(workspaceId as UUID);
      return resp.results;
    },
    enabled: !!workspaceId,
  });
}

export function useCreateTestCase() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof testcasesApi.create>[0]) =>
      testcasesApi.create(data),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({
        queryKey: testcaseKeys.list(created.workspace_id),
      });
    },
  });
}
