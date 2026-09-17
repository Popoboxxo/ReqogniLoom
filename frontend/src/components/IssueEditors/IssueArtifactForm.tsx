/**
 * Issue editor on the definition-driven renderer (spec section 6.2, rollout
 * wave 1b).
 *
 * This file holds only the Issue-specific glue: which API to call and how to
 * map between the REST shape and the form's value bag. Layout, sections,
 * validation display, dirty warning and delete all live in ArtifactForm.
 *
 * Parity gain over the deleted IssueForm: dirty warning and definition-driven
 * field visibility, neither of which that form had (spec section 6.3 — the
 * migration unifies upward).
 */

import { useMemo } from "react";

import { issuesApi } from "../../api/issues";
import type { Issue } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

// BUG-11 (Systemaudit 2026-08-18, §4): exported so IssueEditors' create
// dialog can offer the same category choices as this form, instead of
// duplicating the literal list. (Carried over from the deleted IssueForm.)
export const CATEGORY_OPTIONS = ["defect", "improvement", "documentation", "question"];

/**
 * Server-owned fields the form must never send back.
 *
 * `assignee_id`/`assignee_changed_date` are deliberately absent from the live
 * bootstrapped Issue definition (Task 20 finding, fixed at the shared
 * introspection point in `bootstrap_attribute_definitions.py`): assignee
 * changes go through `IssueService.assign_issue()`, a dedicated method with
 * its own audit trail, never wired to any REST/MCP endpoint. So neither
 * renders as a field here in the first place.
 *
 * `uid` (Task 19 C-1 fix round): a real, visible attribute (bootstrap marks
 * it editable=false, so ArtifactForm renders no input for it) but still
 * spread into the PATCH body from `initialValues` — and `uid` is in
 * `_PROTECTED_PATCH_FIELDS` (backend/rest_api/mixins/workflow_transitions.py),
 * which rejects any PATCH carrying it with a 400. This client-side exclude is
 * defense-in-depth on top of the shared backend fix.
 */
const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "artifact",
  "artifact_id",
  "status",
  "uid",
]);

export function issueToFormValues(issue: Issue): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } = issue as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToIssuePatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface IssueArtifactFormProps {
  issue: Issue;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function IssueArtifactForm({
  issue,
  onSaved,
  onDeleted,
  onDirtyChange,
}: IssueArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => issueToFormValues(issue), [issue]);

  return (
    <ArtifactForm
      itemType="Issue"
      artifactId={issue.id}
      initialValues={initialValues}
      // DEVIATION from the plan brief (same class as RiskArtifactForm, Task
      // 19): `AttributeItemType` uses "Issue"; `WorkflowArtifactType` mirrors
      // the frontend's own lowercase workflow-route family ("issue", see
      // WorkflowStatusEditor/workflow-transitions.ts and the deleted
      // IssueForm's own `artifactType="issue"`). "Issue" is not a member of
      // `WorkflowArtifactType` and fails to compile.
      workflowArtifactType="issue"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await issuesApi.update(issue.id, formValuesToIssuePatch(values));
        onSaved();
      }}
      onDelete={async () => {
        await issuesApi.delete(issue.id);
        onDeleted();
      }}
    />
  );
}
