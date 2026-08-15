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
import { Dialog } from '../shared/Dialog';
import fieldHints from '../shared/FieldHints.module.css';
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
}

/**
 * Fallback element-type suggestions shown when the workspace does not yet
 * contain any ArchitectureElement (REQ-006 / D5). Mirrors the values of the
 * former fixed choice list so existing muscle memory keeps working, while
 * the field itself is now free text.
 */
const DEFAULT_ELEMENT_TYPE_SUGGESTIONS = ['System', 'Subsystem', 'Component', 'Interface', 'Function'];

/**
 * Shared style tokens.
 */
const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: 'block',
  marginBottom: 'var(--space-2)',
  color: 'var(--color-text)',
  fontSize: 'var(--font-size-sm)',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  fontSize: 'var(--font-size-base)',
  padding: 'var(--space-2) var(--space-3)',
  marginBottom: 'var(--space-4)',
  boxSizing: 'border-box',
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-text)',
  fontFamily: 'var(--font-sans)',
  transition: 'var(--transition-fast)',
  outline: 'none',
};

const readOnlyStyle: React.CSSProperties = {
  ...inputStyle,
  background: 'var(--color-surface-raised)',
  cursor: 'not-allowed',
};

/**
 * Delete Confirmation Dialog.
 */
interface DeleteConfirmationDialogProps {
  elementName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

function DeleteConfirmationDialog({
  elementName,
  onConfirm,
  onCancel,
}: DeleteConfirmationDialogProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <Dialog
      title={t('arch.deleteTitle')}
      onClose={onCancel}
      size="sm"
      testId="arch-form-delete-dialog"
      footer={
        <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'flex-end' }}>
          <button className="btn-secondary" onClick={onCancel}>
            {t('actions.cancel')}
          </button>
          <button data-testid="confirm-delete-btn" className="btn-danger" onClick={onConfirm}>
            {t('actions.delete')}
          </button>
        </div>
      }
    >
      <p style={{ margin: 0, color: 'var(--color-text-muted)' }}>
        {t('arch.deleteConfirm')}: <strong style={{ color: 'var(--color-text)' }}>{elementName}</strong>?
      </p>
    </Dialog>
  );
}

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
export function ArchitectureForm({
  element,
  elements,
  onSaved,
  onDelete,
  isExtendedPreset,
  onDecompose,
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

  // Sync form state when element changes
  useEffect(() => {
    setTitle(element.title);
    setDescription(element.description);
    setElementType(element.element_type);
    setParentId(element.parent_id ?? '');
    setAsilLevel(element.asil_level ?? null);
    setMakeOrBuy(element.make_or_buy ?? null);
    setChangeReason(element.change_reason ?? '');
    setCustomFields(element.custom_fields ?? {});
  }, [element.id]);

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
      const payload: Partial<ArchitectureElement> & { change_reason?: string } = {
        title,
        description,
        element_type: elementType,
        parent_id: parentId === '' ? null : parentId,
        asil_level: asilLevel,
        make_or_buy: makeOrBuy,
        // REQ-L2-AS-037: always send custom_fields (backend validates the map).
        custom_fields: customFields,
      };
      if (isExtendedPreset && changeReason.trim()) {
        payload.change_reason = changeReason.trim();
      }
      await architectureApi.update(element.id, payload);
      setChangeReason('');
      onSaved();
    } catch (err: unknown) {
      setSaveError(extractErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }, [
    element.id,
    title,
    description,
    elementType,
    parentId,
    asilLevel,
    makeOrBuy,
    changeReason,
    customFields,
    isExtendedPreset,
    onSaved,
  ]);

  const handleConfirmDelete = useCallback(async (): Promise<void> => {
    setShowDeleteDialog(false);
    onDelete(element.id);
  }, [element.id, onDelete]);

  return (
    <div>
      {showDeleteDialog && (
        <DeleteConfirmationDialog
          elementName={title}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setShowDeleteDialog(false)}
        />
      )}

      {/* Primary actions live at the top for consistency across all artifact
          forms (P1-f). */}
      <div
        style={{
          display: 'flex',
          gap: 'var(--space-3)',
          marginBottom: 'var(--space-4)',
        }}
      >
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
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-4)',
          }}
        >
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

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 'var(--space-4)',
            marginBottom: 'var(--space-4)',
          }}
        >
          {/* SysEng 2.0 §1.2: structural role is derived from tree position by
              the backend and shown read-only here — it is NOT the free-text
              element_type field below and cannot be edited directly. Reparenting
              an element (drag & drop in the tree) changes this value
              automatically. */}
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <label style={labelStyle}>{t('arch.role')}</label>
            <div
              data-testid="arch-role-display"
              style={{
                ...readOnlyStyle,
                marginBottom: 0,
                padding: 'var(--space-2) var(--space-3)',
                color: 'var(--color-text)',
                fontSize: 'var(--font-size-sm)',
                fontWeight: 600,
              }}
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
          <label style={labelStyle}>{t('editor.status')}</label>
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
      <label htmlFor="arch-title" style={labelStyle}>
        {t('editor.title')}
      </label>
      <input
        id="arch-title"
        data-testid="arch-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        style={{ ...inputStyle, fontSize: 'var(--font-size-lg)', fontWeight: 600 }}
        onFocus={(e) => {
          (e.currentTarget as HTMLInputElement).style.borderColor = 'var(--color-primary)';
        }}
        onBlur={(e) => {
          (e.currentTarget as HTMLInputElement).style.borderColor = 'var(--color-border)';
        }}
      />

      {/* Element type — free text with autocomplete (REQ-006 / D5: types can be
          changed and extended freely, no longer a fixed choice list) */}
      <label htmlFor="arch-type" style={labelStyle}>
        {t('arch.elementType')}
      </label>
      <div style={{ position: 'relative', width: 'auto', minWidth: '200px', marginBottom: 'var(--space-4)' }}>
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
          style={{ ...inputStyle, marginBottom: 0 }}
        />
        {typeDropdownOpen && typeSuggestions.length > 0 && (
          <div
            data-testid="arch-element-type-dropdown"
            style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              zIndex: 100,
              background: 'var(--color-surface-raised)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              maxHeight: '200px',
              overflowY: 'auto',
              marginTop: '4px',
            }}
          >
            {typeSuggestions.map((suggestion) => (
              <div
                key={suggestion}
                data-testid={`arch-element-type-suggestion-${suggestion}`}
                onClick={() => handleTypeSuggestionClick(suggestion)}
                style={{
                  padding: 'var(--space-2) var(--space-3)',
                  cursor: 'pointer',
                  color: 'var(--color-text)',
                  fontSize: 'var(--font-size-base)',
                  borderBottom: '1px solid var(--color-border-subtle)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--color-card-active-bg)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                }}
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
      <label htmlFor="arch-parent" style={labelStyle}>
        {t('arch.parentElement', 'Parent Element')}
      </label>
      <select
        id="arch-parent"
        data-testid="arch-parent-select"
        value={parentId}
        onChange={(e) => setParentId(e.target.value)}
        style={{ ...inputStyle, width: 'auto', minWidth: '200px' }}
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
          <label htmlFor="arch-asil" style={labelStyle}>
            ASIL Level (Functional Safety)
          </label>
          <select
            id="arch-asil"
            data-testid="arch-asil-select"
            value={asilLevel ?? ''}
            onChange={(e) => setAsilLevel((e.target.value as ASILLevel) || null)}
            style={{ ...inputStyle, width: 'auto', minWidth: '200px' }}
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
          <label htmlFor="arch-mob" style={labelStyle}>
            Make-or-Buy Decision
          </label>
          <select
            id="arch-mob"
            data-testid="arch-make-or-buy-select"
            value={makeOrBuy ?? ''}
            onChange={(e) => setMakeOrBuy((e.target.value as MakeOrBuyDecision) || null)}
            style={{ ...inputStyle, width: 'auto', minWidth: '200px' }}
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
      <label style={labelStyle}>
        {t('editor.description')}
      </label>
      <MarkdownPreview
        value={description}
        onChange={setDescription}
      />

      {/* Custom Fields (REQ-L2-AS-037) */}
      <div style={{ marginTop: 'var(--space-5)', marginBottom: 'var(--space-3)' }}>
        <label style={labelStyle}>{t('customFields.section')}</label>
        <CustomFieldsEditor
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
          <label htmlFor="arch-change-reason" style={labelStyle}>
            {t('req.changeReason')} <span className={fieldHints.requiredMarker}>*</span>
          </label>
          <input
            id="arch-change-reason"
            data-testid="arch-change-reason-input"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            placeholder={t('req.changeReasonPlaceholderArchitecture')}
            style={inputStyle}
          />
        </>
      )}

      {/* Error alert */}
      {saveError && (
        <p
          role="alert"
          style={{
            color: 'var(--color-danger)',
            marginTop: 'var(--space-3)',
            fontSize: 'var(--font-size-sm)',
          }}
        >
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
