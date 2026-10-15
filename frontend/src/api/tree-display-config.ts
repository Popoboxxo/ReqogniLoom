/**
 * ARCH-L1-001 ReactFrontend — tree display configuration API (Issue #1257).
 *
 * leaf_id: COMP-RF-TREE-001 (shared WorkspaceTree — configurable navigation tree)
 *
 * Wraps the three routes of the navigation tree's configurable field selection.
 * The feature is three-level with precedence **user > workspace > global**:
 *
 * | Scope | Route | Who may write |
 * |-------|-------|---------------|
 * | `user` | `/api/v1/users/me/tree-display-config/` | the caller (self-service) |
 * | `workspace` | `/api/v1/workspaces/<id>/tree-display-config/` | write authority in that workspace |
 * | `global` | `/api/v1/system/tree-display-config/` | the `admin` role |
 *
 * A GET without `item_type` returns the whole `{item_type: [...]}` map plus the
 * field catalogue (what an editor needs); with `item_type` it returns that one
 * artifact type's selection. `resolve=effective` additionally asks the server to
 * walk `user > workspace > global > built-in default` and report which level
 * supplied the value — that is the read the tree itself performs, so the client
 * never re-implements the precedence.
 *
 * A `PATCH` with `fields: null` *resets* that level for the item type, so
 * resolution falls back to the next level.
 *
 * Consumed by direct import (the settings sections and
 * `hooks/useTreeDisplayFields`) and deliberately NOT re-exported from
 * `api/index.ts`, exactly like `display-preferences.ts` and `memory.ts`
 * (self-service user surfaces).
 */

import { apiClient } from "./client";

/** Which level a call reads from or writes to. */
export type TreeDisplayScope = "user" | "workspace" | "global";

/** A stored field entry: the key plus its width token. */
export interface TreeDisplayField {
  key: string;
  /** `full` spans the row, `half` shares it with a sibling. */
  width: "full" | "half";
}

/** One selectable field, as published by the server-side catalogue. */
export interface TreeDisplayCatalogEntry {
  key: string;
  /** i18n key the UI resolves before falling back to `label`. */
  label_key: string;
  /** Untranslated English fallback label. */
  label: string;
  width: "full" | "half";
  /** `true` for a built-in field, `false` for a workspace custom attribute. */
  system: boolean;
}

/** One level's stored selection for one item type (the PATCH response shape). */
export interface TreeDisplayScopePayload {
  scope: TreeDisplayScope;
  item_type: string;
  /** `null` means "nothing stored at this level" — resolution falls through. */
  fields: TreeDisplayField[] | null;
  catalog: TreeDisplayCatalogEntry[];
}

/** One level's whole stored map (the GET response shape). */
export interface TreeDisplayScopeMap {
  scope: TreeDisplayScope;
  config: Record<string, TreeDisplayField[]>;
  catalog: TreeDisplayCatalogEntry[];
}

/** The resolved selection (GET `?resolve=effective`). */
export interface TreeDisplayEffectivePayload {
  item_type: string;
  /** Which level supplied the value, or `default` for the built-in fallback. */
  scope: TreeDisplayScope | "default";
  fields: TreeDisplayField[];
  catalog: TreeDisplayCatalogEntry[];
}

export interface TreeDisplayConfigWrite {
  itemType: string;
  /** Ordered list of keys; `null` resets the level for the item type. */
  fields: string[] | TreeDisplayField[] | null;
}

const USER_PATH = "/users/me/tree-display-config/";

function pathFor(scope: TreeDisplayScope, workspaceId?: string | null): string {
  if (scope === "user") return USER_PATH;
  if (scope === "global") return "/system/tree-display-config/";
  if (!workspaceId) {
    throw new Error("The workspace tree-display scope requires a workspace_id");
  }
  return `/workspaces/${workspaceId}/tree-display-config/`;
}

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, value);
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

export const treeDisplayConfigApi = {
  /** GET one level's stored selection (whole map, or one item type). */
  async getScope(
    scope: TreeDisplayScope,
    options: { itemType?: string; workspaceId?: string | null } = {}
  ): Promise<TreeDisplayScopeMap | TreeDisplayScopePayload> {
    return apiClient.get<TreeDisplayScopeMap | TreeDisplayScopePayload>(
      pathFor(scope, options.workspaceId) +
        query({ item_type: options.itemType })
    );
  },

  /**
   * GET the *resolved* selection for `itemType`
   * (`user > workspace > global > built-in default`).
   *
   * `workspaceId` selects which route is used: with one, the workspace route
   * answers (the server checks membership, because the workspace participates);
   * without one, the personal route answers and only `user > global` apply.
   */
  async getEffective(options: {
    itemType: string;
    workspaceId?: string | null;
  }): Promise<TreeDisplayEffectivePayload> {
    const scope: TreeDisplayScope = options.workspaceId ? "workspace" : "user";
    return apiClient.get<TreeDisplayEffectivePayload>(
      pathFor(scope, options.workspaceId) +
        query({ item_type: options.itemType, resolve: "effective" })
    );
  },

  /** PATCH one level's selection for one item type (`fields: null` resets). */
  async set(
    scope: TreeDisplayScope,
    write: TreeDisplayConfigWrite,
    workspaceId?: string | null
  ): Promise<TreeDisplayScopePayload> {
    return apiClient.patch<TreeDisplayScopePayload>(
      pathFor(scope, workspaceId),
      { item_type: write.itemType, fields: write.fields }
    );
  },
};
