/**
 * ReqTraceLinkPanel — "hierarchical view" regression tests (issue #416).
 *
 * The panel receives a **Requirement** id while `GET /tracelinks/` answers
 * with **Artifact** ids, so the fixtures below deliberately use two disjoint
 * id spaces. A fixture that reuses one id for both cannot reproduce the bug:
 * the panel would appear to work while the real UI rendered the current
 * requirement as its own parent, child and every linked element.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../api/tracelinks');
vi.mock('../../api/requirements');
vi.mock('../../api/testcases');
vi.mock('../../api/architecture');
vi.mock('react-i18next', () => {
  const t = (key: string, fallback?: string): string =>
    typeof fallback === 'string' ? fallback : key;
  return { useTranslation: () => ({ t }) };
});

import * as tracelinksModule from '../../api/tracelinks';
import * as testcasesModule from '../../api/testcases';
import * as architectureModule from '../../api/architecture';
import { ReqTraceLinkPanel } from './ReqTraceLinkPanel';
import type { Requirement } from '../../types';

const WORKSPACE_ID = 'ws-001';

// Requirement ids (what the editor knows) …
const L1_REQ_ID = 'req-l1';
const L2_REQ_ID = 'req-l2';
// … and the Artifact ids the trace-link API actually returns.
const L1_ART_ID = 'art-l1';
const L2_ART_ID = 'art-l2';
const ARCH_ART_ID = 'art-arch';
const ARCH_ENTITY_ID = 'arch-1';

const REQUIREMENTS = [
  {
    id: L1_REQ_ID,
    artifact_id: L1_ART_ID,
    workspace_id: WORKSPACE_ID,
    title: 'L1 Das System muss jede Zustandsaenderung protokollieren',
    description: '',
    category: 'functional',
    status: 'draft',
    version: 1,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
  {
    id: L2_REQ_ID,
    artifact_id: L2_ART_ID,
    workspace_id: WORKSPACE_ID,
    title: 'L2 Audit-Log schreibt jeden Statuswechsel',
    description: '',
    category: 'functional',
    status: 'draft',
    version: 1,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
] as unknown as Requirement[];

/** L1 decomposes into L2, and L1 is allocated to an architecture element. */
const LINKS = [
  {
    id: 'tl-decomp',
    source_id: L1_ART_ID,
    source_title: REQUIREMENTS[0].title,
    source_type: 'Requirement',
    target_id: L2_ART_ID,
    target_title: REQUIREMENTS[1].title,
    target_type: 'Requirement',
    link_type: 'decomposes',
    version: 1,
    created_at: '2026-02-01T00:00:00Z',
  },
  {
    id: 'tl-alloc',
    source_id: L1_ART_ID,
    source_title: REQUIREMENTS[0].title,
    source_type: 'Requirement',
    target_id: ARCH_ART_ID,
    target_title: 'AuthModule',
    target_type: 'ArchitectureElement',
    link_type: 'allocated-to',
    version: 1,
    created_at: '2026-02-01T00:00:00Z',
  },
];

function renderPanel(requirementId: string): void {
  render(
    <MemoryRouter>
      <ReqTraceLinkPanel
        workspaceId={WORKSPACE_ID}
        requirementId={requirementId}
        requirements={REQUIREMENTS}
        onLinksChanged={() => undefined}
      />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
    results: LINKS,
    count: LINKS.length,
    next: null,
    previous: null,
  } as never);
  vi.mocked(testcasesModule.testcasesApi.list).mockResolvedValue({ results: [] } as never);
  vi.mocked(architectureModule.architectureApi.list).mockResolvedValue({
    results: [
      {
        id: ARCH_ENTITY_ID,
        artifact_id: ARCH_ART_ID,
        workspace_id: WORKSPACE_ID,
        title: 'AuthModule',
        description: '',
        element_type: 'module',
        version: 1,
        created_at: '2026-02-01T00:00:00Z',
        updated_at: '2026-02-01T00:00:00Z',
      },
    ],
  } as never);
});

describe('ReqTraceLinkPanel — hierarchical view (#416)', () => {
  it('[#416] lists the child requirement, not the current requirement, on L1', async () => {
    renderPanel(L1_REQ_ID);

    await waitFor(() => {
      expect(screen.getByTestId('req-tracelink-requirements-section')).toBeInTheDocument();
    });

    const nodes = screen.getAllByTestId('req-tree-node');
    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toHaveAttribute('data-artifact-id', L2_ART_ID);
    expect(nodes[0]).toHaveAttribute('data-relation', 'child');
    expect(nodes[0]).toHaveTextContent('L2 Audit-Log schreibt jeden Statuswechsel');
    // The bug: the block rendered the artifact it was opened from.
    expect(screen.queryByText(/L1 Das System muss/)).not.toBeInTheDocument();
    expect(screen.getByTestId('req-hierarchy-group-child')).toBeInTheDocument();
  });

  it('[#416] lists the parent requirement, not the current requirement, on L2', async () => {
    renderPanel(L2_REQ_ID);

    await waitFor(() => {
      expect(screen.getByTestId('req-tracelink-requirements-section')).toBeInTheDocument();
    });

    const nodes = screen.getAllByTestId('req-tree-node');
    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toHaveAttribute('data-artifact-id', L1_ART_ID);
    expect(nodes[0]).toHaveAttribute('data-relation', 'parent');
    expect(screen.getByTestId('req-hierarchy-group-parent')).toBeInTheDocument();
    expect(screen.queryByText(/L2 Audit-Log/)).not.toBeInTheDocument();
  });

  it('[#416] routes a hierarchy node to the entity id, not the artifact id', async () => {
    renderPanel(L1_REQ_ID);

    await waitFor(() => {
      expect(screen.getAllByTestId('req-tree-node')).toHaveLength(1);
    });
    // `data-req-id` is what the title button navigates to — a 404 when it is
    // the Artifact id (the audit saw `404 GET /api/v1/requirements/<artifact>`).
    expect(screen.getAllByTestId('req-tree-node')[0]).toHaveAttribute('data-req-id', L2_REQ_ID);
  });

  it('[#416] resolves the architecture row to the linked element, not to itself', async () => {
    renderPanel(L1_REQ_ID);

    const archTitle = await screen.findByTestId('req-tracelink-arch-title');
    expect(archTitle).toHaveTextContent('AuthModule');
  });

  it('[#416] hierarchy nodes start expandable and load their own neighbours', async () => {
    const user = userEvent.setup();
    renderPanel(L1_REQ_ID);

    await waitFor(() => {
      expect(screen.getAllByTestId('req-tree-node')).toHaveLength(1);
    });

    // The toggle used to be disabled until children were known — which only
    // happened after expanding, so it could never be opened.
    const toggle = screen.getByTestId('req-tree-toggle');
    expect(toggle).not.toBeDisabled();

    await user.click(toggle);

    // L2's only hierarchy link points back at L1, which is already on the
    // path: rendered once, flagged as a cycle, not expandable (#415 guard).
    await waitFor(() => {
      expect(screen.getAllByTestId('req-tree-node')).toHaveLength(2);
    });
    const nodes = screen.getAllByTestId('req-tree-node');
    expect(nodes[1]).toHaveAttribute('data-artifact-id', L1_ART_ID);
    expect(nodes[1]).toHaveAttribute('data-cycle', 'true');
    expect(screen.getAllByTestId('req-tree-toggle')[1]).toBeDisabled();
  });

  it('[#416] shows an incoming verifies link from a test case', async () => {
    // Both endpoint *types* of this link were excluded by the old section
    // conditions (`!== 'Requirement'` on both sides), so it appeared in no
    // block at all — the requirement looked untested in its own editor.
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [
        {
          id: 'tl-verifies',
          source_id: 'art-tc',
          source_title: 'TC-1 Statuswechsel wird protokolliert',
          source_type: 'TestCase',
          target_id: L1_ART_ID,
          target_title: REQUIREMENTS[0].title,
          target_type: 'Requirement',
          link_type: 'verifies',
          version: 1,
          created_at: '2026-02-01T00:00:00Z',
        },
      ],
      count: 1,
      next: null,
      previous: null,
    } as never);

    renderPanel(L1_REQ_ID);

    const title = await screen.findByTestId('req-tracelink-title');
    expect(title).toHaveTextContent('TC-1 Statuswechsel wird protokolliert');
  });

  it('[#416] falls back to the shared endpoint when artifact_id is unavailable', async () => {
    // Older API responses (or an entity the list does not contain) leave the
    // panel without `artifact_id`; the self artifact is then inferred as the
    // endpoint common to every returned link.
    const requirementsWithoutArtifactId = REQUIREMENTS.map((r) => ({
      ...r,
      artifact_id: undefined,
    })) as unknown as Requirement[];

    render(
      <MemoryRouter>
        <ReqTraceLinkPanel
          workspaceId={WORKSPACE_ID}
          requirementId={L1_REQ_ID}
          requirements={requirementsWithoutArtifactId}
          onLinksChanged={() => undefined}
        />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getAllByTestId('req-tree-node')).toHaveLength(1);
    });
    expect(screen.getAllByTestId('req-tree-node')[0]).toHaveAttribute(
      'data-artifact-id',
      L2_ART_ID
    );
  });
});
