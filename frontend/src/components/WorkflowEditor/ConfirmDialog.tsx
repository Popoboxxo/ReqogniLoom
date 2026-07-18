/**
 * REQ-177 — ConfirmDialog: destructive-action confirmation (design brief §9).
 *
 * Required before deleting a state or a transition. Reuses the WorkflowModal
 * shell so the confirmation matches the editor's aesthetic; the confirm button
 * is danger-styled.
 */

import { WorkflowModal } from "./WorkflowModal";
import styles from "./WorkflowEditor.module.css";

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => Promise<void> | void;
  onClose: () => void;
  busy?: boolean;
  errorMessage?: string | null;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Delete",
  onConfirm,
  onClose,
  busy = false,
  errorMessage,
}: ConfirmDialogProps): JSX.Element {
  return (
    <WorkflowModal
      title={title}
      onClose={onClose}
      testId="workflow-confirm-dialog"
      footer={
        <>
          <button
            type="button"
            className={styles.btnGhost}
            onClick={onClose}
            data-testid="workflow-confirm-cancel"
          >
            Cancel
          </button>
          <button
            type="button"
            className={`${styles.btnPrimary} ${styles.btnDanger}`}
            onClick={() => void onConfirm()}
            disabled={busy}
            data-testid="workflow-confirm-submit"
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p className={styles.modalText}>{message}</p>
      {errorMessage && (
        <p className={styles.modalError} role="alert" data-testid="workflow-confirm-error">
          {errorMessage}
        </p>
      )}
    </WorkflowModal>
  );
}
