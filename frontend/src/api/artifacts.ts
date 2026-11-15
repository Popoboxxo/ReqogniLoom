/**
 * ARCH-L1-001 ReactFrontend — Artifacts API.
 *
 * leaf_id: COMP-RF-001 (SidebarNavigation / ArtifactTree)
 * req_id:  REQ-L2-RF-005 (Artefakt-Navigation)
 *
 * Wraps /api/v1/artifacts/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Artifact, ISODateTime, PaginatedResponse, UUID } from "../types";

/**
 * #399: one baseline the artifact is a member of, with its drift verdict.
 * Mirrors `BaselineFacade.ArtifactBaselineMembership` (spec section 6.2).
 */
export interface ArtifactBaselineMembership {
  baseline_id: UUID;
  baseline_name: string;
  /** document | project | global */
  scope: string;
  baselined_at: ISODateTime;
  /**
   * Informational: the `Artifact.version` captured at baseline time — not the
   * entity's own version. A content edit bumps the entity version without
   * bumping `Artifact.version`, so this can equal `current_version` even when
   * the artifact genuinely drifted. `drifted` is authoritative.
   */
  baselined_version: number;
  /** Informational: the `Artifact.version` right now; same caveat as `baselined_version`. */
  current_version: number;
  drifted: boolean;
  /**
   * `false` for legacy delta-index entries captured without a `state` — the
   * version comparison is then the only signal available.
   */
  drift_known: boolean;
}

/** #399: response of `GET /api/v1/artifacts/{id}/baseline-membership/`. */
export interface BaselineMembershipResponse {
  artifact_id: UUID;
  /** `true` when at least one membership is drifted. */
  drifted: boolean;
  memberships: ArtifactBaselineMembership[];
}

/**
 * Body of `POST /api/v1/artifacts/{id}/move/` (P1 Task 1.4).
 *
 * The two fields encode *three* cases, because the server distinguishes an
 * absent `after_id` from an explicit `null` (spec B8):
 *   - `parent_id` only            → append at the end of the new parent,
 *   - `after_id: null`            → insert as the first child,
 *   - `after_id: '<sibling id>'`  → insert directly behind that sibling.
 *
 * `after_id` is therefore optional and never derived from `parent_id`; a
 * caller that means "first" must pass `null`, not `undefined`.
 */
export interface MoveArtifactOptions {
  parent_id: UUID | null;
  after_id?: UUID | null;
}

export const artifactsApi = {
  list(workspaceId: UUID, parentId?: UUID): Promise<PaginatedResponse<Artifact>> {
    const params: Record<string, string> = { workspace_id: workspaceId };
    if (parentId) params["parent_id"] = parentId;
    return getList<Artifact>("/artifacts/", params);
  },

  get(id: UUID): Promise<Artifact> {
    return apiClient.get<Artifact>(`/artifacts/${id}/`);
  },

  /**
   * #399: baseline membership + drift for one artifact. Called once per open
   * editor header, never per list row (spec D7 — a list badge would be an
   * N+1 without a batch endpoint).
   */
  baselineMembership(id: UUID): Promise<BaselineMembershipResponse> {
    return apiClient.get<BaselineMembershipResponse>(
      `/artifacts/${id}/baseline-membership/`
    );
  },

  create(data: {
    workspace_id: UUID;
    artifact_type: string;
    parent_id?: UUID;
  }): Promise<Artifact> {
    return apiClient.post<Artifact>("/artifacts/", data);
  },

  /**
   * Reparent and/or reorder one artifact (`POST /artifacts/{id}/move/`).
   *
   * `id` is the **backing Artifact** id, not the entity id an editor route
   * uses — `Requirement.artifact_id` / `ArchitectureElement.artifact_id` is
   * the value this route keys on. Passing an entity id answers 404.
   */
  move(id: UUID, options: MoveArtifactOptions): Promise<Artifact> {
    const body: { parent_id: UUID | null; after_id?: UUID | null } = {
      parent_id: options.parent_id,
    };
    // Presence, not truthiness: `null` means "insert first" and must survive,
    // while an omitted/undefined key means "append at the end". JSON drops an
    // undefined value either way, so only the key is written when it is set.
    if (options.after_id !== undefined) body.after_id = options.after_id;
    return apiClient.post<Artifact>(`/artifacts/${id}/move/`, body);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/artifacts/${id}/`);
  },

  /**
   * `PATCH /api/v1/artifacts/bulk-update/` (R3 → R6, plan
   * 2026-11-15-document-view-on-document.md).
   *
   * All-or-nothing: the server validates and writes every entry inside one
   * transaction, so a single bad entry leaves the database untouched and the
   * whole batch comes back as 409 with an `errors` list (see
   * `extractBulkErrors`). A 400 is a *request* problem (empty list, more than
   * `BULK_UPDATE_MAX_ENTRIES` entries) and carries no per-entry detail.
   */
  bulkUpdate(
    workspaceId: UUID,
    entries: BulkUpdateEntry[]
  ): Promise<BulkUpdateResult> {
    return apiClient.patch<BulkUpdateResult>("/artifacts/bulk-update/", {
      workspace_id: workspaceId,
      entries,
    });
  },
};

/** One write of `PATCH /artifacts/bulk-update/` (mirrors `BulkEntry`). */
export interface BulkUpdateEntry {
  /** The **backing Artifact** id (`Document.artifact_id`, not the entity id). */
  artifact_id: UUID;
  /** The version the surface rendered; a mismatch rolls the batch back. */
  expected_version: number;
  fields: Record<string, unknown>;
}

/** One successfully written entry; `version` is the post-write revision. */
export interface BulkUpdateUpdatedEntry {
  artifact_id: UUID;
  version: number;
}

/** One rejected entry (mirrors `BulkUpdateResult.errors`). */
export interface BulkUpdateErrorEntry {
  index: number;
  artifact_id: UUID;
  /** Backend error code, e.g. `FIELD_FROZEN`, `CONFLICT`, `VALIDATION_ERROR`. */
  code: string;
  message: string;
  /** Set when the failure is attributable to a single field. */
  field?: string;
}

export interface BulkUpdateResult {
  updated: BulkUpdateUpdatedEntry[];
  errors: BulkUpdateErrorEntry[];
}

/** Server-side ceiling of one batch (mirrors `BulkUpdateService.MAX_ENTRIES`). */
export const BULK_UPDATE_MAX_ENTRIES = 100;

/**
 * Normalise the two shapes a rejected batch can arrive in into one
 * `BulkUpdateErrorEntry[]`.
 *
 * The contract says 409 answers with `{updated, errors}`. The shared API
 * client, however, throws the *parsed body* of any non-2xx response, and the
 * REST error envelope is the house shape for service failures — so a batch
 * rejected before it reaches the service (or a future server-side change)
 * arrives as `{error: {code, message, details: [{field, errors}]}}`. Both are
 * mapped here so the caller never has to know which one it got; an unknown
 * shape degrades to the envelope's `message`.
 */
export function extractBulkErrors(error: unknown): BulkUpdateErrorEntry[] {
  const body = error as
    | {
        errors?: unknown;
        error?: {
          code?: string;
          message?: string;
          details?: ReadonlyArray<{ field?: string; errors?: string[] }>;
        };
      }
    | null
    | undefined;

  if (Array.isArray(body?.errors)) {
    return body.errors as BulkUpdateErrorEntry[];
  }

  const envelope = body?.error;
  if (!envelope) return [];

  if (Array.isArray(envelope.details) && envelope.details.length > 0) {
    return envelope.details.map((detail, index) => ({
      index,
      artifact_id: "",
      code: envelope.code ?? "UNKNOWN",
      message: detail.errors?.[0] ?? envelope.message ?? "",
      ...(detail.field ? { field: detail.field } : {}),
    }));
  }

  return [
    {
      index: 0,
      artifact_id: "",
      code: envelope.code ?? "UNKNOWN",
      message: envelope.message ?? "",
    },
  ];
}
