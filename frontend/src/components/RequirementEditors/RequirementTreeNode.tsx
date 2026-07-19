/**
 * RequirementTreeNode — Recursive tree node for requirement parent-child hierarchy.
 *
 * Displays derives-from / derived-by trace links as an expandable tree,
 * bounded by MAX_DEPTH to prevent infinite recursion in cyclic graphs.
 * Used by ReqTraceLinkPanel for hierarchical requirement visualization.
 */

import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { tracelinksApi } from '../../api/tracelinks';
import type { Requirement, TraceLink, UUID } from '../../types';

/** Max depth — bounds recursion for cyclic trace graphs */
const MAX_DEPTH = 3;

interface RequirementTreeNodeProps {
  workspaceId: UUID;
  requirement: Requirement;
  depth: number;
  onSelectRequirement?: (id: UUID) => void;
}

interface ChildNode {
  requirement: Requirement;
  link: TraceLink;
  direction: 'parent' | 'child';
}

export const RequirementTreeNode: React.FC<RequirementTreeNodeProps> = ({
  workspaceId,
  requirement,
  depth,
  onSelectRequirement,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);
  const [childNodes, setChildNodes] = useState<ChildNode[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const atMaxDepth = depth >= MAX_DEPTH;

  const toggle = async (): Promise<void> => {
    if (atMaxDepth) return;

    if (expanded) {
      setExpanded(false);
      return;
    }

    if (childNodes === null) {
      setLoading(true);
      setError(null);
      try {
        const resp = await tracelinksApi.listForArtifact(workspaceId, requirement.id);
        // Fetch full requirement objects for all linked targets
        // For now, use backend-supplied titles as fallback
        const nodes: ChildNode[] = [];
        for (const link of resp.results) {
          if (!['derives-from', 'derived-by'].includes(link.link_type)) continue;

          const isSource = link.source_id === requirement.id;
          const targetId = isSource ? link.target_id : link.source_id;
          const direction =
            (isSource && link.link_type === 'derives-from') ||
            (!isSource && link.link_type === 'derived-by')
              ? 'parent'
              : 'child';

          // Create minimal Requirement from TraceLink data
          nodes.push({
            requirement: {
              id: targetId,
              title: isSource ? link.target_title ?? '' : link.source_title ?? '',
              description: '',
              category: 'functional',
              type: 'SyReq',
              status: 'draft',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              version: 1,
              workspace_id: workspaceId,
            },
            link,
            direction,
          });
        }
        setChildNodes(nodes);
      } catch (err: unknown) {
        const msg =
          (err as { error?: { message?: string } })?.error?.message ?? String(err);
        setError(msg);
        setChildNodes([]);
      } finally {
        setLoading(false);
      }
    }
    setExpanded(true);
  };

  // Group child nodes by direction (parent/child)
  const groups = new Map<'parent' | 'child', ChildNode[]>();
  for (const node of childNodes ?? []) {
    const bucket = groups.get(node.direction) ?? [];
    bucket.push(node);
    groups.set(node.direction, bucket);
  }

  const hasParents = (groups.get('parent') ?? []).length > 0;
  const hasChildren = (groups.get('child') ?? []).length > 0;

  const handleTitleClick = (): void => {
    if (onSelectRequirement) {
      onSelectRequirement(requirement.id);
    } else {
      navigate(`/requirements/${requirement.id}`);
    }
  };

  return (
    <div
      data-testid="req-tree-node"
      data-req-id={requirement.id}
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
          disabled={atMaxDepth || (!hasParents && !hasChildren)}
          aria-expanded={expanded}
          style={{
            background: 'none',
            border: 'none',
            cursor: atMaxDepth || (!hasParents && !hasChildren) ? 'not-allowed' : 'pointer',
            fontSize: 'var(--font-size-sm)',
            color: 'var(--color-text-muted)',
            width: '1.25em',
            padding: 0,
          }}
        >
          {!hasParents && !hasChildren ? '·' : expanded ? '▼' : '▶'}
        </button>

        <span
          style={{
            fontSize: 'var(--font-size-xs)',
            background: 'var(--color-surface-raised)',
            padding: '2px 8px',
            borderRadius: 'var(--radius-full)',
            color: 'var(--color-text-muted)',
            fontWeight: 500,
          }}
        >
          Req
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
          title={requirement.title}
        >
          {requirement.title || requirement.id.slice(0, 8)}
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
            <p
              role="alert"
              style={{
                color: 'var(--color-danger)',
                fontSize: 'var(--font-size-sm)',
                margin: 'var(--space-2) 0 var(--space-2) var(--space-5)',
              }}
            >
              {error}
            </p>
          )}

          {!loading && !error && childNodes && childNodes.length === 0 && (
            <p
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
            Array.from(groups.entries()).map(([dir, nodes]) => (
              <div key={dir} data-testid={`req-tree-group-${dir}`} style={{ marginLeft: 'var(--space-5)' }}>
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
                  {dir === 'parent' ? '↑ Parents' : '↓ Children'}
                </div>

                {nodes.map((node) => (
                  <RequirementTreeNode
                    key={node.link.id}
                    workspaceId={workspaceId}
                    requirement={node.requirement}
                    depth={depth + 1}
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
