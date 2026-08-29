/**
 * WorkspaceTree unit tests — REQ-003 (Einheitliches Tree-Modul).
 *
 * Covers:
 *   - Flat node rendering
 *   - Hierarchical node rendering with expand/collapse
 *   - Click-to-select (onSelect callback)
 *   - Selected node highlighting (aria-selected)
 *   - Built-in search filter (text match + parent visibility)
 *   - Empty state label
 *   - No-matches label after search
 *   - Level badge rendering (showLevelBadge)
 *   - Status badge rendering (node.badge)
 *   - onAddChild button per node
 */

import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import {
  act,
  createEvent,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkspaceTree } from './workspace-tree';
import type { WorkspaceTreeNode, WorkspaceTreeProps } from './workspace-tree';

// Issue #676: WorkspaceTree resolves its own label defaults through i18n now,
// so `t` has to exist. Echoing the key back (repo-wide test convention, cf.
// `create-trace-link-dialog.test.tsx`) keeps the assertions below able to
// prove *which* key a default came from.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback ?? key }),
}));

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const FLAT_NODES: WorkspaceTreeNode[] = [
  { id: 'n1', name: 'Alpha Need', parentId: null },
  { id: 'n2', name: 'Beta Need', parentId: null },
  { id: 'n3', name: 'Gamma Need', parentId: null },
];

const TREE_NODES: WorkspaceTreeNode[] = [
  { id: 'root', name: 'L0 System', parentId: null, level: 'L0' },
  { id: 'child1', name: 'L1 Subsystem A', parentId: 'root', level: 'L1' },
  { id: 'child2', name: 'L1 Subsystem B', parentId: 'root', level: 'L1' },
  { id: 'grandchild', name: 'L2 Component', parentId: 'child1', level: 'L2' },
];

const BADGE_NODES: WorkspaceTreeNode[] = [
  {
    id: 'b1',
    name: 'Open Risk',
    parentId: null,
    badge: { text: 'open', bg: 'rgba(255,255,255,0.1)', color: '#cbd5e1' },
  },
  {
    id: 'b2',
    name: 'Approved ADR',
    parentId: null,
    badge: { text: 'approved', bg: 'rgba(16,185,129,0.2)', color: '#6ee7b7' },
  },
];

// ---------------------------------------------------------------------------
// Render helper (showSearch=false so callers can test node rendering cleanly)
// ---------------------------------------------------------------------------

function renderTree(
  props: Partial<WorkspaceTreeProps> & { nodes: WorkspaceTreeNode[] },
): ReturnType<typeof render> {
  return render(
    <WorkspaceTree
      onSelect={vi.fn()}
      showSearch={false}
      {...props}
    />,
  );
}

// ---------------------------------------------------------------------------
// Fake timer cleanup — prevent leaked timers from blocking subsequent tests
// ---------------------------------------------------------------------------

afterEach(() => {
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------
// Flat list rendering
// ---------------------------------------------------------------------------

describe('WorkspaceTree — flat nodes', () => {
  it('renders all flat nodes', () => {
    renderTree({ nodes: FLAT_NODES });
    expect(screen.getByText('Alpha Need')).toBeInTheDocument();
    expect(screen.getByText('Beta Need')).toBeInTheDocument();
    expect(screen.getByText('Gamma Need')).toBeInTheDocument();
  });

  it('flat nodes have no expand toggle', () => {
    renderTree({ nodes: FLAT_NODES });
    expect(
      screen.queryByTestId('workspace-tree-toggle-n1'),
    ).not.toBeInTheDocument();
  });

  it('renders with role="tree" and role="treeitem"', () => {
    renderTree({ nodes: FLAT_NODES });
    expect(screen.getByRole('tree')).toBeInTheDocument();
    expect(screen.getAllByRole('treeitem')).toHaveLength(3);
  });

  it('shows empty label when nodes array is empty', () => {
    renderTree({ nodes: [], emptyLabel: 'Nothing here yet.' });
    expect(screen.getByText('Nothing here yet.')).toBeInTheDocument();
    expect(screen.queryByRole('tree')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Issue #676 — translated label defaults (no hardcoded English fallbacks)
// ---------------------------------------------------------------------------

describe('WorkspaceTree — i18n label defaults (#676)', () => {
  it('falls back to the editor.empty key when no emptyLabel is passed', () => {
    renderTree({ nodes: [] });
    expect(screen.getByTestId('workspace-tree-empty')).toHaveTextContent(
      'editor.empty',
    );
  });

  it('falls back to the editor.searchPlaceholder key for the built-in search', () => {
    render(<WorkspaceTree nodes={FLAT_NODES} onSelect={vi.fn()} showSearch />);
    expect(screen.getByTestId('workspace-tree-search')).toHaveAttribute(
      'placeholder',
      'editor.searchPlaceholder',
    );
  });

  it('uses translated accessible names for the chevron and add-child buttons', () => {
    renderTree({ nodes: TREE_NODES, onAddChild: vi.fn() });
    // Roots auto-expand, so the root chevron reads as "collapse".
    expect(screen.getByTestId('workspace-tree-toggle-root')).toHaveAttribute(
      'aria-label',
      'editor.collapseNode',
    );
    expect(screen.getByTestId('workspace-tree-add-child-root')).toHaveAttribute(
      'aria-label',
      'editor.addChild',
    );
  });
});

// ---------------------------------------------------------------------------
// Node selection
// ---------------------------------------------------------------------------

describe('WorkspaceTree — selection', () => {
  it('calls onSelect with node id on click', async () => {
    const onSelect = vi.fn();
    renderTree({ nodes: FLAT_NODES, onSelect });
    await userEvent.click(screen.getByText('Beta Need'));
    expect(onSelect).toHaveBeenCalledWith('n2');
  });

  it('marks selected node with aria-selected=true', () => {
    renderTree({ nodes: FLAT_NODES, selectedId: 'n1' });
    const selected = screen.getByTestId('workspace-tree-node-n1');
    expect(selected).toHaveAttribute('aria-selected', 'true');
  });

  it('non-selected nodes have aria-selected=false', () => {
    renderTree({ nodes: FLAT_NODES, selectedId: 'n1' });
    const notSelected = screen.getByTestId('workspace-tree-node-n2');
    expect(notSelected).toHaveAttribute('aria-selected', 'false');
  });
});

// ---------------------------------------------------------------------------
// Issue #665 — a selection made outside the tree is revealed inside it
// ---------------------------------------------------------------------------

describe('WorkspaceTree — reveals an externally made selection (#665)', () => {
  it('expands the ancestor path of a deeply selected node', async () => {
    renderTree({ nodes: TREE_NODES, selectedId: 'grandchild' });

    // `grandchild` sits two levels down; only roots auto-expand, so without
    // the reveal effect it would stay hidden inside a collapsed `child1`.
    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-grandchild')).toBeInTheDocument();
    });
    expect(screen.getByTestId('workspace-tree-node-child1')).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('reveals a selection that arrives before the nodes have loaded', async () => {
    const { rerender } = render(
      <WorkspaceTree nodes={[]} onSelect={vi.fn()} showSearch={false} selectedId="grandchild" />,
    );
    expect(screen.queryByTestId('workspace-tree-node-grandchild')).not.toBeInTheDocument();

    rerender(
      <WorkspaceTree
        nodes={TREE_NODES}
        onSelect={vi.fn()}
        showSearch={false}
        selectedId="grandchild"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-grandchild')).toBeInTheDocument();
    });
  });

  it('does not re-expand a path the user collapsed by hand', async () => {
    renderTree({ nodes: TREE_NODES, selectedId: 'grandchild' });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-grandchild')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('workspace-tree-toggle-child1'));

    // The selection has not changed, so the reveal must not fire again and
    // fight the collapse the user just performed.
    expect(
      screen.queryByTestId('workspace-tree-node-grandchild'),
    ).not.toBeInTheDocument();
  });

  it('re-reveals a previously collapsed path when the selection returns to it', async () => {
    const renderAt = (selectedId: string): JSX.Element => (
      <WorkspaceTree
        nodes={TREE_NODES}
        onSelect={vi.fn()}
        showSearch={false}
        selectedId={selectedId}
      />
    );
    const { rerender } = render(renderAt('grandchild'));
    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-grandchild')).toBeInTheDocument();
    });

    // User collapses the revealed path again, then navigates elsewhere.
    await userEvent.click(screen.getByTestId('workspace-tree-toggle-child1'));
    expect(screen.queryByTestId('workspace-tree-node-grandchild')).not.toBeInTheDocument();
    rerender(renderAt('child2'));
    expect(screen.queryByTestId('workspace-tree-node-grandchild')).not.toBeInTheDocument();

    // Coming back to the hidden node must open the path a second time —
    // "already revealed once" must not be sticky per node id.
    rerender(renderAt('grandchild'));
    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-grandchild')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Issue #668 — collapsed ancestor marks a hidden selection
// ---------------------------------------------------------------------------

describe('WorkspaceTree — hidden-selection marker (#668)', () => {
  /** Collapses `child1`, which holds the selected `grandchild`. */
  async function renderWithCollapsedSelectedParent(): Promise<void> {
    renderTree({ nodes: TREE_NODES, selectedId: 'grandchild' });
    // #665: the selected grandchild's ancestors auto-expand, so `child1` is
    // reachable and expanded before the user collapses it again by hand.
    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-grandchild')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId('workspace-tree-toggle-child1'));
  }

  it('marks a collapsed parent that hides the selected node', async () => {
    await renderWithCollapsedSelectedParent();

    expect(
      screen.queryByTestId('workspace-tree-node-grandchild'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('workspace-tree-node-child1')).toHaveAttribute(
      'data-contains-selection',
      'true',
    );
  });

  it('marks every collapsed ancestor, not just the direct parent', async () => {
    await renderWithCollapsedSelectedParent();
    // Collapsing the root as well hides `child1` itself; the root then has to
    // carry the marker or the selection becomes invisible again.
    await userEvent.click(screen.getByTestId('workspace-tree-toggle-root'));

    expect(screen.queryByTestId('workspace-tree-node-child1')).not.toBeInTheDocument();
    expect(screen.getByTestId('workspace-tree-node-root')).toHaveAttribute(
      'data-contains-selection',
      'true',
    );
  });

  it('does not mark an expanded ancestor — the selection is visible there', async () => {
    renderTree({ nodes: TREE_NODES, selectedId: 'grandchild' });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-grandchild')).toBeInTheDocument();
    });

    expect(
      screen.getByTestId('workspace-tree-node-child1'),
    ).not.toHaveAttribute('data-contains-selection');
    expect(
      screen.getByTestId('workspace-tree-node-root'),
    ).not.toHaveAttribute('data-contains-selection');
  });

  it('never marks the selected node itself', () => {
    renderTree({ nodes: TREE_NODES, selectedId: 'root' });
    expect(
      screen.getByTestId('workspace-tree-node-root'),
    ).not.toHaveAttribute('data-contains-selection');
  });

  it('marks nothing when a sibling subtree is collapsed', async () => {
    renderTree({ nodes: TREE_NODES, selectedId: 'child2' });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-child1')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByTestId('workspace-tree-toggle-child1'));

    expect(
      screen.getByTestId('workspace-tree-node-child1'),
    ).not.toHaveAttribute('data-contains-selection');
  });
});

// ---------------------------------------------------------------------------
// Hierarchical expand / collapse
// ---------------------------------------------------------------------------

describe('WorkspaceTree — hierarchical expand/collapse', () => {
  it('renders root node immediately', () => {
    renderTree({ nodes: TREE_NODES });
    // Root is always visible at depth 0 regardless of expand state
    expect(screen.getByText('L0 System')).toBeInTheDocument();
  });

  it('root node has expand toggle', () => {
    renderTree({ nodes: TREE_NODES });
    expect(screen.getByTestId('workspace-tree-toggle-root')).toBeInTheDocument();
  });

  it('children are visible after root auto-expands on first render', async () => {
    renderTree({ nodes: TREE_NODES });
    // useEffect auto-expands roots asynchronously after first render
    await waitFor(() => {
      expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument();
      expect(screen.getByText('L1 Subsystem B')).toBeInTheDocument();
    });
  });

  it('collapse toggle hides children', async () => {
    const user = userEvent.setup();
    renderTree({ nodes: TREE_NODES });

    // Wait for auto-expand
    await waitFor(() =>
      expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument(),
    );

    // Collapse root
    await user.click(screen.getByTestId('workspace-tree-toggle-root'));

    expect(screen.queryByText('L1 Subsystem A')).not.toBeInTheDocument();
    expect(screen.queryByText('L1 Subsystem B')).not.toBeInTheDocument();
  });

  it('expand toggle after collapse shows children again', async () => {
    const user = userEvent.setup();
    renderTree({ nodes: TREE_NODES });

    await waitFor(() =>
      expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument(),
    );

    // Collapse
    await user.click(screen.getByTestId('workspace-tree-toggle-root'));
    expect(screen.queryByText('L1 Subsystem A')).not.toBeInTheDocument();

    // Expand again
    await user.click(screen.getByTestId('workspace-tree-toggle-root'));
    await waitFor(() =>
      expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument(),
    );
  });

  it('toggle click does not trigger onSelect', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    renderTree({ nodes: TREE_NODES, onSelect });

    await user.click(screen.getByTestId('workspace-tree-toggle-root'));
    expect(onSelect).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Built-in search
// ---------------------------------------------------------------------------

describe('WorkspaceTree — internal search', () => {
  it('renders search box when showSearch=true', () => {
    render(<WorkspaceTree nodes={FLAT_NODES} onSelect={vi.fn()} showSearch={true} />);
    expect(screen.getByTestId('workspace-tree-search')).toBeInTheDocument();
  });

  it('does not render search box when showSearch=false', () => {
    renderTree({ nodes: FLAT_NODES });
    expect(screen.queryByTestId('workspace-tree-search')).not.toBeInTheDocument();
  });

  it('filters nodes after 300ms debounce', async () => {
    vi.useFakeTimers();

    render(<WorkspaceTree nodes={FLAT_NODES} onSelect={vi.fn()} showSearch={true} />);

    const input = screen.getByTestId('workspace-tree-search');
    fireEvent.change(input, { target: { value: 'Alpha' } });

    // Before debounce — all nodes still visible (query is not yet committed)
    expect(screen.getByText('Beta Need')).toBeInTheDocument();

    // Advance past debounce and flush React state update
    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    expect(screen.getByText('Alpha Need')).toBeInTheDocument();
    expect(screen.queryByText('Beta Need')).not.toBeInTheDocument();
    expect(screen.queryByText('Gamma Need')).not.toBeInTheDocument();

    vi.useRealTimers();
  });

  it('shows no-matches label when search has no results', async () => {
    vi.useFakeTimers();

    render(
      <WorkspaceTree
        nodes={FLAT_NODES}
        onSelect={vi.fn()}
        showSearch={true}
        noMatchesLabel="Keine Treffer."
      />,
    );

    fireEvent.change(screen.getByTestId('workspace-tree-search'), {
      target: { value: 'xyzzy_nonexistent' },
    });

    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    expect(screen.getByText('Keine Treffer.')).toBeInTheDocument();

    vi.useRealTimers();
  });

  it('search keeps parent visible when child matches', async () => {
    vi.useFakeTimers();

    render(
      <WorkspaceTree nodes={TREE_NODES} onSelect={vi.fn()} showSearch={true} />,
    );

    // Wait for auto-expand effect — with fake timers, React state updates via
    // useEffect still flush synchronously through act.
    await act(async () => {
      // useEffect for auto-expand fires after render
    });

    fireEvent.change(screen.getByTestId('workspace-tree-search'), {
      target: { value: 'Component' },
    });

    await act(async () => {
      vi.advanceTimersByTime(350);
    });

    // "L2 Component" matches — its ancestors must stay visible
    expect(screen.getByText('L2 Component')).toBeInTheDocument();
    expect(screen.getByText('L0 System')).toBeInTheDocument();
    expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument();
    // Sibling branch not on path to match — hidden
    expect(screen.queryByText('L1 Subsystem B')).not.toBeInTheDocument();

    vi.useRealTimers();
  });
});

// ---------------------------------------------------------------------------
// Level badge (showLevelBadge)
// ---------------------------------------------------------------------------

describe('WorkspaceTree — level badge', () => {
  it('renders level badge for root when showLevelBadge=true', () => {
    // Root node is always visible at depth 0 — no waitFor needed
    renderTree({ nodes: TREE_NODES, showLevelBadge: true });
    expect(screen.getByTestId('workspace-tree-level-root')).toHaveTextContent('L0');
  });

  it('does not render level badge when showLevelBadge=false (default)', () => {
    renderTree({ nodes: TREE_NODES });
    // Root is visible immediately; badge should be absent
    expect(screen.getByText('L0 System')).toBeInTheDocument();
    expect(
      screen.queryByTestId('workspace-tree-level-root'),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Status / type badge (node.badge)
// ---------------------------------------------------------------------------

describe('WorkspaceTree — status badge', () => {
  it('renders badge text when node.badge is provided', () => {
    renderTree({ nodes: BADGE_NODES });
    expect(screen.getByTestId('workspace-tree-badge-b1')).toHaveTextContent('open');
    expect(screen.getByTestId('workspace-tree-badge-b2')).toHaveTextContent('approved');
  });

  it('does not render badge element when node.badge is absent', () => {
    renderTree({ nodes: FLAT_NODES });
    expect(
      screen.queryByTestId('workspace-tree-badge-n1'),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// onAddChild button
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Virtualization opt-in (REQ-091)
// ---------------------------------------------------------------------------

describe('WorkspaceTree — virtualization (REQ-091)', () => {
  // 120 flat nodes → exceeds the 100-item threshold.
  const LARGE_NODES: WorkspaceTreeNode[] = Array.from({ length: 120 }, (_, i) => ({
    id: `v${i}`,
    name: `Node ${i}`,
    parentId: null,
  }));

  it('renders the virtualized scroll container when virtualize=true and rows exceed threshold', () => {
    renderTree({ nodes: LARGE_NODES, virtualize: true });
    expect(screen.getByTestId('workspace-tree-scroll')).toBeInTheDocument();
  });

  it('does not virtualize small lists even when virtualize=true', () => {
    renderTree({ nodes: FLAT_NODES, virtualize: true });
    // 3 nodes < 100 threshold → normal rendering, no scroll container
    expect(screen.queryByTestId('workspace-tree-scroll')).not.toBeInTheDocument();
    expect(screen.getAllByRole('treeitem')).toHaveLength(3);
  });

  it('does not virtualize large lists when virtualize is not opted in', () => {
    renderTree({ nodes: LARGE_NODES });
    expect(screen.queryByTestId('workspace-tree-scroll')).not.toBeInTheDocument();
  });

  it('mounts far fewer DOM rows than total nodes when virtualized', () => {
    // jsdom reports 0 layout height, so the virtualizer windows down to a small
    // subset — the key guarantee: not all 120 rows hit the DOM at once.
    renderTree({ nodes: LARGE_NODES, virtualize: true });
    expect(screen.queryAllByRole('treeitem').length).toBeLessThan(
      LARGE_NODES.length,
    );
  });
});

// ---------------------------------------------------------------------------
// Task 4.1: ARIA treeview keyboard navigation
// ---------------------------------------------------------------------------

describe('WorkspaceTree — keyboard navigation', () => {
  // Flat list (no expand/collapse) plus a hierarchical branch, so ↑/↓/Home/End
  // and letter-jump can be exercised on a simple list while →/←/* get a real
  // parent/child/sibling structure.
  const KB_FLAT: WorkspaceTreeNode[] = [
    { id: 'k1', name: 'Alpha', parentId: null },
    { id: 'k2', name: 'Bravo', parentId: null },
    { id: 'k3', name: 'Charlie', parentId: null },
    { id: 'k4', name: 'Another Alpha-like', parentId: null },
  ];

  const KB_TREE: WorkspaceTreeNode[] = [
    { id: 'root', name: 'Root', parentId: null },
    { id: 'child-a', name: 'Child A', parentId: 'root' },
    { id: 'child-b', name: 'Child B', parentId: 'root' },
    { id: 'grandchild', name: 'Grandchild', parentId: 'child-a' },
  ];

  // Dispatches a keydown on the tree's root <ul role="tree"> — where the
  // keyboard handler is actually attached. It does NOT depend on which
  // element holds real DOM focus: the handler reads its "current item" from
  // WorkspaceTree's own `focusedId` state (the roving-tabindex source of
  // truth), exactly like a real browser event bubbling up from whichever
  // <li> has tabIndex=0 and real focus. Using `.focus()` on an arbitrary row
  // to fake a starting position does NOT update that state, so this helper
  // drives navigation with real ArrowDown/ArrowUp presses instead — the only
  // way to move `focusedId` (and real DOM focus, via `focusRowAtIndex`) is
  // through the component's own handler.
  //
  // Before the very first key press nothing has real DOM focus yet (a real
  // user would have Tab-ed into the tree, landing on whichever row already
  // carries tabIndex=0 — the same row `effectiveFocusedId` designates). We
  // replicate that one-time "tab into the tree" step here so genuine no-op
  // keys (e.g. ArrowRight on a leaf) can be asserted to *retain* focus
  // rather than comparing against an unfocused document.body.
  function pressKey(key: string): void {
    const tree = screen.getByRole('tree');
    if (!tree.contains(document.activeElement)) {
      tree.querySelector<HTMLElement>('[tabindex="0"]')?.focus();
    }
    fireEvent.keyDown(tree, { key });
  }

  it('ArrowDown moves focus to the next visible item', () => {
    renderTree({ nodes: KB_FLAT });
    // Default focus target is the first visible row (k1) before any key press.
    pressKey('ArrowDown');
    expect(screen.getByTestId('workspace-tree-node-k2')).toHaveFocus();
  });

  it('ArrowDown at the last item stays on the last item', () => {
    renderTree({ nodes: KB_FLAT });
    pressKey('ArrowDown');
    pressKey('ArrowDown');
    pressKey('ArrowDown'); // now at k4 (last)
    pressKey('ArrowDown'); // no-op, clamped
    expect(screen.getByTestId('workspace-tree-node-k4')).toHaveFocus();
  });

  it('ArrowUp moves focus to the previous visible item', () => {
    renderTree({ nodes: KB_FLAT });
    pressKey('ArrowDown'); // k1 -> k2
    pressKey('ArrowUp'); // k2 -> k1
    expect(screen.getByTestId('workspace-tree-node-k1')).toHaveFocus();
  });

  it('ArrowUp at the first item stays on the first item', () => {
    renderTree({ nodes: KB_FLAT });
    pressKey('ArrowUp'); // already at k1, clamped
    expect(screen.getByTestId('workspace-tree-node-k1')).toHaveFocus();
  });

  it('ArrowRight on a collapsed parent expands it without moving focus', async () => {
    renderTree({ nodes: KB_TREE });
    // Collapse root first (it auto-expands on mount). Default focus is root.
    await waitFor(() => expect(screen.getByText('Child A')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('workspace-tree-toggle-root'));
    expect(screen.queryByText('Child A')).not.toBeInTheDocument();

    pressKey('ArrowRight');

    expect(screen.getByText('Child A')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-tree-node-root')).toHaveFocus();
  });

  it('ArrowRight on an already-expanded parent moves focus to its first child', async () => {
    renderTree({ nodes: KB_TREE });
    await waitFor(() => expect(screen.getByText('Child A')).toBeInTheDocument());

    pressKey('ArrowRight'); // root is expanded -> move to first child

    expect(screen.getByTestId('workspace-tree-node-child-a')).toHaveFocus();
  });

  it('ArrowRight on a leaf is a no-op', () => {
    renderTree({ nodes: KB_FLAT });
    pressKey('ArrowRight'); // k1 is a leaf
    expect(screen.getByTestId('workspace-tree-node-k1')).toHaveFocus();
  });

  it('ArrowLeft on an expanded parent collapses it without moving focus', async () => {
    renderTree({ nodes: KB_TREE });
    await waitFor(() => expect(screen.getByText('Child A')).toBeInTheDocument());

    pressKey('ArrowLeft'); // root is expanded -> collapse

    expect(screen.queryByText('Child A')).not.toBeInTheDocument();
    expect(screen.getByTestId('workspace-tree-node-root')).toHaveFocus();
  });

  it('ArrowLeft on a collapsed/leaf child moves focus to its parent', async () => {
    renderTree({ nodes: KB_TREE });
    await waitFor(() => expect(screen.getByText('Child B')).toBeInTheDocument());

    pressKey('ArrowRight'); // root -> child-a
    pressKey('ArrowDown'); // child-a -> child-b
    pressKey('ArrowLeft'); // child-b has no children -> move to parent (root)

    expect(screen.getByTestId('workspace-tree-node-root')).toHaveFocus();
  });

  it('Home moves focus to the first visible item', () => {
    renderTree({ nodes: KB_FLAT });
    pressKey('ArrowDown');
    pressKey('ArrowDown');
    pressKey('ArrowDown'); // now at k4
    pressKey('Home');
    expect(screen.getByTestId('workspace-tree-node-k1')).toHaveFocus();
  });

  it('End moves focus to the last visible item', () => {
    renderTree({ nodes: KB_FLAT });
    pressKey('End');
    expect(screen.getByTestId('workspace-tree-node-k4')).toHaveFocus();
  });

  it('letter-jump moves focus to the next item starting with the typed character, cycling', () => {
    renderTree({ nodes: KB_FLAT });
    // Default focus is k1 ("Alpha"). Pressing "a" should cycle past k1
    // itself to k4 ("Another Alpha-like" — the next name starting with "a").
    pressKey('a');
    expect(screen.getByTestId('workspace-tree-node-k4')).toHaveFocus();
  });

  it('letter-jump is case-insensitive', () => {
    renderTree({ nodes: KB_FLAT });
    pressKey('B'); // matches "Bravo" (k2)
    expect(screen.getByTestId('workspace-tree-node-k2')).toHaveFocus();
  });

  it('Enter activates the focused item the same way a click does', () => {
    const onSelect = vi.fn();
    renderTree({ nodes: KB_FLAT, onSelect });
    pressKey('ArrowDown'); // k1 -> k2
    pressKey('Enter');
    expect(onSelect).toHaveBeenCalledWith('k2');
  });

  it('* expands all siblings at the current item\'s level', async () => {
    renderTree({ nodes: KB_TREE });
    // Root auto-expands on mount; child-a/child-b (its children) do not.
    await waitFor(() => expect(screen.getByText('Child A')).toBeInTheDocument());
    expect(screen.queryByText('Grandchild')).not.toBeInTheDocument();

    pressKey('ArrowRight'); // root -> child-a
    pressKey('ArrowDown'); // child-a -> child-b
    pressKey('*'); // expand every sibling of child-b (i.e. child-a too)

    expect(screen.getByText('Grandchild')).toBeInTheDocument();
  });

  it('clicking a row also moves roving-tabindex focus to it', async () => {
    const user = userEvent.setup();
    renderTree({ nodes: KB_FLAT });
    await user.click(screen.getByText('Charlie'));
    expect(screen.getByTestId('workspace-tree-node-k3')).toHaveAttribute('tabindex', '0');
    expect(screen.getByTestId('workspace-tree-node-k1')).toHaveAttribute('tabindex', '-1');
  });

  it('only the focused row has tabIndex=0 (roving tabindex)', () => {
    renderTree({ nodes: KB_FLAT });
    expect(screen.getByTestId('workspace-tree-node-k1')).toHaveAttribute('tabindex', '0');
    expect(screen.getByTestId('workspace-tree-node-k2')).toHaveAttribute('tabindex', '-1');
    expect(screen.getByTestId('workspace-tree-node-k3')).toHaveAttribute('tabindex', '-1');
    expect(screen.getByTestId('workspace-tree-node-k4')).toHaveAttribute('tabindex', '-1');
  });
});

// ---------------------------------------------------------------------------
// Task 4.1: keyboard navigation in the virtualized path — the target row is
// NOT initially mounted and must be scrolled into view before it can be
// focused.
//
// Two jsdom limitations have to be worked around, both noted in the task
// brief as the "hard part":
//
//  1. jsdom does not run layout, so `offsetWidth`/`offsetHeight` are always
//     0. @tanstack/react-virtual reads the scroll container's rect
//     synchronously via `observeElementRect` (virtual-core/src/index.ts) —
//     with a 0x0 rect its visible range is empty and it mounts NO rows at
//     all, which would make "scroll a not-yet-rendered node into view" a
//     vacuous test (there'd be nothing rendered before OR after). We patch
//     `offsetWidth`/`offsetHeight` on HTMLElement.prototype for this describe
//     block to a realistic container size so the virtualizer computes a real
//     window of rows, matching what happens in a real browser.
//  2. jsdom's `scrollTo()` does not update `scrollTop` or dispatch a
//     `scroll` event. @tanstack/react-virtual's offset tracking
//     (`observeElementOffset`) is driven entirely by a native 'scroll'
//     listener reading `element.scrollTop`. So after our keyboard handler
//     calls `rowVirtualizer.scrollToIndex(...)`, we manually fire a
//     `scroll` event with the resulting `scrollTop` — this is the standard,
//     documented way to drive @tanstack/virtual-core in jsdom tests, and
//     genuinely exercises the "scroll the target into the DOM, then attach
//     DOM focus" sequence in `focusRowAtIndex`/`registerRowRef`.
// ---------------------------------------------------------------------------

describe('WorkspaceTree — keyboard navigation in the virtualized path', () => {
  const ROW_HEIGHT = 34; // VIRTUAL_ROW_HEIGHT in workspace-tree.tsx
  const CONTAINER_HEIGHT = 340; // ~10 rows visible at once

  const LARGE_NODES: WorkspaceTreeNode[] = Array.from({ length: 150 }, (_, i) => ({
    id: `v${i}`,
    name: `Node ${i}`,
    parentId: null,
  }));

  let offsetHeightSpy: ReturnType<typeof vi.spyOn>;
  let offsetWidthSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    offsetHeightSpy = vi
      .spyOn(HTMLElement.prototype, 'offsetHeight', 'get')
      .mockReturnValue(CONTAINER_HEIGHT);
    offsetWidthSpy = vi
      .spyOn(HTMLElement.prototype, 'offsetWidth', 'get')
      .mockReturnValue(800);
  });

  afterEach(() => {
    offsetHeightSpy.mockRestore();
    offsetWidthSpy.mockRestore();
  });

  function pressKey(key: string): void {
    const tree = screen.getByRole('tree');
    if (!tree.contains(document.activeElement)) {
      tree.querySelector<HTMLElement>('[tabindex="0"]')?.focus();
    }
    fireEvent.keyDown(tree, { key });
  }

  /** Mirrors what a real 'scroll' event delivers after scrollToIndex(). */
  function fireScrollTo(scrollTop: number): void {
    const scrollContainer = screen.getByTestId('workspace-tree-scroll');
    Object.defineProperty(scrollContainer, 'scrollTop', {
      configurable: true,
      writable: true,
      value: scrollTop,
    });
    fireEvent.scroll(scrollContainer, { target: { scrollTop } });
  }

  it('with a real container size, the virtualizer mounts only a window of rows (not all 150)', () => {
    renderTree({ nodes: LARGE_NODES, virtualize: true });
    const mounted = screen.queryAllByRole('treeitem').length;
    expect(mounted).toBeGreaterThan(0);
    expect(mounted).toBeLessThan(LARGE_NODES.length);
    // The last node is far outside the initial window.
    expect(screen.queryByTestId('workspace-tree-node-v149')).not.toBeInTheDocument();
  });

  it('End moves focus to the last item even though it is not initially rendered', async () => {
    renderTree({ nodes: LARGE_NODES, virtualize: true });
    expect(screen.queryByTestId('workspace-tree-node-v149')).not.toBeInTheDocument();

    pressKey('End');
    // Drive the virtualizer's offset tracking the way a real scroll would.
    fireScrollTo(150 * ROW_HEIGHT);

    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-v149')).toHaveFocus();
    });
  });

  it('Home moves focus back to the first item from a scrolled-down position', async () => {
    renderTree({ nodes: LARGE_NODES, virtualize: true });

    // Scroll down first so v0 is unmounted, then land keyboard focus at the
    // bottom via End (exercising the same scroll-then-focus path).
    pressKey('End');
    fireScrollTo(150 * ROW_HEIGHT);
    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-v149')).toHaveFocus();
      expect(screen.queryByTestId('workspace-tree-node-v0')).not.toBeInTheDocument();
    });

    pressKey('Home');
    fireScrollTo(0);

    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-v0')).toHaveFocus();
    });
  });

  it('ArrowDown across the virtualized window still moves focus one row at a time', () => {
    renderTree({ nodes: LARGE_NODES, virtualize: true });
    // v0 is focusable by default (default focus target); no scroll needed
    // since v1 is within the initially mounted window.
    pressKey('ArrowDown');
    expect(screen.getByTestId('workspace-tree-node-v1')).toHaveFocus();
  });

  it('letter-jump can scroll a distant match into view before focusing it', async () => {
    // Rename a far-away node so letter-jump has a unique target outside the
    // initial window, proving the same scroll-then-focus path works for the
    // letter-jump key too, not just Home/End.
    const nodes = LARGE_NODES.map((n, i) =>
      i === 140 ? { ...n, name: 'Zzz-Target' } : n,
    );
    renderTree({ nodes, virtualize: true });
    expect(screen.queryByTestId('workspace-tree-node-v140')).not.toBeInTheDocument();

    pressKey('z');
    fireScrollTo(140 * ROW_HEIGHT);

    await waitFor(() => {
      expect(screen.getByTestId('workspace-tree-node-v140')).toHaveFocus();
    });
  });
});

// ---------------------------------------------------------------------------
// Visual connector lines (issue #661)
// ---------------------------------------------------------------------------

describe('WorkspaceTree — connector lines', () => {
  it('renders a connector-line class on non-root tree rows', async () => {
    renderTree({ nodes: TREE_NODES });
    // Wait for auto-expand so children are visible
    await waitFor(() => {
      expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument();
    });
    const childRow = screen.getByTestId('workspace-tree-node-child1');
    expect(childRow.className).toMatch(/treeLine/);
  });

  it('does not render connector-line class on root rows', () => {
    renderTree({ nodes: TREE_NODES });
    const rootRow = screen.getByTestId('workspace-tree-node-root');
    expect(rootRow.className).not.toMatch(/treeLine/);
  });

  it('renders connector-line class on deeper nested rows (depth > 1)', async () => {
    renderTree({ nodes: TREE_NODES });
    await waitFor(() => {
      expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument();
    });
    // Expand child1 to reveal grandchild (depth 2)
    fireEvent.click(screen.getByTestId('workspace-tree-toggle-child1'));
    await waitFor(() => {
      expect(screen.getByText('L2 Component')).toBeInTheDocument();
    });
    const grandchildRow = screen.getByTestId('workspace-tree-node-grandchild');
    expect(grandchildRow.className).toMatch(/treeLine/);
  });
});

describe('WorkspaceTree — onAddChild', () => {
  it('renders add-child button when onAddChild is provided', () => {
    renderTree({ nodes: FLAT_NODES, onAddChild: vi.fn() });
    expect(screen.getByTestId('workspace-tree-add-child-n1')).toBeInTheDocument();
  });

  it('add-child button is absent without onAddChild prop', () => {
    renderTree({ nodes: FLAT_NODES });
    expect(
      screen.queryByTestId('workspace-tree-add-child-n1'),
    ).not.toBeInTheDocument();
  });

  it('calls onAddChild with node id and does not trigger onSelect', async () => {
    const onAddChild = vi.fn();
    const onSelect = vi.fn();
    renderTree({ nodes: FLAT_NODES, onAddChild, onSelect });

    // Use fireEvent to avoid userEvent timer issues
    fireEvent.click(screen.getByTestId('workspace-tree-add-child-n2'));

    expect(onAddChild).toHaveBeenCalledWith('n2');
    expect(onSelect).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Drag & drop reparenting (user decision 2026-08-15)
// ---------------------------------------------------------------------------

describe('WorkspaceTree — ARIA treeitem accessibility (#667)', () => {
  it('does not expose the toggle/add-child buttons as tab-focusable or in the a11y tree', () => {
    render(
      <WorkspaceTree
        nodes={TREE_NODES}
        onToggle={vi.fn()}
        onAddChild={vi.fn()}
        onSelect={vi.fn()}
        showSearch={false}
      />,
    );
    const toggleButton = screen.getByTestId('workspace-tree-toggle-root');
    expect(toggleButton).toHaveAttribute('tabIndex', '-1');
    expect(toggleButton).toHaveAttribute('aria-hidden', 'true');
    const addChildButton = screen.getByTestId('workspace-tree-add-child-root');
    expect(addChildButton).toHaveAttribute('tabIndex', '-1');
    expect(addChildButton).toHaveAttribute('aria-hidden', 'true');
  });

  it('expands a node via ArrowRight on the focused treeitem', async () => {
    const onToggle = vi.fn();
    render(
      <WorkspaceTree
        nodes={TREE_NODES}
        onToggle={onToggle}
        onSelect={vi.fn()}
        showSearch={false}
      />,
    );
    // Collapse root first (it auto-expands on mount)
    await waitFor(() =>
      expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('workspace-tree-toggle-root'));
    expect(screen.queryByText('L1 Subsystem A')).not.toBeInTheDocument();
    onToggle.mockClear();

    const treeitem = screen.getAllByRole('treeitem')[0];
    fireEvent.keyDown(treeitem, { key: 'ArrowRight' });
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(treeitem).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('L1 Subsystem A')).toBeInTheDocument();
  });
});

describe('WorkspaceTree — drag & drop reparenting', () => {
  /**
   * Minimal stand-in for the browser's DataTransfer. jsdom ships no
   * implementation, and the component reads `getData('text/plain')` on drop,
   * so every drag sequence in these tests carries one of these through
   * dragStart → dragOver → drop, exactly like a real drag does.
   */
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

  const row = (id: string): HTMLElement =>
    screen.getByTestId(`workspace-tree-node-${id}`);

  /**
   * Expands a row. Only root nodes auto-expand on first render, so any test
   * that needs a grandchild in the DOM has to open its parent first.
   */
  function expandRow(id: string): void {
    fireEvent.click(screen.getByTestId(`workspace-tree-toggle-${id}`));
  }

  /**
   * Fires a dragleave whose `relatedTarget` (the element the pointer moved
   * onto) actually survives into the handler. jsdom has no `DragEvent`
   * constructor, so `fireEvent.dragLeave(el, { relatedTarget })` silently
   * drops that init field — the property has to be defined on the event.
   */
  function dragLeaveTowards(target: HTMLElement, related: Node | null): void {
    const event = createEvent.dragLeave(target);
    Object.defineProperty(event, 'relatedTarget', { value: related });
    fireEvent(target, event);
  }

  /** Drags `fromId` and drops it on `toId`'s row. */
  function dragOnto(fromId: string, toId: string): void {
    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row(fromId), { dataTransfer });
    fireEvent.dragOver(row(toId), { dataTransfer });
    fireEvent.drop(row(toId), { dataTransfer });
  }

  // -- opt-in: consumers without onReparent are completely unaffected -------

  it('rows are not draggable when onReparent is omitted', () => {
    renderTree({ nodes: TREE_NODES });
    expect(row('root')).not.toHaveAttribute('draggable', 'true');
  });

  it('no root dropzone exists when onReparent is omitted', () => {
    renderTree({ nodes: TREE_NODES });
    fireEvent.dragStart(row('root'), { dataTransfer: makeDataTransfer() });
    expect(
      screen.queryByTestId('workspace-tree-root-dropzone'),
    ).not.toBeInTheDocument();
  });

  it('rows become draggable when onReparent is provided', () => {
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });
    expect(row('root')).toHaveAttribute('draggable', 'true');
  });

  // -- the reparent call itself --------------------------------------------

  it('dropping a node onto another node reparents it under that node', () => {
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });

    dragOnto('child1', 'child2');

    expect(onReparent).toHaveBeenCalledTimes(1);
    expect(onReparent).toHaveBeenCalledWith('child1', 'child2');
  });

  it('dropping onto the root dropzone detaches the node to root level', () => {
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('child1'), { dataTransfer });
    const dropzone = screen.getByTestId('workspace-tree-root-dropzone');
    fireEvent.dragOver(dropzone, { dataTransfer });
    fireEvent.drop(dropzone, { dataTransfer });

    expect(onReparent).toHaveBeenCalledWith('child1', null);
  });

  it('falls back to the dragged-node state when dataTransfer carries no id', () => {
    // Some browsers (and every synthetic drop that skips dragStart's payload)
    // hand over an empty text/plain; the in-flight drag id must still resolve.
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('child1'), { dataTransfer });
    fireEvent.drop(row('child2'), { dataTransfer: makeDataTransfer() });

    expect(onReparent).toHaveBeenCalledWith('child1', 'child2');
  });

  // -- client-side no-ops ---------------------------------------------------

  it('dropping a node onto itself is a no-op', () => {
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });

    dragOnto('child1', 'child1');

    expect(onReparent).not.toHaveBeenCalled();
  });

  it('dropping a node onto its current parent is a no-op', () => {
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });

    dragOnto('child1', 'root');

    expect(onReparent).not.toHaveBeenCalled();
  });

  it('dropping a root node onto the root dropzone is a no-op', () => {
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('root'), { dataTransfer });
    fireEvent.drop(screen.getByTestId('workspace-tree-root-dropzone'), {
      dataTransfer,
    });

    expect(onReparent).not.toHaveBeenCalled();
  });

  it('dropping a node onto its own child is a no-op', () => {
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });

    dragOnto('root', 'child1');

    expect(onReparent).not.toHaveBeenCalled();
  });

  it('dropping a node onto a deeper descendant is a no-op', () => {
    // Moving a node into its own subtree closes a cycle in any tree, whatever
    // the artifact type — so the tree refuses it instead of forwarding it.
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });
    expandRow('child1');

    dragOnto('root', 'grandchild');

    expect(onReparent).not.toHaveBeenCalled();
  });

  it('detaching a node to root is never treated as a cycle', () => {
    const onReparent = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent });
    expandRow('child1');

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('grandchild'), { dataTransfer });
    fireEvent.drop(screen.getByTestId('workspace-tree-root-dropzone'), {
      dataTransfer,
    });

    expect(onReparent).toHaveBeenCalledWith('grandchild', null);
  });

  it('does not offer a descendant as a drop target while dragging', () => {
    // The form prevents the same move by leaving descendants out of its parent
    // dropdown; the tree's equivalent is to not light the row up at all.
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });
    expandRow('child1');

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('root'), { dataTransfer });
    fireEvent.dragOver(row('grandchild'), { dataTransfer });

    expect(row('grandchild')).not.toHaveAttribute('data-drop-target', 'true');
  });

  // -- drop-target highlighting --------------------------------------------

  it('marks the hovered row as the current drop target', () => {
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('child1'), { dataTransfer });
    fireEvent.dragOver(row('child2'), { dataTransfer });

    expect(row('child2')).toHaveAttribute('data-drop-target', 'true');
  });

  it('does not mark the dragged row itself as a drop target', () => {
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('child1'), { dataTransfer });
    fireEvent.dragOver(row('child1'), { dataTransfer });

    expect(row('child1')).not.toHaveAttribute('data-drop-target', 'true');
    expect(row('child1')).toHaveAttribute('data-dragging', 'true');
  });

  it('keeps the highlight when the pointer moves onto a nested child of the same row', () => {
    // Native D&D fires dragleave when the pointer crosses onto the row's own
    // chevron/label/badge — treating that as "left the row" makes the
    // highlight flicker through a whole drag.
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('child1'), { dataTransfer });
    fireEvent.dragOver(row('child2'), { dataTransfer });

    const nestedChild = row('child2').querySelector('span');
    expect(nestedChild).not.toBeNull();
    dragLeaveTowards(row('child2'), nestedChild);

    expect(row('child2')).toHaveAttribute('data-drop-target', 'true');
  });

  it('clears the highlight once the pointer truly leaves the row', () => {
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('child1'), { dataTransfer });
    fireEvent.dragOver(row('child2'), { dataTransfer });
    dragLeaveTowards(row('child2'), row('root'));

    expect(row('child2')).not.toHaveAttribute('data-drop-target', 'true');
  });

  // -- root dropzone lifecycle ---------------------------------------------

  it('root dropzone is absent until a drag starts', () => {
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });
    expect(
      screen.queryByTestId('workspace-tree-root-dropzone'),
    ).not.toBeInTheDocument();
  });

  it('root dropzone disappears again when the drag ends', () => {
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });

    const dataTransfer = makeDataTransfer();
    fireEvent.dragStart(row('child1'), { dataTransfer });
    expect(screen.getByTestId('workspace-tree-root-dropzone')).toBeInTheDocument();

    fireEvent.dragEnd(row('child1'));
    expect(
      screen.queryByTestId('workspace-tree-root-dropzone'),
    ).not.toBeInTheDocument();
  });

  it('root dropzone disappears after a completed drop', () => {
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn() });

    dragOnto('child1', 'child2');

    expect(
      screen.queryByTestId('workspace-tree-root-dropzone'),
    ).not.toBeInTheDocument();
  });

  it('renders the caller-provided root dropzone label', () => {
    renderTree({
      nodes: TREE_NODES,
      onReparent: vi.fn(),
      rootDropzoneLabel: 'Drop here to make root (L0)',
    });

    fireEvent.dragStart(row('child1'), { dataTransfer: makeDataTransfer() });

    expect(
      screen.getByTestId('workspace-tree-root-dropzone'),
    ).toHaveTextContent('Drop here to make root (L0)');
  });

  // -- interaction with the other tree capabilities -------------------------

  it('starting a drag does not select the node', () => {
    const onSelect = vi.fn();
    renderTree({ nodes: TREE_NODES, onReparent: vi.fn(), onSelect });

    fireEvent.dragStart(row('child1'), { dataTransfer: makeDataTransfer() });

    expect(onSelect).not.toHaveBeenCalled();
  });

  it('virtualized rows are draggable too', () => {
    // Same container-size stubs the virtualized keyboard tests use — jsdom
    // reports zero layout height, so without them the virtualizer may mount
    // no rows at all.
    const offsetHeightSpy = vi
      .spyOn(HTMLElement.prototype, 'offsetHeight', 'get')
      .mockReturnValue(340);
    const offsetWidthSpy = vi
      .spyOn(HTMLElement.prototype, 'offsetWidth', 'get')
      .mockReturnValue(800);
    try {
      const many: WorkspaceTreeNode[] = Array.from({ length: 150 }, (_, i) => ({
        id: `v${i}`,
        name: `Node ${i}`,
        parentId: null,
      }));
      renderTree({ nodes: many, virtualize: true, onReparent: vi.fn() });

      expect(screen.getByTestId('workspace-tree-scroll')).toBeInTheDocument();
      expect(row('v0')).toHaveAttribute('draggable', 'true');
    } finally {
      offsetHeightSpy.mockRestore();
      offsetWidthSpy.mockRestore();
    }
  });
});
