/**
 * Bottom action area of the definition-driven artifact form: the change-reason
 * input, the Save/Deprecate/Cancel row and the deprecate confirmation dialog.
 *
 * Extracted from `ArtifactForm.tsx` (Phase 5b decomposition, FE-01 / F-01).
 * Renders inside the same `<form>` and produces the identical DOM (a component
 * boundary adds no element). All state arrives in ONE structured `actions`
 * prop (R2F-002): the four nested groups (`common`, `create`, `changeReason`,
 * `deprecate`) are always present, so dependent flags travel together and
 * concurrent states such as "change reason invalid AND deprecate dialog open"
 * stay representable.
 */

import { useTranslation } from "react-i18next";

import type { ArtifactFormActionState } from "./action-state";
import { SAVE_SHORTCUT_ARIA } from "../../../hooks/useSaveShortcut";
import { ConfirmDialog } from "../ConfirmDialog";
import { RequiredMark } from "../FormField";
import styles from "./ArtifactForm.module.css";

/**
 * #1595/#1732: stable id of the visible "required fields are still empty"
 * hint. Since #1732 the Create button is no longer disabled by an empty field
 * (a click validates and explains at the field itself), so the hint is a
 * proactive `role="status"` summary rather than the only explanation of a
 * greyed-out control.
 */
const CREATE_HINT_ID = "artifact-form-create-hint";

export interface ArtifactFormActionsProps {
  /** Structured state of the whole action area — see `action-state.ts`. */
  actions: ArtifactFormActionState;
  /** Form-level cancel, owned by the caller (absent when no cancel is offered). */
  onCancel?: () => void;
}

export function ArtifactFormActions({
  actions,
  onCancel,
}: ArtifactFormActionsProps): JSX.Element {
  const { t } = useTranslation();
  const { common, create, changeReason, deprecate } = actions;

  return (
    <>
      {changeReason.needed ? (
        <label className={styles.field}>
          {/* #1393: the marker is a DOM node (`RequiredMark`), not the CSS
              `::after` this label used to rely on — a pseudo-element is
              invisible to `textContent` and to any measurement tool, which is
              exactly how "no visible marker" survived the earlier review. */}
          <span className={styles.label}>
            {t("artifactForm.changeReason")}
            <RequiredMark />
          </span>
          {/* #1393: the server refuses both the save and the DELETE without a
              reason once the workspace policy is mandatory (`400 …
              "change_reason is required by preset policy."`), so the control
              itself has to SAY it is required. `required` + `aria-required`;
              the enclosing form is `noValidate`, so the #977 inline-error flow
              still owns the actual refusal. */}
          <input
            className={`${styles.control} ${changeReason.invalid ? styles.controlInvalid : ""}`}
            data-testid="artifact-form-change-reason"
            type="text"
            value={changeReason.value}
            ref={changeReason.ref}
            required
            aria-required="true"
            aria-invalid={changeReason.invalid || undefined}
            aria-describedby={changeReason.invalid ? changeReason.errorId : undefined}
            onChange={(event) => changeReason.onChange(event.target.value)}
          />
          {changeReason.invalid ? (
            // Issue #977 (proof-journey finding): the save was refused, but the
            // reason appeared only in the banner at the very top of the form
            // while this field sits below every section. A user who clicked
            // Save saw nothing happen where they were looking. The message now
            // also sits at the field, and focus moves there on refusal.
            <span className={styles.errors} id={changeReason.errorId} role="alert">
              {t("artifactForm.changeReasonRequired")}
            </span>
          ) : null}
        </label>
      ) : null}

      {/* #1595, updated by #1732: an empty required field no longer disables
          the create action — the click explains itself at each field. This
          hint stays as a proactive summary of what is still missing. */}
      {!common.isReadOnly && create.artifactId === null && common.missingCreateValue && create.missingCreateLabels.length > 0 ? (
        <p
          id={CREATE_HINT_ID}
          data-testid={CREATE_HINT_ID}
          role="status"
          className={styles.createHint}
        >
          {t("artifactForm.createRequiredHint", {
            fields: create.missingCreateLabels.join(", "),
            defaultValue: "Required fields are still empty: {{fields}}",
          })}
        </p>
      ) : null}

      {!common.isReadOnly ? (
        <div className={styles.actions}>
          {deprecate.onDeprecate && deprecate.transition ? (
            <button
              type="button"
              className="btn-secondary"
              data-testid="artifact-form-deprecate"
              disabled={common.saving}
              onClick={deprecate.onRequest}
            >
              {t("artifactForm.deprecate")}
            </button>
          ) : null}
          {onCancel ? (
            <button type="button" className="btn-secondary" data-testid="artifact-form-cancel" disabled={common.saving} onClick={onCancel}>
              {t("actions.cancel")}
            </button>
          ) : null}
          <button
            type="submit"
            className="btn-primary"
            data-testid={create.saveTestId}
            // #1732: only an in-flight save disables the action. An empty
            // required field is reported on click (field-level role="alert" +
            // focus), never by a silent disabled state.
            disabled={common.saving}
            // Issue #1087: the shortcut has to be discoverable on the control
            // that also performs it. `aria-keyshortcuts` is the machine-
            // readable form (WAI-ARIA 1.2) and the only one assistive tech can
            // surface; the title carries the same fact for pointer users.
            // There is no app-wide shortcuts/help surface to list it in (the
            // only shortcut help in the repo is the workflow canvas's own),
            // so the button annotates itself rather than a new page appearing.
            aria-keyshortcuts={SAVE_SHORTCUT_ARIA}
            title={t("artifactForm.saveShortcutHint", "Speichern (Strg/Cmd+S)")}
          >
            {common.saving ? t("actions.saving") : t(create.artifactId === null ? "actions.create" : "actions.save")}
          </button>
        </div>
      ) : null}

      {deprecate.confirm && deprecate.transition ? (
        <ConfirmDialog
          title={t("artifactForm.deprecateTitle")}
          message={t("artifactForm.deprecateConfirm", {
            target: deprecate.transition.target_state,
          })}
          confirmLabel={t("artifactForm.deprecate")}
          cancelLabel={t("actions.cancel")}
          testId="artifact-form-deprecate-dialog"
          confirmTestId="artifact-form-deprecate-confirm"
          cancelTestId="artifact-form-deprecate-cancel"
          isSubmitting={common.saving}
          confirmDisabled={deprecate.missing}
          onConfirm={() => void deprecate.onConfirm()}
          onCancel={deprecate.onCancel}
        >
          {deprecate.needed ? (
            <label className={styles.field}>
              <span className={styles.label}>
                {t("artifactForm.deprecateReason")}
                <RequiredMark />
              </span>
              <textarea
                className={styles.control}
                data-testid="artifact-form-deprecate-reason"
                value={deprecate.value}
                // Same contract as the change-reason input above: the marker
                // alone is not machine-readable, so `required` + `aria-required`
                // both carry the flag.
                required
                aria-required="true"
                onChange={(event) => deprecate.onChangeReason(event.target.value)}
              />
            </label>
          ) : null}
        </ConfirmDialog>
      ) : null}
    </>
  );
}
