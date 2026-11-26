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
import type { WorkflowTransitionStateChange } from "../types/workflow";

/**
 * Artifact types that participate in the WorkflowEngine lifecycle *and* whose
 * list endpoint honours a server-side `?status=` filter. This is the union the
 * Reviews UI switches over, so it must stay exactly the set of types whose
 * queue can be filtered server-side (see `StatusFilterableArtifactType`).
 */
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

/**
 * Artifact types served by the two mixin-based ViewSets
 * (`DocumentViewSet` / `WorkItemViewSet` in
 * `backend/rest_api/views_entity_core.py`). Both mix in
 * `WorkflowTransitionsMixin` (backend/rest_api/mixins/workflow_transitions.py),
 * so they expose the same `GET/POST /{resource}/{id}/transitions/` pair as
 * every other workflow type, but with one deliberate deviation on POST: the
 * body is identical, the response additionally carries the **entity** revision
 * (`version`, the value to echo as `expected_version` on the next guarded
 * write) and the serialized entity (`document` / `work_item`) — the generic
 * ViewSets return the workflow fields only. They are *not* part of
 * `WorkflowArtifactType` because their list endpoints expose `status` as a row
 * field and ignore `?status=` (ADR-026 §9 / Plan F); see
 * `StatusFilterableArtifactType`.
 */
export type DocumentWorkflowArtifactType = "document" | "work-item";

/**
 * Every artifact type the generic transition helpers below can address.
 *
 * Note for callers of `listByStatus`: the widened members are transition-only.
 * Their list endpoints ignore `?status=`, so a status-filtered listing would
 * silently return unfiltered rows — hence the narrow
 * `StatusFilterableArtifactType` parameter on that one helper.
 */
export type TransitionArtifactType =
  | WorkflowArtifactType
  | DocumentWorkflowArtifactType;

/**
 * Types whose list endpoint filters by `?status=` server-side (status-mirror
 * column). Document/WorkItem expose `status` as a row field and their lists
 * ignore `?status=`, so a status-filtered query against them must be a
 * *compile* error rather than a silently unfiltered result.
 */
export type StatusFilterableArtifactType = Exclude<
  TransitionArtifactType,
  DocumentWorkflowArtifactType
>;

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
  /**
   * Display label of the AI agent that proposed this artifact, or null when the
   * item is not in the "proposed" state (KI-Vorschlag-als-Zustand spec §4.4).
   */
  proposed_by: string | null;
  /**
   * Entity revision, present on the document/work-item routes only. It is the
   * value to echo as `expected_version` on the next guarded write (KA-F-08).
   * For every other type this key carries the WorkflowItemState revision.
   */
  version?: number;
  /**
   * The WorkflowItemState revision, returned by the document/work-item routes
   * under this name because `version` is taken by the entity there — those two
   * ViewSets rename it in their GET response
   * (backend/rest_api/views_entity_core.py).
   */
  workflow_version?: number;
}

/**
 * Response of POST /{resource}/{id}/transitions/ — the canonical
 * item-transition result of the WorkflowEngine.
 *
 * The state change itself is the shared `WorkflowTransitionStateChange` every
 * transition route returns; this interface adds the artifact-specific extras.
 * The workspace-*definition* PATCH (`PATCH /workflows/{id}/`, `{id,
 * target_state}`) is a different payload with its own type —
 * `WorkflowDefinitionTransitionResult` in `./workflows`.
 */
export interface WorkflowTransitionResult
  extends WorkflowTransitionStateChange {
  /**
   * Entity revision after the transition — returned by the document/work-item
   * routes only. On those routes `expected_version` guards the entity, not the
   * workflow revision; the entity payload itself (`document` / `work_item`)
   * stays on the specialised wrappers' result types.
   */
  version?: number;
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
  /**
   * Optimistic-lock counter of the row (single-row types). For the
   * immutable-row-per-version types (Goal/MainGoal) this is NOT the revision
   * namespace used by `/versions/`/`/diff/` — that is `sequence_number`, which
   * these types also return. Callers that need "the latest revision" must
   * prefer `sequence_number` when present (GH-1200).
   */
  version?: number;
  /** Per-lineage/per-workspace revision number (Goal/MainGoal only). */
  sequence_number?: number;
}

/**
 * Maps the artifact type to its REST collection path segment. These MUST match
 * the DRF router registrations in ``backend/rest_api/urls.py`` — note the
 * test-case ViewSet is registered as ``testcases`` (no hyphen) and the
 * document/work-item ViewSets as ``documents`` / ``work-items``.
 */
const RESOURCE_PATH: Record<TransitionArtifactType, string> = {
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
  // P1.9: router registrations (backend/rest_api/urls.py) —
  // DocumentViewSet → "documents", WorkItemViewSet → "work-items".
  document: "documents",
  "work-item": "work-items",
};

const transitionsPath = (type: TransitionArtifactType, id: UUID): string =>
  `/${RESOURCE_PATH[type]}/${id}/transitions/`;

/**
 * POST a transition to `/{resource}/{id}/transitions/`, addressing the resource
 * through the shared `RESOURCE_PATH` table above.
 *
 * Exported so the specialised wrappers (`documentsApi`, `workItemsApi`) keep
 * their own payload/result contracts while sharing one URL source of truth —
 * this helper owns the path so the two cannot drift from the generic routes.
 * ``expected_version`` is only a generic parameter here; the caller's body
 * decides whether it means the workflow revision or the entity revision (on
 * document/work-item it is the entity, ADR-026 §9).
 */
export function postWorkflowTransition<TResult>(
  type: TransitionArtifactType,
  id: UUID,
  body: Record<string, unknown>
): Promise<TResult> {
  return apiClient.post<TResult>(transitionsPath(type, id), body);
}

export const workflowTransitionsApi = {
  /** GET the current workflow state and the moves allowed from it. */
  getTransitions(
    type: TransitionArtifactType,
    id: UUID
  ): Promise<WorkflowTransitionsResponse> {
    return apiClient.get<WorkflowTransitionsResponse>(transitionsPath(type, id));
  },

  /**
   * POST a workflow transition (role / change_reason / signature gates are
   * enforced server-side). ``credential`` carries the password/TOTP token for
   * transitions whose ``signature_gate`` is true.
   *
   * ``expectedVersion`` is sent as ``expected_version`` only when defined; on
   * the document/work-item routes it guards the entity revision, on every other
   * type the WorkflowItemState revision.
   */
  transition(
    type: TransitionArtifactType,
    id: UUID,
    targetState: string,
    changeReason?: string,
    credential?: string,
    expectedVersion?: number
  ): Promise<WorkflowTransitionResult> {
    return postWorkflowTransition<WorkflowTransitionResult>(type, id, {
      target_state: targetState,
      change_reason: changeReason ?? "",
      credential: credential ?? "",
      ...(expectedVersion !== undefined
        ? { expected_version: expectedVersion }
        : {}),
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
   *
   * ``type`` is deliberately narrowed to `StatusFilterableArtifactType`:
   * Document/WorkItem list endpoints ignore ``?status=`` (their ``status`` is a
   * row field), so asking for a status-filtered document list would silently
   * return unfiltered rows. Passing one of them here must fail to compile.
   */
  async listByStatus(
    type: StatusFilterableArtifactType,
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
