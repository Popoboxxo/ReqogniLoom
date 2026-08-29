import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { testcasesApi, type TestCase } from '../../api/testcases';
import type { CustomFields } from '../../types';
import { VersionBadge } from '../shared/VersionBadge';
import { StatusBadge } from '../shared/StatusBadge';
import { getWorkflowStatusLabel } from '../../utils/workflowStatus';
import { ArtifactId } from '../shared/ArtifactId';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useEntityReset } from '../../hooks/use-entity-reset';
import { useFormDirty } from '../../hooks/use-form-dirty';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import styles from './TestCaseForm.module.css';

interface TestCaseFormProps {
  testCase: TestCase | null;
  onSaved: () => void;
  onDeleted?: () => void;
  /**
   * Systemaudit 2026-08-27 UI-07: invoked whenever this form's "has unsaved
   * local edits" state changes, so the parent (TestCaseEditors) can warn
   * before navigating away to a different test case and silently discarding
   * them. Mirrors RequirementForm's `onDirtyChange` (issue #672).
   */
  onDirtyChange?: (isDirty: boolean) => void;
}

/**
 * Systemaudit 2026-08-27 UI-07: mirrors `RequirementFormValues`
 * (RequirementForm.tsx) — a snapshot of every locally-editable field, shared
 * between the entity-switch reset, the `isDirty` baseline and the post-save
 * `markClean` call, so all three always agree on the same shape.
 */
interface TestCaseFormValues {
  title: string;
  description: string;
  customFields: CustomFields;
  changeReason: string;
}

export function TestCaseForm({ testCase, onSaved, onDeleted, onDirtyChange }: TestCaseFormProps): JSX.Element {
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

  // Systemaudit 2026-08-27 UI-07: "has unsaved local edits" tracking, so the
  // parent (TestCaseEditors) can warn before navigating away to a different
  // test case — mirrors RequirementForm's issue #672 handling. The baseline
  // is re-anchored explicitly from the entity-switch reset below and from a
  // successful Save, never implicitly from the raw `testCase` prop (see
  // `useFormDirty`'s own docstring for why).
  const formValues = useMemo<TestCaseFormValues>(
    () => ({
      title: formData.title ?? '',
      description: formData.description ?? '',
      customFields: formData.custom_fields ?? {},
      changeReason,
    }),
    [formData.title, formData.description, formData.custom_fields, changeReason]
  );
  const { isDirty, markClean } = useFormDirty(formValues, formValues);

  useEffect(() => {
    onDirtyChange?.(isDirty);
    // Cleanup: report "not dirty" on unmount so a stale `true` from a
    // previous mount (e.g. after Delete) can't make the parent show an
    // unsaved-changes dialog for a form that no longer exists.
    return () => {
      onDirtyChange?.(false);
    };
  }, [isDirty, onDirtyChange]);

  // Systemaudit 2026-08-27 UI-07: keyed on `testCase?.id` (via the shared
  // `useEntityReset`, matching RequirementForm/ArchitectureForm/NeedForm),
  // NOT on the whole `testCase` object — a refetch of the SAME test case
  // (e.g. right after Save, via `onSaved()`'s refresh, or an unrelated
  // background reload) must not blindly overwrite local edits still in
  // flight. `'__none__'` is a stable sentinel for "no test case selected".
  useEntityReset(testCase?.id ?? '__none__', () => {
    const next: TestCaseFormValues = testCase
      ? {
          title: testCase.title,
          description: testCase.description ?? '',
          customFields: testCase.custom_fields ?? {},
          changeReason: '',
        }
      : { title: '', description: '', customFields: {}, changeReason: '' };
    setFormData(testCase ? { ...testCase } : {});
    // Reset transient action state when switching to a different test case.
    setChangeReason(next.changeReason);
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
    markClean(next);
  });

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
      // Systemaudit 2026-08-27 UI-07: `change_reason` annotates *this* edit
      // only — clear it on a successful save (mirrors RequirementForm/
      // NeedForm) and re-anchor the isDirty baseline to exactly what was
      // just submitted, not to whatever `testCase` next resolves with via
      // `onSaved()`'s refresh, which lags this by a network round trip.
      setChangeReason('');
      markClean({ ...formValues, changeReason: '' });
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
      // Issue #670: the confirmation is a modal now, not an inline row — it
      // must be dismissed explicitly on success too, otherwise it keeps
      // covering the page whenever the parent leaves this form mounted (e.g.
      // it only refetches instead of clearing the selection).
      setConfirmDelete(false);
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
    return <p className={styles.emptyState}>{t('testcases.selectTestCase')}</p>;
  }

  // Issue #669: the former in-body `inputStyle` / `labelStyle`
  // `React.CSSProperties` constants (re-created on every render) now live in
  // `TestCaseForm.module.css` as `.input` / `.label`, mirroring how
  // RequirementForm keeps its chrome out of the TSX.

  return (
    <div className={styles.card}>
      <div className={styles.main}>
        <div className={styles.header}>
          <div className={styles.identity}>
            <StatusBadge status={testCase.status} label={getWorkflowStatusLabel(testCase.status)} />
            {testCase.version && <VersionBadge version={testCase.version} />}
            <ArtifactId value={testCase.uid} fallback={testCase.id.slice(0, 8)} testId="tc-id" />
          </div>
          <div className={styles.headerActions}>
            <button data-testid="tc-delete-btn" onClick={() => setConfirmDelete(true)} className="btn-danger">
              {t('actions.delete')}
            </button>
            <button data-testid="tc-save-btn" onClick={handleSave} className="btn-primary" disabled={isSaving}>
              {isSaving ? t('actions.saving') : t('actions.save')}
            </button>
          </div>
        </div>

        {/* Issue #670: deletion used to confirm through an inline
            "Löschen? Ja/Nein" row in this header — one of three competing
            delete interactions across the artifact forms. All of them now run
            through the shared <ConfirmDialog>. The historical button testids
            are preserved so existing E2E selectors keep working. */}
        {confirmDelete && (
          <ConfirmDialog
            title={t('testcases.deleteTitle')}
            message={t('actions.deleteConfirmPromptNamed', { name: testCase.title })}
            confirmLabel={isDeleting ? t('actions.deleting') : t('actions.delete')}
            onConfirm={() => void handleDelete()}
            onCancel={() => setConfirmDelete(false)}
            isSubmitting={isDeleting}
            testId="tc-delete-dialog"
            confirmTestId="tc-confirm-delete-btn"
            cancelTestId="tc-cancel-delete-btn"
          />
        )}
        {saveError && (
          <p role="alert" className={styles.error}>
            {saveError}
          </p>
        )}
        {deleteError && (
          <p role="alert" className={styles.error}>
            {deleteError}
          </p>
        )}
        <div className={styles.fields}>
          <div>
            <label htmlFor="tc-title" className={styles.label}>
              {t('editor.title')} <span className={styles.requiredMarker}>*</span>
            </label>
            <input id="tc-title" type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} className={styles.input} aria-required="true" />
          </div>
          <div>
            <label className={styles.label}>{t('editor.description')}</label>
            <MarkdownPreview value={formData.description || ''} onChange={(v) => handleChange('description', v)} />
          </div>
          <div className={styles.fieldRow}>
            <div className={styles.fieldRowItem}>
              <label className={styles.label}>{t('editor.status')}</label>
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
              <label htmlFor="tc-change-reason" className={styles.label}>
                {t('req.changeReason')} <span className={styles.requiredMarker}>*</span>
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
                className={`${styles.input} ${styles.textarea}`}
                placeholder={t('req.changeReasonPlaceholder')}
              />
            </div>
          )}
        </div>

        {/* SECTION: Custom Fields */}
        <div className={styles.customFieldsSection}>
          <h3 className={styles.sectionHeading}>{t('customFields.section')}</h3>
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
