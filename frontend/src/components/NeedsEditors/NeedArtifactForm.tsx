/**
 * StakeholderNeed editor on the definition-driven renderer (spec section 6.2,
 * rollout wave 2c).
 *
 * NeedForm was the ONLY consumer of the old AttributeVisibilityConfig prop
 * chain; deleting it removes the last live reader of that mechanism. Field
 * visibility now comes from the resolved definition like every other type.
 *
 * DeriveRequirementsPanel / TraceLinkPanel / the manual-derive form are not
 * attributes and stay in NeedsEditors as siblings of this form (scope
 * boundary shared with the ADR/ArchitectureElement waves).
 *
 * change_reason (REQ-162): unlike Risk/Issue — whose services never call
 * `PresetPolicyService.is_change_reason_required` — `StakeholderNeedService.
 * update_need()` genuinely rejects an Extended-preset PATCH with no
 * `change_reason` (application/stakeholder_need_service.py:296). `change_reason`
 * is a write_only serializer param, not a model column, so the bootstrap
 * introspection loop never produces it as an attribute and `ArtifactForm`
 * itself has no concept of it at all. Carrying this field over from the
 * deleted `NeedForm` (regression-tested by the now-migrated
 * `need-form-change-reason.test.tsx`) is therefore this file's job, not the
 * shared renderer's — same class of "genuinely item-type-specific" decision
 * as `RiskArtifactForm`'s `owner_user_id` alias / `IssueArtifactForm`'s
 * assignee exclusion.
 *
 * custom_fields (Task 23 fix round 4, F-1 — reverts round N-2's merge): the
 * free-form JSON editor (`CustomFieldsEditor`) is rendered by `NeedsEditors`
 * as a JSX sibling of this form (same scope boundary as `changeReason`
 * below). Its current draft is passed in via the `customFields` prop and is
 * an unconditional OVERWRITE of the PATCH's `custom_fields` —
 * `customFields ?? need.custom_fields ?? {}`, full-stop, no merge with
 * `need.custom_fields` or `values.custom_fields`.
 *
 * N-2 tried a 3-way merge (need.custom_fields as base, values.custom_fields
 * and the sibling draft layered on top) to protect a hypothetical future
 * `kind: "extended"` attribute writing into `values.custom_fields`. That was
 * live-broken: `StakeholderNeedService.update_need()` REPLACES the whole
 * `custom_fields` map server-side (no server-side merge), so merging the
 * STALE `need.custom_fields` baseline back in on every save meant a key
 * deleted or renamed in the sibling editor got silently resurrected from
 * that stale baseline (delete → PATCH → GET still shows it; rename → GET
 * shows both old and new key). The sibling `CustomFieldsEditor`'s draft is
 * authoritative because it is the only thing that ever actually edits
 * `custom_fields` today — the live StakeholderNeed definition has zero
 * `kind: "extended"` attributes (verified across all 3 presets), so
 * `values.custom_fields` never diverges from `need.custom_fields` anyway.
 * Tracked project-wide as urgent gap #7 in
 * `.superpowers/sdd/2026-09-03-attribute-definition/progress.md` — the day a
 * `kind: "extended"` attribute exists for StakeholderNeed, an edit made only
 * through that widget (with the sibling editor untouched) would need its own
 * handling; not solved here.
 */

import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { stakeholderNeedApi } from "../../api/stakeholder-need";
import { useWorkspace } from "../../context/WorkspaceContext";
import { useEntityReset } from "../../hooks/use-entity-reset";
import type { StakeholderNeed } from "../../types";
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
 * `parent_id`/`suspect`: declared `read_only=True` on `StakeholderNeedSerializer`
 * (verified live against rest_api/serializers.py) — DRF drops them silently on
 * write, so this is low-priority defensive cleanup, same class as
 * `RiskArtifactForm`'s `owner_user_display`/`rpn` exclusion.
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
  "parent_id",
  "suspect",
]);

export function needToFormValues(need: StakeholderNeed): ArtifactFormValues {
  const { custom_fields: customFields, ...rest } =
    need as unknown as Record<string, unknown>;
  return {
    ...rest,
    custom_fields: (customFields as Record<string, unknown>) ?? {},
  };
}

export function formValuesToNeedPatch(
  values: ArtifactFormValues
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (READ_ONLY_KEYS.has(key)) continue;
    patch[key] = value;
  }
  return patch;
}

export interface NeedArtifactFormProps {
  need: StakeholderNeed;
  onSaved: () => void;
  onDeleted: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
  /** Current value of the sibling `CustomFieldsEditor` NeedsEditors renders
   *  next to this form (R-1 fix). Falls back to `need.custom_fields` so the
   *  form still works standalone (e.g. in tests that mount it directly). */
  customFields?: Record<string, unknown>;
}

export function NeedArtifactForm({
  need,
  onSaved,
  onDeleted,
  onDirtyChange,
  customFields,
}: NeedArtifactFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  // REQ-162: Extended preset requires a change_reason on every update
  // (backend/application/preset_policy_service.py: is_change_reason_required).
  const isExtendedPreset = activeWorkspace?.preset === "extended";
  const [changeReason, setChangeReason] = useState("");
  // R-2: reset on entity switch, not just on save — otherwise a reason typed
  // for need A silently rides along on need B's PATCH once B is selected
  // (the component is reused across list selections, never remounted).
  useEntityReset(need.id, () => setChangeReason(""));
  const initialValues = useMemo(() => needToFormValues(need), [need]);

  // S-2: `changeReason` lives outside ArtifactForm's own `values` bag, so its
  // internal `useFormDirty` never sees it. Combine ArtifactForm's own dirty
  // signal with "has the user typed an unsubmitted change reason" so the
  // unsaved-changes dialog in NeedsEditors also catches this case.
  const [formDirty, setFormDirty] = useState(false);
  const hasPendingChangeReason = changeReason.trim().length > 0;
  useEffect(() => {
    onDirtyChange?.(formDirty || hasPendingChangeReason);
    return () => onDirtyChange?.(false);
  }, [formDirty, hasPendingChangeReason, onDirtyChange]);

  const labelStyle: CSSProperties = {
    fontWeight: 500,
    color: "var(--color-text)",
    display: "block",
    marginBottom: "var(--space-1)",
  };

  return (
    <>
      <ArtifactForm
        itemType="StakeholderNeed"
        artifactId={need.id}
        initialValues={initialValues}
        workflowArtifactType="need"
        onDirtyChange={setFormDirty}
        onSave={async (values) => {
          // Client-side guard mirrors the deleted NeedForm's handleSave: the
          // backend 400s anyway (see docstring above), but blocking here
          // avoids a round trip and lands the message via ArtifactForm's own
          // error surface (`artifact-form-error`, role="alert").
          if (isExtendedPreset && !changeReason.trim()) {
            throw new Error(t("req.changeReasonRequired"));
          }
          const patch = formValuesToNeedPatch(values);
          // F-1: unconditional overwrite, reverting N-2's merge — the
          // sibling CustomFieldsEditor's draft is authoritative, full-stop.
          // See docstring above for why merging need.custom_fields back in
          // silently resurrected deleted/renamed keys.
          patch.custom_fields = customFields ?? need.custom_fields ?? {};
          if (isExtendedPreset) {
            patch.change_reason = changeReason.trim();
          }
          await stakeholderNeedApi.update(need.id, patch);
          setChangeReason("");
          onSaved();
        }}
        onDelete={async () => {
          // S-1: the backend gates DELETE identically to PATCH (same
          // `is_change_reason_required` check) — reuse the same textarea
          // value rather than adding a second prompt/modal for it.
          if (isExtendedPreset) {
            await stakeholderNeedApi.delete(need.id, changeReason.trim());
          } else {
            await stakeholderNeedApi.delete(need.id);
          }
          onDeleted();
        }}
      />
      {isExtendedPreset && (
        <div style={{ marginTop: "var(--space-4)" }}>
          <label htmlFor="need-change-reason" style={labelStyle}>
            {t("req.changeReason")} <span style={{ color: "var(--color-danger)" }}>*</span>
          </label>
          <textarea
            id="need-change-reason"
            data-testid="need-change-reason-input"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            rows={2}
            style={{
              width: "100%",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-3)",
              fontFamily: "var(--font-sans)",
              fontSize: "var(--font-size-base)",
              color: "var(--color-text)",
              background: "var(--color-surface)",
              boxSizing: "border-box",
              resize: "vertical",
            }}
            placeholder={t("req.changeReasonPlaceholderNeed")}
          />
        </div>
      )}
    </>
  );
}
