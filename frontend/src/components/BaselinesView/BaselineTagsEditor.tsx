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
 * <= 64 chars, `^[\w][\w .:+#/-]*$`) through the shared `./baselineTags`
 * module — Python's `\w` is Unicode-aware, so the JS mirror is
 * `[\p{L}\p{N}_]` rather than the ASCII-only JS `\w`. The backend stays the
 * authority.
 *
 * Accessibility baseline: real `<button>`s, the pill list and heading are
 * labelled, the input carries an accessible name distinct from the add
 * button's, removing a chip returns focus to a neighbour (never `<body>`),
 * and the error region is `role="alert"`. No WCAG conformance claim — the
 * binding verdict is `accessibility-specialist`'s.
 */

import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { MAX_TAG_LENGTH, MAX_TAGS, isValidTagLabel, sameTagSet } from './baselineTags';
import styles from './BaselineTagsEditor.module.css';

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

/** Order-sensitive comparison, used to detect a *new* `tags` prop. */
function sameSequence(a: readonly string[], b: readonly string[]): boolean {
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
  // F3 (ui-review): removing a chip unmounts the focused remove button, so
  // focus used to fall to <body>. `focusAfterRemove` names the index whose
  // neighbour should take focus once the shorter list has rendered.
  const [focusAfterRemove, setFocusAfterRemove] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const removeButtonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // F2 (ui-review): the backend returns the stored labels case-insensitively
  // sorted, the draft keeps insertion order. Whenever the parent hands down a
  // *different* list (save round-trip, list refetch, baseline switch) the
  // draft is dropped so the editor renders the server's canonical order.
  // Render-phase state adjustment, not an effect — React re-renders before
  // committing, so no stale draft is ever painted.
  const [syncedTags, setSyncedTags] = useState<string[]>(tags);
  if (!sameSequence(syncedTags, tags)) {
    setSyncedTags(tags);
    setDraft(null);
  }

  const current = draft ?? tags;
  // Case-insensitive set comparison: an order-only difference is not an edit.
  const dirty = draft !== null && !sameTagSet(draft, tags);

  useEffect(() => {
    if (focusAfterRemove === null) return;
    const buttons = removeButtonRefs.current.filter(
      (button): button is HTMLButtonElement => button !== null,
    );
    // The same index now addresses the chip that followed the removed one;
    // the clamp covers "the last chip was removed" and hands focus to the
    // text field when no chip is left.
    const target = buttons[Math.min(focusAfterRemove, buttons.length - 1)];
    (target ?? inputRef.current)?.focus();
    setFocusAfterRemove(null);
  }, [focusAfterRemove]);

  const addLabel = (): void => {
    const trimmed = label.trim();
    if (!trimmed) return;
    if (!isValidTagLabel(trimmed)) {
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
    setFocusAfterRemove(index);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === 'Enter') {
      event.preventDefault();
      addLabel();
    }
  };

  const handleSave = async (): Promise<void> => {
    // `saving` is guarded here instead of through the button's `disabled`
    // attribute: a button that disables itself on press drops focus to
    // <body>, which is exactly the in-flight affordance hole F3 reported.
    if (draft === null || saving) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(draft);
      // Keep the persisted draft visible until the parent's refetch lands —
      // clearing it here would flash the previous tag set back. The prop sync
      // above drops it as soon as the server's sorted list arrives.
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
              ref={(button) => {
                removeButtonRefs.current[index] = button;
              }}
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
          ref={inputRef}
          type="text"
          data-testid="baseline-tag-input"
          className={styles.tagInput}
          value={label}
          maxLength={MAX_TAG_LENGTH}
          placeholder={t('baselines.tagPlaceholder')}
          aria-label={t('baselines.tagInputLabel')}
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
        disabled={disabled || !dirty}
        aria-busy={saving || undefined}
        onClick={() => void handleSave()}
      >
        {saving ? t('actions.saving') : t('baselines.tagSave')}
      </button>
    </section>
  );
}
