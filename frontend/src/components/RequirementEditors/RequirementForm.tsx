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

import { useState, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useEntityType } from '../../context/EntityTypeContext';
import { useWorkspace } from '../../context/WorkspaceContext';
import {
  Requirement,
  RequirementType,
  VerificationMethod,
  UUID,
  TraceLink,
  CustomFields,
  REQ_CATEGORIES,
  WORKFLOW_STATES,
} from '../../types';
import { requirementsApi } from '../../api/requirements';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { MarkdownPreview } from './MarkdownPreview';
import { ArtifactDiff } from '../ArtifactDiff/ArtifactDiff';
import { VersionBadge } from '../shared/VersionBadge';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
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
 *
 * The `upstreamLinks`/`downstreamLinks`/`linkedTitles`/`linkedRoutes`
 * props are retained on the public interface for compatibility with
 * `RequirementEditors.tsx` (out of scope of the current task) but are
 * no longer consumed here — traceability is now surfaced through the
 * shared ArtifactInspector (REQ-L1-095).
 */
export const RequirementForm: React.FC<RequirementFormProps> = ({
  requirement,
  requirements: _requirements,
  workspaceId,
  onSaved,
}) => {
  const { t } = useTranslation();
  const { isFieldVisible, isFieldRequired } = useEntityType();
  const { activeWorkspace } = useWorkspace();
  const isExtendedPreset = activeWorkspace?.preset === 'extended';

  // Form state
  const [title, setTitle] = useState(requirement.title);
  const [description, setDescription] = useState(requirement.description);
  const [category, setCategory] = useState(requirement.category);
  const [workflowState, setWorkflowState] = useState(requirement.status);
  const [changeReason, setChangeReason] = useState(requirement.change_reason || '');
  const [type, setType] = useState<RequirementType>(requirement.type || 'SyReq');
  const [complexityFibonacci, setComplexityFibonacci] = useState<number | ''>(
    requirement.complexity_fibonacci || 1
  );
  const [verificationMethod, setVerificationMethod] = useState<VerificationMethod | ''>(
    requirement.verification_method || ''
  );
  // REQ-L2-AS-037: user-defined custom fields (stored on the backing Artifact).
  const [customFields, setCustomFields] = useState<CustomFields>(
    requirement.custom_fields || {}
  );

  // UI state
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  // Feed the ArtifactInspector with the current version
  // (REQ-L2-RF-035). The actual /versions/ list is fetched inside
  // VersionPanel; we only hand it the current row to anchor the
  // diff baseline (UI standards §4.1).
  const currentVersion: VersionRef = useMemo(
    () => ({
      version: requirement.version,
      label: `v${requirement.version}`,
      createdAt: requirement.updated_at ?? requirement.created_at,
      baselineIds: [],
    }),
    [requirement.version, requirement.created_at, requirement.updated_at]
  );

  /**
   * Validate form data before saving.
   */
  const validateForm = useCallback((): string | null => {
    if (!title.trim()) {
      return t('editor.titleRequired');
    }
    if (isExtendedPreset && isFieldVisible('change_reason') && isFieldRequired('change_reason') && !changeReason.trim()) {
      return t('req.changeReasonRequired');
    }
    
    // Type-specific validations
    if (type === 'SyReq') {
      if (isFieldVisible('verification_method') && isFieldRequired('verification_method') && !verificationMethod) {
        return t('editor.verificationMethodRequired');
      }
    }
    return null;
  }, [title, changeReason, type, verificationMethod, t, isExtendedPreset, isFieldVisible, isFieldRequired]);

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
      if (type === 'SyReq') {
        updateData.complexity_fibonacci = complexityFibonacci === '' ? null : Number(complexityFibonacci);
        updateData.verification_method = verificationMethod || null;
      }

      // REQ-L2-AS-037: always send custom_fields (backend validates the map).
      updateData.custom_fields = customFields;

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
    complexityFibonacci,
    verificationMethod,
    customFields,
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
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--space-3)' }}>
            <h2
              style={{
                fontSize: 'var(--font-size-xl)',
                fontWeight: 700,
                color: 'var(--color-text)',
                margin: 0,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              {requirement.suspect && <span title="Needs review due to upstream changes">⚠️</span>}
              {requirement.title || t('editor.untitled')}
            </h2>
          </div>
          <div
            style={{
              display: 'flex',
              gap: 'var(--space-4)',
              fontSize: 'var(--font-size-sm)',
              color: 'var(--color-text-muted)',
            }}
          >
            {requirement.uid ? (
              <span
                style={{
                  fontFamily: 'monospace',
                  fontSize: '0.75rem',
                  color: 'var(--color-text-muted)',
                  userSelect: 'all',
                }}
                title="Unique Identifier"
              >
                {requirement.uid}
              </span>
            ) : (
              <span
                style={{
                  fontFamily: 'monospace',
                  fontSize: '0.75rem',
                  color: 'var(--color-text-muted)',
                  userSelect: 'all',
                  opacity: 0.6,
                }}
                title="Short ID (UUID prefix, no semantic uid assigned yet)"
              >
                {requirement.id.slice(0, 8)}
              </span>
            )}
            <VersionBadge version={requirement.version || '1'} />
          </div>
        </div>

        {/* SECTION: General Information */}
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
            General Information
          </h3>
          
          <label htmlFor="req-title" style={labelStyle}>
            {t('editor.title')} <span style={{ color: 'var(--color-danger)' }}>*</span>
          </label>
          <input
            id="req-title"
            data-testid="req-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            style={{ ...inputStyle, marginBottom: 'var(--space-4)' }}
          />

          <label htmlFor="req-description" style={{ ...labelStyle, marginBottom: 'var(--space-1)' }}>
            {t('editor.description')}
          </label>
          <MarkdownPreview value={description} onChange={setDescription} />
        </div>

        {/* SECTION: Classification & Properties */}
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
            Classification & Properties
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 'var(--space-4)' }}>
            {isFieldVisible('category') && (
              <div>
                <label htmlFor="req-category" style={labelStyle}>
                  {t('editor.category')} {isFieldRequired('category') && <span style={{ color: 'var(--color-danger)' }}>*</span>}
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
              </div>
            )}

            {isFieldVisible('status') && (
              <div>
                <label htmlFor="req-workflow" style={labelStyle}>
                  {t('editor.workflowState')} {isFieldRequired('status') && <span style={{ color: 'var(--color-danger)' }}>*</span>}
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
              </div>
            )}

            {isFieldVisible('type') && (
              <div>
                <label htmlFor="req-type" style={labelStyle}>
                  {t('editor.type')} {isFieldRequired('type') && <span style={{ color: 'var(--color-danger)' }}>*</span>}
                </label>
                <select
                  id="req-type"
                  data-testid="req-type"
                  value={type}
                  onChange={(e) => setType(e.target.value as RequirementType)}
                  style={inputStyle}
                >
                  <option value="StReq">{t('reqType.StReq')}</option>
                  <option value="SyReq">{t('reqType.SyReq')}</option>
                  <option value="SWReq">{t('reqType.SWReq')}</option>
                  <option value="HWReq">{t('reqType.HWReq')}</option>
                </select>
              </div>
            )}


            {type === 'SyReq' && isFieldVisible('complexity_fibonacci') && (
              <div>
                <label htmlFor="complexity-fibonacci" style={labelStyle}>
                  {t('editor.complexityFibonacci')} {isFieldRequired('complexity_fibonacci') && <span style={{ color: 'var(--color-danger)' }}>*</span>}
                </label>
                <select
                  id="complexity-fibonacci"
                  data-testid="complexity-fibonacci"
                  value={complexityFibonacci}
                  onChange={(e) => setComplexityFibonacci(Number(e.target.value))}
                  style={inputStyle}
                >
                  {FIBONACCI_SEQUENCE.map((val) => (
                    <option key={val} value={val}>
                      {val}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {type === 'SyReq' && isFieldVisible('verification_method') && (
              <div>
                <label htmlFor="verification-method" style={labelStyle}>
                  {t('editor.verificationMethod')} {isFieldRequired('verification_method') && <span style={{ color: 'var(--color-danger)' }}>*</span>}
                </label>
                <select
                  id="verification-method"
                  data-testid="verification-method"
                  value={verificationMethod}
                  onChange={(e) => setVerificationMethod(e.target.value as VerificationMethod)}
                  style={inputStyle}
                >
                  <option value="">{t('editor.selectVerificationMethod')} --</option>
                  <option value="Inspection">Inspection</option>
                  <option value="Review">Review</option>
                  <option value="Test">Test</option>
                  <option value="Analysis">Analysis</option>
                </select>
              </div>
            )}
          </div>
        </div>

        {/* SECTION: Custom Fields (REQ-L2-AS-037) */}
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
            {t('customFields.section')}
          </h3>
          <CustomFieldsEditor
            value={requirement.custom_fields}
            onChange={setCustomFields}
            disabled={isSaving}
          />
        </div>

        {/* SECTION: Change Control */}
        {isExtendedPreset && isFieldVisible('change_reason') && (
          <div style={{ marginBottom: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
              Change Control
            </h3>
            
            <label htmlFor="change-reason" style={labelStyle}>
              {t('req.changeReason')} {isFieldRequired('change_reason') && <span style={{ color: 'var(--color-danger)' }}>*</span>}
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
          </div>
        )}

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
            className="btn-primary"
            onClick={() => void handleSave()}
            disabled={isSaving}
          >
            {isSaving ? t('actions.saving') : t('actions.save')}
          </button>
          <button
            data-testid="view-diff-btn"
            className={showDiff ? 'btn-primary' : 'btn-secondary'}
            onClick={() => setShowDiff(!showDiff)}
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

      </div>

      {/* ArtifactInspector RightSidebar (REQ-L1-095).
          Replaces the inline TraceLinkPanel with a unified shell that
          renders VersionPanel + DiffPanel + TracePanel. */}
      <RightSidebar
        kind="requirement"
        artifactId={requirement.id}
        currentVersion={currentVersion}
      />
    </div>
  );
};

RequirementForm.displayName = 'RequirementForm';
