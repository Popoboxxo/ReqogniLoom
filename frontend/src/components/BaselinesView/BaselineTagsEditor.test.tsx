/**
 * F4.3 — Baseline tag editor (REQ-L1-018).
 *
 * Pins the component contract the detail panel mounts:
 *   - existing tags render as chips
 *   - clicking "add" appends the typed label
 *   - Enter in the input appends (keyboard parity with the add button)
 *   - clicking a chip's remove control drops that label
 *   - a rejected save (backend 400 VALIDATION_ERROR) renders inline in
 *     `baseline-tag-error` instead of disappearing into a console
 *   - a label the backend would reject is caught before the network call
 *   - a label with Unicode letters (`ü`, `ß`) is accepted — the client charset
 *     mirrors Python's Unicode-aware `\w`, not JavaScript's ASCII-only one
 *   - after a save the editor drops its draft and renders the server-sorted
 *     list as clean (not dirty)
 *   - removing a chip keeps focus inside the editor
 *
 * i18n is stubbed the same way as the neighbouring container tests (the key,
 * or the string fallback, is returned verbatim) so the assertions do not
 * depend on the active locale.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('react-i18next', () => {
  const t = (key: string, fallbackOrOptions?: string | Record<string, unknown>): string =>
    typeof fallbackOrOptions === 'string' ? fallbackOrOptions : key;
  return { useTranslation: () => ({ t }) };
});

import { BaselineTagsEditor } from './BaselineTagsEditor';

const renderEditor = (
  props: Partial<Parameters<typeof BaselineTagsEditor>[0]> = {}
): ReturnType<typeof render> =>
  render(<BaselineTagsEditor tags={[]} onSave={vi.fn().mockResolvedValue(undefined)} {...props} />);

describe('BaselineTagsEditor (F4.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the existing tags as chips', () => {
    renderEditor({ tags: ['Release', 'RC1'] });

    const chips = screen.getAllByTestId('baseline-tag-chip');
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent('Release');
    expect(chips[1]).toHaveTextContent('RC1');
    expect(screen.getByTestId('baseline-tags')).toBeInTheDocument();
  });

  it('adds the typed label via the add button', async () => {
    const user = userEvent.setup();
    renderEditor({ tags: ['Release'] });

    await user.type(screen.getByTestId('baseline-tag-input'), 'RC1');
    await user.click(screen.getByTestId('baseline-tag-add-btn'));

    expect(screen.getAllByTestId('baseline-tag-chip')).toHaveLength(2);
    expect(screen.getByText('RC1')).toBeInTheDocument();
    // The input is cleared so the next label starts from an empty field.
    expect(screen.getByTestId('baseline-tag-input')).toHaveValue('');
  });

  it('adds a tag on Enter (keyboard path)', async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.type(screen.getByTestId('baseline-tag-input'), 'Release{Enter}');

    expect(screen.getAllByTestId('baseline-tag-chip')).toHaveLength(1);
    expect(screen.getByTestId('baseline-tag-chip')).toHaveTextContent('Release');
  });

  it('removes a tag when its remove control is clicked', async () => {
    const user = userEvent.setup();
    renderEditor({ tags: ['Release', 'RC1'] });

    await user.click(screen.getAllByTestId('baseline-tag-remove-btn')[0]!);

    const chips = screen.getAllByTestId('baseline-tag-chip');
    expect(chips).toHaveLength(1);
    expect(chips[0]).toHaveTextContent('RC1');
  });

  it('saves the edited set through onSave', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor({ tags: ['Release'], onSave });

    await user.type(screen.getByTestId('baseline-tag-input'), 'RC1{Enter}');
    await user.click(screen.getByTestId('baseline-tag-save-btn'));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(['Release', 'RC1']);
    });
  });

  it('shows a rejected save inline (400 VALIDATION_ERROR)', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({
      error: { code: 'VALIDATION_ERROR', message: 'Invalid baseline tag(s).' },
    });
    renderEditor({ tags: [], onSave });

    await user.type(screen.getByTestId('baseline-tag-input'), 'Release{Enter}');
    await user.click(screen.getByTestId('baseline-tag-save-btn'));

    const errorBox = await screen.findByTestId('baseline-tag-error');
    expect(errorBox).toHaveTextContent('Invalid baseline tag(s).');
    expect(errorBox).toHaveAttribute('role', 'alert');
    // The draft survives the rejection so the user can correct it in place.
    expect(screen.getByTestId('baseline-tag-chip')).toHaveTextContent('Release');
  });

  it('rejects a label the backend would refuse before calling onSave', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor({ onSave });

    // Comma is outside the backend's allowed label shape.
    await user.type(screen.getByTestId('baseline-tag-input'), 'bad,label{Enter}');

    expect(screen.queryAllByTestId('baseline-tag-chip')).toHaveLength(0);
    expect(screen.getByTestId('baseline-tag-error')).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('enforces the maximum tag count', async () => {
    const user = userEvent.setup();
    renderEditor({ tags: ['one', 'two'], maxTags: 2 });

    await user.type(screen.getByTestId('baseline-tag-input'), 'three{Enter}');

    expect(screen.getAllByTestId('baseline-tag-chip')).toHaveLength(2);
    const errorBox = screen.getByTestId('baseline-tag-error');
    expect(within(errorBox).queryByText('three')).not.toBeInTheDocument();
  });

  // F1 (ui-review): the backend's `_TAG_PATTERN` uses Python's Unicode-aware
  // `\w`; an ASCII-only JS `\w` rejected labels the server accepts.
  it('accepts Unicode labels the backend also accepts (F1)', async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.type(screen.getByTestId('baseline-tag-input'), 'Prüfung{Enter}');
    await user.type(screen.getByTestId('baseline-tag-input'), 'Straße-2{Enter}');

    const chips = screen.getAllByTestId('baseline-tag-chip');
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent('Prüfung');
    expect(chips[1]).toHaveTextContent('Straße-2');
    expect(screen.queryByTestId('baseline-tag-error')).not.toBeInTheDocument();
  });

  // F2 (ui-review): the backend returns the stored labels case-insensitively
  // sorted; an order-sensitive dirty check left the editor permanently dirty
  // after a save and never showed the server's order.
  it('renders the server order after a save and is no longer dirty (F2)', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(<BaselineTagsEditor tags={[]} onSave={onSave} />);

    await user.type(screen.getByTestId('baseline-tag-input'), 'zulu{Enter}alpha{Enter}');
    await user.click(screen.getByTestId('baseline-tag-save-btn'));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(['zulu', 'alpha']);
    });

    // What the refetch hands back: the persisted, server-sorted set.
    rerender(<BaselineTagsEditor tags={['alpha', 'zulu']} onSave={onSave} />);

    const chips = screen.getAllByTestId('baseline-tag-chip');
    expect(chips[0]).toHaveTextContent(/^alpha/);
    expect(chips[1]).toHaveTextContent(/^zulu/);
    // An order-only difference is not an edit: the save button stays disabled.
    expect(screen.getByTestId('baseline-tag-save-btn')).toBeDisabled();
  });

  // F3 (ui-review): removing a chip unmounted the focused button and dropped
  // focus to <body>.
  it('moves focus to the neighbouring remove control after a removal (F3)', async () => {
    const user = userEvent.setup();
    renderEditor({ tags: ['Release', 'RC1', 'Final'] });

    await user.click(screen.getAllByTestId('baseline-tag-remove-btn')[1]!);

    const remaining = screen.getAllByTestId('baseline-tag-remove-btn');
    expect(remaining).toHaveLength(2);
    // "Final" moved into the removed chip's slot and takes over focus.
    expect(document.activeElement).toBe(remaining[1]);
  });

  it('returns focus to the text field when the last chip is removed (F3)', async () => {
    const user = userEvent.setup();
    renderEditor({ tags: ['Release'] });

    await user.click(screen.getByTestId('baseline-tag-remove-btn'));

    expect(document.activeElement).toBe(screen.getByTestId('baseline-tag-input'));
  });

  // F3 (ui-review): the save button used to disable itself on press (focus ->
  // body) with no progress affordance at all.
  it('announces an in-flight save and keeps focus on the button (F3)', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockReturnValue(new Promise<void>(() => {}));
    renderEditor({ onSave });

    await user.type(screen.getByTestId('baseline-tag-input'), 'Release{Enter}');
    const saveButton = screen.getByTestId('baseline-tag-save-btn');
    await user.click(saveButton);

    await waitFor(() => {
      expect(saveButton).toHaveAttribute('aria-busy', 'true');
    });
    expect(saveButton).not.toBeDisabled();
    expect(document.activeElement).toBe(saveButton);
  });

  // F8 (ui-review): the input's aria-label duplicated the add button's visible
  // label, so two controls shared one accessible name.
  it('names the text input differently from the add button (F8)', () => {
    renderEditor();

    expect(screen.getByTestId('baseline-tag-input')).toHaveAccessibleName(
      'baselines.tagInputLabel',
    );
    expect(screen.getByTestId('baseline-tag-add-btn')).toHaveAccessibleName(
      'baselines.tagAdd',
    );
  });
});
