/**
 * Risk editor — first form migrated onto the definition-driven renderer
 * (spec section 6.2, smallest risk first).
 *
 * This file holds only the Risk-specific glue: which API to call and how to map
 * between the REST shape and the form's value bag. Layout, sections, validation
 * display, dirty warning and delete all live in ArtifactForm.
 */

import { useMemo } from "react";

import { risksApi } from "../../api/risks";
import type { Risk } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

/** Kept here (was in the deleted RiskForm) — RiskEditors imports it for its filter. */
export const CATEGORY_OPTIONS = [
  "technical",
  "operational",
  "organizational",
  "business",
] as const;

/**
 * Server-owned fields the form must never send back.
 *
 * DEVIATION from the plan brief: does not include `owner_user_id`. The brief
 * did not name it at all, but the real, bootstrapped Risk definition (verified
 * live via `introspect_core_attributes("Risk", "standard")`) carries a `user`-
 * typed attribute for it — a real, editable field, not a read-only one. It is
 * intentionally absent from this set so an owner assignment actually saves.
 */
const READ_ONLY_KEYS = new Set([
  "id",
  "workspace_id",
  "tenant_id",
  "version",
  "created_at",
  "modified_at",
  "updated_at",
  "risk_score",
  "severity",
  "artifact",
  "artifact_id",
  "status",
  // C-1 fix round: `uid` is a real, visible attribute (bootstrap now marks it
  // editable=false, so ArtifactForm no longer renders an input for it) but
  // was still spread into the PATCH body from `initialValues`, and `uid` is
  // in `_PROTECTED_PATCH_FIELDS` (backend/rest_api/mixins/workflow_transitions.py)
  // — the backend rejects any PATCH carrying it with a 400. This client-side
  // exclude is defense-in-depth on top of the backend fix, since a future
  // widening of the definition must not silently reopen this failure mode.
  "uid",
  // Declared read_only by RiskSerializer; DRF drops them silently, so this is
  // low-priority defensive cleanup rather than a bug fix on its own.
  "owner_user_display",
  "rpn",
]);

export function riskToFormValues(risk: Risk): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } = risk as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToRiskPatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface RiskArtifactFormProps {
  risk: Risk;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function RiskArtifactForm({
  risk,
  onSaved,
  onDeleted,
  onDirtyChange,
}: RiskArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => riskToFormValues(risk), [risk]);

  return (
    <ArtifactForm
      itemType="Risk"
      artifactId={risk.id}
      initialValues={initialValues}
      // DEVIATION from the plan brief: the brief wrote `"Risk"` here. The two
      // type unions this call straddles use different casing on purpose —
      // `AttributeItemType` mirrors the backend's `item_type` string
      // ("Risk"), `WorkflowArtifactType` mirrors the frontend's own
      // lowercase workflow-route family ("risk", see
      // WorkflowStatusEditor/workflow-transitions.ts and the deleted
      // RiskForm's own `artifactType="risk"`). `"Risk"` is not a member of
      // `WorkflowArtifactType` and fails to compile.
      workflowArtifactType="risk"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await risksApi.update(risk.id, formValuesToRiskPatch(values));
        onSaved();
      }}
      onDelete={async () => {
        await risksApi.delete(risk.id);
        onDeleted();
      }}
    />
  );
}
