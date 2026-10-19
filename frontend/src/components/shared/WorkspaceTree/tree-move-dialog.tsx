/**
 * WorkspaceTree — keyboard-accessible reparenting picker (H-1, SC 2.1.1/2.5.7).
 *
 * Native HTML5 drag & drop has no keyboard trigger, so a drag-only tree offers
 * no way to move a node without a pointer (WCAG 2.1.1 Keyboard) and no
 * single-pointer alternative to dragging (WCAG 2.5.7 Dragging Movements). This
 * dialog is the visible, keyboard-operable path: the row's "Move…" button opens
 * it, the destination parent is chosen in a native `<select>`, and confirming
 * forwards the same `onReparent(draggedId, newParentId)` call the drop handler
 * already makes. Drag & drop stays as an additional shortcut.
 *
 * Candidate parents exclude the node itself and its whole subtree (see
 * `collectSelfAndDescendantIds` — a cycle makes the subtree unreachable); the
 * node's current parent is shown but disabled, because "move to where it
 * already is" would be a no-op.
 *
 * Rendered through the shared `<Dialog>` primitive, which owns the modal
 * semantics, focus trap, Escape handling and focus return. It hands focus to
 * the `<select>` via `initialFocusRef`; the file deliberately carries no
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
  const selectRef = useRef<HTMLSelectElement>(null);
  // The picker starts on the current parent so "nothing selected" is never a
  // state the user can confirm by accident.
  const [targetId, setTargetId] = useState<string>(node.parentId ?? '');

  const forbidden = useMemo(
    () => collectSelfAndDescendantIds(nodes, node.id),
    [nodes, node.id],
  );
  const candidates = useMemo(
    () => nodes.filter((candidate) => !forbidden.has(candidate.id)),
    [nodes, forbidden],
  );

  const unchanged = targetId === (node.parentId ?? '');

  return (
    <Dialog
      title={t('editor.moveNodeTitle')}
      description={t('editor.moveNodeDescription')}
      testId={`${testIdPrefix}-move-dialog`}
      initialFocusRef={selectRef}
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
      <div className={styles.field}>
        <label htmlFor={selectId} className={styles.label}>
          {t('editor.moveNodeTarget')}
        </label>
        <select
          id={selectId}
          ref={selectRef}
          className="field-select"
          data-testid={`${testIdPrefix}-move-target`}
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
        >
          <option value="" disabled={node.parentId === null}>
            {t('editor.moveNodeRoot')}
          </option>
          {candidates.map((candidate) => (
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
      </div>
    </Dialog>
  );
}
