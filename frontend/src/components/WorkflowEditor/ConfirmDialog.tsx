/**
 * REQ-177 — ConfirmDialog: destructive-action confirmation (design brief §9).
 *
 * Required before deleting a state or a transition. Reuses the WorkflowModal
 * shell so the confirmation matches the editor's aesthetic; the confirm button
 * is danger-styled.
 */

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
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
  /** Extra content rendered between the message and error (e.g. a checkbox). */
  children?: ReactNode;
  /** When true the confirm button is disabled (e.g. gate not yet satisfied). */
  confirmDisabled?: boolean;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  onConfirm,
  onClose,
  busy = false,
  errorMessage,
  children,
  confirmDisabled = false,
}: ConfirmDialogProps): JSX.Element {
  const { t } = useTranslation();
  return (
    <WorkflowModal
      title={title}
      onClose={onClose}
      preventClose={busy}
      testId="workflow-confirm-dialog"
      footer={
        <>
          <button
            type="button"
            className={styles.btnGhost}
            onClick={onClose}
            data-testid="workflow-confirm-cancel"
          >
            {t("actions.cancel")}
          </button>
          <button
            type="button"
            className={`${styles.btnPrimary} ${styles.btnDanger}`}
            onClick={() => void onConfirm()}
            disabled={busy || confirmDisabled}
            data-testid="workflow-confirm-submit"
          >
            {confirmLabel ?? t("workflow.confirmDialog.defaultConfirmLabel")}
          </button>
        </>
      }
    >
      <p className={styles.modalText}>{message}</p>
      {children}
      {errorMessage && (
        <p className={styles.modalError} role="alert" data-testid="workflow-confirm-error">
          {errorMessage}
        </p>
      )}
    </WorkflowModal>
  );
}
