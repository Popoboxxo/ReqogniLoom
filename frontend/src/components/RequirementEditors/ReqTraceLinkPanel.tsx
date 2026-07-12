/**
 * REQ-L2-RF-006: ReqTraceLinkPanel Component
 *
 * Standalone panel for managing TraceLinks for a single requirement:
 * - Create TraceLink (to other Requirements, TestCases, ArchitectureElements)
 * - List existing TraceLinks
 * - Delete TraceLinks
 * - Derive new Requirements from ArchitectureElements
 *
 * leaf_id: COMP-RF-003-ReqTraceLinkPanel
 * req_id: REQ-L2-RF-006
 *
 * Interfaces implemented:
 * IF-RF-INT-002 ← I18nService via useTranslation
 * IF-RF-EXT-OUT-001 → GET/POST/DELETE /api/v1/tracelinks/
 * IF-RF-EXT-OUT-002 → GET/POST /api/v1/requirements/derive/
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { requirementsApi } from '../../api/requirements';
import { tracelinksApi } from '../../api/tracelinks';
import { testcasesApi } from '../../api/testcases';
import { architectureApi } from '../../api/architecture';
import { DeriveRequirementForm } from '../shared/DeriveRequirementForm';
import { ALL_LINK_TYPES, getLinkTypeLabel } from '../../constants/traceLinkLabels';
import type {
  Requirement,
  TraceLink,
  LinkType,
  UUID,
  TestCase,
  ArchitectureElement,
} from '../../types';

const inputStyle: React.CSSProperties = {
  width: '100%',
  fontSize: 'var(--font-size-base)',
  padding: 'var(--space-2) var(--space-3)',
  marginBottom: 'var(--space-2)',
  boxSizing: 'border-box',
  background: 'var(--color-surface)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-text)',
  fontFamily: 'var(--font-sans)',
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: 'block',
  marginBottom: 'var(--space-1)',
  color: 'var(--color-text)',
  fontSize: 'var(--font-size-sm)',
};

interface ReqTraceLinkPanelProps {
  workspaceId: UUID;
  requirementId: UUID;
  requirements: Requirement[];
  onLinksChanged: () => void;
}

/**
 * ReqTraceLinkPanel — Standalone panel for requirement TraceLink management.
 */
export const ReqTraceLinkPanel: React.FC<ReqTraceLinkPanelProps> = ({
  workspaceId,
  requirementId,
  requirements,
  onLinksChanged,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState<boolean>(false);
  const [targetId, setTargetId] = useState<string>('');
  const [linkType, setLinkType] = useState<LinkType>('derives-from');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [architectureElements, setArchitectureElements] = useState<ArchitectureElement[]>([]);
  const [showDeriveForm, setShowDeriveForm] = useState<boolean>(false);
  const [deriveTitle, setDeriveTitle] = useState<string>('');
  const [deriveArchitectureElementId, setDeriveArchitectureElementId] = useState<string>('');
  const [isDeriving, setIsDeriving] = useState<boolean>(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);

  // Load TraceLinks
  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    async function load(): Promise<void> {
      try {
        const resp = await tracelinksApi.listForArtifact(workspaceId, requirementId);
        if (cancelled) return;
        setLinks(resp.results);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ?? String(err);
        setError(msg);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, requirementId, reloadKey]);

  // Load TestCases
  useEffect(() => {
    let cancelled = false;
    testcasesApi
      .list(workspaceId)
      .then((resp) => {
        if (!cancelled) setTestCases(resp.results);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ?? String(err);
         
        console.warn('Failed to load TestCases for trace-link target list:', msg);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  // Load ArchitectureElements
  useEffect(() => {
    let cancelled = false;
    architectureApi
      .list(workspaceId)
      .then((resp) => {
        if (!cancelled) setArchitectureElements(resp.results);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ?? String(err);
         
        console.warn('Failed to load ArchitectureElements for trace-link target list:', msg);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const requirementsById = React.useMemo(() => {
    const m: Record<UUID, Requirement> = {};
    for (const r of requirements) m[r.id] = r;
    return m;
  }, [requirements]);

  const testCasesById = React.useMemo(() => {
    const m: Record<UUID, TestCase> = {};
    for (const tc of testCases) m[tc.id] = tc;
    return m;
  }, [testCases]);

  const architectureElementsById = React.useMemo(() => {
    const m: Record<UUID, ArchitectureElement> = {};
    for (const ae of architectureElements) m[ae.id] = ae;
    return m;
  }, [architectureElements]);

  const otherRequirements = requirements.filter((r) => r.id !== requirementId);

  const openForm = (): void => {
    setTargetId('');
    setLinkType('derives-from');
    setSubmitError(null);
    setShowForm(true);
  };

  const cancelForm = (): void => {
    setShowForm(false);
    setSubmitError(null);
  };

  const submitForm = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    if (!targetId) {
      setSubmitError(t('traceability.targetRequired'));
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await tracelinksApi.create({
        source_id: requirementId,
        target_id: targetId,
        link_type: linkType,
      });
      setShowForm(false);
      setTargetId('');
      setReloadKey((k) => k + 1);
      onLinksChanged();
    } catch (err: unknown) {
      const apiErr = err as {
        error?: {
          message?: string;
          details?: { field?: string; errors?: string[] }[];
        };
      };
      const baseMsg = apiErr?.error?.message;
      const firstDetail = apiErr?.error?.details?.[0];
      const detailMsg = firstDetail
        ? `${firstDetail.field ?? ''}: ${(firstDetail.errors ?? []).join(', ')}`
        : '';
      const msg = baseMsg ? (detailMsg ? `${baseMsg} — ${detailMsg}` : baseMsg) : String(err);
      setSubmitError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (linkId: UUID): Promise<void> => {
    try {
      await tracelinksApi.delete(linkId);
      setReloadKey((k) => k + 1);
      onLinksChanged();
    } catch (err: unknown) {
      console.error('Delete tracelink failed:', err);
    }
  };

  const openDeriveForm = (): void => {
    setDeriveTitle('');
    setDeriveArchitectureElementId('');
    setDeriveError(null);
    setShowDeriveForm(true);
  };

  const cancelDeriveForm = (): void => {
    setShowDeriveForm(false);
    setDeriveError(null);
  };

  const submitDerive = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    if (!deriveTitle.trim()) {
      setDeriveError(t('traceability.deriveTitleRequired'));
      return;
    }
    if (!deriveArchitectureElementId) {
      setDeriveError(t('traceability.deriveArchitectureElementRequired'));
      return;
    }
    setIsDeriving(true);
    setDeriveError(null);
    try {
      const { requirement: created } = await requirementsApi.derive(requirementId, {
        title: deriveTitle.trim(),
        architecture_element_id: deriveArchitectureElementId,
      });
      setShowDeriveForm(false);
      setDeriveTitle('');
      setDeriveArchitectureElementId('');
      onLinksChanged();
      navigate(`/requirements/${created.id}`);
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      setDeriveError(apiErr?.error?.message ?? String(err));
    } finally {
      setIsDeriving(false);
    }
  };

  return (
    <div
      data-testid="req-tracelink-panel"
      style={{
        marginTop: 'var(--space-6)',
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-card)',
        padding: 'var(--space-4)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 'var(--space-3)',
        }}
      >
        <h4
          style={{
            margin: 0,
            fontSize: 'var(--font-size-base)',
            fontWeight: 700,
            color: 'var(--color-text)',
          }}
        >
          {t('arch.tracelinkPanelTitle')}
        </h4>
        {!showForm && !showDeriveForm && (
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <button
              type="button"
              data-testid="req-tracelink-create-btn"
              className="btn-primary"
              onClick={openForm}
            >
              {t('traceability.create')}
            </button>
            <button
              type="button"
              data-testid="req-tracelink-viewall-btn"
              className="btn-secondary"
              onClick={() => navigate('/traceability')}
              title={t('nav.traceability')}
            >
              {t('traceability.viewAll')}
            </button>
          </div>
        )}
      </div>

      {showForm && (
        <form onSubmit={(e) => void submitForm(e)} style={{ marginBottom: 'var(--space-4)' }}>
          <label style={labelStyle}>{t('traceability.target')}</label>
          <select
            data-testid="req-tracelink-target-select"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            disabled={isSubmitting}
            style={inputStyle}
          >
            {otherRequirements.length === 0 &&
            testCases.length === 0 &&
            architectureElements.length === 0 ? (
              <option>{t('traceability.noArtifacts')}</option>
            ) : null}
            {otherRequirements.length > 0 && (
              <optgroup label={t('traceability.requirementsGroup')}>
                {otherRequirements.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title || t('editor.untitled')}
                  </option>
                ))}
              </optgroup>
            )}
            {testCases.length > 0 && (
              <optgroup label={t('traceability.testCasesGroup')}>
                {testCases.map((tc) => (
                  <option key={tc.id} value={tc.id}>
                    {tc.title || t('editor.untitled')}
                  </option>
                ))}
              </optgroup>
            )}
            {architectureElements.length > 0 && (
              <optgroup label={t('traceability.architectureGroup')}>
                {architectureElements.map((ae) => (
                  <option key={ae.id} value={ae.id}>
                    {ae.title || t('editor.untitled')}
                  </option>
                ))}
              </optgroup>
            )}
          </select>

          <label style={labelStyle}>{t('traceability.linkType')}</label>
          <select
            data-testid="req-tracelink-type-select"
            value={linkType}
            onChange={(e) => setLinkType(e.target.value as LinkType)}
            disabled={isSubmitting}
            style={inputStyle}
          >
            {ALL_LINK_TYPES.map((lt) => (
              <option key={lt} value={lt}>
                {getLinkTypeLabel(lt)}
              </option>
            ))}
          </select>

          {submitError && (
            <p
              role="alert"
              style={{
                color: 'var(--color-danger)',
                fontSize: 'var(--font-size-sm)',
                margin: 0,
              }}
            >
              {submitError}
            </p>
          )}

          <div
            style={{
              display: 'flex',
              gap: 'var(--space-2)',
              justifyContent: 'flex-end',
            }}
          >
            <button
              type="button"
              data-testid="req-tracelink-cancel-btn"
              className="btn-secondary"
              onClick={cancelForm}
              disabled={isSubmitting}
            >
              {t('actions.cancel')}
            </button>
            <button
              type="submit"
              data-testid="req-tracelink-submit-btn"
              className="btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? t('traceability.submitting') : t('traceability.submit')}
            </button>
          </div>
        </form>
      )}

      {isLoading && (
        <p
          role="status"
          style={{
            color: 'var(--color-text-muted)',
            fontSize: 'var(--font-size-sm)',
            margin: 0,
          }}
        >
          {t('loading')}
        </p>
      )}

      {error && !isLoading && (
        <p
          role="alert"
          style={{
            color: 'var(--color-danger)',
            fontSize: 'var(--font-size-sm)',
            margin: 0,
          }}
        >
          {error}
        </p>
      )}

      {!isLoading && !error && links.length === 0 && (
        <p
          style={{
            fontSize: 'var(--font-size-sm)',
            color: 'var(--color-text-muted)',
            margin: 0,
          }}
        >
          {t('traceability.none')}
        </p>
      )}

      {links.length > 0 && (
        <ul
          data-testid="req-tracelink-list"
          style={{ margin: '0', padding: '0' }}
        >
          {links.map((link) => {
            // REQ-002: prefer backend-supplied target_title; fall back to local
            // lookup (loaded requirements/architectureElements/testCases) and
            // finally to the truncated UUID prefix.
            const backendTitle =
              link.target_id === requirementId
                ? link.source_title
                : link.target_title;
            const localTitle =
              requirementsById[link.target_id]?.title ||
              architectureElementsById[link.target_id]?.title ||
              testCasesById[link.target_id]?.title ||
              requirementsById[link.source_id]?.title ||
              architectureElementsById[link.source_id]?.title ||
              testCasesById[link.source_id]?.title;
            const otherId =
              link.target_id === requirementId ? link.source_id : link.target_id;
            const displayTitle =
              (backendTitle && backendTitle.length > 0 ? backendTitle : null) ??
              localTitle ??
              otherId.slice(0, 8);

            return (
              <li
                key={link.id}
                data-testid="req-tracelink-item"
                style={{
                  padding: 'var(--space-2) var(--space-3)',
                  marginBottom: 'var(--space-2)',
                  background: 'var(--color-surface-raised)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 'var(--font-size-sm)',
                  color: 'var(--color-text)',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                <span
                  style={{
                    background: 'var(--color-badge-draft)',
                    color: 'var(--color-badge-draft-text)',
                    padding: '2px 6px',
                    borderRadius: 'var(--radius-full)',
                    fontSize: 'var(--font-size-sm)',
                    marginRight: 'var(--space-2)',
                  }}
                >
                  {getLinkTypeLabel(link.link_type)}
                </span>
                <span data-testid="req-tracelink-title">{displayTitle}</span>
                <button
                  data-testid="req-tracelink-delete-btn"
                  onClick={() => void handleDelete(link.id)}
                  style={{
                    marginLeft: 'auto',
                    background: 'none',
                    border: 'none',
                    color: 'var(--color-danger)',
                    cursor: 'pointer',
                    fontSize: 'var(--font-size-sm)',
                    fontWeight: 600,
                  }}
                  title={t('actions.delete')}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {/* Derive a new Requirement from this one, allocated to an architecture
          element — same trigger/form shell as Needs and Architecture. */}
      <div style={{ marginTop: 'var(--space-4)' }}>
        <DeriveRequirementForm
          isOpen={showDeriveForm}
          onOpen={openDeriveForm}
          onCancel={cancelDeriveForm}
          onSubmit={(e) => void submitDerive(e)}
          title={deriveTitle}
          onTitleChange={setDeriveTitle}
          architectureElements={architectureElements}
          architectureElementId={deriveArchitectureElementId}
          onArchitectureElementChange={setDeriveArchitectureElementId}
          architectureRequired
          isSubmitting={isDeriving}
          error={deriveError}
          testIdPrefix="req"
        />
      </div>
    </div>
  );
};

ReqTraceLinkPanel.displayName = 'ReqTraceLinkPanel';
