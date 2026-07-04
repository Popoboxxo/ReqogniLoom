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
import { attributeVisibilityApi } from '../../api';
import { useWorkspace } from '../../context/WorkspaceContext';

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
}) => {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();

  // -----------------------------------------------------------------------
  // State: selected entity type, visibility toggles, loading/error
  // -----------------------------------------------------------------------

  const [selectedEntityType, setSelectedEntityType] = useState<EntityType>('requirement');
  const [visibilityMap, setVisibilityMap] = useState<Record<string, boolean>>({});
  const [requiredMap, setRequiredMap] = useState<Record<string, boolean>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const [configs, setConfigs] = useState<AttributeVisibilityConfig[]>([]);

  useEffect(() => {
    let isMounted = true;
    attributeVisibilityApi.list()
      .then((data) => {
        if (isMounted) setConfigs(data);
      })
      .catch((err) => {
        if (isMounted) {
          const error = err instanceof Error ? err : new Error(String(err));
          setSaveError(error.message);
          onError?.(error);
        }
      });
    return () => { isMounted = false; };
  }, [onError]);

  useEffect(() => {
    // Filter configs for selected entity type
    const typeConfigs = configs.filter(
      (cfg) => cfg.entity_type === selectedEntityType
    );

    // Build visibility and required map from configs
    const vMap: Record<string, boolean> = {};
    const rMap: Record<string, boolean> = {};
    ENTITY_ATTRIBUTES[selectedEntityType]?.forEach((attr) => {
      const config = typeConfigs.find((cfg) => cfg.attribute_name === attr);
      
      // Indisputable defaults
      if (attr === 'title' || attr === 'description') {
        vMap[attr] = true;
        rMap[attr] = attr === 'title'; // title is always required, description is optional
      } else {
        vMap[attr] = config?.is_visible ?? true;
        rMap[attr] = config?.is_required ?? false;
      }
    });

    setVisibilityMap(vMap);
    setRequiredMap(rMap);
    setSaveError(null);
    setSaveSuccess(false);
  }, [selectedEntityType, configs]);

  // -----------------------------------------------------------------------
  // Handlers: toggle attribute visibility, save
  // -----------------------------------------------------------------------

  const handleToggleAttribute = useCallback((attrName: string, type: 'visible' | 'required'): void => {
    if (attrName === 'title' || attrName === 'description') return; // indisputable

    if (type === 'visible') {
      setVisibilityMap((prev) => {
        const nextVis = !prev[attrName];
        // If we hide it, it cannot be required
        if (!nextVis) {
          setRequiredMap((rPrev) => ({ ...rPrev, [attrName]: false }));
        }
        return { ...prev, [attrName]: nextVis };
      });
    } else {
      setRequiredMap((prev) => {
        const nextReq = !prev[attrName];
        // If we require it, it must be visible
        if (nextReq) {
          setVisibilityMap((vPrev) => ({ ...vPrev, [attrName]: true }));
        }
        return { ...prev, [attrName]: nextReq };
      });
    }
  }, []);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      // Build config records from visibility and required maps
      const payload: AttributeVisibilityConfig[] = Object.keys(visibilityMap).map(
        (attribute_name) => ({
          entity_type: selectedEntityType,
          attribute_name,
          is_visible: visibilityMap[attribute_name],
          is_required: requiredMap[attribute_name] || false,
        })
      );

      const response = await attributeVisibilityApi.upsert(payload);

      setConfigs((prev) => {
        // Update local configs with the response
        const newConfigs = [...prev];
        response.forEach((newCfg) => {
          const idx = newConfigs.findIndex(
            (c) => c.entity_type === newCfg.entity_type && c.attribute_name === newCfg.attribute_name
          );
          if (idx >= 0) newConfigs[idx] = newCfg;
          else newConfigs.push(newCfg);
        });
        return newConfigs;
      });

      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
      onSave?.(response);
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
            'Configure which fields are visible and required in artifact editors.'
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

      {/* Attribute Checklist Table */}
      <div>
        <h4
          style={{
            margin: '0 0 var(--space-2) 0',
            fontSize: 'var(--font-size-sm)',
            fontWeight: 600,
            color: 'var(--color-text-muted)',
          }}
        >
          {t('admin.visibleFields', 'Fields')}
        </h4>
        <div
          style={{
            maxHeight: '400px',
            overflowY: 'auto',
            background: 'var(--color-background)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)',
          }}
        >
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-border)' }}>
              <tr>
                <th style={{ padding: 'var(--space-2) var(--space-3)', fontSize: 'var(--font-size-xs)', fontWeight: 600 }}>Attribute</th>
                <th style={{ padding: 'var(--space-2) var(--space-3)', fontSize: 'var(--font-size-xs)', fontWeight: 600, textAlign: 'center' }}>{t('admin.visible', 'Visible')}</th>
                <th style={{ padding: 'var(--space-2) var(--space-3)', fontSize: 'var(--font-size-xs)', fontWeight: 600, textAlign: 'center' }}>{t('admin.required', 'Required')}</th>
              </tr>
            </thead>
            <tbody>
              {attributes.map((attr) => {
                const isIndisputable = attr === 'title' || attr === 'description';
                return (
                  <tr
                    key={attr}
                    style={{
                      borderBottom: '1px solid var(--color-border)',
                      transition: 'background 0.2s ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'var(--color-surface)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    <td style={{ padding: 'var(--space-2) var(--space-3)' }}>
                      <span
                        style={{
                          fontFamily: 'monospace',
                          fontSize: 'var(--font-size-xs)',
                          color: isIndisputable ? 'var(--color-text-muted)' : 'var(--color-text)',
                        }}
                      >
                        {attr}
                        {isIndisputable && ' (core)'}
                      </span>
                    </td>
                    <td style={{ padding: 'var(--space-2) var(--space-3)', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={visibilityMap[attr] ?? true}
                        disabled={isIndisputable}
                        onChange={() => handleToggleAttribute(attr, 'visible')}
                        style={{ cursor: isIndisputable ? 'not-allowed' : 'pointer', accentColor: 'var(--color-primary)' }}
                      />
                    </td>
                    <td style={{ padding: 'var(--space-2) var(--space-3)', textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={requiredMap[attr] ?? false}
                        disabled={isIndisputable}
                        onChange={() => handleToggleAttribute(attr, 'required')}
                        style={{ cursor: isIndisputable ? 'not-allowed' : 'pointer', accentColor: 'var(--color-primary)' }}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
