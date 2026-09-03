/**
 * R2/T1 (final review of the P0 hardening plan): ReqTraceLinkPanel still
 * showed three write triggers to a "viewer" — Create TraceLink, the per-link
 * Delete ("x") and the DeriveRequirementForm (which derives a *new*
 * requirement). Only the server rejected the actual write, which is exactly
 * the P0 audit finding this plan exists to close, just in a different spot.
 *
 * Contract (same as SidebarNavigation.tsx / RequirementList.roleGate.test.tsx):
 * genuinely absent from the DOM for a viewer, not merely disabled.
 *
 * leaf_id: COMP-RF-003-ReqTraceLinkPanel
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../api/tracelinks');
vi.mock('../../api/requirements');
vi.mock('../../api/testcases');
vi.mock('../../api/architecture');
vi.mock('../../context/AuthContext');
vi.mock('react-i18next', () => {
  const t = (key: string, fallback?: string): string =>
    typeof fallback === 'string' ? fallback : key;
  return { useTranslation: () => ({ t }) };
});

import * as tracelinksModule from '../../api/tracelinks';
import * as testcasesModule from '../../api/testcases';
import * as architectureModule from '../../api/architecture';
import * as authModule from '../../context/AuthContext';
import { ReqTraceLinkPanel } from './ReqTraceLinkPanel';
import type { Requirement } from '../../types';

const WORKSPACE_ID = 'ws-001';
const REQ_ID = 'req-l1';
const ART_ID = 'art-l1';
const CHILD_REQ_ID = 'req-l2';
const CHILD_ART_ID = 'art-l2';
const ARCH_ART_ID = 'art-arch';
const ARCH_ENTITY_ID = 'arch-1';

const REQUIREMENTS = [
  {
    id: REQ_ID,
    artifact_id: ART_ID,
    workspace_id: WORKSPACE_ID,
    title: 'L1 requirement',
    description: '',
    category: 'functional',
    status: 'draft',
    version: 1,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
  {
    id: CHILD_REQ_ID,
    artifact_id: CHILD_ART_ID,
    workspace_id: WORKSPACE_ID,
    title: 'L2 requirement',
    description: '',
    category: 'functional',
    status: 'draft',
    version: 1,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
] as unknown as Requirement[];

/** A decomposition link plus an allocated-to link (the latter renders the
 * per-link Delete trigger in the non-requirement link list). */
const LINKS = [
  {
    id: 'tl-decomp',
    source_id: ART_ID,
    source_title: REQUIREMENTS[0].title,
    source_type: 'Requirement',
    target_id: CHILD_ART_ID,
    target_title: REQUIREMENTS[1].title,
    target_type: 'Requirement',
    link_type: 'decomposes',
    version: 1,
    created_at: '2026-02-01T00:00:00Z',
  },
  {
    id: 'tl-alloc',
    source_id: ART_ID,
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

function mockRoles(roles: string[]): void {
  vi.mocked(authModule.useAuth).mockReturnValue({
    roles,
  } as unknown as ReturnType<typeof authModule.useAuth>);
}

function renderPanel(): void {
  render(
    <MemoryRouter>
      <ReqTraceLinkPanel
        workspaceId={WORKSPACE_ID}
        requirementId={REQ_ID}
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

describe('ReqTraceLinkPanel — role-gated write triggers (R2/T1)', () => {
  it('hides Create TraceLink, per-link Delete and the derive form from a viewer', async () => {
    mockRoles(['viewer']);
    renderPanel();

    // Wait until the links have loaded, otherwise "absent" is trivially true.
    await waitFor(() => {
      expect(tracelinksModule.tracelinksApi.listForArtifact).toHaveBeenCalled();
    });

    expect(screen.queryByTestId('req-tracelink-create-btn')).not.toBeInTheDocument();
    expect(screen.queryAllByTestId('req-tracelink-delete-btn')).toHaveLength(0);
    expect(screen.queryByTestId('req-derive-btn')).not.toBeInTheDocument();
    // The read-only "view all" navigation stays available to a viewer.
    expect(screen.getByTestId('req-tracelink-viewall-btn')).toBeInTheDocument();
  });

  it('shows Create TraceLink, per-link Delete and the derive form to an editor', async () => {
    mockRoles(['editor']);
    renderPanel();

    expect(await screen.findByTestId('req-tracelink-create-btn')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByTestId('req-tracelink-delete-btn').length).toBeGreaterThan(0);
    });
    expect(screen.getByTestId('req-derive-btn')).toBeInTheDocument();
  });

  it('shows them to an admin too (superset of editor)', async () => {
    mockRoles(['admin']);
    renderPanel();

    expect(await screen.findByTestId('req-tracelink-create-btn')).toBeInTheDocument();
    expect(screen.getByTestId('req-derive-btn')).toBeInTheDocument();
  });
});
