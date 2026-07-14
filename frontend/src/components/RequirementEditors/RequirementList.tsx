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
import { Requirement, RequirementType, UUID } from '../../types';
import { REQ_CATEGORIES, WORKFLOW_STATES } from '../../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getTypeColor(type?: RequirementType): string {
  switch (type) {
    case 'SyReq': return '#10B981';
    case 'SWReq': return '#8B5CF6';
    case 'HWReq': return '#F59E0B';
    default:      return '#6B7280';
  }
}

/** Map a Requirement to a WorkspaceTreeNode with optional parent hierarchy. */
function reqToNode(req: Requirement): WorkspaceTreeNode {
  const badge = req.type
    ? { text: getTypeBadgeAbbreviation(req.type), bg: getTypeColor(req.type), color: 'white' }
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
      sorted.sort((a, b) => {
        const ai = WORKFLOW_STATES.indexOf(a.status);
        const bi = WORKFLOW_STATES.indexOf(b.status);
        const av = ai === -1 ? WORKFLOW_STATES.length : ai;
        const bv = bi === -1 ? WORKFLOW_STATES.length : bi;
        return av - bv || a.title.localeCompare(b.title);
      });
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
  onCreateNew: () => void;
  isCreating?: boolean;
}

/**
 * RequirementList — Left panel with filterable list of requirements.
 * (REQ-003) Uses WorkspaceTree for uniform compact-row navigation.
 */
export const RequirementList: React.FC<RequirementListProps> = ({
  requirements,
  selectedId,
  onSelect,
  onDelete,
  onCreateNew,
  isCreating = false,
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
    () => visibleRequirements.map(reqToNode),
    [visibleRequirements],
  );

  const hasActiveListControls = Boolean(listSearch || categoryFilter || statusFilter);

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
            options: WORKFLOW_STATES.map((state) => ({ value: state, label: state })),
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
            : null
        }
      />

      {/* Create button */}
      <button
        data-testid="create-req-btn"
        onClick={onCreateNew}
        style={{
          marginBottom: 'var(--space-3)',
          background: 'var(--color-primary)',
          color: 'white',
          border: 'none',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--space-2) var(--space-4)',
          fontSize: 'var(--font-size-sm)',
          cursor: 'pointer',
          transition: 'var(--transition-fast)',
          fontWeight: 600,
        }}
      >
        {isCreating ? t('actions.creating') : `+ ${t('actions.new')}`}
      </button>

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

      {/* Unified tree navigation — REQ-003 */}
      {/* REQ-091: enable virtualization for this hot-path list (threshold 100). */}
      <WorkspaceTree
        data-testid="req-list-tree"
        nodes={treeNodes}
        selectedId={selectedId}
        onSelect={onSelect}
        showSearch={false}
        virtualize
        emptyLabel={t('editor.empty')}
        noMatchesLabel={t('editor.noMatches')}
      />
    </div>
  );
};

RequirementList.displayName = 'RequirementList';
