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
// UI-39: numeric mapping mirrors Risk._PROB_NUMERIC / _IMPACT_NUMERIC in
// backend/application/models.py — needed client-side to render the
// probability x impact matrix and preview the score before saving.
const LEVEL_NUMERIC: Record<string, number> = { low: 1, medium: 2, high: 3 };

/** UI-39: same low/medium/high score banding backend Risk.severity derives from. */
function scoreBand(score: number): 'low' | 'medium' | 'high' {
  if (score >= 9) return 'high';
  if (score >= 4) return 'medium';
  return 'low';
}

const SCORE_BAND_COLORS: Record<'low' | 'medium' | 'high', { fg: string; bg: string }> = {
  low: { fg: 'var(--color-success)', bg: 'rgba(var(--color-success-rgb), 0.14)' },
  medium: { fg: 'var(--color-warning)', bg: 'rgba(var(--color-warning-rgb), 0.16)' },
  high: { fg: 'var(--color-danger)', bg: 'rgba(var(--color-danger-rgb), 0.16)' },
};

// UI-39: named style objects for the risk-matrix section, hoisted to module
// scope (F6, Systemaudit 2026-08-27 AP-5 review) since none depend on
// component state/props — a per-render re-allocation was pure waste. Mirrors
// `AiPromptsSection.tsx`'s hoisted-style-constant precedent. `matrixLabelStyle`
// duplicates `labelStyle`'s values instead of spreading it, since `labelStyle`
// itself stays component-local (pre-existing, out of this fix's scope).
const matrixLabelStyle: React.CSSProperties = {
  fontWeight: 500, color: 'var(--color-text)', display: 'block', marginBottom: 'var(--space-2)',
};
const matrixSectionStyle: React.CSSProperties = {
  display: 'flex', gap: 'var(--space-6)', alignItems: 'flex-start', flexWrap: 'wrap',
  marginBottom: 'var(--space-2)', padding: 'var(--space-3)',
  background: 'var(--color-surface-raised)', borderRadius: 'var(--radius-md)',
};
const matrixTableStyle: React.CSSProperties = { borderCollapse: 'collapse' };
const matrixProbabilityAxisStyle: React.CSSProperties = {
  display: 'flex', justifyContent: 'space-between', fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-muted)', marginTop: 'var(--space-1)', width: 'fit-content', minWidth: '100%',
};
const scoreDisplayStyle: React.CSSProperties = { fontSize: 'var(--font-size-sm)', color: 'var(--color-text)' };
const rpnHintStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)', color: 'var(--color-text-muted)', marginTop: 'var(--space-1)', maxWidth: 220,
};
const flexOneStyle: React.CSSProperties = { flex: 1 };
const matrixCellStyle = (colors: { fg: string; bg: string }, isCurrent: boolean): React.CSSProperties => ({
  width: 40, height: 32, textAlign: 'center', verticalAlign: 'middle',
  fontSize: 'var(--font-size-xs)', fontWeight: isCurrent ? 700 : 500,
  color: colors.fg, background: colors.bg,
  border: isCurrent ? `2px solid ${colors.fg}` : '1px solid var(--color-border)',
});

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
    for (const key of ['title', 'description', 'severity', 'probability', 'impact', 'detection', 'category', 'owner', 'mitigation_strategy'] as const) {
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
            <button data-testid="risk-save-btn" onClick={handleSave} className="btn-primary" disabled={isSaving}>
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
            <label htmlFor="risk-title" style={labelStyle}>{t('editor.title')} <span style={{ color: 'var(--color-danger)' }}>*</span></label>
            <input id="risk-title" type="text" value={formData.title || ''} onChange={(e) => handleChange('title', e.target.value)} style={inputStyle} aria-required="true" />
          </div>
          <div>
            <label htmlFor="risk-description" style={labelStyle}>{t('editor.description')}</label>
            <textarea id="risk-description" value={formData.description || ''} onChange={(e) => handleChange('description', e.target.value)} rows={4} style={inputStyle} />
          </div>
          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div style={{ flex: 1 }}>
              <label htmlFor="risk-severity" style={labelStyle}>{t('risks.severity')}</label>
              <select id="risk-severity" value={formData.severity || 'medium'} onChange={(e) => handleChange('severity', e.target.value as RiskSeverity)} style={inputStyle}>
                {SEVERITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="risk-probability" style={labelStyle}>{t('risks.probability')}</label>
              <select id="risk-probability" value={formData.probability || 'medium'} onChange={(e) => handleChange('probability', e.target.value as RiskProbability)} style={inputStyle}>
                {PROBABILITY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="risk-impact" style={labelStyle}>{t('risks.impact')}</label>
              <select id="risk-impact" value={formData.impact || 'medium'} onChange={(e) => handleChange('impact', e.target.value as RiskImpact)} style={inputStyle}>
                {IMPACT_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div style={flexOneStyle}>
              {/* UI-39: FMEA detectability score (1=easy .. 10=impossible),
                  feeds the Risk Priority Number alongside probability x impact.
                  Backend field existed (RiskSerializer.detection) with no
                  editor exposing it. */}
              <label htmlFor="risk-detection" style={labelStyle}>
                {t('risks.detection', 'Detection (1-10)')}
              </label>
              <input
                id="risk-detection"
                data-testid="risk-detection-input"
                type="number"
                min={1}
                max={10}
                step={1}
                value={formData.detection ?? 5}
                onChange={(e) => {
                  const parsed = Number(e.target.value);
                  const clamped = Number.isFinite(parsed)
                    ? Math.min(10, Math.max(1, Math.round(parsed)))
                    : 5;
                  handleChange('detection', clamped);
                }}
                style={inputStyle}
              />
            </div>
          </div>

          {/* UI-39: risk_score was computed by the backend but never surfaced
              in the UI; the probability x impact matrix gives at-a-glance
              context for where this risk sits (no library, plain CSS grid). */}
          <div
            data-testid="risk-matrix-section"
            style={matrixSectionStyle}
          >
            <div>
              <div style={matrixLabelStyle}>
                {t('risks.matrixTitle', 'Risk Matrix (Probability × Impact)')}
              </div>
              <table
                data-testid="risk-matrix"
                style={matrixTableStyle}
                aria-label={t('risks.matrixTitle', 'Risk Matrix (Probability × Impact)')}
              >
                <tbody>
                  {[...IMPACT_OPTIONS].reverse().map((impactLevel) => (
                    <tr key={impactLevel}>
                      {PROBABILITY_OPTIONS.map((probLevel) => {
                        const cellScore = LEVEL_NUMERIC[impactLevel] * LEVEL_NUMERIC[probLevel];
                        const band = scoreBand(cellScore);
                        const colors = SCORE_BAND_COLORS[band];
                        const isCurrent =
                          (formData.probability || 'medium') === probLevel &&
                          (formData.impact || 'medium') === impactLevel;
                        return (
                          <td
                            key={`${impactLevel}-${probLevel}`}
                            data-testid={`risk-matrix-cell-${impactLevel}-${probLevel}`}
                            title={`${t('risks.impact')}: ${impactLevel} · ${t('risks.probability')}: ${probLevel} · ${t('risks.score', 'Score')}: ${cellScore}`}
                            style={matrixCellStyle(colors, isCurrent)}
                          >
                            {cellScore}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={matrixProbabilityAxisStyle}>
                <span>{t('risks.probability')} →</span>
              </div>
            </div>
            <div>
              <div style={matrixLabelStyle}>
                {t('risks.computedScores', 'Computed Scores')}
              </div>
              <div data-testid="risk-score-display" style={scoreDisplayStyle}>
                {t('risks.riskScoreLabel', 'Risk Score')}: <strong>{risk.risk_score ?? '—'}</strong>
              </div>
              <div data-testid="risk-rpn-display" style={scoreDisplayStyle}>
                {t('risks.rpnLabel', 'RPN (FMEA)')}: <strong>{risk.rpn ?? '—'}</strong>
              </div>
              <p style={rpnHintStyle}>
                {t(
                  'risks.rpnHint',
                  'Risk Score = Probability × Impact. RPN = Probability × Impact × Detection. Recalculated on save.'
                )}
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-4)' }}>
            <div role="group" aria-labelledby="risk-status-label" style={{ flex: 1 }}>
              <span id="risk-status-label" style={labelStyle}>{t('editor.status')}</span>
              {/* REQ-165: WorkflowEngine-driven status editor (replaces the
                  hardcoded status select). role="group" + aria-labelledby
                  because WorkflowStatusEditor renders a group of transition
                  buttons, not a single form control. */}
              <WorkflowStatusEditor
                artifactType="risk"
                artifactId={risk.id}
                currentStatus={risk.status}
                disabled={isSaving}
                onTransitionComplete={onSaved}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label htmlFor="risk-category" style={labelStyle}>{t('risks.category')}</label>
              <select id="risk-category" value={formData.category || 'technical'} onChange={(e) => handleChange('category', e.target.value as RiskCategory)} style={inputStyle}>
                {CATEGORY_OPTIONS.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>
          {/* UI-10 (system audit P4): close only when focus leaves the whole
              field (input + dropdown), not when it moves from the input to a
              suggestion — a plain setTimeout would close the list out from
              under a keyboard user tabbing into it. The wrapper itself is not
              an interactive element; it only observes focus leaving its
              subtree (the input and the listbox remain the actual widgets). */}
          {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
          <div
            style={{ position: 'relative' }}
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
                setOwnerDropdownOpen(false);
              }
            }}
          >
            <label htmlFor="risk-owner" style={labelStyle}>{t('risks.owner')}</label>
            <input
              id="risk-owner"
              type="text"
              value={formData.owner || ''}
              onChange={(e) => handleChange('owner', e.target.value)}
              onFocus={() => {
                if ((formData.owner || '').length > 0 && ownerSuggestions.length > 0) {
                  setOwnerDropdownOpen(true);
                }
              }}
              role="combobox"
              aria-expanded={ownerDropdownOpen && ownerSuggestions.length > 0}
              aria-controls="risk-owner-dropdown"
              aria-autocomplete="list"
              style={inputStyle}
              data-testid="risk-owner-input"
            />
            {ownerDropdownOpen && ownerSuggestions.length > 0 && (
              <div
                id="risk-owner-dropdown"
                role="listbox"
                aria-label={t('risks.owner')}
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
                    role="option"
                    aria-selected={suggestion === formData.owner}
                    tabIndex={0}
                    onClick={() => handleOwnerSuggestionClick(suggestion)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleOwnerSuggestionClick(suggestion);
                      }
                    }}
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
            <label htmlFor="risk-mitigation-strategy" style={labelStyle}>{t('risks.mitigationStrategy')}</label>
            <textarea id="risk-mitigation-strategy" value={formData.mitigation_strategy || ''} onChange={(e) => handleChange('mitigation_strategy', e.target.value)} rows={3} style={inputStyle} />
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
