/**
 * ARCH-L1-001 ReactFrontend — Reviews aggregate API (issue #1193).
 *
 * leaf_id: COMP-RF-REV-001 (ReviewsView)
 * req_id:  REQ-144 (Review/Approval UI)
 *
 * Thin wrapper over the existing backend pending-review queue
 * (``backend/rest_api/review_views.ReviewsPendingView``):
 *
 *     GET /api/v1/reviews/?workspace_id=<uuid>[&item_type=<WorkflowItemType>]
 *     GET /api/v1/reviews/pending/?workspace_id=<uuid>[&item_type=...]
 *
 * The backend answers the standard pagination envelope
 * (``{count, next, previous, results}``); ``count`` is the number of pending
 * items *before* pagination, which is exactly the aggregate the Reviews UI was
 * missing: it could only ever count the one artifact type its filter selected,
 * so a workspace with 68 open approvals spread across several types looked
 * empty whenever the default (``Requirement``) type had none.
 *
 * This is a UI-only wrapper — no backend endpoint is invented here. The route
 * and its query parameters are the ones ``ReviewsPendingView`` documents
 * (``workspace_id`` required; optional ``item_type``; optional repeatable
 * ``state``). ``page_size=1`` keeps the aggregate call cheap: only ``count``
 * is consumed, the single ``results`` row is discarded.
 */

import { getList } from "./client";
import type { PaginatedResponse } from "../types";
import type { WorkflowArtifactType } from "./workflow-transitions";

/**
 * One row of ``GET /api/v1/reviews/``.
 *
 * Mirrors ``application.review_queue_service.PendingReviewItem.to_dict``. Only
 * the fields the frontend consumes are typed; the payload is additive by
 * contract.
 */
export interface PendingReviewItem {
  item_id: string;
  item_type: string;
  current_state: string;
  workspace_id: string;
  is_proposal: boolean;
  proposed_by: string;
  proposed_at: string;
  approval_targets: string[];
}

/**
 * Maps the UI's ``WorkflowArtifactType`` to the backend ``WorkflowItemState``
 * ``item_type`` (``workflow/models.py`` consumers, e.g.
 * ``rest_api/views.py``'s ``workflow_item_type`` class attributes). The queue's
 * ``?item_type=`` filter compares against this CamelCase namespace, not the
 * kebab-case resource segment used elsewhere in the API.
 */
export const REVIEW_ITEM_TYPE: Record<WorkflowArtifactType, string> = {
  requirement: "Requirement",
  need: "StakeholderNeed",
  adr: "Adr",
  "test-case": "TestCase",
  risk: "Risk",
  issue: "Issue",
  architecture: "ArchitectureElement",
  icd: "Icd",
  glossary: "GlossaryTerm",
  diagram: "Diagram",
  goal: "Goal",
  "main-goal": "MainGoal",
};

export const reviewsApi = {
  /**
   * Number of pending items in ``workspaceId``, optionally narrowed to one
   * artifact type. Uses ``count`` from the pagination envelope so it stays
   * correct regardless of how many rows a page carries.
   *
   * SEMANTICS — a **union of two decision sets**, not "approvals":
   *
   *   1. items in front of a genuine approval gate (``in_review`` and every
   *      other state with an approval-gated outgoing transition), and
   *   2. items in the proposal state (``proposed``) — AI proposals awaiting a
   *      confirm/discard chore.
   *
   * The backend union is deliberate and documented in
   * ``application.review_queue_service`` (``ReviewQueueService.list_pending``):
   * a proposal's own moves are editor-gated by design, so the approval-gate
   * predicate does not catch them and the queue adds them by state name. With
   * no ``state`` narrowing (this call) the count therefore covers **both**
   * sets — and that is the point of the aggregate badge (#1193): "is anything
   * waiting anywhere, of either kind?".
   *
   * The count is right; a caller that renders it must NOT label it "open
   * approvals" (fix F2). Use "pending decisions" / "offene Entscheidungen",
   * which is true of both sets. Narrowing via ``state`` would defeat the
   * aggregate's whole purpose (each state is a strict subset).
   *
   * Any future per-state breakdown must pass ``state`` explicitly; the REST
   * endpoint accepts repeatable/comma-separated ``?state=``.
   */
  async listPendingCount(
    workspaceId: string,
    artifactType?: WorkflowArtifactType,
  ): Promise<number> {
    const params: Record<string, string> = {
      workspace_id: workspaceId,
      page_size: "1",
    };
    if (artifactType) {
      params.item_type = REVIEW_ITEM_TYPE[artifactType];
    }
    const resp: PaginatedResponse<PendingReviewItem> = await getList(
      "/reviews/",
      params,
    );
    return resp.count;
  },
};
