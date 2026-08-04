/**
 * NeedList — left-panel navigation for stakeholder needs (REQ-003).
 *
 * Refactored to use the shared WorkspaceTree component for a consistent
 * compact tree-row style across all artifact views (REQ-003).
 *
 * Search + status filter + sort remain in ListToolbar; WorkspaceTree
 * receives the already-filtered list and renders it as compact tree rows.
 */
import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ListToolbar } from '../shared/ListToolbar';
import { EmptyState } from '../shared/EmptyState';
import { getStatusBadgeStyle } from '../../utils/statusBadge';
import { WorkspaceTree } from '../shared/WorkspaceTree';
import type { WorkspaceTreeNode } from '../shared/WorkspaceTree';
import type { StakeholderNeed } from '../../types';
import { WORKFLOW_STATES } from '../../types';

interface NeedListProps {
  needs: StakeholderNeed[];
  selectedId?: string;
  showCreateForm?: boolean;
  setShowCreateForm?: (show: boolean) => void;
  newTitle?: string;
  setNewTitle?: (val: string) => void;
  onSubmitCreate?: () => void;
  createError?: string | null;
  onCreateClick?: () => void;
}

type NeedSortKey = 'default' | 'title' | 'status' | 'updated';

function sortNeeds(
  list: StakeholderNeed[],
  sortKey: NeedSortKey,
): StakeholderNeed[] {
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
      sorted.sort((a, b) => {
        const d1 = a.updated_at || '';
        const d2 = b.updated_at || '';
        return d2.localeCompare(d1);
      });
      break;
    default:
      break;
  }
  return sorted;
}

/** Map a StakeholderNeed to a WorkspaceTreeNode (flat — no hierarchy). */
function needToNode(need: StakeholderNeed): WorkspaceTreeNode {
  const style = getStatusBadgeStyle(need.status);
  return {
    id: need.id,
    name: need.title || 'Untitled',
    parentId: null,
    badge: {
      text: need.status,
      bg: style.background as string,
      color: style.color as string,
    },
  };
}

export function NeedList({
  needs,
  selectedId,
  showCreateForm,
  setShowCreateForm,
  newTitle,
  setNewTitle,
  onSubmitCreate,
  createError,
  onCreateClick,
}: NeedListProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [listSearch, setListSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortKey, setSortKey] = useState<NeedSortKey>('default');

  const visibleNeeds = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = needs.filter((need) => {
      if (
        q &&
        !need.title.toLowerCase().includes(q) &&
        !(need.uid && need.uid.toLowerCase().includes(q))
      ) {
        return false;
      }
      if (statusFilter && need.status !== statusFilter) return false;
      return true;
    });
    return sortNeeds(filtered, sortKey);
  }, [needs, listSearch, statusFilter, sortKey]);

  const treeNodes = useMemo(
    () => visibleNeeds.map(needToNode),
    [visibleNeeds],
  );

  const hasActiveListControls = Boolean(listSearch || statusFilter);

  return (
    <div>
      <ListToolbar
        testIdPrefix="need-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t('editor.searchPlaceholder', 'Search needs...')}
        filters={[
          {
            id: 'status',
            allLabel: t('editor.allStatuses', 'All Statuses'),
            value: statusFilter,
            options: WORKFLOW_STATES.map((state) => ({ value: state, label: state })),
            onChange: setStatusFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: 'default', label: t('editor.sortDefault', 'Default') },
          { value: 'title', label: t('editor.sortTitleAsc', 'Title (A-Z)') },
          { value: 'status', label: t('editor.sortStatus', 'Status') },
          { value: 'updated', label: t('editor.sortUpdatedDesc', 'Recently Updated') },
        ]}
        onSortChange={(value) => setSortKey(value as NeedSortKey)}
        sortLabel={t('editor.sortLabel', 'Sort by')}
        countLabel={
          hasActiveListControls
            ? t('editor.filteredCount', {
                shown: visibleNeeds.length,
                total: needs.length,
              })
            : null
        }
        // #315: the "Neuer Bedarf" primary action now lives in the
        // PageHeader (UI_KONZEPT.md §12.2), not in this list toolbar —
        // matches Adr/Risk/Issue/TestCase editors. `onCreateClick` is still
        // forwarded (below) for the empty-state's own create action.
      />

      {showCreateForm && setShowCreateForm && setNewTitle && onSubmitCreate && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmitCreate();
          }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
            padding: 'var(--space-3)',
            marginBottom: 'var(--space-3)',
            background: 'var(--color-surface-raised)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <label
            style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--color-text)' }}
          >
            {t('editor.title', 'Title')}
          </label>
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            autoFocus
            placeholder={t('editor.newNeedTitle', 'e.g. As a user, I need...')}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)',
              color: 'var(--color-text)',
            }}
          />
          {createError && (
            <p
              role="alert"
              style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', margin: 0 }}
            >
              {createError}
            </p>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button
              type="button"
              onClick={() => setShowCreateForm(false)}
              style={{
                background: 'transparent',
                color: 'var(--color-text)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)',
                cursor: 'pointer',
              }}
            >
              {t('cancel', 'Cancel')}
            </button>
            <button
              type="submit"
              disabled={!(newTitle || '').trim()}
              style={{
                background: 'var(--color-primary)',
                color: 'white',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)',
                cursor: 'pointer',
              }}
            >
              {t('create', 'Create')}
            </button>
          </div>
        </form>
      )}

      {/* #179: distinct empty vs. no-match states (ch. 13.3) instead of
          WorkspaceTree's built-in plain-text emptyLabel/noMatchesLabel —
          "there is nothing" wants a create action, "there is something,
          just not under this filter" must not offer one. */}
      {needs.length === 0 ? (
        <EmptyState
          variant="empty"
          testId="need-list-empty"
          title={t('needs.emptyTitle', 'Noch keine Bedarfe')}
          description={t(
            'needs.emptyDescription',
            'Stakeholder-Bedarfe beschreiben, was Stakeholder brauchen und warum.',
          )}
          actions={
            onCreateClick
              ? [{ label: t('needs.newNeed', 'Neuer Bedarf'), onClick: onCreateClick, testId: 'need-list-empty-create' }]
              : undefined
          }
        />
      ) : visibleNeeds.length === 0 ? (
        <EmptyState
          variant="no-match"
          testId="need-list-no-match"
          onResetFilters={() => {
            setListSearch('');
            setStatusFilter('');
          }}
        />
      ) : (
        // Unified tree navigation — REQ-003
        // REQ-091: enable virtualization for this hot-path list (threshold 100).
        <WorkspaceTree
          data-testid="need-list-tree"
          nodes={treeNodes}
          selectedId={selectedId}
          onSelect={(id) => navigate(`/needs/${id}`)}
          showSearch={false}
          virtualize
        />
      )}
    </div>
  );
}

NeedList.displayName = 'NeedList';
