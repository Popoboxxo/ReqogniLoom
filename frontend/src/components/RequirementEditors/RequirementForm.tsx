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

import { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useEntityType } from '../../context/EntityTypeContext';
import { useWorkspace } from '../../context/WorkspaceContext';
import {
  Requirement,
  RequirementType,
  RequirementLevel,
  REQUIREMENT_LEVELS,
  VerificationMethod,
  UUID,
  TraceLink,
  CustomFields,
  REQ_CATEGORIES,
} from '../../types';
import { requirementsApi } from '../../api/requirements';
import { extractErrorMessage } from '../../api/client';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { ArtifactCustomFields } from '../shared/ArtifactCustomFields';
import { MarkdownPreview } from './MarkdownPreview';
import { VersionBadge } from '../shared/VersionBadge';
import { FIBONACCI_SEQUENCE } from '../../utils/fibonacciUtils';
import styles from './RequirementEditors.module.css';

/**
 * #344: the save error banner lives directly under the header action row, i.e.
 * next to the Save button the user just pressed. Hoisted to a module-level
 * constant so it does not add to the inline-style ratchet (see
 * `src/test/ui-ratchet.test.ts`).
 */
const saveErrorStyle: React.CSSProperties = {
  color: 'var(--color-danger)',
  border: '1px solid var(--color-danger)',
  borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3)',
  margin: 'var(--space-3) 0 0 0',
  fontSize: 'var(--font-size-sm)',
};

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
  /** Optional: invoked when the user cancels editing (e.g. deselect / back to list). */
  onCancel?: () => void;
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
  workspaceId: _workspaceId,  // retained for API compatibility; not consumed here
  onSaved,
  onCancel,
}) => {
  const { t } = useTranslation();
  const { isFieldVisible, isFieldRequired } = useEntityType();
  const { activeWorkspace } = useWorkspace();
  const isExtendedPreset = activeWorkspace?.preset === 'extended';
  // #412: `acceptance_criteria` is part of `mandatory_fields` for BOTH the
  // 'standard' and 'extended' presets (backend/presets/registry.py), and is
  // enforced server-side by workflow.precondition_rules.check_mandatory_fields
  // on the approval transition (draft->approved for standard, in_review->approved
  // for extended — see precondition_rules.py module docstring). Unlike
  // change_reason (extended-only), gating this field's visibility on
  // isExtendedPreset alone would still leave 'standard' workspace users
  // stuck with an un-fixable approval-transition error.
  const isAcceptanceCriteriaRequiredPreset =
    activeWorkspace?.preset === 'standard' || isExtendedPreset;

  // Form state
  const [title, setTitle] = useState(requirement.title);
  const [description, setDescription] = useState(requirement.description);
  const [acceptanceCriteria, setAcceptanceCriteria] = useState(
    requirement.acceptance_criteria || ''
  );
  const [category, setCategory] = useState(requirement.category);
  // REQ-143/REQ-161: the lifecycle state is owned by the WorkflowEngine and is
  // now edited through the shared <WorkflowStatusEditor/>, which fetches the
  // allowed transitions and performs them via the WorkflowFacade transitions
  // API. The form no longer carries a status <select> of its own.
  const [changeReason, setChangeReason] = useState(requirement.change_reason || '');
  const [type, setType] = useState<RequirementType>(requirement.type || 'SyReq');
  const [complexityFibonacci, setComplexityFibonacci] = useState<number | ''>(
    requirement.complexity_fibonacci || 1
  );
  const [verificationMethod, setVerificationMethod] = useState<VerificationMethod | ''>(
    requirement.verification_method || ''
  );
  // Issue #394: V-model hierarchy level (L0-L4). `''` represents "not set"
  // (backend field is nullable and NULL until assigned explicitly).
  const [level, setLevel] = useState<RequirementLevel | ''>(
    requirement.level ?? ''
  );
  // REQ-L2-AS-037: user-defined custom fields (stored on the backing Artifact).
  const [customFields, setCustomFields] = useState<CustomFields>(
    requirement.custom_fields || {}
  );

  // UI state
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveErrorRef = useRef<HTMLParagraphElement | null>(null);

  // Code review regression: unlike every sibling editor (AdrForm, RiskForm,
  // IssueForm, TestCaseForm all have this reset effect keyed on their
  // entity prop), this form never resynced its local state when a
  // different `requirement` was selected — its fields were only ever
  // initialised from the initial `useState(requirement.X)` call, so
  // switching the selected requirement in the list left the form showing
  // (and, on Save, silently overwriting the new requirement with) the
  // previously-selected one's stale field values.
  useEffect(() => {
    setTitle(requirement.title);
    setDescription(requirement.description);
    setAcceptanceCriteria(requirement.acceptance_criteria || '');
    setCategory(requirement.category);
    setChangeReason(requirement.change_reason || '');
    setType(requirement.type || 'SyReq');
    setComplexityFibonacci(requirement.complexity_fibonacci || 1);
    setVerificationMethod(requirement.verification_method || '');
    setLevel(requirement.level ?? '');
    setCustomFields(requirement.custom_fields || {});
    setSaveError(null);
  }, [requirement]);

  // #344: bring a freshly raised save error into view. `scrollIntoView` is
  // absent in jsdom, hence the optional call.
  useEffect(() => {
    if (saveError) {
      saveErrorRef.current?.scrollIntoView?.({ block: 'nearest' });
    }
  }, [saveError]);

  /**
   * Validate form data before saving.
   */
  const validateForm = useCallback((): string | null => {
    if (!title.trim()) {
      return t('editor.titleRequired');
    }
    // #344: the backend requires a change_reason on EVERY update in the
    // extended preset (PresetPolicyService.is_change_reason_required), and
    // rejects the whole PATCH with 400 otherwise — the user's edit is lost.
    // The old guard additionally required `isFieldRequired('change_reason')`,
    // which comes from AttributeVisibilityConfig and defaults to `false` when
    // no config row exists (the default state), so the client-side check never
    // fired and every save in an extended workspace silently 400'd.
    // The workspace preset is the authority here; an explicit
    // AttributeVisibilityConfig can only make the field required in addition.
    if ((isExtendedPreset || isFieldRequired('change_reason')) && !changeReason.trim()) {
      return t('req.changeReasonRequired');
    }

    // #412: unlike change_reason, acceptance_criteria is NOT enforced on
    // every write — it is only checked by
    // workflow.precondition_rules.check_mandatory_fields at the
    // approval-transition (draft->approved for 'standard', in_review->approved
    // for 'extended'). Blocking every Save here would forbid legitimate
    // incomplete drafts, so this form deliberately does not hard-block Save;
    // it only renders the field (see isAcceptanceCriteriaRequiredPreset
    // below) so users have a way to fill it in before attempting approval —
    // the actual gate error still surfaces from the transition endpoint.

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
      // REQ-143: `status` is NOT sent here — it is a read-only WorkflowEngine
      // mirror. A lifecycle change is a separate, gated transition call below.
      const updateData: Record<string, unknown> = {
        title,
        description,
        acceptance_criteria: acceptanceCriteria,
        category,
        type,
        // Issue #394: always sent (like `category`) — `''` maps to `null` so
        // an explicit "not set" selection actually clears a previously
        // assigned level instead of being silently dropped.
        level: level === '' ? null : level,
      };

      // #344: never send an empty `change_reason`. It is not a content field —
      // it annotates *this* edit. Sending `""` cannot satisfy the extended
      // preset's mandatory-reason policy (the backend 400s either way) and in
      // a non-extended workspace it would blank the reason recorded for the
      // previous revision. Only a reason the user actually typed is sent.
      if (changeReason.trim()) {
        updateData.change_reason = changeReason.trim();
      }

      // Include type-specific fields
      if (type === 'SyReq') {
        updateData.complexity_fibonacci = complexityFibonacci === '' ? null : Number(complexityFibonacci);
        updateData.verification_method = verificationMethod || null;
      }

      // REQ-L2-AS-037: always send custom_fields (backend validates the map).
      updateData.custom_fields = customFields;

      await requirementsApi.update(requirement.id, updateData);

      // REQ-161: lifecycle transitions are no longer bundled with Save — they
      // run independently through <WorkflowStatusEditor/> (WorkflowFacade).
      onSaved();
    } catch (err: unknown) {
      // REQ-009: extract field-level details from the ApiError response so
      // users see the actual validation message, not just the generic fallback.
      setSaveError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }, [
    validateForm,
    requirement.id,
    title,
    description,
    acceptanceCriteria,
    category,
    changeReason,
    type,
    complexityFibonacci,
    verificationMethod,
    level,
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
            {/* REQ: primary actions live in the header for consistency across
                all artifact forms (P1-f). */}
            <div style={{ display: 'flex', gap: 'var(--space-3)' }}>
              <button
                data-testid="save-btn"
                className="btn-primary"
                onClick={() => void handleSave()}
                disabled={isSaving}
              >
                {isSaving ? t('actions.saving') : t('actions.save')}
              </button>
              {onCancel && (
                <button
                  data-testid="cancel-btn"
                  className="btn-ghost"
                  onClick={onCancel}
                  disabled={isSaving}
                >
                  {t('actions.cancel')}
                </button>
              )}
            </div>
          </div>
          {/* #344: a failed save must never be invisible. The banner sits
              directly under the action row (the Save button lives in the
              header), and scrolls itself into view, so the user cannot miss it
              no matter how far down the long form they had scrolled. */}
          {saveError && (
            <p
              ref={saveErrorRef}
              role="alert"
              data-testid="req-save-error"
              style={saveErrorStyle}
            >
              {saveError}
            </p>
          )}
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
            {t('req.section.generalInformation')}
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

          {/* #412: acceptance_criteria has a persistence.models field and is
              part of `mandatory_fields` for the 'standard'/'extended' presets
              (backend/presets/registry.py), enforced at the approval
              transition (workflow/precondition_rules.py). It previously had
              no editor field at all, so a user hitting that gate had no way
              to satisfy it. Rendered unconditionally (like `description`
              above) so a 'minimal' workspace upgrading its preset later does
              not lose any criteria a user already entered; the asterisk only
              signals the preset-driven requirement. */}
          <label htmlFor="req-acceptance-criteria" style={labelStyle}>
            {t('editor.acceptanceCriteria')}{' '}
            {isAcceptanceCriteriaRequiredPreset && (
              <span className={styles.requiredMarker}>*</span>
            )}
          </label>
          <textarea
            id="req-acceptance-criteria"
            data-testid="req-acceptance-criteria"
            value={acceptanceCriteria}
            onChange={(e) => setAcceptanceCriteria(e.target.value)}
            rows={4}
            style={inputStyle}
            placeholder={t('editor.acceptanceCriteriaPlaceholder')}
          />
          {isAcceptanceCriteriaRequiredPreset && !acceptanceCriteria.trim() && (
            <p data-testid="req-acceptance-criteria-hint" className={styles.fieldHint}>
              {t('req.acceptanceCriteriaRequired')}
            </p>
          )}
        </div>

        {/* SECTION: Classification & Properties */}
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
            {t('req.section.classificationProperties')}
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
                <label style={labelStyle}>
                  {t('editor.workflowState')}
                </label>
                {/* REQ-161: unified WorkflowEngine-driven status editor. Current
                    state is read-only; transitions run through the WorkflowFacade
                    and re-fetch the requirement on completion. */}
                <WorkflowStatusEditor
                  artifactType="requirement"
                  artifactId={requirement.id}
                  currentStatus={requirement.status}
                  disabled={isSaving}
                  onTransitionComplete={onSaved}
                />
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
                  {/* #344: these must stay in sync with the backend's
                      RequirementType choices (persistence/models.py) and the
                      DB CHECK constraint from migration 0050. The dropdown
                      used to offer SWReq/HWReq, which no longer exist there —
                      picking one made the whole PATCH 400 and lost the edit. */}
                  <option value="SyReq">{t('reqType.SyReq')}</option>
                  <option value="UseCase">{t('reqType.UseCase')}</option>
                  <option value="FeatureReq">{t('reqType.FeatureReq')}</option>
                </select>
              </div>
            )}

            {/* Issue #394: V-model hierarchy level (L0-L4). Previously the
                model field existed (`persistence.models.Requirement.level`)
                but had no editor — this is the field-level equivalent of the
                `L{n}` badge ArchitectureElement already shows. Rendered
                unconditionally (no isFieldVisible gate, like `type`'s
                sibling `complexity_fibonacci`/`verification_method` fields
                are gated by SyReq-only visibility) since the level applies to
                every requirement type, not just SyReq. */}
            <div>
              <label htmlFor="req-level" style={labelStyle}>
                {t('editor.level')}
              </label>
              <select
                id="req-level"
                data-testid="req-level"
                value={level}
                onChange={(e) => setLevel(e.target.value === '' ? '' : (Number(e.target.value) as RequirementLevel))}
                style={inputStyle}
              >
                <option value="">{t('editor.levelUnset')}</option>
                {REQUIREMENT_LEVELS.map((lvl) => (
                  <option key={lvl} value={lvl}>
                    {t(`reqLevel.L${lvl}`)}
                  </option>
                ))}
              </select>
            </div>

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

        {/* SECTION: Workspace custom fields (REQ-016) — workspace-defined,
            typed fields persisted per artifact instance. Only shown for an
            existing requirement (needs an artifact id). */}
        {requirement.artifact_id && (
          <ArtifactCustomFields artifactId={requirement.artifact_id} />
        )}

        {/* SECTION: Change Control */}
        {/* #344: in the extended preset the change reason is mandatory
            server-side, so the field must be rendered regardless of the
            AttributeVisibilityConfig — hiding it would make every save
            impossible to complete. */}
        {isExtendedPreset && (
          <div style={{ marginBottom: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
              {t('req.section.changeControl')}
            </h3>
            
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
          </div>
        )}

        {/* #344: the save error banner moved up next to the Save button in the
            header — down here it was ~350 lines below the fold, so a failed
            save looked like nothing happened at all. */}

        {/* Actions moved to the header (P1-f). Diff is served by the
            ArtifactInspector right sidebar (REQ-001, REQ-L2-RF-036). */}

      </div>
    </div>
  );
};

RequirementForm.displayName = 'RequirementForm';
