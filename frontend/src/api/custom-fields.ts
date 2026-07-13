/**
 * ARCH-L1-001 ReactFrontend — Custom Fields API (REQ-016).
 *
 * Wraps the workspace-wide custom field definition endpoints and the
 * per-artifact value endpoints:
 *   - /api/v1/workspaces/<id>/custom-field-definitions/  (list, create)
 *   - /api/v1/custom-field-definitions/<id>/             (patch, delete)
 *   - /api/v1/artifacts/<id>/custom-field-values/        (get, put)
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export const CUSTOM_FIELD_TYPES = ["text", "number", "dropdown"] as const;
export type CustomFieldType = (typeof CUSTOM_FIELD_TYPES)[number];

export interface CustomFieldDefinition {
  id: UUID;
  workspace_id: UUID;
  name: string;
  field_type: CustomFieldType;
  is_required: boolean;
  options: string[];
  order: number;
}

/** A definition merged with the current value for one artifact instance. */
export interface CustomFieldValueRow {
  id: UUID | null;
  definition_id: UUID;
  artifact_id: UUID;
  value: string;
  name: string;
  field_type: CustomFieldType;
  is_required: boolean;
  options: string[];
  order: number;
}

export interface CustomFieldDefinitionInput {
  name: string;
  field_type: CustomFieldType;
  is_required: boolean;
  options?: string[];
  order?: number;
}

export interface CustomFieldValueInput {
  definition_id: UUID;
  value: string;
}

export const customFieldsApi = {
  /** List workspace-wide custom field definitions. */
  listDefinitions(workspaceId: UUID): Promise<CustomFieldDefinition[]> {
    return apiClient.get<CustomFieldDefinition[]>(
      `/workspaces/${workspaceId}/custom-field-definitions/`
    );
  },

  /** Create a new definition in a workspace (admin only). */
  createDefinition(
    workspaceId: UUID,
    data: CustomFieldDefinitionInput
  ): Promise<CustomFieldDefinition> {
    return apiClient.post<CustomFieldDefinition>(
      `/workspaces/${workspaceId}/custom-field-definitions/`,
      data
    );
  },

  /** Update an existing definition (admin only). */
  updateDefinition(
    id: UUID,
    data: Partial<CustomFieldDefinitionInput>
  ): Promise<CustomFieldDefinition> {
    return apiClient.patch<CustomFieldDefinition>(
      `/custom-field-definitions/${id}/`,
      data
    );
  },

  /** Delete a definition and all its values (admin only). */
  deleteDefinition(id: UUID): Promise<void> {
    return apiClient.delete(`/custom-field-definitions/${id}/`);
  },

  /** Read the definitions + current values for one artifact. */
  getValues(artifactId: UUID): Promise<CustomFieldValueRow[]> {
    return apiClient.get<CustomFieldValueRow[]>(
      `/artifacts/${artifactId}/custom-field-values/`
    );
  },

  /** Upsert values for one artifact. Empty values clear the stored entry. */
  putValues(
    artifactId: UUID,
    values: CustomFieldValueInput[]
  ): Promise<CustomFieldValueRow[]> {
    return apiClient.put<CustomFieldValueRow[]>(
      `/artifacts/${artifactId}/custom-field-values/`,
      values
    );
  },
};
