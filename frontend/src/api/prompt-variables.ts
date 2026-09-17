/**
 * ARCH-L1-001 ReactFrontend — prompt variable catalog API (spec §3.1, §5).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001 (Tenant-scoped editable LLM prompt configuration)
 *
 * Wraps the catalog endpoints, which mirror the prompt-template slot API's
 * scope semantics exactly:
 *
 *   GET    /prompt-variables/[?workspace_id=]        → every variable + state
 *   PUT    /prompt-variables/<name>/[?workspace_id=] → publish a new version
 *   DELETE /prompt-variables/<name>/[?workspace_id=] → drop that scope's row
 *
 * Resolution mirrors the backend resolver: workspace override → tenant
 * default → factory value.
 */

import { apiClient } from "./client";

/** Whether a variable is admin-editable config or code-bound data. */
export type PromptVariableKind = "config" | "data";

/** How the stored value is typed. */
export type PromptVariableType = "int" | "str" | "bool" | "json";

/** Which scope an effective variable value came from. */
export type PromptVariableScope = "workspace" | "global" | "factory";

/** One catalog variable with its value at every scope. */
export interface PromptVariableState {
  /** Placeholder name as used in prompt bodies, i.e. `{name}`. */
  name: string;
  kind: PromptVariableKind;
  var_type: PromptVariableType;
  description: string;
  /** Factory value, or `null` for a variable created at runtime. */
  factory_default: unknown;
  /** Active tenant-wide value, or `null` when never customised. */
  global_value: unknown;
  global_version: number | null;
  /** Active workspace override, or `null` when the workspace inherits. */
  workspace_value: unknown;
  workspace_version: number | null;
  has_workspace_override: boolean;
  /** The value that actually applies at the requested scope. */
  effective_value: unknown;
  effective_scope: PromptVariableScope;
  /** False for `kind: "data"` — those are documentation only. */
  is_editable: boolean;
}

/** Read shape returned by GET /prompt-variables/. */
export interface PromptVariableList {
  variables: PromptVariableState[];
  count: number;
  /** Echo of the requested workspace scope (`null` = tenant-global view). */
  workspace_id: string | null;
}

/** Extra fields only needed when introducing a brand-new variable. */
export interface SaveVariableOptions {
  varType?: PromptVariableType;
  description?: string;
}

/** Build the `?workspace_id=` suffix for a scope (empty for tenant-global). */
function scopeQuery(workspaceId?: string | null): string {
  return workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
}

export const promptVariablesApi = {
  /**
   * List every catalog variable. Pass a `workspaceId` to also resolve that
   * workspace's overrides; omit it for the tenant-global view only.
   */
  async list(workspaceId?: string | null): Promise<PromptVariableList> {
    return apiClient.get<PromptVariableList>(
      `/prompt-variables/${scopeQuery(workspaceId)}`
    );
  },

  /**
   * Publish a new version of `name` for the given scope. Omitting
   * `workspaceId` writes the tenant-wide default instead of an override.
   * `options` only matters for a name the backend has no factory entry for.
   */
  async save(
    name: string,
    value: unknown,
    workspaceId?: string | null,
    options: SaveVariableOptions = {}
  ): Promise<PromptVariableState> {
    const body: Record<string, unknown> = { value };
    if (options.varType !== undefined) body.var_type = options.varType;
    if (options.description !== undefined) body.description = options.description;
    return apiClient.put<PromptVariableState>(
      `/prompt-variables/${encodeURIComponent(name)}/${scopeQuery(workspaceId)}`,
      body
    );
  },

  /**
   * Drop `name`'s row at the given scope. Clearing a workspace scope restores
   * the tenant default; clearing the tenant scope restores the factory value.
   * Returns the now-effective state.
   */
  async clear(
    name: string,
    workspaceId?: string | null
  ): Promise<PromptVariableState> {
    return apiClient.delete<PromptVariableState>(
      `/prompt-variables/${encodeURIComponent(name)}/${scopeQuery(workspaceId)}`
    );
  },
};
