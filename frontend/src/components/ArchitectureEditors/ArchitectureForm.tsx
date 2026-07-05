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
import { useWorkspace } from '../../context/WorkspaceContext';
import { useEntityType } from '../../context/EntityTypeContext';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';
import { ArtifactDiff } from '../ArtifactDiff/ArtifactDiff';
import { VersionBadge } from '../shared/VersionBadge';
import { architectureApi } from '../../api/architecture';
import { extractErrorMessage } from '../../api/client';
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
}

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
  const dangerButtonStyle: React.CSSProperties = {
    background: 'var(--color-danger)',
    color: '#ffffff',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--space-2) var(--space-4)',
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    cursor: 'pointer',
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 1000,
      }}
    >
      <div
        style={{
          background: 'var(--color-surface)',
          padding: 'var(--space-6)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-md)',
          maxWidth: '400px',
          textAlign: 'center',
          fontFamily: 'var(--font-sans)',
          color: 'var(--color-text)',
        }}
      >
        <h3 style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-size-lg)' }}>
          {t('arch.deleteTitle')}
        </h3>
        <p style={{ margin: 0, marginBottom: 'var(--space-4)', color: 'var(--color-text-muted)' }}>
          {t('arch.deleteConfirm')}: <strong style={{ color: 'var(--color-text)' }}>{elementName}</strong>?
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'center', marginTop: 'var(--space-4)' }}>
          <button data-testid="confirm-delete-btn" onClick={onConfirm} style={dangerButtonStyle}>
            {t('actions.delete')}
          </button>
          <button
            onClick={onCancel}
            style={{
              background: 'var(--color-surface-raised)',
              color: 'var(--color-text)',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-2) var(--space-4)',
              fontSize: 'var(--font-size-sm)',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            {t('actions.cancel')}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Read-only field component.
 */
interface ReadOnlyFieldProps {
  label: string;
  value: string | number | null | undefined;
}

function ReadOnlyField({ label, value }: ReadOnlyFieldProps): JSX.Element {
  return (
    <div style={{ marginBottom: 'var(--space-4)' }}>
      <label style={labelStyle}>{label}</label>
      <div
        style={{
          ...readOnlyStyle,
          marginBottom: 0,
          padding: 'var(--space-2) var(--space-3)',
          color: 'var(--color-text-muted)',
          fontSize: 'var(--font-size-sm)',
          fontFamily: 'monospace',
        }}
      >
        {value || '—'}
      </div>
    </div>
  );
}

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
}: ArchitectureFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const { visibleFields } = useEntityType();

  // Form state
  const [title, setTitle] = useState(element.title);
  const [description, setDescription] = useState(element.description);
  const [elementType, setElementType] = useState(element.element_type);
  const [parentId, setParentId] = useState<string>(element.parent_id ?? '');
  const [asilLevel, setAsilLevel] = useState<ASILLevel>(element.asil_level ?? null);
  const [makeOrBuy, setMakeOrBuy] = useState<MakeOrBuyDecision>(element.make_or_buy ?? null);
  const [changeReason, setChangeReason] = useState(element.change_reason ?? '');

  // UI state
  const [isSaving, setIsSaving] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  // Sync form state when element changes
  useEffect(() => {
    setTitle(element.title);
    setDescription(element.description);
    setElementType(element.element_type);
    setParentId(element.parent_id ?? '');
    setAsilLevel(element.asil_level ?? null);
    setMakeOrBuy(element.make_or_buy ?? null);
    setChangeReason(element.change_reason ?? '');
  }, [element.id]);

  // Client-side cycle guard
  const invalidParentIds = useMemo((): Set<string> => {
    const childrenByParent = new Map<string, string[]>();
    for (const el of elements) {
      if (!el.parent_id) continue;
      const bucket = childrenByParent.get(el.parent_id);
      if (bucket) bucket.push(el.id);
      else childrenByParent.set(el.parent_id, [el.id]);
    }
    const invalid = new Set<string>([element.id]);
    const stack: string[] = [element.id];
    while (stack.length > 0) {
      const current = stack.pop();
      if (!current) break;
      for (const childId of childrenByParent.get(current) ?? []) {
        if (!invalid.has(childId)) {
          invalid.add(childId);
          stack.push(childId);
        }
      }
    }
    return invalid;
  }, [elements, element.id]);

  const parentOptions = useMemo(
    () => elements.filter((el) => !invalidParentIds.has(el.id)),
    [elements, invalidParentIds]
  );

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
    isExtendedPreset,
    onSaved,
  ]);

  const handleConfirmDelete = useCallback(async (): Promise<void> => {
    setShowDeleteDialog(false);
    onDelete(element.id);
  }, [element.id, onDelete]);

  const primaryButtonStyle: React.CSSProperties = {
    background: 'var(--color-primary)',
    color: '#ffffff',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--space-2) var(--space-4)',
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    cursor: 'pointer',
  };

  const dangerButtonStyle: React.CSSProperties = {
    background: 'var(--color-danger)',
    color: '#ffffff',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--space-2) var(--space-4)',
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    cursor: 'pointer',
  };

  return (
    <div>
      {showDeleteDialog && (
        <DeleteConfirmationDialog
          elementName={title}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setShowDeleteDialog(false)}
        />
      )}

      {/* Header with UID and Version (read-only) */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        <h2
          style={{
            margin: 0,
            marginBottom: 'var(--space-4)',
            fontSize: 'var(--font-size-2xl)',
            fontWeight: 700,
            color: 'var(--color-text)',
          }}
        >
          {title || t('editor.untitled')}
        </h2>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 'var(--space-4)',
            marginBottom: 'var(--space-4)',
          }}
        >
          {element.uid && <ReadOnlyField label="UID" value={element.uid} />}
          <div>
            <label style={labelStyle}>Version</label>
            <VersionBadge version={element.version || 1} />
          </div>
          <ReadOnlyField label="Hierarchy Level" value={element.level ?? 0} />
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

      {/* Element type dropdown */}
      <label htmlFor="arch-type" style={labelStyle}>
        {t('arch.elementType')}
      </label>
      <select
        id="arch-type"
        data-testid="arch-element-type-select"
        value={elementType}
        onChange={(e) => setElementType(e.target.value as ElementType)}
        style={{ ...inputStyle, width: 'auto', minWidth: '200px' }}
      >
        <option value="component">{t('arch.elementType.component')}</option>
        <option value="interface">{t('arch.elementType.interface')}</option>
        <option value="subsystem">{t('arch.elementType.subsystem')}</option>
        <option value="layer">{t('arch.elementType.layer')}</option>
        <option value="module">{t('arch.elementType.module')}</option>
      </select>

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

      {/* Change reason — extended preset only */}
      {isExtendedPreset && (
        <>
          <label htmlFor="arch-change-reason" style={labelStyle}>
            {t('req.changeReason')}
          </label>
          <input
            id="arch-change-reason"
            data-testid="arch-change-reason-input"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            placeholder={t('req.changeReasonPlaceholder')}
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

      {/* Action buttons */}
      <div
        style={{
          display: 'flex',
          gap: 'var(--space-3)',
          marginTop: 'var(--space-4)',
        }}
      >
        <button
          data-testid="arch-save-btn"
          onClick={() => void handleSave()}
          disabled={isSaving}
          style={{
            ...primaryButtonStyle,
            opacity: isSaving ? 0.6 : 1,
            cursor: isSaving ? 'not-allowed' : 'pointer',
          }}
        >
          {isSaving ? t('actions.saving') : t('actions.save')}
        </button>
        <button
          data-testid="arch-delete-btn"
          onClick={() => setShowDeleteDialog(true)}
          style={dangerButtonStyle}
        >
          {t('actions.delete')}
        </button>
        <button
          data-testid="arch-view-diff-btn"
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
          {showDiff ? 'Hide Diff' : 'View Diff'}
        </button>
      </div>

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
