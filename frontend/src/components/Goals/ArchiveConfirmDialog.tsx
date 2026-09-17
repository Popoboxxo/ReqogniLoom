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
 *
 * UI-29 (Systemaudit 2026-08-27 AP-5): the archive move previously sent a
 * mechanically generated `change_reason` string ("Statuswechsel nach
 * Archiviert.") whenever the target workflow demanded one, silently
 * defeating the audit-trail intent of the `requires_change_reason` gate —
 * see the (now resolved) scope-boundary comment on `GoalsPage.runTransition`
 * and `MainGoalPanel.handleArchive`. This dialog now prompts for a real
 * reason (mirrors `WorkflowStatusEditor`'s reason-textarea pattern:
 * confirm disabled until non-empty) whenever `requiresChangeReason` is true
 * for the move being confirmed; callers fall back to a computed default only
 * as a defense-in-depth safety net if the reason is somehow still empty.
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "../shared/Dialog";
import styles from "./Goals.module.css";

export interface ArchiveConfirmDialogProps {
  /** Title of the artifact about to be archived, quoted in the body text. */
  itemLabel: string;
  /** Label of the confirming button — the workflow's own target-state label. */
  confirmLabel: string;
  /**
   * UI-29: when true, the WorkflowEngine's `requires_change_reason` gate
   * applies to this move — the dialog then requires a non-empty reason
   * before the confirm button is enabled, instead of letting the caller
   * synthesise one.
   */
  requiresChangeReason?: boolean;
  isSubmitting?: boolean;
  /** Called with the user-entered (trimmed) reason, `""` when not required. */
  onConfirm: (changeReason: string) => void;
  onCancel: () => void;
  testId?: string;
}

export function ArchiveConfirmDialog({
  itemLabel,
  confirmLabel,
  requiresChangeReason = false,
  isSubmitting = false,
  onConfirm,
  onCancel,
  testId = "goal-archive-dialog",
}: ArchiveConfirmDialogProps): JSX.Element {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const reasonMissing = requiresChangeReason && !reason.trim();

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
            onClick={() => onConfirm(reason.trim())}
            disabled={isSubmitting || reasonMissing}
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
      {requiresChangeReason && (
        <div className={styles.dialogHint}>
          <label htmlFor={`${testId}-reason`} className={styles.label}>
            {t("goals.archiveReasonLabel", "Begründung (Pflichtfeld)")}
          </label>
          <textarea
            id={`${testId}-reason`}
            data-testid={`${testId}-reason`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={isSubmitting}
            rows={2}
            placeholder={t(
              "goals.archiveReasonPlaceholder",
              "Warum wird dieses Artefakt archiviert?",
            )}
            className={styles.textarea}
          />
        </div>
      )}
    </Dialog>
  );
}

ArchiveConfirmDialog.displayName = "ArchiveConfirmDialog";
