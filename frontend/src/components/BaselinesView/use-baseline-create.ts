/**
 * ARCH-L1-001 ReactFrontend — baseline create form state (#598 S2).
 *
 * Extracted from `BaselinesView.tsx`: the draft (scope, artifact, name, tags),
 * the audit-gate override panel and the open/close lifecycle. The submit stays
 * in the view because it owns the mutation; `useBaselinesData` also consumes
 * `showForm`/`formScope`/`formArtifactId`, so this hook must be callable
 * *before* it — hence it does not depend on the data layer.
 *
 * Contract kept verbatim:
 *   - opening closes compare and clears the selection (via `onBeforeOpen`),
 *   - document scope auto-picks the first artifact once available,
 *   - closing discards tags, override reason and the gate panel,
 *   - tags are validated against the baseline contract before they reach the
 *     server (20-label cap, label charset), emitting the same local keys.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import type { BaselineScope } from "../../api/baselines";
import { MAX_TAGS, isValidTagLabel } from "./baselineTags";

/** Mirrors the backend's minimum (see `baseline_facade.py`). */
export const MIN_OVERRIDE_REASON_LENGTH = 15;

export interface UseBaselineCreateFormOptions {
  t: TFunction;
  /** Called before the form opens (leaves compare, clears the selection). */
  onBeforeOpen: () => void;
}

export interface UseBaselineCreateFormResult {
  showForm: boolean;
  formName: string;
  formTags: string[];
  formArtifactId: string;
  formScope: BaselineScope;
  isSaving: boolean;
  createError: string | null;
  gateBlocked: boolean;
  overrideReason: string;
  createSubmitDisabled: boolean;
  overrideSubmitDisabled: boolean;
  setShowForm: (value: boolean) => void;
  setFormName: (value: string) => void;
  setFormTags: (value: string[]) => void;
  setFormArtifactId: (value: string) => void;
  setFormScope: (value: BaselineScope) => void;
  setIsSaving: (value: boolean) => void;
  setCreateError: (value: string | null) => void;
  setGateBlocked: (value: boolean) => void;
  setOverrideReason: (value: string) => void;
  handleFormTagsChange: (next: string[]) => void;
  openCreateForm: () => void;
  closeCreateForm: () => void;
  /** Reset the draft after a successful create, leaving the panel. */
  resetAfterCreate: () => void;
}

export function useBaselineCreateForm({
  t,
  onBeforeOpen,
}: UseBaselineCreateFormOptions): UseBaselineCreateFormResult {
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState("");
  const [formTags, setFormTags] = useState<string[]>([]);
  const [formArtifactId, setFormArtifactId] = useState("");
  const [formScope, setFormScope] = useState<BaselineScope>("project");
  const [isSaving, setIsSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [gateBlocked, setGateBlocked] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");

  // F5 (ui-review): the shared TagInput knows nothing about the baseline tag
  // contract, so validate here and emit the same local keys as the editor.
  const handleFormTagsChange = useCallback(
    (next: string[]): void => {
      setCreateError(null);
      // TagInput only appends (or removes); a longer list means the last entry
      // is the one just committed.
      if (next.length > formTags.length) {
        const added = next[next.length - 1] ?? "";
        if (!isValidTagLabel(added)) {
          setCreateError(t("baselines.tagInvalid", { label: added }));
          return;
        }
        if (next.length > MAX_TAGS) {
          setCreateError(t("baselines.tagLimit", { max: MAX_TAGS }));
          return;
        }
      }
      setFormTags(next);
    },
    [formTags, t]
  );

  // #1282: creation runs in the shared modal <Dialog>; open and close are
  // distinct actions and closing discards the draft.
  const openCreateForm = useCallback((): void => {
    onBeforeOpen();
    setFormName("");
    setFormTags([]);
    setCreateError(null);
    setGateBlocked(false);
    setOverrideReason("");
    setShowForm(true);
  }, [onBeforeOpen]);

  const closeCreateForm = useCallback((): void => {
    setShowForm(false);
    setFormTags([]);
    setCreateError(null);
    setGateBlocked(false);
    setOverrideReason("");
  }, []);

  const resetAfterCreate = useCallback((): void => {
    setShowForm(false);
    setFormName("");
    setFormTags([]);
    setFormArtifactId("");
    setFormScope("project");
    setGateBlocked(false);
    setOverrideReason("");
  }, []);

  const overrideSubmitDisabled =
    isSaving || overrideReason.trim().length < MIN_OVERRIDE_REASON_LENGTH;

  // REQ-L1-049: the same boolean drives the submit button and its class.
  const createSubmitDisabled =
    isSaving || (formScope === "document" && !formArtifactId);

  return {
    showForm,
    formName,
    formTags,
    formArtifactId,
    formScope,
    isSaving,
    createError,
    gateBlocked,
    overrideReason,
    createSubmitDisabled,
    overrideSubmitDisabled,
    setShowForm,
    setFormName,
    setFormTags,
    setFormArtifactId,
    setFormScope,
    setIsSaving,
    setCreateError,
    setGateBlocked,
    setOverrideReason,
    handleFormTagsChange,
    openCreateForm,
    closeCreateForm,
    resetAfterCreate,
  };
}
