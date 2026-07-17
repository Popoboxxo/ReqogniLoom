import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useWorkspace } from '../../context/WorkspaceContext';
import type { Adr } from '../../types';
import { adrsApi } from '../../api/adrs';
import { VersionBadge } from '../shared/VersionBadge';
import { getStatusBadgeStyle } from '../../utils/statusBadge';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';

interface AdrFormProps {
  adr: Adr | null;
  onSaved: () => void;
  onDeleted: () => void;
}

export function AdrForm({ adr, onSaved, onDeleted }: AdrFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  // REQ-162: Extended preset captures a change_reason on every update
  // (forwarded to the backend audit log).
  const isExtendedPreset = activeWorkspace?.preset === 'extended';
  const [formData, setFormData] = useState<Partial<Adr>>({});
  const [changeReason, setChangeReason] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (adr) setFormData({ ...adr });
    else setFormData({});
    // Reset transient action state when switching to a different ADR.
    setChangeReason('');
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
  }, [adr]);

  const handleChange = (field: keyof Adr, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (saveError) setSaveError(null);
    if (deleteError) setDeleteError(null);
  };

  const handleSave = async () => {
    if (!adr) return;
    // REQ-162: Extended preset requires a change_reason before saving.
    if (isExtendedPreset && !changeReason.trim()) {
      setSaveError(t('req.changeReasonRequired'));
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    try {
      await adrsApi.update(adr.id, {
        title: formData.title,
        description: formData.description,
        context: formData.context,
        consequences: formData.consequences,
        status: formData.status,
        ...(isExtendedPreset ? { change_reason: changeReason.trim() } : {}),
      });
      onSaved();
    } catch (err) {
      console.error(err);
      const msg = (err as { error?: { message?: string } })?.error?.message ?? t('adrs.saveFailed');
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!adr) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await adrsApi.delete(adr.id);
      onDeleted();
    } catch (err) {
      console.error(err);
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        t('adrs.deleteFailed', 'Löschen fehlgeschlagen. Bitte erneut versuchen.');
      setDeleteError(msg);
      setConfirmDelete(false);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!adr) {
    return (
      <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-lg)', textAlign: 'center', padding: 'var(--space-8)' }}>
        {t('adrs.selectAdr')}
      </p>
    );
  }

  const inputStyle: React.CSSProperties = {
    width: '100%', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
    padding: 'var(--space-3)', fontFamily: 'var(--font-sans)', fontSize: 'var(--font-size-base)',
    marginBottom: 'var(--space-4)', color: 'var(--color-text)', background: 'var(--color-surface)',
    boxSizing: 'border-box',
  };
  const labelStyle: React.CSSProperties = {
    fontWeight: 500, color: 'var(--color-text)', display: 'block', marginBottom: 'var(--space-1)',
  };

  return (
    <div style={{
      background: 'var(--color-surface)', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-card)',
      padding: 'var(--space-6)', flex: 1, display: 'flex', gap: 'var(--space-6)', alignItems: 'flex-start',
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-6)' }}>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            <span style={getStatusBadgeStyle(adr.status)}>
              {adr.status}
            </span>
            {adr.version && <VersionBadge version={adr.version} />}
            {adr.uid ? (
              <span
                style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--color-text-muted)', userSelect: 'all' }}
                title="Unique Identifier"
              >
                {adr.uid}
              </span>
            ) : (
              <span
                style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--color-text-muted)', userSelect: 'all', opacity: 0.6 }}
                title="Short ID (UUID prefix, no semantic uid assigned yet)"
              >
                {adr.id.slice(0, 8)}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            {!confirmDelete ? (
              <button data-testid="adr-delete-btn" onClick={() => setConfirmDelete(true)} className="btn-danger">
                {t('actions.delete')}
              </button>
            ) : (
              <>
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                  {t('actions.deleteConfirmPrompt', 'Löschen?')}
                </span>
                <button data-testid="adr-confirm-delete-btn" onClick={handleDelete} className="btn-danger" disabled={isDeleting}>
                  {isDeleting ? t('actions.deleting', 'Löschen...') : t('actions.confirmDelete', 'Ja, löschen')}
                </button>
                <button data-testid="adr-cancel-delete-btn" onClick={() => setConfirmDelete(false)} className="btn-ghost" disabled={isDeleting}>
                  {t('actions.cancel')}
                </button>
              </>
            )}
            <button onClick={handleSave} className="btn-primary" disabled={isSaving}>
              {isSaving ? t('actions.saving') : t('actions.save')}
            </button>
          </div>
        </div>
        {saveError && (
          <p role="alert" style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', marginBottom: 'var(--space-4)' }}>
            {saveError}
          </p>
        )}
        {deleteError && (
          <p role="alert" style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', marginBottom: 'var(--space-4)' }}>
            {deleteError}
          </p>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <div>
            <label style={labelStyle}>{t('editor.title')} <span style={{ color: 'var(--color-danger)' }}>*</span></label>
            <input type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} style={inputStyle} aria-required="true" placeholder={t('adrs.titlePlaceholder', 'Titel der Architekturentscheidung')} />
          </div>
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <label style={labelStyle}>{t('editor.description')}</label>
            <MarkdownPreview value={formData.description || ''} onChange={(v) => handleChange('description', v)} />
          </div>
          <div>
            <label style={labelStyle}>{t('adrs.context')}</label>
            <MarkdownPreview value={formData.context || ''} onChange={(v) => handleChange('context', v)} />
          </div>
          <div>
            <label style={labelStyle}>{t('adrs.consequences')}</label>
            <MarkdownPreview value={formData.consequences || ''} onChange={(v) => handleChange('consequences', v)} />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('editor.status')}</label>
              {/* REQ-165: WorkflowEngine-driven status editor (replaces the
                  hardcoded STATUS_OPTIONS select). */}
              <WorkflowStatusEditor
                artifactType="adr"
                artifactId={adr.id}
                currentStatus={adr.status}
                disabled={isSaving}
                onTransitionComplete={onSaved}
              />
            </div>
          </div>

          {/* REQ-162: Change Control — Extended preset only. */}
          {isExtendedPreset && (
            <div>
              <label htmlFor="adr-change-reason" style={labelStyle}>
                {t('req.changeReason')} <span style={{ color: 'var(--color-danger)' }}>*</span>
              </label>
              <textarea
                id="adr-change-reason"
                data-testid="adr-change-reason-input"
                value={changeReason}
                onChange={(e) => {
                  setChangeReason(e.target.value);
                  if (saveError) setSaveError(null);
                }}
                rows={2}
                style={{ ...inputStyle, resize: 'vertical' }}
                placeholder={t('req.changeReasonPlaceholder')}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
