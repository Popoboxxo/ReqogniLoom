/**
 * Task 4.4 (UI concept plan, virtualization ratchet) — AdrList DOM node
 * count stays roughly constant once WorkspaceTree's virtualization kicks
 * in, instead of growing 1:1 with the number of ADRs.
 *
 * Mirrors `workspace-tree.test.tsx`'s "mounts far fewer DOM rows than total
 * nodes when virtualized" assertion, driven through the real `<AdrList>`
 * (not `<WorkspaceTree>` directly) so it also proves the `renderRow`/
 * `virtualize` wiring, not just the underlying primitive.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '../../i18n/index';

import { AdrList } from './AdrList';
import type { Adr } from '../../types';

function makeAdr(i: number): Adr {
  return {
    id: `adr-${i}`,
    workspace_id: 'ws-1',
    title: `ADR ${i}`,
    description: '',
    context: '',
    consequences: '',
    status: 'Draft',
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function renderList(count: number) {
  const items = Array.from({ length: count }, (_, i) => makeAdr(i));
  return render(<AdrList items={items} onSelect={vi.fn()} onCreateNew={vi.fn()} />);
}

describe('AdrList virtualization (Task 4.4)', () => {
  it('mounts far fewer DOM rows than total ADRs at 500 entries', () => {
    renderList(500);
    // Virtualized scroll container is present (>100-item threshold, REQ-091).
    expect(screen.getByTestId('adr-list-rows-scroll')).toBeInTheDocument();
    expect(screen.queryAllByRole('treeitem').length).toBeLessThan(500);
  });

  it('DOM row count at 500 entries stays roughly the same as at 150 entries', () => {
    // Both sizes exceed the 100-item virtualization threshold, so the
    // number of DOM rows should be windowed to the viewport in both cases
    // rather than scaling with the total — this is the "constant DOM node
    // count" acceptance criterion, not just "less than total".
    const { unmount } = renderList(150);
    const rowsAt150 = screen.queryAllByRole('treeitem').length;
    unmount();

    renderList(500);
    const rowsAt500 = screen.queryAllByRole('treeitem').length;

    expect(rowsAt500).toBe(rowsAt150);
  });
});
