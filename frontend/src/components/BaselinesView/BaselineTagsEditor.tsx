/**
 * F4.3 — Baseline tag editor.
 *
 * leaf_id: COMP-RF-002 (BaselinesView)
 * req_id:  REQ-L1-018 (Baselines)
 *
 * Replaces a baseline's complete tag set through `PUT /api/v1/baselines/{id}/tags/`
 * (F4.2 backend contract). The component is a controlled draft over the
 * `tags` prop: local edits live in `draft` until the save round-trip succeeds,
 * so a rejected write (400 `VALIDATION_ERROR` with per-label `details`, 403,
 * 404) never silently discards what the user typed.
 *
 * Validation mirrors `BaselineFacade._normalise_tags` (max 20 labels, label
 * <= 64 chars, `^[\w][\w .:+#/-]*$`) so the obvious mistakes are caught before
 * a network round-trip; the backend stays the authority.
 *
 * Accessibility baseline: real `<button>`s, the pill list and heading are
 * labelled, the input carries an accessible name, and the error region is
 * `role="alert"`. No WCAG conformance claim — the binding verdict is
 * `accessibility-specialist`'s.
 */

import { useId, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './BaselineTagsEditor.module.css';

/** Mirrors `MAX_TAGS_PER_BASELINE` in `backend/application/baseline_facade.py`. */
const MAX_TAGS = 20;
/** Mirrors `MAX_TAG_LENGTH` in `backend/application/baseline_facade.py`. */
const MAX_TAG_LENGTH = 64;
/** Mirrors `_TAG_PATTERN` in `backend/application/baseline_facade.py`. */
const TAG_PATTERN = /^[\w][\w .:+#/-]*$/;

export interface BaselineTagsEditorProps {
  /** Persisted tags of the selected baseline. */
  tags: string[];
  /** Replace the complete tag set; a rejection is rendered inline. */
  onSave: (tags: string[]) => Promise<void>;
  /** Upper bound (defaults to the backend's 20). */
  maxTags?: number;
  /** Disable every control, e.g. without write authority. */
  disabled?: boolean;
}

function sameLabels(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((label, i) => label === b[i]);
}

/**
 * Human-readable message from a failed `setTags` call. Per-label `details`
 * win over the generic envelope message, because they name the offending
 * label rather than just "invalid tag(s)".
 */
function tagErrorMessage(err: unknown): string {
  const envelope = (
    err as {
      error?: {
        message?: string;
        details?: { label?: string | null; error?: string }[];
      };
    }
  )?.error;
  const detail = envelope?.details?.[0];
  if (detail?.label) {
    return `${detail.label}: ${detail.error ?? envelope?.message ?? ''}`.trim();
  }
  if (detail?.error) return detail.error;
  return envelope?.message ?? String(err);
}

export function BaselineTagsEditor({
  tags,
  onSave,
  maxTags = MAX_TAGS,
  disabled = false,
}: BaselineTagsEditorProps): JSX.Element {
  const { t } = useTranslation();
  const headingId = useId();
  // `null` means "no local edits" — the component renders the prop value
  // directly and the save button stays disabled.
  const [draft, setDraft] = useState<string[] | null>(null);
  const [label, setLabel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const current = draft ?? tags;
  const dirty = draft !== null && !sameLabels(draft, tags);

  const addLabel = (): void => {
    const trimmed = label.trim();
    if (!trimmed) return;
    if (trimmed.length > MAX_TAG_LENGTH || !TAG_PATTERN.test(trimmed)) {
      setError(t('baselines.tagInvalid', { label: trimmed }));
      return;
    }
    if (current.some((tag) => tag.toLowerCase() === trimmed.toLowerCase())) {
      // Duplicates are silently dropped (backend de-duplicates the same way).
      setLabel('');
      setError(null);
      return;
    }
    if (current.length >= maxTags) {
      setError(t('baselines.tagLimit', { max: maxTags }));
      return;
    }
    setDraft([...current, trimmed]);
    setLabel('');
    setError(null);
  };

  const removeLabel = (index: number): void => {
    setDraft(current.filter((_, i) => i !== index));
    setError(null);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === 'Enter') {
      event.preventDefault();
      addLabel();
    }
  };

  const handleSave = async (): Promise<void> => {
    if (draft === null) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
      // Keep the persisted draft visible until the parent's refetch lands —
      // clearing it here would flash the previous tag set back.
      setDraft(draft);
    } catch (err: unknown) {
      setError(tagErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section data-testid="baseline-tags" className={styles.editor} aria-labelledby={headingId}>
      <h3 id={headingId} className={styles.heading}>
        {t('baselines.tags')}
      </h3>

      <ul className={styles.chipList} aria-label={t('baselines.tags')}>
        {current.map((tag, index) => (
          <li key={tag} data-testid="baseline-tag-chip" className={styles.tagChip}>
            <span className={styles.chipLabel}>{tag}</span>
            <button
              type="button"
              data-testid="baseline-tag-remove-btn"
              className={`btn-icon ${styles.chipRemove}`}
              aria-label={t('baselines.tagRemove', { label: tag })}
              disabled={disabled || saving}
              onClick={() => removeLabel(index)}
            >
              &times;
            </button>
          </li>
        ))}
      </ul>

      <div className={styles.addRow}>
        <input
          type="text"
          data-testid="baseline-tag-input"
          className={styles.tagInput}
          value={label}
          maxLength={MAX_TAG_LENGTH}
          placeholder={t('baselines.tagPlaceholder')}
          aria-label={t('baselines.tagAdd')}
          disabled={disabled || saving}
          onChange={(event) => {
            setLabel(event.target.value);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
        />
        <button
          type="button"
          data-testid="baseline-tag-add-btn"
          className="btn-secondary"
          disabled={disabled || saving}
          onClick={addLabel}
        >
          {t('baselines.tagAdd')}
        </button>
      </div>

      {error && (
        <p role="alert" data-testid="baseline-tag-error" className={styles.error}>
          {error}
        </p>
      )}

      <button
        type="button"
        data-testid="baseline-tag-save-btn"
        className="btn-primary"
        disabled={disabled || saving || !dirty}
        onClick={() => void handleSave()}
      >
        {t('baselines.tagSave')}
      </button>
    </section>
  );
}
