/**
 * P2.7 / P4.4 — RequirementList display contracts.
 *
 * P2.7: the level display prefers the workspace ladder's `tier_name` and only
 * falls back to the legacy `L${level}` alias when the ladder lookup was
 * unavailable (`tier_name: null`).
 *
 * P4.4: the batch lock map is overlaid onto the tree nodes, so a frozen
 * requirement shows the lock marker while nothing else on the row changes.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RequirementList } from './RequirementList';
import type { Requirement } from '../../types';

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ roles: ['admin'] }),
}));

vi.mock('../../context/WorkspaceContext', () => ({
  useWorkspace: () => ({ activeWorkspace: { id: 'ws-a' } }),
  useOptionalWorkspace: () => ({ activeWorkspace: { id: 'ws-a' } }),
}));

// P4.4: keep the focused test off the network. One row is frozen.
vi.mock('../shared/WorkspaceTree/useWorkspaceLocks', () => ({
  useWorkspaceLocks: (workspaceId: string | null, type: string) =>
    workspaceId === 'ws-a' && type === 'requirement'
      ? { 'req-locked': 'Freigegeben' }
      : {},
}));

vi.mock('react-i18next', () => ({
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
      const labels: Record<string, string> = {
        'reqLevel.L1': 'L1 System',
        'reqLevel.L4': 'L4 Präsentation',
        'reqLevel.derived': 'abgeleitet',
        'reqLevel.derivedAllocation': 'abgeleitet (Allokation)',
        'reqType.SyReq': 'System Requirement',
        'reqTypeShort.SyReq': 'System',
        'editor.level': 'V-Modell-Ebene',
      };
      return labels[key] ?? key;
    },
  }),
}));

function makeRequirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: 'req-1',
    workspace_id: 'ws-1',
    title: 'First requirement',
    description: '',
    category: 'functional',
    status: 'draft',
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function renderList(requirements: Requirement[]): ReturnType<typeof render> {
  return render(
    <RequirementList
      requirements={requirements}
      onSelect={vi.fn()}
      onDelete={vi.fn()}
      onCreateNew={vi.fn()}
      allocation="all"
      onAllocationChange={vi.fn()}
    />,
  );
}

describe('RequirementList — tier display (P2.7)', () => {
  it("prefers the ladder's tier_name over the integer L-alias", () => {
    const req = makeRequirement({
      id: 'req-tier',
      type: 'SyReq',
      level: 4,
      tier_key: 'assembly',
      tier_name: 'Montageebene',
      level_source: 'derived_allocation',
    });
    renderList([req]);

    const attrs = screen.getByTestId(`req-row-${req.id}-attributes`);
    expect(attrs).toHaveTextContent('V-Modell-Ebene');
    expect(attrs).toHaveTextContent('Montageebene');
    expect(attrs).toHaveTextContent('abgeleitet (Allokation)');
    expect(attrs).not.toHaveTextContent('L4 Präsentation');

    // The type badge carries the same ladder name as its tier prefix.
    expect(screen.getByTestId(`req-row-${req.id}-level`)).toHaveTextContent(
      'Montageebene',
    );
  });

  it('falls back to the L-alias when tier_name is null', () => {
    const req = makeRequirement({
      id: 'req-fallback',
      type: 'SyReq',
      level: 1,
      tier_key: null,
      tier_name: null,
      level_source: 'derived',
    });
    renderList([req]);

    const attrs = screen.getByTestId(`req-row-${req.id}-attributes`);
    expect(attrs).toHaveTextContent('L1 System');
    expect(attrs).toHaveTextContent('abgeleitet');
  });
});

describe('RequirementList — workflow lock wiring (P4.4)', () => {
  it('marks a locked requirement in the tree', () => {
    const req = makeRequirement({ id: 'req-locked', type: 'SyReq', level: 1 });
    renderList([req]);

    const marker = screen.getByTestId('req-list-tree-lock-req-locked');
    expect(marker).toBeInTheDocument();
    expect(marker).toHaveAttribute('title', expect.stringContaining('Freigegeben'));
  });

  it('renders unlocked requirements without a marker', () => {
    const req = makeRequirement({ id: 'req-open', type: 'SyReq', level: 1 });
    renderList([req]);

    expect(
      screen.queryByTestId('req-list-tree-lock-req-open'),
    ).not.toBeInTheDocument();
  });
});
