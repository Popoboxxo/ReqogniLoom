/**
 * ADR-Supersede-Flow (REQ-L3-ADR-005, UI-32 Systemaudit 2026-08-27 AP-5).
 *
 * Extracted from the deleted `AdrForm.tsx` as-is (Task 21, ADR rollout wave).
 * `ArtifactForm` (spec section 6) has no concept of an ADR-specific lifecycle
 * action like "supersede" — it only knows generic save/delete/workflow-status
 * transitions — so this capability does not fit inside the definition-driven
 * renderer and stays a standalone sibling component instead of being dropped.
 * `AdrArtifactForm`'s parity policy comment ("never cuts one") is why this
 * file exists rather than being deleted along with `AdrForm.tsx`.
 */
import { useEffect, useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useWorkspace } from '../../context/WorkspaceContext';
import type { Adr, TraceLink } from '../../types';
import { adrsApi } from '../../api/adrs';
import { tracelinksApi } from '../../api/tracelinks';

// UI-32: hoisted named style constants (ui-ratchet.test.ts style-brace ceiling).
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
const selectStyle: React.CSSProperties = {
  width: '100%', border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
  padding: 'var(--space-3)', fontFamily: 'var(--font-sans)', fontSize: 'var(--font-size-base)',
  marginBottom: 'var(--space-4)', color: 'var(--color-text)', background: 'var(--color-surface)',
  boxSizing: 'border-box',
};
const labelStyle: React.CSSProperties = {
  fontWeight: 500, color: 'var(--color-text)', display: 'block', marginBottom: 'var(--space-1)',
};
// F-4 (code review, Task 21 fix round): the old AdrForm rendered this panel
// inside its own Card; as a standalone sibling it otherwise sits directly on
// the page background with no separation from AdrArtifactForm above it.
const supersedeWrapperStyle: React.CSSProperties = {
  marginTop: 'var(--space-4)',
};

interface AdrSupersedePanelProps {
  adr: Adr;
  /** The other ADRs in the same workspace, offered as candidate successors. */
  otherAdrs: Adr[];
  /**
   * Forwards the mutation's own response so the caller can write it into its
   * cache/state synchronously instead of only invalidating and waiting for a
   * refetch — see `useAdrData.refresh`'s doc comment.
   */
  onSaved: (updated: Adr) => void;
}

export function AdrSupersedePanel({ adr, otherAdrs, onSaved }: AdrSupersedePanelProps): JSX.Element | null {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();

  const [supersedeOpen, setSupersedeOpen] = useState(false);
  const [supersedeTargetId, setSupersedeTargetId] = useState('');
  const [supersedeReason, setSupersedeReason] = useState('');
  const [isSuperseding, setIsSuperseding] = useState(false);
  const [supersedeError, setSupersedeError] = useState<string | null>(null);
  const [supersededByLink, setSupersededByLink] = useState<TraceLink | null>(null);

  useEffect(() => {
    setSupersedeOpen(false);
    setSupersedeTargetId('');
    setSupersedeReason('');
    setSupersedeError(null);
  }, [adr.id]);

  // UI-32: resolve "Abgelöst durch: [ADR-XXX]" from the `decides` TraceLink
  // `AdrService.transition_status` creates (source=successor, target=this
  // ADR) — there is no dedicated `superseded_by` column on Adr, the
  // TraceLink graph is the single source of truth (REQ-L3-ADR-005).
  useEffect(() => {
    let cancelled = false;
    if (adr.status !== 'Superseded' || !activeWorkspace) {
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

  const candidateSuccessors = otherAdrs.filter((other) => other.id !== adr.id);

  // Fix (systemaudit 2026-08-29, Bug 4): the only workflow transition into
  // 'Superseded' is 'Approved' -> 'Superseded' (backend/workflow/
  // definition_store.py::_adr_transitions — adr_default is currently the
  // only ADR workflow definition).
  const canSupersede = adr.status === 'Approved';

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
    if (!supersedeTargetId) return;
    setIsSuperseding(true);
    setSupersedeError(null);
    try {
      const updated = await adrsApi.supersede(adr.id, supersedeTargetId, supersedeReason.trim());
      setSupersedeOpen(false);
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

  if (adr.status === 'Superseded') {
    return supersededByLink ? (
      <p data-testid="adr-superseded-by" style={supersededByTextStyle}>
        {t('adrs.supersededBy', {
          title: supersededByLink.source_title || supersededByLink.source_id.slice(0, 8),
          defaultValue: 'Abgelöst durch: {{title}}',
        })}
      </p>
    ) : null;
  }

  return (
    <div style={supersedeWrapperStyle}>
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
            style={selectStyle}
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
  );
}
