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

import { apiClient, getList } from "./client";
import type {
  UUID,
  ArtifactDiffResult,
  ArtifactVersion,
} from "../types";

/** Artifact types that participate in the WorkflowEngine lifecycle. */
export type WorkflowArtifactType =
  | "requirement"
  | "need"
  | "adr"
  | "test-case"
  | "risk"
  | "issue"
  | "architecture"
  | "icd"
  | "glossary"
  | "diagram"
  // Issue #372: Goal/MainGoal are tracked via workflow_item_type "Goal" /
  // "MainGoal" (backend/rest_api/views.py GoalViewSet/MainGoalViewSet,
  // workflow/definition_store.py goal_default/main_goal_default) but were
  // missing from this union, so the Reviews UI never offered them as a
  // selectable type and their 30 pending items never loaded.
  | "goal"
  | "main-goal";

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

/**
 * A single entry of the append-only workflow transition history, as returned
 * by GET /{resource}/{id}/workflow-history/ (WorkflowTransitionsMixin, PR2).
 * Mirrors ``requirementsApi.WorkflowHistoryEntry`` so any artifact type shares
 * one history contract.
 */
export interface WorkflowHistoryEntry {
  id: string;
  from_state: string | null;
  to_state: string;
  actor: string;
  change_reason: string;
  transitioned_at: string;
  sealed: boolean;
}

/**
 * The minimal, artifact-type-agnostic shape the review queue needs from a
 * list item. Every reviewable entity (requirement/need/adr/test-case/risk/
 * issue) exposes these fields.
 */
export interface ReviewListItem {
  id: string;
  uid?: string | null;
  title: string;
  description?: string;
  version?: number;
}

/**
 * Maps the artifact type to its REST collection path segment. These MUST match
 * the DRF router registrations in ``backend/rest_api/urls.py`` — note the
 * test-case ViewSet is registered as ``testcases`` (no hyphen).
 */
const RESOURCE_PATH: Record<WorkflowArtifactType, string> = {
  requirement: "requirements",
  need: "needs",
  adr: "adrs",
  "test-case": "testcases",
  risk: "risks",
  issue: "issues",
  architecture: "architecture",
  // Router registrations (backend/rest_api/urls.py): IcdViewSet → "icds",
  // GlossaryTermViewSet → "glossary" (NOT "glossary-terms").
  icd: "icds",
  glossary: "glossary",
  // Router registration (backend/rest_api/urls.py): DiagramViewSet → "diagrams".
  diagram: "diagrams",
  // Issue #372: router registrations (backend/rest_api/urls.py) —
  // GoalViewSet → "goals", MainGoalViewSet → "main-goals".
  goal: "goals",
  "main-goal": "main-goals",
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

  /** GET the append-only workflow transition history for an artifact. */
  getWorkflowHistory(
    type: WorkflowArtifactType,
    id: UUID
  ): Promise<WorkflowHistoryEntry[]> {
    return apiClient.get<WorkflowHistoryEntry[]>(
      `/${RESOURCE_PATH[type]}/${id}/workflow-history/`
    );
  },

  /**
   * GET the artifacts of ``type`` in the given workflow ``status`` for a
   * workspace (the review queue's list source). Returns the (possibly
   * paginated) first page's results.
   */
  async listByStatus(
    type: WorkflowArtifactType,
    workspaceId: UUID,
    status: string
  ): Promise<ReviewListItem[]> {
    const resp = await getList<ReviewListItem>(`/${RESOURCE_PATH[type]}/`, {
      workspace_id: workspaceId,
      status,
    });
    return resp.results;
  },

  /** Field-level diff between two versions of an artifact. */
  diff(
    type: WorkflowArtifactType,
    id: UUID,
    fromVersion: number,
    toVersion: number
  ): Promise<ArtifactDiffResult> {
    return apiClient.get<ArtifactDiffResult>(
      `/${RESOURCE_PATH[type]}/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for an artifact. */
  versions(
    type: WorkflowArtifactType,
    id: UUID
  ): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(
      `/${RESOURCE_PATH[type]}/${id}/versions/`
    );
  },
};
