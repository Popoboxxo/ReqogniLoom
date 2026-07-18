/**
 * ARCH-L1-001 ReactFrontend — Global Workflow Defaults API (REQ-178/179).
 *
 * leaf_id: COMP-RF-001 (NavigationShell — System Settings scope)
 *
 * Wraps the tenant-wide, per-(item_type, preset) global workflow definition
 * endpoints under ``/api/v1/workflow-defaults/`` (see
 * docs/api/workflow-permissions-global-default.openapi.yaml). Mirrors the
 * workspace-scoped ``workflowsApi`` (REQ-176/177) verbatim so the existing
 * ``WorkflowEditorPage`` composition can be reused in ``scope="global"`` mode
 * without a second graph editor — the response shapes are structurally
 * compatible (``WorkflowGraphGlobal`` is a superset-minus-overrides of the
 * workspace graph the derivation already consumes).
 *
 * Contract note: the OpenAPI state/transition mutation responses are typed as
 * ``WorkflowGraphGlobal`` (no ``propagated_workspace_count`` field), yet the UI
 * spec (§SCR-205) asks to surface the propagation count when a global edit
 * ripples into on-default workspaces. These wrappers therefore read the count
 * defensively as an OPTIONAL field: when the backend includes it, the caller
 * toasts it; when absent, the mutation still succeeds silently. See the handoff
 * note for this intentional tolerance.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";
import type { WorkspacePreset } from "../types";
import {
  toWorkflowGraph,
  type WorkflowDefinitionGraph,
  type WorkflowEntityType,
  type WorkflowGraph,
} from "./workflows";

/** Raw global-definition payload (WorkflowGraphGlobal, OpenAPI). */
export interface GlobalWorkflowDefinitionGraph {
  scope: "global";
  tenant_id: UUID;
  item_type: string;
  preset: WorkspacePreset;
  initialized: boolean;
  initial_state: string | null;
  states: string[];
  transitions: WorkflowDefinitionGraph["transitions"];
  updated_at?: string | null;
  /** Optional per contract-tolerance note — surfaced as a toast when present. */
  propagated_workspace_count?: number;
}

/** A derived editor graph plus the optional propagation count of a mutation. */
export interface GlobalWorkflowMutationResult {
  graph: WorkflowGraph;
  propagatedWorkspaceCount?: number;
}

/**
 * Adapt a global payload into the workspace-shaped ``WorkflowDefinitionGraph``
 * the editor's derivation (``toWorkflowGraph``) already consumes. The global
 * resource has no ``is_custom`` (legacy Extended-only flag) — it is always
 * ``false`` for a global default.
 */
function toDefinitionGraph(
  raw: GlobalWorkflowDefinitionGraph
): WorkflowDefinitionGraph {
  return {
    item_type: raw.item_type,
    preset: raw.preset,
    is_custom: false,
    initial_state: raw.initial_state,
    initialized: raw.initialized,
    states: raw.states,
    transitions: raw.transitions,
  };
}

function toResult(
  entityType: WorkflowEntityType,
  raw: GlobalWorkflowDefinitionGraph
): GlobalWorkflowMutationResult {
  return {
    graph: toWorkflowGraph(entityType, toDefinitionGraph(raw)),
    propagatedWorkspaceCount:
      typeof raw.propagated_workspace_count === "number"
        ? raw.propagated_workspace_count
        : undefined,
  };
}

function basePath(entityType: WorkflowEntityType, preset: WorkspacePreset): string {
  return `/workflow-defaults/${encodeURIComponent(entityType)}/${encodeURIComponent(
    preset
  )}`;
}

export const workflowDefaultsApi = {
  /**
   * GET /api/v1/workflow-defaults/{item_type}/{preset}/ — the full global state
   * machine. Returns ``initialized: false`` with empty states when the row does
   * not exist yet (never 404), so the UI can offer an "Initialize" affordance.
   */
  async getGraph(
    entityType: WorkflowEntityType,
    preset: WorkspacePreset
  ): Promise<WorkflowGraph> {
    const raw = await apiClient.get<GlobalWorkflowDefinitionGraph>(
      `${basePath(entityType, preset)}/`
    );
    return toWorkflowGraph(entityType, toDefinitionGraph(raw));
  },

  async initialize(
    entityType: WorkflowEntityType,
    preset: WorkspacePreset
  ): Promise<GlobalWorkflowMutationResult> {
    const raw = await apiClient.post<GlobalWorkflowDefinitionGraph>(
      `${basePath(entityType, preset)}/initialize/`,
      {}
    );
    return toResult(entityType, raw);
  },

  async createState(
    entityType: WorkflowEntityType,
    preset: WorkspacePreset,
    name: string
  ): Promise<GlobalWorkflowMutationResult> {
    const raw = await apiClient.post<GlobalWorkflowDefinitionGraph>(
      `${basePath(entityType, preset)}/states/`,
      { name }
    );
    return toResult(entityType, raw);
  },

  async updateState(
    entityType: WorkflowEntityType,
    preset: WorkspacePreset,
    oldName: string,
    newName: string
  ): Promise<GlobalWorkflowMutationResult> {
    const raw = await apiClient.patch<GlobalWorkflowDefinitionGraph>(
      `${basePath(entityType, preset)}/states/${encodeURIComponent(oldName)}/`,
      { name: newName }
    );
    return toResult(entityType, raw);
  },

  async deleteState(
    entityType: WorkflowEntityType,
    preset: WorkspacePreset,
    name: string
  ): Promise<GlobalWorkflowMutationResult> {
    const raw = await apiClient.delete<GlobalWorkflowDefinitionGraph>(
      `${basePath(entityType, preset)}/states/${encodeURIComponent(name)}/`
    );
    return toResult(entityType, raw);
  },

  async createTransition(
    entityType: WorkflowEntityType,
    preset: WorkspacePreset,
    payload: {
      from_state: string;
      to_state: string;
      allowed_roles?: string[];
      requires_change_reason?: boolean;
      signature_gate?: boolean;
    }
  ): Promise<GlobalWorkflowMutationResult> {
    const raw = await apiClient.post<GlobalWorkflowDefinitionGraph>(
      `${basePath(entityType, preset)}/transitions/`,
      payload
    );
    return toResult(entityType, raw);
  },

  async updateTransition(
    entityType: WorkflowEntityType,
    preset: WorkspacePreset,
    fromState: string,
    toState: string,
    patch: {
      allowed_roles?: string[];
      requires_change_reason?: boolean;
      signature_gate?: boolean;
    }
  ): Promise<GlobalWorkflowMutationResult> {
    const id = `${fromState}__${toState}`;
    const raw = await apiClient.patch<GlobalWorkflowDefinitionGraph>(
      `${basePath(entityType, preset)}/transitions/${encodeURIComponent(id)}/`,
      patch
    );
    return toResult(entityType, raw);
  },

  async deleteTransition(
    entityType: WorkflowEntityType,
    preset: WorkspacePreset,
    fromState: string,
    toState: string
  ): Promise<GlobalWorkflowMutationResult> {
    const id = `${fromState}__${toState}`;
    const raw = await apiClient.delete<GlobalWorkflowDefinitionGraph>(
      `${basePath(entityType, preset)}/transitions/${encodeURIComponent(id)}/`
    );
    return toResult(entityType, raw);
  },
};
