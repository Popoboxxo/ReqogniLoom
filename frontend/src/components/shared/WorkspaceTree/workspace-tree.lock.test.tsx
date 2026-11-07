/**
 * P4.4 — workflow lock display and move guards in WorkspaceTree.
 *
 * A node whose `locked` field is set (the artifact's current workflow state
 * carries `state_meta.freeze_on_enter`) must:
 *   - render a lock icon whose tooltip names the freezing state,
 *   - never start a drag,
 *   - ignore Alt+↑/↓,
 *   - offer no "Move…" dialog button,
 *   - and, when the backend rejects a move anyway (409 CONFLICT), show the
 *     backend's reason verbatim — the state name — instead of a generic copy.
 *
 * Only the *display* is guarded here: the backend stays the authority for the
 * freeze, which is why a rejected move is still surfaced.
 */

import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { WorkspaceTree } from './workspace-tree';
import type { WorkspaceTreeNode, WorkspaceTreeProps } from './workspace-tree';

vi.mock('react-i18next', () => ({
  // Two call shapes reach the component: `t(key, 'literal fallback')` and
  // `t(key, { interpolation })`. The latter must render the state name so the
  // tooltip assertion is meaningful.
  useTranslation: () => ({
    t: (key: string, options?: string | Record<string, unknown>) => {
      if (typeof options === 'string') return options;
      if (
        options &&
        typeof options === 'object' &&
        typeof options.state === 'string'
      ) {
        return `${key}: ${options.state}`;
      }
      return key;
    },
  }),
}));

/**
 * jsdom ships no `DragEvent`; the same shim as the reorder spec restores the
 * two pieces the tree reads (coordinates and `dataTransfer`).
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

const STATE = 'Freigegeben';

const NODES: WorkspaceTreeNode[] = [
  { id: 'root', name: 'Root', parentId: null },
  { id: 'a', name: 'Alpha', parentId: 'root', locked: { state: STATE } },
  { id: 'b', name: 'Bravo', parentId: 'root' },
  { id: 'c', name: 'Charlie', parentId: 'root' },
];

function renderTree(
  props: Partial<WorkspaceTreeProps> & { nodes: WorkspaceTreeNode[] },
): ReturnType<typeof render> {
  return render(
    <WorkspaceTree
      data-testid="tree"
      onSelect={vi.fn()}
      showSearch={false}
      onReorder={vi.fn().mockResolvedValue(undefined)}
      {...props}
    />,
  );
}

function row(id: string): HTMLElement {
  return screen.getByTestId(`tree-node-${id}`);
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

describe('WorkspaceTree — workflow lock (P4.4)', () => {
  it('renders a lock icon whose tooltip names the freezing state', () => {
    renderTree({ nodes: NODES });

    const marker = screen.getByTestId('tree-lock-a');
    expect(marker).toBeInTheDocument();
    expect(marker).toHaveAttribute('title', expect.stringContaining(STATE));
    expect(marker).toHaveAttribute('aria-label', expect.stringContaining(STATE));

    // Only the locked row carries a marker.
    expect(screen.queryByTestId('tree-lock-b')).not.toBeInTheDocument();
  });

  it('never starts a drag from a locked row', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: NODES, onReorder });

    expect(row('a')).toHaveAttribute('draggable', 'false');
    expect(row('b')).toHaveAttribute('draggable', 'true');

    const dataTransfer = makeDataTransfer();
    const target = row('b');
    stubRowBox(target);
    fireEvent.dragStart(row('a'), { dataTransfer });
    fireEvent.dragOver(target, { dataTransfer, clientY: 95 });
    fireEvent.drop(target, { dataTransfer, clientY: 95 });

    expect(onReorder).not.toHaveBeenCalled();
  });

  it('does not forward Alt+↑/↓ for a locked row', () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    renderTree({ nodes: NODES, onReorder });
    fireEvent.click(row('a'));

    fireEvent.keyDown(row('a'), { key: 'ArrowDown', altKey: true });
    fireEvent.keyDown(row('a'), { key: 'ArrowUp', altKey: true });

    expect(onReorder).not.toHaveBeenCalled();
    // The row does not advertise a shortcut it cannot perform.
    expect(row('a')).not.toHaveAttribute('aria-keyshortcuts');
    expect(row('b')).toHaveAttribute(
      'aria-keyshortcuts',
      'Alt+ArrowUp Alt+ArrowDown',
    );
  });

  it('does not offer the "Move…" dialog on a locked row', () => {
    renderTree({ nodes: NODES });

    expect(screen.queryByTestId('tree-move-a')).not.toBeInTheDocument();
    expect(screen.getByTestId('tree-move-b')).toBeInTheDocument();
  });

  it('shows the backend’s 409 reason (the state name) verbatim', async () => {
    // Shape thrown by apiClient for a non-2xx JSON body (see client.ts).
    const conflict = {
      status: 409,
      error: { code: 'CONFLICT', message: STATE, details: [] },
    };
    const onReorder = vi.fn().mockRejectedValue(conflict);
    renderTree({ nodes: NODES, onReorder });

    // "Charlie" between "Alpha" and "Bravo" — an unlocked row, so the move is
    // forwarded and the backend's refusal is the only thing stopping it.
    const dataTransfer = makeDataTransfer();
    const target = row('a');
    stubRowBox(target);
    fireEvent.dragStart(row('c'), { dataTransfer });
    fireEvent.dragOver(target, { dataTransfer, clientY: 95 });
    fireEvent.drop(target, { dataTransfer, clientY: 95 });

    await waitFor(() =>
      expect(screen.getByTestId('tree-reorder-error')).toHaveTextContent(STATE),
    );
  });
});
