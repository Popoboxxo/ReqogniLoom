/**
 * ARCH-L1-001 ReactFrontend — <ConfirmDialog> (issue #672).
 *
 * Generic yes/no confirmation built on the shared <Dialog> primitive (ch.
 * 12.8) — same building block `ArchiveConfirmDialog` and
 * `ArchitectureForm`'s inline delete dialog already use, extracted here so
 * a third call site (unsaved-changes-before-navigation) does not hand-roll
 * a fourth ad-hoc confirm overlay.
 */

import { useTranslation } from 'react-i18next';
import { Dialog } from './Dialog';

export interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  testId?: string;
  /**
   * UI-24: while a confirm action is in flight (async `onConfirm`), Escape
   * and a backdrop click used to close the dialog anyway — the caller's
   * mutation kept running detached from any visible dialog. Callers that
   * track their own submitting state pass it here to suppress Escape/
   * backdrop/close-button dismissal and disable both footer buttons until
   * the action settles.
   */
  isSubmitting?: boolean;
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  testId = 'confirm-dialog',
  isSubmitting = false,
}: ConfirmDialogProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <Dialog
      title={title}
      onClose={() => {
        if (!isSubmitting) onCancel();
      }}
      closeOnBackdropClick={!isSubmitting}
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
            {cancelLabel ?? t('actions.cancel', 'Abbrechen')}
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
      <p data-testid={`${testId}-body`}>{message}</p>
    </Dialog>
  );
}

ConfirmDialog.displayName = 'ConfirmDialog';
