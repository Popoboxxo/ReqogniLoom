/**
 * ARCH-L1-001 ReactFrontend — requirement delete workflow (#598 S2, #811).
 *
 * Extracted from `RequirementList.tsx`: the confirm/retry lifecycle of a
 * requirement deletion is independent of the list's search, filter, sort and
 * tree state, so it owns its own module now.
 *
 * Contract that must not regress (#811): the dialog closes **only** on a
 * confirmed successful delete. A rejected delete — typically the missing
 * `change_reason` under the extended preset — keeps the dialog open with the
 * user's input intact so they can supply the reason and retry.
 */

import { useCallback, useState } from "react";

export interface UseRequirementDeleteOptions {
  /** Deletes one requirement; resolves `true` only when the server accepted it. */
  onDelete: (id: string, changeReason?: string) => Promise<boolean>;
  /** Extended preset: a non-empty `change_reason` is mandatory (#811). */
  requiresChangeReason: boolean;
}

export interface UseRequirementDeleteResult {
  confirmDeleteId: string | null;
  deleteChangeReason: string;
  isDeleting: boolean;
  deleteAttempted: boolean;
  requestDelete: (id: string) => void;
  closeDeleteDialog: () => void;
  handleConfirmDelete: () => Promise<void>;
  /** Keeps the "reason required" mark in sync while typing. */
  onReasonChange: (value: string) => void;
}

export function useRequirementDelete({
  onDelete,
  requiresChangeReason,
}: UseRequirementDeleteOptions): UseRequirementDeleteResult {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleteChangeReason, setDeleteChangeReason] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteAttempted, setDeleteAttempted] = useState(false);

  const closeDeleteDialog = useCallback((): void => {
    setConfirmDeleteId(null);
    setDeleteChangeReason("");
    setDeleteAttempted(false);
  }, []);

  const requestDelete = useCallback((id: string): void => {
    setConfirmDeleteId(id);
  }, []);

  const onReasonChange = useCallback((value: string): void => {
    setDeleteChangeReason(value);
    if (deleteAttempted) setDeleteAttempted(false);
  }, [deleteAttempted]);

  /**
   * #811: awaits the result and closes only on confirmed success. On failure
   * the dialog stays open; the caller surfaces the server message in its own
   * `req-action-error` banner above the list.
   */
  const handleConfirmDelete = useCallback(async (): Promise<void> => {
    if (!confirmDeleteId) return;
    if (requiresChangeReason && !deleteChangeReason.trim()) {
      setDeleteAttempted(true);
      return;
    }
    setIsDeleting(true);
    try {
      const succeeded = await onDelete(
        confirmDeleteId,
        deleteChangeReason.trim() || undefined
      );
      if (succeeded) {
        closeDeleteDialog();
      }
    } finally {
      setIsDeleting(false);
    }
  }, [confirmDeleteId, requiresChangeReason, deleteChangeReason, onDelete, closeDeleteDialog]);

  return {
    confirmDeleteId,
    deleteChangeReason,
    isDeleting,
    deleteAttempted,
    requestDelete,
    closeDeleteDialog,
    handleConfirmDelete,
    onReasonChange,
  };
}
