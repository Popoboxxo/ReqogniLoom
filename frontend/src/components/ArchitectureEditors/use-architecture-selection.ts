/**
 * ArchitectureEditors — unsaved-changes selection guard (S3.2 WP-5).
 *
 * Extracted verbatim from `ArchitectureEditors.tsx` (issue #672): the form's
 * dirty flag, the tree click held back while dirty and the confirm handler
 * that discards the edit and navigates. This is one decision — "may the open
 * element be swapped?" — and has no dependency on the list actions or the
 * inspector.
 */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

export interface UseArchitectureSelectionOptions {
  selectedId: string | undefined;
}

export interface UseArchitectureSelectionResult {
  isFormDirty: boolean;
  setIsFormDirty: (dirty: boolean) => void;
  pendingSelectId: string | null;
  setPendingSelectId: (id: string | null) => void;
  selectElement: (id: string) => void;
  confirmPendingSelect: () => void;
}

export function useArchitectureSelection({
  selectedId,
}: UseArchitectureSelectionOptions): UseArchitectureSelectionResult {
  const navigate = useNavigate();

  const [isFormDirty, setIsFormDirty] = useState(false);
  const [pendingSelectId, setPendingSelectId] = useState<string | null>(null);

  /**
   * Issue #672: the tree's onSelect used to call `navigate()` directly,
   * which swaps the URL — and therefore the `element` prop the open
   * ArchitectureForm is bound to — immediately, discarding any unsaved edit
   * with no warning. Unsaved edits now gate the navigation behind a
   * confirmation instead.
   */
  const selectElement = useCallback(
    (id: string): void => {
      if (isFormDirty && id !== selectedId) {
        setPendingSelectId(id);
        return;
      }
      navigate(`/architecture/${id}`);
    },
    [isFormDirty, navigate, selectedId]
  );

  const confirmPendingSelect = useCallback((): void => {
    if (!pendingSelectId) return;
    const target = pendingSelectId;
    setPendingSelectId(null);
    setIsFormDirty(false);
    navigate(`/architecture/${target}`);
  }, [pendingSelectId, navigate]);

  return {
    isFormDirty,
    setIsFormDirty,
    pendingSelectId,
    setPendingSelectId,
    selectElement,
    confirmPendingSelect,
  };
}
