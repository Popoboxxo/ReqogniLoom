/**
 * ARCH-L1-001 ReactFrontend — stakeholder-need create flow (#598 S2, #1100/#1732).
 *
 * Extracted from `NeedsEditors.tsx`: the create dialog's draft, validation and
 * submit lifecycle. The dialog markup still lives in `NeedList`; this module
 * owns the state the page threads down.
 *
 * Contract kept verbatim:
 *   - opening is refused while the real workspaces are not loaded yet, so no
 *     POST can hit the null-UUID placeholder workspace,
 *   - only what was typed is sent (BUG-11),
 *   - a rejected create keeps the dialog and the input, shows the server
 *     message and any field-named details,
 *   - `Ctrl`/`Cmd`+`S` goes through the form's own submit path (validation and
 *     focus move included), not straight into the create call,
 *   - closing clears the error message.
 */

import { useCallback, useRef, useState } from "react";
import type { TFunction } from "i18next";

import { stakeholderNeedApi } from "../../api/stakeholder-need";
import { extractApiErrorMessage } from "../../api/client";
import { fieldErrorsFromException } from "../shared/ArtifactForm/field-errors";
import { useSaveShortcut } from "../../hooks/useSaveShortcut";

export interface UseNeedCreateOptions {
  workspaceId: string | undefined;
  /** False while the workspace list is still the placeholder. */
  hasWorkspaces: boolean;
  refresh: () => void;
  navigate: (path: string) => void;
  t: TFunction;
}

export interface UseNeedCreateResult {
  showCreate: boolean;
  newTitle: string;
  newDescription: string;
  newCategory: string;
  createError: string | null;
  createFieldErrors: Record<string, string[]>;
  isCreating: boolean;
  setShowCreate: (show: boolean) => void;
  setNewTitle: (value: string) => void;
  setNewDescription: (value: string) => void;
  setNewCategory: (value: string) => void;
  handleCreateNew: () => Promise<void>;
  openCreate: () => void;
  createFormRef: React.RefObject<HTMLFormElement | null>;
  createTriggerRef: React.RefObject<HTMLButtonElement | null>;
}

export function useNeedCreate({
  workspaceId,
  hasWorkspaces,
  refresh,
  navigate,
  t,
}: UseNeedCreateOptions): UseNeedCreateResult {
  const [showCreate, setShowCreateState] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [createFieldErrors, setCreateFieldErrors] = useState<Record<string, string[]>>({});
  const [isCreating, setIsCreating] = useState(false);

  const createFormRef = useRef<HTMLFormElement | null>(null);
  const createTriggerRef = useRef<HTMLButtonElement | null>(null);

  const setShowCreate = useCallback((show: boolean): void => {
    if (!show) setCreateError(null);
    setShowCreateState(show);
  }, []);

  const openCreate = useCallback((): void => {
    // Never open against the null-UUID placeholder workspace.
    if (!hasWorkspaces) return;
    setCreateError(null);
    setNewDescription("");
    setNewCategory("");
    setShowCreateState(true);
  }, [hasWorkspaces]);

  const handleCreateNew = useCallback(async (): Promise<void> => {
    if (!workspaceId || !hasWorkspaces) return;
    if (!newTitle.trim()) return;
    setCreateError(null);
    setCreateFieldErrors({});
    setIsCreating(true);
    try {
      const resp = await stakeholderNeedApi.create(workspaceId, {
        title: newTitle.trim(),
        // BUG-11: only send what was actually typed.
        ...(newDescription.trim() ? { description: newDescription.trim() } : {}),
        ...(newCategory.trim() ? { category: newCategory.trim() } : {}),
      });
      setNewTitle("");
      setNewDescription("");
      setNewCategory("");
      setShowCreateState(false);
      refresh();
      navigate(`/needs/${resp.id}`);
    } catch (err: unknown) {
      const message = extractApiErrorMessage(err) ?? t("needs.createFailed");
      setCreateError(message);
      setCreateFieldErrors(fieldErrorsFromException(err, message));
    } finally {
      setIsCreating(false);
    }
  }, [workspaceId, hasWorkspaces, newTitle, newDescription, newCategory, refresh, navigate, t]);

  // #1732: the chord goes through the form's own submit path — that is what
  // runs the required-field validation and the focus move. Calling the create
  // directly would bypass both.
  useSaveShortcut({
    onSave: () => createFormRef.current?.requestSubmit(),
    enabled: showCreate,
    isSaving: isCreating,
    containerRef: createFormRef,
    canSave: true,
  });

  return {
    showCreate,
    newTitle,
    newDescription,
    newCategory,
    createError,
    createFieldErrors,
    isCreating,
    setShowCreate,
    setNewTitle,
    setNewDescription,
    setNewCategory,
    handleCreateNew,
    openCreate,
    createFormRef,
    createTriggerRef,
  };
}
