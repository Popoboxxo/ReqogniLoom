/**
 * ARCH-L1-001 ReactFrontend — Workflows API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings scope)
 * req_id:  REQ-L2-RA-001 (WorkflowDefinition endpoints)
 *
 * Wraps /api/v1/workflows/ (WorkflowDefinitionViewSet).
 *
 * Backend contract notes (rest_api/views.py::WorkflowDefinitionViewSet):
 *   - GET  /workflows/           always returns an empty result set — the
 *     WorkflowFacade does not expose a list operation. The client keeps the
 *     call for forward-compatibility.
 *   - POST /workflows/           initializes workflow states for an artifact
 *     ({workspace_id, artifact_id, name}) → 201 {"message": ...}
 *   - PATCH /workflows/<id>/     performs a state transition on the entity
 *     ({target_state, change_reason?}) → 200 {"id", "target_state"}
 *   - DELETE                     always 403 (definitions cannot be deleted).
 */

import { apiClient, extractErrorMessage, getList } from "./client";
import { ForbiddenError } from "./errors";
import type { PaginatedResponse, UUID } from "../types";

/**
 * Turn any thrown workflow-mutation error into a human-readable message
 * (REQ-177). ``ForbiddenError`` (403 — preset gate / missing admin role)
 * carries its message directly; every other ``ApiError`` (409 conflict, 400
 * validation) is unwrapped by ``extractErrorMessage``.
 */
export function extractWorkflowError(err: unknown): string {
  if (err instanceof ForbiddenError) return err.message;
  return extractErrorMessage(err);
}

export interface WorkflowDefinition {
  id: UUID;
  workspace_id: UUID;
  artifact_id: UUID;
  name: string;
  version: number;
  created_at: string;
}

export interface WorkflowTransitionResult {
  id: string;
  target_state: string;
}

// ---------------------------------------------------------------------------
// REQ-176 — Full workflow-graph read model (Workflow Editor, Phase 1).
//
// The instance-scoped ``/{resource}/{id}/transitions/`` endpoint only returns
// the moves allowed from ONE item's current state. The editor needs the whole
// state machine, so it reads the dedicated
// ``GET /api/v1/workflows/definition/?workspace_id&item_type`` endpoint
// (WorkflowDefinitionViewSet.definition) which returns every state and every
// transition with its role / change_reason / signature metadata.
// ---------------------------------------------------------------------------

/**
 * Entity types the Workflow Editor can visualise. The value is the backend
 * ``workflow_item_type`` string (see the ViewSet declarations in
 * ``backend/rest_api/views.py``), so it maps 1:1 onto the ``item_type`` query
 * parameter of the definition endpoint.
 */
export type WorkflowEntityType =
  | "Requirement"
  | "StakeholderNeed"
  | "ArchitectureElement"
  | "Adr"
  | "Risk"
  | "TestCase"
  | "Issue";

/** Derived visual classification of a state (not stored server-side). */
export type WorkflowStateType = "initial" | "active" | "terminal" | "error";

/** A single transition of the raw backend definition payload. */
export interface WorkflowDefinitionTransition {
  from_state: string;
  to_state: string;
  allowed_roles: string[];
  requires_change_reason: boolean;
  signature_gate: boolean;
}

/** Raw response of GET /api/v1/workflows/definition/. */
export interface WorkflowDefinitionGraph {
  item_type: string;
  preset: string | null;
  is_custom: boolean;
  initial_state: string | null;
  initialized: boolean;
  states: string[];
  transitions: WorkflowDefinitionTransition[];
}

/** A state ready for the editor: raw name plus derived type + counts. */
export interface WorkflowState {
  /** Stable id — the state name is unique within a machine. */
  id: string;
  name: string;
  type: WorkflowStateType;
  description?: string;
  outgoingCount: number;
  incomingCount: number;
  isInitial: boolean;
}

/** A transition ready for the editor: derived id/name plus rule metadata. */
export interface WorkflowTransition {
  /** Stable id derived from the endpoints — unique per (from, to) pair. */
  id: string;
  name: string;
  from_state: string;
  to_state: string;
  change_reason_required: boolean;
  required_role?: string;
  /** True when a signature gate guards this transition (guard indicator). */
  signature_gate: boolean;
}

/** Fully-derived editor model for one entity type's workflow. */
export interface WorkflowGraph {
  entityType: WorkflowEntityType;
  preset: string | null;
  isCustom: boolean;
  initialized: boolean;
  states: WorkflowState[];
  transitions: WorkflowTransition[];
}

// Case-insensitive name fragments that mark a state as an error/terminal-failure
// state (no dedicated "error" type exists in the backend model — REQ-176).
const ERROR_STATE_PATTERN = /(reject|error|fail|cancel|wontfix|abort)/i;

/** Derive the visual state type from the graph topology and naming. */
function deriveStateType(
  name: string,
  initialState: string | null,
  hasOutgoing: boolean
): WorkflowStateType {
  if (name === initialState) return "initial";
  if (ERROR_STATE_PATTERN.test(name)) return "error";
  if (!hasOutgoing) return "terminal";
  return "active";
}

/**
 * Turn the raw backend definition payload into the editor's derived
 * ``WorkflowGraph``: classify each state, count in/out edges, and synthesise
 * transition ids/names (the backend model has no transition names — the label
 * is derived as ``from → to``).
 */
export function toWorkflowGraph(
  entityType: WorkflowEntityType,
  raw: WorkflowDefinitionGraph
): WorkflowGraph {
  const outgoing = new Map<string, number>();
  const incoming = new Map<string, number>();
  for (const t of raw.transitions) {
    outgoing.set(t.from_state, (outgoing.get(t.from_state) ?? 0) + 1);
    incoming.set(t.to_state, (incoming.get(t.to_state) ?? 0) + 1);
  }

  const states: WorkflowState[] = raw.states.map((name) => {
    const outgoingCount = outgoing.get(name) ?? 0;
    return {
      id: name,
      name,
      type: deriveStateType(name, raw.initial_state, outgoingCount > 0),
      outgoingCount,
      incomingCount: incoming.get(name) ?? 0,
      isInitial: name === raw.initial_state,
    };
  });

  const transitions: WorkflowTransition[] = raw.transitions.map((t) => ({
    id: `${t.from_state}__${t.to_state}`,
    name: `${t.from_state} → ${t.to_state}`,
    from_state: t.from_state,
    to_state: t.to_state,
    change_reason_required: t.requires_change_reason,
    required_role: t.allowed_roles.length ? t.allowed_roles.join(", ") : undefined,
    signature_gate: t.signature_gate,
  }));

  return {
    entityType,
    preset: raw.preset,
    isCustom: raw.is_custom,
    initialized: raw.initialized,
    states,
    transitions,
  };
}

export const workflowsApi = {
  /** GET /api/v1/workflows/ — currently always empty (see contract notes). */
  list(workspaceId: UUID): Promise<PaginatedResponse<WorkflowDefinition>> {
    return getList<WorkflowDefinition>("/workflows/", {
      workspace_id: workspaceId,
    });
  },

  /**
   * GET /api/v1/workflows/definition/ — the FULL state machine for an entity
   * type (REQ-176). Returns every state and transition (with role /
   * change_reason / signature metadata) so the Workflow Editor can render the
   * whole graph. When no workflow is configured, ``initialized`` is false and
   * ``states``/``transitions`` are empty.
   */
  getDefinition(
    entityType: WorkflowEntityType,
    workspaceId: UUID
  ): Promise<WorkflowDefinitionGraph> {
    const qs = new URLSearchParams({
      workspace_id: workspaceId,
      item_type: entityType,
    }).toString();
    return apiClient.get<WorkflowDefinitionGraph>(
      `/workflows/definition/?${qs}`
    );
  },

  /**
   * Convenience wrapper: fetch a definition and derive the editor's
   * ``WorkflowGraph`` (state classification, edge counts, transition labels).
   */
  async getGraph(
    entityType: WorkflowEntityType,
    workspaceId: UUID
  ): Promise<WorkflowGraph> {
    const raw = await workflowsApi.getDefinition(entityType, workspaceId);
    return toWorkflowGraph(entityType, raw);
  },

  /** POST /api/v1/workflows/ — initialize workflow states for an artifact. */
  initialize(data: {
    workspace_id: UUID;
    artifact_id: UUID;
    name: string;
  }): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>("/workflows/", data);
  },

  // -------------------------------------------------------------------------
  // REQ-177 — Edit-mode mutations (Workflow Editor Phase 2).
  //
  // State identity is the state NAME; transition identity is the
  // ``<from>__<to>`` pair (matching ``toWorkflowGraph``'s derived ids). Every
  // mutation returns the full, re-derived ``WorkflowGraph`` so the caller can
  // refresh the canvas from one round-trip. Backend validation errors (409
  // conflict on delete-with-references, 400 duplicate/empty, 403 preset gate)
  // surface as thrown ``ApiError``/``ForbiddenError`` — use
  // ``extractWorkflowError`` to render them.
  // -------------------------------------------------------------------------

  async createState(
    entityType: WorkflowEntityType,
    workspaceId: UUID,
    name: string
  ): Promise<WorkflowGraph> {
    const raw = await apiClient.post<WorkflowDefinitionGraph>(
      "/workflows/definition/states/",
      { workspace_id: workspaceId, item_type: entityType, name }
    );
    return toWorkflowGraph(entityType, raw);
  },

  async updateState(
    entityType: WorkflowEntityType,
    workspaceId: UUID,
    oldName: string,
    newName: string
  ): Promise<WorkflowGraph> {
    const raw = await apiClient.patch<WorkflowDefinitionGraph>(
      `/workflows/definition/states/${encodeURIComponent(oldName)}/`,
      { workspace_id: workspaceId, item_type: entityType, name: newName }
    );
    return toWorkflowGraph(entityType, raw);
  },

  async deleteState(
    entityType: WorkflowEntityType,
    workspaceId: UUID,
    name: string
  ): Promise<WorkflowGraph> {
    const qs = new URLSearchParams({
      workspace_id: workspaceId,
      item_type: entityType,
    }).toString();
    const raw = await apiClient.delete<WorkflowDefinitionGraph>(
      `/workflows/definition/states/${encodeURIComponent(name)}/?${qs}`
    );
    return toWorkflowGraph(entityType, raw);
  },

  async createTransition(
    entityType: WorkflowEntityType,
    workspaceId: UUID,
    payload: {
      from_state: string;
      to_state: string;
      allowed_roles?: string[];
      requires_change_reason?: boolean;
      signature_gate?: boolean;
    }
  ): Promise<WorkflowGraph> {
    const raw = await apiClient.post<WorkflowDefinitionGraph>(
      "/workflows/definition/transitions/",
      { workspace_id: workspaceId, item_type: entityType, ...payload }
    );
    return toWorkflowGraph(entityType, raw);
  },

  async updateTransition(
    entityType: WorkflowEntityType,
    workspaceId: UUID,
    fromState: string,
    toState: string,
    patch: {
      allowed_roles?: string[];
      requires_change_reason?: boolean;
      signature_gate?: boolean;
    }
  ): Promise<WorkflowGraph> {
    const id = `${fromState}__${toState}`;
    const raw = await apiClient.patch<WorkflowDefinitionGraph>(
      `/workflows/definition/transitions/${encodeURIComponent(id)}/`,
      { workspace_id: workspaceId, item_type: entityType, ...patch }
    );
    return toWorkflowGraph(entityType, raw);
  },

  async deleteTransition(
    entityType: WorkflowEntityType,
    workspaceId: UUID,
    fromState: string,
    toState: string
  ): Promise<WorkflowGraph> {
    const id = `${fromState}__${toState}`;
    const qs = new URLSearchParams({
      workspace_id: workspaceId,
      item_type: entityType,
    }).toString();
    const raw = await apiClient.delete<WorkflowDefinitionGraph>(
      `/workflows/definition/transitions/${encodeURIComponent(id)}/?${qs}`
    );
    return toWorkflowGraph(entityType, raw);
  },

  async initializeWorkflow(
    entityType: WorkflowEntityType,
    workspaceId: UUID
  ): Promise<WorkflowGraph> {
    const raw = await apiClient.post<WorkflowDefinitionGraph>(
      "/workflows/definition/initialize/",
      { workspace_id: workspaceId, item_type: entityType }
    );
    return toWorkflowGraph(entityType, raw);
  },

  /** PATCH /api/v1/workflows/<entityId>/ — transition an entity's state. */
  transition(
    entityId: UUID,
    targetState: string,
    changeReason?: string
  ): Promise<WorkflowTransitionResult> {
    return apiClient.patch<WorkflowTransitionResult>(`/workflows/${entityId}/`, {
      target_state: targetState,
      change_reason: changeReason ?? "",
    });
  },
};
