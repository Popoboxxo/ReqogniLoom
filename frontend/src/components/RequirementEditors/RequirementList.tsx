/**
 * REQ-003: RequirementList — refactored to WorkspaceTree for unified navigation.
 * REQ-L3-RF003-005: RequirementList Component.
 *
 * leaf_id: COMP-RF-003-RequirementList
 * req_id: REQ-003, REQ-L3-RF003-001, REQ-L3-RF003-004
 *
 * Uses the shared WorkspaceTree component (REQ-003) for consistent compact
 * tree rows across all artifact views. Requirements with parent_id are
 * rendered hierarchically with expand/collapse support.
 *
 * Search + filter + sort remain in ListToolbar; WorkspaceTree receives the
 * already-filtered/sorted list with showSearch=false.
 *
 * TODO (future): wire delete via WorkspaceTree context menu once that feature
 * is added in a later iteration. Currently, delete happens via the form's
 * delete button; the inline two-step confirm overlay in this component is
 * kept as a fallback but not triggered from the tree rows.
 */

import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ListToolbar } from '../shared/ListToolbar';
import { WorkspaceTree, getTypeBadgeAbbreviation } from '../shared/WorkspaceTree';
import type { WorkspaceTreeNode } from '../shared/WorkspaceTree';
import { ArtifactRow } from '../shared/ArtifactRow';
import { EmptyState } from '../shared/EmptyState';
import { Requirement, RequirementType, UUID } from '../../types';
import { REQ_CATEGORIES } from '../../types';
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from '../../utils/workflowStatus';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTypeColor(type?: RequirementType): string {
  switch (type) {
    case 'SyReq': return '#10B981';
    case 'UseCase': return '#8B5CF6';
    case 'FeatureReq': return '#F59E0B';
    default:      return '#6B7280';
  }
}

/**
 * Issue #394: V-model level badge prefix (`L0`-`L4`), rendered in front of
 * the type abbreviation — analogous to the `L{n}` badge ArchitectureElement
 * already shows (issue root cause: "L1/L2 requirements are visually
 * identical, flat list without hierarchy indicator"). Empty string when the
 * level has not been assigned (NULL until set explicitly, see
 * `persistence.models.Requirement.level`).
 */
function reqLevelPrefix(level?: number | null): string {
  return level != null ? `L${level} ` : '';
}

/**
 * Map a Requirement to a WorkspaceTreeNode with optional parent hierarchy.
 *
 * @param req - Requirement to convert.
 * @param typeLabel - Spelled-out label for `req.type` (e.g. from
 *   `t('reqType.SyReq')`), used as the badge tooltip/aria-label
 *   (issue #169 — "SR" abbreviation without legend).
 * @param levelLabel - Spelled-out label for `req.level` (e.g. from
 *   `t('reqLevel.L1')`), appended to the tooltip (issue #394).
 */
function reqToNode(req: Requirement, typeLabel?: string, levelLabel?: string): WorkspaceTreeNode {
  const badge = req.type
    ? {
        text: reqLevelPrefix(req.level) + getTypeBadgeAbbreviation(req.type),
        bg: getTypeColor(req.type),
        color: 'white',
        title: levelLabel ? `${levelLabel} · ${typeLabel ?? ''}` : typeLabel,
      }
    : undefined;
  return {
    id: req.id,
    name: (req.suspect ? '⚠ ' : '') + (req.title || 'Untitled'),
    parentId: req.parent_id ?? null,
    badge,
  };
}

// ---------------------------------------------------------------------------
// Sorting
// ---------------------------------------------------------------------------

type ReqSortKey = 'default' | 'title' | 'status' | 'updated';

function sortRequirements(list: Requirement[], sortKey: ReqSortKey): Requirement[] {
  const sorted = [...list];
  switch (sortKey) {
    case 'title':
      sorted.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case 'status':
      sorted.sort(
        (a, b) => compareWorkflowStatus(a.status, b.status) || a.title.localeCompare(b.title),
      );
      break;
    case 'updated':
      sorted.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
      break;
    default:
      break;
  }
  return sorted;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface RequirementListProps {
  requirements: Requirement[];
  selectedId?: string;
  onSelect: (id: UUID) => void;
  onDelete: (id: UUID) => void;
  /** Task 3.1: wired to the "empty" EmptyState's create action (ch. 12.7/13.3). */
  onCreateNew: () => void;
}

/**
 * RequirementList — Left panel with filterable list of requirements.
 * (REQ-003) Uses WorkspaceTree for uniform compact-row navigation; rows are
 * rendered as <ArtifactRow> (Task 3.1, ch. 12.3) via WorkspaceTree's
 * `renderRow` slot, keeping the tree's own chevron/indent/select chrome.
 */
export const RequirementList: React.FC<RequirementListProps> = ({
  requirements,
  selectedId,
  onSelect,
  onDelete,
  onCreateNew,
}) => {
  const { t } = useTranslation();
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [listSearch, setListSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortKey, setSortKey] = useState<ReqSortKey>('default');

  const visibleRequirements = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = requirements.filter((req) => {
      if (q && !req.title.toLowerCase().includes(q) && !req.id.toLowerCase().includes(q)) {
        return false;
      }
      if (categoryFilter && req.category !== categoryFilter) return false;
      if (statusFilter && req.status !== statusFilter) return false;
      return true;
    });
    return sortRequirements(filtered, sortKey);
  }, [requirements, listSearch, categoryFilter, statusFilter, sortKey]);

  const treeNodes = useMemo(
    () =>
      visibleRequirements.map((req) =>
        reqToNode(
          req,
          req.type ? t(`reqType.${req.type}`) : undefined,
          req.level != null ? t(`reqLevel.L${req.level}`) : undefined,
        ),
      ),
    [visibleRequirements, t],
  );

  // Task 3.1: lookup used by renderRow to hydrate <ArtifactRow> from the
  // WorkspaceTreeNode id — avoids widening WorkspaceTreeNode's shape.
  const reqById = useMemo(() => {
    const map = new Map<string, Requirement>();
    for (const req of visibleRequirements) map.set(req.id, req);
    return map;
  }, [visibleRequirements]);

  // GH-453: options are derived from the loaded items, so their values are
  // exactly what `req.status !== statusFilter` compares against. Requirement
  // states additionally vary per rigor preset (minimal/standard/extended),
  // which no single hardcoded list could ever cover.
  const statusOptions = useMemo(
    () => buildStatusFilterOptions(requirements, statusFilter),
    [requirements, statusFilter],
  );

  const hasActiveListControls = Boolean(listSearch || categoryFilter || statusFilter);

  const resetFilters = (): void => {
    setListSearch('');
    setCategoryFilter('');
    setStatusFilter('');
  };

  return (
    <div>
      <ListToolbar
        testIdPrefix="req-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t('editor.searchPlaceholder')}
        filters={[
          {
            id: 'category',
            allLabel: t('editor.allCategories'),
            value: categoryFilter,
            options: REQ_CATEGORIES.map((cat) => ({ value: cat, label: cat })),
            onChange: setCategoryFilter,
          },
          {
            id: 'status',
            allLabel: t('editor.allStatuses'),
            value: statusFilter,
            options: statusOptions,
            onChange: setStatusFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: 'default', label: t('editor.sortDefault') },
          { value: 'title', label: t('editor.sortTitleAsc') },
          { value: 'status', label: t('editor.sortStatus') },
          { value: 'updated', label: t('editor.sortUpdatedDesc') },
        ]}
        onSortChange={(value) => setSortKey(value as ReqSortKey)}
        sortLabel={t('editor.sortLabel')}
        countLabel={
          hasActiveListControls
            ? t('editor.filteredCount', {
                shown: visibleRequirements.length,
                total: requirements.length,
              })
            : String(requirements.length)
        }
      />

      {/* Delete confirmation overlay (two-step) */}
      {confirmDeleteId && (
        <div
          style={{
            display: 'flex',
            gap: 'var(--space-2)',
            alignItems: 'center',
            padding: 'var(--space-2) var(--space-3)',
            marginBottom: 'var(--space-2)',
            background: 'var(--color-surface-raised)',
            border: '1px solid var(--color-danger)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <span
            style={{ flex: 1, fontSize: 'var(--font-size-sm)', color: 'var(--color-text)' }}
          >
            {t('actions.confirmDeletePrompt', 'Delete this requirement?')}
          </span>
          <button
            data-testid="req-confirm-delete-btn"
            onClick={() => { onDelete(confirmDeleteId); setConfirmDeleteId(null); }}
            style={{
              background: 'var(--color-danger)', color: 'white', border: 'none',
              borderRadius: 'var(--radius-md)', padding: '2px 8px',
              fontSize: 'var(--font-size-xs)', fontWeight: 600, cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {t('actions.confirmDelete', 'Ja, löschen')}
          </button>
          <button
            data-testid="req-cancel-delete-btn"
            onClick={() => setConfirmDeleteId(null)}
            style={{
              background: 'transparent', color: 'var(--color-text)',
              border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
              padding: '2px 8px', fontSize: 'var(--font-size-xs)', cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {t('actions.cancel')}
          </button>
        </div>
      )}

      {/* Task 3.1 / ch. 13.3: distinguish "nothing exists" from "nothing
          matches the current filter" — the former wants a create action,
          the latter only a filter reset. */}
      {requirements.length === 0 ? (
        <EmptyState
          variant="empty"
          testId="req-list-empty"
          title={t('editor.emptyTitle')}
          description={t('editor.emptyDescription')}
          actions={[
            { label: t('requirements.newRequirement'), onClick: onCreateNew, testId: 'req-list-empty-create' },
          ]}
        />
      ) : visibleRequirements.length === 0 ? (
        <EmptyState variant="no-match" testId="req-list-no-match" onResetFilters={resetFilters} />
      ) : (
        // Unified tree navigation — REQ-003. Rows are <ArtifactRow> via
        // renderRow (Task 3.1); WorkspaceTree still owns expand/collapse,
        // depth indent and click-to-select.
        // REQ-091: enable virtualization for this hot-path list (threshold 100).
        <WorkspaceTree
          data-testid="req-list-tree"
          nodes={treeNodes}
          selectedId={selectedId}
          onSelect={onSelect}
          showSearch={false}
          virtualize
          // Task 3.1: <ArtifactRow>'s two-line id/title layout is taller
          // than WorkspaceTree's default single-line row estimate (34px);
          // override it so virtualized rows (>100 items, REQ-091) don't
          // overlap.
          virtualRowHeight={64}
          emptyLabel={t('editor.empty')}
          noMatchesLabel={t('editor.noMatches')}
          renderRow={(node, { isSelected }) => {
            const req = reqById.get(node.id);
            if (!req) return null;
            return (
              <ArtifactRow
                id={req.uid}
                idFallback={req.id.slice(0, 8)}
                levelLabel={
                  req.type
                    ? reqLevelPrefix(req.level) + getTypeBadgeAbbreviation(req.type)
                    : undefined
                }
                levelTitle={
                  req.type
                    ? req.level != null
                      ? `${t(`reqLevel.L${req.level}`)} · ${t(`reqType.${req.type}`)}`
                      : t(`reqType.${req.type}`)
                    : undefined
                }
                title={(req.suspect ? '⚠ ' : '') + (req.title || t('editor.untitled'))}
                status={req.status}
                statusLabel={getWorkflowStatusLabel(req.status)}
                version={req.version}
                selected={isSelected}
                testId={`req-row-${req.id}`}
              />
            );
          }}
        />
      )}
    </div>
  );
};

RequirementList.displayName = 'RequirementList';
