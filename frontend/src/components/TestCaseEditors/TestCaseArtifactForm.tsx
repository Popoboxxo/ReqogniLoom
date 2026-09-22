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
 *
 * #424 / #402 (cluster 5):
 * - the header exposes the review action (`tc-review-button`) wired to
 *   `POST /testcases/{id}/review/` (`testcasesApi.review`), and a success
 *   badge once `reviewed === true`;
 * - `scenario_kind` is an explicit select (`tc-scenario-kind-select`), merged
 *   into the save patch. It is deliberately NOT driven by the attribute
 *   definition: the choice is a fixed two-value contract from the model, so
 *   the control must exist regardless of whether the server-side definition
 *   was bootstrapped before or after this column landed;
 * - `origin`/`reviewed`/`baseline_drift` join the read-only key set: `origin`
 *   is write-once, `reviewed` is only toggled through the review endpoint, and
 *   `baseline_drift` is a read-only response annotation — none of them may
 *   ride along on a PATCH.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { extractErrorMessage } from "../../api/client";
import { testcasesApi } from "../../api/testcases";
import type { ScenarioKind } from "../../api/testcases";
import type { TestCase } from "../../types";
import { useEntityReset } from "../../hooks/use-entity-reset";
import { ArtifactForm, type ArtifactFormValues } from "../shared/ArtifactForm";
import { Badge } from "../shared/Badge";
import styles from "./TestCaseArtifactForm.module.css";

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
 *
 * #424: `origin` (immutable after creation), `reviewed` (only settable via the
 * review endpoint) and `baseline_drift` (read-only response annotation) are
 * excluded for the same reason — the serializer rejects `origin`/`reviewed` on
 * an update (spec section 4.4), and `baseline_drift` is not a column at all.
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
  "origin",
  "reviewed",
  "baseline_drift",
]);

const DEFAULT_SCENARIO_KIND: ScenarioKind = "nominal";

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
  /** #424: called after the review action succeeded, so the host refetches the
   *  detail (and the covering list). */
  onReviewed?: () => void;
}

export function TestCaseArtifactForm({
  testCase,
  onSaved,
  onDeleted,
  onDirtyChange,
  customFields,
  onReviewed,
}: TestCaseArtifactFormProps): JSX.Element {
  const { t } = useTranslation();
  const baselineScenarioKind: ScenarioKind =
    testCase.scenario_kind ?? DEFAULT_SCENARIO_KIND;

  const [scenarioKind, setScenarioKind] = useState<ScenarioKind>(baselineScenarioKind);
  const [artifactDirty, setArtifactDirty] = useState(false);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const scenarioDirty = scenarioKind !== baselineScenarioKind;

  // Re-anchor the local scenario/review state when the host swaps the open
  // test case (the editor reuses one mounted form across a list selection —
  // same primitive ArtifactForm itself uses).
  useEntityReset(testCase.id, () => {
    setScenarioKind(baselineScenarioKind);
    setArtifactDirty(false);
    setReviewError(null);
  });

  // The scenario select lives outside ArtifactForm's own value bag, so the
  // dirty contract has to fold it in here — otherwise editing only the
  // scenario would be discarded without the host's unsaved-changes dialog.
  useEffect(() => {
    onDirtyChange?.(artifactDirty || scenarioDirty);
  }, [artifactDirty, scenarioDirty, onDirtyChange]);

  const handleReview = useCallback(async (): Promise<void> => {
    if (reviewSaving) return;
    setReviewSaving(true);
    setReviewError(null);
    try {
      await testcasesApi.review(testCase.id, { reviewed: true });
      onReviewed?.();
    } catch (err) {
      setReviewError(extractErrorMessage(err) || t("testcases.reviewedFailed"));
    } finally {
      setReviewSaving(false);
    }
  }, [onReviewed, reviewSaving, t, testCase.id]);

  const initialValues = useMemo(() => testCaseToFormValues(testCase), [testCase]);
  const isReviewed = testCase.reviewed === true;

  const headerActions = (
    <>
      {isReviewed ? (
        <Badge variant="success" testId="tc-reviewed-badge">
          {t("testcases.reviewed")}
        </Badge>
      ) : (
        <button
          type="button"
          className="btn-secondary"
          data-testid="tc-review-button"
          onClick={() => void handleReview()}
          disabled={reviewSaving}
          aria-busy={reviewSaving || undefined}
        >
          {t("testcases.markReviewed")}
        </button>
      )}
      {reviewError ? (
        <span role="alert" className={styles.reviewError} data-testid="tc-review-error">
          {reviewError}
        </span>
      ) : null}
    </>
  );

  return (
    <>
      <div className={styles.scenarioField}>
        <label className={styles.scenarioLabel} htmlFor="tc-scenario-kind">
          {t("testcases.scenarioKind.label")}
        </label>
        <select
          id="tc-scenario-kind"
          className={styles.scenarioSelect}
          data-testid="tc-scenario-kind-select"
          value={scenarioKind}
          onChange={(event) => setScenarioKind(event.target.value as ScenarioKind)}
        >
          <option value="nominal">{t("testcases.scenarioKind.nominal")}</option>
          <option value="off_nominal">{t("testcases.scenarioKind.offNominal")}</option>
        </select>
      </div>

      <ArtifactForm
        itemType="TestCase"
        artifactId={testCase.id}
        initialValues={initialValues}
        workflowArtifactType="test-case"
        onDirtyChange={setArtifactDirty}
        headerActions={headerActions}
        onSave={async (values) => {
          const patch = formValuesToTestCasePatch(values);
          // Sibling CustomFieldsEditor's draft is authoritative — unconditional
          // overwrite, never a merge against the stale `testCase.custom_fields`
          // baseline (Task 23 F-1 lesson: the backend REPLACES the whole map).
          patch.custom_fields = customFields ?? testCase.custom_fields ?? {};
          // #402: the scenario select is this adapter's own control, not an
          // ArtifactForm value — carry its current value into the same PATCH.
          patch.scenario_kind = scenarioKind;
          await testcasesApi.update(testCase.id, patch);
          onSaved();
        }}
        onDelete={async () => {
          await testcasesApi.delete(testCase.id);
          onDeleted();
        }}
      />
    </>
  );
}
