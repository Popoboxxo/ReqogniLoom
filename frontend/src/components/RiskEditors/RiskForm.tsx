import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useWorkspace } from '../../context/WorkspaceContext';
import type { Risk, RiskSeverity, RiskProbability, RiskImpact, RiskCategory } from '../../types';
import { risksApi } from '../../api/risks';
import { VersionBadge } from '../shared/VersionBadge';
import { StatusBadge } from '../shared/StatusBadge';
import { getWorkflowStatusLabel } from '../../utils/workflowStatus';
import { ArtifactId } from '../shared/ArtifactId';
import { ArtifactCustomFields } from '../shared/ArtifactCustomFields';
import { WorkflowStatusEditor } from '../WorkflowStatusEditor';

interface RiskFormProps {
  risk: Risk | null;
  onSaved: () => void;
  onDeleted: () => void;
}

const SEVERITY_OPTIONS = ['low', 'medium', 'high'];
const PROBABILITY_OPTIONS = ['low', 'medium', 'high'];
const IMPACT_OPTIONS = ['low', 'medium', 'high'];
// BUG-11 (Systemaudit 2026-08-18, §4): exported so RiskEditors' create
// dialog can offer the same category choices as this edit form, instead of
// duplicating the literal list.
export const CATEGORY_OPTIONS = ['technical', 'operational', 'organizational', 'business'];

export function RiskForm({ risk, onSaved, onDeleted }: RiskFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  // REQ-162: Extended preset captures a change_reason on every update
  // (forwarded to the backend audit log).
  const isExtendedPreset = activeWorkspace?.preset === 'extended';
  const [formData, setFormData] = useState<Partial<Risk>>({});
  const [changeReason, setChangeReason] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [allOwners, setAllOwners] = useState<string[]>([]);
  const [ownerSuggestions, setOwnerSuggestions] = useState<string[]>([]);
  const [ownerDropdownOpen, setOwnerDropdownOpen] = useState(false);

  useEffect(() => {
    if (risk) setFormData({ ...risk });
    else setFormData({});
    // Reset transient action state when switching to a different risk.
    setChangeReason('');
    setConfirmDelete(false);
    setSaveError(null);
    setDeleteError(null);
  }, [risk]);

  // Load all risks and extract unique owner values for autocomplete
  useEffect(() => {
    if (!risk?.workspace_id) return;
    const loadOwners = async () => {
      try {
        const response = await risksApi.list(risk.workspace_id);
        const risks = Array.isArray(response) ? response : response.results || [];
        const owners = Array.from(
          new Set(
            risks
              .map((r: Risk) => r.owner)
              .filter((owner: string | null | undefined): owner is string => Boolean(owner))
          )
        ).sort();
        setAllOwners(owners);
      } catch (err) {
        console.error('Failed to load owners for autocomplete:', err);
      }
    };
    loadOwners();
  }, [risk?.workspace_id]);

  const handleChange = <K extends keyof Risk>(field: K, value: Risk[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (saveError) setSaveError(null);
    if (deleteError) setDeleteError(null);
    // Update owner suggestions when owner field changes
    if (field === 'owner' && typeof value === 'string') {
      if (value.length > 0) {
        const filtered = allOwners.filter((owner) =>
          owner.toLowerCase().includes(value.toLowerCase())
        );
        setOwnerSuggestions(filtered);
        setOwnerDropdownOpen(filtered.length > 0);
      } else {
        setOwnerSuggestions([]);
        setOwnerDropdownOpen(false);
      }
    }
  };

  const handleOwnerSuggestionClick = (suggestion: string) => {
    handleChange('owner', suggestion);
    setOwnerDropdownOpen(false);
  };

  const saveFields = () => {
    if (!risk) return {};
    const fields: Partial<Record<keyof Risk, unknown>> = {};
    // #263: `status` is deliberately absent. It is a read-only WorkflowEngine
    // mirror; lifecycle changes run through POST .../transitions/.
    for (const key of ['title', 'description', 'severity', 'probability', 'impact', 'category', 'owner', 'mitigation_strategy'] as const) {
      if (key in formData) fields[key] = formData[key];
    }
    return fields;
  };

  const handleSave = async () => {
    if (!risk) return;
    // REQ-162: Extended preset requires a change_reason before saving.
    if (isExtendedPreset && !changeReason.trim()) {
      setSaveError(t('req.changeReasonRequired'));
      return;
    }
    setIsSaving(true);
    setSaveError(null);
    try {
      await risksApi.update(risk.id, {
        ...saveFields(),
        ...(isExtendedPreset ? { change_reason: changeReason.trim() } : {}),
      } as Partial<Risk> & { change_reason?: string });
      onSaved();
    } catch (err) {
      console.error(err);
      const msg = (err as { error?: { message?: string } })?.error?.message ?? t('risks.saveFailed');
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!risk) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await risksApi.delete(risk.id);
      onDeleted();
    } catch (err) {
      console.error(err);
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        t('risks.deleteFailed', 'Löschen fehlgeschlagen. Bitte erneut versuchen.');
      setDeleteError(msg);
      setConfirmDelete(false);
    } finally {
      setIsDeleting(false);
    }
  };

  if (!risk) {
    return (
      <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-lg)', textAlign: 'center', padding: 'var(--space-8)' }}>
        {t('risks.selectRisk')}
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
            <StatusBadge status={risk.status} label={getWorkflowStatusLabel(risk.status)} />
            {risk.version && <VersionBadge version={risk.version} />}
            <ArtifactId value={risk.uid} fallback={risk.id.slice(0, 8)} testId="risk-id" />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
            {!confirmDelete ? (
              <button data-testid="risk-delete-btn" onClick={() => setConfirmDelete(true)} className="btn-danger">
                {t('actions.delete')}
              </button>
            ) : (
              <>
                <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                  {t('actions.deleteConfirmPrompt', 'Löschen?')}
                </span>
                <button data-testid="risk-confirm-delete-btn" onClick={handleDelete} className="btn-danger" disabled={isDeleting}>
                  {isDeleting ? t('actions.deleting', 'Löschen...') : t('actions.confirmDelete', 'Ja, löschen')}
                </button>
                <button data-testid="risk-cancel-delete-btn" onClick={() => setConfirmDelete(false)} className="btn-ghost" disabled={isDeleting}>
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
            <input type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} style={inputStyle} aria-required="true" />
          </div>
          <div>
            <label style={labelStyle}>{t('editor.description')}</label>
            <textarea value={formData.description || ''} onChange={(e) => handleChange('description', e.target.value)} rows={4} style={inputStyle} />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('risks.severity')}</label>
              <select value={formData.severity || 'medium'} onChange={(e) => handleChange('severity', e.target.value as RiskSeverity)} style={inputStyle}>
                {SEVERITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('risks.probability')}</label>
              <select value={formData.probability || 'medium'} onChange={(e) => handleChange('probability', e.target.value as RiskProbability)} style={inputStyle}>
                {PROBABILITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('risks.impact')}</label>
              <select value={formData.impact || 'medium'} onChange={(e) => handleChange('impact', e.target.value as RiskImpact)} style={inputStyle}>
                {IMPACT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('editor.status')}</label>
              {/* REQ-165: WorkflowEngine-driven status editor (replaces the
                  hardcoded status select). */}
              <WorkflowStatusEditor
                artifactType="risk"
                artifactId={risk.id}
                currentStatus={risk.status}
                disabled={isSaving}
                onTransitionComplete={onSaved}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>{t('risks.category')}</label>
              <select value={formData.category || 'technical'} onChange={(e) => handleChange('category', e.target.value as RiskCategory)} style={inputStyle}>
                {CATEGORY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>
          <div style={{ position: 'relative' }}>
            <label style={labelStyle}>{t('risks.owner')}</label>
            <input
              type="text"
              value={formData.owner || ''}
              onChange={(e) => handleChange('owner', e.target.value)}
              onFocus={() => {
                if ((formData.owner || '').length > 0 && ownerSuggestions.length > 0) {
                  setOwnerDropdownOpen(true);
                }
              }}
              onBlur={() => {
                // Delay closing dropdown to allow click on suggestion to register
                setTimeout(() => setOwnerDropdownOpen(false), 150);
              }}
              style={inputStyle}
              data-testid="risk-owner-input"
            />
            {ownerDropdownOpen && ownerSuggestions.length > 0 && (
              <div
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
                data-testid="risk-owner-dropdown"
              >
                {ownerSuggestions.map((suggestion) => (
                  <div
                    key={suggestion}
                    onClick={() => handleOwnerSuggestionClick(suggestion)}
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
                    data-testid={`risk-owner-suggestion-${suggestion}`}
                  >
                    {suggestion}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <label style={labelStyle}>{t('risks.mitigationStrategy')}</label>
            <textarea value={formData.mitigation_strategy || ''} onChange={(e) => handleChange('mitigation_strategy', e.target.value)} rows={3} style={inputStyle} />
          </div>

          {/* 12.11: workspace-defined custom fields, typed and persisted per
              artifact instance. Only shown for an existing risk that already
              has a backing Artifact id — see the `artifact_id` comment on
              the `Risk` type for why this is currently always empty. */}
          {risk.artifact_id && (
            <ArtifactCustomFields artifactId={risk.artifact_id} />
          )}

          {/* REQ-162: Change Control — Extended preset only. */}
          {isExtendedPreset && (
            <div>
              <label htmlFor="risk-change-reason" style={labelStyle}>
                {t('req.changeReason')} <span style={{ color: 'var(--color-danger)' }}>*</span>
              </label>
              <textarea
                id="risk-change-reason"
                data-testid="risk-change-reason-input"
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
