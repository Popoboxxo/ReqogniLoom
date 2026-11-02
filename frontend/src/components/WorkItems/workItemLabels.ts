/**
 * ARCH-L1-001 ReactFrontend — WorkItem label helpers (Plan F F3-T9).
 *
 * Status and kind are machine values on the wire; these maps are the only
 * place the UI turns them into translated copy. Unknown workspace-customized
 * states fall back to the shared workflow humanizer so a new state still
 * renders readably.
 */

import type { TFunction } from "i18next";

import type { WorkItemKind } from "../../types";
import { getWorkflowStatusLabel } from "../../utils/workflowStatus";
import type { BadgeVariant } from "../../utils/statusBadge";

const KIND_LABEL_KEY: Record<WorkItemKind, string> = {
  Phase: "work_items.kinds.phase",
  Step: "work_items.kinds.step",
  Milestone: "work_items.kinds.milestone",
  OpenPoint: "work_items.kinds.openPoint",
  Checkpoint: "work_items.kinds.checkpoint",
};

/** Static keys (not template literals) so the i18n source scan can see them. */
const STATUS_LABEL_KEY: Record<string, string> = {
  todo: "work_items.statuses.todo",
  in_progress: "work_items.statuses.inProgress",
  blocked: "work_items.statuses.blocked",
  done: "work_items.statuses.done",
  dropped: "work_items.statuses.dropped",
  in_review: "work_items.statuses.inReview",
  outdated: "work_items.statuses.outdated",
};

const KIND_VARIANT: Record<WorkItemKind, BadgeVariant> = {
  Phase: "neutral",
  Step: "neutral",
  Milestone: "info",
  OpenPoint: "warning",
  Checkpoint: "info",
};

export function workItemKindLabel(t: TFunction, kind: WorkItemKind): string {
  return t(KIND_LABEL_KEY[kind] ?? "work_items.kinds.step");
}

export function workItemStatusLabel(t: TFunction, status: string): string {
  const key = STATUS_LABEL_KEY[status.trim().toLowerCase()];
  return key ? t(key) : getWorkflowStatusLabel(status);
}

export function workItemKindVariant(kind: WorkItemKind): BadgeVariant {
  return KIND_VARIANT[kind] ?? "neutral";
}

/** A checkpoint is a resume marker, not a work deliverable (spec §5). */
export function isCheckpoint(kind: WorkItemKind): boolean {
  return kind === "Checkpoint";
}
