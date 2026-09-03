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
 * Delete is triggered per-row via a small "x" button next to each
 * <ArtifactRow> (renderRow below), which opens the shared <ConfirmDialog>
 * (issue #670 — it used to be a hand-built inline confirm banner above the
 * tree). Previously this state (`confirmDeleteId`) had no caller at all,
 * making delete unreachable from the UI (Systemaudit 2026-08-27 UI-05).
 */

import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { usePersistedListState } from '../../hooks/usePersistedListState';
import { useHasRole } from '../../hooks/useHasRole';
import { useWorkspace } from '../../context/WorkspaceContext';
import { ListToolbar } from '../shared/ListToolbar';
import { WorkspaceTree, getTypeBadgeAbbreviation } from '../shared/WorkspaceTree';
import type { WorkspaceTreeNode } from '../shared/WorkspaceTree';
import { ArtifactRow } from '../shared/ArtifactRow';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { EmptyState } from '../shared/EmptyState';
import { Requirement, RequirementType, UUID } from '../../types';
import { REQ_CATEGORIES } from '../../types';
import styles from './RequirementList.module.css';
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
    case 'SyReq': return 'var(--color-reqtype-syreq)';
    case 'UseCase': return 'var(--color-reqtype-usecase)';
    case 'FeatureReq': return 'var(--color-reqtype-featurereq)';
    default:      return 'var(--color-reqtype-default)';
  }
}

/**
 * Contrast-audit follow-up (#140/#161 blast-radius analysis): the badge below
 * used a single hardcoded `color: 'white'` for all 4 background variants
 * above. Recomputed WCAG contrast for the frozen (theme-independent) reqtype
 * palette found white only clears AA on `-default` (gray-600, 7.53:1) —
 * `-syreq`/`-usecase`/`-featurereq` measure 2.54:1/3.96:1/2.15:1 with white,
 * all under the 4.5:1 floor, but clear it with black (8.29:1/5.31:1/9.78:1).
 * Hence a companion text-color lookup instead of a static value.
 */
function getTypeTextColor(type?: RequirementType): string {
  switch (type) {
    case 'SyReq': return 'var(--color-reqtype-syreq-text)';
    case 'UseCase': return 'var(--color-reqtype-usecase-text)';
    case 'FeatureReq': return 'var(--color-reqtype-featurereq-text)';
    default:      return 'var(--color-reqtype-default-text)';
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
        color: getTypeTextColor(req.type),
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
  /**
   * Issue #811: returns whether the delete actually succeeded (2xx) so the
   * confirm dialog below only closes on confirmed success — a rejected
   * delete (e.g. the extended preset's mandatory `change_reason`) must leave
   * the dialog open and the requirement in place.
   */
  onDelete: (id: UUID, changeReason?: string) => Promise<boolean>;
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
  const { activeWorkspace } = useWorkspace();
  // R2/T1 (systemaudit 2026-09-02): a viewer must not see the per-row Delete
  // trigger at all — only the server rejected the delete before. Shared with
  // SidebarNavigation/RequirementForm/RequirementEditors via useHasRole.
  const hasRole = useHasRole();
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  // Issue #811: the extended preset requires a `change_reason` on delete too
  // (RequirementService.delete_requirement) — mirrors RequirementForm's own
  // `isChangeReasonRequired` gate for saves (#339).
  const isChangeReasonRequired = activeWorkspace?.preset === 'extended';
  const [deleteChangeReason, setDeleteChangeReason] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteAttempted, setDeleteAttempted] = useState(false);
  // BUG-19: persisted per tab session (sessionStorage) so navigating away to
  // a detail view and back — or to another route entirely — does not
  // silently discard the user's search/filter/sort selection.
  //
  // Review finding F-02: the key MUST include the active workspace ID.
  // Without it, switching workspaces carried over the PREVIOUS workspace's
  // search/filter/sort selection, making the newly-active workspace look
  // filtered or empty for no visible reason — worse than the original
  // BUG-19 symptom. `usePersistedListState` re-reads sessionStorage
  // whenever this key changes (F-03), so switching workspaces correctly
  // restores that workspace's own last-used selection (or the default, on
  // first visit).
  const workspaceScope = activeWorkspace?.id ?? 'no-workspace';
  const [listSearch, setListSearch] = usePersistedListState(
    `reqlo:list-state:requirements:${workspaceScope}:search`,
    '',
  );
  const [categoryFilter, setCategoryFilter] = usePersistedListState(
    `reqlo:list-state:requirements:${workspaceScope}:category`,
    '',
  );
  const [statusFilter, setStatusFilter] = usePersistedListState(
    `reqlo:list-state:requirements:${workspaceScope}:status`,
    '',
  );
  const [sortKey, setSortKey] = usePersistedListState<ReqSortKey>(
    `reqlo:list-state:requirements:${workspaceScope}:sort`,
    'default',
  );

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

  const closeDeleteDialog = (): void => {
    setConfirmDeleteId(null);
    setDeleteChangeReason('');
    setDeleteAttempted(false);
  };

  /**
   * Issue #811: the dialog used to close as soon as this handler ran,
   * regardless of whether `onDelete` actually succeeded — a rejected delete
   * (e.g. missing `change_reason` under the extended preset) looked
   * identical to a successful one. It now awaits the result and only closes
   * on confirmed success; on failure the dialog stays open (the caller
   * already surfaces the server message via the `req-action-error` banner
   * above this list) so the user can supply the missing reason and retry.
   */
  const handleConfirmDelete = async (): Promise<void> => {
    if (!confirmDeleteId) return;
    if (isChangeReasonRequired && !deleteChangeReason.trim()) {
      setDeleteAttempted(true);
      return;
    }
    setIsDeleting(true);
    try {
      const succeeded = await onDelete(confirmDeleteId, deleteChangeReason.trim() || undefined);
      if (succeeded) {
        closeDeleteDialog();
      }
    } finally {
      setIsDeleting(false);
    }
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

      {/* Issue #670: this used to be a hand-built inline confirm banner above
          the tree — the third of three competing delete interactions in the
          app, and the only one that never used a dialog. It now runs through
          the shared <ConfirmDialog> like every artifact form does, so the
          confirmation looks and behaves the same everywhere. The two button
          testids are preserved verbatim for the existing E2E selectors.

          Side effect: the banner asked for `actions.confirmDeletePrompt`,
          a key that exists in NEITHER locale file (the real one is
          `actions.deleteConfirmPrompt`), so German users were silently shown
          the hardcoded English fallback "Delete this requirement?". The
          dialog uses a real, translated key. */}
      {confirmDeleteId && (
        <ConfirmDialog
          title={t('req.deleteTitle')}
          message={t('actions.deleteConfirmPromptNamed', {
            name: requirements.find((req) => req.id === confirmDeleteId)?.title ?? '',
          })}
          confirmLabel={isDeleting ? t('actions.deleting') : t('actions.delete')}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={closeDeleteDialog}
          isSubmitting={isDeleting}
          testId="req-delete-dialog"
          confirmTestId="req-confirm-delete-btn"
          cancelTestId="req-cancel-delete-btn"
        >
          {/* Issue #811: the extended preset rejects a delete without a
              change_reason server-side, but the dialog never offered a field
              for it — making delete unreachable from the UI for that preset. */}
          {isChangeReasonRequired && (
            <div className={styles.deleteReasonField}>
              <label htmlFor="req-delete-change-reason" className={styles.deleteReasonLabel}>
                {t('req.changeReason')} <span className={styles.requiredMarker}>*</span>
              </label>
              <textarea
                id="req-delete-change-reason"
                data-testid="req-delete-change-reason"
                value={deleteChangeReason}
                onChange={(e) => {
                  setDeleteChangeReason(e.target.value);
                  if (deleteAttempted) setDeleteAttempted(false);
                }}
                placeholder={t('req.changeReasonPlaceholder')}
                disabled={isDeleting}
                aria-invalid={deleteAttempted && !deleteChangeReason.trim()}
                aria-describedby={deleteAttempted && !deleteChangeReason.trim() ? 'req-delete-change-reason-error' : undefined}
                rows={2}
                className={styles.deleteReasonInput}
              />
              {deleteAttempted && !deleteChangeReason.trim() && (
                <p
                  id="req-delete-change-reason-error"
                  role="alert"
                  data-testid="req-delete-change-reason-error"
                  className={styles.deleteReasonError}
                >
                  {t('req.changeReasonRequired')}
                </p>
              )}
            </div>
          )}
        </ConfirmDialog>
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
          // R2/T1: a viewer must not be offered a create action the server
          // would reject — same gate as the per-row Delete trigger below.
          actions={
            hasRole('editor')
              ? [
                  {
                    label: t('requirements.newRequirement'),
                    onClick: onCreateNew,
                    testId: 'req-list-empty-create',
                  },
                ]
              : []
          }
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
              <div style={{ display: 'flex', alignItems: 'center', width: '100%', gap: 'var(--space-1)' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
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
                </div>
                {/* Issue-#-tracked gap (RequirementEditors.test.tsx): the
                    confirm overlay above already exists, but nothing ever
                    called setConfirmDeleteId with a real id — this button is
                    that missing trigger. stopPropagation keeps the click from
                    also selecting the row (the <li> above owns onSelect).
                    R2/T1: rendered conditionally, not just disabled — a
                    viewer must not find this trigger in the DOM at all. */}
                {hasRole('editor') && (
                  <button
                    type="button"
                    data-testid={`req-row-delete-${req.id}`}
                    aria-label={t('actions.delete')}
                    title={t('actions.delete')}
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmDeleteId(req.id);
                    }}
                    style={{
                      flexShrink: 0,
                      width: '22px',
                      height: '22px',
                      padding: 0,
                      border: 'none',
                      background: 'transparent',
                      color: 'var(--color-text-muted)',
                      cursor: 'pointer',
                      fontSize: '0.85rem',
                      lineHeight: 1,
                      borderRadius: 'var(--radius-sm)',
                    }}
                  >
                    ✕
                  </button>
                )}
              </div>
            );
          }}
        />
      )}
    </div>
  );
};

RequirementList.displayName = 'RequirementList';
