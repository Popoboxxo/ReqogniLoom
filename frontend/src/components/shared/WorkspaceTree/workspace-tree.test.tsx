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
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkspaceTree } from './workspace-tree';
import type { WorkspaceTreeNode, WorkspaceTreeProps } from './workspace-tree';

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
