import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { ArchitectureElement, StakeholderNeed, MoscowPriority, CustomFields, Requirement } from '../../types';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useEntityReset } from '../../hooks/use-entity-reset';
import { useFormDirty } from '../../hooks/use-form-dirty';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';
import { stakeholderNeedApi } from '../../api/stakeholder-need';
import type { DerivedRequirementDraft } from '../../api/stakeholder-need';
import { DeriveRequirementsPanel } from './DeriveRequirementsPanel';
import { requirementsApi } from '../../api/requirements';
import { architectureApi } from '../../api/architecture';
import { tracelinksApi } from '../../api/tracelinks';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { DeriveRequirementForm } from '../shared/DeriveRequirementForm';
import { VersionBadge } from '../shared/VersionBadge';
import { ArtifactId } from '../shared/ArtifactId';
import { StatusBadge } from '../shared/StatusBadge';
import { getWorkflowStatusLabel } from '../../utils/workflowStatus';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { ArtifactCustomFields } from '../shared/ArtifactCustomFields';

/**
 * Systemaudit 2026-08-27 UI-06: mirrors `RequirementFormValues`
 * (RequirementForm.tsx) — a snapshot of every locally-editable field, shared
 * between the entity-switch reset, the `isDirty` baseline and the post-save
 * `markClean` call, so all three always agree on the same shape.
 */
interface NeedFormValues {
  title: string;
  description: string;
  category: string;
  moscowPriority: MoscowPriority | undefined;
  customFields: CustomFields;
  changeReason: string;
}

interface NeedFormProps {
  need: StakeholderNeed | null;
  onSaved: () => void;
  onDeleted: () => void;
  attributeVisibility?: Record<string, boolean>;
  onNeedsChanged?: () => void;
  /**
   * Systemaudit 2026-08-27 UI-06: invoked whenever this form's "has unsaved
   * local edits" state changes, so the parent (NeedsEditors) can warn before
   * navigating away to a different need and silently discarding them.
   * Mirrors RequirementForm's `onDirtyChange` (issue #672).
   */
  onDirtyChange?: (isDirty: boolean) => void;
}

export function NeedForm({ need, onSaved, onDeleted, attributeVisibility = {}, onNeedsChanged, onDirtyChange }: NeedFormProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  // REQ-162: Extended preset requires a change_reason on every update
  // (backend/application/preset_policy_service.py: is_change_reason_required).
  const isExtendedPreset = activeWorkspace?.preset === 'extended';
  const [formData, setFormData] = useState<Partial<StakeholderNeed>>({});
  const [changeReason, setChangeReason] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [isDeriving, setIsDeriving] = useState(false);
  const [derivationStatus, setDerivationStatus] = useState<string | null>(null);
  const [derivationIsError, setDerivationIsError] = useState(false);
  const [derivedDrafts, setDerivedDrafts] = useState<DerivedRequirementDraft[] | null>(null);

  // Manual "Ableiten": create a Requirement derived from this need, with an
  // optional architecture allocation (SE: Req --derives-from--> Need,
  // Req --allocated-to--> ArchitectureElement).
  const [showDeriveForm, setShowDeriveForm] = useState(false);
  const [deriveTitle, setDeriveTitle] = useState('');
  const [deriveArchId, setDeriveArchId] = useState('');
  const [isManualDeriving, setIsManualDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);
  const [archElements, setArchElements] = useState<ArchitectureElement[]>([]);

  useEffect(() => {
    if (!showDeriveForm || !need) return;
    let cancelled = false;
    architectureApi
      .listAll(need.workspace_id)
      .then((els) => { if (!cancelled) setArchElements(els); })
      .catch(() => { if (!cancelled) setArchElements([]); });
    return () => { cancelled = true; };
  }, [showDeriveForm, need]);

  const handleManualDerive = async () => {
    if (!need) return;
    if (!deriveTitle.trim()) {
      setDeriveError(t('traceability.deriveTitleRequired'));
      return;
    }
    setIsManualDeriving(true);
    setDeriveError(null);
    // UI-33 (Systemaudit 2026-08-27 AP-5): this is three independent REST
    // calls (create Requirement, create 'derives-from' link, optionally
    // create 'allocated-to' link), not one DB transaction — a failure on
    // either link call used to leave `created` as an orphaned Requirement
    // (persisted, but never linked back to the Need) while the user only
    // saw a generic "derive failed" message with no indication anything had
    // been written at all.
    let created: Requirement | null = null;
    try {
      created = await requirementsApi.create({
        workspace_id: need.workspace_id,
        title: deriveTitle.trim(),
      });
      await tracelinksApi.create({
        source_id: created.id,
        target_id: need.artifact_id,
        link_type: 'derives-from',
      });
      if (deriveArchId) {
        await tracelinksApi.create({
          source_id: created.id,
          target_id: deriveArchId,
          link_type: 'allocated-to',
        });
      }
      setShowDeriveForm(false);
      setDeriveTitle('');
      setDeriveArchId('');
      if (onNeedsChanged) onNeedsChanged();
      navigate(`/requirements/${created.id}`);
    } catch (err) {
      console.error(err);
      const apiErr = err as { error?: { message?: string } };
      const baseMessage = apiErr?.error?.message ?? t('needs.deriveFailed');
      if (created) {
        // Best-effort compensating action: soft-delete the orphan instead
        // of leaving it silently in the working set, and tell the user
        // explicitly whether that cleanup succeeded — never just "derive
        // failed" once something was actually persisted.
        try {
          await requirementsApi.delete(created.id);
          setDeriveError(
            t('needs.deriveRolledBack', {
              message: baseMessage,
              defaultValue: `${baseMessage} The already-created requirement was rolled back (archived).`,
            }),
          );
        } catch (rollbackErr) {
          console.error(rollbackErr);
          setDeriveError(
            t('needs.derivePartialFailure', {
              message: baseMessage,
              id: created.id,
              defaultValue: `${baseMessage} Warning: a requirement was already created, but linking it to the need failed and the automatic rollback failed too. Please check manually (requirement id: ${created.id}).`,
            }),
          );
        }
      } else {
        setDeriveError(baseMessage);
      }
    } finally {
      setIsManualDeriving(false);
    }
  };

  const handleDerive = async () => {
    if (!need) return;
    setIsDeriving(true);
    setDerivationIsError(false);
    setDerivationStatus(t('needs.deriveStarting'));
    setDerivedDrafts(null);
    try {
      const res = await stakeholderNeedApi.deriveRequirements(need.id);
      const drafts = res.drafts ?? [];
      if (drafts.length === 0) {
        setDerivationStatus(t('needs.deriveEmpty'));
        return;
      }
      setDerivedDrafts(drafts);
      setDerivationStatus(null);
    } catch (err) {
      console.error(err);
      const apiErr = err as { error?: { message?: string } };
      setDerivationIsError(true);
      setDerivationStatus(apiErr?.error?.message ?? t('needs.deriveFailed'));
    } finally {
      setIsDeriving(false);
    }
  };

  const handleDraftsAccepted = (count: number) => {
    setDerivedDrafts(null);
    setDerivationIsError(false);
    setDerivationStatus(t('needs.deriveCreated', { count }));
    if (onNeedsChanged) onNeedsChanged();
  };

  // Systemaudit 2026-08-27 UI-06: "has unsaved local edits" tracking, so the
  // parent (NeedsEditors) can warn before navigating away to a different
  // need — mirrors RequirementForm's issue #672 handling. The baseline is
  // re-anchored explicitly from the entity-switch reset below and from a
  // successful Save, never implicitly from the raw `need` prop (see
  // `useFormDirty`'s own docstring for why).
  const formValues = useMemo<NeedFormValues>(
    () => ({
      title: formData.title ?? '',
      description: formData.description ?? '',
      category: formData.category ?? '',
      moscowPriority: formData.moscow_priority,
      customFields: formData.custom_fields ?? {},
      changeReason,
    }),
    [
      formData.title,
      formData.description,
      formData.category,
      formData.moscow_priority,
      formData.custom_fields,
      changeReason,
    ]
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

  // Systemaudit 2026-08-27 UI-06: keyed on `need?.id` (via the shared
  // `useEntityReset`, matching RequirementForm/ArchitectureForm), NOT on the
  // whole `need` object — a refetch of the SAME need (e.g. right after Save,
  // via `onSaved()`'s refresh, or an unrelated background reload) must not
  // blindly overwrite local edits still in flight. `'__none__'` is a stable
  // sentinel for "no need selected" so that case still resets exactly once.
  useEntityReset(need?.id ?? '__none__', () => {
    const next: NeedFormValues = need
      ? {
          title: need.title,
          description: need.description ?? '',
          category: need.category ?? '',
          moscowPriority: need.moscow_priority,
          customFields: need.custom_fields ?? {},
          changeReason: need.change_reason || '',
        }
      : {
          title: '',
          description: '',
          category: '',
          moscowPriority: undefined,
          customFields: {},
          changeReason: '',
        };
    setFormData(need ? { ...need } : {});
    setChangeReason(next.changeReason);
    // Reset transient action state when switching to a different need.
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
    markClean(next);
  });

  const handleChange = <K extends keyof StakeholderNeed>(field: K, value: StakeholderNeed[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear any pending error once the user starts editing (UI standards §5.4).
    if (saveError) setSaveError(null);
    if (deleteError) setDeleteError(null);
  };

  const handleSave = async () => {
    if (!need) return;
    // REQ-162: Extended preset enforces a mandatory change_reason on every
    // update (backend returns HTTP 400 otherwise) — block the save client-side
    // with the same message pattern used in RequirementForm/ArchitectureForm.
    if (isExtendedPreset && !changeReason.trim()) {
      setSaveError(t('req.changeReasonRequired'));
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    try {
      const updateData: Partial<StakeholderNeed> = {
        title: formData.title,
        description: formData.description,
        category: formData.category,
        moscow_priority: formData.moscow_priority,
        // #263: `status` is deliberately NOT sent. It is a read-only
        // WorkflowEngine mirror; lifecycle changes run through
        // POST .../transitions/ (see <WorkflowStatusEditor/> below).
        custom_fields: formData.custom_fields,
      };
      if (isExtendedPreset) {
        updateData.change_reason = changeReason.trim();
      }
      await stakeholderNeedApi.update(need.id, updateData);

      // Systemaudit 2026-08-27 UI-06: `change_reason` annotates *this* edit
      // only — it never round-trips through the server — so it is cleared
      // here explicitly on a successful save (mirrors RequirementForm's
      // post-save behavior, issue #344/#672). The isDirty baseline is
      // re-anchored to exactly what was just submitted, not to whatever
      // `need` next resolves with via `onSaved()`'s refresh — which lags
      // this by a network round trip and would otherwise show a spurious
      // "unsaved changes" state until it resolves.
      setChangeReason('');
      markClean({ ...formValues, changeReason: '' });
      onSaved();
    } catch (err) {
      console.error(err);
      const msg = (err as { error?: { message?: string } })?.error?.message ?? t('needs.saveFailed');
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!need) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await stakeholderNeedApi.delete(need.id);
      // Issue #670: the confirmation is a modal now, not an inline row — it
      // must be dismissed explicitly on success too, otherwise it keeps
      // covering the page whenever the parent leaves this form mounted.
      setConfirmDelete(false);
      onDeleted();
    } catch (err) {
      console.error(err);
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        t('needs.deleteFailed', 'Löschen fehlgeschlagen. Bitte erneut versuchen.');
      setDeleteError(msg);
      setConfirmDelete(false);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!need) {
    return (
      <p
        style={{
          color: 'var(--color-text-muted)',
          fontSize: 'var(--font-size-lg)',
          textAlign: 'center',
          padding: 'var(--space-8)',
        }}
      >
        {t("needs.selectNeed")}
      </p>
    );
  }

  // Styles to match RequirementForm
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
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-6)' }}>
          {/* Identity block — UI concept ch. 12.4: id, status, version in
              that order, identical to the list row. Replaces the inline
              `fontFamily: monospace` span (one of four such duplicates). */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', minWidth: 0 }}>
            <ArtifactId
              testId="need-artifact-id"
              value={need.uid}
              fallback={need.id.slice(0, 8)}
              copyValue={need.uid || need.id}
            />
            {need.status && <StatusBadge status={need.status} testId="need-status-badge" label={getWorkflowStatusLabel(need.status)} />}
            {need.version && <VersionBadge version={need.version} />}
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            <button
              data-testid="need-delete-btn"
              onClick={() => setConfirmDelete(true)}
              className="btn-danger"
            >
              {t('actions.delete')}
            </button>
            <button data-testid="need-save-btn" onClick={handleSave} className="btn-primary" disabled={isSaving}>
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
            title={t('needs.deleteTitle')}
            message={t('actions.deleteConfirmPromptNamed', { name: need.title })}
            confirmLabel={isDeleting ? t('actions.deleting') : t('actions.delete')}
            onConfirm={() => void handleDelete()}
            onCancel={() => setConfirmDelete(false)}
            isSubmitting={isDeleting}
            testId="need-delete-dialog"
            confirmTestId="need-confirm-delete-btn"
            cancelTestId="need-cancel-delete-btn"
          />
        )}

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
            <label htmlFor="need-title" style={labelStyle}>
              {t('editor.title')}
            </label>
            <input
              id="need-title"
              type="text"
              value={formData.title || ''}
              onChange={(e) => handleChange('title', e.target.value)}
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: 'var(--space-4)' }}>
            <label style={labelStyle}>
              {t('editor.description')}
            </label>
            <MarkdownPreview
              value={formData.description || ''}
              onChange={(v) => handleChange('description', v)}
            />
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>
                {t('editor.workflowState', 'Status')}
              </label>
              {/* REQ-165: unified WorkflowEngine-driven status editor replaces the
                  hardcoded status <select>. Transitions run through the
                  WorkflowFacade and re-fetch the need on completion. */}
              <WorkflowStatusEditor
                artifactType="need"
                artifactId={need.id}
                currentStatus={need.status}
                disabled={isSaving}
                onTransitionComplete={onSaved}
              />
            </div>

            <div style={{ flex: 1 }}>
              <label htmlFor="need-category" style={labelStyle}>
                {t('editor.category')}
              </label>
              <input
                id="need-category"
                type="text"
                value={formData.category || ''}
                onChange={(e) => handleChange('category', e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={{ flex: 1 }}>
              {attributeVisibility.moscow_priority !== false && (
                <>
                  <label htmlFor="need-moscow-priority" style={labelStyle}>
                    {t('editor.moscowPriority')}
                  </label>
                  <select
                    id="need-moscow-priority"
                    value={formData.moscow_priority || ''}
                    onChange={(e) => handleChange('moscow_priority', (e.target.value || undefined) as MoscowPriority | undefined)}
                    style={inputStyle}
                  >
                    <option value="">{t('needs.priorityNone')}</option>
                    <option value="Must">Must</option>
                    <option value="Should">Should</option>
                    <option value="Could">Could</option>
                    <option value="Won't">Won't</option>
                  </select>
                </>
              )}
            </div>
          </div>
        </div>

        {/* SECTION: Custom Fields */}
        <div style={{ marginBottom: 'var(--space-6)', marginTop: 'var(--space-6)' }}>
          <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
            {t('customFields.section')}
          </h3>
          <CustomFieldsEditor
            key={need.id}
            value={need.custom_fields}
            onChange={(newFields) => handleChange('custom_fields', newFields)}
            disabled={isSaving}
          />
        </div>

        {/* SECTION: workspace-defined attributes (REQ-016, UI concept
            ch. 12.11). CustomFieldsEditor above edits the free-form JSON blob
            on the need itself; this block renders the typed
            CustomFieldDefinitions of the workspace, which existed in the data
            model but were never shown outside the Requirements editor.
            Renders nothing when the workspace defines no fields. */}
        {need.artifact_id && <ArtifactCustomFields artifactId={need.artifact_id} />}

        {/* SECTION: Change Control (REQ-162) — Extended preset only, mirrors
            RequirementForm/ArchitectureForm change_reason handling. */}
        {isExtendedPreset && (
          <div style={{ marginBottom: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
              {t('req.section.changeControl')}
            </h3>

            <label htmlFor="need-change-reason" style={labelStyle}>
              {t('req.changeReason')} <span style={{ color: 'var(--color-danger)' }}>*</span>
            </label>
            <textarea
              id="need-change-reason"
              data-testid="need-change-reason-input"
              value={changeReason}
              onChange={(e) => {
                setChangeReason(e.target.value);
                if (saveError) setSaveError(null);
              }}
              rows={2}
              style={{ ...inputStyle, resize: 'vertical' }}
              placeholder={t('req.changeReasonPlaceholderNeed')}
            />
          </div>
        )}

        <TraceLinkPanel
          workspaceId={need.workspace_id}
          artifactId={need.artifact_id}
          onDerive={handleDerive}
          isDeriving={isDeriving}
        />
        {derivationStatus && (
          <div
            role={derivationIsError ? 'alert' : 'status'}
            data-testid="need-derive-status"
            style={{
              marginTop: 'var(--space-2)',
              fontSize: 'var(--font-size-sm)',
              color: derivationIsError ? 'var(--color-danger)' : 'var(--color-text)',
            }}
          >
            {derivationStatus}
          </div>
        )}
        {derivedDrafts && (
          <div style={{ marginTop: 'var(--space-3)' }}>
            <DeriveRequirementsPanel
              workspaceId={need.workspace_id}
              needArtifactId={need.artifact_id}
              drafts={derivedDrafts}
              onAccepted={handleDraftsAccepted}
              onDiscard={() => setDerivedDrafts(null)}
            />
          </div>
        )}

        {/* Manual derive: Requirement from this need + optional architecture
            allocation — same flow as in the requirements mask. */}
        <div style={{ marginTop: 'var(--space-4)' }}>
          <DeriveRequirementForm
            isOpen={showDeriveForm}
            onOpen={() => setShowDeriveForm(true)}
            onCancel={() => { setShowDeriveForm(false); setDeriveError(null); }}
            onSubmit={(e) => { e.preventDefault(); void handleManualDerive(); }}
            title={deriveTitle}
            onTitleChange={setDeriveTitle}
            architectureElements={archElements}
            architectureElementId={deriveArchId}
            onArchitectureElementChange={setDeriveArchId}
            isSubmitting={isManualDeriving}
            error={deriveError}
            testIdPrefix="need"
          />
        </div>
      </div>
    </div>
  );
}
