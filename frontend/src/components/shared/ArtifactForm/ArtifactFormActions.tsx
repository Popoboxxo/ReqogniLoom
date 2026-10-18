/**
 * Bottom action area of the definition-driven artifact form: the change-reason
 * input, the Save/Deprecate/Cancel row and the deprecate confirmation dialog.
 *
 * Extracted from `ArtifactForm.tsx` (Phase 5b decomposition, FE-01 / F-01).
 * Renders inside the same `<form>` and produces the identical DOM (a component
 * boundary adds no element). All state and handlers come from
 * `useArtifactFormState`; this file is the presentation of the action area.
 */

import type { RefObject } from "react";
import { useTranslation } from "react-i18next";

import type { WorkflowAllowedTransition } from "../../../api/workflow-transitions";
import { SAVE_SHORTCUT_ARIA } from "../../../hooks/useSaveShortcut";
import { ConfirmDialog } from "../ConfirmDialog";
import styles from "./ArtifactForm.module.css";

export interface ArtifactFormActionsProps {
  isReadOnly: boolean;
  saving: boolean;
  artifactId: string | null;
  saveTestId: string;
  missingCreateValue: boolean;
  onCancel?: () => void;
  changeReasonNeeded: boolean;
  changeReason: string;
  changeReasonInvalid: boolean;
  changeReasonRef: RefObject<HTMLInputElement | null>;
  changeReasonErrorId: string;
  onChangeChangeReason: (value: string) => void;
  onDeprecate?: (targetState: string, changeReason?: string) => Promise<void>;
  deprecateTransition: WorkflowAllowedTransition | undefined;
  deprecateReasonNeeded: boolean;
  deprecateReasonMissing: boolean;
  deprecateReason: string;
  confirmDeprecate: boolean;
  onRequestDeprecate: () => void;
  onCancelDeprecate: () => void;
  onChangeDeprecateReason: (value: string) => void;
  onConfirmDeprecate: () => Promise<void>;
}

export function ArtifactFormActions({
  isReadOnly,
  saving,
  artifactId,
  saveTestId,
  missingCreateValue,
  onCancel,
  changeReasonNeeded,
  changeReason,
  changeReasonInvalid,
  changeReasonRef,
  changeReasonErrorId,
  onChangeChangeReason,
  onDeprecate,
  deprecateTransition,
  deprecateReasonNeeded,
  deprecateReasonMissing,
  deprecateReason,
  confirmDeprecate,
  onRequestDeprecate,
  onCancelDeprecate,
  onChangeDeprecateReason,
  onConfirmDeprecate,
}: ArtifactFormActionsProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <>
      {changeReasonNeeded ? (
        <label className={styles.field}>
          <span className={`${styles.label} ${styles.required}`}>
            {t("artifactForm.changeReason")}
          </span>
          <input
            className={`${styles.control} ${changeReasonInvalid ? styles.controlInvalid : ""}`}
            data-testid="artifact-form-change-reason"
            type="text"
            value={changeReason}
            ref={changeReasonRef}
            aria-required="true"
            aria-invalid={changeReasonInvalid || undefined}
            aria-describedby={changeReasonInvalid ? changeReasonErrorId : undefined}
            onChange={(event) => onChangeChangeReason(event.target.value)}
          />
          {changeReasonInvalid ? (
            // Issue #977 (proof-journey finding): the save was refused, but the
            // reason appeared only in the banner at the very top of the form
            // while this field sits below every section. A user who clicked
            // Save saw nothing happen where they were looking. The message now
            // also sits at the field, and focus moves there on refusal.
            <span className={styles.errors} id={changeReasonErrorId} role="alert">
              {t("artifactForm.changeReasonRequired")}
            </span>
          ) : null}
        </label>
      ) : null}

      {!isReadOnly ? (
        <div className={styles.actions}>
          {onDeprecate && deprecateTransition ? (
            <button
              type="button"
              className="btn-secondary"
              data-testid="artifact-form-deprecate"
              disabled={saving}
              onClick={onRequestDeprecate}
            >
              {t("artifactForm.deprecate")}
            </button>
          ) : null}
          {onCancel ? (
            <button type="button" className="btn-secondary" data-testid="artifact-form-cancel" disabled={saving} onClick={onCancel}>
              {t("actions.cancel")}
            </button>
          ) : null}
          <button
            type="submit"
            className="btn-primary"
            data-testid={saveTestId}
            disabled={saving || missingCreateValue}
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
            {saving ? t("actions.saving") : t(artifactId === null ? "actions.create" : "actions.save")}
          </button>
        </div>
      ) : null}

      {confirmDeprecate && deprecateTransition ? (
        <ConfirmDialog
          title={t("artifactForm.deprecateTitle")}
          message={t("artifactForm.deprecateConfirm", {
            target: deprecateTransition.target_state,
          })}
          confirmLabel={t("artifactForm.deprecate")}
          cancelLabel={t("actions.cancel")}
          testId="artifact-form-deprecate-dialog"
          confirmTestId="artifact-form-deprecate-confirm"
          cancelTestId="artifact-form-deprecate-cancel"
          isSubmitting={saving}
          confirmDisabled={deprecateReasonMissing}
          onConfirm={() => void onConfirmDeprecate()}
          onCancel={onCancelDeprecate}
        >
          {deprecateReasonNeeded ? (
            <label className={styles.field}>
              <span className={`${styles.label} ${styles.required}`}>
                {t("artifactForm.deprecateReason")}
              </span>
              <textarea
                className={styles.control}
                data-testid="artifact-form-deprecate-reason"
                value={deprecateReason}
                aria-required="true"
                onChange={(event) => onChangeDeprecateReason(event.target.value)}
              />
            </label>
          ) : null}
        </ConfirmDialog>
      ) : null}
    </>
  );
}
