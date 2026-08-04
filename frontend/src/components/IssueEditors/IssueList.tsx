/**
 * IssueList — left-panel navigation for issues (REQ-003).
 *
 * Task 2.3 remodel: rows are <ArtifactRow> (ch. 12.3 — id/level on top,
 * title below, status + version badges) instead of a WorkspaceTree node, and
 * the empty list vs. empty filter result render through <EmptyState> with
 * distinct text and actions (ch. 12.7/13.3). The page title, always-visible
 * summary and "New Issue" primary action now live in <PageHeader> at the
 * IssueEditors level (ch. 12.1/12.2) — this component only owns
 * search/filter/sort and the row list. Mirrors AdrList/RiskList (Tasks 2.1/2.2).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ListToolbar } from '../shared/ListToolbar';
import { ArtifactRow } from '../shared/ArtifactRow';
import { EmptyState } from '../shared/EmptyState';
import type { Issue } from '../../types';
import { WORKFLOW_STATES } from '../../types';
import styles from './IssueList.module.css';

interface IssueListProps {
  items: Issue[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onCreateNew: () => void;
}

type SortKey = 'default' | 'title' | 'status' | 'updated';

function sortItems(list: Issue[], sortKey: SortKey): Issue[] {
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

export function IssueList({ items, selectedId, onSelect, onCreateNew }: IssueListProps): JSX.Element {
  const { t } = useTranslation();
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

  const hasActiveListControls = Boolean(listSearch || statusFilter);

  const resetFilters = (): void => {
    setListSearch('');
    setStatusFilter('');
  };

  return (
    <div data-testid="issue-list">
      <ListToolbar
        testIdPrefix="issue-list"
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
        countLabel={hasActiveListControls ? t('editor.filteredCount', { shown: visible.length, total: items.length }) : String(items.length)}
      />

      {items.length === 0 ? (
        // ch. 13.3: "there is nothing" — offer the create action, not a
        // filter reset.
        <EmptyState
          variant="empty"
          testId="issue-list-empty"
          title={t('issues.emptyTitle', 'No issues yet')}
          description={t(
            'issues.emptyDescription',
            'Issues track defects, improvements and open questions for this workspace.',
          )}
          actions={[{ label: t('issues.newIssue', 'New Issue'), onClick: onCreateNew, testId: 'issue-list-empty-create' }]}
        />
      ) : visible.length === 0 ? (
        // ch. 13.3: "there is something, just not under this filter" — offer
        // only a filter reset, never a create action.
        <EmptyState variant="no-match" testId="issue-list-no-match" onResetFilters={resetFilters} />
      ) : (
        <div className={styles.rows} data-testid="issue-list-rows">
          {visible.map((issue) => (
            <ArtifactRow
              key={issue.id}
              id={issue.uid}
              idFallback={issue.id.slice(0, 8)}
              title={issue.title || t('issues.untitled', 'Untitled')}
              status={issue.status}
              version={issue.version}
              selected={issue.id === selectedId}
              onClick={() => onSelect(issue.id)}
              testId={`issue-row-${issue.id}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

IssueList.displayName = 'IssueList';
