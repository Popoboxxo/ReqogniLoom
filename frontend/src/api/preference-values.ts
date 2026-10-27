/**
 * ARCH-L1-001 ReactFrontend — Q1 three-level preference values (Plan C, T-C2-5).
 *
 * Wraps the six preference routes of the generic preference service
 * (`backend/rest_api/preference_value_views.py`). One key is stored at up to
 * three levels and resolved **user > workspace > global > registry default**:
 *
 * | Scope | Level route | Effective route |
 * |-------|-------------|-----------------|
 * | `user` | `/api/v1/users/me/preference-values/` | `/api/v1/users/me/preference-values/effective/` |
 * | `workspace` | `/api/v1/workspaces/<id>/preference-values/` | `/api/v1/workspaces/<id>/preference-values/effective/` |
 * | `global` | `/api/v1/system/preference-values/` | (covered by the personal effective read) |
 *
 * Two different reads, deliberately kept apart:
 *
 * - **level** (`getLevel` / `patchLevel`) answers "what does *this* level
 *   store". An absent key means "inherit", never "empty".
 * - **effective** (`effective`) answers "what does the caller actually get, and
 *   which level supplied it" (`source`). The settings sections use it for the
 *   inherited hint; the level payload is what decides whether a key is set
 *   here, because `source` alone can report a level above this one (a personal
 *   override sits above the workspace level).
 *
 * `patchLevel` sends `{"values": {<key>: <value> | null}}`; `null` **resets**
 * the key at that level (the server deletes the row), so it must survive the
 * JSON body unchanged. The PATCH is atomic server-side: one rejected key means
 * nothing was written.
 *
 * The registry (`registry`) names every key this build knows plus its type,
 * default, allowed levels and `ui_editor` rendering hint — the generic settings
 * section renders from it instead of hard-coding keys.
 *
 * Consumed by direct import (the settings sections and `queries/preferences`)
 * and deliberately NOT re-exported from `api/index.ts`, exactly like
 * `display-preferences.ts` and `memory.ts` (self-service user surfaces).
 */

import { apiClient } from "./client";

/** Which level a call reads from or writes to. */
export type PreferenceScope = "user" | "workspace" | "global";

/** Where an effective value came from (`merged` = a `union`-mode key). */
export type PreferenceSource =
  | "user"
  | "workspace"
  | "global"
  | "default"
  | "merged";

/** The value shapes a registered key can carry. */
export type PreferenceValueType = "bool" | "enum" | "str_list";

/** Generic settings-section editor; `null` = the key has a dedicated UI. */
export type PreferenceUiEditor = "checkbox" | "select" | null;

/** One registry entry — everything the generic section needs to render a key. */
export interface PreferenceKeySpec {
  key: string;
  type: PreferenceValueType;
  /** Allowed `enum` / `str_list` values; `null` = unconstrained. */
  choices: string[] | null;
  /** Registry default, used when no level is set. */
  default: unknown;
  /** Levels that may carry this key. */
  levels: PreferenceScope[];
  /** `override` = highest set level wins; `union` = levels merge. */
  mode: "override" | "union";
  ui_editor: PreferenceUiEditor;
}

/** One resolved key: its effective value and the level that supplied it. */
export interface EffectivePreference {
  value: unknown;
  source: PreferenceSource;
}

/** Body of both `…/effective/` reads. */
export interface PreferenceEffective {
  /** `null` on the account-wide read. */
  workspace_id: string | null;
  values: Record<string, EffectivePreference>;
}

/** Body of the three level routes: only the keys actually set there. */
export interface PreferenceLevel {
  scope: PreferenceScope;
  workspace_id: string | null;
  values: Record<string, unknown>;
}

export interface PreferenceRegistry {
  keys: PreferenceKeySpec[];
}

const USER_PATH = "/users/me/preference-values/";
const GLOBAL_PATH = "/system/preference-values/";

/** The level route for `scope`; the workspace scope cannot guess its id. */
function levelPath(scope: PreferenceScope, workspaceId?: string): string {
  if (scope === "user") return USER_PATH;
  if (scope === "global") return GLOBAL_PATH;
  if (!workspaceId) {
    throw new Error("The workspace preference scope requires a workspace_id");
  }
  return `/workspaces/${workspaceId}/preference-values/`;
}

export const preferenceValuesApi = {
  /** GET the key catalogue (metadata only; every member may read it). */
  async registry(): Promise<PreferenceRegistry> {
    return apiClient.get<PreferenceRegistry>("/preference-values/registry/");
  },

  /**
   * GET the resolved values for the caller.
   *
   * With a `workspaceId` the workspace route answers
   * (`user > workspace > global > default`); without one the account-wide read
   * answers (`user > global > default`) and `workspace_id` is `null`.
   */
  async effective(workspaceId?: string | null): Promise<PreferenceEffective> {
    const path = workspaceId
      ? `/workspaces/${workspaceId}/preference-values/effective/`
      : "/users/me/preference-values/effective/";
    return apiClient.get<PreferenceEffective>(path);
  },

  /** GET one level's stored values (absent key = inherit, not empty). */
  async getLevel(
    scope: PreferenceScope,
    workspaceId?: string
  ): Promise<PreferenceLevel> {
    return apiClient.get<PreferenceLevel>(levelPath(scope, workspaceId));
  },

  /**
   * PATCH one level. `null` per key resets it (delete the row), so the next
   * lower level takes over again. Returns the level's fresh stored values.
   */
  async patchLevel(
    scope: PreferenceScope,
    values: Record<string, unknown | null>,
    workspaceId?: string
  ): Promise<PreferenceLevel> {
    return apiClient.patch<PreferenceLevel>(levelPath(scope, workspaceId), {
      values,
    });
  },
};
