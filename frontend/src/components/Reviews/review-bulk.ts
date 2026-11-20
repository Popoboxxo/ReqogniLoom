/**
 * Shared primitives for the Reviews bulk-confirm paths.
 *
 * Extracted from `ReviewsView.tsx` so both the component and the
 * `useReviewBulk` hook can use the same sequential runner and the same
 * with/without-reason transition POST shape without an import cycle.
 */
import {
  workflowTransitionsApi,
  type WorkflowArtifactType,
} from "../../api/workflow-transitions";
import type { ReviewQueueMode } from "./useReviewsData";

/** The two decisions a reviewer can apply to a bulk selection. */
export type ReviewBulkAction = "approve" | "reject";

/** Report of one bulk run; `mode` freezes the queue at run start. */
export interface ReviewBulkResult {
  ok: number;
  failed: number;
  /**
   * Which decision produced the report, so the sentence can name the right
   * verb ("freigegeben" vs "abgelehnt"). Absent on the proposals path.
   */
  action?: ReviewBulkAction;
  mode: ReviewQueueMode;
}

/**
 * Confirm a selection one row at a time and collect failures by id.
 *
 * Sequential on purpose: a rejected item must not abort the remaining rows,
 * and the per-item `onError` capture is what lets the UI report *why* a row
 * failed instead of only showing "N failed".
 */
export async function bulkConfirm(
  ids: readonly string[],
  confirmOne: (id: string) => Promise<unknown>,
  onError?: (id: string, error: unknown) => void,
): Promise<{ confirmed: string[]; failed: string[] }> {
  const confirmed: string[] = [];
  const failed: string[] = [];
  for (const id of ids) {
    try {
      await confirmOne(id);
      confirmed.push(id);
    } catch (error) {
      failed.push(id);
      onError?.(id, error);
    }
  }
  return { confirmed, failed };
}

/**
 * POST one transition, omitting `change_reason` entirely when the reviewer
 * typed nothing. Both bulk paths used to duplicate this branch; keeping the
 * no-reason call shape byte-identical matters for recorded requests.
 */
export async function confirmTransition(
  artifactType: WorkflowArtifactType,
  id: string,
  targetState: string,
  reason: string,
): Promise<void> {
  if (reason.trim()) {
    await workflowTransitionsApi.transition(artifactType, id, targetState, reason);
    return;
  }
  await workflowTransitionsApi.transition(artifactType, id, targetState);
}
