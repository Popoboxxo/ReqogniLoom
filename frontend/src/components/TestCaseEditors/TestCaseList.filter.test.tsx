/**
 * GH-453 — the TestCase list status filter actually filters.
 *
 * Two regressions meet in this component:
 *   1. the API used to answer `status: "Draft"` while every other entity
 *      answered `"draft"` (the reported issue), and
 *   2. the filter dropdown was built from a hardcoded Title-Case array that
 *      matched no entity's vocabulary, so choosing an option emptied the list.
 *
 * These tests drive the real <TestCaseList> through the real <ListToolbar>
 * select, so they fail if either the option values or the comparison drift
 * apart again.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '../../i18n/index';

import { TestCaseList } from './TestCaseList';
import type { TestCase } from '../../api/testcases';

function makeTestCase(id: string, title: string, status: string): TestCase {
  return {
    id,
    workspace_id: 'ws-1',
    title,
    description: '',
    status,
    version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

const ITEMS: TestCase[] = [
  makeTestCase('tc-1', 'Draft case', 'draft'),
  makeTestCase('tc-2', 'Ready case', 'ready'),
  makeTestCase('tc-3', 'Approved case', 'approved'),
  makeTestCase('tc-4', 'Second approved case', 'approved'),
];

function renderList(items: TestCase[] = ITEMS) {
  return render(
    <TestCaseList items={items} onSelect={vi.fn()} onCreateNew={vi.fn()} />,
  );
}

function statusSelect(): HTMLSelectElement {
  return screen.getByTestId('tc-list-filter-status') as HTMLSelectElement;
}

describe('TestCaseList status filter (GH-453)', () => {
  it('offers exactly the lowercase states the loaded items carry', () => {
    renderList();

    const options = within(statusSelect())
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value);

    // First entry is the "All Statuses" reset option (empty value).
    expect(options[0]).toBe('');
    expect(options.slice(1)).toEqual(['draft', 'ready', 'approved']);
  });

  it('labels the options readably even though the values are lowercase', () => {
    renderList();

    const labels = within(statusSelect())
      .getAllByRole('option')
      .map((o) => o.textContent);

    expect(labels.slice(1)).toEqual(['Draft', 'Ready', 'Approved']);
  });

  it('narrows the list to the selected status instead of emptying it', async () => {
    const user = userEvent.setup();
    renderList();

    expect(screen.getAllByTestId(/^tc-row-tc-\d+$/)).toHaveLength(4);

    await user.selectOptions(statusSelect(), 'approved');

    const rows = screen.getAllByTestId(/^tc-row-tc-\d+$/);
    expect(rows).toHaveLength(2);
    expect(screen.getByText('Approved case')).toBeInTheDocument();
    expect(screen.getByText('Second approved case')).toBeInTheDocument();
    expect(screen.queryByText('Draft case')).not.toBeInTheDocument();
  });

  it('restores the full list when the filter is reset', async () => {
    const user = userEvent.setup();
    renderList();

    await user.selectOptions(statusSelect(), 'draft');
    expect(screen.getAllByTestId(/^tc-row-tc-\d+$/)).toHaveLength(1);

    await user.selectOptions(statusSelect(), '');
    expect(screen.getAllByTestId(/^tc-row-tc-\d+$/)).toHaveLength(4);
  });

  it('renders the row badge with the readable label, not the raw value', () => {
    renderList();

    expect(screen.getByTestId('tc-row-tc-1-status')).toHaveTextContent('Draft');
    expect(screen.getByTestId('tc-row-tc-3-status')).toHaveTextContent('Approved');
  });

  it('still filters a workspace whose TestCase workflow uses custom states', async () => {
    const user = userEvent.setup();
    renderList([
      makeTestCase('tc-9', 'Custom case', 'awaiting_sign_off'),
      makeTestCase('tc-8', 'Draft case', 'draft'),
    ]);

    const options = within(statusSelect())
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value);
    expect(options.slice(1)).toEqual(['draft', 'awaiting_sign_off']);

    await user.selectOptions(statusSelect(), 'awaiting_sign_off');
    expect(screen.getAllByTestId(/^tc-row-tc-\d+$/)).toHaveLength(1);
    expect(screen.getByText('Custom case')).toBeInTheDocument();
  });
});
