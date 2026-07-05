/**
 * REQ-L1-084: EntityTypeContext for Dynamic Field Rendering
 *
 * Provides type-aware context to form components, enabling:
 * - Entity type detection (requirement, architecture_element, test_case, etc.)
 * - Subtype routing (StReq vs. SyReq, ASIL levels, etc.)
 * - Attribute visibility configuration (via API persistence)
 *
 * Usage:
 * ```tsx
 * <EntityTypeProvider entityType="requirement" subType="StReq" visibleFields={...}>
 *   <RequirementForm />
 * </EntityTypeProvider>
 *
 * // Inside form:
 * const { entityType, visibleFields } = useEntityType();
 * if (visibleFields['moscow_priority']) {
 *   <MoscowPriorityDropdown />
 * }
 * ```
 *
 * leaf_id: COMP-RF-006-EntityTypeContext
 * interfaces: Context provider for all artifact editors
 */

import React, { createContext, useContext, ReactNode, useMemo } from 'react';

/**
 * Supported entity types for artifact editors.
 * Extensible enum for future artifact types.
 */
export type EntityType =
  | 'requirement'
  | 'stakeholder_need'
  | 'architecture_element'
  | 'test_case'
  | 'adr'
  | 'risk'
  | 'issue';

/**
 * Requirement subtypes (requirement-specific routing).
 * Maps to requirement categories or classification.
 */
export type RequirementSubType =
  | 'SyReq' // System Requirement
  | 'SWReq' // Software Requirement
  | 'HWReq'; // Hardware Requirement

/**
 * Architecture element subtypes.
 */
export type ArchitectureSubType =
  | 'component'
  | 'interface'
  | 'subsystem'
  | 'layer'
  | 'module';

/**
 * Union of all supported subtypes.
 */
export type EntitySubType = RequirementSubType | ArchitectureSubType | string;

/**
 * Attribute visibility configuration.
 * Persisted via API (GET/POST /api/v1/attribute-visibility-config/)
 *
 * Example:
 * {
 *   entity_type: 'requirement',
 *   entity_subtype: 'StReq',
 *   attribute: 'moscow_priority',
 *   is_visible: true
 * }
 */
export interface AttributeVisibilityConfig {
  id?: string;
  entity_type: EntityType;
  entity_subtype?: EntitySubType;
  attribute_name: string;
  is_visible: boolean;
  is_required?: boolean;
  created_at?: string;
  updated_at?: string;
}

/**
 * Visible fields map: attribute name → boolean
 * Example: { moscow_priority: true, complexity_fibonacci: false, ... }
 */
export type VisibleFieldsMap = Record<string, boolean>;

/**
 * Required fields map: attribute name → boolean
 * Example: { moscow_priority: true, description: false, ... }
 */
export type RequiredFieldsMap = Record<string, boolean>;

/**
 * Context value interface.
 */
export interface EntityTypeContextValue {
  /** Entity type (requirement, architecture_element, etc.) */
  entityType: EntityType;

  /** Optional subtype for entity-specific rendering (StReq, SyReq, etc.) */
  entitySubType?: EntitySubType;

  /** Visibility config for form fields */
  visibleFields: VisibleFieldsMap;

  /** Required config for form fields */
  requiredFields: RequiredFieldsMap;

  /** Check if a specific field is visible */
  isFieldVisible: (fieldName: string) => boolean;

  /** Check if a specific field is required */
  isFieldRequired: (fieldName: string) => boolean;

  /** Get all visible field names */
  getVisibleFieldNames: () => string[];

  /** Raw visibility config records (for admin UI) */
  visibilityConfigs?: AttributeVisibilityConfig[];
}

/**
 * Default context value (fallback).
 */
const defaultContextValue: EntityTypeContextValue = {
  entityType: 'requirement',
  visibleFields: {},
  requiredFields: {},
  isFieldVisible: () => true, // Default: show all
  isFieldRequired: () => false, // Default: optional
  getVisibleFieldNames: () => [],
};

/**
 * EntityTypeContext — created once per component tree.
 */
const EntityTypeContext = createContext<EntityTypeContextValue>(
  defaultContextValue
);

/**
 * Provider props for EntityTypeProvider.
 */
export interface EntityTypeProviderProps {
  children: ReactNode;
  entityType: EntityType;
  entitySubType?: EntitySubType;
  visibleFields?: VisibleFieldsMap;
  requiredFields?: RequiredFieldsMap;
  visibilityConfigs?: AttributeVisibilityConfig[];
}

/**
 * EntityTypeProvider — wraps form components to provide type-aware context.
 *
 * @param props - Configuration for entity type and visibility
 * @returns Provider wrapper
 */
export const EntityTypeProvider: React.FC<EntityTypeProviderProps> = ({
  children,
  entityType,
  entitySubType,
  visibleFields = {},
  requiredFields = {},
  visibilityConfigs = [],
}) => {
  // Memoize computed context value
  const value = useMemo<EntityTypeContextValue>(() => {
    return {
      entityType,
      entitySubType,
      visibleFields,
      requiredFields,
      visibilityConfigs,
      isFieldVisible: (fieldName: string): boolean => {
        // If field explicitly configured, respect that
        if (fieldName in visibleFields) {
          return visibleFields[fieldName];
        }
        // Default: show all fields if not configured
        return true;
      },
      isFieldRequired: (fieldName: string): boolean => {
        if (fieldName in requiredFields) {
          return requiredFields[fieldName];
        }
        // Default: optional
        return false;
      },
      getVisibleFieldNames: (): string[] => {
        return Object.entries(visibleFields)
          .filter(([, isVisible]) => isVisible)
          .map(([fieldName]) => fieldName);
      },
    };
  }, [entityType, entitySubType, visibleFields, requiredFields, visibilityConfigs]);

  return (
    <EntityTypeContext.Provider value={value}>
      {children}
    </EntityTypeContext.Provider>
  );
};

/**
 * Hook to consume EntityTypeContext.
 *
 * Usage:
 * ```tsx
 * const { entityType, visibleFields, isFieldVisible } = useEntityType();
 * if (isFieldVisible('moscow_priority')) {
 *   // render field
 * }
 * ```
 *
 * @returns Current context value
 * @throws Error if used outside EntityTypeProvider
 */
export const useEntityType = (): EntityTypeContextValue => {
  const context = useContext(EntityTypeContext);
  if (!context) {
    throw new Error('useEntityType must be used within EntityTypeProvider');
  }
  return context;
};

/**
 * Utility: Check if current entity is a requirement type.
 *
 * @param context - EntityTypeContextValue
 * @returns true if entityType === 'requirement'
 */
export const isRequirement = (context: EntityTypeContextValue): boolean => {
  return context.entityType === 'requirement';
};

/**
 * Utility: Check if current entity is architecture element type.
 */
export const isArchitectureElement = (context: EntityTypeContextValue): boolean => {
  return context.entityType === 'architecture_element';
};

/**
 * Utility: Check if requirement is system requirement subtype.
 */
export const isSysReq = (context: EntityTypeContextValue): boolean => {
  return (
    isRequirement(context) &&
    context.entitySubType === 'SyReq'
  );
};

/**
 * Utility: Check if requirement is stakeholder requirement subtype.
 */
export const isStReq = (context: EntityTypeContextValue): boolean => {
  return (
    isRequirement(context) &&
    context.entitySubType === 'StReq'
  );
};
