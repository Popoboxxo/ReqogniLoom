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

import React, { useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { X } from 'lucide-react';
import { usePersistedListState } from '../../hooks/usePersistedListState';
import { useHasRole } from '../../hooks/useHasRole';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useArtifactList, artifactId } from '../../hooks/useArtifactList';
import { ListToolbar } from '../shared/ListToolbar';
import {
  WorkspaceTree,
  artifactNodeId,
  getTypeBadgeAbbreviation,
} from '../shared/WorkspaceTree';
import { useWorkspaceLocks } from '../shared/WorkspaceTree/useWorkspaceLocks';
import type {
  WorkspaceTreeGroup,
  WorkspaceTreeNode,
} from '../shared/WorkspaceTree';
import type {
  RequirementAllocationFilter,
  RequirementLevelFilter,
} from './useRequirementData';
import { REQUIREMENT_LEVEL_FILTER_VALUES } from './useRequirementData';
import { ArtifactRow } from '../shared/ArtifactRow';
import type { ArtifactRowAttribute } from '../shared/ArtifactRow';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { EmptyState } from '../shared/EmptyState';
import { FormField } from '../shared/FormField';
import { Requirement, RequirementType, UUID } from '../../types';
import { REQ_CATEGORIES } from '../../types';
import styles from './RequirementList.module.css';
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from '../../utils/workflowStatus';
import { isOutdatedState } from '../../utils/outdatedStates';
import { useRequirementDelete } from './use-requirement-delete';

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
 * P2.7 — the requirement's tier display name.
 *
 * `tier_name` is the resolved label of the workspace ladder and is preferred
 * whenever present; `L${level}` stays the permanent fallback alias for rows
 * whose ladder lookup was unavailable (`tier_name: null`).
 */
function reqTierFull(
  req: Requirement,
  t: TFunction,
): string | undefined {
  if (req.tier_name) return req.tier_name;
  return req.level != null ? t(`reqLevel.L${req.level}`) : undefined;
}

/**
 * Short form used inside the type badge ("<tier> <type>"): the ladder name when
 * available, otherwise the compact `L{n}` alias. No `t()` call is needed for
 * the fallback — the alias is language-independent.
 */
function reqTierPrefix(req: Requirement): string {
  const short = req.tier_name ?? (req.level != null ? `L${req.level}` : '');
  return short ? `${short} ` : '';
}

/**
 * Provenance label for the tier (P2.7 / V6). The backend's `level_source`
 * distinguishes manual overrides from the three derivation rules; a legacy
 * `derived` keeps the pre-P2 wording and an unknown/absent value falls back to
 * "derived" exactly as before.
 */
function reqLevelSourceLabel(
  source: Requirement['level_source'],
  t: TFunction,
): string {
  switch (source) {
    case 'manual':
      return t('reqLevel.manual');
    case 'derived_allocation':
      return t('reqLevel.derivedAllocation');
    case 'derived_hierarchy':
      return t('reqLevel.derivedHierarchy');
    case 'derived_type':
      return t('reqLevel.derivedType');
    case 'unresolved':
      return t('reqLevel.unresolved');
    case 'derived':
    default:
      return t('reqLevel.derived');
  }
}

/**
 * Map a Requirement to a WorkspaceTreeNode with optional parent hierarchy.
 *
 * @param req - Requirement to convert.
 * @param typeLabel - Spelled-out label for `req.type` (e.g. from
 *   `t('reqType.SyReq')`), used as the badge tooltip/aria-label
 *   (issue #169 — "SR" abbreviation without legend).
 * @param levelLabel - Display name of the requirement's tier (P2.7: the
 *   workspace ladder's `tier_name`, falling back to `t('reqLevel.L1')`),
 *   appended to the tooltip (issue #394).
 * @param typeShort - Concise, *evident* badge text for `req.type` (issue
 *   #807, e.g. "System" instead of the cryptic "SR"). Falls back to the
 *   legacy abbreviation when not supplied.
 */
function reqToNode(
  req: Requirement,
  typeLabel?: string,
  levelLabel?: string,
  typeShort?: string,
): WorkspaceTreeNode {
  const badge = req.type
    ? {
        text: reqTierPrefix(req) + (typeShort ?? getTypeBadgeAbbreviation(req.type)),
        bg: getTypeColor(req.type),
        color: getTypeTextColor(req.type),
        title: levelLabel ? `${levelLabel} · ${typeLabel ?? ''}` : typeLabel,
      }
    : undefined;
  return {
    id: req.id,
    // The suspect flag is not part of the tree-label contract: this tree is
    // always rendered through `renderRow` (see below), so `name` is used only
    // for search matching. The visible suspect marker lives on the row itself
    // (<ArtifactRow suspect>, #1092), never as an emoji in this string.
    name: req.title || 'Untitled',
    parentId: req.parent_id ?? null,
    badge,
  };
}

/** Local date (no time) for the row's "Last updated" attribute (issue #804). */
function formatUpdatedAt(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
}

// ---------------------------------------------------------------------------
// Sorting
// ---------------------------------------------------------------------------

type ReqSortKey = 'default' | 'title' | 'status' | 'updated';

/**
 * Persistence guard for the session-stored sort key (`usePersistedListState`'s
 * `options.validate`): a stored JSON string passes the hook's derived `typeof`
 * shape check no matter its value, so a foreign string (e.g. left over from an
 * older build with a renamed sort option) would be adopted as the active sort
 * key — matching no option in the sort select. The union above is the domain
 * contract; anything outside it falls back to the "default" initial value.
 */
function isReqSortKey(value: unknown): value is ReqSortKey {
  return (
    value === 'default' || value === 'title' || value === 'status' || value === 'updated'
  );
}

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
  /**
   * P1 Task 1.7: positional move from the tree (drag drop, Alt+↑/↓ or the
   * "Move…" dialog). The tree forwards node ids — the caller maps them to the
   * backing Artifact ids the move endpoint keys on.
   */
  onReorder?: (
    id: UUID,
    newParentId: UUID | null,
    afterId: UUID | null | undefined,
  ) => Promise<void>;
  /**
   * P6 Task 6.3: the workspace's visual groups, resolved to tree node ids.
   * Supplying them turns on WorkspaceTree's "Gruppen anzeigen" toggle; omitting
   * them keeps the plain requirement tree (and every pre-P6 test) unchanged.
   */
  groups?: WorkspaceTreeGroup[];
  /**
   * P6 Task 6.3: reorder one group member. `afterId` is a requirement node id
   * (the tree's id space); the caller owns the mapping to the membership link
   * ids the REST surface expects.
   */
  onReorderGroupMember?: (
    groupId: string,
    id: string,
    afterId: string | null | undefined,
  ) => Promise<void>;
  /**
   * P6 Task 6.3: the group administration panel (create group, add/remove
   * members). Rendered above the tree as an optional slot so this list stays
   * free of group API state; omitted by every pre-P6 caller.
   */
  groupPanel?: React.ReactNode;
  /**
   * #1668: server-side allocation filter, owned by the container because it
   * drives the list query (`?allocated=`). Rendered here so it sits next to
   * the other list filters; ``all`` is the unfiltered state.
   */
  allocation: RequirementAllocationFilter;
  onAllocationChange: (value: RequirementAllocationFilter) => void;
  /**
   * V6: server-side level filter, owned by the container because it drives the
   * list query (`?level=`). Rendered here next to the other list filters;
   * ``all`` is the unfiltered state.
   */
  level: RequirementLevelFilter;
  onLevelChange: (value: RequirementLevelFilter) => void;
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
  onReorder,
  groups,
  onReorderGroupMember,
  groupPanel,
  allocation,
  onAllocationChange,
  level,
  onLevelChange,
}) => {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  // P4.4: one batch read for the whole tree. Keys are Requirement.id — exactly
  // the node id space this list uses. A failed read yields `{}` (no markers);
  // the backend still rejects a move of a frozen requirement with 409.
  const locks = useWorkspaceLocks(activeWorkspace?.id ?? null, 'requirement');
  // R2/T1 (systemaudit 2026-09-02): a viewer must not see the per-row Delete
  // trigger at all — only the server rejected the delete before. Shared with
  // SidebarNavigation/RequirementForm/RequirementEditors via useHasRole.
  const hasRole = useHasRole();
  // Issue #811: the extended preset requires a `change_reason` on delete too
  // (RequirementService.delete_requirement) — mirrors RequirementForm's own
  // `isChangeReasonRequired` gate for saves (#339).
  const isChangeReasonRequired = activeWorkspace?.preset === 'extended';
  const {
    confirmDeleteId,
    deleteChangeReason,
    isDeleting,
    deleteAttempted,
    requestDelete,
    closeDeleteDialog,
    handleConfirmDelete,
    onReasonChange,
  } = useRequirementDelete({
    onDelete,
    requiresChangeReason: isChangeReasonRequired,
  });
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
  // G1 (audit follow-up): the stored sort key is a string union — the derived
  // shape check is too shallow for it, so `validate` narrows it explicitly
  // (see isReqSortKey).
  const [sortKey, setSortKey] = usePersistedListState<ReqSortKey>(
    `reqlo:list-state:requirements:${workspaceScope}:sort`,
    'default',
    { validate: isReqSortKey },
  );

  // Phase 3a (F-13): same derivation chain as every other editor list —
  // see useArtifactList. `useCallback` keeps each callback's identity tied
  // to its actual dependencies, so the memoized chain only recomputes when
  // the filter values / labels really change.
  const filter = useCallback(
    (req: Requirement, q: string) => {
      if (q && !req.title.toLowerCase().includes(q) && !req.id.toLowerCase().includes(q)) {
        return false;
      }
      if (categoryFilter && req.category !== categoryFilter) return false;
      if (statusFilter && req.status !== statusFilter) return false;
      return true;
    },
    [categoryFilter, statusFilter],
  );

  const toNode = useCallback(
    (req: Requirement) =>
      reqToNode(
        req,
        req.type ? t(`reqType.${req.type}`) : undefined,
        reqTierFull(req, t),
        req.type ? t(`reqTypeShort.${req.type}`) : undefined,
      ),
    [t],
  );

  // Task 3.1: byId is the lookup used by renderRow to hydrate <ArtifactRow>
  // from the WorkspaceTreeNode id — avoids widening WorkspaceTreeNode's
  // shape.
  const { visible: visibleRequirements, treeNodes, byId: reqById } = useArtifactList({
    items: requirements,
    query: listSearch,
    filter,
    sortItems: sortRequirements,
    sortKey,
    toNode,
    getKey: artifactId,
  });

  // P4.4: overlay the batch lock map onto the tree nodes. Kept separate from
  // `toNode` so the pure requirement→node mapping stays independent of a
  // workspace-level read.
  const lockedTreeNodes = useMemo(
    () =>
      treeNodes.map((node) =>
        locks[node.id] ? { ...node, locked: { state: locks[node.id] } } : node,
      ),
    [treeNodes, locks],
  );

  // GH-453: options are derived from the loaded items, so their values are
  // exactly what `req.status !== statusFilter` compares against. Requirement
  // states additionally vary per rigor preset (minimal/standard/extended),
  // which no single hardcoded list could ever cover.
  const statusOptions = useMemo(
    () => buildStatusFilterOptions(requirements, statusFilter),
    [requirements, statusFilter],
  );

  // V6: the four level options are fixed — the backend accepts exactly 1..4
  // (`parse_int_param(..., minimum=1, maximum=4)`) and `level` is derived per
  // ADR-005. Deriving the *set* from the loaded items (as the status filter
  // does) would make a level unselectable exactly when it matters: to show
  // that a level currently has no requirements. Only the *label* is taken
  // from the loaded rows (`tier_name` honours the workspace's terminology
  // profile); `reqLevel.L{n}` stays the permanent alias.
  const levelOptions = useMemo(
    () =>
      REQUIREMENT_LEVEL_FILTER_VALUES.map((value) => {
        const named = requirements.find(
          (req) => String(req.level ?? '') === value && req.tier_name,
        );
        return { value, label: named?.tier_name ?? t(`reqLevel.L${value}`) };
      }),
    [requirements, t],
  );

  const hasActiveListControls = Boolean(
    listSearch ||
      categoryFilter ||
      statusFilter ||
      allocation !== 'all' ||
      level !== 'all',
  );

  const resetFilters = (): void => {
    setListSearch('');
    setCategoryFilter('');
    setStatusFilter('');
    onAllocationChange('all');
    onLevelChange('all');
  };

  return (
    <div>
      {groupPanel}

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
          {
            // V6: server-side V-Modell level filter (`?level=1..4`). Not part of
            // the client-side `filter` chain below: `level` is derived per
            // ADR-005 and the backend owns the predicate.
            id: 'level',
            allLabel: t('editor.allLevels'),
            value: level === 'all' ? '' : level,
            options: levelOptions,
            onChange: (value) =>
              onLevelChange((value || 'all') as RequirementLevelFilter),
          },
          {
            // #1668: server-side allocation filter, not a client-side one —
            // "has an allocated-to link" is only known to the backend.
            id: 'allocation',
            allLabel: t('editor.allAllocations'),
            value: allocation === 'all' ? '' : allocation,
            options: [
              { value: 'allocated', label: t('editor.allocated') },
              { value: 'unallocated', label: t('editor.unallocated') },
            ],
            onChange: (value) =>
              onAllocationChange((value || 'all') as RequirementAllocationFilter),
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
        actions={
          allocation === 'unallocated' ? (
            // #1668: the list is already server-filtered to the unallocated
            // rows, so its length *is* the gap count. Visible only while that
            // filter is active — a permanent "N unallocated" badge on an
            // unfiltered list would be a number without a scope.
            <span
              data-testid="req-list-unallocated-count"
              className={styles.unallocatedCount}
            >
              {t('editor.unallocatedCount', { count: requirements.length })}
            </span>
          ) : undefined
        }
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
              {/* #1393: the marker is the shared `<RequiredMark>` DOM node (not
                  a hand-written `*` span) and the control carries `required` +
                  `aria-required`, consistent with `ArtifactFormActions`. The
                  refusal still comes from `handleConfirmDelete` (the confirm
                  dialog renders no `<form>`, so nothing is browser-validated);
                  the shared `FieldErrorText` renders the message under the
                  control with the same `…-error` id the textarea describes. */}
              <FormField
                htmlFor="req-delete-change-reason"
                label={t('req.changeReason')}
                required
                error={
                  deleteAttempted && !deleteChangeReason.trim()
                    ? t('req.changeReasonRequired')
                    : null
                }
                labelClassName={styles.deleteReasonLabel}
              >
                <textarea
                  id="req-delete-change-reason"
                  data-testid="req-delete-change-reason"
                  value={deleteChangeReason}
                  onChange={(e) => {
                    onReasonChange(e.target.value);
                  }}
                  placeholder={t('req.changeReasonPlaceholder')}
                  disabled={isDeleting}
                  required
                  aria-required="true"
                  aria-invalid={deleteAttempted && !deleteChangeReason.trim()}
                  aria-describedby={deleteAttempted && !deleteChangeReason.trim() ? 'req-delete-change-reason-error' : undefined}
                  rows={2}
                  className={styles.deleteReasonInput}
                />
              </FormField>
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
                    // #797: the same label shape the header's primary create
                    // action uses ("+ {Entity}") — a second wording for the
                    // same action on the same screen was the defect.
                    prefixWithPlus: true,
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
          nodes={lockedTreeNodes}
          selectedId={selectedId}
          onSelect={onSelect}
          // P1 Task 1.7: the requirement tree gains re-parenting + reordering,
          // which it never had (only the architecture tree did).
          onReorder={onReorder}
          groups={groups}
          onReorderGroupMember={onReorderGroupMember}
          showSearch={false}
          // Issue #1257: resolve the configured field selection for this
          // artifact type in this workspace (user > workspace > global).
          itemType="Requirement"
          workspaceId={activeWorkspace?.id ?? null}
          // Issue #665: remember which branches were open so a sidebar section
          // switch (which unmounts this tree) does not reset it.
          stateKey="requirements"
          virtualize
          // Task 3.1: <ArtifactRow>'s multi-line layout (title, labelled
          // identifier, SE-attribute line — issue #804) is taller than
          // WorkspaceTree's default single-line row estimate (34px); override
          // it so virtualized rows (>100 items, REQ-091) don't overlap.
          virtualRowHeight={88}
          emptyLabel={t('editor.empty')}
          noMatchesLabel={t('editor.noMatches')}
          renderRow={(node, { isSelected }) => {
            // P6: a grouped requirement is rendered as a clone with its own
            // synthetic row id; the artifact's own id is `sourceNodeId`.
            const req = reqById?.get(artifactNodeId(node));
            if (!req) return null;
            // Issue #807: a concise, self-explaining type label ("System")
            // instead of the cryptic abbreviation ("SR"); the spelled-out
            // `reqType.*` text stays the tooltip/aria-label.
            const typeShort = req.type ? t(`reqTypeShort.${req.type}`) : undefined;
            // P2.7: ladder display name with the `L${level}` alias as fallback.
            const tier = reqTierFull(req, t);
            // Issue #804: the SE classification a reviewer compares at a
            // glance. Built from fields the list payload already carries —
            // trace-link counts are not part of it, so they are not shown
            // rather than faked.
            const attributes: ArtifactRowAttribute[] = [
              {
                label: t('editor.category'),
                value: req.category
                  ? t(`categories.${req.category}`, { defaultValue: req.category })
                  : null,
              },
              {
                label: t('editor.level'),
                // P2.7: prefer the workspace ladder's display name
                // (`tier_name`); the old `L${level}` alias stays the fallback.
                // #1289: provenance is spelled out so a manual override is
                // distinguishable from every derived rule.
                value: tier
                  ? `${tier} · ${reqLevelSourceLabel(req.level_source, t)}`
                  : null,
              },
              {
                label: t('editor.verificationMethod'),
                value: req.verification_method
                  ? t(`verificationMethod.${req.verification_method}`, {
                      defaultValue: req.verification_method,
                    })
                  : null,
              },
              {
                label: t('editor.complexityFibonacci'),
                value: req.complexity_fibonacci ?? null,
              },
              {
                label: t('editor.sortUpdatedDesc'),
                value: req.updated_at ? formatUpdatedAt(req.updated_at) : null,
              },
            ];
            return (
              <div className={styles.rowWrap}>
                <div className={styles.rowMain}>
                  <ArtifactRow
                    id={req.uid}
                    idFallback={req.id.slice(0, 8)}
                    levelLabel={
                      req.type
                        ? reqTierPrefix(req) + (typeShort ?? getTypeBadgeAbbreviation(req.type))
                        : undefined
                    }
                    levelTitle={
                      req.type
                        ? tier
                          ? `${tier} · ${t(`reqType.${req.type}`)}`
                          : t(`reqType.${req.type}`)
                        : undefined
                    }
                    title={req.title || t('editor.untitled')}
                    suspect={req.suspect}
                    status={req.status}
                    statusLabel={getWorkflowStatusLabel(req.status)}
                    version={req.version}
                    outdated={isOutdatedState(req.status)}
                    attributes={attributes}
                    selected={isSelected}
                    testId={`req-row-${req.id}`}
                  />
                </div>
                {/* Issue-#-tracked gap (RequirementEditors.test.tsx): the
                    confirm overlay above already exists, but nothing ever
                    called the delete request with a real id — this button is
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
                      requestDelete(req.id);
                    }}
                    className={styles.deleteButton}
                  >
                    <X aria-hidden="true" size={14} />
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
