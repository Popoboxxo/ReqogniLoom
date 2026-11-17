/**
 * ARCH-L1-001 ReactFrontend — allocation-tree rows with stable emphasis (UI-009).
 *
 * The row line is the interactive unit of the "Bäume" renderer: hovering or
 * focusing it calls `emphasise(kind, rowId)`. That callback is created once by
 * the renderer (`useCallback`) and passed unchanged to every row; each row owns
 * its `rowId` and calls `emphasise` with it from a handler created INSIDE this
 * component. Previously the inline arrows in the renderer changed identity on
 * every render, so a single hover re-rendered every row (O(N) DOM work, poor
 * INP). `React.memo` now skips a row whose props did not change.
 *
 * Emphasis reaches a row as a primitive boolean, not as the `useMemo` id sets:
 * the set identity changes for all rows on every emphasis switch, whereas the
 * boolean only flips on the row (and the rows at the other end of its edges)
 * that actually changed. Ancestor rows still receive freshly built `children`
 * elements, but their nested rows are memoized too, so no unrelated DOM work
 * is performed.
 *
 * The markup is byte-for-byte the contract the renderer's tests and the edge
 * measurement rely on: `data-emphasized`, `data-alloc-row`, `data-alloc-kind`,
 * class names, `data-testid`s, the disclosure ARIA and the mouse/focus parity.
 */

import { memo, type DragEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronRight, Lock, X } from 'lucide-react';

import type { AllocationRow } from '../../api/allocation-view';
import { isRowLocked, lockStateName } from '../../utils/allocation';
import styles from './AllocationTreesRenderer.module.css';

/** Stable emphasis trigger shared by every memoized row. */
export type Emphasise = (kind: 'requirement' | 'element', id: string) => void;

export interface EmphasisRequirementRowProps {
  rowId: string;
  emphasise: Emphasise;
  /** Primitive: only the emphasised requirements carry `true`. */
  emphasized: boolean;
  row: AllocationRow;
  expanded: boolean;
  hasChildren: boolean;
  selected: boolean;
  targetTitle: string | null;
  targetExternal: boolean;
  canEdit: boolean;
  onToggle: (id: string) => void;
  onDragStart: (row: AllocationRow, event: DragEvent<HTMLElement>) => void;
  onDragEnd: () => void;
  onSelectToggle: (id: string) => void;
  onDeallocateRow: (id: string) => void;
  /** Pre-built `<ul role="group">` subtree (or `null` for a leaf). */
  children?: ReactNode;
}

export interface EmphasisElementRowProps {
  rowId: string;
  emphasise: Emphasise;
  /** Primitive: only the emphasised elements carry `true`. */
  emphasized: boolean;
  row: AllocationRow;
  expanded: boolean;
  hasChildren: boolean;
  isDropTarget: boolean;
  onToggle: (id: string) => void;
  onDragOverElement: (elementId: string, event: DragEvent<HTMLElement>) => void;
  onDragLeaveElement: () => void;
  dropOnElement: (elementId: string, event: DragEvent<HTMLElement>) => void;
  children?: ReactNode;
}

interface RowChromeProps {
  rowId: string;
  expanded: boolean;
  hasChildren: boolean;
  subtreeId: string;
  labelId: string;
  onToggle: (id: string) => void;
}

/** The disclosure toggle (or its inline-size spacer) shared by both columns. */
function RowChrome({
  rowId,
  expanded,
  hasChildren,
  subtreeId,
  labelId,
  onToggle,
}: RowChromeProps): JSX.Element {
  if (!hasChildren) {
    // Same inline size as the toggle so titles line up across levels.
    return <span className={styles.expanderSpacer} aria-hidden="true" />;
  }
  return (
    <button
      type="button"
      className={`btn-ghost ${styles.expander}`}
      aria-expanded={expanded}
      aria-controls={subtreeId}
      aria-labelledby={labelId}
      data-testid={`alloc-expand-${rowId}`}
      onClick={() => onToggle(rowId)}
    >
      <ChevronRight
        aria-hidden="true"
        size={14}
        className={expanded ? styles.iconOpen : styles.icon}
      />
    </button>
  );
}

/**
 * Unmemoized implementation of a requirement row. Exported so tests can wrap
 * it in a render-count spy before `memo` is applied; production uses the
 * `EmphasisRequirementRow` export below.
 */
export function EmphasisRequirementRowView({
  rowId,
  emphasise,
  emphasized,
  row,
  expanded,
  hasChildren,
  selected,
  targetTitle,
  targetExternal,
  canEdit,
  onToggle,
  onDragStart,
  onDragEnd,
  onSelectToggle,
  onDeallocateRow,
  children,
}: EmphasisRequirementRowProps): JSX.Element {
  const { t } = useTranslation();
  const locked = isRowLocked(row.locked);
  const lockedState = lockStateName(row.locked);
  const labelId = `alloc-label-${rowId}`;
  const subtreeId = `alloc-subtree-${rowId}`;

  return (
    <li
      data-testid={`alloc-req-${rowId}`}
      data-locked={locked ? 'true' : 'false'}
      data-selected={selected ? 'true' : 'false'}
      data-emphasized={emphasized ? 'true' : 'false'}
      className={[
        styles.node,
        selected ? styles.nodeSelected : '',
        emphasized ? styles.nodeEmphasized : '',
        locked ? styles.nodeLocked : '',
      ]
        .filter(Boolean)
        .join(' ')}
      draggable={canEdit && !locked}
      onDragStart={(event) => onDragStart(row, event)}
      onDragEnd={onDragEnd}
    >
      {/*
       * The measured line, not the <li>: the <li> also contains the subtree,
       * so its box would centre an edge on the middle of the whole branch.
       */}
      <div
        className={styles.rowLine}
        data-alloc-row={rowId}
        data-alloc-kind="requirement"
        // Emphasis is a visual read help, not an action: hovering and focusing
        // are the two equivalent triggers, neither changes data. The highlight
        // stays after leave, so a click on the row keeps it. The handler is
        // created HERE (once per row render), not inline in the parent.
        onMouseEnter={() => emphasise('requirement', rowId)}
        onFocus={() => emphasise('requirement', rowId)}
      >
        <RowChrome
          rowId={rowId}
          expanded={expanded}
          hasChildren={hasChildren}
          subtreeId={subtreeId}
          labelId={labelId}
          onToggle={onToggle}
        />
        {!row.allocated_to && (
          <span
            className={styles.unallocatedMarker}
            data-testid={`unallocated-marker-${rowId}`}
            title={t('connectionView.unallocated')}
            aria-hidden="true"
          />
        )}
        <input
          type="checkbox"
          id={`alloc-check-${rowId}`}
          data-testid={`alloc-select-${rowId}`}
          checked={selected}
          disabled={locked || !canEdit}
          onChange={() => onSelectToggle(rowId)}
        />
        <label
          htmlFor={`alloc-check-${rowId}`}
          id={labelId}
          className={styles.rowTitle}
          title={row.title}
        >
          {row.title}
        </label>
        {row.tier_name && (
          <span className={styles.badge} data-testid={`alloc-tier-${rowId}`}>
            {row.tier_name}
          </span>
        )}
        {locked && (
          <span
            className={styles.lock}
            data-testid={`alloc-locked-${rowId}`}
            title={lockedState ?? t('connectionView.locked')}
            aria-label={t('connectionView.lockedTooltip', {
              state: lockedState ?? t('connectionView.locked'),
            })}
          >
            <Lock aria-hidden="true" size={12} />
          </span>
        )}
        {canEdit && row.allocation_trace_link_id && (
          <button
            type="button"
            className={`btn-ghost ${styles.rowAction}`}
            data-testid={`alloc-deallocate-${rowId}`}
            aria-label={t('connectionView.trees.deallocate', {
              title: row.title,
            })}
            onClick={() => onDeallocateRow(row.allocation_trace_link_id as string)}
          >
            <X aria-hidden="true" size={12} />
          </button>
        )}
        {/* Last in the row: the target text sits next to the corridor. */}
        <span
          className={`${styles.target} ${targetExternal ? styles.targetExternal : ''}`}
          data-testid={targetExternal ? `alloc-target-external-${rowId}` : `alloc-target-${rowId}`}
          data-external={targetExternal ? 'true' : 'false'}
          title={
            targetExternal
              ? t('connectionView.targetExternal')
              : (targetTitle ?? t('connectionView.unallocated'))
          }
        >
          {targetExternal
            ? t('connectionView.targetExternal')
            : (targetTitle ?? t('connectionView.unallocated'))}
        </span>
      </div>
      {children}
    </li>
  );
}

/** Memoized requirement row: skips DOM work when no relevant prop changed. */
export const EmphasisRequirementRow = memo(EmphasisRequirementRowView);

/**
 * Unmemoized implementation of an element row. See the requirement view for
 * why the implementation is exported separately.
 */
export function EmphasisElementRowView({
  rowId,
  emphasise,
  emphasized,
  row,
  expanded,
  hasChildren,
  isDropTarget,
  onToggle,
  onDragOverElement,
  onDragLeaveElement,
  dropOnElement,
  children,
}: EmphasisElementRowProps): JSX.Element {
  const { t } = useTranslation();
  const locked = isRowLocked(row.locked);
  const labelId = `alloc-label-${rowId}`;
  const subtreeId = `alloc-subtree-${rowId}`;

  return (
    <li
      data-testid={`alloc-el-${rowId}`}
      data-drop-target={isDropTarget ? 'true' : 'false'}
      data-emphasized={emphasized ? 'true' : 'false'}
      className={
        isDropTarget
          ? styles.nodeDropTarget
          : [styles.node, emphasized ? styles.nodeEmphasized : ''].filter(Boolean).join(' ')
      }
      onDragOver={(event) => onDragOverElement(rowId, event)}
      onDragLeave={onDragLeaveElement}
      onDrop={(event) => dropOnElement(rowId, event)}
    >
      {/* Measured line only — see the requirement row's comment. */}
      <div
        className={styles.rowLine}
        data-alloc-row={rowId}
        data-alloc-kind="element"
        onMouseEnter={() => emphasise('element', rowId)}
        onFocus={() => emphasise('element', rowId)}
      >
        <RowChrome
          rowId={rowId}
          expanded={expanded}
          hasChildren={hasChildren}
          subtreeId={subtreeId}
          labelId={labelId}
          onToggle={onToggle}
        />
        <span
          id={labelId}
          className={`${styles.rowTitle} ${styles.elementTitle}`}
          title={row.title}
        >
          {row.title}
        </span>
        {row.type && <span className={styles.badge}>{row.type}</span>}
        {locked && (
          <span
            className={styles.lock}
            data-testid={`alloc-el-locked-${rowId}`}
            title={lockStateName(row.locked) ?? t('connectionView.locked')}
            aria-label={t('connectionView.lockedTooltip', {
              state: lockStateName(row.locked) ?? t('connectionView.locked'),
            })}
          >
            <Lock aria-hidden="true" size={12} />
          </span>
        )}
        {/* The element column has no right-aligned column of its own, so the
            type badge stays next to the title instead of drifting to the far
            edge of the 50%-wide column. */}
        <span className={styles.fill} aria-hidden="true" />
      </div>
      {children}
    </li>
  );
}

/** Memoized element row: skips DOM work when no relevant prop changed. */
export const EmphasisElementRow = memo(EmphasisElementRowView);
