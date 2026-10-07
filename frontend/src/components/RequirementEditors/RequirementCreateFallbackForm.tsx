/**
 * #1087: the hand-written Requirement create fallback.
 *
 * `ArtifactForm` renders this only when the attribute definition could not be
 * loaded (or carries no attributes) — and in exactly that branch the shared
 * renderer disables its own `useSaveShortcut`, because there is no
 * definition-driven save path to drive. The fallback therefore has to own the
 * chord itself, through the same `useSaveShortcut`, so `Ctrl`/`Cmd`+`S` still
 * saves here instead of opening the browser's "Save page as…" over the draft.
 *
 * A standalone component rather than a hook call on `RequirementEditors`: the
 * registry in `useSaveShortcut` grants the chord to the most recently mounted
 * form, and child effects run before parent effects. A parent-level hook would
 * register *after* the definition-driven `ArtifactForm` create dialog and
 * wrongly win over it; mounted inside the fallback subtree, this one registers
 * only when the fallback actually renders.
 */

import { useRef } from "react";
import { useTranslation } from "react-i18next";

import { SAVE_SHORTCUT_ARIA, useSaveShortcut } from "../../hooks/useSaveShortcut";
import { REQ_CATEGORIES } from "../../types";
import fieldHints from "../shared/FieldHints.module.css";
import styles from "./RequirementEditors.module.css";

export interface RequirementCreateFallbackFormProps {
  title: string;
  description: string;
  category: string;
  createError: string | null;
  isCreating: boolean;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  focusTitle: (input: HTMLInputElement | null) => void;
}

export function RequirementCreateFallbackForm({
  title,
  description,
  category,
  createError,
  isCreating,
  onTitleChange,
  onDescriptionChange,
  onCategoryChange,
  onSubmit,
  onCancel,
  focusTitle,
}: RequirementCreateFallbackFormProps): JSX.Element {
  const { t } = useTranslation();
  // #1100 follow-up: the form owns the shortcut, so the hook can tell a covered
  // surface from the interaction context (see useSaveShortcut).
  const formRef = useRef<HTMLFormElement>(null);
  // This component only exists while the modal is open, so the shortcut is
  // unconditionally enabled; `isSaving` still swallows a held-down chord.
  useSaveShortcut({
    onSave: onSubmit,
    enabled: true,
    isSaving: isCreating,
    containerRef: formRef,
    // Mirrors the Save button's `disabled={!title.trim()}` (#1100).
    canSave: title.trim().length > 0,
  });

  return (
    <form
      ref={formRef}
      data-testid="create-req-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className={styles.createForm}
    >
      <label htmlFor="new-req-title" className={styles.createLabel}>
        {t('editor.title')}
      </label>
      <input
        id="new-req-title"
        data-testid="req-new-title-input"
        ref={focusTitle}
        type="text"
        value={title}
        onChange={(e) => onTitleChange(e.target.value)}
        disabled={isCreating}
        placeholder={t('editor.newRequirementTitle')}
        className={styles.createInput}
      />

      {/* BUG-11: description/category — ordinary create() fields the backend
          already accepts, previously missing from this form. */}
      <label htmlFor="new-req-description" className={fieldHints.createLabelInline}>
        {t('editor.description')}
      </label>
      <textarea
        id="new-req-description"
        data-testid="req-new-description-input"
        value={description}
        onChange={(e) => onDescriptionChange(e.target.value)}
        disabled={isCreating}
        rows={3}
        className={fieldHints.createInput}
      />

      <label htmlFor="new-req-category" className={fieldHints.createLabelInline}>
        {t('editor.category')}
      </label>
      <select
        id="new-req-category"
        data-testid="req-new-category-select"
        value={category}
        onChange={(e) => onCategoryChange(e.target.value)}
        disabled={isCreating}
        className={fieldHints.createInput}
      >
        <option value="">{t('editor.categoryPlaceholder')} --</option>
        {REQ_CATEGORIES.map((cat) => (
          <option key={cat} value={cat}>
            {cat}
          </option>
        ))}
      </select>

      {/* #340: the server's own reason (e.g. "contains disallowed content:
          HTML markup is not permitted in free-text fields") belongs directly
          under the field that produced it — see
          docs/architecture/UI_STYLE_GUIDE.md §5.2. */}
      {createError && (
        <p role="alert" data-testid="req-create-error" className={styles.formError}>
          {createError}
        </p>
      )}
      <div className={styles.formActions}>
        {/* issue #719: the create dialog uses the shared
            btn-secondary/btn-primary pair and the "Erstellen" verb like the
            other create dialogs. */}
        <button
          data-testid="req-new-cancel-btn"
          type="button"
          className="btn-secondary"
          onClick={onCancel}
          disabled={isCreating}
        >
          {t('actions.cancel')}
        </button>
        <button
          data-testid="req-new-save-btn"
          type="submit"
          className="btn-primary"
          // BUG-02: title is required — disable rather than silently
          // substitute a placeholder title on submit.
          disabled={isCreating || !title.trim()}
          aria-keyshortcuts={SAVE_SHORTCUT_ARIA}
          title={t('artifactForm.saveShortcutHint', 'Speichern (Strg/Cmd+S)')}
        >
          {isCreating ? t('actions.saving') : t('actions.create', 'Erstellen')}
        </button>
      </div>
    </form>
  );
}
