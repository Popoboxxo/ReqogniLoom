/**
 * ARCH-L1-001 ReactFrontend — Reviews Data Hook.
 *
 * leaf_id: COMP-RF-REV-001 (ReviewsView)
 * req_id:  REQ-144 (Review/Approval UI on top of the REQ-143 WorkflowEngine)
 *
 * TanStack Query data-fetching for the review queue: the list of
 * requirements currently `in_review`, the selected requirement's allowed
 * transitions (REQ-143 contract), its workflow history (REQ-144), and the
 * transition mutation used by the Approve/Reject actions.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  requirementsApi,
  type RequirementTransitionResult,
  type RequirementTransitions,
  type WorkflowHistoryEntry,
} from "../../api/requirements";
import type { Requirement } from "../../types";
import { useWorkspace } from "../../context/WorkspaceContext";
import { extractErrorMessage } from "../../api/client";

// REQ-144: the review queue only ever shows requirements in this state.
export const REVIEW_STATE = "in_review";

export const reviewKeys = {
  all: ["reviews"] as const,
  list: (workspaceId: string) => ["reviews", "list", workspaceId] as const,
  transitions: (id: string) => ["reviews", "transitions", id] as const,
  history: (id: string) => ["reviews", "history", id] as const,
};

export interface UseReviewsDataParams {
  /** Currently selected requirement id, or null when nothing is selected. */
  selectedId: string | null;
  /**
   * Whether to also fetch the workflow history for the selected item
   * (REQ-144 History tab). Defaults to false so the base Details view does
   * not pay for an unused request.
   */
  includeHistory?: boolean;
}

export interface TransitionArgs {
  targetState: string;
  changeReason?: string;
  credential?: string;
}

export interface ReviewsData {
  requirements: Requirement[];
  isLoading: boolean;
  error: string | null;
  transitions: RequirementTransitions | null;
  transitionsLoading: boolean;
  history: WorkflowHistoryEntry[];
  historyLoading: boolean;
  historyError: string | null;
  refreshList: () => Promise<void>;
  refreshSelected: () => Promise<void>;
  transition: (args: TransitionArgs) => Promise<RequirementTransitionResult>;
}

export function useReviewsData(params: UseReviewsDataParams): ReviewsData {
  const { selectedId, includeHistory = false } = params;
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: reviewKeys.list(workspaceId ?? ""),
    queryFn: async () =>
      (await requirementsApi.list(workspaceId as string, REVIEW_STATE))
        .results,
    enabled: !!workspaceId,
  });

  const transitionsEnabled = !!selectedId;
  const transitionsQuery = useQuery({
    queryKey: reviewKeys.transitions(selectedId ?? ""),
    queryFn: () => requirementsApi.getTransitions(selectedId as string),
    enabled: transitionsEnabled,
  });

  const historyEnabled = !!selectedId && includeHistory;
  const historyQuery = useQuery({
    queryKey: reviewKeys.history(selectedId ?? ""),
    queryFn: () => requirementsApi.getWorkflowHistory(selectedId as string),
    enabled: historyEnabled,
  });

  const refreshList = async (): Promise<void> => {
    if (!workspaceId) return;
    await queryClient.invalidateQueries({
      queryKey: reviewKeys.list(workspaceId),
    });
  };

  const refreshSelected = async (): Promise<void> => {
    if (!selectedId) return;
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: reviewKeys.transitions(selectedId),
      }),
      queryClient.invalidateQueries({
        queryKey: reviewKeys.history(selectedId),
      }),
    ]);
  };

  const transitionMutation = useMutation({
    mutationFn: ({ targetState, changeReason, credential }: TransitionArgs) => {
      if (!selectedId) {
        return Promise.reject(new Error("no requirement selected"));
      }
      return requirementsApi.transition(
        selectedId,
        targetState,
        changeReason,
        credential
      );
    },
    onSuccess: async () => {
      await Promise.all([refreshList(), refreshSelected()]);
    },
  });

  return {
    requirements: listQuery.data ?? [],
    isLoading: !!workspaceId && listQuery.isLoading,
    error: listQuery.error ? extractErrorMessage(listQuery.error) : null,
    transitions: transitionsEnabled ? transitionsQuery.data ?? null : null,
    transitionsLoading: transitionsEnabled && transitionsQuery.isLoading,
    history: historyEnabled ? historyQuery.data ?? [] : [],
    historyLoading: historyEnabled && historyQuery.isLoading,
    historyError: historyQuery.error
      ? extractErrorMessage(historyQuery.error)
      : null,
    refreshList,
    refreshSelected,
    transition: (args) => transitionMutation.mutateAsync(args),
  };
}
