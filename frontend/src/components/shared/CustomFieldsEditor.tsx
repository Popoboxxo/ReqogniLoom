/**
 * REQ-L2-AS-037: CustomFieldsEditor — edit user-defined flat key-value
 * attributes stored on an artifact's custom_fields map.
 *
 * The editor is uncontrolled internally (row list with local ids so empty /
 * duplicate keys can exist transiently) and reports the derived, cleaned
 * custom_fields map to the parent via onChange. Type coercion (string / number
 * / boolean) happens here so the backend receives correctly typed scalars; the
 * backend re-validates (single source of truth in persistence.custom_fields).
 *
 * Named export only (no default export). Styling uses tokens.css variables to
 * stay consistent with the surrounding editor forms.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { CustomFields, CustomFieldValue } from '../../types';

type FieldType = 'string' | 'number' | 'boolean';

interface FieldRow {
  id: string;
  key: string;
  value: string;
  type: FieldType;
}

interface CustomFieldsEditorProps {
  /** Current custom_fields map (from the loaded artifact). */
  value?: CustomFields;
  /** Called with the derived, cleaned map whenever a row changes. */
  onChange: (next: CustomFields) => void;
  /** Disable all inputs (e.g. while saving). */
  disabled?: boolean;
}

let rowSeq = 0;
const nextRowId = (): string => {
  rowSeq += 1;
  return `cf-${rowSeq}-${Date.now()}`;
};

const inferType = (value: CustomFieldValue): FieldType => {
  if (typeof value === 'number') return 'number';
  if (typeof value === 'boolean') return 'boolean';
  return 'string';
};

const toRows = (value: CustomFields | undefined): FieldRow[] => {
  if (!value) return [];
  return Object.entries(value).map(([key, val]) => ({
    id: nextRowId(),
    key,
    value: val === null || val === undefined ? '' : String(val),
    type: inferType(val),
  }));
};

/**
 * Build the outgoing custom_fields map from the current rows. Rows with an
 * empty key are skipped. Numbers that fail to parse fall back to null.
 */
const rowsToMap = (rows: FieldRow[]): CustomFields => {
  const out: CustomFields = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (!key) continue;
    let value: CustomFieldValue;
    if (row.type === 'number') {
      value = row.value.trim() === '' ? null : Number(row.value);
      if (typeof value === 'number' && Number.isNaN(value)) value = null;
    } else if (row.type === 'boolean') {
      value = row.value === 'true';
    } else {
      value = row.value;
    }
    out[key] = value;
  }
  return out;
};

export const CustomFieldsEditor: React.FC<CustomFieldsEditorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  const { t } = useTranslation();
  // Seed rows once from the incoming value; the editor owns the row list after.
  const [rows, setRows] = useState<FieldRow[]>(() => toRows(value));
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Issue #423: `onChange` (the parent form's setState, e.g. RequirementForm's
  // setCustomFields) used to be called synchronously from inside the
  // `setRows` updater functions below. React can invoke that updater during
  // this component's render phase, which triggered "Cannot update a
  // component (RequirementForm) while rendering a different component
  // (CustomFieldsEditor)". Row mutations now only update local `rows`
  // state; propagating the derived map to the parent happens here, in an
  // effect that runs after commit, never during render. The `isFirstRun`
  // guard skips the initial mount so the parent isn't redundantly re-set to
  // an equivalent value it already owns.
  const isFirstRun = useRef(true);
  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false;
      return;
    }
    onChangeRef.current(rowsToMap(rows));
  }, [rows]);

  const updateRow = useCallback((id: string, patch: Partial<FieldRow>): void => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }, []);

  const addRow = useCallback((): void => {
    setRows((prev) => [
      ...prev,
      { id: nextRowId(), key: '', value: '', type: 'string' as FieldType },
    ]);
  }, []);

  const removeRow = useCallback((id: string): void => {
    setRows((prev) => prev.filter((r) => r.id !== id));
  }, []);

  const inputStyle: React.CSSProperties = useMemo(
    () => ({
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-md)',
      padding: 'var(--space-2)',
      fontFamily: 'var(--font-sans)',
      fontSize: 'var(--font-size-sm)',
      color: 'var(--color-text)',
      background: 'var(--color-surface)',
      boxSizing: 'border-box',
    }),
    []
  );

  return (
    <div data-testid="custom-fields-editor">
      {rows.length === 0 && (
        <p
          style={{
            color: 'var(--color-text-muted)',
            fontSize: 'var(--font-size-sm)',
            margin: '0 0 var(--space-3) 0',
          }}
        >
          {t('customFields.empty')}
        </p>
      )}

      {rows.map((row) => (
        <div
          key={row.id}
          data-testid="custom-field-row"
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr 120px 32px',
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-2)',
            alignItems: 'center',
          }}
        >
          <input
            data-testid="custom-field-key"
            aria-label={t('customFields.key')}
            placeholder={t('customFields.key')}
            value={row.key}
            disabled={disabled}
            onChange={(e) => updateRow(row.id, { key: e.target.value })}
            style={inputStyle}
          />

          {row.type === 'boolean' ? (
            <select
              data-testid="custom-field-value"
              aria-label={t('customFields.value')}
              value={row.value === 'true' ? 'true' : 'false'}
              disabled={disabled}
              onChange={(e) => updateRow(row.id, { value: e.target.value })}
              style={inputStyle}
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <input
              data-testid="custom-field-value"
              aria-label={t('customFields.value')}
              placeholder={t('customFields.value')}
              type={row.type === 'number' ? 'number' : 'text'}
              value={row.value}
              disabled={disabled}
              onChange={(e) => updateRow(row.id, { value: e.target.value })}
              style={inputStyle}
            />
          )}

          <select
            data-testid="custom-field-type"
            aria-label={t('customFields.type')}
            value={row.type}
            disabled={disabled}
            onChange={(e) => {
              const type = e.target.value as FieldType;
              // Reset boolean value to a valid option when switching to boolean.
              const value = type === 'boolean' && row.value !== 'true' ? 'false' : row.value;
              updateRow(row.id, { type, value });
            }}
            style={inputStyle}
          >
            <option value="string">{t('customFields.typeString')}</option>
            <option value="number">{t('customFields.typeNumber')}</option>
            <option value="boolean">{t('customFields.typeBoolean')}</option>
          </select>

          <button
            type="button"
            data-testid="custom-field-remove"
            aria-label={t('customFields.remove')}
            title={t('customFields.remove')}
            disabled={disabled}
            onClick={() => removeRow(row.id)}
            style={{
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--color-surface)',
              color: 'var(--color-danger)',
              cursor: disabled ? 'not-allowed' : 'pointer',
              height: '100%',
              fontSize: 'var(--font-size-base)',
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
      ))}

      <button
        type="button"
        data-testid="custom-field-add"
        className="btn-secondary"
        disabled={disabled}
        onClick={addRow}
        style={{ marginTop: 'var(--space-2)' }}
      >
        + {t('customFields.addField')}
      </button>
    </div>
  );
};

CustomFieldsEditor.displayName = 'CustomFieldsEditor';
