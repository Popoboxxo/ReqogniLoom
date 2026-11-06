/**
 * ARCH-L1-001 ReactFrontend — Allocation-view API (P3, V10/B9).
 *
 * Wraps the read object that feeds the connection-view renderers plus the two
 * write paths it needs:
 *
 *   GET    /api/v1/workspaces/{id}/allocation-view/   flat rows + meta
 *   GET    /api/v1/workspaces/{id}/tiers/             tier labels
 *   POST   /api/v1/trace-links/bulk/                  atomic allocate/re-allocate
 *   DELETE /api/v1/trace-links/{id}/                  deallocate
 *
 * Row ids are domain-entity ids: `row.id` is the Requirement / ArchitectureElement
 * id the bulk endpoint expects (`requirement_id` / `element_id`), while
 * `row.artifact_id` is the backing Artifact id (never sent back as an entity id).
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** Whether a row is a requirement or an architecture element. */
export type AllocationRowKind = "requirement" | "element";

/** Non-null while the requirement's workflow state freezes it (P4). */
export interface AllocationLock {
  state?: string;
}

/** One flat row of the allocation view. */
export interface AllocationRow {
  kind: AllocationRowKind;
  /** Domain-entity id (Requirement / ArchitectureElement id). */
  id: UUID;
  /** Backing Artifact id. */
  artifact_id: UUID;
  /** Parent element id for `kind: "element"`; artifact parent for requirements. */
  parent_id: string | null;
  sort_key: string | null;
  title: string;
  state: string | null;
  tier_key: string | null;
  tier_name: string | null;
  level: number | null;
  type: string | null;
  category: string | null;
  /**
   * Element **Artifact** id the requirement is allocated to (N:1) — the
   * `TraceLink.target` value, matching `buildGraph`'s edge lookup.
   */
  allocated_to: string | null;
  /** Id of the `allocated-to` TraceLink (needed to deallocate). */
  allocation_trace_link_id: string | null;
  /** Element entity id (the `ArchitectureElement.id`), when resolved. */
  element_id: string | null;
  allocation_intent: string | null;
  locked: AllocationLock | null;
  findings: unknown[];
  group: string | null;
  /**
   * P5 card field "owner". The read object does not guarantee the field yet
   * (the committed row contract predates the card graph), so it is optional
   * and the card falls back to "—".
   */
  owner?: string | { name?: string; id?: string } | null;
  /** Local readable id when the backend supplies one (card field "ID"). */
  uid?: string | null;
}

/** Counters computed over the filtered set (not over the current page). */
export interface AllocationMeta {
  total: number;
  unallocated: number;
  locked: number;
  findings: number;
  page_size: number;
  offset: number;
}

export interface AllocationViewResponse {
  results: AllocationRow[];
  meta: AllocationMeta;
}

/** Query parameters the backend accepts. */
export interface AllocationViewQuery {
  allocated?: boolean;
  intent?: string;
  tier?: string;
  type?: string;
  category?: string;
  state?: string;
  element_subtree?: string;
  q?: string;
  open?: boolean;
  page_size?: number;
  offset?: number;
}

export interface BulkAllocationItem {
  requirement_id: string;
  element_id: string;
}

export interface BulkAllocationResult {
  allocated: Array<{
    requirement_id: string;
    element_id: string;
    trace_link_id: string;
  }>;
}

/** One tier of the workspace ladder (labels + position). */
export interface WorkspaceTier {
  tier_key: string;
  name: Record<string, string>;
  position: number;
  rule: string;
  from_end: number | null;
  level: number;
}

export interface WorkspaceTiersResponse {
  workspace_id: string;
  tiers: WorkspaceTier[];
}

function toSearchParams(query: AllocationViewQuery): string {
  const params = new URLSearchParams();
  if (query.allocated !== undefined) params.set("allocated", String(query.allocated));
  if (query.intent) params.set("intent", query.intent);
  if (query.tier) params.set("tier", query.tier);
  if (query.type) params.set("type", query.type);
  if (query.category) params.set("category", query.category);
  if (query.state) params.set("state", query.state);
  if (query.element_subtree) params.set("element_subtree", query.element_subtree);
  if (query.q) params.set("q", query.q);
  if (query.open !== undefined) params.set("open", String(query.open));
  if (query.page_size !== undefined) params.set("page_size", String(query.page_size));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

export const allocationViewApi = {
  /** GET the flat allocation view for a workspace. */
  view(
    workspaceId: UUID,
    query: AllocationViewQuery = {}
  ): Promise<AllocationViewResponse> {
    return apiClient.get<AllocationViewResponse>(
      `/workspaces/${workspaceId}/allocation-view/${toSearchParams(query)}`
    );
  },

  /** GET the workspace tier ladder (labels for the tier filter). */
  tiers(workspaceId: UUID): Promise<WorkspaceTiersResponse> {
    return apiClient.get<WorkspaceTiersResponse>(
      `/workspaces/${workspaceId}/tiers/`
    );
  },

  /**
   * POST an atomic allocation batch. Used for both allocate and re-allocate:
   * the backend replaces the existing `allocated-to` edge in one transaction
   * and rolls the whole batch back if any item fails.
   */
  bulkAllocate(items: BulkAllocationItem[]): Promise<BulkAllocationResult> {
    return apiClient.post<BulkAllocationResult>("/trace-links/bulk/", { items });
  },

  /** DELETE one `allocated-to` TraceLink (deallocate). */
  deallocate(traceLinkId: string): Promise<void> {
    return apiClient.delete<void>(`/trace-links/${traceLinkId}/`);
  },
};
