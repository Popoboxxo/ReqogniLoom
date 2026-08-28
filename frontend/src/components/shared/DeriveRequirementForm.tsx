/**
 * DeriveRequirementForm — shared "Ableiten" (manual derive) trigger + inline
 * form, used identically across Needs, Architecture, and Requirements so the
 * manual-derive UI is visually consistent everywhere (UI standards: "aus
 * einem Guss"). The AI-assisted derive (✨ gradient button) stays exclusive
 * to Needs via TraceLinkPanel's `onDerive` prop — it is backed by a real LLM
 * endpoint that only exists for StakeholderNeed.
 */

import React from 'react';
import { useTranslation } from 'react-i18next';
import type { ArchitectureElement } from '../../types';

const inputStyle: React.CSSProperties = {
  width: '100%',
  fontSize: 'var(--font-size-base)',
  padding: 'var(--space-2) var(--space-3)',
  marginBottom: 'var(--space-3)',
  boxSizing: 'border-box',
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-text)',
  fontFamily: 'var(--font-sans)',
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: 'block',
  marginBottom: 'var(--space-1)',
  color: 'var(--color-text)',
  fontSize: 'var(--font-size-sm)',
};

export interface DeriveRequirementFormProps {
  isOpen: boolean;
  onOpen: () => void;
  onCancel: () => void;
  onSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
  title: string;
  onTitleChange: (value: string) => void;
  architectureElements: ArchitectureElement[];
  architectureElementId: string;
  onArchitectureElementChange: (value: string) => void;
  /** Requirements' /derive/ endpoint requires an architecture element; Needs treat it as optional. */
  architectureRequired?: boolean;
  /** Architecture elements' own derive has no field at all — the current element is the implicit target. */
  showArchitectureField?: boolean;
  isSubmitting: boolean;
  error: string | null;
  /** Prefix for data-testid attributes, kept per call site to avoid breaking existing test selectors. */
  testIdPrefix: string;
}

export function DeriveRequirementForm({
  isOpen,
  onOpen,
  onCancel,
  onSubmit,
  title,
  onTitleChange,
  architectureElements,
  architectureElementId,
  onArchitectureElementChange,
  architectureRequired = false,
  showArchitectureField = true,
  isSubmitting,
  error,
  testIdPrefix,
}: DeriveRequirementFormProps): JSX.Element {
  const { t } = useTranslation();
  const titleInputId = React.useId();
  const archSelectId = React.useId();

  if (!isOpen) {
    return (
      <button
        type="button"
        data-testid={`${testIdPrefix}-derive-btn`}
        className="btn-secondary"
        onClick={onOpen}
      >
        {t('traceability.derive')}
      </button>
    );
  }

  return (
    <form
      data-testid={`${testIdPrefix}-derive-form`}
      onSubmit={onSubmit}
      style={{
        border: '1px solid var(--color-border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-4)',
        background: 'var(--color-surface-raised)',
      }}
    >
      <label htmlFor={titleInputId} style={labelStyle}>{t('traceability.deriveTitle')} *</label>
      <input
        id={titleInputId}
        type="text"
        data-testid={`${testIdPrefix}-derive-title-input`}
        value={title}
        onChange={(e) => onTitleChange(e.target.value)}
        autoFocus
        disabled={isSubmitting}
        style={inputStyle}
      />

      {showArchitectureField && (
        <>
          <label htmlFor={archSelectId} style={labelStyle}>
            {architectureRequired
              ? t('traceability.deriveArchitectureElement')
              : t('needs.deriveArchOptional')}
            {architectureRequired ? ' *' : ''}
          </label>
          <select
            id={archSelectId}
            data-testid={`${testIdPrefix}-derive-arch-select`}
            value={architectureElementId}
            onChange={(e) => onArchitectureElementChange(e.target.value)}
            disabled={isSubmitting}
            style={inputStyle}
          >
            <option value="">
              {architectureRequired ? t('editor.selectOption') : t('needs.priorityNone')}
            </option>
            {architectureElements.map((el) => (
              <option key={el.id} value={el.id}>
                {el.title}
              </option>
            ))}
          </select>
        </>
      )}

      {error && (
        <p style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', margin: '0 0 var(--space-2) 0' }}>
          {error}
        </p>
      )}

      {/* `flexWrap` is what keeps this row inside the form when the column is
          narrow. Without it the row is `nowrap` + `justify-content: flex-end`,
          so once the buttons no longer fit they overflow past the *start*
          edge, land outside the form's box and are covered by whatever sits
          to the left of it (on the requirement route: the SplitView divider),
          making the submit button unclickable. Same reasoning as the actions
          group in PageHeader.tsx (issue #314). */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 'var(--space-2)',
          justifyContent: 'flex-end',
          minWidth: 0,
        }}
      >
        <button type="button" className="btn-ghost" onClick={onCancel} disabled={isSubmitting}>
          {t('actions.cancel')}
        </button>
        <button
          type="submit"
          data-testid={`${testIdPrefix}-derive-submit-btn`}
          className="btn-primary"
          disabled={isSubmitting}
        >
          {isSubmitting ? t('actions.deriving', 'Ableiten...') : t('traceability.derive')}
        </button>
      </div>
    </form>
  );
}
