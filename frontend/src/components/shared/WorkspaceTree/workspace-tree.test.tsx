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

import { describe, it, expect, vi, afterEach } from 'vitest';
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
