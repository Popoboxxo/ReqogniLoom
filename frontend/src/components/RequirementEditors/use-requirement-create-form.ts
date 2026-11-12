/**
 * ARCH-L1-001 ReactFrontend — requirement create form state (#598 S2).
 *
 * Extracted from `RequirementEditors.tsx`: the draft, the open/close lifecycle
 * and the error slot of the create dialog. The two submit paths stay in the
 * page because they differ (definition form vs. inline fallback) and own the
 * mutation; they call `closeCreateForm()` on success.
 *
 * Contract kept verbatim:
 *   - toggling the dialog discards a stale error first (the message described
 *     the previous attempt),
 *   - every close affordance (Escape, backdrop, ×, Cancel) discards the whole
 *     draft,
 *   - typing a title after a rejection clears the message.
 */

import { useCallback, useState } from "react";

export interface UseRequirementCreateFormResult {
  showCreateForm: boolean;
  newTitle: string;
  newDescription: string;
  newCategory: string;
  isCreating: boolean;
  createError: string | null;
  setNewTitle: (value: string) => void;
  setNewDescription: (value: string) => void;
  setNewCategory: (value: string) => void;
  setCreating: (value: boolean) => void;
  setCreateError: (value: string | null) => void;
  openCreateForm: () => void;
  toggleCreateForm: () => void;
  closeCreateForm: () => void;
}

export function useRequirementCreateForm(): UseRequirementCreateFormResult {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const openCreateForm = useCallback((): void => {
    setCreateError(null);
    setShowCreateForm(true);
  }, []);

  /** Open/close the inline create form, discarding any stale error. */
  const toggleCreateForm = useCallback((): void => {
    setCreateError(null);
    setShowCreateForm((open) => !open);
  }, []);

  // F-08: every close affordance discards the draft exactly like Cancel.
  const closeCreateForm = useCallback((): void => {
    setShowCreateForm(false);
    setCreateError(null);
    setNewTitle("");
    setNewDescription("");
    setNewCategory("");
  }, []);

  const changeTitle = useCallback(
    (value: string): void => {
      setNewTitle(value);
      // The message described the previous attempt; keep it until the user
      // actually starts correcting the input.
      if (createError) setCreateError(null);
    },
    [createError]
  );

  return {
    showCreateForm,
    newTitle,
    newDescription,
    newCategory,
    isCreating,
    createError,
    setNewTitle: changeTitle,
    setNewDescription,
    setNewCategory,
    setCreating: setIsCreating,
    setCreateError,
    openCreateForm,
    toggleCreateForm,
    closeCreateForm,
  };
}
