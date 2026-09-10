/**
 * ArchitectureElement editor on the definition-driven renderer
 * (spec section 6.2, rollout wave 2d).
 *
 * This file holds only the ArchitectureElement-specific glue: which API to
 * call and how to map between the REST shape and the form's value bag.
 * Layout, sections, validation display, dirty warning and delete all live in
 * ArtifactForm.
 *
 * `parent_id` is the same-type containment FK and renders as an ordinary
 * `reference` attribute. Cross-type relations are TraceLinks and stay in the
 * trace panel — the element hierarchy is deliberately not a link.
 *
 * The decompose panel and the element tree are not attributes and stay in
 * ArchitectureEditors.
 */

import { useMemo } from "react";

import { architectureApi } from "../../api/architecture";
import type { ArchitectureElement } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

/**
 * Server-owned fields the form must never send back.
 *
 * `level`/`role` are backend-computed from tree position (SysEng 2.0 §1.2),
 * never accepted as input by `ArchitectureElementSerializer`. `uid` is a
 * real, visible attribute (bootstrap marks it editable=false, so
 * ArtifactForm renders no input for it) but is still spread into the PATCH
 * body from `initialValues`, and `uid` is in `_PROTECTED_PATCH_FIELDS`
 * (backend/rest_api/mixins/workflow_transitions.py) — this client-side
 * exclude is defense-in-depth on top of the shared backend fix (Task 19
 * C-1). `suspect` (SN-30 upstream-change flag) is excluded from
 * introspection (`EXCLUDED_MODEL_FIELDS`) and the view never forwards it
 * from PATCH to the service either way, but excluding it here too avoids
 * sending dead data on every save.
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
  "uid",
  "status",
  "level",
  "role",
  "suspect",
]);

export function architectureToFormValues(
  element: ArchitectureElement
): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } =
    element as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToArchitecturePatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface ArchitectureArtifactFormProps {
  element: ArchitectureElement;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function ArchitectureArtifactForm({
  element,
  onSaved,
  onDeleted,
  onDirtyChange,
}: ArchitectureArtifactFormProps): JSX.Element {
  const initialValues = useMemo(
    () => architectureToFormValues(element),
    [element]
  );

  return (
    <ArtifactForm
      itemType="ArchitectureElement"
      artifactId={element.id}
      initialValues={initialValues}
      // DEVIATION from the plan brief (same class as RiskArtifactForm/
      // IssueArtifactForm, Tasks 19/20): `AttributeItemType` uses
      // "ArchitectureElement"; `WorkflowArtifactType` mirrors the frontend's
      // own lowercase workflow-route family ("architecture", see
      // WorkflowStatusEditor/workflow-transitions.ts and the deleted
      // ArchitectureForm's own `artifactType="architecture"`).
      workflowArtifactType="architecture"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await architectureApi.update(
          element.id,
          formValuesToArchitecturePatch(values)
        );
        onSaved();
      }}
      onDelete={async () => {
        await architectureApi.delete(element.id);
        onDeleted();
      }}
    />
  );
}
