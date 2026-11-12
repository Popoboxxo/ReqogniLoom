/**
 * ARCH-L1-001 ReactFrontend — architecture inline create (#598 S2, #1100/#1732).
 *
 * Extracted from `ArchitectureEditors.tsx`: the quick-create dialog and the
 * tree's "+ child" path share one create. They are independent of the list
 * filters, the derive flows, the decompose panel and the risk dialog.
 *
 * Contract kept verbatim:
 *   - the submit button stays active; a click validates, marks the field and
 *     moves focus there (#1732),
 *   - a synchronous ref guards against a same-tick double submit (button plus
 *     `Ctrl`/`Cmd`+`S`, #1100/FR-U5-01),
 *   - a rejected create reports the server message in the list banner and, when
 *     the 400 names a field, under that control (#340/#1392),
 *   - only what was typed is sent (`description` stays absent when empty,
 *     BUG-11).
 */

import { useCallback, useRef, useState } from "react";
import type { TFunction } from "i18next";

import { architectureApi } from "../../api/architecture";
import { extractApiErrorMessage } from "../../api/client";
import { fieldErrorsFromException } from "../shared/ArtifactForm/field-errors";
import { useSaveShortcut } from "../../hooks/useSaveShortcut";
import type { RequiredValidation } from "../shared/useRequiredValidation";

export interface UseArchitectureCreateOptions {
  workspaceId: string | undefined;
  t: TFunction;
  refresh: () => void;
  navigate: (path: string) => void;
  validation: Pick<RequiredValidation, "validate" | "focusFirstInvalid">;
  /** The list-level banner is shared with delete, so the page owns its setter. */
  onError: (message: string) => void;
}

export interface UseArchitectureCreateResult {
  showCreateForm: boolean;
  newTitle: string;
  newDescription: string;
  isCreating: boolean;
  createFieldErrors: Record<string, string[]>;
  setNewTitle: (value: string) => void;
  setNewDescription: (value: string) => void;
  setCreateFieldErrors: (errors: Record<string, string[]>) => void;
  createFormRef: React.RefObject<HTMLFormElement | null>;
  handleCreate: (
    parentId?: string,
    customTitle?: string,
    customDescription?: string
  ) => Promise<void>;
  handleInlineCreate: () => Promise<void>;
  handleCancelCreate: () => void;
  openCreateForm: () => void;
}

export function useArchitectureCreate({
  workspaceId,
  t,
  refresh,
  navigate,
  validation,
  onError,
}: UseArchitectureCreateOptions): UseArchitectureCreateResult {
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createFieldErrors, setCreateFieldErrors] = useState<Record<string, string[]>>({});
  const submittingRef = useRef(false);
  const createFormRef = useRef<HTMLFormElement | null>(null);

  const handleCreate = useCallback(
    async (
      parentId?: string,
      customTitle?: string,
      customDescription?: string
    ): Promise<void> => {
      if (!workspaceId) return;
      onError("");
      setCreateFieldErrors({});
      setIsCreating(true);
      try {
        const created = await architectureApi.create({
          workspace_id: workspaceId,
          title: customTitle || t("arch.newElementTitle"),
          element_type: "component",
          parent_id: parentId ?? undefined,
          // BUG-11: only send what was actually typed.
          ...(customDescription?.trim() ? { description: customDescription.trim() } : {}),
        });
        setShowCreateForm(false);
        setNewTitle("");
        setNewDescription("");
        refresh();
        navigate(`/architecture/${created.id}`);
      } catch (err: unknown) {
        // #340: a rejected create used to end in a bare console.error. The
        // server message goes to the list banner; a field-naming 400 also
        // lands under that control (#1392).
        const message = extractApiErrorMessage(err) ?? t("arch.createFailed");
        onError(message);
        setCreateFieldErrors(fieldErrorsFromException(err, message));
      } finally {
        setIsCreating(false);
      }
    },
    [workspaceId, t, refresh, navigate, onError]
  );

  const handleInlineCreate = useCallback(async (): Promise<void> => {
    // FR-U5-01: same-tick guard for both the Create button and the chord. The
    // tree's "+ child" path calls `handleCreate` directly and is a single
    // gesture, so it needs no guard.
    if (submittingRef.current) return;
    const fields = [{ name: "title", value: newTitle, inputId: "arch-new-title" }];
    const invalid = validation.validate(fields);
    if (invalid.length > 0) {
      validation.focusFirstInvalid(fields, invalid);
      return;
    }
    submittingRef.current = true;
    try {
      await handleCreate(undefined, newTitle.trim(), newDescription);
    } finally {
      submittingRef.current = false;
    }
  }, [newTitle, newDescription, handleCreate, validation]);

  // #1100: the inline form opts into the shared shortcut; enabled only while
  // the dialog is open, and the hook's topmost-form rule makes it win over the
  // detail form still mounted behind it.
  useSaveShortcut({
    onSave: handleInlineCreate,
    enabled: showCreateForm,
    isSaving: isCreating,
    containerRef: createFormRef,
    canSave: newTitle.trim().length > 0,
  });

  const openCreateForm = useCallback((): void => {
    setShowCreateForm(true);
  }, []);

  const handleCancelCreate = useCallback((): void => {
    setShowCreateForm(false);
    setNewTitle("");
    setNewDescription("");
  }, []);

  return {
    showCreateForm,
    newTitle,
    newDescription,
    isCreating,
    createFieldErrors,
    setNewTitle,
    setNewDescription,
    setCreateFieldErrors,
    createFormRef,
    handleCreate,
    handleInlineCreate,
    handleCancelCreate,
    openCreateForm,
  };
}
