import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { testcasesApi, type TestCase } from '../../api/testcases';
import { VersionBadge } from '../shared/VersionBadge';
import { StatusBadge } from '../shared/StatusBadge';
import { ArtifactId } from '../shared/ArtifactId';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';
import { useWorkspace } from '../../context/WorkspaceContext';

interface TestCaseFormProps {
  testCase: TestCase | null;
  onSaved: () => void;
  onDeleted?: () => void;
}

export function TestCaseForm({ testCase, onSaved, onDeleted }: TestCaseFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  // REQ-162: Extended preset captures a change_reason on every update
  // (forwarded to the backend audit log).
  const isExtendedPreset = activeWorkspace?.preset === 'extended';
  const [formData, setFormData] = useState<Partial<TestCase>>({});
  const [changeReason, setChangeReason] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (testCase) setFormData({ ...testCase });
    else setFormData({});
    // Reset transient action state when switching to a different test case.
    setChangeReason('');
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
  }, [testCase]);

  const handleChange = <K extends keyof TestCase>(field: K, value: TestCase[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (saveError) setSaveError(null);
    if (deleteError) setDeleteError(null);
  };

  const handleSave = async () => {
    if (!testCase) return;
    // REQ-162: Extended preset requires a change_reason before saving.
    if (isExtendedPreset && !changeReason.trim()) {
      setSaveError(t('req.changeReasonRequired'));
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    try {
      await testcasesApi.update(testCase.id, {
        title: formData.title,
        description: formData.description,
        // #263: `status` is deliberately NOT sent. It is a read-only
        // WorkflowEngine mirror; lifecycle changes run through
        // POST .../transitions/ (see <WorkflowStatusEditor/>).
        custom_fields: formData.custom_fields,
        ...(isExtendedPreset ? { change_reason: changeReason.trim() } : {}),
      });
      onSaved();
    } catch (err) {
      console.error(err);
      const msg = (err as { error?: { message?: string } })?.error?.message ?? t('testcases.saveFailed');
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!testCase) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await testcasesApi.delete(testCase.id);
      onDeleted?.();
    } catch (err) {
      console.error(err);
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        t('testcases.deleteFailed', 'Löschen fehlgeschlagen. Bitte erneut versuchen.');
      setDeleteError(msg);
      setConfirmDelete(false);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!testCase) {
    return (
      <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-lg)', textAlign: 'center', padding: 'var(--space-8)' }}>
        {t('testcases.selectTestCase')}
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
            <StatusBadge status={testCase.status} />
            {testCase.version && <VersionBadge version={testCase.version} />}
            <ArtifactId value={testCase.uid} fallback={testCase.id.slice(0, 8)} testId="tc-id" />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            {!confirmDelete ? (
              <button data-testid="tc-delete-btn" onClick={() => setConfirmDelete(true)} className="btn-danger">
                {t('actions.delete')}
              </button>
            ) : (
              <>
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                  {t('actions.deleteConfirmPrompt', 'Löschen?')}
                </span>
                <button data-testid="tc-confirm-delete-btn" onClick={handleDelete} className="btn-danger" disabled={isDeleting}>
                  {isDeleting ? t('actions.deleting', 'Löschen...') : t('actions.confirmDelete', 'Ja, löschen')}
                </button>
                <button data-testid="tc-cancel-delete-btn" onClick={() => setConfirmDelete(false)} className="btn-ghost" disabled={isDeleting}>
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
            <label htmlFor="tc-title" style={labelStyle}>{t('editor.title')} <span style={{ color: 'var(--color-danger)' }}>*</span></label>
            <input id="tc-title" type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} style={inputStyle} aria-required="true" />
          </div>
          <div>
            <label style={labelStyle}>{t('editor.description')}</label>
            <MarkdownPreview value={formData.description || ''} onChange={(v) => handleChange('description', v)} />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('editor.status')}</label>
              {/* REQ-165: WorkflowEngine-driven status editor (replaces the
                  hardcoded status select). */}
              <WorkflowStatusEditor
                artifactType="test-case"
                artifactId={testCase.id}
                currentStatus={testCase.status}
                disabled={isSaving}
                onTransitionComplete={onSaved}
              />
            </div>
          </div>

          {/* REQ-162: Change Control — Extended preset only. */}
          {isExtendedPreset && (
            <div>
              <label htmlFor="tc-change-reason" style={labelStyle}>
                {t('req.changeReason')} <span style={{ color: 'var(--color-danger)' }}>*</span>
              </label>
              <textarea
                id="tc-change-reason"
                data-testid="tc-change-reason-input"
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

        {/* SECTION: Custom Fields */}
        <div style={{ marginBottom: 'var(--space-6)', marginTop: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
            {t('customFields.section')}
          </h3>
          <CustomFieldsEditor
            value={testCase.custom_fields}
            onChange={(newFields) => handleChange('custom_fields', newFields)}
            disabled={isSaving}
          />
        </div>
      </div>
    </div>
  );
}
