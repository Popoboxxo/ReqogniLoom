/**
 * IssueList — left-panel navigation for issues (REQ-003).
 *
 * Task 2.3 remodel: rows are <ArtifactRow> (ch. 12.3 — id/level on top,
 * title below, status + version badges), and the empty list vs. empty
 * filter result render through <EmptyState> with distinct text and actions
 * (ch. 12.7/13.3). The page title, always-visible summary and "New Issue"
 * primary action now live in <PageHeader> at the IssueEditors level
 * (ch. 12.1/12.2) — this component only owns search/filter/sort and the
 * row list. Mirrors AdrList/RiskList (Tasks 2.1/2.2).
 *
 * Task 4.4 (virtualization ratchet): rows now render through the shared
 * <WorkspaceTree>'s `renderRow` slot instead of a bare `.map()`, so
 * `virtualize` costs one prop — every node is a root (`parentId: null`),
 * mirroring `NeedList`/`AdrList`/`RiskList`.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ListToolbar } from '../shared/ListToolbar';
import { ArtifactRow } from '../shared/ArtifactRow';
import { EmptyState } from '../shared/EmptyState';
import { WorkspaceTree } from '../shared/WorkspaceTree';
import type { WorkspaceTreeNode } from '../shared/WorkspaceTree';
import type { Issue } from '../../types';
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from '../../utils/workflowStatus';

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
      sorted.sort(
        (a, b) => compareWorkflowStatus(a.status, b.status) || a.title.localeCompare(b.title),
      );
      break;
    }
    case 'updated': sorted.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')); break;
  }
  return sorted;
}

/** Map an Issue to a WorkspaceTreeNode (flat — no hierarchy). */
function issueToNode(issue: Issue): WorkspaceTreeNode {
  return { id: issue.id, name: issue.title || 'Untitled', parentId: null };
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

  const treeNodes = useMemo(() => visible.map(issueToNode), [visible]);

  // Task 4.4: lookup used by renderRow to hydrate <ArtifactRow> from the
  // WorkspaceTreeNode id — mirrors RequirementList's reqById.
  const issueById = useMemo(() => {
    const map = new Map<string, Issue>();
    for (const issue of visible) map.set(issue.id, issue);
    return map;
  }, [visible]);

  // GH-453: options are derived from the loaded items, so their values are
  // exactly what `it.status !== statusFilter` compares against — the shared
  // hardcoded list never matched Issue's vocabulary.
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
    <div data-testid="issue-list">
      <ListToolbar
        testIdPrefix="issue-list"
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
          testId="issue-list-empty"
          title={t('issues.emptyTitle', 'No issues yet')}
          description={t(
            'issues.emptyDescription',
            'Issues track defects, improvements and open questions for this workspace.',
          )}
          actions={[
            {
              // #594 / issue #719: same "+ " gesture marker as the PageHeader
              // primary action that triggers the identical create flow.
              label: t('issues.newIssue', 'New Issue'),
              prefixWithPlus: true,
              onClick: onCreateNew,
              testId: 'issue-list-empty-create',
            },
          ]}
        />
      ) : visible.length === 0 ? (
        // ch. 13.3: "there is something, just not under this filter" — offer
        // only a filter reset, never a create action.
        <EmptyState variant="no-match" testId="issue-list-no-match" onResetFilters={resetFilters} />
      ) : (
        // Task 4.4: WorkspaceTree owns virtualization; rows are <ArtifactRow>
        // via renderRow, same as RequirementList.
        <WorkspaceTree
          data-testid="issue-list-rows"
          nodes={treeNodes}
          selectedId={selectedId}
          onSelect={onSelect}
          showSearch={false}
          virtualize
          // <ArtifactRow>'s two-line id/title layout is taller than
          // WorkspaceTree's default single-line row estimate (34px).
          virtualRowHeight={64}
          emptyLabel={t('editor.empty', 'No items.')}
          noMatchesLabel={t('editor.noMatches', 'No matches found.')}
          renderRow={(node, { isSelected }) => {
            const issue = issueById.get(node.id);
            if (!issue) return null;
            return (
              <ArtifactRow
                id={issue.uid}
                idFallback={issue.id.slice(0, 8)}
                title={issue.title || t('issues.untitled', 'Untitled')}
                status={issue.status}
                statusLabel={getWorkflowStatusLabel(issue.status)}
                version={issue.version}
                selected={isSelected}
                testId={`issue-row-${issue.id}`}
              />
            );
          }}
        />
      )}
    </div>
  );
}

IssueList.displayName = 'IssueList';
