/**
 * Single source of truth for the `admin.entityType.*` i18n keys used to
 * label artifact entity types (CsvImport, AttributeVisibilityAdmin).
 *
 * Keys match the backend's PascalCase artifact_type values where the
 * consumer already works in that vocabulary (CsvImport); consumers that
 * work in a different local vocabulary (e.g. AttributeVisibilityAdmin's
 * snake_case `<select>` option values) reference the same key constants
 * by name instead of duplicating the i18n key string literal, so renaming
 * or adding an entity type only touches one place.
 */
export const ENTITY_TYPE_I18N_KEYS: Record<string, string> = {
  Requirement: "admin.entityType.requirement",
  ArchitectureElement: "admin.entityType.architectureElement",
  TestCase: "admin.entityType.testCase",
  StakeholderNeed: "admin.entityType.stakeholderNeed",
  Adr: "admin.entityType.adr",
  Risk: "admin.entityType.risk",
  Issue: "admin.entityType.issue",
} as const;
