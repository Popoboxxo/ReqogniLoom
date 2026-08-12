import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { useState } from 'react';
import { CustomFieldsEditor } from './CustomFieldsEditor';
import type { CustomFields } from '../../types';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, d?: string) => d ?? k }),
}));

/**
 * Issue #423 — mirrors how every consuming form (RequirementForm, NeedForm,
 * ArchitectureForm, TestCaseForm) wires this component: a parent component
 * owning the `custom_fields` map via `onChange={setCustomFields}`.
 */
function Harness(): JSX.Element {
  const [customFields, setCustomFields] = useState<CustomFields>({});
  return (
    <>
      <CustomFieldsEditor value={customFields} onChange={setCustomFields} />
      <output data-testid="harness-value">{JSON.stringify(customFields)}</output>
    </>
  );
}

describe('CustomFieldsEditor', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it(
    'does not log "Cannot update a component while rendering a different component" ' +
      'when rows are added/edited (issue #423)',
    () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      const { getByTestId, getAllByTestId } = render(<Harness />);

      fireEvent.click(getByTestId('custom-field-add'));
      fireEvent.change(getAllByTestId('custom-field-key')[0], { target: { value: 'foo' } });
      fireEvent.change(getAllByTestId('custom-field-value')[0], { target: { value: 'bar' } });
      fireEvent.click(getByTestId('custom-field-add'));
      fireEvent.click(getAllByTestId('custom-field-remove')[1]);

      const offendingCall = errorSpy.mock.calls.find((call) =>
        String(call[0]).includes('Cannot update a component')
      );
      expect(offendingCall).toBeUndefined();
    }
  );

  it('still propagates row edits to the parent onChange handler', () => {
    const { getByTestId, getAllByTestId } = render(<Harness />);

    fireEvent.click(getByTestId('custom-field-add'));
    fireEvent.change(getAllByTestId('custom-field-key')[0], { target: { value: 'foo' } });
    fireEvent.change(getAllByTestId('custom-field-value')[0], { target: { value: 'bar' } });

    expect(getByTestId('harness-value').textContent).toBe(JSON.stringify({ foo: 'bar' }));
  });

  it('removing a row propagates the reduced map to the parent', () => {
    const { getByTestId, getAllByTestId } = render(<Harness />);

    fireEvent.click(getByTestId('custom-field-add'));
    fireEvent.change(getAllByTestId('custom-field-key')[0], { target: { value: 'foo' } });
    fireEvent.change(getAllByTestId('custom-field-value')[0], { target: { value: 'bar' } });
    fireEvent.click(getAllByTestId('custom-field-remove')[0]);

    expect(getByTestId('harness-value').textContent).toBe(JSON.stringify({}));
  });
});
