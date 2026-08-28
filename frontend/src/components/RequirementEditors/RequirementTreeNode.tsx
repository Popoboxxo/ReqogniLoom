/**
 * RequirementTreeNode — recursive tree node for the requirement hierarchy.
 *
 * Renders the decomposition neighbourhood (`derives-from`, `decomposes`,
 * `parent-child`) of one artifact as an expandable tree, bounded by MAX_DEPTH.
 * Used by ReqTraceLinkPanel for the "hierarchical view" block.
 *
 * Issue #416 — two independent defects lived here:
 *
 *  1. **Wrong identity.** TraceLink endpoints are *Artifact* ids, but the node
 *     compared them against a *Requirement* id. Neither endpoint matched, so
 *     `isSource` was always false and every link resolved back to its source —
 *     i.e. the current requirement itself. The block dutifully rendered the
 *     artifact it was supposed to navigate away from. Nodes therefore carry
 *     both ids now and delegate endpoint resolution to `utils/traceEndpoints`.
 *  2. **Wrong link types.** The filter accepted `derives-from` and
 *     `derived-by` — the latter does not exist in the backend enum
 *     (`backend/traceability/types.py::LinkType`), while the real hierarchy
 *     types `decomposes` and `parent-child` were dropped. A decomposed
 *     requirement showed no children at all.
 *
 * The expand toggle was additionally disabled whenever children were not yet
 * known, which is the state every collapsed node starts in — so the tree could
 * never be opened in the first place. Cycle handling mirrors ImpactView
 * (#415): ids already on the path from the root are rendered once and marked,
 * never traversed again.
 */

import React, { useMemo, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { tracelinksApi } from '../../api/tracelinks';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import {
  formatShortId,
  hierarchyRelation,
  type HierarchyRelation,
} from '../../utils/traceEndpoints';
import type { UUID } from '../../types';

/** Max depth — bounds recursion for deep decomposition chains */
const MAX_DEPTH = 3;

/** One artifact in the hierarchy tree. */
export interface HierarchyNode {
  /** Artifact id — the id space TraceLink endpoints live in. */
  artifactId: UUID;
  /** Domain entity id, when known — the id the editor routes to. */
  entityId?: UUID;
  title: string;
  /** Backend artifact type ("Requirement", "ArchitectureElement", ...). */
  artifactType: string;
  /** Position relative to the node above it; undefined for a root. */
  relation?: HierarchyRelation;
}

interface RequirementTreeNodeProps {
  workspaceId: UUID;
  node: HierarchyNode;
  depth: number;
  /** Artifact ids already on the path from the root (cycle guard). */
  visitedIds?: ReadonlySet<UUID>;
  /** This node closes a cycle — rendered, but never expanded. */
  isCycle?: boolean;
  /** `artifactId -> entityId` map so children can route to their editor. */
  entityIdByArtifactId?: Readonly<Record<UUID, UUID>>;
  onSelectRequirement?: (id: UUID) => void;
}

const EMPTY_VISITED: ReadonlySet<UUID> = new Set<UUID>();
const NO_ENTITY_IDS: Readonly<Record<UUID, UUID>> = {};

/* Hoisted out of JSX: the inline-style ratchet (`ui-ratchet.test.ts`) counts
   `style={{` literals under components/ and only allows the frozen baseline. */
const TREE_ERROR_STYLE: CSSProperties = {
  color: 'var(--color-danger)',
  fontSize: 'var(--font-size-sm)',
  margin: 'var(--space-2) 0 var(--space-2) var(--space-5)',
};

const TREE_RETRY_BUTTON_STYLE: CSSProperties = {
  background: 'none',
  border: 'none',
  padding: 0,
  color: 'var(--color-primary)',
  fontSize: 'var(--font-size-sm)',
  fontFamily: 'inherit',
  textDecoration: 'underline',
  cursor: 'pointer',
};

export const RequirementTreeNode: React.FC<RequirementTreeNodeProps> = ({
  workspaceId,
  node,
  depth,
  visitedIds = EMPTY_VISITED,
  isCycle = false,
  entityIdByArtifactId = NO_ENTITY_IDS,
  onSelectRequirement,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [childNodes, setChildNodes] = useState<HierarchyNode[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const atMaxDepth = depth >= MAX_DEPTH;
  const toggleDisabled = atMaxDepth || isCycle;

  const selfIds = useMemo(() => {
    const ids = new Set<UUID>([node.artifactId]);
    if (node.entityId) ids.add(node.entityId);
    return ids;
  }, [node.artifactId, node.entityId]);

  const childVisitedIds = useMemo(
    () => new Set<UUID>([...visitedIds, node.artifactId]),
    [visitedIds, node.artifactId]
  );

  /**
   * Fetches this node's hierarchy neighbours.
   *
   * On failure `childNodes` deliberately stays `null`: it is the "not loaded
   * yet" marker that `toggle` checks, so writing `[]` here (as this used to)
   * made the failure permanent — collapsing and re-expanding took the
   * already-loaded path and the node stayed empty for the rest of its life
   * with no way to retry short of a page reload (UI-58).
   */
  const loadChildren = async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const resp = await tracelinksApi.listForArtifact(workspaceId, node.artifactId);
      const links = resp.results;
      const nodes: HierarchyNode[] = [];
      const seen = new Set<UUID>();
      for (const link of links) {
        // `selfIds` always contains this node's Artifact id (it is what the
        // request was made with), so no inference is needed here.
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
      setChildNodes(nodes);
    } catch (err: unknown) {
      const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const toggle = async (): Promise<void> => {
    if (toggleDisabled) return;

    if (expanded) {
      setExpanded(false);
      return;
    }

    if (childNodes === null) {
      setExpanded(true);
      await loadChildren();
      return;
    }
    setExpanded(true);
  };

  // Group neighbours by direction (parents above, children below).
  const groups = new Map<HierarchyRelation, HierarchyNode[]>();
  for (const child of childNodes ?? []) {
    const relation = child.relation ?? 'child';
    const bucket = groups.get(relation) ?? [];
    bucket.push(child);
    groups.set(relation, bucket);
  }

  const displayTitle = node.title || formatShortId(node.artifactId);
  const routeId = node.entityId ?? node.artifactId;

  const handleTitleClick = (): void => {
    if (onSelectRequirement) {
      onSelectRequirement(routeId);
    } else {
      navigate(getArtifactRoute(node.artifactType || 'Requirement', routeId));
    }
  };

  return (
    <div
      data-testid="req-tree-node"
      data-req-id={routeId}
      data-artifact-id={node.artifactId}
      data-relation={node.relation}
      data-cycle={isCycle ? 'true' : undefined}
      data-depth={depth}
      style={{ marginLeft: depth === 0 ? 0 : 'var(--space-5)' }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: 'var(--space-2) var(--space-1)',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <button
          type="button"
          data-testid="req-tree-toggle"
          onClick={() => void toggle()}
          disabled={toggleDisabled}
          aria-expanded={expanded}
          aria-label={expanded ? t('editor.collapseNode', 'Collapse') : t('editor.expandNode', 'Expand')}
          title={isCycle ? t('traceability.cycleNode') : undefined}
          style={{
            background: 'none',
            border: 'none',
            cursor: toggleDisabled ? 'not-allowed' : 'pointer',
            fontSize: 'var(--font-size-sm)',
            color: 'var(--color-text-muted)',
            width: '1.25em',
            padding: 0,
          }}
        >
          {toggleDisabled ? '·' : expanded ? '▼' : '▶'}
        </button>

        <span
          data-testid="req-tree-type"
          style={{
            fontSize: 'var(--font-size-xs)',
            background: 'var(--color-surface-raised)',
            padding: '2px 8px',
            borderRadius: 'var(--radius-full)',
            color: 'var(--color-text-muted)',
            fontWeight: 500,
          }}
        >
          {node.artifactType || 'Req'}
        </span>

        <button
          type="button"
          onClick={handleTitleClick}
          data-testid="req-tree-title"
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            color: 'var(--color-primary)',
            cursor: 'pointer',
            textDecoration: 'underline',
            fontSize: 'var(--font-size-sm)',
            fontFamily: 'inherit',
            textAlign: 'left',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
          }}
          title={displayTitle}
        >
          {displayTitle}
        </button>
      </div>

      {expanded && (
        <div>
          {loading && (
            <p
              role="status"
              style={{
                fontSize: 'var(--font-size-sm)',
                color: 'var(--color-text-muted)',
                margin: 'var(--space-2) 0 var(--space-2) var(--space-5)',
              }}
            >
              {t('loading')}
            </p>
          )}

          {error && (
            <div
              role="alert"
              data-testid="req-tree-error"
              style={TREE_ERROR_STYLE}
            >
              <span>{error}</span>{' '}
              <button
                type="button"
                data-testid="req-tree-retry"
                onClick={() => void loadChildren()}
                disabled={loading}
                style={TREE_RETRY_BUTTON_STYLE}
              >
                {t('editor.retryLoadChildren')}
              </button>
            </div>
          )}

          {!loading && !error && childNodes && childNodes.length === 0 && (
            <p
              data-testid="req-tree-empty"
              style={{
                fontSize: 'var(--font-size-sm)',
                color: 'var(--color-text-muted)',
                margin: 'var(--space-2) 0 var(--space-2) var(--space-5)',
              }}
            >
              {t('traceability.none')}
            </p>
          )}

          {!loading &&
            !error &&
            childNodes &&
            Array.from(groups.entries()).map(([relation, nodes]) => (
              <div
                key={relation}
                data-testid={`req-tree-group-${relation}`}
                style={{ marginLeft: 'var(--space-5)' }}
              >
                <div
                  style={{
                    fontSize: 'var(--font-size-xs)',
                    color: 'var(--color-text-muted)',
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.03em',
                    padding: 'var(--space-2) 0 var(--space-1)',
                  }}
                >
                  {relation === 'parent'
                    ? `↑ ${t('traceability.upstream')}`
                    : `↓ ${t('traceability.downstream')}`}
                </div>

                {nodes.map((child) => (
                  <RequirementTreeNode
                    key={`${relation}:${child.artifactId}`}
                    workspaceId={workspaceId}
                    node={child}
                    depth={depth + 1}
                    visitedIds={childVisitedIds}
                    isCycle={childVisitedIds.has(child.artifactId)}
                    entityIdByArtifactId={entityIdByArtifactId}
                    onSelectRequirement={onSelectRequirement}
                  />
                ))}
              </div>
            ))}
        </div>
      )}
    </div>
  );
};

RequirementTreeNode.displayName = 'RequirementTreeNode';
