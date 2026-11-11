/**
 * ARCH-L1-001 ReactFrontend — attribute confirmation flows (#598 S2).
 *
 * Extracted from `AttributeEditorPage.tsx`: the two destructive confirmations
 * (delete an attribute definition, remove one option value) are independent of
 * the page's draft/loaded state, section layout and save lifecycle.
 *
 * Both keep the same two-phase shape:
 *   1. `request*` opens the dialog and probes the usage count (non-global
 *      definitions only — a global one has no workspace usage to count),
 *   2. `confirm*` performs the action. Deleting hits the API and reloads;
 *      removing an option is a *local* patch, because options are saved
 *      through the page's normal Save button (Task 6 in the page history).
 */

import { useCallback, useState } from "react";

import {
  attributeDefinitionsApi,
  type AttributeItemType,
  type AttributeSpec,
} from "../../api/attribute-definitions";
import { extractErrorMessage } from "../../api/client";
import type { WorkspacePreset } from "../../types";

import { patchAttribute } from "./attribute-edits";

export interface UseAttributeConfirmationsOptions {
  workspaceId: string | undefined;
  isGlobal: boolean;
  itemType: AttributeItemType;
  preset: WorkspacePreset;
  /** The attribute whose options are being edited (option removal only). */
  selectedAttribute: AttributeSpec | null;
  /** Draft state setter — option removal is a local, unsaved patch. */
  setAttributes: React.Dispatch<React.SetStateAction<AttributeSpec[]>>;
  /** Re-read after a successful delete. */
  reload: () => Promise<void>;
  /** Surface a failed deletion in the page's error banner. */
  onError: (message: string) => void;
}

export interface UseAttributeConfirmationsResult {
  deleteTarget: string | null;
  deleteUsageCount: number | null;
  deleting: boolean;
  requestDeleteAttribute: (name: string) => void;
  closeDeleteAttribute: () => void;
  confirmDeleteAttribute: () => Promise<void>;

  removeOptionTarget: string | null;
  removeOptionUsageCount: number | null;
  requestRemoveOption: (optionValue: string) => void;
  closeRemoveOption: () => void;
  confirmRemoveOption: () => void;
}

export function useAttributeConfirmations({
  workspaceId,
  isGlobal,
  itemType,
  preset,
  selectedAttribute,
  setAttributes,
  reload,
  onError,
}: UseAttributeConfirmationsOptions): UseAttributeConfirmationsResult {
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleteUsageCount, setDeleteUsageCount] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [removeOptionTarget, setRemoveOptionTarget] = useState<string | null>(null);
  const [removeOptionUsageCount, setRemoveOptionUsageCount] = useState<number | null>(
    null
  );

  const requestDeleteAttribute = useCallback(
    (name: string): void => {
      setDeleteTarget(name);
      setDeleteUsageCount(null);
      if (!isGlobal && workspaceId) {
        void attributeDefinitionsApi
          .getUsageCount(workspaceId, itemType, name)
          .then(setDeleteUsageCount)
          .catch(() => setDeleteUsageCount(0));
      } else {
        setDeleteUsageCount(0);
      }
    },
    [workspaceId, isGlobal, itemType]
  );

  const closeDeleteAttribute = useCallback((): void => {
    setDeleteTarget(null);
    setDeleteUsageCount(null);
  }, []);

  const confirmDeleteAttribute = useCallback(async (): Promise<void> => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      if (isGlobal) {
        await attributeDefinitionsApi.deleteGlobalAttribute(itemType, preset, deleteTarget);
      } else if (workspaceId) {
        await attributeDefinitionsApi.deleteWorkspaceAttribute(
          workspaceId,
          itemType,
          deleteTarget
        );
      }
      setDeleteTarget(null);
      await reload();
    } catch (exc: unknown) {
      onError(extractErrorMessage(exc));
    } finally {
      setDeleting(false);
    }
  }, [workspaceId, deleteTarget, isGlobal, itemType, reload, preset, onError]);

  const requestRemoveOption = useCallback(
    (optionValue: string): void => {
      setRemoveOptionTarget(optionValue);
      setRemoveOptionUsageCount(null);
      if (!isGlobal && workspaceId && selectedAttribute) {
        void attributeDefinitionsApi
          .getUsageCount(
            workspaceId,
            itemType,
            selectedAttribute.name,
            optionValue
          )
          .then(setRemoveOptionUsageCount)
          .catch(() => setRemoveOptionUsageCount(0));
      } else {
        setRemoveOptionUsageCount(0);
      }
    },
    [workspaceId, isGlobal, itemType, selectedAttribute]
  );

  const closeRemoveOption = useCallback((): void => {
    setRemoveOptionTarget(null);
    setRemoveOptionUsageCount(null);
  }, []);

  const confirmRemoveOption = useCallback((): void => {
    if (!removeOptionTarget || !selectedAttribute) return;
    setAttributes((current) =>
      patchAttribute(current, selectedAttribute.name, {
        options: selectedAttribute.options.filter(
          (option) => option.value !== removeOptionTarget
        ),
      })
    );
    setRemoveOptionTarget(null);
  }, [removeOptionTarget, selectedAttribute, setAttributes]);

  return {
    deleteTarget,
    deleteUsageCount,
    deleting,
    requestDeleteAttribute,
    closeDeleteAttribute,
    confirmDeleteAttribute,
    removeOptionTarget,
    removeOptionUsageCount,
    requestRemoveOption,
    closeRemoveOption,
    confirmRemoveOption,
  };
}
