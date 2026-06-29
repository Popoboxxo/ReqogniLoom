/**
 * ARCH-L1-001 ReactFrontend — User workspace preferences API (REQ-L1-027).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceContext consumer)
 * req_id:  REQ-L1-027 (Per-user visibility overrides)
 *
 * Wraps the backend endpoints under /api/v1/users/me/preferences/.
 *   GET  ?workspace_id=<uuid>  → 200 with optional_artifact_visibility OR 404
 *   PATCH {workspace_id, optional_artifact_visibility: {...}} → 200 with merged row
 *
 * Note: feature keys mirror PRESET_VISIBILITY (types/index.ts) so the
 * backend service can do a shallow {**preset, **overrides} merge without
 * a key translation.  The six optional-artifact keys are listed in
 * OPTIONAL_FEATURES; the special ``_hide_all_optional`` key is a UI-only
 * master switch stored in the same JSON blob.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Per-feature visibility overrides. Keys MUST match PRESET_VISIBILITY. */
export interface FeatureVisibility {
  adr: boolean;
  risk: boolean;
  issue: boolean;
  diagrams: boolean;
  icds: boolean;
  metrics: boolean;
}

export type OptionalArtifactFeature = keyof FeatureVisibility;

/** All keys that can be stored inside optional_artifact_visibility JSON. */
export type PreferenceKey = OptionalArtifactFeature | "_hide_all_optional";

/** Subset of preference keys that represent per-feature overrides. */
export const OPTIONAL_FEATURES: readonly OptionalArtifactFeature[] = [
  "adr",
  "risk",
  "issue",
  "diagrams",
  "icds",
  "metrics",
] as const;

/** Backend response shape for GET /users/me/preferences/. */
interface PreferenceResponse {
  id: UUID;
  user_id: UUID;
  workspace_id: UUID;
  optional_artifact_visibility: Partial<Record<PreferenceKey, boolean>>;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

/** Sparse override map — only the keys the user has actually set. */
export type FeatureOverrides = Partial<FeatureVisibility>;

export const preferencesApi = {
  /**
   * Fetch the current user's preference row for the given workspace.
   * Returns ``null`` when the backend responds with 404 (no preference yet).
   *
   * ``overrides`` contains ONLY the keys the user has actually set in the
   * backend row.  Missing keys mean "fall back to the preset default";
   * callers (WorkspaceContext) implement that fallback via ``isFeatureVisible``.
   */
  async get(workspaceId: UUID): Promise<{
    overrides: FeatureOverrides;
    hideAllOptional: boolean;
  } | null> {
    let resp: PreferenceResponse;
    try {
      resp = await apiClient.get<PreferenceResponse>(
        `/users/me/preferences/?workspace_id=${encodeURIComponent(workspaceId)}`
      );
    } catch (err: unknown) {
      // 404 → no preference row yet → caller falls back to preset defaults.
      const apiErr = err as { error?: { code?: string } };
      if (apiErr?.error?.code === "NOT_FOUND") return null;
      throw err;
    }
    const v = resp.optional_artifact_visibility;
    const overrides: FeatureOverrides = {};
    for (const f of OPTIONAL_FEATURES) {
      const val = v[f];
      if (typeof val === "boolean") overrides[f] = val;
    }
    return {
      overrides,
      hideAllOptional: v._hide_all_optional === true,
    };
  },

  /**
   * Merge *visibility* into the existing preference row for the given workspace.
   * Returns the merged sparse override map plus the master flag.
   */
  async update(
    workspaceId: UUID,
    visibility: Partial<Record<PreferenceKey, boolean>>
  ): Promise<{
    overrides: FeatureOverrides;
    hideAllOptional: boolean;
  }> {
    const resp = await apiClient.patch<PreferenceResponse>(
      `/users/me/preferences/`,
      {
        workspace_id: workspaceId,
        optional_artifact_visibility: visibility,
      }
    );
    const v = resp.optional_artifact_visibility;
    const overrides: FeatureOverrides = {};
    for (const f of OPTIONAL_FEATURES) {
      const val = v[f];
      if (typeof val === "boolean") overrides[f] = val;
    }
    return {
      overrides,
      hideAllOptional: v._hide_all_optional === true,
    };
  },
};
