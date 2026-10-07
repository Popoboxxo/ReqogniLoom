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
import { reviewsApi } from "../../api/reviews";
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

/** Which queue the review list shows. */
export type ReviewQueueMode = "review" | "proposals";

/**
 * Workflow state the queue lists for a given artifact type and mode.
 *
 * In "proposals" mode the state is the same literal for every type — the
 * proposal state is injected into every non-minimal graph under one name
 * (backend/workflow/definition_store.py PROPOSED_STATE), so no per-type
 * override table is needed here.
 */
export function pendingStateFor(
  type: WorkflowArtifactType,
  mode: ReviewQueueMode = "review",
): string {
  if (mode === "proposals") return "proposed";
  return PENDING_STATE_OVERRIDES[type] ?? REVIEW_STATE;
}

// REQ-167: the queue is entity-type-agnostic; the requirement queue is the
// default so existing callers (and the REQ-144 tests) keep working unchanged.
const DEFAULT_ARTIFACT_TYPE: WorkflowArtifactType = "requirement";

export const reviewKeys = {
  all: ["reviews"] as const,
  list: (
    type: WorkflowArtifactType,
    workspaceId: string,
    mode: ReviewQueueMode = "review",
  ) => ["reviews", type, "list", workspaceId, mode] as const,
  transitions: (type: WorkflowArtifactType, id: string) =>
    ["reviews", type, "transitions", id] as const,
  history: (type: WorkflowArtifactType, id: string) =>
    ["reviews", type, "history", id] as const,
  /**
   * Separate key for the *always-on* proposal count (#1089).
   *
   * Deliberately not part of `list`: that key is scoped by `mode`, so reusing
   * it would make the count query and the visible queue fight over one cache
   * entry and flip the rendered list as the user toggles. The count is a
   * separate question ("is anything waiting in the other queue?") and gets its
   * own entry.
   */
  proposalCount: (type: WorkflowArtifactType, workspaceId: string) =>
    ["reviews", type, "proposal-count", workspaceId] as const,
  /**
   * Aggregate count of *every* pending item in the workspace (#1193).
   *
   * Separate from `list`/`proposalCount` on purpose: those answer "what is in
   * the queue I am looking at", this answers "how much is waiting anywhere".
   * Keyed only by workspace (no artifact type) because that is the whole point
   * — the Reviews UI defaulted to one type and therefore rendered an empty
   * queue even when dozens of approvals were pending under other types.
   */
  pendingTotal: (workspaceId: string) =>
    ["reviews", "pending-total", workspaceId] as const,
  /** Pending count for one artifact type (#1193), derived from the same route. */
  pendingTypeCount: (type: WorkflowArtifactType, workspaceId: string) =>
    ["reviews", type, "pending-count", workspaceId] as const,
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
  /**
   * Spec §4.4: which queue to show — the historical `in_review` queue, or
   * the AI-proposals queue (items in the "proposed" state). Defaults to
   * "review" so existing callers keep their historical behavior.
   */
  queueMode?: ReviewQueueMode;
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
  /**
   * How many items the *other* queue holds for this workspace/type (#1089).
   *
   * Fetched in both modes so the "AI proposals only" toggle can say how many
   * are waiting even while the review queue is on screen. Before this, a user
   * landing on /reviews in the default mode saw an empty proposals queue with
   * no indication that anything was in it — the same "created but never
   * presented" gap the backend fix closes, one layer up.
   */
  pendingProposalCount: number;
  proposalCountLoading: boolean;
  /**
   * Aggregate pending count for the whole workspace across every artifact type
   * (#1193), or `null` while loading / on failure. Drives the "N pending
   * decisions" badge and the "other types still have N" hint. "Pending" is the
   * backend union of approval-gated items and AI proposals — see
   * `reviewsApi.listPendingCount`; the UI copy must say "decisions", never
   * "approvals" (fix F2).
   */
  totalPendingCount: number | null;
  totalPendingCountLoading: boolean;
  /**
   * Pending count in artifact types *other* than the selected one (#1193),
   * `0` when either aggregate count is not yet known. Zero on failure as well:
   * the hint is informational, so a failed count must not surface an error.
   */
  otherTypesPendingCount: number;
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
    queueMode = "review",
  } = params;
  const { activeWorkspace } = useWorkspace();
  const workspaceId = activeWorkspace?.id;
  const queryClient = useQueryClient();

  const resolver = useMemo(
    () => getReviewsResolver(artifactType),
    [artifactType]
  );

  const listQuery = useQuery({
    queryKey: reviewKeys.list(artifactType, workspaceId ?? "", queueMode),
    queryFn: () =>
      resolver.list(workspaceId as string, pendingStateFor(artifactType, queueMode)),
    enabled: !!workspaceId,
  });

  // #1089: the proposals queue is fetched in BOTH modes, so the toggle can
  // report how many AI proposals are waiting. Skipped while the proposals
  // queue is already on screen (that query *is* the answer) — one request
  // either way, never two for the same list.
  const proposalsAreVisible = queueMode === "proposals";
  const proposalCountQuery = useQuery({
    queryKey: reviewKeys.proposalCount(artifactType, workspaceId ?? ""),
    queryFn: () =>
      resolver.list(
        workspaceId as string,
        pendingStateFor(artifactType, "proposals")
      ),
    enabled: !!workspaceId && !proposalsAreVisible,
  });

  // #1193: how many decisions are pending *anywhere* in the workspace, and how
  // many of those sit outside the currently selected artifact type. The first
  // makes the queue honest about its own emptiness; the difference powers the
  // "in other types there are N" hint.
  //
  // Both are best-effort: a failed count degrades to `null`/`0` rather than an
  // error banner, because a badge nobody can act on must never displace the
  // queue's own error state. The count is the union of approval-gated items and
  // AI proposals (see `reviewsApi.listPendingCount`), so the UI labels it
  // "pending decisions" (fix F2).
  const pendingTotalQuery = useQuery({
    queryKey: reviewKeys.pendingTotal(workspaceId ?? ""),
    queryFn: () => reviewsApi.listPendingCount(workspaceId as string),
    enabled: !!workspaceId,
  });
  const pendingTypeCountQuery = useQuery({
    queryKey: reviewKeys.pendingTypeCount(artifactType, workspaceId ?? ""),
    queryFn: () =>
      reviewsApi.listPendingCount(workspaceId as string, artifactType),
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
      queryKey: reviewKeys.list(artifactType, workspaceId, queueMode),
    });
    // The visible list and the cross-queue count answer different keys, so a
    // confirm/approve that empties the proposals queue has to invalidate the
    // count explicitly — otherwise the toggle keeps advertising a number the
    // reviewer can no longer act on.
    await queryClient.invalidateQueries({
      queryKey: reviewKeys.proposalCount(artifactType, workspaceId),
    });
    // #1193: the badge and the "other types" hint are counts over the same
    // queue a transition just changed, so they have to be refetched alongside
    // it — otherwise an approval leaves the total advertising a pending item
    // that is already decided.
    await queryClient.invalidateQueries({
      queryKey: reviewKeys.pendingTotal(workspaceId),
    });
    await queryClient.invalidateQueries({
      queryKey: reviewKeys.pendingTypeCount(artifactType, workspaceId),
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
    // In proposals mode the visible list IS the answer, so the count is read
    // from it; otherwise from the dedicated count query. A failed count query
    // degrades to 0 (the toggle then simply shows no number) rather than
    // surfacing an error banner for a badge nobody needs to act on.
    pendingProposalCount: proposalsAreVisible
      ? (listQuery.data ?? []).length
      : (proposalCountQuery.data ?? []).length,
    proposalCountLoading: proposalsAreVisible
      ? listQuery.isLoading
      : proposalCountQuery.isLoading,
    // #1193: `undefined` (loading or error) collapses to `null` so callers can
    // distinguish "not known yet" from a genuine zero total.
    totalPendingCount: pendingTotalQuery.data ?? null,
    totalPendingCountLoading: pendingTotalQuery.isLoading,
    // Only meaningful when BOTH counts resolved. If the per-type count failed
    // while the total succeeded, subtracting an implicit 0 would over-report
    // the "other types" number with items that are actually in this type.
    otherTypesPendingCount:
      pendingTotalQuery.data !== undefined &&
      pendingTypeCountQuery.data !== undefined
        ? Math.max(0, pendingTotalQuery.data - pendingTypeCountQuery.data)
        : 0,
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
