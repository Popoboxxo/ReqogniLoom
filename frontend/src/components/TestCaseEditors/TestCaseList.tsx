/**
 * TestCaseList — left-panel navigation for test cases (REQ-003).
 *
 * Task 2.4 remodel: rows are <ArtifactRow> (ch. 12.3 — id/level on top,
 * title below, status + version badges) instead of a WorkspaceTree node, and
 * the empty list vs. empty filter result render through <EmptyState> with
 * distinct text and actions (ch. 12.7/13.3). The page title, always-visible
 * summary and "New Test Case" primary action now live in <PageHeader> at the
 * TestCaseEditors level (ch. 12.1/12.2) — this component only owns
 * search/filter/sort and the row list. Mirrors AdrList/RiskList/IssueList
 * (Tasks 2.1/2.2/2.3).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ListToolbar } from '../shared/ListToolbar';
import { ArtifactRow } from '../shared/ArtifactRow';
import { EmptyState } from '../shared/EmptyState';
import type { TestCase } from '../../api/testcases';
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from '../../utils/workflowStatus';
import styles from './TestCaseList.module.css';

interface TestCaseListProps {
  items: TestCase[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onCreateNew: () => void;
}

type SortKey = 'default' | 'title' | 'status' | 'updated';

function sortItems(list: TestCase[], sortKey: SortKey): TestCase[] {
  const sorted = [...list];
  switch (sortKey) {
    case 'title': sorted.sort((a, b) => a.title.localeCompare(b.title)); break;
    case 'status': {
      sorted.sort(
        (a, b) => compareWorkflowStatus(a.status, b.status) || a.title.localeCompare(b.title),
      );
      break;
    }
    case 'updated': sorted.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')); break;
  }
  return sorted;
}

export function TestCaseList({ items, selectedId, onSelect, onCreateNew }: TestCaseListProps): JSX.Element {
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

  // GH-453: derived from the loaded items, so the option values are exactly
  // the values `it.status !== statusFilter` compares against — for whichever
  // vocabulary this workspace's TestCase workflow uses.
  const statusOptions = useMemo(
    () => buildStatusFilterOptions(items, statusFilter),
    [items, statusFilter],
  );

  const hasActiveListControls = Boolean(listSearch || statusFilter);

  const resetFilters = (): void => {
    setListSearch('');
    setStatusFilter('');
  };

  return (
    <div data-testid="tc-list">
      <ListToolbar
        testIdPrefix="tc-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t('editor.searchPlaceholder', 'Search...')}
        filters={[{
          id: 'status', allLabel: t('editor.allStatuses', 'All Statuses'), value: statusFilter,
          options: statusOptions, onChange: setStatusFilter,
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
          testId="tc-list-empty"
          title={t('testcases.emptyTitle', 'No test cases yet')}
          description={t(
            'testcases.emptyDescription',
            'Test cases verify requirements are met and record how the system was checked.',
          )}
          actions={[{ label: t('testcases.newTestCase', 'New Test Case'), onClick: onCreateNew, testId: 'tc-list-empty-create' }]}
        />
      ) : visible.length === 0 ? (
        // ch. 13.3: "there is something, just not under this filter" — offer
        // only a filter reset, never a create action.
        <EmptyState variant="no-match" testId="tc-list-no-match" onResetFilters={resetFilters} />
      ) : (
        <div className={styles.rows} data-testid="tc-list-rows">
          {visible.map((tc) => (
            <ArtifactRow
              key={tc.id}
              id={tc.uid}
              idFallback={tc.id.slice(0, 8)}
              title={tc.title || t('testcases.untitled', 'Untitled')}
              status={tc.status}
              statusLabel={getWorkflowStatusLabel(tc.status)}
              version={tc.version}
              selected={tc.id === selectedId}
              onClick={() => onSelect(tc.id)}
              testId={`tc-row-${tc.id}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

TestCaseList.displayName = 'TestCaseList';
