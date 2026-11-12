/**
 * ARCH-L1-001 ReactFrontend — memory entry actions (#598 S2, #1296).
 *
 * Extracted from `MemoryPage.tsx`: the row actions (promote, forget) and the
 * "add fact" dialog are independent of the browse list, the filters, the
 * search and the digest.
 *
 * Contract kept verbatim:
 *   - only one row action runs at a time (`busyId`), every row disables while
 *     it does,
 *   - a failed action keeps the list intact, shows its own message and stores
 *     the exact action for the retry control (#1296); a retry with nothing
 *     pending reloads the page instead,
 *   - forget is confirmed in the shared dialog before the request,
 *   - a created fact reloads from page 1.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { memoryApi, type MemoryEntry } from "../../api/memory";
import { formatMemoryErrorMessage } from "./memory-format";

export interface UseMemoryEntryActionsOptions {
  workspaceId: string | undefined;
  /** Page the list is currently on — actions reload the same page. */
  page: number;
  reloadEntries: (page: number) => void;
  t: TFunction;
}

export interface RetryableAction {
  kind: "promote" | "forget";
  entry: MemoryEntry;
}

export interface UseMemoryEntryActionsResult {
  showAddFact: boolean;
  openAddFact: () => void;
  closeAddFact: () => void;
  pendingForget: MemoryEntry | null;
  requestForget: (entry: MemoryEntry) => void;
  cancelForget: () => void;
  busyId: string | null;
  actionError: string | null;
  retryableAction: RetryableAction | null;
  handlePromote: (entry: MemoryEntry) => Promise<void>;
  handleForget: (entry: MemoryEntry) => Promise<void>;
  retryFailedAction: () => void;
  handleCreated: () => void;
}

export function useMemoryEntryActions({
  workspaceId,
  page,
  reloadEntries,
  t,
}: UseMemoryEntryActionsOptions): UseMemoryEntryActionsResult {
  const [showAddFact, setShowAddFact] = useState(false);
  const [pendingForget, setPendingForget] = useState<MemoryEntry | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [retryableAction, setRetryableAction] = useState<RetryableAction | null>(null);

  const handlePromote = useCallback(
    async (entry: MemoryEntry): Promise<void> => {
      if (!workspaceId) return;
      setBusyId(entry.entry_id);
      setActionError(null);
      setRetryableAction(null);
      try {
        await memoryApi.promoteEntry(entry.entry_id, { workspace_id: workspaceId });
        reloadEntries(page);
      } catch (err: unknown) {
        setActionError(
          formatMemoryErrorMessage(
            err,
            t("memory.action.promoteError", "Befördern fehlgeschlagen.")
          )
        );
        setRetryableAction({ kind: "promote", entry });
      } finally {
        setBusyId(null);
      }
    },
    [workspaceId, page, reloadEntries, t]
  );

  const handleForget = useCallback(
    async (entry: MemoryEntry): Promise<void> => {
      setBusyId(entry.entry_id);
      setActionError(null);
      setRetryableAction(null);
      try {
        await memoryApi.forgetEntry(entry.entry_id);
        reloadEntries(page);
      } catch (err: unknown) {
        setActionError(
          formatMemoryErrorMessage(
            err,
            t("memory.action.forgetError", "Vergessen fehlgeschlagen.")
          )
        );
        setRetryableAction({ kind: "forget", entry });
      } finally {
        setBusyId(null);
      }
    },
    [page, reloadEntries, t]
  );

  /** Re-run the operation whose row action failed (#1296). */
  const retryFailedAction = useCallback((): void => {
    const action = retryableAction;
    setActionError(null);
    setRetryableAction(null);
    if (!action) {
      reloadEntries(page);
      return;
    }
    if (action.kind === "promote") void handlePromote(action.entry);
    else void handleForget(action.entry);
  }, [retryableAction, page, reloadEntries, handlePromote, handleForget]);

  const requestForget = useCallback((entry: MemoryEntry): void => {
    setActionError(null);
    setRetryableAction(null);
    setPendingForget(entry);
  }, []);

  const cancelForget = useCallback((): void => {
    setPendingForget(null);
  }, []);

  const openAddFact = useCallback((): void => {
    setShowAddFact(true);
  }, []);

  const closeAddFact = useCallback((): void => {
    setShowAddFact(false);
  }, []);

  const handleCreated = useCallback((): void => {
    setShowAddFact(false);
    reloadEntries(1);
  }, [reloadEntries]);

  return {
    showAddFact,
    openAddFact,
    closeAddFact,
    pendingForget,
    requestForget,
    cancelForget,
    busyId,
    actionError,
    retryableAction,
    handlePromote,
    handleForget,
    retryFailedAction,
    handleCreated,
  };
}
