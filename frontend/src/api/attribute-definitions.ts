/**
 * ARCH-L1-001 ReactFrontend — Attribute Definition API.
 *
 * Wraps /api/v1/attribute-defaults/ (tenant-wide, per item_type + preset) and
 * /api/v1/workspaces/{id}/attribute-definitions/{item_type}/ (resolved copy).
 *
 * The resolved shape is what ArtifactForm renders and what the table view
 * derives its columns and filter operators from — it is the single client-side
 * source for "what fields does this artifact type have".
 */

import { apiClient } from "./client";
import type { UUID, WorkspacePreset } from "../types";

/**
 * The 11 bootstrapped item types (verified against
 * `backend/attribute_definitions/schema.py::ITEM_TYPES`) — kept as its own
 * union instead of a bare `string` because the frontend already has two other,
 * incompatible item-type vocabularies (`WorkflowEntityType`,
 * `ArtifactKind` in `components/shared/ArtifactInspector/types.ts`, the latter
 * lowercase camelCase) that a caller could pass here by mistake and get a
 * silent 404 instead of a compile error.
 */
export type AttributeItemType =
  | "Requirement"
  | "StakeholderNeed"
  | "ArchitectureElement"
  | "TestCase"
  | "Adr"
  | "Risk"
  | "Issue"
  | "Goal"
  | "Icd"
  | "GlossaryTerm"
  | "ChangeRequest";

export type AttributeKind = "core" | "extended";

export type AttributeType =
  | "text"
  | "textarea"
  | "number"
  | "boolean"
  | "enum"
  | "multi-enum"
  | "date"
  | "reference"
  | "user"
  | "widget";

/** `"workflow"` = changeable only through a workflow transition. */
export type AttributeEditable = boolean | "workflow";

/** Display density only — never a visibility or security boundary. */
export type AttributeAudience = "basic" | "expert";

export type WidgetKey =
  | "risk_matrix_rpz"
  | "markdown_tab_group"
  | "steps_editor"
  | "tag_input";

export interface AttributeOption {
  value: string;
  label_de: string;
  label_en: string;
}

export interface LocalizedText {
  de: string;
  en: string;
}

export interface AttributeValidationRules {
  regex?: string;
  min?: number;
  max?: number;
  length?: number;
}

/** One entry of `definition_json.attributes[]` — the published contract. */
export interface AttributeSpec {
  name: string;
  kind: AttributeKind;
  type: AttributeType;
  widget_key: WidgetKey | null;
  fields: string[];
  options: AttributeOption[];
  required: boolean;
  visible: boolean;
  locked: boolean;
  editable: AttributeEditable;
  section: string;
  order: number;
  label: LocalizedText;
  help_text: LocalizedText;
  default: unknown;
  validation: AttributeValidationRules;
  ai_elicit: boolean;
  export: boolean;
  audience: AttributeAudience;
}

/** Where an attribute in a resolved (workspace-scoped) definition comes from
 * — Task 4's "Herkunft" table column. `"global_customized"` marks EVERY
 * inherited attribute once the workspace has any local edit at all
 * (`is_customized` is per-definition, not per-attribute — see the backend's
 * `AttributeDefinitionService._workspace_payload` docstring). */
export type AttributeOrigin = "global" | "global_customized" | "workspace_only";

export interface ResolvedAttributeDefinition {
  item_type: AttributeItemType;
  preset: WorkspacePreset;
  is_customized: boolean;
  version: number;
  attributes: AttributeSpec[];
  /** `attribute.name` -> its origin. Present on every resolved (workspace-
   * scoped) definition; absent on the global-scope payload, which has no
   * origin concept. */
  origins: Record<string, AttributeOrigin>;
}

/** What `AttributeCreateDialog` collects — always creates a `kind: "extended"`
 * entry (only the bootstrap command may create `kind: "core"`). */
export interface NewAttributeInput {
  name: string;
  type: AttributeType;
  required: boolean;
  section: string;
  options?: AttributeOption[];
}

export interface GlobalAttributeDefinition {
  item_type: AttributeItemType;
  preset: WorkspacePreset;
  initialized: boolean;
  version: number;
  attributes: AttributeSpec[];
  /** Present on a PUT response: how many on-default workspaces were updated. */
  propagated_workspace_count?: number;
}

function globalPath(itemType: AttributeItemType, preset: WorkspacePreset): string {
  return `/attribute-defaults/${encodeURIComponent(itemType)}/${encodeURIComponent(
    preset
  )}/`;
}

function workspacePath(workspaceId: UUID, itemType: AttributeItemType): string {
  return `/workspaces/${workspaceId}/attribute-definitions/${encodeURIComponent(
    itemType
  )}/`;
}

function createPayload(input: NewAttributeInput): Record<string, unknown> {
  return {
    name: input.name,
    kind: "extended",
    type: input.type,
    required: input.required,
    section: input.section,
    ...(input.options ? { options: input.options } : {}),
  };
}

export const attributeDefinitionsApi = {
  async listGlobal(filters?: {
    itemType?: AttributeItemType;
    preset?: WorkspacePreset;
  }): Promise<GlobalAttributeDefinition[]> {
    const query = new URLSearchParams();
    if (filters?.itemType) query.set("item_type", filters.itemType);
    if (filters?.preset) query.set("preset", filters.preset);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    const raw = await apiClient.get<{ definitions: GlobalAttributeDefinition[] }>(
      `/attribute-defaults/${suffix}`
    );
    return raw.definitions;
  },

  /** Never 404s: an unseeded type returns `initialized: false` with no attributes. */
  getGlobal(
    itemType: AttributeItemType,
    preset: WorkspacePreset
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.get<GlobalAttributeDefinition>(globalPath(itemType, preset));
  },

  putGlobal(
    itemType: AttributeItemType,
    preset: WorkspacePreset,
    attributes: AttributeSpec[]
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.put<GlobalAttributeDefinition>(globalPath(itemType, preset), {
      attributes,
    });
  },

  getWorkspace(
    workspaceId: UUID,
    itemType: AttributeItemType
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.get<ResolvedAttributeDefinition>(
      workspacePath(workspaceId, itemType)
    );
  },

  putWorkspace(
    workspaceId: UUID,
    itemType: AttributeItemType,
    attributes: AttributeSpec[]
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.put<ResolvedAttributeDefinition>(
      workspacePath(workspaceId, itemType),
      { attributes }
    );
  },

  resetWorkspace(
    workspaceId: UUID,
    itemType: AttributeItemType
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.post<ResolvedAttributeDefinition>(
      `${workspacePath(workspaceId, itemType)}reset/`,
      {}
    );
  },

  createGlobalAttribute(
    itemType: AttributeItemType,
    preset: WorkspacePreset,
    input: NewAttributeInput
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.post<GlobalAttributeDefinition>(
      globalPath(itemType, preset),
      createPayload(input)
    );
  },

  deleteGlobalAttribute(
    itemType: AttributeItemType,
    preset: WorkspacePreset,
    name: string
  ): Promise<GlobalAttributeDefinition> {
    return apiClient.delete<GlobalAttributeDefinition>(
      `${globalPath(itemType, preset)}?name=${encodeURIComponent(name)}`
    );
  },

  createWorkspaceAttribute(
    workspaceId: UUID,
    itemType: AttributeItemType,
    input: NewAttributeInput
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.post<ResolvedAttributeDefinition>(
      workspacePath(workspaceId, itemType),
      createPayload(input)
    );
  },

  deleteWorkspaceAttribute(
    workspaceId: UUID,
    itemType: AttributeItemType,
    name: string
  ): Promise<ResolvedAttributeDefinition> {
    return apiClient.delete<ResolvedAttributeDefinition>(
      `${workspacePath(workspaceId, itemType)}?name=${encodeURIComponent(name)}`
    );
  },
};
