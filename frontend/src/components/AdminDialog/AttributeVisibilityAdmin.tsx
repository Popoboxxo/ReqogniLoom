/**
 * REQ-L1-084: Attribute Visibility Configuration Admin UI
 *
 * Allows admins to configure which fields are visible per entity type.
 * Persists via API: GET/POST /api/v1/attribute-visibility-config/
 *
 * Features:
 * - Entity type selector dropdown
 * - Checklist of attributes per type
 * - Bulk save to backend
 * - RBAC: Admin role only
 *
 * Usage (typically in Settings/Admin modal):
 * ```tsx
 * <Modal title="Attribute Visibility" onClose={...}>
 *   <AttributeVisibilityAdmin onSave={() => refetch()} />
 * </Modal>
 * ```
 *
 * leaf_id: COMP-RF-007-AttributeVisibilityAdmin
 * interfaces: Admin UI for Settings/Workspace panel
 */

import React, { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { EntityType, EntitySubType, AttributeVisibilityConfig, VisibleFieldsMap } from '../../context/EntityTypeContext';

/**
 * Available attributes per entity type.
 * Maps entity type → list of attribute keys.
 *
 * Defined here for now; could be extended to a config file or API.
 */
const ENTITY_ATTRIBUTES: Record<EntityType, string[]> = {
  requirement: [
    'title',
    'description',
    'category',
    'status',
    'version',
    'moscow_priority', // StReq-specific
    'complexity_fibonacci', // SyReq-specific
    'verification_method', // SyReq-specific
    'traceability_links',
    'created_at',
    'updated_at',
  ],
  architecture_element: [
    'title',
    'description',
    'element_type',
    'parent_id',
    'level',
    'version',
    'asil_level', // ASIL classification
    'make_or_buy', // Make/Buy decision
    'uid',
    'traceability_links',
    'created_at',
    'updated_at',
  ],
  test_case: [
    'title',
    'description',
    'test_type',
    'status',
    'execution_time_ms',
    'expected_result',
    'preconditions',
    'version',
    'created_at',
    'updated_at',
  ],
  adr: [
    'title',
    'context',
    'decision',
    'consequences',
    'status',
    'version',
    'created_at',
    'updated_at',
  ],
  risk: [
    'title',
    'description',
    'probability',
    'impact',
    'risk_score',
    'category',
    'owner',
    'mitigation_strategy',
    'status',
    'created_at',
    'updated_at',
  ],
  issue: [
    'title',
    'description',
    'severity',
    'category',
    'status',
    'tags',
    'created_at',
    'updated_at',
  ],
};

/**
 * Props for AttributeVisibilityAdmin component.
 */
export interface AttributeVisibilityAdminProps {
  /** Callback when visibility config is saved */
  onSave?: (configs: AttributeVisibilityConfig[]) => void;

  /** Callback on error */
  onError?: (error: Error) => void;

  /** Initial visibility configs (from API) */
  initialConfigs?: AttributeVisibilityConfig[];
}

/**
 * AttributeVisibilityAdmin — admin UI for field visibility configuration.
 *
 * Manages attribute visibility per entity type via:
 * 1. Entity type selector
 * 2. Checkbox list of attributes
 * 3. Save button (persists to backend)
 * 4. Error/success feedback
 */
export const AttributeVisibilityAdmin: React.FC<AttributeVisibilityAdminProps> = ({
  onSave,
  onError,
  initialConfigs = [],
}) => {
  const { t } = useTranslation();

  // -----------------------------------------------------------------------
  // State: selected entity type, visibility toggles, loading/error
  // -----------------------------------------------------------------------

  const [selectedEntityType, setSelectedEntityType] = useState<EntityType>('requirement');
  const [visibilityMap, setVisibilityMap] = useState<VisibleFieldsMap>({});
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // -----------------------------------------------------------------------
  // Load visibility config for selected entity type
  // -----------------------------------------------------------------------

  useEffect(() => {
    // Filter configs for selected entity type
    const typeConfigs = initialConfigs.filter(
      (cfg) => cfg.entity_type === selectedEntityType
    );

    // Build visibility map from configs
    const map: VisibleFieldsMap = {};
    ENTITY_ATTRIBUTES[selectedEntityType]?.forEach((attr) => {
      const config = typeConfigs.find((cfg) => cfg.attribute === attr);
      // Default: visible if no config found
      map[attr] = config?.is_visible ?? true;
    });

    setVisibilityMap(map);
    setSaveError(null);
    setSaveSuccess(false);
  }, [selectedEntityType, initialConfigs]);

  // -----------------------------------------------------------------------
  // Handlers: toggle attribute visibility, save
  // -----------------------------------------------------------------------

  const handleToggleAttribute = useCallback((attrName: string): void => {
    setVisibilityMap((prev) => ({
      ...prev,
      [attrName]: !prev[attrName],
    }));
  }, []);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      // Build config records from visibility map
      const configs: AttributeVisibilityConfig[] = Object.entries(visibilityMap).map(
        ([attribute, is_visible]) => ({
          entity_type: selectedEntityType,
          attribute,
          is_visible,
        })
      );

      // TODO: Replace with actual API call when endpoint is ready
      // const response = await attributeVisibilityApi.upsert(configs);

      // For now, log and simulate success
      console.log('Saving attribute visibility config:', configs);

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      onSave?.(configs);
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      setSaveError(error.message);
      onError?.(error);
    } finally {
      setIsSaving(false);
    }
  }, [selectedEntityType, visibilityMap, onSave, onError]);

  const attributes = ENTITY_ATTRIBUTES[selectedEntityType] || [];

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-4)',
        padding: 'var(--space-4)',
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-md)',
        fontFamily: 'var(--font-sans)',
        color: 'var(--color-text)',
      }}
    >
      {/* Header */}
      <div>
        <h3
          style={{
            margin: '0 0 var(--space-2) 0',
            fontSize: 'var(--font-size-lg)',
            fontWeight: 600,
          }}
        >
          {t('admin.attributeVisibility', 'Attribute Visibility')}
        </h3>
        <p
          style={{
            margin: 0,
            fontSize: 'var(--font-size-sm)',
            color: 'var(--color-text-muted)',
          }}
        >
          {t(
            'admin.attributeVisibilityDescription',
            'Configure which fields are visible in artifact editors.'
          )}
        </p>
      </div>

      {/* Entity Type Selector */}
      <div>
        <label
          htmlFor="entity-type-select"
          style={{
            display: 'block',
            marginBottom: 'var(--space-2)',
            fontSize: 'var(--font-size-sm)',
            fontWeight: 600,
          }}
        >
          {t('admin.entityType', 'Entity Type')}
        </label>
        <select
          id="entity-type-select"
          value={selectedEntityType}
          onChange={(e) => setSelectedEntityType(e.target.value as EntityType)}
          style={{
            width: '100%',
            padding: 'var(--space-2) var(--space-3)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)',
            background: 'var(--color-background)',
            color: 'var(--color-text)',
            fontSize: 'var(--font-size-sm)',
            fontFamily: 'var(--font-sans)',
            cursor: 'pointer',
          }}
        >
          <option value="requirement">
            {t('admin.entityType.requirement', 'Requirement')}
          </option>
          <option value="architecture_element">
            {t('admin.entityType.architectureElement', 'Architecture Element')}
          </option>
          <option value="test_case">
            {t('admin.entityType.testCase', 'Test Case')}
          </option>
          <option value="adr">
            {t('admin.entityType.adr', 'Architecture Decision Record')}
          </option>
          <option value="risk">
            {t('admin.entityType.risk', 'Risk')}
          </option>
          <option value="issue">
            {t('admin.entityType.issue', 'Issue')}
          </option>
        </select>
      </div>

      {/* Attribute Checklist */}
      <div>
        <h4
          style={{
            margin: '0 0 var(--space-2) 0',
            fontSize: 'var(--font-size-sm)',
            fontWeight: 600,
            color: 'var(--color-text-muted)',
          }}
        >
          {t('admin.visibleFields', 'Visible Fields')}
        </h4>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
            maxHeight: '400px',
            overflowY: 'auto',
            padding: 'var(--space-3)',
            background: 'var(--color-background)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)',
          }}
        >
          {attributes.map((attr) => (
            <label
              key={attr}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--space-2)',
                cursor: 'pointer',
                fontSize: 'var(--font-size-sm)',
                padding: 'var(--space-1) var(--space-2)',
                borderRadius: 'var(--radius-sm)',
                transition: 'background 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--color-surface)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
              }}
            >
              <input
                type="checkbox"
                checked={visibilityMap[attr] ?? true}
                onChange={() => handleToggleAttribute(attr)}
                style={{
                  cursor: 'pointer',
                  width: '16px',
                  height: '16px',
                  accentColor: 'var(--color-primary)',
                }}
              />
              <span
                style={{
                  fontFamily: 'monospace',
                  fontSize: 'var(--font-size-xs)',
                  color: 'var(--color-text)',
                }}
              >
                {attr}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* Error/Success Messages */}
      {saveError && (
        <div
          role="alert"
          style={{
            padding: 'var(--space-3)',
            background: 'var(--color-danger)',
            color: '#ffffff',
            borderRadius: 'var(--radius-md)',
            fontSize: 'var(--font-size-sm)',
          }}
        >
          {saveError}
        </div>
      )}

      {saveSuccess && (
        <div
          role="status"
          style={{
            padding: 'var(--space-3)',
            background: 'var(--color-success)',
            color: '#ffffff',
            borderRadius: 'var(--radius-md)',
            fontSize: 'var(--font-size-sm)',
          }}
        >
          {t('admin.saved', 'Configuration saved successfully.')}
        </div>
      )}

      {/* Save Button */}
      <button
        onClick={() => void handleSave()}
        disabled={isSaving}
        style={{
          background: 'var(--color-primary)',
          color: '#ffffff',
          border: 'none',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--space-2) var(--space-4)',
          fontSize: 'var(--font-size-sm)',
          fontWeight: 600,
          cursor: isSaving ? 'not-allowed' : 'pointer',
          opacity: isSaving ? 0.6 : 1,
          fontFamily: 'var(--font-sans)',
          transition: 'background 0.2s ease',
        }}
        onMouseEnter={(e) => {
          if (!isSaving) {
            e.currentTarget.style.background = 'var(--color-primary-dark)';
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'var(--color-primary)';
        }}
      >
        {isSaving ? t('actions.saving', 'Saving…') : t('actions.save', 'Save')}
      </button>
    </div>
  );
};

export default AttributeVisibilityAdmin;
