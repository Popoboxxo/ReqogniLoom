/**
 * REQ-L3-RF003-005: RequirementForm Component
 *
 * Type-dependent form for editing requirements with:
 * - Type detection (StReq, SyReq, SWReq, HWReq)
 * - Moscow Priority field (visible only for StReq)
 * - Complexity Fibonacci slider (visible only for SyReq)
 * - Verification Method dropdown (visible only for SyReq)
 * - Read-only UID + Version header
 * - Standard fields (title, description, category, workflowState, change_reason)
 * - Save/Cancel and Diff toggle
 * - TraceLink panel
 *
 * leaf_id: COMP-RF-003-RequirementForm
 * req_id: REQ-L3-RF003-001, REQ-L3-RF003-005
 *
 * Interfaces implemented:
 * IF-RF-INT-002 ← I18nService via useTranslation
 * IF-RF-EXT-OUT-001 → PATCH /api/v1/requirements/
 */

import React, { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useEntityType } from '../../context/EntityTypeContext';
import {
  Requirement,
  RequirementType,
  MoscowPriority,
  VerificationMethod,
  UUID,
  TraceLink,
  REQ_CATEGORIES,
  WORKFLOW_STATES,
} from '../../types';
import { requirementsApi } from '../../api/requirements';
import { MarkdownPreview } from './MarkdownPreview';
import { ArtifactDiff } from '../ArtifactDiff/ArtifactDiff';
import { ReqTraceLinkPanel } from './ReqTraceLinkPanel';
import { TraceabilityPanel } from './TraceabilityPanel';
import { FIBONACCI_SEQUENCE } from '../../utils/fibonacciUtils';

/**
 * Props for RequirementForm.
 */
interface RequirementFormProps {
  requirement: Requirement;
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
  linkedTitles: Record<string, string>;
  linkedRoutes: Record<string, string>;
  requirements: Requirement[];
  workspaceId: UUID;
  onSaved: () => void;
}

/**
 * RequirementForm — Right panel component with type-dependent field rendering.
 */
export const RequirementForm: React.FC<RequirementFormProps> = ({
  requirement,
  upstreamLinks,
  downstreamLinks,
  linkedTitles,
  linkedRoutes,
  requirements,
  workspaceId,
  onSaved,
}) => {
  const { t } = useTranslation();
  const { entitySubType, visibleFields, isFieldVisible } = useEntityType();

  // Form state
  const [title, setTitle] = useState(requirement.title);
  const [description, setDescription] = useState(requirement.description);
  const [category, setCategory] = useState(requirement.category);
  const [workflowState, setWorkflowState] = useState(requirement.status);
  const [changeReason, setChangeReason] = useState(requirement.change_reason || '');
  const [type, setType] = useState<RequirementType>(requirement.type || 'SyReq');
  const [moscowPriority, setMoscowPriority] = useState<MoscowPriority | ''>(
    requirement.moscow_priority || ''
  );
  const [complexityFibonacci, setComplexityFibonacci] = useState<number>(
    requirement.complexity_fibonacci || 1
  );
  const [verificationMethod, setVerificationMethod] = useState<VerificationMethod | ''>(
    requirement.verification_method || ''
  );

  // UI state
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  /**
   * Validate form data before saving.
   */
  const validateForm = useCallback((): string | null => {
    if (!title.trim()) {
      return t('editor.titleRequired');
    }
    if (!changeReason.trim()) {
      return t('req.changeReasonRequired');
    }
    // Type-specific validations
    if (type === 'StReq' && !moscowPriority) {
      return t('editor.moscowPriorityRequired');
    }
    if (type === 'SyReq') {
      if (!verificationMethod) {
        return t('editor.verificationMethodRequired');
      }
    }
    return null;
  }, [title, changeReason, type, moscowPriority, verificationMethod, t]);

  /**
   * Handle save action.
   */
  const handleSave = useCallback(async (): Promise<void> => {
    const validationError = validateForm();
    if (validationError) {
      setSaveError(validationError);
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    try {
      const updateData: Record<string, unknown> = {
        title,
        description,
        category,
        status: workflowState,
        change_reason: changeReason,
        type,
      };

      // Include type-specific fields
      if (type === 'StReq' && moscowPriority) {
        updateData.moscow_priority = moscowPriority;
      }
      if (type === 'SyReq') {
        updateData.complexity_fibonacci = complexityFibonacci;
        updateData.verification_method = verificationMethod;
      }

      await requirementsApi.update(requirement.id, updateData);
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  }, [
    validateForm,
    requirement.id,
    title,
    description,
    category,
    workflowState,
    changeReason,
    type,
    moscowPriority,
    complexityFibonacci,
    verificationMethod,
    onSaved,
  ]);

  // Styles
  const inputStyle: React.CSSProperties = {
    width: '100%',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--space-3)',
    fontFamily: 'var(--font-sans)',
    fontSize: 'var(--font-size-base)',
    marginBottom: 'var(--space-4)',
    color: 'var(--color-text)',
    background: 'var(--color-surface)',
    boxSizing: 'border-box',
  };

  const labelStyle: React.CSSProperties = {
    fontWeight: 500,
    color: 'var(--color-text)',
    display: 'block',
    marginBottom: 'var(--space-1)',
  };

  return (
    <div
      style={{
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-card)',
        padding: 'var(--space-6)',
        flex: 1,
        display: 'flex',
        gap: 'var(--space-6)',
        alignItems: 'flex-start',
      }}
    >
      {/* Main editor */}
      <div style={{ flex: 1 }}>
        {/* Header with UID and Version (read-only) */}
        <div
          style={{
            marginBottom: 'var(--space-6)',
            padding: 'var(--space-4)',
            background: 'var(--color-surface-raised)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)',
          }}
        >
          <h2
            style={{
              fontSize: 'var(--font-size-xl)',
              fontWeight: 700,
              marginBottom: 'var(--space-3)',
              color: 'var(--color-text)',
              marginTop: 0,
            }}
          >
            {requirement.title || t('editor.untitled')}
          </h2>
          <div
            style={{
              display: 'flex',
              gap: 'var(--space-4)',
              fontSize: 'var(--font-size-sm)',
              color: 'var(--color-text-muted)',
            }}
          >
            {requirement.uid && (
              <div>
                <span style={{ fontWeight: 600 }}>UID:</span> {requirement.uid}
              </div>
            )}
            <div>
              <span style={{ fontWeight: 600 }}>Version:</span> {requirement.version || '1'}
            </div>
          </div>
        </div>

        {/* Title */}
        <label htmlFor="req-title" style={labelStyle}>
          {t('editor.title')} <span style={{ color: 'var(--color-danger)' }}>*</span>
        </label>
        <input
          id="req-title"
          data-testid="req-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={inputStyle}
        />

        {/* Description */}
        <label htmlFor="req-description" style={{ ...labelStyle, marginBottom: 'var(--space-1)' }}>
          {t('editor.description')}
        </label>
        <MarkdownPreview value={description} onChange={setDescription} />

        {/* Category */}
        <label htmlFor="req-category" style={{ ...labelStyle, marginBottom: 'var(--space-4)' }}>
          {t('editor.category')}
        </label>
        <select
          id="req-category"
          data-testid="req-category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          style={inputStyle}
        >
          <option value="">{t('editor.categoryPlaceholder')} --</option>
          {REQ_CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>

        {/* Workflow State */}
        <label htmlFor="req-workflow" style={labelStyle}>
          {t('editor.workflowState')}
        </label>
        <select
          id="req-workflow"
          data-testid="req-workflow"
          value={workflowState}
          onChange={(e) => setWorkflowState(e.target.value)}
          style={inputStyle}
        >
          {WORKFLOW_STATES.map((state) => (
            <option key={state} value={state}>
              {state}
            </option>
          ))}
        </select>

        {/* Type selector */}
        <label htmlFor="req-type" style={labelStyle}>
          {t('editor.type')}
        </label>
        <select
          id="req-type"
          data-testid="req-type"
          value={type}
          onChange={(e) => setType(e.target.value as RequirementType)}
          style={inputStyle}
        >
          <option value="StReq">Stakeholder Requirement (StReq)</option>
          <option value="SyReq">System Requirement (SyReq)</option>
          <option value="SWReq">Software Requirement (SWReq)</option>
          <option value="HWReq">Hardware Requirement (HWReq)</option>
        </select>

        {/* Type-specific fields: Moscow Priority (StReq only) */}
        {type === 'StReq' && isFieldVisible('moscow_priority') && (
          <>
            <label htmlFor="moscow-priority" style={labelStyle}>
              {t('editor.moscowPriority')} <span style={{ color: 'var(--color-danger)' }}>*</span>
            </label>
            <select
              id="moscow-priority"
              data-testid="moscow-priority"
              value={moscowPriority}
              onChange={(e) => setMoscowPriority(e.target.value as MoscowPriority)}
              style={inputStyle}
            >
              <option value="">{t('editor.selectPriority')} --</option>
              <option value="M">Must Have (M)</option>
              <option value="S">Should Have (S)</option>
              <option value="C">Could Have (C)</option>
              <option value="W">Won't Have (W)</option>
            </select>
          </>
        )}

        {/* Type-specific fields: Complexity Fibonacci (SyReq only) */}
        {type === 'SyReq' && isFieldVisible('complexity_fibonacci') && (
          <>
            <label htmlFor="complexity-fibonacci" style={labelStyle}>
              {t('editor.complexityFibonacci')}
            </label>
            <div
              style={{
                display: 'flex',
                gap: 'var(--space-4)',
                alignItems: 'center',
                marginBottom: 'var(--space-4)',
              }}
            >
              <input
                id="complexity-fibonacci"
                data-testid="complexity-fibonacci"
                type="range"
                min="0"
                max={FIBONACCI_SEQUENCE.length - 1}
                value={FIBONACCI_SEQUENCE.indexOf(complexityFibonacci) >= 0 ? FIBONACCI_SEQUENCE.indexOf(complexityFibonacci) : 0}
                onChange={(e) => {
                  const idx = parseInt(e.target.value, 10);
                  setComplexityFibonacci(FIBONACCI_SEQUENCE[idx]);
                }}
                style={{
                  flex: 1,
                }}
              />
              <span
                style={{
                  fontWeight: 600,
                  color: 'var(--color-text)',
                  minWidth: '80px',
                  textAlign: 'right',
                }}
              >
                {complexityFibonacci}
              </span>
            </div>
          </>
        )}

        {/* Type-specific fields: Verification Method (SyReq only) */}
        {type === 'SyReq' && isFieldVisible('verification_method') && (
          <>
            <label htmlFor="verification-method" style={labelStyle}>
              {t('editor.verificationMethod')} <span style={{ color: 'var(--color-danger)' }}>*</span>
            </label>
            <select
              id="verification-method"
              data-testid="verification-method"
              value={verificationMethod}
              onChange={(e) => setVerificationMethod(e.target.value as VerificationMethod)}
              style={inputStyle}
            >
              <option value="">{t('editor.selectVerificationMethod')} --</option>
              <option value="inspection">Inspection</option>
              <option value="demonstration">Demonstration</option>
              <option value="test">Test</option>
              <option value="analysis">Analysis</option>
            </select>
          </>
        )}

        {/* Change Reason */}
        <label htmlFor="change-reason" style={labelStyle}>
          {t('req.changeReason')} <span style={{ color: 'var(--color-danger)' }}>*</span>
        </label>
        <textarea
          id="change-reason"
          data-testid="change-reason-input"
          value={changeReason}
          onChange={(e) => setChangeReason(e.target.value)}
          rows={2}
          style={{ ...inputStyle, resize: 'vertical' }}
          placeholder={t('req.changeReasonPlaceholder')}
        />

        {/* Error message */}
        {saveError && (
          <p role="alert" style={{ color: 'var(--color-danger)', marginBottom: 'var(--space-4)' }}>
            {saveError}
          </p>
        )}

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
          <button
            data-testid="save-btn"
            onClick={() => void handleSave()}
            disabled={isSaving}
            style={{
              background: 'var(--color-primary)',
              color: 'white',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-2) var(--space-6)',
              fontSize: 'var(--font-size-sm)',
              fontWeight: 600,
              cursor: isSaving ? 'not-allowed' : 'pointer',
              opacity: isSaving ? 0.7 : 1,
              transition: 'var(--transition-fast)',
            }}
          >
            {isSaving ? t('actions.saving') : t('actions.save')}
          </button>
          <button
            data-testid="view-diff-btn"
            onClick={() => setShowDiff(!showDiff)}
            style={{
              background: showDiff ? 'var(--color-primary)' : 'transparent',
              color: showDiff ? 'white' : 'var(--color-primary)',
              border: '1px solid var(--color-primary)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-2) var(--space-4)',
              fontSize: 'var(--font-size-sm)',
              cursor: 'pointer',
              fontWeight: 500,
            }}
          >
            {showDiff ? t('editor.hideDiff') : t('editor.viewDiff')}
          </button>
        </div>

        {/* Artifact Diff View */}
        {showDiff && (
          <ArtifactDiff
            entityId={requirement.id}
            entityType="requirement"
            currentVersion={requirement.version}
            diffFetcher={requirementsApi.diff}
            versionsFetcher={requirementsApi.versions}
            onClose={() => setShowDiff(false)}
          />
        )}

        {/* TraceLink panel */}
        <ReqTraceLinkPanel
          workspaceId={workspaceId}
          requirementId={requirement.id}
          requirements={requirements}
          onLinksChanged={onSaved}
        />
      </div>

      {/* Traceability sidebar */}
      <TraceabilityPanel
        upstreamLinks={upstreamLinks}
        downstreamLinks={downstreamLinks}
        linkedTitles={linkedTitles}
        linkedRoutes={linkedRoutes}
      />
    </div>
  );
};

RequirementForm.displayName = 'RequirementForm';
