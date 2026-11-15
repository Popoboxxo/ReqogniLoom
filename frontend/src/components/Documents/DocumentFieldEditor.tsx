/**
 * ARCH-L1-001 ReactFrontend — inline field editor for the document reading
 * view (R5, plan 2026-11-15-document-view-on-document.md).
 *
 * One `<DocumentFieldEditor>` renders one entry of the reading object's
 * `fields[]` and its write verdict. It is presentational on purpose: the
 * draft state and the request live in `useDocumentDrafts`, so the control can
 * be rendered (and tested) without a network.
 *
 * The three write verdicts map to three DOM states, and each one is visible to
 * a screen reader, not only to the eye:
 *
 * - `FIELD_FROZEN` → `disabled` (the field is released; nothing to try) plus
 *   the server's reason as `title` *and* via `aria-describedby`,
 * - `REPO_EXTERNAL` / `PERMISSION` (or `editable: false`) → `readOnly` (the
 *   text stays readable and copyable, it just cannot be written),
 * - otherwise → editable.
 *
 * Accessibility baseline only (semantic label, described-by wiring, visible
 * focus via the shared tokens): the binding WCAG verdict is the accessibility
 * specialist's.
 */

import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Lock } from "lucide-react";

import type { ReadingField } from "../../types";
import type { DocumentDraft } from "./useDocumentDrafts";
import styles from "./Documents.module.css";

/** Fields that are edited as multi-line Markdown rather than a single line. */
const MULTILINE_FIELDS = new Set(["body", "description"]);

/** Codes that mean "released", i.e. the control is disabled rather than read-only. */
const FROZEN_CODE = "FIELD_FROZEN";

export interface DocumentFieldEditorProps {
  field: ReadingField;
  /** Already translated label of the field. */
  label: string;
  /** Draft of this field, when it has been touched. */
  draft?: DocumentDraft;
  /** Where the save happens — `batch` hides the per-field save button. */
  mode: "immediate" | "batch";
  /**
   * The document is released for this field (`frozen_fields`). The reading
   * object normally already reports `locked.code === FIELD_FROZEN`; the extra
   * flag keeps a stale projection from offering a write the server refuses.
   */
  frozen?: boolean;
  onChange: (field: string, value: string) => void;
  onSave: (field: string) => void;
  onReload: (field: string) => void;
}

export function DocumentFieldEditor({
  field,
  label,
  draft,
  mode,
  frozen = false,
  onChange,
  onSave,
  onReload,
}: DocumentFieldEditorProps): JSX.Element {
  const { t } = useTranslation();

  const lockedCode = field.locked?.code ?? null;
  const isFrozen = frozen || lockedCode === FROZEN_CODE;
  const isReadOnly = !isFrozen && (!field.editable || lockedCode !== null);
  const isConflict = draft?.status === "conflict";
  const isError = draft?.status === "error";
  const isSaving = draft?.status === "saving";
  const isDirty = draft?.status === "dirty";

  const inputId = `document-field-input-${field.name}`;
  const reasonId = `document-field-reason-${field.name}`;
  const messageId = `document-field-message-${field.name}`;

  // The server's lock sentence wins over the surface's own wording: it knows
  // *why* the field is not writable, the surface would only be guessing.
  const lockReason = field.locked?.detail ?? null;
  const describedBy = [lockReason ? reasonId : null, isConflict || isError ? messageId : null]
    .filter(Boolean)
    .join(" ");

  const value = draft ? String(draft.value ?? "") : String(field.value ?? "");
  const controlClass = [
    MULTILINE_FIELDS.has(field.name) ? styles.fieldTextarea : styles.fieldInput,
    isConflict ? styles.fieldConflict : "",
  ]
    .filter(Boolean)
    .join(" ");

  function handleKeyDown(event: KeyboardEvent<HTMLElement>): void {
    // Enter saves only a single-line control: in a textarea it is a newline.
    if (event.key !== "Enter" || MULTILINE_FIELDS.has(field.name)) return;
    if (mode !== "immediate" || isSaving || !isDirty) return;
    event.preventDefault();
    onSave(field.name);
  }

  return (
    <div
      className={styles.fieldEditor}
      data-testid={`document-field-editor-${field.name}`}
    >
      <label className={styles.fieldName} htmlFor={inputId}>
        {label}
      </label>

      <div className={styles.fieldControl}>
        {MULTILINE_FIELDS.has(field.name) ? (
          <textarea
            id={inputId}
            className={controlClass}
            value={value}
            rows={field.name === "body" ? 8 : 3}
            disabled={isFrozen}
            readOnly={isReadOnly}
            aria-invalid={isConflict || isError || undefined}
            aria-describedby={describedBy || undefined}
            title={lockReason ?? undefined}
            data-testid={`document-field-input-${field.name}`}
            onChange={(event) => onChange(field.name, event.target.value)}
            onKeyDown={handleKeyDown}
          />
        ) : (
          <input
            id={inputId}
            className={controlClass}
            type={field.name === "doc_date" ? "date" : "text"}
            value={value}
            disabled={isFrozen}
            readOnly={isReadOnly}
            aria-invalid={isConflict || isError || undefined}
            aria-describedby={describedBy || undefined}
            title={lockReason ?? undefined}
            data-testid={`document-field-input-${field.name}`}
            onChange={(event) => onChange(field.name, event.target.value)}
            onKeyDown={handleKeyDown}
          />
        )}

        {isFrozen && (
          <span
            id={reasonId}
            className={styles.fieldLock}
            data-testid={`document-field-lock-${field.name}`}
            title={lockReason ?? t("documents.fieldFrozen")}
          >
            <Lock size={14} aria-hidden="true" />
            <span className="visually-hidden">
              {lockReason ?? t("documents.fieldFrozen")}
            </span>
          </span>
        )}

        {mode === "immediate" && !isFrozen && !isReadOnly && isDirty && (
          <button
            type="button"
            className="btn-secondary"
            data-testid={`document-field-save-${field.name}`}
            onClick={() => onSave(field.name)}
          >
            {t("documents.save")}
          </button>
        )}
        {isSaving && (
          <span
            className={styles.fieldNote}
            data-testid={`document-field-saving-${field.name}`}
            role="status"
          >
            {t("documents.saving")}
          </span>
        )}
      </div>

      {isConflict && (
        <div
          id={messageId}
          className={styles.fieldConflictNote}
          data-testid={`document-field-conflict-${field.name}`}
          role="alert"
        >
          <span>
            {draft?.error ?? t("documents.fieldConflict")}
          </span>
          <button
            type="button"
            className="btn-ghost"
            data-testid={`document-field-reload-${field.name}`}
            onClick={() => onReload(field.name)}
          >
            {t("documents.reloadField")}
          </button>
        </div>
      )}

      {isError && (
        <p
          id={messageId}
          className={styles.fieldErrorNote}
          data-testid={`document-field-error-${field.name}`}
          role="alert"
        >
          {draft?.error ?? t("documents.fieldSaveFailed")}
        </p>
      )}
    </div>
  );
}

DocumentFieldEditor.displayName = "DocumentFieldEditor";
