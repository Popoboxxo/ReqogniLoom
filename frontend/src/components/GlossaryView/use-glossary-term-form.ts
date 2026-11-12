/**
 * ARCH-L1-001 ReactFrontend — glossary term form (#598 S2, UI §12.11 / #802).
 *
 * Extracted from `GlossaryView.tsx`: the create/edit form, its draft and both
 * error slots. The list, the filters, the synonym linking and the AI
 * derivation stay in the view.
 *
 * Contract kept verbatim:
 *   - a failed save keeps the form open with the message and the input intact
 *     (UI standards §12.11),
 *   - one close path for the create dialog and the in-pane editor — it clears
 *     the message, because a failed save must not leave it behind,
 *   - a successful save leaves the form, selects the saved term and reloads
 *     the list,
 *   - synonyms travel as a comma-separated string in the form and as a
 *     trimmed, non-empty array to the API.
 */

import { useCallback, useState } from "react";
import type { TFunction } from "i18next";

import { glossaryApi } from "../../api/glossary";
import type { GlossaryTerm } from "../../types";
import { extractErrorMessage } from "../../api/client";
import { fieldErrorsFromException } from "../shared/ArtifactForm/field-errors";
import type { GlossaryFormData } from "./GlossaryTermForm";

const EMPTY_FORM: GlossaryFormData = {
  term: "",
  definition: "",
  synonyms: "",
  abbreviation: "",
};

export interface UseGlossaryTermFormOptions {
  workspaceId: string | undefined;
  t: TFunction;
  reloadTerms: () => void;
  /** Select the saved term in the detail pane. */
  onSelect: (id: string) => void;
}

export interface UseGlossaryTermFormResult {
  isFormOpen: boolean;
  editingId: string | null;
  formData: GlossaryFormData;
  formError: string | null;
  formFieldErrors: Record<string, string[]>;
  handleSubmit: (event: React.FormEvent) => Promise<void>;
  handleEdit: (term: GlossaryTerm) => void;
  openCreateForm: () => void;
  closeForm: () => void;
  resetForm: () => void;
  updateFormField: (field: keyof GlossaryFormData, value: string) => void;
}

export function useGlossaryTermForm({
  workspaceId,
  t,
  reloadTerms,
  onSelect,
}: UseGlossaryTermFormOptions): UseGlossaryTermFormResult {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formData, setFormData] = useState<GlossaryFormData>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [formFieldErrors, setFormFieldErrors] = useState<Record<string, string[]>>({});

  const resetForm = useCallback((): void => {
    setFormData(EMPTY_FORM);
    setEditingId(null);
  }, []);

  const handleSubmit = useCallback(
    async (event: React.FormEvent): Promise<void> => {
      event.preventDefault();
      if (!workspaceId) return;

      setFormError(null);
      setFormFieldErrors({});
      try {
        const payload = {
          workspace_id: workspaceId,
          term: formData.term,
          definition: formData.definition,
          synonyms: formData.synonyms
            ? formData.synonyms
                .split(",")
                .map((part) => part.trim())
                .filter(Boolean)
            : [],
          abbreviation: formData.abbreviation,
        };

        const saved = editingId
          ? await glossaryApi.update(editingId, payload)
          : await glossaryApi.create(payload);

        setIsFormOpen(false);
        resetForm();
        onSelect(saved.id);
        reloadTerms();
      } catch (err: unknown) {
        // Keep the form open on failure (UI standards §12.11) — the user's
        // input must not be lost and the form must not silently close.
        const message = extractErrorMessage(err) || t("glossary.saveFailed");
        setFormError(message);
        setFormFieldErrors(fieldErrorsFromException(err, message));
      }
    },
    [workspaceId, formData, editingId, resetForm, onSelect, reloadTerms, t]
  );

  const handleEdit = useCallback(
    (term: GlossaryTerm): void => {
      setFormData({
        term: term.term,
        definition: term.definition,
        synonyms: term.synonyms ? term.synonyms.join(", ") : "",
        abbreviation: term.abbreviation || "",
      });
      setEditingId(term.id);
      onSelect(term.id);
      setIsFormOpen(true);
    },
    [onSelect]
  );

  const openCreateForm = useCallback((): void => {
    resetForm();
    setIsFormOpen(true);
  }, [resetForm]);

  /**
   * Single close path for both the create dialog and the in-pane edit form
   * (#802) — a failed save keeps the form open with the message visible, so
   * the error has to be cleared here, not on open only.
   */
  const closeForm = useCallback((): void => {
    setIsFormOpen(false);
    setFormError(null);
  }, []);

  const updateFormField = useCallback(
    (field: keyof GlossaryFormData, value: string): void => {
      setFormData((prev) => ({ ...prev, [field]: value }));
    },
    []
  );

  return {
    isFormOpen,
    editingId,
    formData,
    formError,
    formFieldErrors,
    handleSubmit,
    handleEdit,
    openCreateForm,
    closeForm,
    resetForm,
    updateFormField,
  };
}
