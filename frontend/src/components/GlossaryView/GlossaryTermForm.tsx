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
import styles from "./GlossaryView.module.css";

export interface GlossaryFormData {
  term: string;
  definition: string;
  synonyms: string;
  abbreviation: string;
}

interface GlossaryTermFormProps {
  formData: GlossaryFormData;
  editingId: string | null;
  heading?: string;
  errorMessage: string | null;
  termInputRef: RefObject<HTMLInputElement | null>;
  onSubmit: (e: React.FormEvent) => void;
  onFieldChange: (field: keyof GlossaryFormData, value: string) => void;
  onClose: () => void;
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
  children,
}: GlossaryTermFormProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <form onSubmit={onSubmit} data-testid="glossary-form">
      {heading && <h2 className={styles.formHeading}>{heading}</h2>}
      <div className={styles.formGrid}>
        <div>
          <label className={styles.fieldLabel} htmlFor="glossary-term-input">
            {t("glossary.term")} *
          </label>
          <input id="glossary-term-input" required className={styles.input} value={formData.term} onChange={(e) => onFieldChange("term", e.target.value)} disabled={!!editingId} ref={termInputRef} />
        </div>
        <div>
          <label className={styles.fieldLabel} htmlFor="glossary-abbreviation-input">
            {t("glossary.abbreviation")}
          </label>
          <input id="glossary-abbreviation-input" className={styles.input} value={formData.abbreviation} onChange={(e) => onFieldChange("abbreviation", e.target.value)} />
        </div>
        <div className={styles.formGridFullRow}>
          <label className={styles.fieldLabel} htmlFor="glossary-definition-input">
            {t("glossary.definition")} *
          </label>
          <textarea id="glossary-definition-input" required rows={3} className={`${styles.input} ${styles.textareaResize}`} value={formData.definition} onChange={(e) => onFieldChange("definition", e.target.value)} />
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
          className={`${styles.btn} ${styles.btnOutline}`}
        >
          {t("actions.cancel", "Cancel")}
        </button>
        <button type="submit" data-testid="glossary-form-save" className={styles.btn}>
          {t("actions.save", "Save")}
        </button>
      </div>
    </form>
  );
}
