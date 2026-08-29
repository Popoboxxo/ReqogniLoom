import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useWorkspace } from '../../context/WorkspaceContext';
import type { Adr, TraceLink } from '../../types';
import { adrsApi } from '../../api/adrs';
import { tracelinksApi } from '../../api/tracelinks';
import { VersionBadge } from '../shared/VersionBadge';
import { StatusBadge } from '../shared/StatusBadge';
import { getWorkflowStatusLabel } from '../../utils/workflowStatus';
import { ArtifactId } from '../shared/ArtifactId';
import { ArtifactCustomFields } from '../shared/ArtifactCustomFields';
import { MarkdownPreview } from '../RequirementEditors/MarkdownPreview';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';

// UI-32: hoisted named style constants for the ADR-Supersede-Flow instead of
// inline literals (ui-ratchet.test.ts style-brace ceiling).
const supersededByTextStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-text-muted)',
  margin: 0,
};
const supersedePanelStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-2)',
  padding: 'var(--space-3)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  background: 'var(--color-surface-raised)',
};
const supersedeTextareaStyle: React.CSSProperties = {
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
  resize: 'vertical',
};
const supersedeErrorStyle: React.CSSProperties = {
  color: 'var(--color-danger)',
  fontSize: 'var(--font-size-sm)',
  margin: 0,
};
const supersedeActionsRowStyle: React.CSSProperties = {
  display: 'flex',
  gap: 'var(--space-2)',
};

interface AdrFormProps {
  adr: Adr | null;
  /**
   * UI-32 (Systemaudit 2026-08-27 AP-5): the other ADRs in the same
   * workspace, offered as candidate successors in the "Supersede durch..."
   * picker. Excludes `adr` itself (the caller passes the full workspace
   * list; this component filters it).
   */
  otherAdrs: Adr[];
  /**
   * UI-LOW-3 (Systemaudit, LOW finding): `handleSupersede` below passes the
   * mutation's own response through so the caller can write it into its
   * cache/state synchronously instead of only invalidating and waiting for
   * a refetch — see `useAdrData.refresh`'s doc comment. Optional because the
   * plain-save and delete paths have no comparable "fresh entity" to hand
   * back (and are not the ones this finding was about).
   */
  onSaved: (updated?: Adr) => void;
  onDeleted: () => void;
}

export function AdrForm({ adr, otherAdrs, onSaved, onDeleted }: AdrFormProps): JSX.Element {
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

  // UI-32: ADR-Supersede-Flow (REQ-L3-ADR-005).
  const [supersedeOpen, setSupersedeOpen] = useState(false);
  const [supersedeTargetId, setSupersedeTargetId] = useState('');
  const [supersedeReason, setSupersedeReason] = useState('');
  const [isSuperseding, setIsSuperseding] = useState(false);
  const [supersedeError, setSupersedeError] = useState<string | null>(null);
  const [supersededByLink, setSupersededByLink] = useState<TraceLink | null>(null);

  useEffect(() => {
    if (adr) setFormData({ ...adr });
    else setFormData({});
    // Reset transient action state when switching to a different ADR.
    setChangeReason('');
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
    setSupersedeOpen(false);
    setSupersedeTargetId('');
    setSupersedeReason('');
    setSupersedeError(null);
  }, [adr]);

  // UI-32: resolve "Abgelöst durch: [ADR-XXX]" from the `decides` TraceLink
  // `AdrService.transition_status` creates (source=successor, target=this
  // ADR) — there is no dedicated `superseded_by` column on Adr, the
  // TraceLink graph is the single source of truth (REQ-L3-ADR-005).
  useEffect(() => {
    let cancelled = false;
    if (!adr || adr.status !== 'Superseded' || !activeWorkspace) {
      setSupersededByLink(null);
      return undefined;
    }
    void (async () => {
      try {
        const resp = await tracelinksApi.listForArtifact(activeWorkspace.id, adr.id);
        if (cancelled) return;
        const link = resp.results.find(
          (l) => l.link_type === 'decides' && l.target_id === adr.id && l.source_type === 'Adr',
        );
        setSupersededByLink(link ?? null);
      } catch {
        // Degrades to "no successor shown" — same contract every other
        // best-effort lookup in this codebase uses (e.g. MainGoalPanel's
        // archive-transition lookup).
        if (!cancelled) setSupersededByLink(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [adr, activeWorkspace]);

  const candidateSuccessors = adr ? otherAdrs.filter((other) => other.id !== adr.id) : [];

  // Fix (systemaudit 2026-08-29, Bug 4): the only workflow transition into
  // 'Superseded' is 'Approved' -> 'Superseded' (backend/workflow/
  // definition_store.py::_adr_transitions — adr_default is currently the
  // only ADR workflow definition). Before this fix, a Draft/In-Review ADR
  // let the user fill in the whole supersede form only to fail at submit
  // time with a generic "Transition not allowed" error from the backend
  // workflow gate. Mirrors that same rule client-side so the button is
  // disabled/hinted up front instead.
  const canSupersede = adr?.status === 'Approved';

  const openSupersede = useCallback((): void => {
    setSupersedeError(null);
    setSupersedeTargetId('');
    setSupersedeReason('');
    setSupersedeOpen(true);
  }, []);

  const closeSupersede = useCallback((): void => {
    setSupersedeOpen(false);
    setSupersedeError(null);
  }, []);

  const handleSupersede = async (): Promise<void> => {
    if (!adr || !supersedeTargetId) return;
    setIsSuperseding(true);
    setSupersedeError(null);
    try {
      const updated = await adrsApi.supersede(adr.id, supersedeTargetId, supersedeReason.trim());
      setSupersedeOpen(false);
      // UI-LOW-3: forward the response so the caller can update its status
      // badge immediately, without waiting for a background refetch.
      onSaved(updated);
    } catch (err) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        t('adrs.supersedeFailed', 'Supersede fehlgeschlagen. Bitte erneut versuchen.');
      setSupersedeError(msg);
    } finally {
      setIsSuperseding(false);
    }
  };

  const handleChange = <K extends keyof Adr>(field: K, value: Adr[K]) => {
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
        // #263: `status` is deliberately NOT sent. It is a read-only
        // WorkflowEngine mirror; lifecycle changes run through
        // POST .../transitions/ (see <WorkflowStatusEditor/>).
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
            <StatusBadge status={adr.status} label={getWorkflowStatusLabel(adr.status)} />
            {adr.version && <VersionBadge version={adr.version} />}
            <ArtifactId value={adr.uid} fallback={adr.id.slice(0, 8)} testId="adr-id" />
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
            <button data-testid="adr-save-btn" onClick={handleSave} className="btn-primary" disabled={isSaving}>
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
            <label htmlFor="adr-title" style={labelStyle}>{t('editor.title')} <span style={{ color: 'var(--color-danger)' }}>*</span></label>
            <input id="adr-title" type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} style={inputStyle} aria-required="true" placeholder={t('adrs.titlePlaceholder', 'Titel der Architekturentscheidung')} />
          </div>
          <div style={{ marginBottom: 'var(--space-4)' }}>
            <label htmlFor="adr-description" style={labelStyle}>{t('editor.description')}</label>
            <MarkdownPreview id="adr-description" value={formData.description || ''} onChange={(v) => handleChange('description', v)} />
          </div>
          <div>
            <label htmlFor="adr-context" style={labelStyle}>{t('adrs.context')}</label>
            <MarkdownPreview id="adr-context" value={formData.context || ''} onChange={(v) => handleChange('context', v)} />
          </div>
          <div>
            <label htmlFor="adr-consequences" style={labelStyle}>{t('adrs.consequences')}</label>
            <MarkdownPreview id="adr-consequences" value={formData.consequences || ''} onChange={(v) => handleChange('consequences', v)} />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div role="group" aria-labelledby="adr-status-label" style={{ flex: 1 }}>
              <span id="adr-status-label" style={labelStyle}>{t('editor.status')}</span>
              {/* REQ-165: WorkflowEngine-driven status editor (replaces the
                  hardcoded STATUS_OPTIONS select). role="group" +
                  aria-labelledby (not a <label htmlFor>) because
                  WorkflowStatusEditor renders a group of transition
                  buttons, not a single form control. */}
              {/* UI-LOW-3 follow-up (code review): `onTransitionComplete` is
                  invoked with the new status *string*. Since `onSaved` now
                  takes an optional `Adr`, passing it bare would forward that
                  string into `useAdrData.refresh`'s setQueryData call and
                  replace the cached ADR with a string. The generic transition
                  has no fresh entity to hand back, so it stays on the
                  invalidate-only path. */}
              <WorkflowStatusEditor
                artifactType="adr"
                artifactId={adr.id}
                currentStatus={adr.status}
                disabled={isSaving}
                onTransitionComplete={() => onSaved()}
              />
            </div>
          </div>

          {/* UI-32 (Systemaudit 2026-08-27 AP-5): ADR-Supersede-Flow
              (REQ-L3-ADR-005) — the backend capability
              (AdrService.transition_status(superseded_by_id=...)) existed
              with no UI entry point at all. */}
          {adr.status === 'Superseded' ? (
            supersededByLink && (
              <p
                data-testid="adr-superseded-by"
                style={supersededByTextStyle}
              >
                {t('adrs.supersededBy', {
                  title: supersededByLink.source_title || supersededByLink.source_id.slice(0, 8),
                  defaultValue: 'Abgelöst durch: {{title}}',
                })}
              </p>
            )
          ) : (
            <div>
              {!supersedeOpen ? (
                <button
                  type="button"
                  data-testid="adr-supersede-btn"
                  className="btn-secondary"
                  onClick={openSupersede}
                  disabled={!canSupersede || candidateSuccessors.length === 0}
                  title={
                    !canSupersede
                      ? t(
                          'adrs.supersedeWrongStatus',
                          'Supersede ist nur für ADRs im Status "Approved" möglich.'
                        )
                      : candidateSuccessors.length === 0
                        ? t('adrs.supersedeNoCandidates', 'Keine anderen ADRs in diesem Workspace vorhanden.')
                        : undefined
                  }
                >
                  {t('adrs.supersedeAction', 'Supersede durch...')}
                </button>
              ) : (
                <div style={supersedePanelStyle}>
                  <label htmlFor="adr-supersede-target" style={labelStyle}>
                    {t('adrs.supersedeTargetLabel', 'Abgelöst durch')}
                  </label>
                  <select
                    id="adr-supersede-target"
                    data-testid="adr-supersede-target-select"
                    value={supersedeTargetId}
                    onChange={(e) => setSupersedeTargetId(e.target.value)}
                    style={inputStyle}
                  >
                    <option value="">{t('adrs.supersedeTargetPlaceholder', 'ADR auswählen...')}</option>
                    {candidateSuccessors.map((candidate) => (
                      <option key={candidate.id} value={candidate.id}>
                        {candidate.title || candidate.id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                  <label htmlFor="adr-supersede-reason" style={labelStyle}>
                    {t('adrs.supersedeReasonLabel', 'Begründung')}
                  </label>
                  <textarea
                    id="adr-supersede-reason"
                    data-testid="adr-supersede-reason-input"
                    value={supersedeReason}
                    onChange={(e) => setSupersedeReason(e.target.value)}
                    rows={2}
                    style={supersedeTextareaStyle}
                  />
                  {supersedeError && (
                    <p role="alert" style={supersedeErrorStyle}>
                      {supersedeError}
                    </p>
                  )}
                  <div style={supersedeActionsRowStyle}>
                    <button
                      type="button"
                      data-testid="adr-supersede-confirm-btn"
                      className="btn-primary"
                      onClick={() => void handleSupersede()}
                      disabled={isSuperseding || !supersedeTargetId}
                    >
                      {isSuperseding ? t('actions.saving', 'Speichert...') : t('adrs.supersedeConfirm', 'Supersede bestätigen')}
                    </button>
                    <button
                      type="button"
                      data-testid="adr-supersede-cancel-btn"
                      className="btn-secondary"
                      onClick={closeSupersede}
                      disabled={isSuperseding}
                    >
                      {t('actions.cancel', 'Abbrechen')}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 12.11: workspace-defined custom fields, typed and persisted per
              artifact instance. Only shown for an existing ADR that already
              has a backing Artifact id — see the `artifact_id` comment on
              the `Adr` type for why this is currently always empty. */}
          {adr.artifact_id && (
            <ArtifactCustomFields artifactId={adr.artifact_id} />
          )}

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
