/**
 * ARCH-L1-001 ReactFrontend — TestRuns Data Hook.
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L2-AS-030 (Test-Run-Protokollierung),
 *          REQ-049 (TanStack Query migration),
 *          REQ-050 (Container/Presenter decomposition — data-fetching extraction)
 *
 * TanStack Query replacement for the hand-rolled fetch/loading/error state that
 * used to live inline in TestRunsList. Owns three queries (run list, selected
 * run detail, assignable test cases for the create form) plus the create
 * mutation. The container keeps only UI state (selection, form fields).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { testRunsApi } from "../../api/test-runs";
import { testcasesApi } from "../../api/testcases";
import type { TestCase } from "../../api/testcases";
import type { TestRun, UUID } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";

export const testRunKeys = {
  all: ["testRuns"] as const,
  list: (workspaceId: string) => ["testRuns", "list", workspaceId] as const,
  detail: (id: string) => ["testRuns", "detail", id] as const,
  testCaseOptions: (workspaceId: string) =>
    ["testRuns", "testCaseOptions", workspaceId] as const,
};

/** Extract a `{ error: { message } }`-shaped API error message, if present. */
function apiErrorMessage(err: unknown): string | null {
  const msg = (err as { error?: { message?: string } })?.error?.message;
  return msg ?? null;
}

export interface CreateTestRunPayload {
  workspace_id: UUID;
  name: string;
  ci_job_id?: string;
  test_case_ids?: UUID[];
}

export interface TestRunsData {
  items: TestRun[];
  isLoading: boolean;
  loadError: string | null;
  selectedRun: TestRun | null;
  updateSelectedRun: (run: TestRun) => void;
  refreshList: () => Promise<void>;
  testCaseOptions: TestCase[];
  testCaseOptionsLoading: boolean;
  testCaseOptionsError: string | null;
  createTestRun: (payload: CreateTestRunPayload) => Promise<TestRun>;
  isCreating: boolean;
  createError: string | null;
  resetCreateError: () => void;
}

export function useTestRunsData(
  selectedId: string | null,
  createFormOpen: boolean,
): TestRunsData {
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: testRunKeys.list(workspaceId ?? ""),
    queryFn: async () => (await testRunsApi.list(workspaceId as string)).results,
    enabled: !!workspaceId && !isLoadingWorkspace,
  });

  const detailQuery = useQuery({
    queryKey: testRunKeys.detail(selectedId ?? ""),
    queryFn: () => testRunsApi.get(selectedId as string),
    enabled: !!selectedId,
  });

  // Assignable test cases are only needed while the create form is open (C4).
  const optionsQuery = useQuery({
    queryKey: testRunKeys.testCaseOptions(workspaceId ?? ""),
    queryFn: async () =>
      (await testcasesApi.list(workspaceId as string)).results,
    enabled: !!workspaceId && !isLoadingWorkspace && createFormOpen,
  });

  const createMutation = useMutation({
    mutationFn: (payload: CreateTestRunPayload) => testRunsApi.create(payload),
    onSuccess: () => {
      if (workspaceId) {
        void queryClient.invalidateQueries({
          queryKey: testRunKeys.list(workspaceId),
        });
      }
    },
  });

  const refreshList = async (): Promise<void> => {
    if (workspaceId) {
      await queryClient.invalidateQueries({
        queryKey: testRunKeys.list(workspaceId),
      });
    }
  };

  return {
    items: listQuery.data ?? [],
    // Loading until the workspace is known and the list has resolved.
    isLoading: isLoadingWorkspace || !workspaceId || listQuery.isLoading,
    loadError: listQuery.error
      ? apiErrorMessage(listQuery.error)
      : detailQuery.error
        ? apiErrorMessage(detailQuery.error)
        : null,
    selectedRun: selectedId ? detailQuery.data ?? null : null,
    // Detail edits (e.g. close-in-place) update the cache so the panel stays
    // mounted with the new status instead of being replaced (REQ-012).
    updateSelectedRun: (run) =>
      queryClient.setQueryData(testRunKeys.detail(run.id), run),
    refreshList,
    testCaseOptions: optionsQuery.data ?? [],
    testCaseOptionsLoading: optionsQuery.isFetching,
    testCaseOptionsError: optionsQuery.error
      ? apiErrorMessage(optionsQuery.error)
      : null,
    createTestRun: (payload) => createMutation.mutateAsync(payload),
    isCreating: createMutation.isPending,
    createError: createMutation.error
      ? apiErrorMessage(createMutation.error) ?? String(createMutation.error)
      : null,
    resetCreateError: () => createMutation.reset(),
  };
}
