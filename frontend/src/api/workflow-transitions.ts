/**
 * ARCH-L1-001 ReactFrontend — Generic Workflow Transitions API.
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-161 (Unified Workflow Status Editor)
 *
 * A single, artifact-type-agnostic wrapper over the ``/{resource}/{id}/transitions/``
 * WorkflowEngine endpoints so every artifact form drives its lifecycle through the
 * same WorkflowFacade contract instead of hardcoded status selects (REQ-160/161).
 *
 * Backend contract (rest_api/views.py — RequirementViewSet.transitions is the
 * reference implementation):
 *   GET  /{resource}/{id}/transitions/
 *       → {current_state, states, allowed_transitions[]}
 *   POST /{resource}/{id}/transitions/
 *       body: {target_state, change_reason?, credential?}
 *       → {id, previous_state, new_state, ...}
 *
 * Only the ``requirement`` endpoint exists today; the other resource paths are
 * declared for forward-compatibility. Until a given endpoint lands, its GET
 * resolves to a 404 which the WorkflowStatusEditor degrades to a read-only
 * "workflow not initialized" view.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** Artifact types that participate in the WorkflowEngine lifecycle. */
export type WorkflowArtifactType =
  | "requirement"
  | "need"
  | "adr"
  | "test-case"
  | "risk"
  | "issue";

/** A single allowed transition from the current state. */
export interface WorkflowAllowedTransition {
  target_state: string;
  requires_change_reason: boolean;
  signature_gate: boolean;
}

/** Response of GET /{resource}/{id}/transitions/. */
export interface WorkflowTransitionsResponse {
  current_state: string | null;
  states: string[];
  allowed_transitions: WorkflowAllowedTransition[];
}

/** Response of POST /{resource}/{id}/transitions/. */
export interface WorkflowTransitionResult {
  id: string;
  previous_state: string;
  new_state: string;
}

/** Maps the artifact type to its REST collection path segment. */
const RESOURCE_PATH: Record<WorkflowArtifactType, string> = {
  requirement: "requirements",
  need: "needs",
  adr: "adrs",
  "test-case": "test-cases",
  risk: "risks",
  issue: "issues",
};

const transitionsPath = (type: WorkflowArtifactType, id: UUID): string =>
  `/${RESOURCE_PATH[type]}/${id}/transitions/`;

export const workflowTransitionsApi = {
  /** GET the current workflow state and the moves allowed from it. */
  getTransitions(
    type: WorkflowArtifactType,
    id: UUID
  ): Promise<WorkflowTransitionsResponse> {
    return apiClient.get<WorkflowTransitionsResponse>(transitionsPath(type, id));
  },

  /**
   * POST a workflow transition (role / change_reason / signature gates are
   * enforced server-side). ``credential`` carries the password/TOTP token for
   * transitions whose ``signature_gate`` is true.
   */
  transition(
    type: WorkflowArtifactType,
    id: UUID,
    targetState: string,
    changeReason?: string,
    credential?: string
  ): Promise<WorkflowTransitionResult> {
    return apiClient.post<WorkflowTransitionResult>(transitionsPath(type, id), {
      target_state: targetState,
      change_reason: changeReason ?? "",
      credential: credential ?? "",
    });
  },
};
