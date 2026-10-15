/**
 * ARCH-L1-001 ReactFrontend — create-dialog form configuration API (Issue #1263).
 *
 * leaf_id: COMP-RF-FORM-001 (shared ArtifactForm — configurable create dialog)
 *
 * Wraps the three routes of the "new artifact" dialog's configurable form
 * definition. The feature is three-level with precedence
 * **user > workspace > global** and per artifact type, exactly like the
 * Attribute-v3 inheritance and the #1257 navigation-tree configuration:
 *
 * | Scope | Route | Who may write |
 * |-------|-------|---------------|
 * | `user` | `/api/v1/users/me/create-form-config/` | the caller (self-service) |
 * | `workspace` | `/api/v1/workspaces/<id>/create-form-config/` | write authority in that workspace |
 * | `global` | `/api/v1/system/create-form-config/` | the `admin` role |
 *
 * A GET without `item_type` returns the whole `{item_type: [...]}` map; with
 * `item_type` it returns that one artifact type's stored selection plus the
 * definition-derived `catalog` (the configurable fields) an editor overlays.
 * `resolve=effective` walks `user > workspace > global > definition default` and
 * reports which level supplied the value — the read the create dialog itself
 * performs, so the client never re-implements the precedence.
 *
 * A `PATCH` with `fields: null` *resets* that level for the item type, so
 * resolution falls back to the next level.
 *
 * Consumed by direct import (the settings sections and
 * `hooks/useCreateFormFields`) and deliberately NOT re-exported from
 * `api/index.ts`, exactly like `tree-display-config.ts` (#1257).
 */

import { apiClient } from "./client";

/** Which level a call reads from or writes to. */
export type CreateFormScope = "user" | "workspace" | "global";

/** One resolved form field: what the create dialog renders, and how. */
export interface CreateFormFieldEntry {
  /** Attribute name from the resolved Attribute-v3 definition. */
  field_key: string;
  /** `false` hides the field from the create dialog. */
  visible: boolean;
  /** `true` demands a value on create (server-enforced, not only in the UI). */
  required: boolean;
  /** Sort position within the dialog. */
  order: number;
  /** Value pre-filled when the create payload omits the field. */
  default: unknown;
}

/** The level a resolved selection came from (GET `?resolve=effective`). */
export interface CreateFormEffectivePayload {
  item_type: string;
  /** Which level supplied the value, or `default` for the definition fallback. */
  scope: CreateFormScope | "default";
  fields: CreateFormFieldEntry[];
  /** The definition-derived configurable fields (base entries). */
  catalog: CreateFormFieldEntry[];
}

/** One level's stored selection for one item type (the PATCH response shape). */
export interface CreateFormScopePayload {
  scope: CreateFormScope;
  item_type?: string;
  /** `null` means "nothing stored at this level" — resolution falls through. */
  fields?: CreateFormFieldEntry[] | null;
  catalog: CreateFormFieldEntry[];
  /** Whole-`{item_type: [...]}` map, present on a GET without `item_type`. */
  config?: Record<string, CreateFormFieldEntry[]>;
}

export interface CreateFormConfigWrite {
  itemType: string;
  /** Ordered entries; `null` resets the level for the item type. */
  fields: CreateFormFieldEntry[] | null;
}

const USER_PATH = "/users/me/create-form-config/";

function pathFor(scope: CreateFormScope, workspaceId?: string | null): string {
  if (scope === "user") return USER_PATH;
  if (scope === "global") return "/system/create-form-config/";
  if (!workspaceId) {
    throw new Error("The workspace create-form scope requires a workspace_id");
  }
  return `/workspaces/${workspaceId}/create-form-config/`;
}

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, value);
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

export const createFormConfigApi = {
  /** GET one level's stored selection (whole map, or one item type). */
  async getScope(
    scope: CreateFormScope,
    options: { itemType?: string; workspaceId?: string | null } = {}
  ): Promise<CreateFormScopePayload> {
    return apiClient.get<CreateFormScopePayload>(
      pathFor(scope, options.workspaceId) + query({ item_type: options.itemType })
    );
  },

  /**
   * GET the *resolved* selection for `itemType`
   * (`user > workspace > global > definition default`).
   *
   * With a `workspaceId`, the workspace route answers (the server checks
   * membership, because the workspace level participates); without one, the
   * personal route answers and only `user > global` apply.
   */
  async getEffective(options: {
    itemType: string;
    workspaceId?: string | null;
  }): Promise<CreateFormEffectivePayload> {
    const scope: CreateFormScope = options.workspaceId ? "workspace" : "user";
    return apiClient.get<CreateFormEffectivePayload>(
      pathFor(scope, options.workspaceId) +
        query({ item_type: options.itemType, resolve: "effective" })
    );
  },

  /** PATCH one level's selection for one item type (`fields: null` resets). */
  async set(
    scope: CreateFormScope,
    write: CreateFormConfigWrite,
    workspaceId?: string | null
  ): Promise<CreateFormScopePayload> {
    return apiClient.patch<CreateFormScopePayload>(
      pathFor(scope, workspaceId),
      { item_type: write.itemType, fields: write.fields }
    );
  },
};
