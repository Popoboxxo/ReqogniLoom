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
      <label style={labelStyle}>{t('traceability.deriveTitle')} *</label>
      <input
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
          <label style={labelStyle}>
            {architectureRequired
              ? t('traceability.deriveArchitectureElement')
              : t('needs.deriveArchOptional')}
            {architectureRequired ? ' *' : ''}
          </label>
          <select
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

      <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'flex-end' }}>
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
