/**
 * RiskList — left-panel navigation for risks (REQ-003).
 *
 * Refactored to use the shared WorkspaceTree component for consistent
 * compact tree rows across all artifact views (REQ-003).
 */
import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ListToolbar } from '../shared/ListToolbar';
import { getStatusBadgeStyle } from '../../utils/statusBadge';
import { WorkspaceTree } from '../shared/WorkspaceTree';
import type { WorkspaceTreeNode } from '../shared/WorkspaceTree';
import type { Risk } from '../../types';
import { WORKFLOW_STATES } from '../../types';

interface RiskListProps {
  items: Risk[];
  selectedId?: string;
  onCreateNew: () => void;
  showCreateForm?: boolean;
  setShowCreateForm?: (show: boolean) => void;
  newTitle?: string;
  setNewTitle?: (val: string) => void;
  onSubmitCreate?: () => void;
  createError?: string | null;
}

type SortKey = 'default' | 'title' | 'status' | 'updated';

function sortItems(list: Risk[], sortKey: SortKey): Risk[] {
  const sorted = [...list];
  switch (sortKey) {
    case 'title': sorted.sort((a, b) => a.title.localeCompare(b.title)); break;
    case 'status': {
      sorted.sort((a, b) => {
        const ai = WORKFLOW_STATES.indexOf(a.status);
        const bi = WORKFLOW_STATES.indexOf(b.status);
        return (ai === -1 ? WORKFLOW_STATES.length : ai) - (bi === -1 ? WORKFLOW_STATES.length : bi) || a.title.localeCompare(b.title);
      });
      break;
    }
    case 'updated': sorted.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')); break;
  }
  return sorted;
}

function riskToNode(risk: Risk): WorkspaceTreeNode {
  const style = getStatusBadgeStyle(risk.status);
  return {
    id: risk.id,
    name: risk.title || 'Untitled',
    parentId: null,
    badge: {
      text: risk.status,
      bg: style.background as string,
      color: style.color as string,
    },
  };
}

export function RiskList({
  items, selectedId, onCreateNew, showCreateForm, setShowCreateForm, newTitle, setNewTitle, onSubmitCreate, createError,
}: RiskListProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [listSearch, setListSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('default');

  const visible = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = items.filter((it) => {
      if (q && !it.title.toLowerCase().includes(q)) return false;
      if (statusFilter && it.status !== statusFilter) return false;
      return true;
    });
    return sortItems(filtered, sortKey);
  }, [items, listSearch, statusFilter, sortKey]);

  const treeNodes = useMemo(() => visible.map(riskToNode), [visible]);

  const hasActiveListControls = Boolean(listSearch || statusFilter);

  return (
    <div>
      <h3
        style={{
          fontSize: 'var(--font-size-lg)',
          fontWeight: 600,
          margin: 0,
          marginBottom: 'var(--space-3)',
          color: 'var(--color-text)',
        }}
      >
        {t('nav.risks')}
      </h3>
      <ListToolbar
        testIdPrefix="risk-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t('editor.searchPlaceholder', 'Search...')}
        filters={[{
          id: 'status', allLabel: t('editor.allStatuses', 'All Statuses'), value: statusFilter,
          options: WORKFLOW_STATES.map((s) => ({ value: s, label: s })), onChange: setStatusFilter,
        }]}
        sortValue={sortKey}
        sortOptions={[
          { value: 'default', label: t('editor.sortDefault', 'Default') },
          { value: 'title', label: t('editor.sortTitleAsc', 'Title (A-Z)') },
          { value: 'status', label: t('editor.sortStatus', 'Status') },
          { value: 'updated', label: t('editor.sortUpdatedDesc', 'Recently Updated') },
        ]}
        onSortChange={(v) => setSortKey(v as SortKey)}
        sortLabel={t('editor.sortLabel', 'Sort by')}
        countLabel={hasActiveListControls ? t('editor.filteredCount', { shown: visible.length, total: items.length }) : null}
      />

      <button
        data-testid="create-risk-btn"
        onClick={onCreateNew}
        disabled={showCreateForm}
        style={{
          marginBottom: 'var(--space-3)', background: 'var(--color-primary)', color: 'white', border: 'none',
          borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)', fontSize: 'var(--font-size-sm)',
          cursor: showCreateForm ? 'not-allowed' : 'pointer', opacity: showCreateForm ? 0.6 : 1,
          transition: 'var(--transition-fast)', fontWeight: 600,
        }}
      >
        + {t('actions.new', 'New')}
      </button>

      {showCreateForm && setShowCreateForm && setNewTitle && onSubmitCreate && (
        <form
          onSubmit={(e) => { e.preventDefault(); onSubmitCreate(); }}
          style={{
            display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', padding: 'var(--space-3)',
            marginBottom: 'var(--space-3)', background: 'var(--color-surface-raised)',
            border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
          }}
        >
          <label style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
            {t('editor.title', 'Title')}
          </label>
          <input
            data-testid="risk-new-title-input"
            type="text" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} autoFocus
            placeholder={t('editor.newNeedTitle', 'e.g. Risk title...')}
            style={{
              padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)', fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)', color: 'var(--color-text)',
            }}
          />
          {createError && (
            <p role="alert" style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', margin: 0 }}>
              {createError}
            </p>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button
              type="button"
              onClick={() => setShowCreateForm(false)}
              style={{
                background: 'transparent', color: 'var(--color-text)', border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)', cursor: 'pointer',
              }}
            >
              {t('cancel', 'Cancel')}
            </button>
            <button
              data-testid="risk-new-save-btn"
              type="submit"
              disabled={!(newTitle || '').trim()}
              style={{
                background: 'var(--color-primary)', color: 'white', border: 'none',
                borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)', cursor: 'pointer',
              }}
            >
              {t('create', 'Create')}
            </button>
          </div>
        </form>
      )}

      {/* Unified tree navigation — REQ-003 */}
      <WorkspaceTree
        data-testid="risk-list-tree"
        nodes={treeNodes}
        selectedId={selectedId}
        onSelect={(id) => navigate(`/risks/${id}`)}
        showSearch={false}
        emptyLabel={t('editor.empty', 'No items available.')}
        noMatchesLabel={t('editor.noMatches', 'No matches found.')}
      />
    </div>
  );
}

RiskList.displayName = 'RiskList';
