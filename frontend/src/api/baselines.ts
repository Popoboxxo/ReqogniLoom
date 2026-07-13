/**
 * ARCH-L1-001 ReactFrontend — Baselines API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L1-018 (Baselines), REQ-L2-RF-007 (Preset-gated visibility)
 *          REQ-L1-049 (Baseline scope-select with 3 scopes)
 *
 * Wraps /api/v1/baselines/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { PaginatedResponse, UUID, ISODateTime } from "../types";

export type BaselineScope = "document" | "project" | "global";

/**
 * REQ-L2-BL-012: full field-level snapshot of a captured entity at baseline
 * creation time. Keys depend on ``artifact_type`` (requirement,
 * architecture_element, stakeholder_need, test_case, trace_link,
 * glossary_term, …). ``null`` for legacy entries created before the feature.
 */
export type BaselineEntryState = Record<string, unknown> | null;

/**
 * REQ-L2-BL-012: one captured item within a baseline. Present only on the
 * detail response (GET /baselines/{id}/), not on the list response.
 */
export interface BaselineDeltaEntry {
  item_id: string;
  version: number;
  entity_type: string;
  state: BaselineEntryState;
}

export interface Baseline {
  id: UUID;
  workspace_id: UUID;
  name: string;
  scope: string;
  description: string;
  artifact_id: UUID | null;
  version: number;
  created_at: ISODateTime;
  /** REQ-L2-BL-012: captured items — only on the detail response. */
  entries?: BaselineDeltaEntry[];
}

export interface ScopePreviewItem {
  id: string;
  title: string;
  type: string;
  entity_type?: string;
}

export interface ScopePreview {
  scope: BaselineScope | string;
  count: number;
  sample: ScopePreviewItem[];
}

/**
 * REQ-L2-BL-012: one field-level change of a captured entity between two
 * baselines. ``old_value`` / ``new_value`` are arbitrary JSON values.
 */
export interface FieldChange {
  field_name: string;
  old_value: unknown;
  new_value: unknown;
}

/**
 * REQ-L2-BL-003: one item in a baseline diff. ``status`` is added/removed/
 * changed. ``field_changes`` is present only for changed items that carry a
 * full-state snapshot on both baselines; ``null`` otherwise.
 */
export interface DiffItem {
  item_id: string;
  entity_type: string;
  status: "added" | "removed" | "changed";
  field_changes: FieldChange[] | null;
  /** REQ-006: human-readable artifact title, null when unresolved (e.g. non-artifact entity types). */
  artifact_name?: string | null;
}

/** REQ-L2-BL-003: field-level structural diff between two baselines. */
export interface BaselineDiff {
  baseline_a_id: UUID;
  baseline_b_id: UUID;
  summary: {
    added: number;
    removed: number;
    changed: number;
  };
  items: DiffItem[];
}

/**
 * REQ-L2-BL-003: compare two baselines of the same scope and return the
 * field-level diff. Wraps GET /api/v1/baselines/diff/.
 */
export async function compareBaselines(
  baselineAId: UUID,
  baselineBId: UUID
): Promise<BaselineDiff> {
  const query = new URLSearchParams({
    baseline_a: baselineAId,
    baseline_b: baselineBId,
  });
  return apiClient.get<BaselineDiff>(`/baselines/diff/?${query.toString()}`);
}

export const baselinesApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<Baseline>> {
    return getList<Baseline>("/baselines/", {
      workspace_id: workspaceId,
    });
  },

  get(id: UUID): Promise<Baseline> {
    return apiClient.get<Baseline>(`/baselines/${id}/`);
  },

  create(data: {
    workspace_id: UUID;
    /** Optional — the backend generates a timestamp-based default. */
    name?: string;
    scope?: string;
    description?: string;
    artifact_id?: UUID | null;
  }): Promise<Baseline> {
    return apiClient.post<Baseline>("/baselines/", data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/baselines/${id}/`);
  },

  /** REQ-L2-BL-003: field-level diff between two baselines of the same scope. */
  compare(baselineAId: UUID, baselineBId: UUID): Promise<BaselineDiff> {
    return compareBaselines(baselineAId, baselineBId);
  },

  /**
   * REQ-L1-049: read-only preview of items a Baseline of the given scope
   * would include. Returns count + sample (max 10 items, each with
   * id/title/type).
   *
   * - scope="global" requires an admin/staff caller; the API returns 403
   *   otherwise.
   * - scope="document" requires ``artifactId``; the API returns 400 if it
   *   is missing.
   */
  previewScope(params: {
    scope: BaselineScope | string;
    workspaceId: UUID;
    artifactId?: UUID | null;
  }): Promise<ScopePreview> {
    const query: Record<string, string> = {
      scope: String(params.scope),
      workspace_id: String(params.workspaceId),
    };
    if (params.artifactId) {
      query.artifact_id = String(params.artifactId);
    }
    const qs = new URLSearchParams(query).toString();
    return apiClient.get<ScopePreview>(
      `/baselines/scope-preview/${qs ? `?${qs}` : ""}`
    );
  },
};
