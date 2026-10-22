/**
 * ARCH-L1-001 ReactFrontend — GoalFormDialog (REQ-L2-TE-020, issue #238).
 *
 * Create/edit surface for a single Goal. Issue #238: every other artifact
 * route creates through a modal (`<Dialog>`, UI concept ch. 12.8) while Goals
 * pushed a bare field stack into the detail pane, which meant the detail pane
 * did two jobs at once and the create flow had no title, no scrim, no focus
 * trap and no Escape.
 *
 * "Edit" is not an in-place update: it appends a new immutable row to the same
 * lineage (`goalsApi.createVersion`, design spec 2.3), which is why the submit
 * label changes with the mode. The API call itself lives in the page so that a
 * rejection surfaces in exactly one place (ch. 12.12) — this component only
 * owns the field state and hands the values up.
 */

import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "../shared/Dialog";
import { FormField } from "../shared/FormField";
import { useFieldContract } from "../../hooks/useFieldContract";
import type { Goal } from "../../types";
import styles from "./Goals.module.css";

export interface GoalFormValues {
  title: string;
  description: string;
}

export interface GoalFormDialogProps {
  /** `null` = create a new lineage; a Goal = append a version to its lineage. */
  editing: Goal | null;
  /**
   * Rejection of the last submit. Rendered inside the dialog so a failed
   * action is stated where it happened and the dialog stays open (ch. 12.12).
   */
  error?: string | null;
  /** Blocks double submits while the page's request is in flight. */
  isSubmitting?: boolean;
  /** GitHub #1392: `details[].field` messages from the rejected save. */
  fieldErrors?: Record<string, string[]>;
  /**
   * Element that opened this dialog (issue #1405 / R1-07). The route owns the
   * ref and hands it over here: the header CTA carries
   * `disabled={Boolean(form)}`, so the browser blurs it in the same commit
   * that mounts the dialog and the focus trap's own `document.activeElement`
   * snapshot would be `<body>`. See `<Dialog triggerRef>`.
   */
  triggerRef?: RefObject<HTMLElement | null>;
  onSubmit: (values: GoalFormValues) => void;
  onClose: () => void;
}

/** Stable id so the footer's submit button can live outside the <form>. */
const FORM_ID = "goal-form";

export function GoalFormDialog({
  editing,
  error = null,
  isSubmitting = false,
  fieldErrors,
  triggerRef,
  onSubmit,
  onClose,
}: GoalFormDialogProps): JSX.Element {
  const { t } = useTranslation();
  // GitHub #1393/#1392: required + `maxLength` from the workspace's own
  // configuration (`Goal.title` is required and 255 characters). The dialog is
  // only mounted while open, so the definition is fetched on demand.
  const { field } = useFieldContract("Goal", { enabled: true });
  const errors = fieldErrors ?? {};
  const [title, setTitle] = useState(editing?.title ?? "");
  const [description, setDescription] = useState(editing?.description ?? "");
  const titleInputRef = useRef<HTMLInputElement>(null);

  // Switching the edited goal (or from edit to create) without remounting
  // must not keep the previous values in the fields.
  useEffect(() => {
    setTitle(editing?.title ?? "");
    setDescription(editing?.description ?? "");
  }, [editing]);

  // ch. 12.8: the dialog title repeats the label of the button that opened it.
  const dialogTitle = editing
    ? t("goals.editTitle", "Ziel bearbeiten")
    : t("goals.newGoal", "Neues Ziel");

  return (
    <Dialog
      title={dialogTitle}
      onClose={onClose}
      testId="goal-form-dialog"
      initialFocusRef={titleInputRef}
      triggerRef={triggerRef}
      footer={
        <>
          <button
            type="button"
            className="btn-secondary"
            data-testid="goal-edit-cancel-button"
            onClick={onClose}
            disabled={isSubmitting}
          >
            {t("actions.cancel", "Abbrechen")}
          </button>
          <button
            type="submit"
            form={FORM_ID}
            className="btn-primary"
            data-testid="goal-create-button"
            disabled={isSubmitting || !title.trim()}
          >
            {isSubmitting
              ? t("actions.saving", "Speichern...")
              : editing
                ? t("goals.saveVersion", "Neue Version speichern")
                : t("goals.create", "Ziel anlegen")}
          </button>
        </>
      }
    >
      <form
        id={FORM_ID}
        data-testid="goal-form"
        className={styles.formGrid}
        // Native `required` on the controls drives `:required` styling and the
        // accessible flag; `noValidate` keeps the browser bubble out of the
        // app's own `details[].field` error flow (same as `ArtifactForm`).
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!title.trim()) return;
          onSubmit({ title, description });
        }}
      >
        {editing && (
          <p className={styles.dialogHint} data-testid="goal-form-version-hint">
            {t(
              "goals.editHint",
              "Bearbeiten legt eine neue Version desselben Ziels an. Die bisherige Version bleibt in der Historie erhalten.",
            )}
          </p>
        )}

        <FormField
          htmlFor="goal-title"
          label={t("goals.goalTitle", "Titel")}
          required={field("title").required}
          error={errors.title?.join(", ")}
          labelClassName={styles.label}
        >
          <input
            ref={titleInputRef}
            id="goal-title"
            type="text"
            data-testid="goal-title-input"
            className={styles.input}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            {...field("title").controlProps}
          />
        </FormField>

        <FormField
          htmlFor="goal-description"
          label={t("goals.goalDescription", "Beschreibung")}
          required={field("description").required}
          error={errors.description?.join(", ")}
          labelClassName={styles.label}
        >
          <textarea
            id="goal-description"
            data-testid="goal-description-input"
            className={styles.textarea}
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            {...field("description").controlProps}
          />
        </FormField>

        {error && (
          <p role="alert" data-testid="goal-form-error" className={styles.error}>
            {error}
          </p>
        )}
      </form>
    </Dialog>
  );
}

GoalFormDialog.displayName = "GoalFormDialog";
