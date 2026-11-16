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
 * - The bulk endpoints are spoken exactly as the merged backend declares them
 *   (`rest_api.serializers.BulkUpdateRequestSerializer` /
 *   `BulkTransitionRequestSerializer`): `{workspace_id, entries}` on update,
 *   `{item_type, ids, to_state, change_reason}` on transition. The result is
 *   normalised into this module's UI shape (`committed`/`updated`/`failed`),
 *   never the other way round.
 * - `bulkUpdate` resolves on a 200 *and* on the 409 all-or-nothing refusal
 *   (`committed: false` + `failed[]`), because the surface must render the
 *   per-artifact failure list instead of a thrown error. 400 (malformed body)
 *   and 403 (no write role) keep throwing through the shared client.
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

export interface BulkUpdateEntry {
  /** Backing `pl_artifact` id — same id the table row reports. */
  artifact_id: string;
  /** The version the row carried when it was rendered. */
  expected_version: number;
  /** Service fields to write, e.g. `{title, body, change_reason}`. */
  fields: Record<string, unknown>;
}

/** One refused entry of `BulkUpdateResponseSerializer.errors`. */
export interface BulkFailure {
  /** Zero-based position in the request's `entries` list. */
  index: number;
  artifact_id: string | null;
  /** `NOT_FOUND | CONFLICT | FIELD_FROZEN | WORKFLOW_FROZEN | …` */
  code: string;
  message: string;
  /** Offending field when the refusal names one (used to mark the cell). */
  field?: string | null;
}

/** One written entry of `BulkUpdateResponseSerializer.updated`. */
export interface BulkUpdatedEntry {
  artifact_id: string;
  /** Version after the write (the value to send next time). */
  version: number;
}

/** UI-facing outcome: `committed: false` means nothing was written. */
export interface BulkUpdateResult {
  committed: boolean;
  updated: BulkUpdatedEntry[];
  failed: BulkFailure[];
}

/** Body of `PATCH /artifacts/bulk-update/` (`BulkUpdateRequestSerializer`). */
export interface BulkUpdateBody {
  /** Every entry must belong to this workspace. */
  workspace_id: UUID;
  /** 1..100 writes, applied all-or-nothing. */
  entries: BulkUpdateEntry[];
}

/** Body of `POST /artifacts/bulk-transition/` (no `workspace_id` by contract). */
export interface BulkTransitionBody {
  item_type: string;
  ids: string[];
  to_state: string;
  change_reason: string;
}

/** One moved entry of `BulkTransitionResponseSerializer.transitioned`. */
export interface BulkTransitionedEntry {
  artifact_id: string;
  state: string;
}

/** UI-facing outcome; partial success is the contract, so failures keep 200. */
export interface BulkTransitionResult {
  transitioned: BulkTransitionedEntry[];
  failed: BulkFailure[];
}

/** Raw body shared by the 200 and the 409 answer of bulk-update. */
interface BulkUpdateResponseBody {
  updated: BulkUpdatedEntry[];
  errors: BulkFailure[];
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

/**
 * Read the 409 refusal body of a bulk-update, if the thrown value is one.
 *
 * The contract answers a refused batch with `{updated: [], errors: [...]}` and
 * status 409; the shared client throws the parsed body. A 400 request defect
 * arrives as the house error envelope (`{error: {code, message, details}}`)
 * instead and must keep throwing — hence the explicit `error`-key exclusion.
 */
function refusedBatchBody(error: unknown): BulkUpdateResponseBody | null {
  if (!isRecord(error) || "error" in error) return null;
  if (!Array.isArray(error.errors)) return null;
  return {
    updated: Array.isArray(error.updated)
      ? (error.updated as BulkUpdatedEntry[])
      : [],
    errors: error.errors as BulkFailure[],
  };
}

/** `{updated, errors}` → the UI result; `committed` only when nothing failed. */
function toBulkUpdateResult(body: BulkUpdateResponseBody | null): BulkUpdateResult {
  const updated = Array.isArray(body?.updated) ? body.updated : [];
  const failed = Array.isArray(body?.errors) ? body.errors : [];
  return { committed: failed.length === 0, updated, failed };
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
   * `PATCH /artifacts/bulk-update/` — all-or-nothing batch write.
   *
   * A 409 refusal is a *result*, not an exception: the server answers with
   * `updated: []` and the per-entry `errors` list, so the surface can mark the
   * offending rows instead of re-reading the page. It is mapped here to
   * `committed: false` + `failed`. 400 (malformed body, empty/oversized
   * `entries`) and 403 (no write role) keep throwing.
   */
  async bulkUpdate(body: BulkUpdateBody): Promise<BulkUpdateResult> {
    try {
      const response = await apiClient.patch<BulkUpdateResponseBody>(
        "/artifacts/bulk-update/",
        { workspace_id: body.workspace_id, entries: body.entries }
      );
      return toBulkUpdateResult(response);
    } catch (error) {
      const refused = refusedBatchBody(error);
      if (refused) return toBulkUpdateResult(refused);
      throw error;
    }
  },

  /**
   * `POST /artifacts/bulk-transition/` — one target state for the selection.
   *
   * The workspace is **not** sent: the backend derives it from the ids (so a
   * caller cannot scope the role check differently from the write). Partial
   * success is the contract, so a 200 can carry both `transitioned` and
   * `failed`; 400/403 still throw.
   */
  async bulkTransition(body: BulkTransitionBody): Promise<BulkTransitionResult> {
    const response = await apiClient.post<BulkTransitionResult>(
      "/artifacts/bulk-transition/",
      {
        item_type: body.item_type,
        ids: body.ids,
        to_state: body.to_state,
        change_reason: body.change_reason,
      }
    );
    return {
      transitioned: Array.isArray(response?.transitioned)
        ? response.transitioned
        : [],
      failed: Array.isArray(response?.failed) ? response.failed : [],
    };
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
