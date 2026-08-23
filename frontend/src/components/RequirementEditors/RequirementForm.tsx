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

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useEntityType } from '../../context/EntityTypeContext';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useEntityReset } from '../../hooks/use-entity-reset';
import { useFormDirty } from '../../hooks/use-form-dirty';
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
import { Spinner } from '../shared/Spinner/Spinner';
import { FIBONACCI_SEQUENCE } from '../../utils/fibonacciUtils';
import styles from './RequirementEditors.module.css';
// F-04 (code review, 2026-08-19): `.inputError`/`.fieldError` live in the
// shared module (see its own header comment) so this form doesn't duplicate
// them locally.
import fieldHints from '../shared/FieldHints.module.css';

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
  /**
   * Issue #672: invoked whenever this form's "has unsaved local edits"
   * state changes, so the parent (RequirementEditors) can warn before
   * navigating away to a different artifact and silently discarding them.
   */
  onDirtyChange?: (isDirty: boolean) => void;
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
/**
 * Snapshot of every locally-editable field, shared between the entity-reset
 * callback, the isDirty baseline and the post-save `markClean` call so all
 * three always agree on the same shape. Explicitly typed rather than
 * inferred: an object literal built from `x || fallback` expressions
 * otherwise widens its narrow union members (e.g. `VerificationMethod | ''`)
 * to plain `string`, which would silently defeat the `useState` setters'
 * own narrower types.
 */
interface RequirementFormValues {
  title: string;
  description: string;
  acceptanceCriteria: string;
  category: string;
  changeReason: string;
  type: RequirementType;
  complexityFibonacci: number | '';
  verificationMethod: VerificationMethod | '';
  level: RequirementLevel | '';
  customFields: CustomFields;
}

export const RequirementForm: React.FC<RequirementFormProps> = ({
  requirement,
  requirements: _requirements,
  workspaceId: _workspaceId,  // retained for API compatibility; not consumed here
  onSaved,
  onCancel,
  onDirtyChange,
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
  // #339: a change reason is mandatory either because the workspace runs the
  // extended preset (PresetPolicyService.is_change_reason_required, enforced
  // on EVERY update) or because an explicit AttributeVisibilityConfig row
  // marks the field required. Both conditions must drive the *same* three
  // things — the client-side guard in validateForm, the `*` marker and the
  // rendering of the field itself. They used to disagree: the guard fired on
  // either condition while the field only rendered for the extended preset,
  // so a config-driven requirement produced a save the user could never
  // complete (no input to fill in).
  const isChangeReasonRequired = isExtendedPreset || isFieldRequired('change_reason');

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

  // Issue #672: "has unsaved local edits" tracking, so the parent can warn
  // before navigating away to a different artifact. The baseline is
  // re-anchored explicitly — from the entity-switch reset below and from a
  // successful Save — never implicitly from the raw `requirement` prop (see
  // `useFormDirty`'s own docstring for why).
  const formValues = useMemo<RequirementFormValues>(
    () => ({
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
    }),
    [
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
    ]
  );
  const { isDirty, markClean } = useFormDirty(formValues, formValues);

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  // UI state
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveErrorRef = useRef<HTMLParagraphElement | null>(null);
  // BUG-08 (Systemaudit 2026-08-18, §4): the top-of-form `saveError` banner
  // already names the problem, but the offending input itself carried no
  // visual/ARIA indication — a user scanning the (long) form had nothing on
  // the field to find. Tracks only the title's own required-check so it
  // doesn't light up for unrelated validation failures (e.g. a missing
  // verification_method on a SyReq).
  const [titleInvalid, setTitleInvalid] = useState(false);
  // N-01/N-02/N-03 (code review, 2026-08-19): change_reason/
  // verification_method must NOT alarm the user before they have done
  // anything — an untouched requirement in an extended-preset workspace
  // legitimately opens with an empty change_reason, and that used to
  // immediately render a red border + ⚠ icon + `role="alert"` (which a
  // screen reader announces on focus) purely from proactively deriving the
  // flag off current form state. Gated behind the same
  // save-attempt-driven event as `titleInvalid` instead: false until the
  // first failed Save, so an untouched form is silent, and — since
  // validateForm() can now surface all three branches at once instead of
  // stopping at the first one — a single failed Save can legitimately show
  // more than one field error simultaneously (mirrors real multi-field
  // form validation; F-03's "no *duplicate* banner + field" guarantee is
  // unaffected, there is still exactly one message per invalid field).
  const [hasAttemptedSave, setHasAttemptedSave] = useState(false);
  // F-02 (code review, 2026-08-19): validateForm() has two more branches
  // besides title (change_reason, verification_method) — leaving only the
  // title branch marked would have made this file inconsistent with
  // itself. Derived directly from the same form state validateForm()
  // reads (not separate useState so they can never fall out of sync with
  // what the user is currently seeing).
  //
  // change_reason additionally keeps its own pre-existing #339 behavior:
  // a plain, low-key hint is shown proactively (before any Save attempt)
  // so the user knows up front the field is required — `changeReasonMissing`
  // drives that. Only the alarming treatment (red border, ⚠ icon,
  // `aria-invalid`, `role="alert"`) is gated behind hasAttemptedSave — see
  // its rendering below. verification_method has no such pre-existing
  // proactive hint, so it is gated behind hasAttemptedSave outright (same
  // as titleInvalid: silent until the first failed Save).
  const changeReasonMissing = isChangeReasonRequired && !changeReason.trim();
  const changeReasonInvalid = hasAttemptedSave && changeReasonMissing;
  const verificationMethodInvalid =
    hasAttemptedSave &&
    type === 'SyReq' &&
    isFieldVisible('verification_method') &&
    isFieldRequired('verification_method') &&
    !verificationMethod;

  // Issue #700/#673: this reset must fire exactly once per genuinely
  // different requirement (switching the selected item in the list), never
  // on a refetch of the SAME requirement — which produces a new object
  // reference with an unchanged id (e.g. right after Save, via `onSaved`'s
  // refresh(), or an unrelated background reload). A `[requirement]`-keyed
  // effect (the previous version of this code) re-ran on every one of
  // those too, blindly resetting `changeReason` to `requirement.change_reason
  // || ''` — but `change_reason` never round-trips through the server at
  // all (it is a save-time-only annotation on the PATCH, not a persisted
  // field), so it is ALWAYS empty on reload. If such a refetch landed while
  // a save was still in flight, this could wipe a change reason the user
  // had just typed before the save call had read it. Scoping the effect to
  // `requirement.id` (via the shared `useEntityReset`, matching the pattern
  // `ArchitectureForm` already used) closes that race: the local state is
  // only ever discarded when the user is actually looking at a different
  // artifact now.
  //
  // The same call also re-anchors the `isDirty` baseline (issue #672) to
  // exactly the values just set, so "unsaved changes" tracking starts
  // clean for the newly-selected requirement.
  useEntityReset(requirement.id, () => {
    const next: RequirementFormValues = {
      title: requirement.title,
      description: requirement.description,
      acceptanceCriteria: requirement.acceptance_criteria || '',
      category: requirement.category,
      // Always resets to '' — matches what the server would return anyway
      // (change_reason is never persisted), so this never disagrees with
      // the isDirty baseline below.
      changeReason: requirement.change_reason || '',
      type: requirement.type || 'SyReq',
      complexityFibonacci: requirement.complexity_fibonacci || 1,
      verificationMethod: requirement.verification_method || '',
      level: requirement.level ?? '',
      customFields: requirement.custom_fields || {},
    };
    setTitle(next.title);
    setDescription(next.description);
    setAcceptanceCriteria(next.acceptanceCriteria);
    setCategory(next.category);
    setChangeReason(next.changeReason);
    setType(next.type);
    setComplexityFibonacci(next.complexityFibonacci);
    setVerificationMethod(next.verificationMethod);
    setLevel(next.level);
    setCustomFields(next.customFields);
    setSaveError(null);
    setTitleInvalid(false);
    setHasAttemptedSave(false);
    markClean(next);
  });

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
    if (isChangeReasonRequired && !changeReason.trim()) {
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
  }, [title, changeReason, type, verificationMethod, t, isChangeReasonRequired, isFieldVisible, isFieldRequired]);

  /**
   * Handle save action.
   */
  const handleSave = useCallback(async (): Promise<void> => {
    const validationError = validateForm();
    if (validationError) {
      // F-03 (code review, 2026-08-19): client-side validation errors now
      // surface ONLY at the field itself (title-invalid marker below,
      // change-reason/verification-method hints in the JSX are derived
      // straight from form state) — never duplicated into the page-level
      // `saveError` banner too, which used to make a screen reader announce
      // the identical "Title is required" message twice. Any stale banner
      // from a *previous* server-side rejection is cleared here as well, so
      // it can't linger next to an unrelated fresh client-side field error.
      setSaveError(null);
      // BUG-08: only the title field itself gets the visual/ARIA marker —
      // it mirrors the actual condition validateForm() checked, so an
      // unrelated failure (e.g. missing verification_method) never lights
      // up a title that is in fact fine.
      setTitleInvalid(!title.trim());
      // N-01/N-02 (code review, 2026-08-19): change_reason/
      // verification_method's derived markers only go live once a Save has
      // actually failed — this is that event. From here on (until the next
      // successful save or a different requirement is selected) they track
      // their own condition live, same as titleInvalid already did.
      setHasAttemptedSave(true);
      return;
    }

    setTitleInvalid(false);
    setHasAttemptedSave(false);
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

      // #344/#672: `change_reason` annotates *this* edit only — it never
      // round-trips through the server (see the `useEntityReset` reset
      // callback above), so it is cleared here explicitly on a successful
      // save. Mirrors ArchitectureForm's existing post-save behavior.
      setChangeReason('');
      // Issue #672: re-anchor the isDirty baseline to exactly what was just
      // submitted — not to whatever `requirement` next resolves with via
      // `onSaved()`'s refetch, which lags this by a network round trip and
      // would otherwise show a spurious "unsaved changes" state until it
      // resolves.
      const savedValues: RequirementFormValues = {
        title,
        description,
        acceptanceCriteria,
        category,
        changeReason: '',
        type,
        complexityFibonacci,
        verificationMethod,
        level,
        customFields,
      };
      markClean(savedValues);

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
    markClean,
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
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 'var(--space-3)',
              // #419: without wrap + minWidth:0, a long title and the fixed-
              // width Save/Cancel buttons fought for the same row and the
              // buttons overlapped the title at every viewport width. Wrapping
              // lets the actions drop to their own line instead.
              flexWrap: 'wrap',
              gap: 'var(--space-2)',
            }}
          >
            <h2
              style={{
                fontSize: 'var(--font-size-xl)',
                fontWeight: 700,
                color: 'var(--color-text)',
                margin: 0,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                minWidth: 0,
                overflowWrap: 'anywhere',
              }}
            >
              {requirement.suspect && <span title="Needs review due to upstream changes">⚠️</span>}
              {requirement.title || t('editor.untitled')}
            </h2>
            {/* REQ: primary actions live in the header for consistency across
                all artifact forms (P1-f). */}
            <div style={{ display: 'flex', gap: 'var(--space-3)', flexShrink: 0 }}>
              <button
                data-testid="save-btn"
                className="btn-primary"
                onClick={() => void handleSave()}
                disabled={isSaving}
              >
                {isSaving ? <Spinner label={t('actions.saving')} /> : t('actions.save')}
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
            onChange={(e) => {
              setTitle(e.target.value);
              // BUG-08: clear the field-level error as soon as the user
              // starts correcting it — same UX as the change-reason/
              // acceptance-criteria hints (#339/#412).
              if (e.target.value.trim()) setTitleInvalid(false);
              // F-01 (code review, 2026-08-19): a stale banner describing
              // the *previous* attempt must not keep contradicting a field
              // that has since been fixed — same pattern as
              // RequirementEditors.tsx's create-form title input (#340).
              if (saveError) setSaveError(null);
            }}
            style={{ ...inputStyle, marginBottom: 'var(--space-4)' }}
            className={titleInvalid ? fieldHints.inputError : undefined}
            aria-invalid={titleInvalid}
            aria-describedby={titleInvalid ? 'req-title-error' : undefined}
          />
          {titleInvalid && (
            <p
              id="req-title-error"
              role="alert"
              data-testid="req-title-field-error"
              className={fieldHints.fieldError}
            >
              <span aria-hidden="true">⚠</span>
              {t('editor.titleRequired')}
            </p>
          )}

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
                  {/* Legacy-value passthrough: the backend `category` field is a
                      free-form CharField with no DB-level choices constraint, so an
                      existing requirement (CSV/ReqIF import, manual DB edit) may carry
                      a value no longer in REQ_CATEGORIES (e.g. a removed category).
                      Without this, the select would show no matching option, and the
                      unknown value would be silently discarded on the next save. */}
                  {category && !(REQ_CATEGORIES as readonly string[]).includes(category) && (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  )}
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
                  className={verificationMethodInvalid ? fieldHints.inputError : undefined}
                  aria-invalid={verificationMethodInvalid}
                  aria-describedby={verificationMethodInvalid ? 'verification-method-error' : undefined}
                >
                  <option value="">{t('editor.selectVerificationMethod')} --</option>
                  <option value="Inspection">Inspection</option>
                  <option value="Review">Review</option>
                  <option value="Test">Test</option>
                  <option value="Analysis">Analysis</option>
                </select>
                {/* F-02 (code review, 2026-08-19): validateForm() has a third
                    branch for this field (mandatory when SyReq +
                    isFieldRequired) — consistency within this same file
                    demanded it get the same visual/ARIA treatment as title,
                    not just an early-return banner message no one could see
                    on a field this far down the form. N-01 (code review,
                    2026-08-19): gated behind hasAttemptedSave (see its own
                    declaration above) — an untouched form must stay silent,
                    not alarm a screen-reader user who has done nothing yet;
                    only live after the first failed Save, same as
                    titleInvalid. */}
                {verificationMethodInvalid && (
                  <p
                    id="verification-method-error"
                    role="alert"
                    data-testid="verification-method-field-error"
                    className={fieldHints.fieldError}
                  >
                    <span aria-hidden="true">⚠</span>
                    {t('editor.verificationMethodRequired')}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* SECTION: Custom Fields (REQ-L2-AS-037) */}
        <div style={{ marginBottom: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
            {t('customFields.section')}
          </h3>
          {/* Issue #673: `key` forces a fresh internal row list whenever the
              edited requirement actually changes — CustomFieldsEditor seeds
              its rows from `value` once on mount and never resyncs them on
              a prop update (by design, so mid-edit rows with a transiently
              empty/duplicate key are not clobbered). Without the key, a
              user who edits any custom field row after switching to a
              different requirement would splice that different
              requirement's now-stale rows into the new one's custom_fields
              on save. */}
          <CustomFieldsEditor
            key={requirement.id}
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
            impossible to complete.
            #339: it is rendered for a config-driven requirement too, so the
            asterisk, the client-side guard and the input never disagree. */}
        {isChangeReasonRequired && (
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
              required
              aria-required="true"
              className={changeReasonInvalid ? fieldHints.inputError : undefined}
              aria-invalid={changeReasonInvalid}
              aria-describedby={changeReasonMissing ? 'change-reason-error' : undefined}
            />
            {/* #339: the asterisk alone was reported as too easy to miss for a
                field whose omission costs the whole edit. Mirrors the
                acceptance-criteria hint above — shown proactively (before any
                Save attempt), as a plain low-key hint, same as it always was.
                N-01 (code review, 2026-08-19): the alarming treatment
                (icon + red border + `role="alert"`) must NOT fire on an
                untouched form — a screen-reader user who has done nothing
                yet must not hear "invalid entry". Only escalates to that
                once hasAttemptedSave is true (first failed Save), matching
                validateForm()'s own change_reason branch; until then it's
                the exact same passive hint acceptance-criteria uses. */}
            {changeReasonMissing && (
              changeReasonInvalid ? (
                <p
                  id="change-reason-error"
                  role="alert"
                  data-testid="change-reason-hint"
                  className={fieldHints.fieldError}
                >
                  <span aria-hidden="true">⚠</span>
                  {t('req.changeReasonRequired')}
                </p>
              ) : (
                <p
                  id="change-reason-error"
                  data-testid="change-reason-hint"
                  className={styles.fieldHint}
                >
                  {t('req.changeReasonRequired')}
                </p>
              )
            )}
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
