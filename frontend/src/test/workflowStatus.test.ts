/**
 * GH-453 — utils/workflowStatus.
 *
 * The status filter in every artifact list used to be built from one hardcoded
 * Title-Case array that matched no entity's real vocabulary, so selecting an
 * option filtered the list down to nothing. Options are now derived from the
 * loaded items; these tests pin that the derived values are the raw API values
 * (what the lists compare with `===`) while the labels stay readable.
 */
import { describe, expect, it } from 'vitest';

import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from '../utils/workflowStatus';

describe('getWorkflowStatusLabel', () => {
  it('capitalizes a lowercase value', () => {
    expect(getWorkflowStatusLabel('draft')).toBe('Draft');
    expect(getWorkflowStatusLabel('approved')).toBe('Approved');
  });

  it('keeps the GH-453 TestCase states readable after the value rename', () => {
    expect(getWorkflowStatusLabel('draft')).toBe('Draft');
    expect(getWorkflowStatusLabel('ready')).toBe('Ready');
    expect(getWorkflowStatusLabel('approved')).toBe('Approved');
    expect(getWorkflowStatusLabel('deprecated')).toBe('Deprecated');
  });

  it('leaves an already Title-Case value (Adr, Risk, Issue) untouched', () => {
    expect(getWorkflowStatusLabel('Draft')).toBe('Draft');
    expect(getWorkflowStatusLabel('Identified')).toBe('Identified');
    expect(getWorkflowStatusLabel('Open')).toBe('Open');
  });

  it('expands separators in multi-word states', () => {
    expect(getWorkflowStatusLabel('in_review')).toBe('In Review');
    expect(getWorkflowStatusLabel('In Review')).toBe('In Review');
    expect(getWorkflowStatusLabel('under_review')).toBe('Under Review');
    expect(getWorkflowStatusLabel('wontfix')).toBe("Won't Fix");
  });

  it('humanizes unknown, workspace-defined states instead of dropping them', () => {
    expect(getWorkflowStatusLabel('awaiting_sign_off')).toBe('Awaiting Sign Off');
  });
});

describe('compareWorkflowStatus', () => {
  it('orders by lifecycle position, not alphabetically', () => {
    const states = ['approved', 'draft', 'deprecated', 'ready'];
    expect([...states].sort(compareWorkflowStatus)).toEqual([
      'draft',
      'ready',
      'approved',
      'deprecated',
    ]);
  });

  it('is case-insensitive, so Adr and TestCase sort the same way', () => {
    expect([...['Approved', 'Draft']].sort(compareWorkflowStatus)).toEqual([
      'Draft',
      'Approved',
    ]);
  });

  it('sorts unknown states after every known one', () => {
    const sorted = ['zzz_custom', 'approved', 'draft'].sort(compareWorkflowStatus);
    expect(sorted).toEqual(['draft', 'approved', 'zzz_custom']);
  });
});

describe('buildStatusFilterOptions', () => {
  it('derives one option per distinct status, in lifecycle order', () => {
    const items = [
      { status: 'approved' },
      { status: 'draft' },
      { status: 'approved' },
      { status: 'ready' },
    ];
    expect(buildStatusFilterOptions(items)).toEqual([
      { value: 'draft', label: 'Draft' },
      { value: 'ready', label: 'Ready' },
      { value: 'approved', label: 'Approved' },
    ]);
  });

  it('uses the raw value as the option value so `item.status === value` matches', () => {
    // The regression the issue was about: an option whose value is not byte
    // identical to the stored status filters the list down to nothing.
    const items = [{ status: 'draft' }, { status: 'approved' }];
    for (const option of buildStatusFilterOptions(items)) {
      expect(items.some((item) => item.status === option.value)).toBe(true);
    }
  });

  it('handles the Title-Case vocabularies that are NOT part of the rename', () => {
    const issues = [{ status: 'Open' }, { status: 'Resolved' }, { status: 'Wontfix' }];
    expect(buildStatusFilterOptions(issues)).toEqual([
      { value: 'Open', label: 'Open' },
      { value: 'Resolved', label: 'Resolved' },
      { value: 'Wontfix', label: "Won't Fix" },
    ]);
  });

  it('ignores missing, null and blank statuses', () => {
    const items = [
      { status: 'draft' },
      { status: '' },
      { status: null },
      { status: undefined },
      {},
    ];
    expect(buildStatusFilterOptions(items)).toEqual([{ value: 'draft', label: 'Draft' }]);
  });

  it('returns no options for an empty list', () => {
    expect(buildStatusFilterOptions([])).toEqual([]);
  });

  it('keeps the active filter value as an option after its last item leaves', () => {
    // Otherwise the <select> falls back to showing "All Statuses" while the
    // filter is still applied — the list looks unfiltered but renders empty.
    const items = [{ status: 'draft' }];
    expect(buildStatusFilterOptions(items, 'ready')).toEqual([
      { value: 'draft', label: 'Draft' },
      { value: 'ready', label: 'Ready' },
    ]);
  });

  it('does not duplicate the active value when items still carry it', () => {
    const items = [{ status: 'draft' }, { status: 'approved' }];
    expect(buildStatusFilterOptions(items, 'approved')).toEqual([
      { value: 'draft', label: 'Draft' },
      { value: 'approved', label: 'Approved' },
    ]);
  });

  it('adds nothing when no filter is active', () => {
    const items = [{ status: 'draft' }];
    expect(buildStatusFilterOptions(items, '')).toEqual([
      { value: 'draft', label: 'Draft' },
    ]);
  });
});
