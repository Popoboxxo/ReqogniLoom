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

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type RequirementTransitions } from "../../api/requirements";
import {
  type WorkflowArtifactType,
  type WorkflowTransitionResult,
  type WorkflowHistoryEntry,
  type ReviewListItem,
} from "../../api/workflow-transitions";
import { useWorkspace } from "../../context/WorkspaceContext";
import { extractErrorMessage } from "../../api/client";
import { getReviewsResolver } from "./reviewsResolver";

// REQ-144: the review queue only ever shows items in this workflow state.
export const REVIEW_STATE = "in_review";

// Issue #372: Goal/MainGoal (workflow/definition_store.py goal_default /
// main_goal_default) don't have an "in_review" state at all — their
// lifecycle is "Entwurf" -> "Freigegeben" -> "Archiviert", with "Entwurf"
// gated by an approver-only transition (the same approval-gate shape the
// MCP `review.list_pending` tool already recognizes generically). Without
// this override the queue queried `status=in_review` for every type and
// silently returned 0 Goal/MainGoal items even after they were added to
// WorkflowArtifactType, because they never reach that state.
const PENDING_STATE_OVERRIDES: Partial<Record<WorkflowArtifactType, string>> = {
  goal: "Entwurf",
  "main-goal": "Entwurf",
};

function pendingStateFor(type: WorkflowArtifactType): string {
  return PENDING_STATE_OVERRIDES[type] ?? REVIEW_STATE;
}

// REQ-167: the queue is entity-type-agnostic; the requirement queue is the
// default so existing callers (and the REQ-144 tests) keep working unchanged.
const DEFAULT_ARTIFACT_TYPE: WorkflowArtifactType = "requirement";

export const reviewKeys = {
  all: ["reviews"] as const,
  list: (type: WorkflowArtifactType, workspaceId: string) =>
    ["reviews", type, "list", workspaceId] as const,
  transitions: (type: WorkflowArtifactType, id: string) =>
    ["reviews", type, "transitions", id] as const,
  history: (type: WorkflowArtifactType, id: string) =>
    ["reviews", type, "history", id] as const,
};

export interface UseReviewsDataParams {
  /** Currently selected item id, or null when nothing is selected. */
  selectedId: string | null;
  /**
   * Whether to also fetch the workflow history for the selected item
   * (REQ-144 History tab). Defaults to false so the base Details view does
   * not pay for an unused request.
   */
  includeHistory?: boolean;
  /**
   * REQ-167: the entity type whose review queue is shown. Defaults to
   * "requirement" so the historical Requirement-only behavior is preserved.
   */
  artifactType?: WorkflowArtifactType;
}

export interface TransitionArgs {
  targetState: string;
  changeReason?: string;
  credential?: string;
}

export interface ReviewsData {
  items: ReviewListItem[];
  isLoading: boolean;
  error: string | null;
  transitions: RequirementTransitions | null;
  transitionsLoading: boolean;
  history: WorkflowHistoryEntry[];
  historyLoading: boolean;
  historyError: string | null;
  refreshList: () => Promise<void>;
  refreshSelected: () => Promise<void>;
  transition: (args: TransitionArgs) => Promise<WorkflowTransitionResult>;
  diff: (
    id: string,
    fromVersion: number,
    toVersion: number
  ) => Promise<import("../../types").ArtifactDiffResult>;
  versions: (
    id: string
  ) => Promise<import("../../types").ArtifactVersion[]>;
}

export function useReviewsData(params: UseReviewsDataParams): ReviewsData {
  const {
    selectedId,
    includeHistory = false,
    artifactType = DEFAULT_ARTIFACT_TYPE,
  } = params;
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const resolver = useMemo(
    () => getReviewsResolver(artifactType),
    [artifactType]
  );

  const listQuery = useQuery({
    queryKey: reviewKeys.list(artifactType, workspaceId ?? ""),
    queryFn: () => resolver.list(workspaceId as string, pendingStateFor(artifactType)),
    enabled: !!workspaceId,
  });

  const transitionsEnabled = !!selectedId;
  const transitionsQuery = useQuery({
    queryKey: reviewKeys.transitions(artifactType, selectedId ?? ""),
    queryFn: () => resolver.getTransitions(selectedId as string),
    enabled: transitionsEnabled,
  });

  const historyEnabled = !!selectedId && includeHistory;
  const historyQuery = useQuery({
    queryKey: reviewKeys.history(artifactType, selectedId ?? ""),
    queryFn: () => resolver.getWorkflowHistory(selectedId as string),
    enabled: historyEnabled,
  });

  const refreshList = async (): Promise<void> => {
    if (!workspaceId) return;
    await queryClient.invalidateQueries({
      queryKey: reviewKeys.list(artifactType, workspaceId),
    });
  };

  const refreshSelected = async (): Promise<void> => {
    if (!selectedId) return;
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: reviewKeys.transitions(artifactType, selectedId),
      }),
      queryClient.invalidateQueries({
        queryKey: reviewKeys.history(artifactType, selectedId),
      }),
    ]);
  };

  const transitionMutation = useMutation({
    mutationFn: ({ targetState, changeReason, credential }: TransitionArgs) => {
      if (!selectedId) {
        return Promise.reject(new Error("no item selected"));
      }
      return resolver.transition(
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
    items: listQuery.data ?? [],
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
    diff: (id, fromVersion, toVersion) =>
      resolver.diff(id, fromVersion, toVersion),
    versions: (id) => resolver.versions(id),
  };
}
