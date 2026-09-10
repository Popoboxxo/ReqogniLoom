/**
 * TestCase editor on the definition-driven renderer (spec section 6.2, wave 2b).
 *
 * Closes audit finding V: `TestCase.steps` has existed as a column with no UI
 * at all, so steps were only writable through the API. The `steps_editor`
 * widget is that missing editor.
 *
 * Naming: the bootstrap registers the widget as `steps` and binds it to the
 * internal-only key `steps_data` (`WIDGET_FIELD_ALIASES`,
 * bootstrap_attribute_definitions.py) — `steps_data` is NOT a real column or
 * serializer field on `TestCase` (the model column and `TestCaseSerializer`
 * both say `steps`); it exists purely as the form-bag key `StepsEditor.tsx`
 * and this file agree on. Translating between the wire name (`steps`) and the
 * form name (`steps_data`) happens HERE and nowhere else.
 *
 * Task 22 finding (fixed at the shared root cause, bootstrap_attribute_
 * definitions.py `introspect_core_attributes`): the bootstrap used to ALSO
 * emit a second, bare `textarea` attribute literally named `steps_data`
 * alongside this widget — a raw-JSON editor competing for the exact same
 * value, and one bound to a key nothing on the backend accepts. That
 * duplicate is gone; the widget attribute below is the sole representation.
 *
 * change_reason (REQ-162, checked live against `TestService.update_test_case`
 * (backend/application/test_service.py) and `TestCaseViewSet.partial_update`
 * (backend/rest_api/views.py)): UNLIKE `StakeholderNeedService.update_need`,
 * `update_test_case` takes no `change_reason` parameter at all,
 * `TestCaseSerializer` declares no `change_reason` field, and
 * `partial_update` never reads `request.data.get("change_reason")`. The
 * deleted `TestCaseForm.tsx`'s client-side "Extended preset requires a
 * change reason" gate + PATCH field were both dead: the value was silently
 * dropped by DRF (undeclared field) and the client-side block only ever
 * blocked without server backing. `PresetPolicyService.is_change_reason_
 * required` is called for Requirement/StakeholderNeed/the workflow facade —
 * never for TestCase. Deliberately NOT carried forward here.
 *
 * custom_fields: `TestCaseSerializer` DOES mix in `CustomFieldsSerializerMixin`
 * (same as `StakeholderNeedSerializer`, unlike Risk/Adr/Issue) — a genuine
 * working control, so the sibling `CustomFieldsEditor` in `TestCaseEditors`
 * (not this file, same scope boundary as `NeedArtifactForm`'s `customFields`
 * prop) is authoritative and its draft OVERWRITES `patch.custom_fields`
 * unconditionally on save (Task 23 F-1 lesson: never merge against the stale
 * `testCase.custom_fields` baseline — the backend REPLACES the whole map).
 */

import { useMemo } from "react";

import { testcasesApi } from "../../api/testcases";
import type { TestCase } from "../../types";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";

const STEPS_WIRE_FIELD = "steps";
const STEPS_FORM_FIELD = "steps_data";

/**
 * Server-owned fields the form must never send back. `uid` (Task 19 C-1 fix
 * round, applies to every item type): visible but not editable, still spread
 * into the PATCH body from `initialValues` — and `uid` is in
 * `_PROTECTED_PATCH_FIELDS` (backend/rest_api/mixins/workflow_transitions.py),
 * which rejects any PATCH carrying it with a 400. `verifies_link_id`:
 * `read_only=True` on `TestCaseSerializer` (the create-time auto-link
 * result) — DRF already drops it silently on deserialize, so this is
 * defense-in-depth/hygiene only, same class as `uid`.
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
  "suspect",
  "status",
  "verifies_link_id",
]);

export function testCaseToFormValues(testCase: TestCase): ArtifactFormValues {
  const {
    custom_fields: customFields,
    [STEPS_WIRE_FIELD]: steps,
    ...rest
  } = testCase as unknown as Record<string, unknown>;
  return {
    ...rest,
    [STEPS_FORM_FIELD]: Array.isArray(steps) ? steps : [],
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToTestCasePatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    if (key === STEPS_FORM_FIELD) {
      patch[STEPS_WIRE_FIELD] = value;
      continue;
    }
    patch[key] = value;
  }
  return patch;
}

export interface TestCaseArtifactFormProps {
  testCase: TestCase;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
  /** Current draft of the sibling `CustomFieldsEditor` `TestCaseEditors`
   *  renders next to this form. Falls back to `testCase.custom_fields` so the
   *  form still works standalone (e.g. mounted directly in a test). */
  customFields?: Record<string, unknown>;
}

export function TestCaseArtifactForm({
  testCase,
  onSaved,
  onDeleted,
  onDirtyChange,
  customFields,
}: TestCaseArtifactFormProps): JSX.Element {
  const initialValues = useMemo(() => testCaseToFormValues(testCase), [testCase]);

  return (
    <ArtifactForm
      itemType="TestCase"
      artifactId={testCase.id}
      initialValues={initialValues}
      workflowArtifactType="test-case"
      onDirtyChange={onDirtyChange}
      onSave={async (values) => {
        const patch = formValuesToTestCasePatch(values);
        // Sibling CustomFieldsEditor's draft is authoritative — unconditional
        // overwrite, never a merge against the stale `testCase.custom_fields`
        // baseline (Task 23 F-1 lesson: the backend REPLACES the whole map).
        patch.custom_fields = customFields ?? testCase.custom_fields ?? {};
        await testcasesApi.update(testCase.id, patch);
        onSaved();
      }}
      onDelete={async () => {
        await testcasesApi.delete(testCase.id);
        onDeleted();
      }}
    />
  );
}
