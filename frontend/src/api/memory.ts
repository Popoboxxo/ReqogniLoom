/**
 * ARCH-L1-001 ReactFrontend — Unified AI memory API (RFC #1002, PR D).
 *
 * Wraps the full REST surface introduced/unified by RFC #1002 PRs A–C
 * (`backend/memory/memory_rest.py`, wired in `backend/rest_api/urls.py`):
 *
 *   GET|POST /workspaces/{ws}/memory/entries/     list / create (workspace scope)
 *   GET      /workspaces/{ws}/memory/search/      semantic search
 *   GET      /workspaces/{ws}/memory/digest/      consolidated digest (F6)
 *   GET|DELETE /memory/entries/{entry_id}/        detail / forget
 *   POST     /memory/entries/{entry_id}/promote/  user -> workspace promote
 *   GET|POST /artifacts/{artifact_id}/memory/     artifact-scoped list / create
 *   GET      /artifacts/{artifact_id}/memory/digest/  artifact digest (F6)
 *   GET|DELETE /memory/me/                        own user-scoped overview / purge
 *   GET      /system/memory/workspaces/           System-Admin workspace overview
 *   DELETE   /system/memory/workspaces/{ws}/      System-Admin workspace purge
 *   GET      /system/memory/entries/              System-Admin entry list
 *   GET      /system/memory/projection/           System-Admin PCA projection
 *   GET      /system/memory/entries/export/       System-Admin DSGVO export
 *   GET      /admin/health/                       shared health snapshot (memory row)
 *
 * Every entry/list/search response carries the ``backend`` + ``degraded``
 * envelope (RFC #1002 F9), so "the backend is down" is distinguishable from
 * "nothing is remembered" — this client preserves both fields on every type
 * that can carry them.
 *
 * Write path note: the REST surface has no user-scope create endpoint.
 * `POST /workspaces/{ws}/memory/entries/` always writes workspace scope and
 * `POST /artifacts/{id}/memory/` always writes artifact scope (see the two
 * views' `MemoryEntryService().write(...)` calls in `memory_rest.py`); user-
 * scope rows are written by agents/MCP. The UI therefore offers Team and
 * Artefakt in the add-fact dialog.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** The three memory tiers (backend `MemoryEntryService.VALID_SCOPES`). */
export type MemoryScope = "user" | "workspace" | "artifact";

/** Scope vocabulary of the System-Admin visualization surface. */
export type SystemMemoryVizScope = "workspace" | "global";

export type MemoryOwnerType = "workspace" | "user";

/** Canonical view of one consolidated memory entry (`MemoryEntryView`). */
export interface MemoryEntry {
  entry_id: string;
  content: string;
  scope: MemoryScope;
  workspace_id: string | null;
  user_id: string | null;
  artifact_id: string | null;
  entity_type: string;
  contributor_user_id: string | null;
  source_event_id: string | null;
  source_session_id: string | null;
  confidence: number;
  language: string;
  created_at: string | null;
  superseded_by: string | null;
  backend: string;
  degraded: boolean;
}

/** Shared `backend` + `degraded` envelope (RFC #1002 F9). */
export interface MemoryEnvelope {
  backend: string;
  degraded: boolean;
}

export interface MemoryEntryPage extends MemoryEnvelope {
  items: MemoryEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface MemorySearchResult extends MemoryEnvelope {
  items: MemoryEntry[];
  query: string;
  scopes: MemoryScope[];
}

/**
 * Consolidated digest of one memory scope (RFC #1002 F6 / Phase 3).
 *
 * Unlike the entry/search envelopes this is not paginated: the LLM-written
 * `digest` is a single Markdown-ish text block, `generated_at` is its
 * ISO-8601 creation timestamp and `backend` names the provider that produced
 * it (`"honcho"` | `"pgvector"`). An empty `digest` means "nothing summarized
 * yet", which is a normal state, not an error.
 */
export interface MemoryDigest {
  digest: string;
  generated_at: string;
  backend: string;
  degraded: boolean;
}

/** `GET /memory/me/` overview; `entries` only present with `include_entries`. */
export interface MemorySelfOverview extends MemoryEnvelope {
  entry_count: number;
  last_updated_at: string | null;
  entries?: MemoryEntry[];
  total?: number;
  page?: number;
  page_size?: number;
}

/** Structured `memory` component of `GET /admin/health/`. */
export interface MemoryHealth {
  backend: string;
  ok: boolean;
  degraded: boolean;
  detail: string;
  status: string;
}

export interface MemoryListQuery {
  scope?: MemoryScope;
  artifact_id?: UUID;
  contributor_user_id?: UUID;
  q?: string;
  page?: number;
  page_size?: number;
}

export interface MemorySearchQuery {
  q: string;
  scope?: MemoryScope;
  artifact_id?: UUID;
  top_k?: number;
}

/** Create payload for the workspace/artifact write endpoints. */
export interface MemoryWritePayload {
  content: string;
  confidence?: number;
  change_reason?: string;
}

export interface MemoryPromotePayload {
  workspace_id?: UUID;
  target_scope?: "workspace";
  change_reason?: string;
}

export interface MemorySelfOverviewQuery {
  includeEntries?: boolean;
  page?: number;
  pageSize?: number;
}

/** One row of `GET /system/memory/workspaces/` (System-Admin overview). */
export interface WorkspaceMemoryOverviewRow {
  workspace_id: UUID;
  workspace_name: string;
  enabled: boolean;
  workspace_entry_count: number;
  user_entry_count: number;
  by_scope: { workspace: number; user: number; artifact: number };
  contributor_count: number;
  degraded: boolean;
  last_consolidated_at: string | null;
}

export interface WorkspaceMemoryDeleteResult {
  workspace_id: UUID;
  workspace_memory_deleted: number;
  artifact_memory_deleted: number;
  user_memory_deleted: number;
}

export interface MemorySystemEntryRow {
  id: string;
  content: string;
  created_at: string;
  confidence: number;
  owner_type: MemoryOwnerType;
  owner_id: string;
  owner_label: string;
}

export interface MemorySystemEntryPage extends MemoryEnvelope {
  results: MemorySystemEntryRow[];
  count: number;
  page: number;
  page_size: number;
}

export interface MemoryProjectionPoint {
  id: string;
  x: number;
  y: number;
  cluster_id: number;
  owner_type: MemoryOwnerType;
  owner_id: string;
  owner_label: string;
}

export interface MemoryProjection extends MemoryEnvelope {
  points: MemoryProjectionPoint[];
  sampled: boolean;
  sample_size: number;
  total_size: number;
  excluded_no_embedding: number;
}

export interface SystemMemoryEntryQuery {
  scope: SystemMemoryVizScope;
  workspaceId?: UUID;
  page?: number;
  pageSize?: number;
  q?: string;
}

export interface SystemMemoryProjectionQuery {
  scope: SystemMemoryVizScope;
  workspaceId?: UUID;
}

export interface SystemMemoryExport extends MemoryEnvelope {
  entries: MemorySystemEntryRow[];
  count: number;
  truncated: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a `?a=b&c=d` query string, dropping `undefined` and empty values. */
function buildQueryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

interface RawHealthComponent {
  name?: string;
  status?: string;
  detail?: string;
  backend?: string;
  ok?: boolean;
  degraded?: boolean;
}

/**
 * Fetch a raw (non-JSON-negotiated by `apiClient`) memory export. The export
 * endpoint answers `text/csv` for `?format=csv`, which `apiClient` (JSON-only)
 * cannot represent, so this bypasses it while keeping the same cookie/CSRF-free
 * GET conventions. Errors are surfaced as the parsed error body so callers can
 * reuse `extractApiErrorMessage`.
 */
async function fetchExport(path: string): Promise<Response> {
  const lang = document.documentElement.lang || "en";
  const response = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    headers: { Accept: "application/json", "Accept-Language": lang },
  });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON error body → fall through to a generic Error below.
    }
    if (body !== null) throw body;
    throw new Error(`HTTP ${response.status}`);
  }
  return response;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export const memoryApi = {
  // -- workspace scope ---------------------------------------------------

  /** GET /workspaces/{ws}/memory/entries/ — list live entries for the scope. */
  listWorkspaceEntries(
    workspaceId: UUID,
    query: MemoryListQuery = {}
  ): Promise<MemoryEntryPage> {
    const qs = buildQueryString({
      scope: query.scope,
      artifact_id: query.artifact_id,
      contributor_user_id: query.contributor_user_id,
      q: query.q,
      page: query.page,
      page_size: query.page_size,
    });
    return apiClient.get<MemoryEntryPage>(
      `/workspaces/${workspaceId}/memory/entries/${qs}`
    );
  },

  /** POST /workspaces/{ws}/memory/entries/ — create a workspace-scoped fact. */
  createWorkspaceEntry(
    workspaceId: UUID,
    payload: MemoryWritePayload
  ): Promise<MemoryEntry> {
    return apiClient.post<MemoryEntry>(
      `/workspaces/${workspaceId}/memory/entries/`,
      payload
    );
  },

  /** GET /workspaces/{ws}/memory/search/ — semantic search for one scope. */
  searchWorkspaceMemory(
    workspaceId: UUID,
    query: MemorySearchQuery
  ): Promise<MemorySearchResult> {
    const qs = buildQueryString({
      q: query.q,
      scope: query.scope,
      artifact_id: query.artifact_id,
      top_k: query.top_k,
    });
    return apiClient.get<MemorySearchResult>(
      `/workspaces/${workspaceId}/memory/search/${qs}`
    );
  },

  /** GET /workspaces/{ws}/memory/digest/ — consolidated workspace digest. */
  getWorkspaceDigest(workspaceId: UUID): Promise<MemoryDigest> {
    return apiClient.get<MemoryDigest>(
      `/workspaces/${workspaceId}/memory/digest/`
    );
  },

  // -- entry detail ------------------------------------------------------

  /** GET /memory/entries/{entry_id}/ — one entry's full provenance view. */
  getEntry(entryId: string): Promise<MemoryEntry> {
    return apiClient.get<MemoryEntry>(`/memory/entries/${entryId}/`);
  },

  /** DELETE /memory/entries/{entry_id}/ — forget one entry. */
  forgetEntry(
    entryId: string,
    changeReason?: string
  ): Promise<{ deleted: boolean }> {
    const qs = buildQueryString({ change_reason: changeReason });
    return apiClient.delete<{ deleted: boolean }>(
      `/memory/entries/${entryId}/${qs}`
    );
  },

  /** POST /memory/entries/{entry_id}/promote/ — promote user -> workspace. */
  promoteEntry(
    entryId: string,
    payload: MemoryPromotePayload = {}
  ): Promise<MemoryEntry> {
    return apiClient.post<MemoryEntry>(
      `/memory/entries/${entryId}/promote/`,
      payload
    );
  },

  // -- artifact scope ----------------------------------------------------

  /** GET /artifacts/{artifact_id}/memory/ — artifact-scoped entry list. */
  listArtifactMemory(
    artifactId: UUID,
    query: { q?: string; page?: number; page_size?: number } = {}
  ): Promise<MemoryEntryPage> {
    const qs = buildQueryString({
      q: query.q,
      page: query.page,
      page_size: query.page_size,
    });
    return apiClient.get<MemoryEntryPage>(`/artifacts/${artifactId}/memory/${qs}`);
  },

  /** GET /artifacts/{artifact_id}/memory/digest/ — consolidated artifact digest. */
  getArtifactDigest(artifactId: UUID): Promise<MemoryDigest> {
    return apiClient.get<MemoryDigest>(`/artifacts/${artifactId}/memory/digest/`);
  },

  /** POST /artifacts/{artifact_id}/memory/ — create an artifact-scoped fact. */
  createArtifactMemory(
    artifactId: UUID,
    payload: MemoryWritePayload
  ): Promise<MemoryEntry> {
    return apiClient.post<MemoryEntry>(
      `/artifacts/${artifactId}/memory/`,
      payload
    );
  },

  // -- self service ------------------------------------------------------

  /** GET /memory/me/ — the caller's own user-scoped overview (+ entries). */
  getSelfOverview(query: MemorySelfOverviewQuery = {}): Promise<MemorySelfOverview> {
    const qs = buildQueryString({
      include_entries: query.includeEntries ? "true" : undefined,
      page: query.page,
      page_size: query.pageSize,
    });
    return apiClient.get<MemorySelfOverview>(`/memory/me/${qs}`);
  },

  /** DELETE /memory/me/ — purge all of the caller's own user-scoped memory. */
  deleteSelfMemory(): Promise<{ deleted: number }> {
    return apiClient.delete<{ deleted: number }>("/memory/me/");
  },

  // -- health ------------------------------------------------------------

  /**
   * GET /admin/health/ — extract the `memory` component from the shared
   * system-health snapshot. Admin-only, matching the parent endpoint.
   */
  async getMemoryHealth(): Promise<MemoryHealth> {
    const snapshot = await apiClient.get<{ components?: RawHealthComponent[] }>(
      "/admin/health/"
    );
    const component = snapshot.components?.find((c) => c.name === "memory");
    if (!component) {
      throw new Error("System health response has no 'memory' component");
    }
    return {
      backend: component.backend ?? "unknown",
      ok: component.ok ?? false,
      degraded: component.degraded ?? false,
      detail: component.detail ?? "",
      status: component.status ?? "unknown",
    };
  },

  // -- system admin ------------------------------------------------------

  /** GET /system/memory/workspaces/ — per-workspace overview. */
  listSystemWorkspaceOverview(): Promise<{ results: WorkspaceMemoryOverviewRow[] }> {
    return apiClient.get<{ results: WorkspaceMemoryOverviewRow[] }>(
      "/system/memory/workspaces/"
    );
  },

  /** DELETE /system/memory/workspaces/{ws}/ — purge both tiers + artifacts. */
  deleteSystemWorkspaceMemory(
    workspaceId: UUID
  ): Promise<WorkspaceMemoryDeleteResult> {
    return apiClient.delete<WorkspaceMemoryDeleteResult>(
      `/system/memory/workspaces/${workspaceId}/`
    );
  },

  /** GET /system/memory/entries/ — paginated, filterable entry list. */
  listSystemEntries(query: SystemMemoryEntryQuery): Promise<MemorySystemEntryPage> {
    const qs = buildQueryString({
      scope: query.scope,
      workspace_id: query.workspaceId,
      page: query.page,
      page_size: query.pageSize,
      q: query.q,
    });
    return apiClient.get<MemorySystemEntryPage>(`/system/memory/entries/${qs}`);
  },

  /** GET /system/memory/projection/ — 2D PCA projection + clustering. */
  getSystemProjection(
    query: SystemMemoryProjectionQuery
  ): Promise<MemoryProjection> {
    const qs = buildQueryString({
      scope: query.scope,
      workspace_id: query.workspaceId,
    });
    return apiClient.get<MemoryProjection>(`/system/memory/projection/${qs}`);
  },

  /** GET /system/memory/entries/export/?format=json — DSGVO export (JSON). */
  async exportSystemEntriesJson(): Promise<SystemMemoryExport> {
    const response = await fetchExport("/system/memory/entries/export/?format=json");
    return response.json() as Promise<SystemMemoryExport>;
  },

  /** GET /system/memory/entries/export/?format=csv — DSGVO export (CSV text). */
  async exportSystemEntriesCsv(): Promise<string> {
    const response = await fetchExport("/system/memory/entries/export/?format=csv");
    return response.text();
  },
};
