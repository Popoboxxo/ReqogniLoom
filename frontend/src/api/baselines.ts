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
  /**
   * F4.2/F4.3: labels attached to this baseline. Always present on both the
   * list and the detail response (sorted case-insensitively by the backend).
   */
  tags: string[];
  /** REQ-L2-BL-012: captured items — only on the detail response. */
  entries?: BaselineDeltaEntry[];
}

/** F4.2: response of `PUT /api/v1/baselines/{id}/tags/`. */
export interface BaselineTagsResponse {
  id: UUID;
  tags: string[];
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

/**
 * GH-513: error code returned by POST /baselines/ when the SE-Auditor reports
 * BLOCKER findings for the workspace. Distinct from a generic
 * `VALIDATION_ERROR` (which the same endpoint also uses for an *unevaluable*
 * auditor — that case is deliberately not waivable), so the UI can offer the
 * documented override path instead of a dead error message.
 */
export const SE_AUDITOR_BLOCKED_CODE = "SE_AUDITOR_BLOCKED";

/** True when `err` is the API's SE-Auditor block envelope (GH-513). */
export function isSeAuditorBlocked(err: unknown): boolean {
  return (
    (err as { error?: { code?: string } })?.error?.code ===
    SE_AUDITOR_BLOCKED_CODE
  );
}

/**
 * Plan F F4.5 — additive baseline rollback (ADR-025).
 *
 * The rollback is a three-step, CCB-gated flow: a read-only preview computes
 * the plan, `rollback-request` opens a change request bound to exactly the
 * items the plan would write, and `rollback` executes it once the CCB has
 * approved. Nothing here is a local invention — each type mirrors the backend
 * serializer pair it reads (`BaselineRollbackPreviewSerializer`,
 * `BaselineRollbackResultSerializer`).
 */
export type RollbackItemAction =
  | "restore"
  | "reactivate"
  | "unchanged"
  | "unsupported"
  | "created_since";

/**
 * One differing restorable field, as the plan reports it (ADR-025 R4):
 * `{field: {"current": v, "baseline": v}}`. Values are arbitrary JSON.
 */
export interface RollbackFieldChange {
  current: unknown;
  baseline: unknown;
}

/** One baseline member as the rollback plan sees it. */
export interface RollbackPlanItem {
  /** Delta-index id — the Artifact UUID for artifact-backed items. */
  item_id: string;
  /** Canonical item type, or "" when no type is supported. */
  artifact_type: string;
  action: RollbackItemAction;
  field_changes: Record<string, RollbackFieldChange>;
  /** Restorable fields the snapshot does not carry — reported, never guessed. */
  unrestorable_fields: string[];
  /** Current optimistic-lock version, or null when the row is gone. */
  current_version: number | null;
}

/** Per-action counts of a rollback plan plus the link buckets. */
export interface RollbackSummary {
  restore: number;
  reactivate: number;
  unchanged: number;
  unsupported: number;
  created_since: number;
  links_to_recreate: number;
  /** Additive backend key; absent on older payloads. */
  skipped_links?: number;
}

/** A baseline trace link the rollback would re-insert (or deliberately skip). */
export interface RollbackLinkRef {
  source_id?: string;
  target_id?: string;
  link_type?: string;
  reason?: string;
}

/** 200 body of `GET /api/v1/baselines/{id}/rollback-preview/`. */
export interface RollbackPreview {
  baseline_id: UUID;
  summary: RollbackSummary;
  items: RollbackPlanItem[];
  links_to_recreate: RollbackLinkRef[];
  skipped_links: RollbackLinkRef[];
}

/** Body of `POST /api/v1/baselines/{id}/rollback-request/`. */
export interface RollbackRequestPayload {
  /** Mandatory justification recorded on the change request. */
  change_reason: string;
  /** Optional CR title; the backend generates one when omitted. */
  title?: string;
}

/** 201 body of `POST /api/v1/baselines/{id}/rollback-request/`. */
export interface RollbackRequestResult {
  change_request_id: UUID;
  /** Workflow state of the new CR — `draft` until the CCB approves it. */
  status: string;
  affected_items: number;
}

/** Body of `POST /api/v1/baselines/{id}/rollback/`. */
export interface RollbackApplyPayload {
  change_request_id: UUID;
}

/** 200 body of `POST /api/v1/baselines/{id}/rollback/`. */
export interface RollbackResult {
  restored: number;
  reactivated: number;
  links_recreated: number;
  /** The change request's state after the run (`implemented`). */
  change_request_status: string;
  skipped: Record<string, unknown>[];
}

/**
 * Stable `error.code` values of the three rollback routes (SEC-RB-05), so the
 * UI branches on the reason instead of inferring it from a 409.
 */
export const ROLLBACK_CODES = {
  planStale: "ROLLBACK_PLAN_STALE",
  alreadyApplied: "ROLLBACK_ALREADY_APPLIED",
  notApproved: "ROLLBACK_NOT_APPROVED",
  tooLarge: "ROLLBACK_TOO_LARGE",
  empty: "ROLLBACK_EMPTY",
} as const;

export const baselinesApi = {
  /**
   * F4.2: list baselines, optionally filtered server-side by one tag.
   * `tag` is omitted entirely when absent — an empty string would be read as
   * a (rejected) empty label by the backend.
   */
  list(params: {
    workspace_id: UUID;
    tag?: string;
  }): Promise<PaginatedResponse<Baseline>> {
    return getList<Baseline>("/baselines/", {
      workspace_id: params.workspace_id,
      ...(params.tag ? { tag: params.tag } : {}),
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
    /**
     * GH-513: written justification for creating the baseline although the
     * SE-Auditor reports BLOCKER findings (error code
     * {@link SE_AUDITOR_BLOCKED_CODE}). Requires the `admin` or `approver`
     * role; the backend records it in the audit log and appends it to the
     * baseline description. Omitting it keeps the fail-closed default.
     */
    override_reason?: string;
    /** F4.2: optional labels to attach at creation time. */
    tags?: string[];
  }): Promise<Baseline> {
    return apiClient.post<Baseline>("/baselines/", data);
  },

  /**
   * F4.2: replace the complete tag set of one baseline. The backend validates
   * (`400 VALIDATION_ERROR` with one `details` entry per rejected label),
   * de-duplicates case-insensitively and returns the sorted result.
   */
  setTags(id: UUID, tags: string[]): Promise<BaselineTagsResponse> {
    return apiClient.put<BaselineTagsResponse>(`/baselines/${id}/tags/`, {
      tags,
    });
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/baselines/${id}/`);
  },

  /** REQ-L2-BL-003: field-level diff between two baselines of the same scope. */
  compare(baselineAId: UUID, baselineBId: UUID): Promise<BaselineDiff> {
    return compareBaselines(baselineAId, baselineBId);
  },

  /**
   * F4.5: what a rollback of this baseline would change. Read-only and open
   * to every workspace member (Viewer included) — it writes nothing and opens
   * no change request (ADR-025 R8).
   */
  rollbackPreview(id: UUID): Promise<RollbackPreview> {
    return apiClient.get<RollbackPreview>(
      `/baselines/${id}/rollback-preview/`
    );
  },

  /**
   * F4.5: open the CCB change request the rollback must pass through
   * (ADR-025 R2). The plan is re-derived server-side and bound to the CR's
   * affected-item set, so approval happens against exactly the items the
   * rollback would write.
   */
  rollbackRequest(
    id: UUID,
    payload: RollbackRequestPayload
  ): Promise<RollbackRequestResult> {
    return apiClient.post<RollbackRequestResult>(
      `/baselines/${id}/rollback-request/`,
      payload
    );
  },

  /**
   * F4.5: execute an approved rollback. One transaction: the plan is
   * re-derived, checked against the CR's affected-item set and written as new
   * versions; any failure rolls the whole run back (ADR-025 R1/R3/R5).
   */
  rollbackApply(
    id: UUID,
    payload: RollbackApplyPayload
  ): Promise<RollbackResult> {
    return apiClient.post<RollbackResult>(
      `/baselines/${id}/rollback/`,
      payload
    );
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
