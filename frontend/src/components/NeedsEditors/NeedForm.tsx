import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { ArchitectureElement, StakeholderNeed, MoscowPriority } from '../../types';
import { useWorkspace } from '../../context/WorkspaceContext';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';
import { stakeholderNeedApi } from '../../api/stakeholder-need';
import { requirementsApi } from '../../api/requirements';
import { architectureApi } from '../../api/architecture';
import { tracelinksApi } from '../../api/tracelinks';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { DeriveRequirementForm } from '../shared/DeriveRequirementForm';
import { VersionBadge } from '../shared/VersionBadge';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';

interface NeedFormProps {
  need: StakeholderNeed | null;
  onSaved: () => void;
  onDeleted: () => void;
  attributeVisibility?: Record<string, boolean>;
  onNeedsChanged?: () => void;
}

export function NeedForm({ need, onSaved, onDeleted, attributeVisibility = {}, onNeedsChanged }: NeedFormProps): JSX.Element {
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
    try {
      const created = await requirementsApi.create({
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
      setDeriveError(apiErr?.error?.message ?? t('needs.deriveFailed'));
    } finally {
      setIsManualDeriving(false);
    }
  };

  const handleDerive = async () => {
    if (!need) return;
    setIsDeriving(true);
    setDerivationIsError(false);
    setDerivationStatus(t('needs.deriveStarting'));
    try {
      const res = await stakeholderNeedApi.deriveRequirements(need.id);
      setDerivationStatus(t('needs.deriveStarted', { taskId: res.task_id }));

      setTimeout(() => {
        setDerivationIsError(false);
        setDerivationStatus(t('needs.deriveSuccess'));
        setIsDeriving(false);
        if (onNeedsChanged) onNeedsChanged();
      }, 3000);
    } catch (err) {
      console.error(err);
      const apiErr = err as { error?: { message?: string } };
      setDerivationIsError(true);
      setDerivationStatus(apiErr?.error?.message ?? t('needs.deriveFailed'));
      setIsDeriving(false);
    }
  };

  useEffect(() => {
    if (need) {
      setFormData({ ...need });
      setChangeReason(need.change_reason || '');
    } else {
      setFormData({});
      setChangeReason('');
    }
    // Reset transient action state when switching to a different need.
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
  }, [need]);

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
        status: formData.status,
        custom_fields: formData.custom_fields,
      };
      if (isExtendedPreset) {
        updateData.change_reason = changeReason.trim();
      }
      await stakeholderNeedApi.update(need.id, updateData);
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
          <div>
            <span style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', fontFamily: 'monospace', marginRight: 'var(--space-2)' }}>
              {need.uid}
            </span>
            {need.version && <VersionBadge version={need.version} />}
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            {!confirmDelete ? (
              <button
                data-testid="need-delete-btn"
                onClick={() => setConfirmDelete(true)}
                className="btn-danger"
              >
                {t('actions.delete')}
              </button>
            ) : (
              <>
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                  {t('actions.deleteConfirmPrompt', 'Löschen?')}
                </span>
                <button
                  data-testid="need-confirm-delete-btn"
                  onClick={handleDelete}
                  className="btn-danger"
                  disabled={isDeleting}
                >
                  {isDeleting ? t('actions.deleting', 'Löschen...') : t('actions.confirmDelete', 'Ja, löschen')}
                </button>
                <button
                  data-testid="need-cancel-delete-btn"
                  onClick={() => setConfirmDelete(false)}
                  className="btn-ghost"
                  disabled={isDeleting}
                >
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
            <label style={labelStyle}>
              {t('editor.title')}
            </label>
            <input
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
              <label style={labelStyle}>
                {t('editor.category')}
              </label>
              <input
                type="text"
                value={formData.category || ''}
                onChange={(e) => handleChange('category', e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={{ flex: 1 }}>
              {attributeVisibility.moscow_priority !== false && (
                <>
                  <label style={labelStyle}>
                    {t('editor.moscowPriority')}
                  </label>
                  <select
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
            value={need.custom_fields}
            onChange={(newFields) => handleChange('custom_fields', newFields)}
            disabled={isSaving}
          />
        </div>

        {/* SECTION: Change Control (REQ-162) — Extended preset only, mirrors
            RequirementForm/ArchitectureForm change_reason handling. */}
        {isExtendedPreset && (
          <div style={{ marginBottom: 'var(--space-6)' }}>
            <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
              Change Control
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
              placeholder={t('req.changeReasonPlaceholder')}
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
