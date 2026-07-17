/**
 * ARCH-L1-001 ReactFrontend — Reviews data resolver.
 *
 * leaf_id: COMP-RF-REV-001 (ReviewsView)
 * req_id:  REQ-165 (Universal Configurable Workflow Engine per Entity Type),
 *          REQ-167 (entity-type-agnostic Review/Approval UI)
 *
 * Maps a WorkflowArtifactType to the data operations the review queue needs
 * (list-by-status, transitions, transition, workflow history, diff, versions)
 * so ReviewsView / useReviewsData work for any workflow-driven entity type,
 * not just requirements.
 *
 * The ``requirement`` branch intentionally delegates to ``requirementsApi``
 * (unchanged endpoints/signatures) so the established Requirement review
 * behavior and its tests keep passing. All other types route through the
 * generic ``workflowTransitionsApi`` helpers (RESOURCE_PATH-backed).
 */

import {
  requirementsApi,
  type RequirementTransitions,
} from "../../api/requirements";
import {
  workflowTransitionsApi,
  type WorkflowArtifactType,
  type WorkflowTransitionResult,
  type WorkflowHistoryEntry,
  type ReviewListItem,
} from "../../api/workflow-transitions";
import type { ArtifactDiffResult, ArtifactVersion } from "../../types";

/** The data operations ReviewsView needs, decoupled from the entity type. */
export interface ReviewsResolver {
  list(workspaceId: string, status: string): Promise<ReviewListItem[]>;
  getTransitions(id: string): Promise<RequirementTransitions>;
  transition(
    id: string,
    targetState: string,
    changeReason?: string,
    credential?: string
  ): Promise<WorkflowTransitionResult>;
  getWorkflowHistory(id: string): Promise<WorkflowHistoryEntry[]>;
  diff(
    id: string,
    fromVersion: number,
    toVersion: number
  ): Promise<ArtifactDiffResult>;
  versions(id: string): Promise<ArtifactVersion[]>;
}

const requirementResolver: ReviewsResolver = {
  list: (workspaceId, status) =>
    requirementsApi.list(workspaceId, status).then((r) => r.results),
  getTransitions: (id) => requirementsApi.getTransitions(id),
  transition: (id, targetState, changeReason, credential) =>
    requirementsApi.transition(id, targetState, changeReason, credential),
  getWorkflowHistory: (id) => requirementsApi.getWorkflowHistory(id),
  diff: (id, fromVersion, toVersion) =>
    requirementsApi.diff(id, fromVersion, toVersion),
  versions: (id) => requirementsApi.versions(id),
};

/** Builds a generic resolver over the workflow-transitions API for any type. */
function genericResolver(type: WorkflowArtifactType): ReviewsResolver {
  return {
    list: (workspaceId, status) =>
      workflowTransitionsApi.listByStatus(type, workspaceId, status),
    getTransitions: (id) => workflowTransitionsApi.getTransitions(type, id),
    transition: (id, targetState, changeReason, credential) =>
      workflowTransitionsApi.transition(
        type,
        id,
        targetState,
        changeReason,
        credential
      ),
    getWorkflowHistory: (id) =>
      workflowTransitionsApi.getWorkflowHistory(type, id),
    diff: (id, fromVersion, toVersion) =>
      workflowTransitionsApi.diff(type, id, fromVersion, toVersion),
    versions: (id) => workflowTransitionsApi.versions(type, id),
  };
}

/** Resolves the data operations for the given artifact type. */
export function getReviewsResolver(
  artifactType: WorkflowArtifactType
): ReviewsResolver {
  return artifactType === "requirement"
    ? requirementResolver
    : genericResolver(artifactType);
}
