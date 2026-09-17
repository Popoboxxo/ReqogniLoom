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
import { useTranslation } from "react-i18next";
import { Dialog } from "../shared/Dialog";
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
  onSubmit: (values: GoalFormValues) => void;
  onClose: () => void;
}

/** Stable id so the footer's submit button can live outside the <form>. */
const FORM_ID = "goal-form";

export function GoalFormDialog({
  editing,
  error = null,
  isSubmitting = false,
  onSubmit,
  onClose,
}: GoalFormDialogProps): JSX.Element {
  const { t } = useTranslation();
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

        <label htmlFor="goal-title" className={styles.label}>
          {t("goals.goalTitle", "Titel")}
        </label>
        <input
          ref={titleInputRef}
          id="goal-title"
          type="text"
          data-testid="goal-title-input"
          className={styles.input}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <label htmlFor="goal-description" className={styles.label}>
          {t("goals.goalDescription", "Beschreibung")}
        </label>
        <textarea
          id="goal-description"
          data-testid="goal-description-input"
          className={styles.textarea}
          rows={4}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

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
