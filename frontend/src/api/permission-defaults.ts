/**
 * ARCH-L1-001 ReactFrontend — Global & Workspace Permission Definition API
 * (REQ-181/182/183/186/187).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — System / Workspace Settings scope)
 *
 * Wraps the permission global-default endpoints (see
 * docs/api/workflow-permissions-global-default.openapi.yaml):
 *   - /permission-defaults/                     global 4×6 role→capability matrix
 *   - /permission-defaults/enforcement/         shadow/authoritative phase read
 *   - /permission-defaults/enforcement/flip/    guarded phase transition
 *   - /workspaces/{id}/permission-definition/   workspace override + reset
 *   - /permission-mismatches/                   read-only shadow-mismatch log
 *
 * The matrix is a CLOSED 4-role × 6-capability boolean shape — no add/remove of
 * rows or columns is possible from the UI, matching the schema's
 * ``additionalProperties: false`` guard.
 */

import { apiClient, getList } from "./client";
import type { PaginatedResponse, UUID } from "../types";

// ---------------------------------------------------------------------------
// Canonical closed vocabulary (source of truth: the OpenAPI addendum).
// ---------------------------------------------------------------------------

export const ROLE_KEYS = ["admin", "editor", "viewer", "approver"] as const;
export type RoleKey = (typeof ROLE_KEYS)[number];

export const CAPABILITY_KEYS = [
  "read",
  "write",
  "workflow_transition",
  "workflow_approval",
  "workspace_config",
  "assign_role",
] as const;
export type CapabilityKey = (typeof CAPABILITY_KEYS)[number];

export type EnforcementMode = "shadow" | "authoritative";

/** Closed role→capability boolean matrix. */
export type CapabilitySet = Record<CapabilityKey, boolean>;
export type PermissionMatrix = Record<RoleKey, CapabilitySet>;

export interface GlobalPermissionDefinition {
  tenant_id: UUID;
  permission_json: PermissionMatrix;
  enforcement_mode: EnforcementMode;
  updated_at?: string | null;
  /** Present on PUT responses (propagation into on-default workspaces). */
  propagated_workspace_count?: number;
}

export interface WorkspacePermissionDefinition {
  workspace_id: UUID;
  permission_json: PermissionMatrix;
  is_customized: boolean;
  source_global_id?: UUID | null;
  updated_at?: string | null;
}

export interface EnforcementStatus {
  enforcement_mode: EnforcementMode;
  pending_mismatch_count: number;
  mismatch_window_days: number;
  last_mismatch_at?: string | null;
  ready_for_authoritative: boolean;
  advisory_note?: string;
}

export type MismatchSubjectType = "user" | "apikey" | "agent";

export interface PermissionDecisionMismatch {
  id: UUID;
  workspace_id?: UUID | null;
  subject_identifier: string;
  subject_type?: MismatchSubjectType;
  capability: CapabilityKey;
  artifact_id?: UUID | null;
  legacy_decision: boolean;
  new_decision: boolean;
  context_json?: Record<string, unknown>;
  created_at: string;
}

export interface MismatchQuery {
  workspace_id?: string;
  capability?: CapabilityKey;
  subject_type?: MismatchSubjectType;
  subject_identifier?: string;
  since?: string;
  until?: string;
  page?: number;
  page_size?: number;
}

/** Build an all-false capability set (used to backfill a missing role/cap). */
export function emptyCapabilitySet(): CapabilitySet {
  return CAPABILITY_KEYS.reduce((acc, cap) => {
    acc[cap] = false;
    return acc;
  }, {} as CapabilitySet);
}

/**
 * Normalise a possibly-partial matrix into the full closed 4×6 shape so the
 * grid always has every cell to render (the API guarantees a full matrix, but
 * this keeps the editor defensive against partial fixtures).
 */
export function normalizeMatrix(input: Partial<PermissionMatrix> | undefined): PermissionMatrix {
  return ROLE_KEYS.reduce((acc, role) => {
    const row = input?.[role] ?? {};
    acc[role] = CAPABILITY_KEYS.reduce((cap_acc, cap) => {
      cap_acc[cap] = Boolean((row as Partial<CapabilitySet>)[cap]);
      return cap_acc;
    }, {} as CapabilitySet);
    return acc;
  }, {} as PermissionMatrix);
}

export const permissionDefaultsApi = {
  /** GET /api/v1/permission-defaults/ — tenant global matrix + phase. */
  getGlobal(): Promise<GlobalPermissionDefinition> {
    return apiClient.get<GlobalPermissionDefinition>("/permission-defaults/");
  },

  /** PUT /api/v1/permission-defaults/ — full-replace the global matrix. */
  replaceGlobal(matrix: PermissionMatrix): Promise<GlobalPermissionDefinition> {
    return apiClient.put<GlobalPermissionDefinition>("/permission-defaults/", {
      permission_json: matrix,
    });
  },

  /** GET /api/v1/permission-defaults/enforcement/ — current phase + readiness. */
  getEnforcement(windowDays?: number): Promise<EnforcementStatus> {
    const qs = windowDays
      ? `?${new URLSearchParams({ window_days: String(windowDays) }).toString()}`
      : "";
    return apiClient.get<EnforcementStatus>(
      `/permission-defaults/enforcement/${qs}`
    );
  },

  /**
   * POST /api/v1/permission-defaults/enforcement/flip/ — guarded phase change.
   * ``shadow → authoritative`` MUST pass ``confirmPendingMismatchCount`` equal
   * to the current server count, else a 409 MISMATCH_COUNT_STALE is thrown.
   * ``authoritative → shadow`` (rollback) needs no count.
   */
  flipEnforcement(
    mode: EnforcementMode,
    confirmPendingMismatchCount?: number
  ): Promise<GlobalPermissionDefinition> {
    const body: {
      enforcement_mode: EnforcementMode;
      confirm_pending_mismatch_count?: number;
    } = { enforcement_mode: mode };
    if (typeof confirmPendingMismatchCount === "number") {
      body.confirm_pending_mismatch_count = confirmPendingMismatchCount;
    }
    return apiClient.post<GlobalPermissionDefinition>(
      "/permission-defaults/enforcement/flip/",
      body
    );
  },

  /** GET /api/v1/workspaces/{id}/permission-definition/ — effective matrix. */
  getWorkspace(workspaceId: UUID): Promise<WorkspacePermissionDefinition> {
    return apiClient.get<WorkspacePermissionDefinition>(
      `/workspaces/${workspaceId}/permission-definition/`
    );
  },

  /** PUT /api/v1/workspaces/{id}/permission-definition/ — override matrix. */
  replaceWorkspace(
    workspaceId: UUID,
    matrix: PermissionMatrix
  ): Promise<WorkspacePermissionDefinition> {
    return apiClient.put<WorkspacePermissionDefinition>(
      `/workspaces/${workspaceId}/permission-definition/`,
      { permission_json: matrix }
    );
  },

  /**
   * POST /api/v1/workspaces/{id}/permission-definition/reset/ — reset to the
   * current global default. Throws 409 NO_GLOBAL_SOURCE when unlinked.
   */
  resetWorkspace(workspaceId: UUID): Promise<WorkspacePermissionDefinition> {
    return apiClient.post<WorkspacePermissionDefinition>(
      `/workspaces/${workspaceId}/permission-definition/reset/`,
      {}
    );
  },

  /** GET /api/v1/permission-mismatches/ — paginated read-only mismatch log. */
  listMismatches(
    query: MismatchQuery = {}
  ): Promise<PaginatedResponse<PermissionDecisionMismatch>> {
    const params: Record<string, string> = {};
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== "" && value !== null) {
        params[key] = String(value);
      }
    }
    return getList<PermissionDecisionMismatch>(
      "/permission-mismatches/",
      params
    );
  },
};

/** Extract the fresh server count from a 409 MISMATCH_COUNT_STALE error body. */
export function extractStaleMismatchCount(err: unknown): number | null {
  const detail = (err as { error?: { details?: Array<{ current_count?: number }> } })
    ?.error?.details?.[0];
  return typeof detail?.current_count === "number" ? detail.current_count : null;
}
