/**
 * ADR editor on the definition-driven renderer (spec section 6.2, wave 2a).
 *
 * The deleted AdrForm stacked three MarkdownPreview editors (description,
 * context, consequences); the definition now expresses that as one
 * `markdown_tab_group` widget bound to those exact three fields.
 * `Adr.decision` was never part of that group and stays an ordinary textarea,
 * so no content becomes unreachable.
 *
 * The ADR-Supersede-Flow (REQ-L3-ADR-005) is NOT part of this file — it has
 * no equivalent in the generic ArtifactForm renderer, so it stays a
 * standalone sibling (`AdrSupersedePanel`), rendered next to this form by
 * `AdrEditors` — see that component's doc comment for why.
 */

import { useMemo } from "react";

import { adrsApi } from "../../api/adrs";
import type { Adr } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

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
]);

export function adrToFormValues(adr: Adr): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } = adr as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToAdrPatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface AdrArtifactFormProps {
  adr: Adr;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
}

export function AdrArtifactForm({
  adr,
  onSaved,
  onDeleted,
  onDirtyChange,
}: AdrArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => adrToFormValues(adr), [adr]);

  return (
    <ArtifactForm
      itemType="Adr"
      artifactId={adr.id}
      initialValues={initialValues}
      // DEVIATION from the plan brief (same class as RiskArtifactForm/
      // IssueArtifactForm, Tasks 19/20): `AttributeItemType` uses "Adr";
      // `WorkflowArtifactType` mirrors the frontend's own lowercase
      // workflow-route family ("adr", see WorkflowStatusEditor/workflow-
      // transitions.ts and the deleted AdrForm's own `artifactType="adr"`).
      workflowArtifactType="adr"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        await adrsApi.update(adr.id, formValuesToAdrPatch(values));
        onSaved();
      }}
      onDelete={async () => {
        await adrsApi.delete(adr.id);
        onDeleted();
      }}
    />
  );
}
