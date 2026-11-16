/**
 * ARCH-L1-001 ReactFrontend — Tabellenansicht API wrapper
 * (plan 2026-11-04-tabellenansicht-s4, Task 4.1).
 *
 * Wraps the slice-1/2/3 endpoints the `ArtifactTable` builds on:
 *   GET   /api/v1/artifacts/table/
 *   PATCH /api/v1/artifacts/bulk-update/
 *   POST  /api/v1/artifacts/bulk-transition/
 *   GET|POST /api/v1/saved-views/
 *   GET|PATCH|DELETE /api/v1/saved-views/{id}/
 *   GET   /api/v1/saved-views/{id}/apply/
 *   GET|PUT /api/v1/users/me/table-view-state/
 *
 * Design notes:
 * - `bulkUpdate` resolves on a 200 *and* on the 400/409 all-or-nothing
 *   failure body (`committed: false` + `failed[]`), because the surface must
 *   render the per-artifact failure list instead of a thrown error. Any other
 *   non-2xx still throws through the shared client.
 * - `savedViewsApi`/`tableViewStateApi` are against contracts that may not be
 *   deployed yet (slice 3 is a separate PR). Callers therefore treat a 404 as
 *   "feature absent" and degrade to an empty/local state — the wrapper itself
 *   keeps the plain client error semantics.
 */

import { apiClient, getList } from "./client";
import type { PaginatedResponse, UUID } from "../types";

// ---------------------------------------------------------------------------
// Wire types (spec §4.1)
// ---------------------------------------------------------------------------

export type FilterOperator = "contains" | "in" | "gte" | "lte" | "eq";

export interface FilterConstraint {
  op: FilterOperator;
  value: unknown;
}

/** `{field: constraint | constraint[]}` — a list is ANDed. */
export type TableFilters = Record<string, FilterConstraint | FilterConstraint[]>;

export interface SortTerm {
  field: string;
  dir: "asc" | "desc";
}

export interface TableRow {
  /** Entity id (domain object), not the backing artifact id. */
  id: string;
  /** Backing `pl_artifact` id — the write target for bulk requests. */
  artifact_id: string;
  item_type: string;
  version: number;
  values: Record<string, unknown>;
  locked: { state: string } | null;
}

export interface BulkItem {
  artifact_id: string;
  expected_version: number;
  fields: Record<string, unknown>;
}

export type BulkFailureCode =
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "FORBIDDEN"
  | "CONFLICT";

export interface BulkFailure {
  index: number;
  artifact_id: string | null;
  code: BulkFailureCode;
  reason: string;
}

export interface BulkUpdatedEntry {
  artifact_id: string;
  id: string;
  item_type: string;
  version: number;
}

export interface BulkUpdateResult {
  committed: boolean;
  mode: string;
  updated: BulkUpdatedEntry[];
  failed: BulkFailure[];
}

export interface BulkUpdateBody {
  /** Defaults to `"atomic"` on the server; declared here for the UI switch. */
  mode?: "atomic" | "partial";
  change_reason?: string;
  items: BulkItem[];
}

export interface BulkTransitionBody {
  item_type: string;
  ids: string[];
  to_state: string;
  change_reason: string;
}

export interface BulkTransitionResult {
  transitioned: string[];
  failed: BulkFailure[];
}

export interface TableViewState {
  columns: { field: string; order: number }[];
  filters: TableFilters;
  sort: SortTerm[];
}

export type SavedViewVisibility = "private" | "workspace";

export interface SavedView {
  id: string;
  workspace_id: string;
  item_type: string;
  owner_id: string;
  name: string;
  visibility: SavedViewVisibility;
  version: number;
  columns: { field: string; order: number }[];
  filters: TableFilters;
  sort: SortTerm[];
}

export interface SavedViewCreateInput {
  name: string;
  visibility?: SavedViewVisibility;
  columns: TableViewState["columns"];
  filters: TableFilters;
  sort: SortTerm[];
}

export interface SavedViewApplyResult extends PaginatedResponse<TableRow> {
  warnings?: string[];
}

export interface TableQueryParams {
  workspace_id: UUID;
  item_type: string;
  filters?: TableFilters;
  sort?: SortTerm[];
  page?: number;
  page_size?: number;
  include_deleted?: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Serialise the JSON-valued query parameters exactly as the DSL expects. */
function tableParams(params: TableQueryParams): Record<string, string> {
  const out: Record<string, string> = {
    workspace_id: params.workspace_id,
    item_type: params.item_type,
  };
  if (params.filters) out.filters = JSON.stringify(params.filters);
  if (params.sort) out.sort = JSON.stringify(params.sort);
  if (params.page !== undefined) out.page = String(params.page);
  if (params.page_size !== undefined) out.page_size = String(params.page_size);
  if (params.include_deleted !== undefined) {
    out.include_deleted = params.include_deleted ? "true" : "false";
  }
  return out;
}

/** Read the failure body of a rejected atomic/partial request, if it is one. */
function failureBody(error: unknown): BulkUpdateResult | null {
  const body = error as Partial<BulkUpdateResult> | null | undefined;
  if (!body || typeof body !== "object") return null;
  if (body.committed !== false || !Array.isArray(body.failed)) return null;
  return {
    committed: false,
    mode: typeof body.mode === "string" ? body.mode : "atomic",
    updated: Array.isArray(body.updated) ? body.updated : [],
    failed: body.failed,
  };
}

/** A slice-3 endpoint that is not deployed yet answers 404; list callers
 * degrade to an empty view instead of surfacing a hard error. */
export async function listOrEmpty<T>(fn: () => Promise<T[]>): Promise<T[]> {
  try {
    return await fn();
  } catch (error) {
    const code = (error as { error?: { code?: string } } | null)?.error?.code;
    if (code === "NOT_FOUND") return [];
    throw error;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** `GET /saved-views/` may answer a paginated or a bare list; normalise both. */
async function listSavedViews(
  workspaceId: UUID,
  itemType: string
): Promise<SavedView[]> {
  const response = await apiClient.get<
    PaginatedResponse<SavedView> | SavedView[]
  >(
    `/saved-views/?${new URLSearchParams({
      workspace_id: workspaceId,
      item_type: itemType,
    }).toString()}`
  );
  if (Array.isArray(response)) return response;
  return response.results;
}

// ---------------------------------------------------------------------------
// Table
// ---------------------------------------------------------------------------

export const tableApi = {
  query(params: TableQueryParams): Promise<PaginatedResponse<TableRow>> {
    return getList<TableRow>("/artifacts/table/", tableParams(params));
  },

  /**
   * `PATCH /artifacts/bulk-update/` — all-or-nothing or per-item.
   *
   * A 400/409 all-or-nothing failure is a *result*, not an exception: the
   * server answers with `committed: false` and the per-item `failed` list, so
   * the surface can show exactly which rows were rejected. Both are resolved
   * here; anything else (403, network, malformed 400) throws.
   */
  async bulkUpdate(body: BulkUpdateBody): Promise<BulkUpdateResult> {
    const payload = { ...body, mode: body.mode ?? "atomic" };
    try {
      return await apiClient.patch<BulkUpdateResult>(
        "/artifacts/bulk-update/",
        payload
      );
    } catch (error) {
      const failure = failureBody(error);
      if (failure) return failure;
      throw error;
    }
  },

  bulkTransition(body: BulkTransitionBody): Promise<BulkTransitionResult> {
    return apiClient.post<BulkTransitionResult>(
      "/artifacts/bulk-transition/",
      body
    );
  },
};

// ---------------------------------------------------------------------------
// Saved views
// ---------------------------------------------------------------------------

export const savedViewsApi = {
  list(workspaceId: UUID, itemType: string): Promise<SavedView[]> {
    return listSavedViews(workspaceId, itemType);
  },

  get(id: string): Promise<SavedView> {
    return apiClient.get<SavedView>(`/saved-views/${id}/`);
  },

  create(
    workspaceId: UUID,
    itemType: string,
    input: SavedViewCreateInput
  ): Promise<SavedView> {
    return apiClient.post<SavedView>("/saved-views/", {
      workspace_id: workspaceId,
      item_type: itemType,
      ...input,
    });
  },

  update(
    id: string,
    input: Partial<SavedViewCreateInput> & { expected_version?: number }
  ): Promise<SavedView> {
    return apiClient.patch<SavedView>(`/saved-views/${id}/`, input);
  },

  remove(id: string): Promise<void> {
    return apiClient.delete(`/saved-views/${id}/`);
  },

  apply(
    id: string,
    params: { workspace_id: UUID; page?: number; page_size?: number } = {
      workspace_id: "",
    }
  ): Promise<SavedViewApplyResult> {
    const query: Record<string, string> = {
      workspace_id: params.workspace_id,
    };
    if (params.page !== undefined) query.page = String(params.page);
    if (params.page_size !== undefined) query.page_size = String(params.page_size);
    return apiClient.get<SavedViewApplyResult>(
      `/saved-views/${id}/apply/?${new URLSearchParams(query).toString()}`
    );
  },
};

// ---------------------------------------------------------------------------
// Per-user table state
// ---------------------------------------------------------------------------

export const tableViewStateApi = {
  async get(workspaceId: UUID, itemType: string): Promise<TableViewState> {
    const response = await apiClient.get<Partial<TableViewState>>(
      `/users/me/table-view-state/?${new URLSearchParams({
        workspace_id: workspaceId,
        item_type: itemType,
      }).toString()}`
    );
    return {
      columns: Array.isArray(response?.columns) ? response.columns : [],
      filters: isRecord(response?.filters) ? response.filters : {},
      sort: Array.isArray(response?.sort) ? response.sort : [],
    };
  },

  put(
    workspaceId: UUID,
    itemType: string,
    state: TableViewState
  ): Promise<TableViewState> {
    return apiClient.put<TableViewState>(
      `/users/me/table-view-state/?${new URLSearchParams({
        workspace_id: workspaceId,
        item_type: itemType,
      }).toString()}`,
      state
    );
  },
};

export const EMPTY_TABLE_VIEW_STATE: TableViewState = {
  columns: [],
  filters: {},
  sort: [],
};
