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
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { CreateTraceLinkDialog } from '../shared/CreateTraceLinkDialog';
import { DeriveRequirementForm } from '../shared/DeriveRequirementForm';
import { RequirementTreeNode, type HierarchyNode } from './RequirementTreeNode';
import { useHasRole } from '../../hooks/useHasRole';
import { getLinkTypeLabel } from '../../constants/traceLinkLabels';
import styles from './ReqTraceLinkPanel.module.css';
import type {
  Requirement,
  TraceLink,
  UUID,
  TestCase,
  ArchitectureElement,
} from '../../types';

/**
 * UI-P3: renders the far endpoint of a link whose artifact was soft-deleted.
 *
 * Deliberately *not* a link: every detail route filters outdated rows out
 * (`AdrService.list_adrs`, `ArchitectureService.list_architecture_elements`,
 * …), so navigating there would only produce a 404. The row itself stays
 * visible because the backend keeps the TraceLink on purpose — see
 * `ArtifactService.resolve_artifact_titles`.
 */
function OutdatedEndpointLabel({
  displayTitle,
  testId,
}: {
  displayTitle: string;
  testId: string;
}): JSX.Element {
  const { t } = useTranslation();
  return (
    <>
      <span data-testid={testId} className={styles.outdatedTitle} title={displayTitle}>
        {displayTitle}
      </span>
      <span
        data-testid={`${testId}-badge`}
        className={styles.outdatedBadge}
        title={t(
          'tracelinks.outdatedHint',
          'Das verknüpfte Artefakt wurde gelöscht. Der Link bleibt für den Audit-Trail erhalten.'
        )}
      >
        {t('tracelinks.outdated', 'Gelöscht')}
      </span>
    </>
  );
}

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
  // R2/T1: same workspace-role gate as SidebarNavigation/RequirementForm/
  // RequirementList/RequirementEditors. The panel's write triggers (create
  // TraceLink, delete TraceLink, derive a new Requirement) were the last
  // ungated ones in this feature area — a viewer saw controls the server
  // then rejected. Rendered conditionally, not merely disabled.
  const hasRole = useHasRole();
  const canEdit = hasRole('editor');
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  // REQ-005 / issue #926: the unified CreateTraceLinkDialog replaces the
  // legacy inline form. A second instance (architecture targets only,
  // allocated-to preselected) backs the #928 allocation block.
  const [showDialog, setShowDialog] = useState<boolean>(false);
  const [showAllocationDialog, setShowAllocationDialog] = useState<boolean>(false);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [architectureElements, setArchitectureElements] = useState<ArchitectureElement[]>([]);
  const [showDeriveForm, setShowDeriveForm] = useState<boolean>(false);
  const [deriveTitle, setDeriveTitle] = useState<string>('');
  const [deriveArchitectureElementId, setDeriveArchitectureElementId] = useState<string>('');
  const [isDeriving, setIsDeriving] = useState<boolean>(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);
  // UI-09 (system audit P4): deleting a trace link is destructive and
  // irreversible — require explicit confirmation.
  const [pendingDeleteLinkId, setPendingDeleteLinkId] = useState<UUID | null>(null);

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
        isOutdated: neighbor.endpoint.isOutdated,
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
        // UI-P3: the far artifact was soft-deleted but its link is retained
        // for the audit trail — the row must not look like a live relation.
        isOutdated: endpoint.isOutdated,
      };
    },
    [selfIds, architectureElementsById, testCasesById, entityIdByArtifactId]
  );

  /** #928: current `allocated-to` links to architecture elements. */
  const allocations = React.useMemo(() => {
    const rows: Array<{ link: TraceLink; node: ReturnType<typeof resolveLinkRow> }> = [];
    for (const link of links) {
      if (link.link_type !== 'allocated-to') continue;
      const neighbor = neighborOf(link, selfIds);
      if (!neighbor) continue;
      if (neighbor.endpoint.artifactType !== 'ArchitectureElement') continue;
      rows.push({ link, node: resolveLinkRow(link) });
    }
    return rows;
  }, [links, selfIds, resolveLinkRow]);

  const handleDelete = async (linkId: UUID): Promise<void> => {
    try {
      await tracelinksApi.delete(linkId);
      setReloadKey((k) => k + 1);
      onLinksChanged();
    } catch (err: unknown) {
      console.error('Delete tracelink failed:', err);
    }
  };

  const confirmDeleteLink = async (): Promise<void> => {
    if (!pendingDeleteLinkId) return;
    const linkId = pendingDeleteLinkId;
    setPendingDeleteLinkId(null);
    await handleDelete(linkId);
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
    <div data-testid="req-tracelink-panel" className={styles.panel}>
      <div className={styles.panelHeader}>
        <h4 className={styles.panelTitle}>
          {t('arch.tracelinkPanelTitle')}
        </h4>
        {!showDeriveForm && (
          <div className={styles.actionRow}>
            {onAiDerive && (
              // Issue #927: distinct "KI-Ableitung" label, decorative icon
              // outside the accessible name, own hint.
              <button
                type="button"
                data-testid="req-ai-derive-btn"
                className={`btn-primary ${styles.aiGradientButton}`}
                onClick={onAiDerive}
                disabled={isAiDeriving}
                aria-label={t('actions.deriveAi', 'KI-Ableitung')}
                title={t(
                  'actions.deriveAiHint',
                  'Die KI erzeugt Entwürfe zur Prüfung – gespeichert wird erst nach deiner Bestätigung'
                )}
              >
                <span aria-hidden="true">✨</span>{' '}
                {isAiDeriving
                  ? t('actions.derivingAi', 'KI-Ableitung läuft…')
                  : t('actions.deriveAi', 'KI-Ableitung')}
              </button>
            )}
            {canEdit && (
              // Issue #926: same shared CreateTraceLinkDialog primitive as
              // every other artifact type (REQ-005) — no more inline form.
              <button
                type="button"
                data-testid="req-tracelink-create-btn"
                className="btn-primary"
                onClick={() => setShowDialog(true)}
              >
                {t('traceability.create')}
              </button>
            )}
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

      {/* Issue #928: dedicated "Systemelement-Zuordnung" block, above the
          link list, so Requirement -> ArchitectureElement (allocated-to) is a
          one-click, visible action instead of a scroll inside a native select.
          Reads/writes the existing allocated-to TraceLinks — no second data
          store (coverage / VCRM / SE-Auditor TRACE-P3 keep working). */}
      <section
        data-testid="req-allocation-section"
        aria-label={t('allocation.heading', 'Systemelement-Zuordnung')}
        className={styles.allocationSection}
      >
        <div className={styles.allocationHeaderRow}>
          <h5 className={styles.allocationHeading}>{t('allocation.heading', 'Systemelement-Zuordnung')}</h5>
          {canEdit && (
            <button
              type="button"
              className="btn-secondary"
              data-testid="req-allocation-assign-btn"
              onClick={() => setShowAllocationDialog(true)}
              title={t(
                'allocation.assignHint',
                'Dieses Requirement einem Systemelement (Architekturelement) zuordnen'
              )}
            >
              {t('allocation.assign', 'Systemelement zuordnen')}
            </button>
          )}
        </div>
        {allocations.length === 0 ? (
          <p data-testid="req-allocation-empty" className={styles.allocationEmpty}>
            {t('allocation.none', 'Kein Systemelement zugeordnet.')}
          </p>
        ) : (
          <ul data-testid="req-allocation-list" className={styles.allocationList}>
            {allocations.map(({ link, node }) =>
              node ? (
                <li key={link.id} data-testid="req-allocation-item" className={styles.allocationItem}>
                  <span className={styles.allocationBadge}>
                    {getLinkTypeLabel(link.link_type)}
                  </span>
                  {node.isOutdated ? (
                    <OutdatedEndpointLabel
                      displayTitle={node.displayTitle}
                      testId="req-allocation-title-outdated"
                    />
                  ) : (
                    <button
                      type="button"
                      data-testid="req-allocation-title"
                      onClick={() => navigate(node.route)}
                      title={node.displayTitle}
                      className={styles.titleButton}
                    >
                      {node.displayTitle}
                    </button>
                  )}
                  {canEdit && (
                    <button
                      data-testid="req-allocation-remove-btn"
                      onClick={() => setPendingDeleteLinkId(link.id)}
                      className={styles.removeButton}
                      title={t('allocation.remove', 'Zuordnung entfernen')}
                      aria-label={t('allocation.remove', 'Zuordnung entfernen')}
                    >
                      <span aria-hidden="true">×</span>
                    </button>
                  )}
                </li>
              ) : null
            )}
          </ul>
        )}
      </section>

      {/* REQ-005 / issue #926: unified modal replaces the legacy inline form. */}
      <CreateTraceLinkDialog
        workspaceId={workspaceId}
        sourceId={requirementId}
        isOpen={showDialog}
        onClose={() => setShowDialog(false)}
        onCreated={() => {
          setShowDialog(false);
          setReloadKey((k) => k + 1);
          onLinksChanged();
        }}
        defaultLinkType="derives-from"
      />
      {/* Issue #928: architecture-only, allocated-to preselected. */}
      <CreateTraceLinkDialog
        workspaceId={workspaceId}
        sourceId={requirementId}
        isOpen={showAllocationDialog}
        onClose={() => setShowAllocationDialog(false)}
        onCreated={() => {
          setShowAllocationDialog(false);
          setReloadKey((k) => k + 1);
          onLinksChanged();
        }}
        allowedTypes={['architecture']}
        defaultLinkType="allocated-to"
      />

      {isLoading && (
        <p role="status" className={styles.loadingText}>
          {t('loading')}
        </p>
      )}

      {error && !isLoading && (
        <p role="alert" className={styles.errorText}>
          {error}
        </p>
      )}

      {!isLoading && !error && links.length === 0 && (
        <p className={styles.emptyText}>
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
              className={styles.sectionBlock}
            >
              <h5 className={styles.sectionHeading}>
                {t('traceability.requirementsGroup')} (hierarchical view)
              </h5>
              {hierarchyGroups.map(([relation, nodes]) => (
                <div key={relation} data-testid={`req-hierarchy-group-${relation}`}>
                  <div className={styles.hierarchyGroupHeading}>
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
              className={styles.sectionBlock}
            >
              <h5 className={styles.sectionHeading}>
                {t('traceability.architectureGroup')}
              </h5>
              <ul
                data-testid="req-tracelink-architecture-list"
                className={styles.linkList}
              >
                {archLinks
                  .map((link) => {
                    // #416: resolve against both ids; skip links this
                    // requirement does not actually take part in.
                    const row = resolveLinkRow(link);
                    if (!row) return null;
                    const { displayTitle, route, isOutdated } = row;

                    return (
                      <li
                        key={link.id}
                        data-testid="req-tracelink-arch-item"
                        className={styles.linkItem}
                      >
                        <span className={styles.linkTypeBadge}>
                          {getLinkTypeLabel(link.link_type)}
                        </span>
                        {isOutdated ? (
                          <OutdatedEndpointLabel
                            displayTitle={displayTitle}
                            testId="req-tracelink-arch-title-outdated"
                          />
                        ) : (
                          <button
                            type="button"
                            data-testid="req-tracelink-arch-title"
                            onClick={() => navigate(route)}
                            className={styles.titleButton}
                            title={displayTitle}
                          >
                            {displayTitle}
                          </button>
                        )}
                        {canEdit && (
                          <button
                            data-testid="req-tracelink-delete-btn"
                            onClick={() => setPendingDeleteLinkId(link.id)}
                            className={styles.removeButton}
                            title={t('actions.delete')}
                            // #741: title alone is only the last-resort fallback in
                            // the accessible-name computation and is never surfaced on
                            // touch — an icon-only button needs an explicit label.
                            aria-label={t('actions.delete')}
                          >
                            <span aria-hidden="true">×</span>
                          </button>
                        )}
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
              <h5 className={styles.sectionHeading}>
                {t('traceability.other', 'Other Links')}
              </h5>
              <ul
                data-testid="req-tracelink-other-list"
                className={styles.linkList}
              >
                {otherLinks
                  .map((link) => {
                    // #416: same endpoint resolution as the architecture list.
                    const row = resolveLinkRow(link);
                    if (!row) return null;
                    const { displayTitle, route, isOutdated } = row;

                    return (
                      <li
                        key={link.id}
                        data-testid="req-tracelink-item"
                        className={styles.linkItem}
                      >
                        <span className={styles.linkTypeBadge}>
                          {getLinkTypeLabel(link.link_type)}
                        </span>
                        {isOutdated ? (
                          <OutdatedEndpointLabel
                            displayTitle={displayTitle}
                            testId="req-tracelink-title-outdated"
                          />
                        ) : (
                          <button
                            type="button"
                            data-testid="req-tracelink-title"
                            onClick={() => navigate(route)}
                            className={styles.titleButton}
                            title={displayTitle}
                          >
                            {displayTitle}
                          </button>
                        )}
                        {canEdit && (
                          <button
                            data-testid="req-tracelink-delete-btn"
                            onClick={() => setPendingDeleteLinkId(link.id)}
                            className={styles.removeButton}
                            title={t('actions.delete')}
                            // #741: title alone is only the last-resort fallback in
                            // the accessible-name computation and is never surfaced on
                            // touch — an icon-only button needs an explicit label.
                            aria-label={t('actions.delete')}
                          >
                            <span aria-hidden="true">×</span>
                          </button>
                        )}
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
      <div className={styles.deriveHost}>
        {canEdit && (
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
        )}
      </div>

      {pendingDeleteLinkId && (
        <ConfirmDialog
          title={t('traceability.deleteConfirmTitle', 'TraceLink löschen')}
          message={t(
            'traceability.deleteConfirmMessage',
            'Diesen TraceLink löschen? Diese Aktion kann nicht rückgängig gemacht werden.'
          )}
          confirmLabel={t('actions.delete', 'Löschen')}
          onConfirm={() => void confirmDeleteLink()}
          onCancel={() => setPendingDeleteLinkId(null)}
          testId="req-tracelink-delete-confirm"
        />
      )}
    </div>
  );
};

ReqTraceLinkPanel.displayName = 'ReqTraceLinkPanel';
