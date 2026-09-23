/**
 * TagInput — pill-style tag editor for REQ-010.
 *
 * Behaviour:
 *  - Press Enter or comma → commit the current input as a new tag
 *  - Press Backspace on empty input → remove the last tag
 *  - Click × on a pill → remove that tag
 *  - Blur with non-empty input → commit the current input as a new tag
 *  - Duplicate tags are silently ignored
 *
 * req_id: REQ-010
 */

import { useState, KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import styles from './tag-input.module.css';

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  'data-testid'?: string;
  /**
   * Id applied to the actual text `<input>` so an external `<label htmlFor>`
   * resolves to a real form control (WCAG 1.3.1 / 4.1.2) instead of the
   * non-interactive pill container.
   */
  inputId?: string;
  /** ArtifactForm's `mode="read"`/saving state (F-1 fix, Task 20 review round). */
  disabled?: boolean;
}

export function TagInput({
  tags,
  onChange,
  placeholder = 'tag1, tag2 ...',
  'data-testid': testId,
  inputId,
  disabled = false,
}: TagInputProps): JSX.Element {
  const { t } = useTranslation();
  const [inputValue, setInputValue] = useState('');

  const commitTag = (raw: string) => {
    const trimmed = raw.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed]);
    }
    setInputValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      commitTag(inputValue);
    } else if (e.key === 'Backspace' && inputValue === '' && tags.length > 0) {
      onChange(tags.slice(0, -1));
    }
  };

  const handleBlur = () => {
    if (inputValue.trim()) {
      commitTag(inputValue);
    }
  };

  const removeTag = (index: number) => {
    onChange(tags.filter((_, i) => i !== index));
  };

  return (
    <div
      data-testid={testId}
      className={styles.container}
      onClick={() => {
        if (disabled) return;
        // Forward click on container to inner input for usability
        const el = document.querySelector<HTMLInputElement>(
          testId ? `[data-testid="${testId}-input"]` : '[data-testid="tag-input-field"]'
        );
        el?.focus();
      }}
    >
      {tags.map((tag, i) => (
        <span
          key={`${tag}-${i}`}
          data-testid="tag-pill"
          className={styles.pill}
        >
          {tag}
          <button
            type="button"
            data-testid="tag-remove-btn"
            disabled={disabled}
            onClick={(e) => {
              e.stopPropagation();
              removeTag(i);
            }}
            className={`${styles.removeBtn} ${disabled ? styles.removeBtnDisabled : ''}`}
            aria-label={t('actions.removeTag', { tag })}
          >
            &times;
          </button>
        </span>
      ))}
      <input
        id={inputId}
        type="text"
        data-testid={testId ? `${testId}-input` : 'tag-input-field'}
        value={inputValue}
        disabled={disabled}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        placeholder={tags.length === 0 ? placeholder : ''}
        className={styles.input}
      />
    </div>
  );
}
