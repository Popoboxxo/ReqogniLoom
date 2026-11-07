/**
 * WorkspaceTree — keyboard-accessible move picker (H-1, SC 2.1.1/2.5.7).
 *
 * Native HTML5 drag & drop has no keyboard trigger, so a drag-only tree offers
 * no way to move a node without a pointer (WCAG 2.1.1 Keyboard) and no
 * single-pointer alternative to dragging (WCAG 2.5.7 Dragging Movements). This
 * dialog is the visible, keyboard-operable path: the row's "Move…" button opens
 * it, the destination parent is chosen from a searchable list, and confirming
 * forwards the same move the drop handler already makes (append as the last
 * child of the chosen parent; the finer position is the Alt+↑/↓ path).
 *
 * Candidate parents exclude the node itself and its whole subtree (see
 * `collectSelfAndDescendantIds` — a cycle makes the subtree unreachable); the
 * node's current parent is shown but disabled, because "move to where it
 * already is" would be a no-op.
 *
 * The search box is a plain filter over the native `<select>`'s options rather
 * than a custom listbox: the select keeps the platform's keyboard selection,
 * type-ahead and screen-reader semantics for free, and the input only narrows
 * which rows it offers.
 *
 * Rendered through the shared `<Dialog>` primitive, which owns the modal
 * semantics, focus trap, Escape handling and focus return. It hands focus to
 * the search input via `initialFocusRef`; the file deliberately carries no
 * native `autoFocus` (one dialog, one focus owner — #1264).
 */

import { useId, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Dialog } from '../Dialog';
import { collectSelfAndDescendantIds } from './tree-hierarchy';
import type { WorkspaceTreeNode } from './workspace-tree';
import styles from './tree-move-dialog.module.css';

export interface TreeMoveDialogProps {
  /** The node being moved. */
  node: WorkspaceTreeNode;
  /** The full flat hierarchy, used to build the candidate list. */
  nodes: readonly WorkspaceTreeNode[];
  /** `data-testid` prefix of the owning tree. */
  testIdPrefix: string;
  /** Dismissed without moving (Escape, backdrop, close, cancel). */
  onClose: () => void;
  /** Confirmed target; `null` means "move to root level". */
  onConfirm: (newParentId: string | null) => void;
}

export function TreeMoveDialog({
  node,
  nodes,
  testIdPrefix,
  onClose,
  onConfirm,
}: TreeMoveDialogProps): JSX.Element | null {
  const { t } = useTranslation();
  const selectId = useId();
  const searchId = useId();
  const searchRef = useRef<HTMLInputElement>(null);
  // The picker starts on the current parent so "nothing selected" is never a
  // state the user can confirm by accident.
  const [targetId, setTargetId] = useState<string>(node.parentId ?? '');
  const [query, setQuery] = useState('');

  const forbidden = useMemo(
    () => collectSelfAndDescendantIds(nodes, node.id),
    [nodes, node.id],
  );
  const candidates = useMemo(
    () => nodes.filter((candidate) => !forbidden.has(candidate.id)),
    [nodes, forbidden],
  );

  /**
   * Search-filtered candidates. The current target is kept in the list even
   * when it does not match, so narrowing the search never silently changes
   * (or blanks) the `<select>`'s selected value.
   */
  const visibleCandidates = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return candidates;
    const matches = candidates.filter(
      (candidate) =>
        candidate.name.toLowerCase().includes(needle) ||
        (candidate.identifier ?? '').toLowerCase().includes(needle),
    );
    if (targetId && !matches.some((candidate) => candidate.id === targetId)) {
      const selected = candidates.find((candidate) => candidate.id === targetId);
      if (selected) return [selected, ...matches];
    }
    return matches;
  }, [candidates, query, targetId]);

  const unchanged = targetId === (node.parentId ?? '');
  const noMatches = visibleCandidates.length === 0;

  return (
    <Dialog
      title={t('editor.moveNodeTitle')}
      description={t('editor.moveNodeDescription')}
      testId={`${testIdPrefix}-move-dialog`}
      initialFocusRef={searchRef}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="btn-ghost"
            data-testid={`${testIdPrefix}-move-cancel`}
            onClick={onClose}
          >
            {t('editor.moveNodeCancel')}
          </button>
          <button
            type="button"
            className="btn-primary"
            data-testid={`${testIdPrefix}-move-confirm`}
            disabled={unchanged}
            onClick={() => onConfirm(targetId === '' ? null : targetId)}
          >
            {t('editor.moveNodeConfirm')}
          </button>
        </>
      }
    >
      <div className={styles.stack}>
      <div className={styles.field}>
        <label htmlFor={searchId} className={styles.label}>
          {t('editor.moveNodeSearch')}
        </label>
        <input
          id={searchId}
          ref={searchRef}
          type="search"
          className="field-input"
          data-testid={`${testIdPrefix}-move-search`}
          value={query}
          placeholder={t('editor.moveNodeSearchPlaceholder')}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label htmlFor={selectId} className={styles.label}>
          {t('editor.moveNodeTarget')}
        </label>
        <select
          id={selectId}
          className="field-select"
          data-testid={`${testIdPrefix}-move-target`}
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
        >
          <option value="" disabled={node.parentId === null}>
            {t('editor.moveNodeRoot')}
          </option>
          {visibleCandidates.map((candidate) => (
            <option
              key={candidate.id}
              value={candidate.id}
              disabled={candidate.id === node.parentId}
            >
              {candidate.identifier
                ? `${candidate.identifier} · ${candidate.name}`
                : candidate.name}
            </option>
          ))}
        </select>
        {noMatches && (
          <p
            className={styles.hint}
            data-testid={`${testIdPrefix}-move-no-matches`}
          >
            {t('editor.moveNodeNoMatches')}
          </p>
        )}
      </div>
      </div>
    </Dialog>
  );
}
