/**
 * Requirement editor on the definition-driven renderer — last of the seven
 * (spec section 6.2), because it carried the most special cases.
 *
 * What is NOT here on purpose: derive, generate-test-case and find-similar are
 * actions on a requirement, not attributes of one. They stay in
 * RequirementEditors as siblings of this form, the same boundary the Need and
 * Architecture migrations drew.
 *
 * change_reason (REQ-162, Task 25): unlike the six prior waves, this is the
 * first adapter to opt into the shared `ArtifactForm`'s own `requiresChangeReason`
 * prop rather than rolling a bespoke sibling field (`NeedArtifactForm`, Task
 * 23) — the capability now lives in the shared renderer so every type can opt
 * in, but only Requirement is wired up to it here.
 *
 * custom_fields (REQ-L2-AS-037): the deleted `RequirementForm` rendered a
 * free-form `<CustomFieldsEditor>` for `custom_fields` — no `kind: "extended"`
 * attribute exists for Requirement, so the definition-driven renderer has no
 * way to draw it. Same scope boundary as `TestCaseArtifactForm`/
 * `NeedArtifactForm` (Tasks 22/23): the editor lives in `RequirementEditors`
 * as a sibling of this form, its current draft comes in via the
 * `customFields` prop, and `onSave` below UNCONDITIONALLY OVERWRITES the
 * patch's `custom_fields` with it — never a merge against a stale baseline
 * (Task 23 fix round 4, F-1: a merge silently resurrects deleted/renamed
 * keys).
 */

import { useMemo } from "react";

import { requirementsApi } from "../../api/requirements";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { Requirement } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

/**
 * Server-owned fields the form must never send back.
 *
 * `uid` (Task 19 C-1 fix round, applies to every item type): a real, visible
 * attribute (bootstrap marks it editable=false, so ArtifactForm renders no
 * input for it) but still spread into the PATCH body from `initialValues` —
 * and `uid` is in `_PROTECTED_PATCH_FIELDS`
 * (backend/rest_api/mixins/workflow_transitions.py), which rejects any PATCH
 * carrying it with a 400. This client-side exclude is defense-in-depth on
 * top of the shared backend fix.
 *
 * `parent_id`/`suspect`: `RequirementSerializer` declares `parent_id` as
 * writable, but `RequirementService.update_requirement()` has no `parent_id`
 * parameter at all — the view never forwards it (verified live against
 * `RequirementViewSet.partial_update`), so sending it back is a no-op that
 * only risks a future accidental parent move if the view's field-forwarding
 * ever widens. `suspect` is read-only server-side, set only by
 * `TraceLinkService.propagate_suspect_status`.
 *
 * `atomicity_warning`: a `SerializerMethodField` (IEEE 29148 §5.2.4
 * non-blocking hint) — inherently read-only to DRF, silently dropped from
 * `validated_data` regardless, but excluded here too so the PATCH body a real
 * live GET->PATCH round-trip emits does not carry a value the server can
 * never accept back, matching the same defensive-exclude convention every
 * other adapter (`RiskArtifactForm`'s `rpn`, `IssueArtifactForm`'s
 * `assignee`) already applies to its own type's derived/computed fields.
 */
const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "updated_at",
  "artifact_id",
  "uid",
  "status",
  "parent_id",
  "suspect",
  "atomicity_warning",
]);

export function requirementToFormValues(
  requirement: Requirement
): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } =
    requirement as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToRequirementPatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface RequirementArtifactFormProps {
  requirement: Requirement;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
  /** Current value of the sibling `CustomFieldsEditor` RequirementEditors
   *  renders next to this form. Falls back to `requirement.custom_fields` so
   *  the form still works standalone (e.g. in tests that mount it directly). */
  customFields?: Record<string, unknown>;
}

export function RequirementArtifactForm({
  requirement,
  onSaved,
  onDeleted,
  onDirtyChange,
  customFields,
}: RequirementArtifactFormProps): JSX.Element {
  const { activeWorkspace } = useWorkspace();
  const initialValues = useMemo(
    () => requirementToFormValues(requirement),
    [requirement]
  );

  return (
    <ArtifactForm
      itemType="Requirement"
      artifactId={requirement.id}
      initialValues={initialValues}
      workflowArtifactType="requirement"
      requiresChangeReason={activeWorkspace?.preset === "extended"}
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        const patch = formValuesToRequirementPatch(values);
        patch.custom_fields = customFields ?? requirement.custom_fields ?? {};
        await requirementsApi.update(requirement.id, patch);
        onSaved();
      }}
      onDelete={async (changeReason) => {
        // F-1 (Task 25 fix round 1): forward the shared change-reason field's
        // value — the Extended preset gates DELETE with the same
        // `is_change_reason_required` check PATCH gets
        // (`RequirementService.delete_requirement`), so an omitted reason
        // 400s exactly like an omitted-reason save would.
        await requirementsApi.delete(requirement.id, changeReason);
        onDeleted();
      }}
    />
  );
}
