/**
 * P6 Task 6.3 — groups as pseudo-folders in WorkspaceTree.
 *
 * Covers the task's acceptance points:
 *   - the "Gruppen anzeigen" toggle exists only when the caller supplies
 *     `groups`, and is off by default;
 *   - toggling it on renders every group as a collapsible folder with its
 *     members in group order;
 *   - a requirement in several groups appears once per group and is marked;
 *   - dragging inside a group reorders through `onReorderGroupMember`
 *     (never through the artifact `onReorder`);
 *   - toggling it off reproduces the plain tree exactly.
 */

import { describe, it, expect, vi, beforeAll, afterAll } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { WorkspaceTree } from './workspace-tree';
import type { WorkspaceTreeNode, WorkspaceTreeProps } from './workspace-tree';
import type { WorkspaceTreeGroup } from './tree-groups';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: string | Record<string, unknown>) =>
      typeof options === 'string' ? options : key,
  }),
}));

/**
 * jsdom ships no `DragEvent`, so @testing-library falls back to a plain
 * `Event` and drops `clientY`/`dataTransfer` (same shim as the P1 reorder
 * tests — the tree's drop-position contract depends on both).
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

const NODES: WorkspaceTreeNode[] = [
  { id: 'a', name: 'Alpha', parentId: null },
  { id: 'b', name: 'Bravo', parentId: null },
  { id: 'c', name: 'Charlie', parentId: null },
  // Belongs to no group — must stay visible when the group view is on.
  { id: 'd', name: 'Delta', parentId: null },
];

const GROUPS: WorkspaceTreeGroup[] = [
  { id: 'g1', title: 'Gruppe Eins', memberIds: ['a', 'b'] },
  { id: 'g2', title: 'Gruppe Zwei', memberIds: ['a', 'c'] },
];

function renderTree(
  props: Partial<WorkspaceTreeProps> & { nodes: WorkspaceTreeNode[] },
): ReturnType<typeof render> {
  return render(<WorkspaceTree onSelect={vi.fn()} showSearch={false} {...props} />);
}

function row(id: string): HTMLElement {
  return screen.getByTestId(`workspace-tree-node-${id}`);
}

/** Visible row ids in DOM order, with synthetic ids stripped of the testid prefix. */
function renderedOrder(): string[] {
  return screen
    .getAllByRole('treeitem')
    .map((el) =>
      (el.getAttribute('data-testid') ?? '').replace('workspace-tree-node-', '')
    );
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

/** Drop `fromId` on the bottom edge of `toId` (insert directly behind it). */
function dragAfter(fromId: string, toId: string): void {
  const dataTransfer = makeDataTransfer();
  const target = row(toId);
  stubRowBox(target);
  fireEvent.dragStart(row(fromId), { dataTransfer });
  fireEvent.dragOver(target, { dataTransfer, clientY: 95 });
  fireEvent.drop(target, { dataTransfer, clientY: 95 });
}

function toggleGroups(): void {
  fireEvent.click(screen.getByTestId('workspace-tree-groups-toggle'));
}

describe('WorkspaceTree — groups as pseudo-folders (P6 Task 6.3)', () => {
  it('renders no toggle at all when the caller supplies no groups', () => {
    renderTree({ nodes: NODES });
    expect(screen.queryByTestId('workspace-tree-groups-toggle')).toBeNull();
    expect(renderedOrder()).toEqual(['a', 'b', 'c', 'd']);
  });

  it('is off by default and shows the plain tree', () => {
    renderTree({ nodes: NODES, groups: GROUPS });
    expect(screen.getByTestId('workspace-tree-groups-toggle')).not.toBeChecked();
    expect(renderedOrder()).toEqual(['a', 'b', 'c', 'd']);
  });

  it('renders each group as a collapsible folder with its members in order', () => {
    renderTree({ nodes: NODES, groups: GROUPS });
    toggleGroups();

    const g1Folder = row('__group__:g1');
    expect(g1Folder).toHaveAttribute('data-group-folder', 'true');
    expect(screen.getByTestId('workspace-tree-group-title-__group__:g1')).toHaveTextContent(
      'Gruppe Eins'
    );
    // Folders open on the switch, so every member is visible.
    expect(screen.getByTestId('workspace-tree-node-__group__:g1::a')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-tree-node-__group__:g1::b')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-tree-node-__group__:g2::c')).toBeInTheDocument();

    // A requirement in no group keeps its plain row below the folders.
    expect(screen.getByTestId('workspace-tree-node-d')).toBeInTheDocument();

    // Collapsing a folder hides its members but keeps the folder.
    fireEvent.click(screen.getByTestId('workspace-tree-toggle-__group__:g1'));
    expect(screen.queryByTestId('workspace-tree-node-__group__:g1::a')).toBeNull();
    expect(screen.getByTestId('workspace-tree-node-__group__:g1')).toBeInTheDocument();
  });

  it('shows a requirement in several groups multiple times and marks it', () => {
    renderTree({ nodes: NODES, groups: GROUPS });
    toggleGroups();

    // `a` is a member of both groups — two distinct rows.
    const first = screen.getByTestId('workspace-tree-node-__group__:g1::a');
    const second = screen.getByTestId('workspace-tree-node-__group__:g2::a');
    expect(first).toBeInTheDocument();
    expect(second).toBeInTheDocument();
    expect(first).toHaveAttribute('data-group-membership', '2');
    expect(second).toHaveAttribute('data-group-membership', '2');
    // The single-group members carry no marker.
    expect(
      screen.getByTestId('workspace-tree-node-__group__:g1::b')
    ).not.toHaveAttribute('data-group-membership');
  });

  it('reorders a member inside its group through onReorderGroupMember', async () => {
    const onReorder = vi.fn().mockResolvedValue(undefined);
    const onReorderGroupMember = vi.fn().mockResolvedValue(undefined);
    renderTree({
      nodes: NODES,
      groups: GROUPS,
      onReorder,
      onReorderGroupMember,
    });
    toggleGroups();

    // Members are [a, b]; dropping `a` behind `b` is a real order change.
    dragAfter('__group__:g1::a', '__group__:g1::b');

    await waitFor(() =>
      expect(onReorderGroupMember).toHaveBeenCalledWith('g1', 'a', 'b')
    );
    expect(onReorder).not.toHaveBeenCalled();
  });

  it('toggling off restores exactly the previous plain tree', () => {
    renderTree({ nodes: NODES, groups: GROUPS });
    const baseline = renderedOrder();

    toggleGroups();
    expect(renderedOrder()).not.toEqual(baseline);

    toggleGroups();
    expect(renderedOrder()).toEqual(baseline);
    expect(screen.queryByTestId('workspace-tree-node-__group__:g1')).toBeNull();
  });
});
