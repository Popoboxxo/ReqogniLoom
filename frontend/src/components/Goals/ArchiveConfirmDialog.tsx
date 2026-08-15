/**
 * ARCH-L1-001 ReactFrontend — ArchiveConfirmDialog (issue #238).
 *
 * Confirmation for the one move on the Goals route that removes an artifact
 * from the working set. Goal/MainGoal cannot be deleted (the backend answers
 * DELETE with a deliberate 405 — see `goal-workflow.ts`), so archiving *is*
 * the delete affordance, and `GoalService.list_current()` drops archived rows
 * from the list: the artifact visibly disappears.
 *
 * ch. 12.8 / 14.2: the dialog title repeats the label of the button that
 * opened it, the body states what will happen in one sentence, and the
 * confirming button names the result ("Archivieren") rather than "OK".
 * Nothing is lost — the archived version stays in the lineage's history —
 * which the body says explicitly so the confirmation is not read as a delete.
 */

import { useTranslation } from "react-i18next";
import { Dialog } from "../shared/Dialog";
import styles from "./Goals.module.css";

export interface ArchiveConfirmDialogProps {
  /** Title of the artifact about to be archived, quoted in the body text. */
  itemLabel: string;
  /** Label of the confirming button — the workflow's own target-state label. */
  confirmLabel: string;
  isSubmitting?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  testId?: string;
}

export function ArchiveConfirmDialog({
  itemLabel,
  confirmLabel,
  isSubmitting = false,
  onConfirm,
  onCancel,
  testId = "goal-archive-dialog",
}: ArchiveConfirmDialogProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <Dialog
      title={confirmLabel}
      onClose={onCancel}
      testId={testId}
      size="sm"
      footer={
        <>
          <button
            type="button"
            className="btn-secondary"
            data-testid={`${testId}-cancel`}
            onClick={onCancel}
            disabled={isSubmitting}
          >
            {t("actions.cancel", "Abbrechen")}
          </button>
          <button
            type="button"
            className="btn-danger"
            data-testid={`${testId}-confirm`}
            onClick={onConfirm}
            disabled={isSubmitting}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className={styles.dialogHint} data-testid={`${testId}-body`}>
        {t("goals.archiveConfirm", {
          title: itemLabel,
          defaultValue:
            "„{{title}}“ wird archiviert und verschwindet aus der Liste. Die Version bleibt in der Historie erhalten.",
        })}
      </p>
    </Dialog>
  );
}

ArchiveConfirmDialog.displayName = "ArchiveConfirmDialog";
