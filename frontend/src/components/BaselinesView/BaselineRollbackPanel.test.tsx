/**
 * F4.5 — Baseline rollback panel (REQ-L1-018, ADR-025, Plan F).
 *
 * Pins the component contract the baseline detail panel mounts:
 *   - "Compute preview" renders the plan: one row per item carrying its
 *     action label, and the non-restorable fields the snapshot cannot supply
 *   - the request/apply controls are write authority (a viewer only previews)
 *   - "Apply" appears only once the change request is `approved`
 *   - the confirmation dialog names the number of artifacts it will restore
 *   - a `409 ROLLBACK_PLAN_STALE` renders the "create a new request" copy
 *   - a double confirmation fires exactly one apply (server R5 stays the
 *     authority, the client just must not help it along)
 *
 * i18n is stubbed with a minimal message table + `{{placeholder}}`
 * interpolation so the assertions can see the interpolated count instead of
 * the raw key.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';

const MESSAGES = vi.hoisted(() => ({
  'baselines.rollback.title': 'Roll back to baseline',
  'baselines.rollback.preview': 'Compute preview',
  'baselines.rollback.actionRestore': 'Restore',
  'baselines.rollback.actionReactivate': 'Reactivate',
  'baselines.rollback.actionUnchanged': 'Unchanged',
  'baselines.rollback.actionUnsupported': 'Not supported',
  'baselines.rollback.actionCreatedSince': 'Created after baseline (kept)',
  'baselines.rollback.unrestorable': 'Not restorable: {{fields}}',
  'baselines.rollback.reason': 'Reason',
  'baselines.rollback.request': 'Create change request',
  'baselines.rollback.awaitApproval': 'The change request must be approved ({{status}}).',
  'baselines.rollback.refreshStatus': 'Refresh status',
  'baselines.rollback.apply': 'Run rollback',
  'baselines.rollback.confirm':
    '{{count}} artifacts will be restored as new versions. Continue?',
  'baselines.rollback.stale': 'Changed since the request — please create a new request.',
  'baselines.rollback.done':
    '{{restored}} restored, {{reactivated}} reactivated, {{links}} links recreated.',
  'baselines.rollback.notApproved': 'Change request is not approved.',
  'baselines.rollback.alreadyApplied': 'Rollback has already been applied.',
  'baselines.rollback.tooLarge': 'Too many artifacts ({{count}}, at most {{max}}).',
  'actions.saving': 'Saving…',
}));

vi.mock('react-i18next', () => {
  const t = (key: string, opts?: unknown): string => {
    const template = (MESSAGES as Record<string, string>)[key] ?? key;
    if (opts && typeof opts === 'object') {
      return template.replace(/{{\s*(\w+)\s*}}/g, (_match, name: string) =>
        String((opts as Record<string, unknown>)[name] ?? '')
      );
    }
    return template;
  };
  return { useTranslation: () => ({ t }) };
});

vi.mock('../../api/baselines');
vi.mock('../../api/change-requests');

import { baselinesApi } from '../../api/baselines';
import { changeRequestsApi } from '../../api/change-requests';
import type { RollbackPreview } from '../../api/baselines';
import { BaselineRollbackPanel } from './BaselineRollbackPanel';

const BASELINE_ID = 'bl-0001';
const CR_ID = 'cr-0001';

const PREVIEW: RollbackPreview = {
  baseline_id: BASELINE_ID,
  summary: {
    restore: 2,
    reactivate: 1,
    unchanged: 1,
    unsupported: 1,
    created_since: 1,
    links_to_recreate: 1,
  },
  items: [
    {
      item_id: 'aaaa1111-0000-0000-0000-000000000001',
      artifact_type: 'Requirement',
      action: 'restore',
      field_changes: { title: { current: 'Changed', baseline: 'Original' } },
      unrestorable_fields: [],
      current_version: 3,
    },
    {
      item_id: 'bbbb2222-0000-0000-0000-000000000002',
      artifact_type: 'Requirement',
      action: 'restore',
      field_changes: {},
      unrestorable_fields: ['acceptance_criteria'],
      current_version: 2,
    },
    {
      item_id: 'cccc3333-0000-0000-0000-000000000003',
      artifact_type: 'Requirement',
      action: 'reactivate',
      field_changes: {},
      unrestorable_fields: [],
      current_version: 1,
    },
    {
      item_id: 'dddd4444-0000-0000-0000-000000000004',
      artifact_type: 'Requirement',
      action: 'unchanged',
      field_changes: {},
      unrestorable_fields: [],
      current_version: 1,
    },
    {
      item_id: 'eeee5555-0000-0000-0000-000000000005',
      artifact_type: '',
      action: 'unsupported',
      field_changes: {},
      unrestorable_fields: [],
      current_version: null,
    },
    {
      item_id: 'ffff6666-0000-0000-0000-000000000006',
      artifact_type: 'Requirement',
      action: 'created_since',
      field_changes: {},
      unrestorable_fields: [],
      current_version: null,
    },
  ],
  links_to_recreate: [],
  skipped_links: [],
};

const renderPanel = (
  props: Partial<Parameters<typeof BaselineRollbackPanel>[0]> = {}
): ReturnType<typeof render> =>
  render(<BaselineRollbackPanel baselineId={BASELINE_ID} canEdit {...props} />);

/** Preview + draft reason + change request, ending in a `draft` CR. */
async function arriveAtRequest(user: UserEvent): Promise<void> {
  await user.click(screen.getByTestId('baseline-rollback-preview-btn'));
  await screen.findByTestId('baseline-rollback-preview-table');
  await user.type(screen.getByTestId('baseline-rollback-reason-input'), 'restore the release state');
  await user.click(screen.getByTestId('baseline-rollback-request-btn'));
  await screen.findByTestId('baseline-rollback-cr-status');
}

describe('BaselineRollbackPanel (F4.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(baselinesApi.rollbackPreview).mockResolvedValue(PREVIEW);
    vi.mocked(baselinesApi.rollbackRequest).mockResolvedValue({
      change_request_id: CR_ID,
      status: 'draft',
      affected_items: 3,
    });
    vi.mocked(changeRequestsApi.get).mockResolvedValue({
      id: CR_ID,
      workspace_id: 'ws-1',
      title: 'Rollback to baseline',
      status: 'draft',
      version: 1,
    });
  });

  it('renders the plan with one row per item and its action label', async () => {
    const user = userEvent.setup();
    renderPanel();

    expect(screen.getByTestId('baseline-rollback-panel')).toBeInTheDocument();
    await user.click(screen.getByTestId('baseline-rollback-preview-btn'));

    const rows = await screen.findAllByTestId('baseline-rollback-item-row');
    expect(rows).toHaveLength(PREVIEW.items.length);
    // Scoped to the rows: the same action labels also head the summary list.
    expect(within(rows[0]).getByText('Restore')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Reactivate')).toBeInTheDocument();
    expect(within(rows[3]).getByText('Unchanged')).toBeInTheDocument();
    expect(within(rows[4]).getByText('Not supported')).toBeInTheDocument();
    expect(
      within(rows[5]).getByText('Created after baseline (kept)')
    ).toBeInTheDocument();
    // ADR-025 R4: a field the snapshot does not carry is reported, not guessed.
    expect(screen.getByText(/Not restorable: acceptance_criteria/)).toBeInTheDocument();
  });

  it('keeps the write actions away from a reader', async () => {
    renderPanel({ canEdit: false });

    expect(screen.getByTestId('baseline-rollback-preview-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('baseline-rollback-reason-input')).not.toBeInTheDocument();
    expect(screen.queryByTestId('baseline-rollback-request-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('baseline-rollback-apply-btn')).not.toBeInTheDocument();
  });

  it('offers the apply action only once the change request is approved', async () => {
    const user = userEvent.setup();
    renderPanel();

    await arriveAtRequest(user);
    expect(screen.getByTestId('baseline-rollback-cr-status')).toHaveTextContent('draft');
    expect(screen.queryByTestId('baseline-rollback-apply-btn')).not.toBeInTheDocument();

    // The CCB approves the CR elsewhere; the panel re-reads the status.
    vi.mocked(changeRequestsApi.get).mockResolvedValue({
      id: CR_ID,
      workspace_id: 'ws-1',
      title: 'Rollback to baseline',
      status: 'approved',
      version: 2,
    });
    await user.click(screen.getByTestId('baseline-rollback-cr-refresh'));

    const apply = await screen.findByTestId('baseline-rollback-apply-btn');
    await waitFor(() => expect(screen.getByTestId('baseline-rollback-cr-status')).toHaveTextContent('approved'));
    expect(apply).toBeEnabled();
  });

  it('confirms with the number of artifacts the rollback will restore', async () => {
    const user = userEvent.setup();
    renderPanel();

    vi.mocked(changeRequestsApi.get).mockResolvedValue({
      id: CR_ID,
      workspace_id: 'ws-1',
      title: 'Rollback to baseline',
      status: 'approved',
      version: 2,
    });
    await arriveAtRequest(user);
    await user.click(await screen.findByTestId('baseline-rollback-apply-btn'));

    // summary.restore (2) + summary.reactivate (1)
    expect(screen.getByTestId('baseline-rollback-confirm-body')).toHaveTextContent(
      '3 artifacts will be restored as new versions. Continue?'
    );
  });

  it('renders the stale copy on a 409 ROLLBACK_PLAN_STALE', async () => {
    const user = userEvent.setup();
    renderPanel();

    vi.mocked(changeRequestsApi.get).mockResolvedValue({
      id: CR_ID,
      workspace_id: 'ws-1',
      title: 'Rollback to baseline',
      status: 'approved',
      version: 2,
    });
    vi.mocked(baselinesApi.rollbackApply).mockRejectedValue({
      error: { code: 'ROLLBACK_PLAN_STALE', message: 'The plan changed.', details: [] },
    });

    await arriveAtRequest(user);
    await user.click(await screen.findByTestId('baseline-rollback-apply-btn'));
    await user.click(screen.getByTestId('baseline-rollback-confirm-confirm'));

    expect(await screen.findByTestId('baseline-rollback-error')).toHaveTextContent(
      'Changed since the request — please create a new request.'
    );
  });

  it('fires exactly one apply when the confirmation is double-clicked', async () => {
    const user = userEvent.setup();
    renderPanel();

    vi.mocked(changeRequestsApi.get).mockResolvedValue({
      id: CR_ID,
      workspace_id: 'ws-1',
      title: 'Rollback to baseline',
      status: 'approved',
      version: 2,
    });
    // Never settles: the in-flight guard, not the response, must hold the line.
    vi.mocked(baselinesApi.rollbackApply).mockImplementation(
      () => new Promise(() => undefined)
    );

    await arriveAtRequest(user);
    await user.click(await screen.findByTestId('baseline-rollback-apply-btn'));

    const confirm = screen.getByTestId('baseline-rollback-confirm-confirm');
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await waitFor(() => expect(baselinesApi.rollbackApply).toHaveBeenCalledTimes(1));
  });
});
