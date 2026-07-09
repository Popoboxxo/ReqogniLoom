import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { Issue } from '../../types';
import { issuesApi } from '../../api/issues';

interface IssueFormProps {
  issue: Issue | null;
  onSaved: () => void;
  onDeleted: () => void;
}

const SEVERITY_OPTIONS = ['low', 'medium', 'high', 'critical'];
const STATUS_OPTIONS = ['Open', 'In Progress', 'Resolved', 'Closed', 'Wontfix'];
const CATEGORY_OPTIONS = ['defect', 'improvement', 'documentation', 'question'];

export function IssueForm({ issue, onSaved, onDeleted }: IssueFormProps): JSX.Element {
  const { t } = useTranslation();
  const [formData, setFormData] = useState<Partial<Issue>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (issue) setFormData({ ...issue });
    else setFormData({});
    // Reset transient action state when switching to a different issue.
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
  }, [issue]);

  const handleChange = (field: keyof Issue, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (saveError) setSaveError(null);
    if (deleteError) setDeleteError(null);
  };

  const handleSave = async () => {
    if (!issue) return;
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
          <div>
            <span style={{ fontSize: '0.8rem', padding: '4px 8px', borderRadius: '99px', background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}>
              {issue.status}
            </span>
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
            <label style={labelStyle}>{t('editor.title')}</label>
            <input type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>{t('editor.description')}</label>
            <textarea value={formData.description || ''} onChange={(e) => handleChange('description', e.target.value)} rows={4} style={inputStyle} />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('issues.severity')}</label>
              <select value={formData.severity || 'medium'} onChange={(e) => handleChange('severity', e.target.value)} style={inputStyle}>
                {SEVERITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('editor.status')}</label>
              <select value={formData.status || 'Open'} onChange={(e) => handleChange('status', e.target.value)} style={inputStyle}>
                {STATUS_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('issues.category')}</label>
              <select value={formData.category || 'defect'} onChange={(e) => handleChange('category', e.target.value)} style={inputStyle}>
                {CATEGORY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label style={labelStyle}>{t('issues.tags')}</label>
            <input type="text" value={(formData.tags || []).join(', ')} onChange={(e) => handleChange('tags', e.target.value.split(',').map((s: string) => s.trim()).filter(Boolean))}
              placeholder="tag1, tag2, tag3" style={inputStyle} />
          </div>
        </div>
      </div>
    </div>
  );
}
