/**
 * Bulk-confirm runners for the Reviews page.
 *
 * Extracted from `ReviewsView.tsx` (CCN 89): the two sequential confirm
 * runners (`approve`/`reject` on the review queue, confirm on the proposals
 * queue) are self-contained once the per-item confirm callbacks and the report
 * setters are injected. The component keeps the state, the effect resets and
 * the DOM; this module owns only the async control flow.
 */
import { useCallback } from "react";
import type { TFunction } from "i18next";
import { toUserErrorMessage } from "../../utils/userErrorMessage";
import {
  bulkConfirm,
  type ReviewBulkAction,
  type ReviewBulkResult,
} from "./review-bulk";
import type { ReviewQueueMode } from "./useReviewsData";

export interface UseReviewBulkActionsOptions {
  selectedIds: readonly string[];
  clearSelection: () => void;
  queueMode: ReviewQueueMode;
  /** Reason typed for the item in the detail pane (proposals bulk path only). */
  changeReason: string;
  confirmReviewItem: (id: string, action: ReviewBulkAction) => Promise<void>;
  confirmProposal: (id: string, reason: string) => Promise<void>;
  refreshList: () => Promise<void>;
  setIsActing: (acting: boolean) => void;
  setBulkResult: (result: ReviewBulkResult | null) => void;
  setBulkError: (message: string | null) => void;
  setBulkReason: (reason: string) => void;
  t: TFunction;
}

export interface UseReviewBulkActionsResult {
  runReviewBulk: (action: ReviewBulkAction) => Promise<void>;
  runProposalBulk: () => Promise<void>;
}

export function useReviewBulkActions({
  selectedIds,
  clearSelection,
  queueMode,
  changeReason,
  confirmReviewItem,
  confirmProposal,
  refreshList,
  setIsActing,
  setBulkResult,
  setBulkError,
  setBulkReason,
  t,
}: UseReviewBulkActionsOptions): UseReviewBulkActionsResult {
  /** #1196: one bulk decision over the review-queue selection. */
  const runReviewBulk = useCallback(
    async (action: ReviewBulkAction): Promise<void> => {
      setIsActing(true);
      setBulkError(null);
      try {
        // #1193: collect the cause of every failed item so the reviewer learns
        // *why* instead of only that something failed.
        const failures: string[] = [];
        const { confirmed, failed } = await bulkConfirm(
          selectedIds,
          (id) => confirmReviewItem(id, action),
          (_id, error) => failures.push(toUserErrorMessage(error, t)),
        );
        clearSelection();
        setBulkReason("");
        setBulkResult({
          ok: confirmed.length,
          failed: failed.length,
          action,
          mode: queueMode,
        });
        setBulkError(failures.length > 0 ? failures[0] : null);
        await refreshList();
      } finally {
        setIsActing(false);
      }
    },
    [
      confirmReviewItem,
      selectedIds,
      clearSelection,
      queueMode,
      refreshList,
      setIsActing,
      setBulkResult,
      setBulkError,
      setBulkReason,
      t,
    ],
  );

  /** #1193: confirm the selected proposals as one sequential run. */
  const runProposalBulk = useCallback(async (): Promise<void> => {
    setIsActing(true);
    setBulkError(null);
    try {
      const failures: string[] = [];
      const { confirmed, failed } = await bulkConfirm(
        selectedIds,
        (id) => confirmProposal(id, changeReason),
        (_id, error) => failures.push(toUserErrorMessage(error, t)),
      );
      clearSelection();
      setBulkResult({
        ok: confirmed.length,
        failed: failed.length,
        mode: queueMode,
      });
      setBulkError(failures.length > 0 ? failures[0] : null);
      await refreshList();
    } finally {
      setIsActing(false);
    }
  }, [
    confirmProposal,
    selectedIds,
    changeReason,
    clearSelection,
    queueMode,
    refreshList,
    setIsActing,
    setBulkResult,
    setBulkError,
    t,
  ]);

  return { runReviewBulk, runProposalBulk };
}
