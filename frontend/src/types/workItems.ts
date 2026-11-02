/**
 * ARCH-L1-001 ReactFrontend — WorkItem artifact types (Plan F F3-T9, #1374).
 *
 * Mirrors `WorkItemSerializer` / `_work_item_to_dict` in
 * `backend/rest_api/views.py`. The workflow state is the read-only `status`
 * resolved by the engine (REQ-143); a soft-deleted item still resolves with
 * `status: "outdated"`. `owner`/`reporter`/`priority`/`custom_fields` live on
 * the backing Artifact, exactly like every other artifact.
 */

import type { CustomFields, ISODateTime, UUID } from "./common";

/** `persistence.models.WorkItem.Kind` — the five item kinds. */
export type WorkItemKind =
  | "Phase"
  | "Step"
  | "Milestone"
  | "OpenPoint"
  | "Checkpoint";

/** Every kind, in the backend's declaration order. */
export const WORK_ITEM_KINDS: readonly WorkItemKind[] = [
  "Phase",
  "Step",
  "Milestone",
  "OpenPoint",
  "Checkpoint",
] as const;

export interface WorkItem {
  id: UUID;
  workspace_id: UUID;
  document_id: UUID;
  /** Backing Artifact id — needed to attach trace links and comments. */
  artifact_id?: UUID | null;
  /** Local readable identifier (`WI-NNN`), server-allocated. */
  uid?: string | null;
  title: string;
  kind: WorkItemKind;
  ordinal: number;
  /** Markdown of the section (used by Step/Checkpoint). */
  body: string;
  /** Optional 0–100 progress, independent of the workflow state. */
  progress: number | null;
  blocked_reason: string;
  /** Resume hint ("where to continue"). */
  next_action: string;
  last_activity_at?: ISODateTime | null;
  last_actor: string;
  evidence_ref: string;
  approved_by: string;
  approved_at?: ISODateTime | null;
  due_date?: ISODateTime | null;
  exit_criteria: string;
  custom_fields?: CustomFields;
  /** Workflow state (`todo`, `in_progress`, `blocked`, `done`, `dropped`, …). */
  status: string;
  /** Optimistic-lock counter — the ETag source, not a content revision. */
  version: number;
  created_at: ISODateTime;
  updated_at: ISODateTime;
}

/** One trace link carried by a resume entry (both directions). */
export interface WorkItemLink {
  id: UUID;
  link_type: string;
  source_id: UUID;
  target_id: UUID;
  direction: "upstream" | "downstream";
}

/** One open item (or the newest checkpoint) of `work_item.resume`. */
export interface WorkItemResumeEntry {
  id: UUID;
  uid?: string | null;
  kind: WorkItemKind;
  status: string;
  progress: number | null;
  next_action: string;
  blocked_reason: string;
  last_actor: string;
  last_activity_at?: ISODateTime | null;
  links: WorkItemLink[];
}

/** Response of `GET /api/v1/work-items/resume/`. */
export interface WorkItemResume {
  checkpoint: WorkItemResumeEntry | null;
  open_items: WorkItemResumeEntry[];
}

/** One move allowed from the item's current state. */
export interface WorkItemAllowedTransition {
  target_state: string;
  requires_change_reason: boolean;
  signature_gate: boolean;
}

/** Response of `GET /api/v1/work-items/{id}/transitions/`. */
export interface WorkItemTransitionsResponse {
  current_state: string | null;
  /** The item revision (the value to echo as `expected_version`). */
  version: number;
  workflow_version?: number;
  states: string[];
  allowed_transitions: WorkItemAllowedTransition[];
  proposed_by?: string | null;
}

/** Response of `POST /api/v1/work-items/{id}/transitions/`. */
export interface WorkItemTransitionResult {
  id: UUID;
  previous_state: string;
  new_state: string;
  version: number;
  work_item: WorkItem;
}
