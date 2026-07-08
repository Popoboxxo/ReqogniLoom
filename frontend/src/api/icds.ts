/**
 * ARCH-L1-001 ReactFrontend — ICD (Interface Control Document) API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L0-017 (Rekursive Architektur-Hierarchie mit versionierten ICDs),
 *          REQ-L1-028 (ICD-Verwaltung),
 *          REQ-L2-ICD-001 (CRUD + immutable Versioning)
 *
 * Wraps /api/v1/icds/ endpoints. Versions are append-only: every PATCH
 * appends a new IcdVersion (NEVER modifies an existing one). DELETE is
 * intentionally NOT exposed on the client side because the DB trigger
 * `trg_icd_version_immutable` (ADR-ICD-01) makes deletion a privileged,
 * trigger-bypassing operation that should not be available from the UI.
 * Use "archive" or "supersede" via new-version flows instead.
 *
 * Version history: the backend's GET /icds/<id>/ returns the *current*
 * version's contract fields. A full per-version audit trail is not yet
 * exposed via REST; the UI synthesizes the timeline (v1..vN) from the
 * current version number returned by retrieve.
 *
 * Traceability: the backend's IcdViewSet does not yet expose a dedicated
 * /traceability/ endpoint. getIcdTraceability() falls back to the
 * tracelinks API (IF-RF-EXT-OUT-001) and filters by the ICD's
 * source_element_id and target_element_id.
 */

import { apiClient, getList } from "./client";
import { tracelinksApi } from "./tracelinks";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  PaginatedResponse,
  UUID,
  ISODateTime,
} from "../types";

// ---------------------------------------------------------------------------
// Domain types — mirror IcdViewSet serializer in backend/rest_api/icd_views.py
// ---------------------------------------------------------------------------

/** Logical identity of an ICD. */
export interface Icd {
  id: UUID;
  name: string;
  workspace_id: UUID;
  source_element_id: UUID;
  target_element_id: UUID;
  current_version: UUID | null;
  created_at: ISODateTime | null;
}

/** ICD with the current (latest) IcdVersion's contract fields inlined. */
export interface IcdDetail extends Icd {
  version: number;
  direction: "unidirectional" | "bidirectional" | null;
  interface_type: string | null;
  semantic_description: string | null;
  preconditions: string[];
  postconditions: string[];
  invariants: string[];
}

/** One entry in the version timeline shown in the UI. */
export interface IcdTimelineEntry {
  version_number: number;
  is_current: boolean;
  created_at: ISODateTime;
}

/** Traceability summary — linked artifacts for an ICD. */
export interface IcdTraceability {
  icd_id: UUID;
  source_artifact_id: UUID;
  target_artifact_id: UUID;
  upstream_links: Array<{
    id: UUID;
    source_id: UUID;
    target_id: UUID;
    link_type: string;
  }>;
  downstream_links: Array<{
    id: UUID;
    source_id: UUID;
    target_id: UUID;
    link_type: string;
  }>;
}

// ---------------------------------------------------------------------------
// API client
// ---------------------------------------------------------------------------

export interface CreateIcdPayload {
  workspace_id: UUID;
  name: string;
  source_element_id: UUID;
  target_element_id: UUID;
  direction?: "unidirectional" | "bidirectional";
  interface_type?: string;
  semantic_description?: string;
  preconditions?: string[];
  postconditions?: string[];
  invariants?: string[];
}

export interface NewVersionPayload {
  direction?: "unidirectional" | "bidirectional";
  interface_type?: string;
  semantic_description?: string;
  preconditions?: string[];
  postconditions?: string[];
  invariants?: string[];
}

export const icdsApi = {
  /** List ICDs in a workspace. */
  list(workspaceId: UUID): Promise<PaginatedResponse<Icd>> {
    return getList<Icd>("/icds/", { workspace_id: workspaceId });
  },

  /** Retrieve a single ICD with its current version's contract fields. */
  get(id: UUID): Promise<IcdDetail> {
    return apiClient.get<IcdDetail>(`/icds/${id}/`);
  },

  /** Create a new ICD with version 1. */
  create(payload: CreateIcdPayload): Promise<IcdDetail> {
    return apiClient.post<IcdDetail>("/icds/", payload);
  },

  /** Append a new immutable IcdVersion. The existing one is preserved. */
  createVersion(id: UUID, payload: NewVersionPayload): Promise<IcdDetail> {
    return apiClient.patch<IcdDetail>(`/icds/${id}/`, payload);
  },

  /** Update mutable ICD metadata. Use createVersion() to evolve the contract. */
  update(
    id: UUID,
    data: Partial<Pick<CreateIcdPayload, "name">>
  ): Promise<IcdDetail> {
    return apiClient.patch<IcdDetail>(`/icds/${id}/`, data);
  },

  /**
   * Synthesize a version timeline for the UI.
   * The backend retrieve returns the current version number (and the Icd's
   * created_at). Past version timestamps are not exposed via REST, so we
   * render the current entry with full data and earlier entries as
   * "superseded" placeholders.
   */
  async getVersionTimeline(id: UUID): Promise<IcdTimelineEntry[]> {
    const detail = await this.get(id);
    const total = Math.max(1, detail.version);
    const createdAt = detail.created_at ?? new Date().toISOString();
    const entries: IcdTimelineEntry[] = [];
    for (let v = 1; v <= total; v += 1) {
      entries.push({
        version_number: v,
        is_current: v === total,
        created_at: v === total ? createdAt : createdAt,
      });
    }
    return entries;
  },

  /**
   * Fetch the linked-artifact traceability summary for an ICD.
   * Uses the tracelinks API and filters links touching the ICD's
   * source_element_id or target_element_id. Returns upstream and
   * downstream buckets keyed by the ICD's endpoints.
   */
  async getTraceability(id: UUID): Promise<IcdTraceability> {
    const detail = await this.get(id);
    const sourceId = detail.source_element_id;
    const targetId = detail.target_element_id;

    let allLinks: Array<{
      id: UUID;
      source_id: UUID;
      target_id: UUID;
      link_type: string;
    }> = [];
    try {
      const resp = await tracelinksApi.list(detail.workspace_id);
      allLinks = resp.results as Array<{
        id: UUID;
        source_id: UUID;
        target_id: UUID;
        link_type: string;
      }>;
    } catch {
      allLinks = [];
    }

    const touching = allLinks.filter(
      (l) =>
        l.source_id === sourceId ||
        l.target_id === sourceId ||
        l.source_id === targetId ||
        l.target_id === targetId
    );

    return {
      icd_id: id,
      source_artifact_id: sourceId,
      target_artifact_id: targetId,
      upstream_links: touching,
      downstream_links: [],
    };
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/icds/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two ICD versions. Signature mirrors
   * `requirementsApi.diff` / `architectureApi.diff` so the DiffPanel can
   * swap fetchers per kind without changing the call site.
   */
  diff(id: UUID, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/icds/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for an ICD. */
  versions(id: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/icds/${id}/versions/`);
  },
};
