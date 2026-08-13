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
 *
 * Issue #416: every list in this panel picked "the other endpoint" with
 * `link.source_id === requirementId`. TraceLink endpoints are Artifact ids
 * while `requirementId` is a Requirement id, so the comparison never held and
 * every row resolved to the link's *source* — for an outgoing link that is the
 * current requirement itself. The "hierarchical view" made this most visible
 * because it also rendered the current requirement as its own tree root. The
 * panel now resolves endpoints through `utils/traceEndpoints` against both
 * ids, and the hierarchy block renders the actual parents and children.
 */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { requirementsApi } from '../../api/requirements';
import { tracelinksApi } from '../../api/tracelinks';
import { testcasesApi } from '../../api/testcases';
import { architectureApi } from '../../api/architecture';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import {
  formatShortId,
  hierarchyRelation,
  inferSelfArtifactId,
  neighborOf,
  type HierarchyRelation,
} from '../../utils/traceEndpoints';
import { DeriveRequirementForm } from '../shared/DeriveRequirementForm';
import { RequirementTreeNode, type HierarchyNode } from './RequirementTreeNode';
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

/** #416: sub-heading of a hierarchy direction group (hoisted — see ui-ratchet). */
const hierarchyGroupHeadingStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-text-muted)',
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: '0.03em',
  padding: 'var(--space-2) 0 var(--space-1)',
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
  /** REQ-008: optional AI-derive callback — when provided renders the ✨ Ableiten button */
  onAiDerive?: () => void;
  /** REQ-008: loading state for the AI-derive button */
  isAiDeriving?: boolean;
}

/**
 * ReqTraceLinkPanel — Standalone panel for requirement TraceLink management.
 */
export const ReqTraceLinkPanel: React.FC<ReqTraceLinkPanelProps> = ({
  workspaceId,
  requirementId,
  requirements,
  onLinksChanged,
  onAiDerive,
  isAiDeriving = false,
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

  const currentRequirement = React.useMemo(
    () => requirements.find((r) => r.id === requirementId),
    [requirements, requirementId]
  );

  /**
   * #416: every id this requirement can appear under in a TraceLink — its
   * Requirement id and its backing Artifact id (the one the API actually
   * uses). `inferSelfArtifactId` covers responses where `artifact_id` is not
   * available: the queried artifact is the endpoint shared by all links.
   */
  const selfIds = React.useMemo(() => {
    const ids = new Set<UUID>([requirementId]);
    if (currentRequirement?.artifact_id) {
      ids.add(currentRequirement.artifact_id);
      return ids;
    }
    // Only guess when the backing artifact id is genuinely unknown — adding a
    // wrong id would make *both* endpoints of a link look like "self" and the
    // neighbour would be dropped instead of rendered.
    const inferred = inferSelfArtifactId(links);
    if (inferred) ids.add(inferred);
    return ids;
  }, [requirementId, currentRequirement?.artifact_id, links]);

  /** #416: Artifact id -> entity id, so link rows route to a real editor. */
  const entityIdByArtifactId = React.useMemo(() => {
    const m: Record<UUID, UUID> = {};
    for (const r of requirements) if (r.artifact_id) m[r.artifact_id] = r.id;
    for (const ae of architectureElements) if (ae.artifact_id) m[ae.artifact_id] = ae.id;
    return m;
  }, [requirements, architectureElements]);

  /**
   * #416: the decomposition neighbourhood of *this* requirement — its parents
   * and children, never itself.
   */
  const hierarchyNodes = React.useMemo(() => {
    const nodes: HierarchyNode[] = [];
    const seen = new Set<UUID>();
    for (const link of links) {
      const hierarchy = hierarchyRelation(link, selfIds);
      if (!hierarchy) continue;
      const { relation, neighbor } = hierarchy;
      if (seen.has(neighbor.endpoint.id)) continue;
      seen.add(neighbor.endpoint.id);
      nodes.push({
        artifactId: neighbor.endpoint.id,
        entityId: entityIdByArtifactId[neighbor.endpoint.id],
        title: neighbor.endpoint.title,
        artifactType: neighbor.endpoint.artifactType,
        relation,
      });
    }
    return nodes;
  }, [links, selfIds, entityIdByArtifactId]);

  const hierarchyGroups: [HierarchyRelation, HierarchyNode[]][] = React.useMemo(() => {
    const parents = hierarchyNodes.filter((n) => n.relation === 'parent');
    const children = hierarchyNodes.filter((n) => n.relation === 'child');
    const groups: [HierarchyRelation, HierarchyNode[]][] = [];
    if (parents.length > 0) groups.push(['parent', parents]);
    if (children.length > 0) groups.push(['child', children]);
    return groups;
  }, [hierarchyNodes]);

  /**
   * Remaining links, partitioned by the artifact type on the far side. Every
   * link this requirement takes part in lands in exactly one of the three
   * blocks (hierarchy / architecture / other) — the old type-based section
   * conditions inspected *both* endpoint types, so e.g. a `TestCase verifies
   * Requirement` link matched neither the architecture nor the "other" filter
   * and was rendered nowhere.
   */
  const { archLinks, otherLinks } = React.useMemo(() => {
    const arch: TraceLink[] = [];
    const other: TraceLink[] = [];
    for (const link of links) {
      if (hierarchyRelation(link, selfIds)) continue; // rendered as a tree above
      const neighbor = neighborOf(link, selfIds);
      if (!neighbor) continue;
      if (neighbor.endpoint.artifactType === 'ArchitectureElement') arch.push(link);
      else other.push(link);
    }
    return { archLinks: arch, otherLinks: other };
  }, [links, selfIds]);

  /**
   * Resolve a link to its far endpoint plus display metadata (#416). Links
   * that touch neither id are dropped instead of silently rendering the
   * current artifact.
   */
  const resolveLinkRow = React.useCallback(
    (link: TraceLink) => {
      const neighbor = neighborOf(link, selfIds);
      if (!neighbor) return null;
      const { endpoint } = neighbor;
      const localTitle =
        architectureElementsById[endpoint.id]?.title ?? testCasesById[endpoint.id]?.title;
      const entityId = entityIdByArtifactId[endpoint.id] ?? endpoint.id;
      return {
        id: endpoint.id,
        artifactType: endpoint.artifactType,
        displayTitle: endpoint.title || localTitle || formatShortId(endpoint.id),
        route: getArtifactRoute(endpoint.artifactType || 'Requirement', entityId),
      };
    },
    [selfIds, architectureElementsById, testCasesById, entityIdByArtifactId]
  );

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
            {onAiDerive && (
              <button
                type="button"
                data-testid="req-ai-derive-btn"
                className="btn-primary"
                onClick={onAiDerive}
                disabled={isAiDeriving}
                style={{ background: 'linear-gradient(135deg, #4f6ef7, #8e2de2)' }}
              >
                ✨ {isAiDeriving ? t('actions.deriving', 'Leitet ab...') : t('actions.derive', 'Ableiten')}
              </button>
            )}
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
        <div data-testid="req-tracelink-sections">
          {/* #416: decomposition hierarchy — parents and children of the
              current requirement, grouped by direction. The current artifact
              is deliberately NOT rendered: it is the context, not a result. */}
          {hierarchyGroups.length > 0 && (
            <div
              data-testid="req-tracelink-requirements-section"
              style={{
                marginBottom: 'var(--space-6)',
                paddingBottom: 'var(--space-4)',
                borderBottom: '1px solid var(--color-border)',
              }}
            >
              <h5
                style={{
                  margin: '0 0 var(--space-2) 0',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 700,
                  color: 'var(--color-text)',
                }}
              >
                {t('traceability.requirementsGroup')} (hierarchical view)
              </h5>
              {hierarchyGroups.map(([relation, nodes]) => (
                <div key={relation} data-testid={`req-hierarchy-group-${relation}`}>
                  <div style={hierarchyGroupHeadingStyle}>
                    {relation === 'parent'
                      ? `↑ ${t('traceability.upstream')}`
                      : `↓ ${t('traceability.downstream')}`}
                  </div>
                  {nodes.map((node) => (
                    <RequirementTreeNode
                      key={`${relation}:${node.artifactId}`}
                      workspaceId={workspaceId}
                      node={node}
                      depth={0}
                      visitedIds={selfIds}
                      entityIdByArtifactId={entityIdByArtifactId}
                      onSelectRequirement={(id) => navigate(getArtifactRoute(node.artifactType || 'Requirement', id))}
                    />
                  ))}
                </div>
              ))}
            </div>
          )}

          {/* ArchitectureElements flat list section */}
          {archLinks.length > 0 && (
            <div
              data-testid="req-tracelink-architecture-section"
              style={{
                marginBottom: 'var(--space-6)',
                paddingBottom: 'var(--space-4)',
                borderBottom: '1px solid var(--color-border)',
              }}
            >
              <h5
                style={{
                  margin: '0 0 var(--space-2) 0',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 700,
                  color: 'var(--color-text)',
                }}
              >
                {t('traceability.architectureGroup')}
              </h5>
              <ul
                data-testid="req-tracelink-architecture-list"
                style={{ margin: '0', padding: '0' }}
              >
                {archLinks
                  .map((link) => {
                    // #416: resolve against both ids; skip links this
                    // requirement does not actually take part in.
                    const row = resolveLinkRow(link);
                    if (!row) return null;
                    const { displayTitle, route } = row;

                    return (
                      <li
                        key={link.id}
                        data-testid="req-tracelink-arch-item"
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
                        <button
                          type="button"
                          data-testid="req-tracelink-arch-title"
                          onClick={() => navigate(route)}
                          style={{
                            background: 'none',
                            border: 'none',
                            padding: 0,
                            color: 'var(--color-primary)',
                            cursor: 'pointer',
                            textDecoration: 'underline',
                            fontSize: 'var(--font-size-sm)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            fontFamily: 'inherit',
                          }}
                          title={displayTitle}
                        >
                          {displayTitle}
                        </button>
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
            </div>
          )}

          {/* TestCases and every other linked artifact type (#416: including
              TestCase<->Requirement links, which used to match no section). */}
          {otherLinks.length > 0 && (
            <div data-testid="req-tracelink-other-section">
              <h5
                style={{
                  margin: '0 0 var(--space-2) 0',
                  fontSize: 'var(--font-size-sm)',
                  fontWeight: 700,
                  color: 'var(--color-text)',
                }}
              >
                {t('traceability.other', 'Other Links')}
              </h5>
              <ul
                data-testid="req-tracelink-other-list"
                style={{ margin: '0', padding: '0' }}
              >
                {otherLinks
                  .map((link) => {
                    // #416: same endpoint resolution as the architecture list.
                    const row = resolveLinkRow(link);
                    if (!row) return null;
                    const { displayTitle, route } = row;

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
                        <button
                          type="button"
                          data-testid="req-tracelink-title"
                          onClick={() => navigate(route)}
                          style={{
                            background: 'none',
                            border: 'none',
                            padding: 0,
                            color: 'var(--color-primary)',
                            cursor: 'pointer',
                            textDecoration: 'underline',
                            fontSize: 'var(--font-size-sm)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            fontFamily: 'inherit',
                          }}
                          title={displayTitle}
                        >
                          {displayTitle}
                        </button>
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
            </div>
          )}
        </div>
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
