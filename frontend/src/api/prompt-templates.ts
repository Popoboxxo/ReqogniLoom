/**
 * ARCH-L1-001 ReactFrontend — prompt template API (REQ-L2-PT-001, issue #119).
 *
 * leaf_id: COMP-RF-001 (WorkspaceSettings — admin configuration)
 * req_id:  REQ-L2-PT-001 (Tenant-scoped editable LLM prompt templates)
 *
 * Wraps the *slot* endpoints under /api/v1/prompt-templates/slots/, which
 * expose every prompt slot the AI-derivation flows use (not just the 4 the
 * older flat /prompt-templates/ facade carried) at both the tenant-global and
 * the per-workspace scope.
 *
 *   GET    /slots/[?workspace_id=]           → every slot with its per-scope state
 *   PUT    /slots/<name>/[?workspace_id=]    → publish a new version for that scope
 *   DELETE /slots/<name>/[?workspace_id=]    → drop that scope's override
 *
 * Resolution mirrors the backend (AiDerivationService._get_template_content):
 * workspace override → tenant-global default → factory default.
 */

import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Which scope an effective prompt value came from. */
export type PromptSlotScope = "workspace" | "global" | "factory";

/** One prompt slot with its content at every scope (GET/PUT/DELETE shape). */
export interface PromptSlotState {
  /** Template name, e.g. `need_to_sysreq`. Open-ended: MCP can add names. */
  name: string;
  /** Factory text, or `null` for a name introduced at runtime via MCP. */
  factory_default: string | null;
  /** Active tenant-global content, or `null` when never customised. */
  global_content: string | null;
  global_version: number | null;
  /** Active workspace override, or `null` when the workspace inherits. */
  workspace_content: string | null;
  workspace_version: number | null;
  has_workspace_override: boolean;
  /** The content that actually applies at the requested scope. */
  effective_content: string;
  effective_scope: PromptSlotScope;
  /** Code-bound variables this slot's render call supplies. */
  data_variables: string[];
  /** Config variables the effective body actually references. */
  config_variables: string[];
  /** `{placeholders}` nothing can fill — almost certainly typos. */
  unknown_placeholders: string[];
}

/** Read shape returned by GET /prompt-templates/slots/. */
export interface PromptSlotList {
  slots: PromptSlotState[];
  count: number;
  /** Echo of the requested workspace scope (`null` = tenant-global view). */
  workspace_id: string | null;
}

/**
 * The slots that have a stable, human-labelled meaning in the UI, in the order
 * they are presented. Any further slot the backend reports (e.g. a template
 * created under a custom name via MCP) is rendered after these, so the UI
 * never silently hides an editable template.
 */
export const KNOWN_PROMPT_SLOTS: readonly string[] = [
  "need_to_sysreq",
  "sysreq_to_arch_assign",
  "sysreq_decompose_next_level",
  "goal_aggregate",
  "testcase_derive",
  "architecture_to_risk",
  "workspace_to_glossary",
  "decision_to_adr",
] as const;

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

/** Build the `?workspace_id=` suffix for a scope (empty for tenant-global). */
function scopeQuery(workspaceId?: string | null): string {
  return workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
}

export const promptTemplatesApi = {
  /**
   * List every prompt slot. Pass a `workspaceId` to also resolve that
   * workspace's overrides; omit it for the tenant-global view only.
   */
  async listSlots(workspaceId?: string | null): Promise<PromptSlotList> {
    return apiClient.get<PromptSlotList>(
      `/prompt-templates/slots/${scopeQuery(workspaceId)}`
    );
  },

  /**
   * Publish a new version of `name` for the given scope. Omitting
   * `workspaceId` writes the tenant-global default instead of an override.
   */
  async saveSlot(
    name: string,
    content: string,
    workspaceId?: string | null
  ): Promise<PromptSlotState> {
    return apiClient.put<PromptSlotState>(
      `/prompt-templates/slots/${encodeURIComponent(name)}/${scopeQuery(workspaceId)}`,
      { content }
    );
  },

  /**
   * Drop `name`'s override at the given scope. Clearing a workspace scope
   * restores the tenant-global default; clearing the tenant-global scope
   * restores the factory text. Returns the now-effective state.
   */
  async clearSlot(
    name: string,
    workspaceId?: string | null
  ): Promise<PromptSlotState> {
    return apiClient.delete<PromptSlotState>(
      `/prompt-templates/slots/${encodeURIComponent(name)}/${scopeQuery(workspaceId)}`
    );
  },
};
