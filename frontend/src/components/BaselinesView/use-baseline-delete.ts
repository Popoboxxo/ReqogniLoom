/**
 * ARCH-L1-001 ReactFrontend — baseline delete confirmation (#598 S2, UI-20).
 *
 * Extracted from `BaselinesView.tsx`: the pending-delete target and its two
 * actions. The delete mutation stays in the data hook; this module only owns
 * the confirmation lifecycle.
 *
 * Contract kept verbatim: the confirmation goes through the shared
 * `<ConfirmDialog>` (i18n + focus trap), and clearing the selection after a
 * successful delete is the caller's job.
 */

import { useCallback, useState } from "react";

export interface UseBaselineDeleteOptions {
  /** Deletes one baseline; errors surface through the data hook. */
  deleteBaseline: (id: string) => Promise<unknown>;
  /** Called after a successful delete (e.g. clear the selection). */
  onDeleted: (id: string) => void;
}

export interface UseBaselineDeleteResult {
  pendingDeleteId: string | null;
  requestDelete: (id: string) => void;
  cancelDelete: () => void;
  confirmDelete: () => void;
}

export function useBaselineDelete({
  deleteBaseline,
  onDeleted,
}: UseBaselineDeleteOptions): UseBaselineDeleteResult {
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      try {
        await deleteBaseline(id);
        onDeleted(id);
      } catch {
        // Failure surfaces via the data hook's `error` (delete mutation error).
      }
    },
    [deleteBaseline, onDeleted]
  );

  const requestDelete = useCallback((id: string): void => {
    setPendingDeleteId(id);
  }, []);

  const cancelDelete = useCallback((): void => {
    setPendingDeleteId(null);
  }, []);

  const confirmDelete = useCallback((): void => {
    if (!pendingDeleteId) return;
    const id = pendingDeleteId;
    setPendingDeleteId(null);
    void handleDelete(id);
  }, [pendingDeleteId, handleDelete]);

  return { pendingDeleteId, requestDelete, cancelDelete, confirmDelete };
}
