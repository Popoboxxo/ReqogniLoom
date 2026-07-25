import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { Issue } from '../../types';
import { issuesApi } from '../../api/issues';
import { VersionBadge } from '../shared/VersionBadge';
import { TagInput } from '../shared/tag-input';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';
import { useWorkspace } from '../../context/WorkspaceContext';

interface IssueFormProps {
  issue: Issue | null;
  onSaved: () => void;
  onDeleted: () => void;
}

const SEVERITY_OPTIONS = ['low', 'medium', 'high', 'critical'];
const CATEGORY_OPTIONS = ['defect', 'improvement', 'documentation', 'question'];

export function IssueForm({ issue, onSaved, onDeleted }: IssueFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  // REQ-162: Extended preset captures a change_reason on every update
  // (forwarded to the backend audit log).
  const isExtendedPreset = activeWorkspace?.preset === 'extended';
  const [formData, setFormData] = useState<Partial<Issue>>({});
  const [changeReason, setChangeReason] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (issue) setFormData({ ...issue });
    else setFormData({});
    // Reset transient action state when switching to a different issue.
    setChangeReason('');
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
  }, [issue]);

  const handleChange = <K extends keyof Issue>(field: K, value: Issue[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (saveError) setSaveError(null);
    if (deleteError) setDeleteError(null);
  };

  const handleSave = async () => {
    if (!issue) return;
    // REQ-162: Extended preset requires a change_reason before saving.
    if (isExtendedPreset && !changeReason.trim()) {
      setSaveError(t('req.changeReasonRequired'));
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    try {
      await issuesApi.update(issue.id, {
        title: formData.title,
        description: formData.description,
        severity: formData.severity,
        category: formData.category,
        status: formData.status,
        tags: formData.tags,
        ...(isExtendedPreset ? { change_reason: changeReason.trim() } : {}),
      });
      onSaved();
    } catch (err) {
      console.error(err);
      const msg = (err as { error?: { message?: string } })?.error?.message ?? t('issues.saveFailed');
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!issue) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await issuesApi.delete(issue.id);
      onDeleted();
    } catch (err) {
      console.error(err);
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        t('issues.deleteFailed', 'Löschen fehlgeschlagen. Bitte erneut versuchen.');
      setDeleteError(msg);
      setConfirmDelete(false);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!issue) {
    return (
      <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-lg)', textAlign: 'center', padding: 'var(--space-8)' }}>
        {t('issues.selectIssue')}
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
            <span style={{ fontSize: '0.8rem', padding: '4px 8px', borderRadius: '99px', background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}>
              {issue.status}
            </span>
            {issue.version && <VersionBadge version={issue.version} />}
            {issue.uid ? (
              <span
                style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--color-text-muted)', userSelect: 'all' }}
                title="Unique Identifier"
              >
                {issue.uid}
              </span>
            ) : (
              <span
                style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: 'var(--color-text-muted)', userSelect: 'all', opacity: 0.6 }}
                title="Short ID (UUID prefix, no semantic uid assigned yet)"
              >
                {issue.id.slice(0, 8)}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            {!confirmDelete ? (
              <button data-testid="issue-delete-btn" onClick={() => setConfirmDelete(true)} className="btn-danger">
                {t('actions.delete')}
              </button>
            ) : (
              <>
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                  {t('actions.deleteConfirmPrompt', 'Löschen?')}
                </span>
                <button data-testid="issue-confirm-delete-btn" onClick={handleDelete} className="btn-danger" disabled={isDeleting}>
                  {isDeleting ? t('actions.deleting', 'Löschen...') : t('actions.confirmDelete', 'Ja, löschen')}
                </button>
                <button data-testid="issue-cancel-delete-btn" onClick={() => setConfirmDelete(false)} className="btn-ghost" disabled={isDeleting}>
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
            <label htmlFor="issue-title" style={labelStyle}>{t('editor.title')} <span style={{ color: 'var(--color-danger)' }}>*</span></label>
            <input id="issue-title" type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} style={inputStyle} aria-required="true" />
          </div>
          <div>
            <label htmlFor="issue-description" style={labelStyle}>{t('editor.description')}</label>
            <textarea id="issue-description" value={formData.description || ''} onChange={(e) => handleChange('description', e.target.value)} rows={4} style={inputStyle} />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label htmlFor="issue-severity" style={labelStyle}>{t('issues.severity')}</label>
              <select id="issue-severity" value={formData.severity || 'medium'} onChange={(e) => handleChange('severity', e.target.value)} style={inputStyle}>
                {SEVERITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('editor.status')}</label>
              {/* REQ-165: WorkflowEngine-driven status editor (replaces the
                  hardcoded status select). */}
              <WorkflowStatusEditor
                artifactType="issue"
                artifactId={issue.id}
                currentStatus={issue.status}
                disabled={isSaving}
                onTransitionComplete={onSaved}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="issue-category" style={labelStyle}>{t('issues.category')}</label>
              <select id="issue-category" value={formData.category || 'defect'} onChange={(e) => handleChange('category', e.target.value)} style={inputStyle}>
                {CATEGORY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label style={labelStyle}>{t('issues.tags')}</label>
            <TagInput
              data-testid="issue-tags-input"
              tags={formData.tags ?? []}
              onChange={(tags) => handleChange('tags', tags)}
              placeholder={t('issues.tagsPlaceholder', 'tag1, tag2 ...')}
            />
          </div>

          {/* REQ-162: Change Control — Extended preset only. */}
          {isExtendedPreset && (
            <div>
              <label htmlFor="issue-change-reason" style={labelStyle}>
                {t('req.changeReason')} <span style={{ color: 'var(--color-danger)' }}>*</span>
              </label>
              <textarea
                id="issue-change-reason"
                data-testid="issue-change-reason-input"
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
