/**
 * ARCH-L1-001 ReactFrontend — own memory settings API (Plan A T-A1-4/T-A1-7).
 *
 * Wraps:
 *   GET /api/v1/memory/me/settings/[?workspace_id=<uuid>]
 *   PUT /api/v1/memory/me/settings/
 *
 * Self-service over the caller's own Q1 **user** level only — there is no
 * `user_id` parameter, so a foreign write is impossible by construction
 * (backend `MemorySelfServiceSettingsView`).
 *
 * `enabled` / `disabled_slots` are the *stored* user level (defaults
 * `true` / `[]`), not the merged value: a GET→PUT round-trip cannot promote a
 * tenant-global or workspace disable into the personal level.
 *
 * With `?workspace_id=` the GET answer additionally carries
 * `effective: {workspace_id, opt_out_allowed}` — the workspace-level
 * `memory.allow_user_opt_out` value, i.e. whether the personal switch is
 * honoured there. The switch is stored either way (ENT-A7 = B), so this flag
 * is the only way the UI can say "not honoured here" without a second
 * request. A caller without a role in that workspace gets 404 (never 403).
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** The workspace policy hint of `GET …?workspace_id=` (only on that request). */
export interface MemorySelfServiceEffective {
  workspace_id: string;
  /**
   * `false` = this workspace forbids the personal opt-out; the switch is
   * still stored, but workspace/artifact memory keeps being injected.
   */
  opt_out_allowed: boolean;
}

export interface MemorySelfServiceSettings {
  /** The caller's personal memory switch (user level). */
  enabled: boolean;
  /** Slots the caller personally disabled (user level, not the merged value). */
  disabled_slots: string[];
  /** Present only when the request named a workspace. */
  effective?: MemorySelfServiceEffective;
}

/**
 * Body of `PUT /memory/me/settings/` — partial (backend
 * `MemorySelfServiceSettingsWriteSerializer`): an omitted field keeps its
 * stored value, `null` resets the caller's level to the registry default.
 */
export interface MemorySelfServiceSettingsUpdate {
  enabled?: boolean | null;
  disabled_slots?: string[] | null;
}

export const memoryMeSettingsApi = {
  /**
   * GET /api/v1/memory/me/settings/ — the caller's own level. Passing
   * `workspaceId` adds the `effective` workspace-policy hint.
   */
  async get(workspaceId?: UUID): Promise<MemorySelfServiceSettings> {
    const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
    return apiClient.get<MemorySelfServiceSettings>(`/memory/me/settings/${query}`);
  },

  /**
   * PUT /api/v1/memory/me/settings/ — partial write of the caller's own
   * level. `?workspace_id=` is a GET-only display aid, so the PUT carries no
   * query and needs no membership check.
   */
  async update(update: MemorySelfServiceSettingsUpdate): Promise<MemorySelfServiceSettings> {
    return apiClient.put<MemorySelfServiceSettings>(`/memory/me/settings/`, update);
  },
};
