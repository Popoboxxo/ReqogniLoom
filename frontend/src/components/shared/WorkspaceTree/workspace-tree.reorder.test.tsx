/**
 * P1 Task 1.7 — positional moves in WorkspaceTree.
 *
 * Covers the four acceptance points of the task:
 *   - dropping *between* two rows forwards the correct `afterId`,
 *   - a rejected move rolls the optimistic order back and surfaces the error,
 *   - Alt+↓ moves one sibling step (keyboard alternative to dragging),
 *   - the "Move…" dialog moves the node under a searched-for parent.
 *
 * The reorder contract itself (drop position → `afterId`, keyboard stepping,
 * prediction) is pure and lives in `tree-reorder.ts`; these tests exercise it
 * through the component, which is where the wiring can actually be wrong.
 */

import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { WorkspaceTree } from './workspace-tree';
import type { WorkspaceTreeNode, WorkspaceTreeProps } from './workspace-tree';

vi.mock('react-i18next', () => ({
  // Two call shapes reach the component: `t(key, 'literal fallback')` and
  // `t(key, { interpolation })`. Echoing the key for the object form keeps the
  // mock honest (an object rendered as a React child would throw).
  useTranslation: () => ({
    t: (key: string, options?: string | Record<string, unknown>) =>
      typeof options === 'string' ? options : key,
  }),
}));

/**
 * jsdom ships no `DragEvent`, so @testing-library falls back to a plain `Event`
 * — which silently drops every `MouseEventInit` field, `clientY` included, and
 * with it the whole pointer-position contract. A `MouseEvent` subclass restores
 * the two pieces the tree reads (coordinates and `dataTransfer`).
 */
class DragEventShim extends MouseEvent {
  readonly dataTransfer: unknown;

  constructor(type: string, init: MouseEventInit & { dataTransfer?: unknown } = {}) {
    super(type, init);
    this.dataTransfer = init.dataTransfer;
  }
}

beforeAll(() => {
  (window as unknown as { DragEvent: unknown }).DragEvent = DragEventShim;
});

afterAll(() => {
  delete (window as unknown as { DragEvent?: unknown }).DragEvent;
});

const HIERARCHY: WorkspaceTreeNode[] = [
  { id: 'root', name: 'Root', parentId: null },
  { id: 'a', name: 'Alpha', parentId: 'root' },
  { id: 'b', name: 'Bravo', parentId: 'root' },
  { id: 'c', name: 'Charlie', parentId: 'root' },
];

const FLAT: WorkspaceTreeNode[] = [
  { id: 'a', name: 'Alpha', parentId: null },
  { id: 'b', name: 'Bravo', parentId: null },
  { id: 'c', name: 'Charlie', parentId: null },
];

function renderTree(
  props: Partial<WorkspaceTreeProps> & { nodes: WorkspaceTreeNode[] },
): ReturnType<typeof render> {
  return render(<WorkspaceTree onSelect={vi.fn()} showSearch={false} {...props} />);
}

function row(id: string): HTMLElement {
  return screen.getByTestId(`workspace-tree-node-${id}`);
}

/** Visible row ids in DOM order — the rendered sibling order. */
function renderedOrder(): string[] {
  return screen
    .getAllByRole('treeitem')
    .map((el) => (el.getAttribute('data-testid') ?? '').replace('workspace-tree-node-', ''));
}

function makeDataTransfer(): {
  setData: (format: string, value: string) => void;
  getData: (format: string) => string;
  dropEffect: string;
  effectAllowed: string;
} {
  const store: Record<string, string> = {};
  return {
    setData: (format, value) => {
      store[format] = value;
    },
    getData: (format) => store[format] ?? '',
    dropEffect: '',
    effectAllowed: '',
  };
}

/**
 * jsdom lays every element out at 0×0, so the row has to be given a real box
 * for the pointer position to mean anything. Height 100 keeps the zone
 * boundaries easy to read: y≈5 is the top edge, y≈50 the middle, y≈95 the
 * bottom edge.
 */
function stubRowBox(element: HTMLElement): void {
  Object.defineProperty(element, 'getBoundingClientRect', {
    configurable: true,
    value: () => ({
      top: 0,
      bottom: 100,
      height: 100,
      left: 0,
      right: 0,
      width: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }),
  });
}

function dragOnto(fromId: string, toId: string, clientY: number): void {
  const dataTransfer = makeDataTransfer();
  const target = row(toId);
  stubRowBox(target);
  fireEvent.dragStart(row(fromId), { dataTransfer });
  fireEvent.dragOver(target, { dataTransfer, clientY });
  fireEvent.drop(target, { dataTransfer, clientY });
}

// ---------------------------------------------------------------------------
// Drag & drop position
// ---------------------------------------------------------------------------

describe('WorkspaceTree — reorder by drag & drop (P1 Task 1.7)', () => {
  it('dropping on a row’s bottom edge inserts behind that sibling', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });

    // "Charlie" between "Alpha" and "Bravo".
    dragOnto('c', 'a', 95);

    expect(onReorder).toHaveBeenCalledTimes(1);
    expect(onReorder).toHaveBeenCalledWith('c', 'root', 'a');
  });

  it('dropping on a row’s top edge inserts before it (after the previous sibling)', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });

    dragOnto('c', 'b', 5);

    expect(onReorder).toHaveBeenCalledWith('c', 'root', 'a');
  });

  it('inserting before the first sibling sends an explicit null afterId', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });

    dragOnto('c', 'a', 5);

    expect(onReorder).toHaveBeenCalledWith('c', 'root', null);
  });

  it('dropping on a row’s middle appends as the last child of that row', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: FLAT, onReorder });

    dragOnto('c', 'a', 50);

    // `undefined` — not `null` — is what the API reads as "append at the end"
    // (spec B8). A regression here would silently move the node to the front.
    expect(onReorder).toHaveBeenCalledTimes(1);
    const [, newParentId, afterId] = onReorder.mock.calls[0];
    expect(newParentId).toBe('a');
    expect(afterId).toBeUndefined();
  });

  it('marks the hovered row with the insert position for the drop indicator', () => {
    renderTree({ nodes: HIERARCHY, onReorder: vi.fn().mockResolvedValue(undefined) });

    const dataTransfer = makeDataTransfer();
    const target = row('b');
    stubRowBox(target);
    fireEvent.dragStart(row('c'), { dataTransfer });
    fireEvent.dragOver(target, { dataTransfer, clientY: 95 });

    expect(target).toHaveAttribute('data-drop-target', 'true');
    expect(target).toHaveAttribute('data-drop-position', 'after');
  });

  it('does not forward a move that would not change anything', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });

    // "Bravo" is already directly behind "Alpha".
    dragOnto('b', 'a', 95);

    expect(onReorder).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Optimistic update + rollback
// ---------------------------------------------------------------------------

describe('WorkspaceTree — optimistic reorder and rollback (P1 Task 1.7)', () => {
  it('reorders immediately and keeps the new order when the call succeeds', async () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });

    dragOnto('c', 'a', 95);

    // Before any refetch: the row moved optimistically.
    expect(renderedOrder()).toEqual(['root', 'a', 'c', 'b']);
    await waitFor(() => expect(onReorder).toHaveBeenCalled());
    expect(renderedOrder()).toEqual(['root', 'a', 'c', 'b']);
    expect(screen.queryByTestId('workspace-tree-reorder-error')).not.toBeInTheDocument();
  });

  it('restores the previous order and shows the error when the call fails', async () => {
    const onReorder = vi.fn().mockRejectedValue(new Error('parent is frozen'));
    renderTree({ nodes: HIERARCHY, onReorder });

    dragOnto('c', 'a', 95);

    // Optimistic first...
    expect(renderedOrder()).toEqual(['root', 'a', 'c', 'b']);

    // ...then rolled back to what the server still holds.
    await waitFor(() =>
      expect(screen.getByTestId('workspace-tree-reorder-error')).toHaveTextContent(
        'parent is frozen',
      ),
    );
    expect(renderedOrder()).toEqual(['root', 'a', 'b', 'c']);
  });

  it('picks up the caller’s refetch and drops the stale prediction', async () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderTree({ nodes: HIERARCHY, onReorder });

    dragOnto('c', 'a', 95);
    expect(renderedOrder()).toEqual(['root', 'a', 'c', 'b']);

    // The caller refetched and reports its own (different) truth: that wins.
    const refetched: WorkspaceTreeNode[] = [
      { id: 'root', name: 'Root', parentId: null },
      { id: 'c', name: 'Charlie', parentId: 'root' },
      { id: 'a', name: 'Alpha', parentId: 'root' },
      { id: 'b', name: 'Bravo', parentId: 'root' },
    ];
    rerender(
      <WorkspaceTree nodes={refetched} onSelect={vi.fn()} showSearch={false} onReorder={onReorder} />,
    );

    expect(renderedOrder()).toEqual(['root', 'c', 'a', 'b']);
  });
});

// ---------------------------------------------------------------------------
// Keyboard: Alt+↑ / Alt+↓
// ---------------------------------------------------------------------------

describe('WorkspaceTree — keyboard reordering (P1 Task 1.7)', () => {
  it('Alt+ArrowDown moves the focused row one step down', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });
    fireEvent.click(row('a'));

    fireEvent.keyDown(row('a'), { key: 'ArrowDown', altKey: true });

    expect(onReorder).toHaveBeenCalledTimes(1);
    expect(onReorder).toHaveBeenCalledWith('a', 'root', 'b');
  });

  it('Alt+ArrowUp moves the focused row one step up', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });
    fireEvent.click(row('c'));

    fireEvent.keyDown(row('c'), { key: 'ArrowUp', altKey: true });

    expect(onReorder).toHaveBeenCalledTimes(1);
    // "Charlie" moves above "Bravo", i.e. directly behind "Alpha".
    expect(onReorder).toHaveBeenCalledWith('c', 'root', 'a');
  });

  it('Alt+ArrowUp on the first sibling is a no-op', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });
    fireEvent.click(row('a'));

    fireEvent.keyDown(row('a'), { key: 'ArrowUp', altKey: true });

    expect(onReorder).not.toHaveBeenCalled();
  });

  it('Alt+ArrowDown on the last sibling is a no-op', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });
    fireEvent.click(row('c'));

    fireEvent.keyDown(row('c'), { key: 'ArrowDown', altKey: true });

    expect(onReorder).not.toHaveBeenCalled();
  });

  it('plain ArrowDown still moves focus instead of reordering', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: HIERARCHY, onReorder });
    fireEvent.click(row('a'));

    fireEvent.keyDown(row('a'), { key: 'ArrowDown' });

    expect(onReorder).not.toHaveBeenCalled();
    expect(row('b')).toHaveAttribute('tabindex', '0');
  });

  it('advertises the shortcut on the rows', () => {
    renderTree({ nodes: HIERARCHY, onReorder: vi.fn().mockResolvedValue(undefined) });
    expect(row('a')).toHaveAttribute(
      'aria-keyshortcuts',
      'Alt+ArrowUp Alt+ArrowDown',
    );
  });

  it('does not promise the shortcut on a tree that cannot reorder', () => {
    // A reparent-only consumer still offers the dialog, but no positional
    // move — advertising Alt+↑/↓ there would be a keyboard dead end.
    renderTree({ nodes: FLAT, onReparent: vi.fn() });
    expect(row('a')).not.toHaveAttribute('aria-keyshortcuts');
  });
});

// ---------------------------------------------------------------------------
// "Move…" dialog with parent search
// ---------------------------------------------------------------------------

describe('WorkspaceTree — move dialog with parent search (P1 Task 1.7)', () => {
  const WITH_TWO_PARENTS: WorkspaceTreeNode[] = [
    { id: 'root', name: 'Root', parentId: null },
    { id: 'child', name: 'Child', parentId: 'root' },
    { id: 'other', name: 'Other parent', parentId: null },
    { id: 'third', name: 'Third parent', parentId: null },
  ];

  it('filters the parent options by the search term', () => {
    renderTree({ nodes: WITH_TWO_PARENTS, onReorder: vi.fn().mockResolvedValue(undefined) });
    fireEvent.click(screen.getByTestId('workspace-tree-move-child'));

    const options = (): (string | null)[] =>
      Array.from(
        screen.getByTestId('workspace-tree-move-target').querySelectorAll('option'),
      ).map((option) => option.getAttribute('value'));

    expect(options()).toEqual(['', 'root', 'other', 'third']);

    fireEvent.change(screen.getByTestId('workspace-tree-move-search'), {
      target: { value: 'oth' },
    });

    // 'Root' is the node's current parent, so it stays listed (and disabled)
    // to keep the <select>'s value valid; everything else is filtered.
    expect(options()).toEqual(['', 'root', 'other']);
    expect(
      screen.queryByTestId('workspace-tree-move-no-matches'),
    ).not.toBeInTheDocument();
  });

  it('tells the user when the search matches nothing', () => {
    renderTree({ nodes: WITH_TWO_PARENTS, onReorder: vi.fn().mockResolvedValue(undefined) });
    // A root node has no current parent to keep listed, so the filter can empty
    // the candidate set completely.
    fireEvent.click(screen.getByTestId('workspace-tree-move-root'));

    fireEvent.change(screen.getByTestId('workspace-tree-move-search'), {
      target: { value: 'zzz' },
    });

    expect(screen.getByTestId('workspace-tree-move-no-matches')).toBeInTheDocument();
  });

  it('moves the node under the chosen parent', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: WITH_TWO_PARENTS, onReorder });
    fireEvent.click(screen.getByTestId('workspace-tree-move-child'));

    fireEvent.change(screen.getByTestId('workspace-tree-move-search'), {
      target: { value: 'other' },
    });
    fireEvent.change(screen.getByTestId('workspace-tree-move-target'), {
      target: { value: 'other' },
    });
    fireEvent.click(screen.getByTestId('workspace-tree-move-confirm'));

    expect(onReorder).toHaveBeenCalledTimes(1);
    // The dialog picks a parent, not a position: append at the end.
    const [nodeId, newParentId, afterId] = onReorder.mock.calls[0];
    expect(nodeId).toBe('child');
    expect(newParentId).toBe('other');
    expect(afterId).toBeUndefined();
  });

  it('does not offer the node’s own subtree as a target', () => {
    renderTree({ nodes: WITH_TWO_PARENTS, onReorder: vi.fn().mockResolvedValue(undefined) });
    fireEvent.click(screen.getByTestId('workspace-tree-move-root'));

    const values = Array.from(
      screen.getByTestId('workspace-tree-move-target').querySelectorAll('option'),
    ).map((option) => option.getAttribute('value'));

    expect(values).not.toContain('root');
    expect(values).not.toContain('child');
  });
});
