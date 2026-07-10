/**
 * REQ-L2-AS-037: CustomFieldsDisplay — read-only Key | Value table of an
 * artifact's custom_fields. Renders nothing when the map is empty/undefined.
 *
 * Named export only (no default export).
 */

import { useTranslation } from 'react-i18next';
import type { CustomFields, CustomFieldValue } from '../../types';

interface CustomFieldsDisplayProps {
  value?: CustomFields;
}

const renderValue = (value: CustomFieldValue): string => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
};

export const CustomFieldsDisplay: React.FC<CustomFieldsDisplayProps> = ({ value }) => {
  const { t } = useTranslation();
  const entries = value ? Object.entries(value) : [];
  if (entries.length === 0) return null;

  return (
    <table
      data-testid="custom-fields-display"
      style={{
        width: '100%',
        borderCollapse: 'collapse',
        fontSize: 'var(--font-size-sm)',
      }}
    >
      <thead>
        <tr>
          <th
            style={{
              textAlign: 'left',
              padding: 'var(--space-2)',
              borderBottom: '1px solid var(--color-border)',
              color: 'var(--color-text-muted)',
              fontWeight: 600,
            }}
          >
            {t('customFields.key')}
          </th>
          <th
            style={{
              textAlign: 'left',
              padding: 'var(--space-2)',
              borderBottom: '1px solid var(--color-border)',
              color: 'var(--color-text-muted)',
              fontWeight: 600,
            }}
          >
            {t('customFields.value')}
          </th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([key, val]) => (
          <tr key={key} data-testid="custom-fields-display-row">
            <td
              style={{
                padding: 'var(--space-2)',
                borderBottom: '1px solid var(--color-border)',
                fontFamily: 'monospace',
                color: 'var(--color-text)',
              }}
            >
              {key}
            </td>
            <td
              style={{
                padding: 'var(--space-2)',
                borderBottom: '1px solid var(--color-border)',
                color: 'var(--color-text)',
              }}
            >
              {renderValue(val)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};

CustomFieldsDisplay.displayName = 'CustomFieldsDisplay';
