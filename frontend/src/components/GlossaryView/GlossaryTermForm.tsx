/**
 * GlossaryTermForm — the shared create/edit form markup for glossary terms.
 *
 * One field source serves both surfaces (unchanged behavior from before the
 * extraction): the #802 create flow rendered through the shared <Dialog> and
 * the in-pane edit form — same overlay, focus trap and Escape-to-close
 * behaviour for create, same right-pane edit surface as the other artifact
 * routes. `children` carries the edit-only sections (workflow status editor,
 * C9 trace-link button) that render between the fields and the error banner.
 */
import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { FormField } from "../shared/FormField";
import { useFieldContract } from "../../hooks/useFieldContract";
import styles from "./GlossaryView.module.css";

export interface GlossaryFormData {
  term: string;
  definition: string;
  synonyms: string;
  abbreviation: string;
}

/**
 * GitHub #1393 regression guard: `term` and `definition` are REQUIRED by the
 * model/create service, and the form must say so even while the server
 * definition is still loading — and permanently if that request fails. The
 * resolved definition (when it arrives) still wins, because `useFieldContract`
 * prefers a server answer over `staticContracts`; this only replaces the
 * fail-OPEN `required: false` default. `term` is bounded at 255 by
 * `GlossaryTerm.term = CharField(max_length=255)` (`persistence/models.py`),
 * the same number the definition publishes as `validation.length`.
 */
const GLOSSARY_STATIC_CONTRACTS = {
  term: { required: true, maxLength: 255 },
  definition: { required: true },
} as const;

interface GlossaryTermFormProps {
  formData: GlossaryFormData;
  editingId: string | null;
  heading?: string;
  errorMessage: string | null;
  termInputRef: RefObject<HTMLInputElement | null>;
  onSubmit: (e: React.FormEvent) => void;
  onFieldChange: (field: keyof GlossaryFormData, value: string) => void;
  onClose: () => void;
  /** GitHub #1392: `details[].field` messages from the rejected save. */
  fieldErrors?: Record<string, string[]>;
  children?: React.ReactNode;
}

export function GlossaryTermForm({
  formData,
  editingId,
  heading,
  errorMessage,
  termInputRef,
  onSubmit,
  onFieldChange,
  onClose,
  fieldErrors,
  children,
}: GlossaryTermFormProps): JSX.Element {
  const { t } = useTranslation();
  // GitHub #1393/#1392: `term` and `definition` are required and `term` is
  // bounded at 255 characters by the model. The form is only mounted while the
  // create dialog or the edit pane is open, so the definition is fetched then.
  // The static fallback keeps both facts true before/without a server answer.
  const { field } = useFieldContract("GlossaryTerm", {
    enabled: true,
    staticContracts: GLOSSARY_STATIC_CONTRACTS,
  });
  const errors = fieldErrors ?? {};

  return (
    <form onSubmit={onSubmit} data-testid="glossary-form" noValidate>
      {heading && <h2 className={styles.formHeading}>{heading}</h2>}
      <div className={styles.formGrid}>
        <div>
          <FormField
            htmlFor="glossary-term-input"
            label={t("glossary.term")}
            required={field("term").required}
            error={errors.term?.join(", ")}
            labelClassName={styles.fieldLabel}
          >
            <input
              id="glossary-term-input"
              className={styles.input}
              value={formData.term}
              onChange={(e) => onFieldChange("term", e.target.value)}
              disabled={!!editingId}
              ref={termInputRef}
              {...field("term").controlProps}
            />
          </FormField>
        </div>
        <div>
          <FormField
            htmlFor="glossary-abbreviation-input"
            label={t("glossary.abbreviation")}
            required={field("abbreviation").required}
            error={errors.abbreviation?.join(", ")}
            labelClassName={styles.fieldLabel}
          >
            <input
              id="glossary-abbreviation-input"
              className={styles.input}
              value={formData.abbreviation}
              onChange={(e) => onFieldChange("abbreviation", e.target.value)}
              {...field("abbreviation").controlProps}
            />
          </FormField>
        </div>
        <div className={styles.formGridFullRow}>
          <FormField
            htmlFor="glossary-definition-input"
            label={t("glossary.definition")}
            required={field("definition").required}
            error={errors.definition?.join(", ")}
            labelClassName={styles.fieldLabel}
          >
            <textarea
              id="glossary-definition-input"
              rows={3}
              className={`${styles.input} ${styles.textareaResize}`}
              value={formData.definition}
              onChange={(e) => onFieldChange("definition", e.target.value)}
              {...field("definition").controlProps}
            />
          </FormField>
        </div>
        <div className={styles.formGridFullRow}>
          <label className={styles.fieldLabel} htmlFor="glossary-synonyms-input">
            {t("glossary.synonyms")}
          </label>
          <input id="glossary-synonyms-input" className={styles.input} value={formData.synonyms} onChange={(e) => onFieldChange("synonyms", e.target.value)} />
        </div>
      </div>

      {children}

      {errorMessage && (
        <p role="alert" data-testid="glossary-form-error" className={styles.alert}>
          {errorMessage}
        </p>
      )}

      <div className={styles.formActions}>
        <button
          type="button"
          data-testid="glossary-form-cancel"
          onClick={onClose}
          className={`btn-secondary ${styles.btn} ${styles.btnOutline}`}
        >
          {t("actions.cancel", "Cancel")}
        </button>
        <button type="submit" data-testid="glossary-form-save" className="btn-primary">
          {t("actions.save", "Save")}
        </button>
      </div>
    </form>
  );
}
