/**
 * ARCH-L1-001 ReactFrontend — LinkTypeCatalog API.
 *
 * Wraps the tenant-wide `/link-type-defaults/` and workspace-scoped
 * `/workspaces/<id>/link-type-definitions/` endpoints.
 *
 * This module replaces the hardcoded 14-member `LinkType` union in
 * `types/index.ts` and the hardcoded `LINK_TYPE_TRI_LABELS` table in
 * `constants/traceLinkLabels.ts` as the source of truth for which link types
 * exist. Those two were maintained independently of the backend enum and had
 * already drifted (`diagram-ref` was missing from both) — audit finding B4.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** One perspective triple of a link-type label. */
export interface TriLabel {
  downstream: string;
  upstream: string;
  neutral: string;
}

/** An allowed endpoint combination. `"*"` is a wildcard on either side. */
export interface LinkTypePair {
  source_type: string;
  target_type: string;
}

/** The four propagation behaviours the backend engine can dispatch on. */
export type SuspectRule =
  | "none"
  | "target_change_flags_source"
  | "source_change_flags_target"
  | "parent_change_flags_children";

/** `definition_json` as validated by `link_types.schema`. */
export interface LinkTypeDefinition {
  label: { de: TriLabel; en: TriLabel };
  allowed_pairs: LinkTypePair[];
  coverage_relevant: boolean;
  suspect_rule: SuspectRule;
  impact_weight: number;
  manual_creatable: boolean;
  system_owned: boolean;
  active: boolean;
  built_in: boolean;
}

/** A materialized per-workspace row. */
export interface WorkspaceLinkType {
  id: UUID;
  workspace_id: UUID;
  key: string;
  definition: LinkTypeDefinition;
  is_customized: boolean;
  source_global_id: UUID | null;
  version: number;
}

/** A tenant-wide template. */
export interface GlobalLinkType {
  id: UUID;
  key: string;
  definition: LinkTypeDefinition;
  version: number;
  /** Present only on an update response. */
  propagated_to?: number;
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

export const linkTypesApi = {
  /** Resolved catalog of a workspace, inactive rows included. */
  async listForWorkspace(workspaceId: UUID): Promise<WorkspaceLinkType[]> {
    const raw = await apiClient.get<WorkspaceLinkType[]>(
      `/workspaces/${workspaceId}/link-type-definitions/`,
    );
    return asArray<WorkspaceLinkType>(raw);
  },

  /** Override one link type for one workspace (sets `is_customized`). */
  async updateForWorkspace(
    workspaceId: UUID,
    key: string,
    definition: LinkTypeDefinition,
  ): Promise<WorkspaceLinkType> {
    return apiClient.put<WorkspaceLinkType>(
      `/workspaces/${workspaceId}/link-type-definitions/${key}/`,
      { definition },
    );
  },

  /** Restore a workspace override to its default. */
  async resetForWorkspace(workspaceId: UUID, key: string): Promise<WorkspaceLinkType> {
    return apiClient.post<WorkspaceLinkType>(
      `/workspaces/${workspaceId}/link-type-definitions/${key}/reset/`,
      {},
    );
  },

  /** Tenant-wide templates. */
  async listGlobal(): Promise<GlobalLinkType[]> {
    const raw = await apiClient.get<GlobalLinkType[]>("/link-type-defaults/");
    return asArray<GlobalLinkType>(raw);
  },

  async createGlobal(key: string, definition: LinkTypeDefinition): Promise<GlobalLinkType> {
    return apiClient.post<GlobalLinkType>("/link-type-defaults/", { key, definition });
  },

  async updateGlobal(key: string, definition: LinkTypeDefinition): Promise<GlobalLinkType> {
    return apiClient.put<GlobalLinkType>(`/link-type-defaults/${key}/`, { definition });
  },

  async deleteGlobal(key: string): Promise<void> {
    await apiClient.delete<void>(`/link-type-defaults/${key}/`);
  },
};
