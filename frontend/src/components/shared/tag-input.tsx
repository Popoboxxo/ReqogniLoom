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

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  'data-testid'?: string;
}

export function TagInput({
  tags,
  onChange,
  placeholder = 'tag1, tag2 ...',
  'data-testid': testId,
}: TagInputProps): JSX.Element {
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
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 'var(--space-1)',
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-2)',
        background: 'var(--color-surface)',
        minHeight: '38px',
        alignItems: 'center',
        marginBottom: 'var(--space-4)',
        cursor: 'text',
        boxSizing: 'border-box',
      }}
      onClick={() => {
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
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 'var(--space-1)',
            background: 'var(--color-primary)',
            color: 'white',
            borderRadius: 'var(--radius-sm)',
            padding: '2px var(--space-2)',
            fontSize: 'var(--font-size-sm)',
            fontWeight: 500,
          }}
        >
          {tag}
          <button
            type="button"
            data-testid="tag-remove-btn"
            onClick={(e) => {
              e.stopPropagation();
              removeTag(i);
            }}
            style={{
              background: 'none',
              border: 'none',
              color: 'inherit',
              cursor: 'pointer',
              padding: 0,
              lineHeight: 1,
              fontSize: '1em',
              opacity: 0.8,
              marginLeft: '2px',
            }}
            aria-label={`Remove tag ${tag}`}
          >
            &times;
          </button>
        </span>
      ))}
      <input
        type="text"
        data-testid={testId ? `${testId}-input` : 'tag-input-field'}
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={handleBlur}
        placeholder={tags.length === 0 ? placeholder : ''}
        style={{
          border: 'none',
          outline: 'none',
          background: 'transparent',
          fontSize: 'var(--font-size-base)',
          color: 'var(--color-text)',
          fontFamily: 'var(--font-sans)',
          minWidth: '80px',
          flex: 1,
          padding: 0,
        }}
      />
    </div>
  );
}
