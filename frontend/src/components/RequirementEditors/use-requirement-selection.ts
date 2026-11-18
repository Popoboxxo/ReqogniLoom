/**
 * RequirementEditors — unsaved-changes selection guard (S3.2 WP-5).
 *
 * Extracted verbatim from `RequirementEditors.tsx` (issue #672 plus the
 * custom-fields dirty fix from Task 23 round 4): the form's dirty flag, the
 * sibling CustomFieldsEditor draft, the tree click held back while dirty, the
 * confirm handler that discards it and the post-save re-anchoring. This is one
 * decision — "may the open requirement be swapped?" — independent of the list
 * writes and the inspector.
 */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useFormDirty } from "../../hooks/use-form-dirty";
import { useEntityReset } from "../../hooks/use-entity-reset";
import type { Requirement } from "../../types";

export interface UseRequirementSelectionOptions {
  selectedId: string | undefined;
  requirement: Requirement | null | undefined;
  refresh: () => void;
}

export interface UseRequirementSelectionResult {
  /** Combined form + custom-fields dirty state (the gate used by the UI). */
  isFormDirty: boolean;
  setIsFormDirty: (dirty: boolean) => void;
  pendingSelectId: string | null;
  setPendingSelectId: (id: string | null) => void;
  customFieldsDraft: Record<string, unknown>;
  setCustomFieldsDraft: (draft: Record<string, unknown>) => void;
  selectRequirement: (id: string) => void;
  confirmPendingSelect: () => void;
  handleSaved: () => void;
}

export function useRequirementSelection({
  selectedId,
  requirement,
  refresh,
}: UseRequirementSelectionOptions): UseRequirementSelectionResult {
  const navigate = useNavigate();

  const [formDirty, setFormDirty] = useState(false);
  const [pendingSelectId, setPendingSelectId] = useState<string | null>(null);

  // Task 25: custom_fields is a free-form JSON blob the definition-driven
  // RequirementArtifactForm cannot render, so the CustomFieldsEditor lives as
  // a sibling. Reset on requirement switch, not on every refetch of the same
  // one.
  const [customFieldsDraft, setCustomFieldsDraft] = useState<Record<string, unknown>>({});
  // customFieldsDraft must feed the same dirty gate as formDirty, or editing
  // only a custom field and switching silently discards the edit with no
  // unsaved-changes dialog — the editor is not wired into the form's own
  // useFormDirty/onDirtyChange at all.
  const { isDirty: customFieldsDirty, markClean: markCustomFieldsClean } = useFormDirty(
    customFieldsDraft,
    requirement?.custom_fields ?? {},
  );
  useEntityReset(requirement?.id ?? '__none__', () => {
    const baseline = requirement?.custom_fields ?? {};
    setCustomFieldsDraft(baseline);
    markCustomFieldsClean(baseline);
  });
  const isFormDirty = formDirty || customFieldsDirty;

  /**
   * Issue #672: navigating the tree used to call `navigate()` directly,
   * which swaps the URL — and therefore the `requirement` prop the open
   * RequirementArtifactForm is bound to — immediately, discarding any unsaved
   * edit with no warning. Unsaved edits now gate the navigation behind a
   * confirmation instead.
   */
  const selectRequirement = useCallback(
    (id: string): void => {
      if (isFormDirty && id !== selectedId) {
        setPendingSelectId(id);
        return;
      }
      navigate(`/requirements/${id}`);
    },
    [isFormDirty, navigate, selectedId]
  );

  const confirmPendingSelect = useCallback((): void => {
    if (!pendingSelectId) return;
    const target = pendingSelectId;
    setPendingSelectId(null);
    setFormDirty(false);
    // Discarding: re-anchor the custom-fields baseline to whatever is
    // currently drafted so isFormDirty drops immediately, not just once the
    // target requirement's own useEntityReset callback fires after
    // navigation.
    markCustomFieldsClean(customFieldsDraft);
    navigate(`/requirements/${target}`);
  }, [pendingSelectId, navigate, customFieldsDraft, markCustomFieldsClean]);

  // A save that touched customFieldsDraft would otherwise leave
  // customFieldsDirty stuck `true` forever — markCustomFieldsClean was only
  // called from useEntityReset/confirmPendingSelect, never after a successful
  // save, so the very next requirement switch showed a false dialog.
  const handleSaved = useCallback((): void => {
    markCustomFieldsClean(customFieldsDraft);
    refresh();
  }, [customFieldsDraft, markCustomFieldsClean, refresh]);

  return {
    isFormDirty,
    setIsFormDirty: setFormDirty,
    pendingSelectId,
    setPendingSelectId,
    customFieldsDraft,
    setCustomFieldsDraft,
    selectRequirement,
    confirmPendingSelect,
    handleSaved,
  };
}
