// ReadOnlyField was removed with the identity-block rewrite: UID, level
// and version now render through <ArtifactId>, <LevelBadge> and
// <VersionBadge> (UI concept ch. 12.4) instead of a generic mono
// read-only cell.

/**
 * ArchitectureForm Component — REQ-L3-RF004-004, REQ-L1-084
 *
 * Editable form for architecture element details with:
 * - UID + Version read-only in header
 * - Standard fields: title, element_type, parent, description
 * - Dynamic ASIL level dropdown (if visible in config)
 * - Dynamic Make-or-Buy dropdown (if visible in config)
 * - Computed hierarchy level display
 * - Change reason field (extended preset only)
 * - Save, Delete, View Diff actions
 *
 * leaf_id: COMP-RF-004-Form
 * req_id: REQ-L3-RF004-004, REQ-L1-084
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useEntityType } from '../../context/EntityTypeContext';
import { useEntityReset } from '../../hooks/use-entity-reset';
import { useFormDirty } from '../../hooks/use-form-dirty';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';
import { ArtifactDiff } from '../ArtifactDiff/ArtifactDiff';
import { VersionBadge } from '../shared/VersionBadge';
import { ArtifactId } from '../shared/ArtifactId';
import { LevelBadge } from '../shared/LevelBadge';
import { collectSelfAndDescendantIds } from '../shared/WorkspaceTree';
import { ArtifactCustomFields } from '../shared/ArtifactCustomFields';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';
import { architectureApi } from '../../api/architecture';
import { extractErrorMessage } from '../../api/client';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import fieldHints from '../shared/FieldHints.module.css';
import styles from './ArchitectureForm.module.css';
import type { CustomFields } from '../../types';
import { ASIL_LEVEL_OPTIONS, MAKE_OR_BUY_OPTIONS } from '../../utils/asilUtils';
import type { ArchitectureElement, ASILLevel, MakeOrBuyDecision, ElementType } from '../../types';

interface ArchitectureFormProps {
  /**
   * Architecture element to edit.
   */
  element: ArchitectureElement;

  /**
   * All workspace elements (for parent picker, cycle guard).
   */
  elements: ArchitectureElement[];

  /**
   * Callback when save succeeds.
   */
  onSaved: () => void;

  /**
   * Callback to delete the element.
   */
  onDelete: (id: string) => void;

  /**
   * Whether to show change_reason field (extended preset).
   */
  isExtendedPreset: boolean;

  /**
   * Called when user clicks "AI Decompose" button.
   */
  onDecompose?: () => void;

  /**
   * Issue #672: invoked whenever this form's "has unsaved local edits"
   * state changes, so the parent (ArchitectureEditors) can warn before
   * navigating away to a different element and silently discarding them.
   */
  onDirtyChange?: (isDirty: boolean) => void;
}

/**
 * Fallback element-type suggestions shown when the workspace does not yet
 * contain any ArchitectureElement (REQ-006 / D5). Mirrors the values of the
 * former fixed choice list so existing muscle memory keeps working, while
 * the field itself is now free text.
 */
const DEFAULT_ELEMENT_TYPE_SUGGESTIONS = ['System', 'Subsystem', 'Component', 'Interface', 'Function'];

// Issue #669: the former `labelStyle` / `inputStyle` / `readOnlyStyle`
// `React.CSSProperties` constants now live in `ArchitectureForm.module.css`
// as `.label` / `.input` / `.readOnlyValue`, mirroring how RequirementForm
// keeps its chrome out of the TSX.
//
// Issue #670: the local `DeleteConfirmationDialog` was removed — deletion now
// runs through the shared `<ConfirmDialog>` like every other artifact form,
// so all artifact types share one delete interaction. Its `data-testid`s
// (`arch-form-delete-dialog`, `arch-cancel-delete-btn`, `confirm-delete-btn`)
// are preserved verbatim via ConfirmDialog's testId overrides, because the
// Playwright suite selects on them.

// ReadOnlyField was removed with the identity-block rewrite: UID, level and
// version now render through <ArtifactId>, <LevelBadge> and <VersionBadge>
// (UI concept ch. 12.4) instead of a generic mono read-only cell that
// re-implemented the identifier style inline.

/**
 * ArchitectureForm — implements REQ-L3-RF004-004 & REQ-L1-084
 *
 * Editable form with ASIL/Make-or-Buy dropdowns,
 * dynamic field visibility, and UID/Version header.
 */

/**
 * Snapshot of every locally-editable field, shared between the entity-reset
 * callback, the isDirty baseline and the post-save `markClean` call so all
 * three always agree on the same shape (see the identical rationale on
 * `RequirementFormValues` in RequirementForm.tsx — object literals built
 * from `x ?? fallback` expressions otherwise widen narrow union members).
 */
interface ArchitectureFormValues {
  title: string;
  description: string;
  elementType: ElementType;
  parentId: string;
  asilLevel: ASILLevel;
  makeOrBuy: MakeOrBuyDecision;
  changeReason: string;
  customFields: CustomFields;
}

export function ArchitectureForm({
  element,
  elements,
  onSaved,
  onDelete,
  isExtendedPreset,
  onDecompose,
  onDirtyChange,
}: ArchitectureFormProps): JSX.Element {
  const { t } = useTranslation();
  const { visibleFields } = useEntityType();

  // Form state
  const [title, setTitle] = useState(element.title);
  const [description, setDescription] = useState(element.description);
  const [elementType, setElementType] = useState(element.element_type);
  const [parentId, setParentId] = useState<string>(element.parent_id ?? '');
  const [asilLevel, setAsilLevel] = useState<ASILLevel>(element.asil_level ?? null);
  const [makeOrBuy, setMakeOrBuy] = useState<MakeOrBuyDecision>(element.make_or_buy ?? null);
  const [changeReason, setChangeReason] = useState(element.change_reason ?? '');
  // REQ-L2-AS-037: user-defined custom fields (stored on the backing Artifact).
  const [customFields, setCustomFields] = useState<CustomFields>(element.custom_fields ?? {});

  // Issue #672: "has unsaved local edits" tracking (see the analogous block
  // in RequirementForm — the baseline is re-anchored explicitly below, from
  // the entity-switch reset and from a successful Save, never implicitly
  // from the raw `element` prop).
  const formValues = useMemo<ArchitectureFormValues>(
    () => ({
      title,
      description,
      elementType,
      parentId,
      asilLevel,
      makeOrBuy,
      changeReason,
      customFields,
    }),
    [title, description, elementType, parentId, asilLevel, makeOrBuy, changeReason, customFields]
  );
  const { isDirty, markClean } = useFormDirty(formValues, formValues);

  useEffect(() => {
    onDirtyChange?.(isDirty);
    // Cleanup: report "not dirty" on unmount so a stale `true` from a
    // previous mount (e.g. after Cancel/Delete) can't make the parent show
    // an unsaved-changes dialog for a form that no longer exists.
    return () => {
      onDirtyChange?.(false);
    };
  }, [isDirty, onDirtyChange]);

  // UI state
  const [isSaving, setIsSaving] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  // REQ-006 (D5): element_type autocomplete state — suggestions are derived
  // from the types already used in this workspace (falls back to
  // DEFAULT_ELEMENT_TYPE_SUGGESTIONS when the workspace has none yet).
  const [typeSuggestions, setTypeSuggestions] = useState<string[]>([]);
  const [typeDropdownOpen, setTypeDropdownOpen] = useState(false);

  // Sync form state when element changes — issue #673: shares
  // `useEntityReset` with RequirementForm so both forms fire exactly once
  // per genuinely different entity (never on a same-id refetch), instead of
  // two hand-written `[x.id]`-keyed effects that can silently drift apart.
  useEntityReset(element.id, () => {
    const next: ArchitectureFormValues = {
      title: element.title,
      description: element.description,
      elementType: element.element_type,
      parentId: element.parent_id ?? '',
      asilLevel: element.asil_level ?? null,
      makeOrBuy: element.make_or_buy ?? null,
      changeReason: element.change_reason ?? '',
      customFields: element.custom_fields ?? {},
    };
    setTitle(next.title);
    setDescription(next.description);
    setElementType(next.elementType);
    setParentId(next.parentId);
    setAsilLevel(next.asilLevel);
    setMakeOrBuy(next.makeOrBuy);
    setChangeReason(next.changeReason);
    setCustomFields(next.customFields);
    markClean(next);
  });

  // Client-side cycle guard — same computation the tree's drag & drop uses to
  // refuse a drop, so both parent-changing surfaces forbid the same set.
  const invalidParentIds = useMemo(
    (): Set<string> =>
      collectSelfAndDescendantIds(
        elements.map((el) => ({ id: el.id, parentId: el.parent_id ?? null })),
        element.id,
      ),
    [elements, element.id],
  );

  const parentOptions = useMemo(
    () => elements.filter((el) => !invalidParentIds.has(el.id)),
    [elements, invalidParentIds]
  );

  // REQ-006 (D5): element types used anywhere in the workspace, de-duplicated
  // and sorted — replaces the former fixed ElementType choice list.
  const allElementTypes = useMemo((): string[] => {
    const existing = Array.from(
      new Set(
        elements
          .map((el): string => el.element_type)
          .filter((type) => Boolean(type))
      )
    ).sort();
    return existing.length > 0 ? existing : DEFAULT_ELEMENT_TYPE_SUGGESTIONS;
  }, [elements]);

  const handleElementTypeChange = useCallback(
    (value: string): void => {
      setElementType(value as ElementType);
      const filtered = value
        ? allElementTypes.filter((ty) => ty.toLowerCase().includes(value.toLowerCase()))
        : allElementTypes;
      setTypeSuggestions(filtered);
      setTypeDropdownOpen(filtered.length > 0);
    },
    [allElementTypes]
  );

  const handleTypeSuggestionClick = useCallback((suggestion: string): void => {
    setElementType(suggestion as ElementType);
    setTypeDropdownOpen(false);
  }, []);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    try {
      const payload: Partial<ArchitectureElement> & {
        change_reason?: string;
        expected_version?: number;
      } = {
        title,
        description,
        element_type: elementType,
        parent_id: parentId === '' ? null : parentId,
        asil_level: asilLevel,
        make_or_buy: makeOrBuy,
        // REQ-L2-AS-037: always send custom_fields (backend validates the map).
        custom_fields: customFields,
        // Systemaudit 2026-08-27 UI-08: without this the backend's 409
        // optimistic-lock guard (ArchitectureService.update_architecture_element)
        // could never actually fire from this UI — every save silently
        // overwrote whatever the server currently held, race or not.
        expected_version: element.version,
      };
      if (isExtendedPreset && changeReason.trim()) {
        payload.change_reason = changeReason.trim();
      }
      await architectureApi.update(element.id, payload);
      setChangeReason('');
      // Issue #672: re-anchor the isDirty baseline to what was just
      // submitted rather than waiting on `onSaved()`'s refetch, which lags
      // this by a network round trip.
      const savedValues: ArchitectureFormValues = {
        title,
        description,
        elementType,
        parentId,
        asilLevel,
        makeOrBuy,
        changeReason: '',
        customFields,
      };
      markClean(savedValues);
      onSaved();
    } catch (err: unknown) {
      setSaveError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }, [
    element.id,
    element.version,
    title,
    description,
    elementType,
    parentId,
    asilLevel,
    makeOrBuy,
    changeReason,
    customFields,
    isExtendedPreset,
    markClean,
    onSaved,
  ]);

  const handleConfirmDelete = useCallback(async (): Promise<void> => {
    setShowDeleteDialog(false);
    onDelete(element.id);
  }, [element.id, onDelete]);

  return (
    <div>
      {showDeleteDialog && (
        <ConfirmDialog
          title={t('arch.deleteTitle')}
          message={t('actions.deleteConfirmPromptNamed', { name: title })}
          confirmLabel={t('actions.delete')}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setShowDeleteDialog(false)}
          testId="arch-form-delete-dialog"
          confirmTestId="confirm-delete-btn"
          cancelTestId="arch-cancel-delete-btn"
        />
      )}

      {/* Primary actions live at the top for consistency across all artifact
          forms (P1-f). */}
      <div className={styles.actions}>
        <button
          data-testid="arch-save-btn"
          className="btn-primary"
          onClick={() => void handleSave()}
          disabled={isSaving}
        >
          {isSaving ? t('actions.saving') : t('actions.save')}
        </button>
        <button
          data-testid="arch-delete-btn"
          className="btn-danger"
          onClick={() => setShowDeleteDialog(true)}
        >
          {t('actions.delete')}
        </button>
        <button
          data-testid="arch-view-diff-btn"
          className={showDiff ? 'btn-primary' : 'btn-secondary'}
          onClick={() => setShowDiff(!showDiff)}
        >
          {showDiff ? t('editor.hideDiff') : t('editor.viewDiff')}
        </button>
        {onDecompose && (
          <button
            data-testid="arch-decompose-btn"
            className="btn-secondary"
            onClick={onDecompose}
          >
            {t('archDecompose.trigger')}
          </button>
        )}
      </div>

      {/* Identity block — UI concept ch. 12.4: id, level, version in one
          row, always in the same order and the same representation as in the
          list and in the trace spine. Replaces the UID/Version/Level grid
          whose UID cell re-implemented the mono style inline. */}
      <div className={styles.identityBlock}>
        <div className={styles.identityRow}>
          <ArtifactId
            testId="arch-artifact-id"
            value={element.uid}
            fallback={element.id.slice(0, 8)}
            copyValue={element.uid || element.id}
          />
          <LevelBadge
            level={element.level ?? 0}
            title={t('arch.level')}
            testId="arch-level-badge"
          />
          <VersionBadge version={element.version || 1} />
        </div>

        <div className={styles.metaGrid}>
          {/* SysEng 2.0 §1.2: structural role is derived from tree position by
              the backend and shown read-only here — it is NOT the free-text
              element_type field below and cannot be edited directly. Reparenting
              an element (drag & drop in the tree) changes this value
              automatically. */}
          <div className={styles.metaField}>
            <label className={styles.label}>{t('arch.role')}</label>
            <div
              data-testid="arch-role-display"
              className={styles.readOnlyValue}
              title={t('arch.roleHint')}
            >
              {element.role ? t(`arch.roleValue.${element.role}`) : '—'}
            </div>
          </div>
        </div>

        {/* REQ-171: WorkflowEngine-driven status editor. ArchitectureElement has
            no denormalized status field, so the current state is loaded from the
            transitions endpoint; "draft" (the workflow initial_state) is only the
            pre-load fallback label. */}
        <div>
          <label className={styles.label}>{t('editor.status')}</label>
          <WorkflowStatusEditor
            artifactType="architecture"
            artifactId={element.id}
            currentStatus="draft"
            disabled={isSaving}
            onTransitionComplete={onSaved}
          />
        </div>
      </div>

      {/* Title field */}
      <label htmlFor="arch-title" className={styles.label}>
        {t('editor.title')}
      </label>
      {/* Issue #669: the former inline `onFocus`/`onBlur` border-color
          assignments are now `.input:focus` in the CSS module. */}
      <input
        id="arch-title"
        data-testid="arch-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className={`${styles.input} ${styles.titleInput}`}
      />

      {/* Element type — free text with autocomplete (REQ-006 / D5: types can be
          changed and extended freely, no longer a fixed choice list) */}
      <label htmlFor="arch-type" className={styles.label}>
        {t('arch.elementType')}
      </label>
      <div className={styles.typeAutocomplete}>
        <input
          id="arch-type"
          type="text"
          data-testid="arch-element-type-select"
          value={elementType}
          onChange={(e) => handleElementTypeChange(e.target.value)}
          onFocus={() => {
            const filtered = elementType
              ? allElementTypes.filter((ty) => ty.toLowerCase().includes(elementType.toLowerCase()))
              : allElementTypes;
            setTypeSuggestions(filtered);
            setTypeDropdownOpen(filtered.length > 0);
          }}
          onBlur={() => {
            // Delay closing to allow a click on a suggestion to register first.
            setTimeout(() => setTypeDropdownOpen(false), 150);
          }}
          placeholder={t('arch.elementTypePlaceholder', 'z.B. System, Subsystem, Component, Interface...')}
          className={`${styles.input} ${styles.typeInput}`}
        />
        {typeDropdownOpen && typeSuggestions.length > 0 && (
          <div data-testid="arch-element-type-dropdown" className={styles.suggestionList}>
            {typeSuggestions.map((suggestion) => (
              // Issue #669: the former inline `onMouseEnter`/`onMouseLeave`
              // background assignments are now `.suggestion:hover`.
              <div
                key={suggestion}
                data-testid={`arch-element-type-suggestion-${suggestion}`}
                onClick={() => handleTypeSuggestionClick(suggestion)}
                className={styles.suggestion}
              >
                {suggestion}
              </div>
            ))}
          </div>
        )}
      </div>
      {/*
       * Issue 422: element_type is a free-text field maintained by hand and
       * independent of the derived `role` shown above (SysEng 2.0 §1.2) —
       * without this hint the two can look like a contradiction (e.g. role
       * "System" next to element_type "component").
       */}
      <p data-testid="arch-element-type-hint" className={fieldHints.hint}>
        {t('archLegend.elementTypeMeaning')}
      </p>

      {/* Parent element picker */}
      <label htmlFor="arch-parent" className={styles.label}>
        {t('arch.parentElement', 'Parent Element')}
      </label>
      <select
        id="arch-parent"
        data-testid="arch-parent-select"
        value={parentId}
        onChange={(e) => setParentId(e.target.value)}
        className={`${styles.input} ${styles.select}`}
      >
        <option value="">{t('arch.noParent', 'No parent (Root / L0)')}</option>
        {parentOptions.map((el) => (
          <option key={el.id} value={el.id}>
            {el.title || t('editor.untitled')} (L{el.level ?? 0})
          </option>
        ))}
      </select>

      {/* ASIL Level Dropdown — dynamic visibility */}
      {visibleFields['asil_level'] && (
        <>
          <label htmlFor="arch-asil" className={styles.label}>
            ASIL Level (Functional Safety)
          </label>
          <select
            id="arch-asil"
            data-testid="arch-asil-select"
            value={asilLevel ?? ''}
            onChange={(e) => setAsilLevel((e.target.value as ASILLevel) || null)}
            className={`${styles.input} ${styles.select}`}
          >
            <option value="">— Not set —</option>
            {ASIL_LEVEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </>
      )}

      {/* Make-or-Buy Dropdown — dynamic visibility */}
      {visibleFields['make_or_buy'] && (
        <>
          <label htmlFor="arch-mob" className={styles.label}>
            Make-or-Buy Decision
          </label>
          <select
            id="arch-mob"
            data-testid="arch-make-or-buy-select"
            value={makeOrBuy ?? ''}
            onChange={(e) => setMakeOrBuy((e.target.value as MakeOrBuyDecision) || null)}
            className={`${styles.input} ${styles.select}`}
          >
            <option value="">— Not set —</option>
            {MAKE_OR_BUY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </>
      )}

      {/* Markdown description */}
      <label className={styles.label}>
        {t('editor.description')}
      </label>
      <MarkdownPreview
        value={description}
        onChange={setDescription}
      />

      {/* Custom Fields (REQ-L2-AS-037) */}
      <div className={styles.customFieldsSection}>
        <label className={styles.label}>{t('customFields.section')}</label>
        {/* Issue #673: `key` makes the row-list reset self-contained even if
            this form is ever mounted without the parent's own
            `key={element.id}` (see the identical note in
            RequirementForm.tsx) — CustomFieldsEditor seeds its rows from
            `value` once on mount and never resyncs them on a prop update. */}
        <CustomFieldsEditor
          key={element.id}
          value={element.custom_fields}
          onChange={setCustomFields}
          disabled={isSaving}
        />
      </div>

      {/* Workspace-defined attributes (REQ-016, UI concept ch. 12.11).
          CustomFieldsEditor above edits the free-form JSON blob on the
          element; this block renders the typed CustomFieldDefinitions of the
          workspace, which the data model has supported all along but only
          the Requirements editor ever displayed. Renders nothing when the
          workspace defines no fields. */}
      {element.artifact_id && <ArtifactCustomFields artifactId={element.artifact_id} />}

      {/*
       * Change reason — extended preset only. Issue 417: the server enforces
       * change_reason on every update in the extended preset identically for
       * all artifact types (PresetPolicyService.is_change_reason_required),
       * so the required marker must match Requirement/StakeholderNeed.
       */}
      {isExtendedPreset && (
        <>
          <label htmlFor="arch-change-reason" className={styles.label}>
            {t('req.changeReason')} <span className={fieldHints.requiredMarker}>*</span>
          </label>
          <input
            id="arch-change-reason"
            data-testid="arch-change-reason-input"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            placeholder={t('req.changeReasonPlaceholderArchitecture')}
            className={styles.input}
          />
        </>
      )}

      {/* Error alert */}
      {saveError && (
        <p role="alert" className={styles.saveError}>
          {saveError}
        </p>
      )}

      {/* Artifact Diff View */}
      {showDiff && (
        <ArtifactDiff
          entityId={element.id}
          entityType="architecture"
          currentVersion={element.version}
          diffFetcher={architectureApi.diff}
          versionsFetcher={architectureApi.versions}
          onClose={() => setShowDiff(false)}
        />
      )}
    </div>
  );
}

export default ArchitectureForm;
