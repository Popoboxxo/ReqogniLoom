/**
 * ARCH-L1-001 ReactFrontend — <ConfirmDialog> (issue #672).
 *
 * Generic yes/no confirmation built on the shared <Dialog> primitive (ch.
 * 12.8) — same building block `ArchiveConfirmDialog` already uses, extracted
 * here so further call sites do not hand-roll ad-hoc confirm overlays.
 *
 * Issue #670 made this the single delete-confirmation for every artifact
 * type. Deleting used to look different in three places: architecture opened
 * a Dialog, the test case / ADR / risk / issue / need forms confirmed inline
 * in their header ("Löschen? Ja / Nein"), and the requirement list showed a
 * banner above the tree. All of them route through this component now, so
 * one deletion looks and behaves like every other — including Escape and
 * backdrop dismissal, which the inline variants never offered.
 */

import type { ReactNode } from 'react';
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
  /**
   * Issue #670: the artifact forms (architecture / test case / ADR / risk /
   * need / issue / requirement) each already ship a stable, E2E-referenced
   * `data-testid` on their confirm and cancel buttons (e.g.
   * `confirm-delete-btn`, `tc-cancel-delete-btn`). Migrating those hand-rolled
   * confirm affordances onto this component must not silently rename them and
   * break the Playwright selectors, so callers may keep their historical ids
   * here. Unset, the ids stay derived from `testId` as before.
   */
  confirmTestId?: string;
  cancelTestId?: string;
  /**
   * Issue #811: some deletions require additional input (e.g. a mandatory
   * `change_reason` under the extended preset) that a plain yes/no message
   * cannot capture. Rendered below the confirmation message, inside the same
   * dialog, so callers can add a field without hand-rolling their own modal.
   */
  children?: ReactNode;
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
  confirmTestId,
  cancelTestId,
  children,
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
            data-testid={cancelTestId ?? `${testId}-cancel`}
            onClick={onCancel}
            disabled={isSubmitting}
          >
            {cancelLabel ?? t('actions.cancel', 'Abbrechen')}
          </button>
          <button
            type="button"
            className="btn-danger"
            data-testid={confirmTestId ?? `${testId}-confirm`}
            onClick={onConfirm}
            disabled={isSubmitting}
          >
            {confirmLabel}
          </button>
        </>
      }
    >
      <p data-testid={`${testId}-body`}>{message}</p>
      {children}
    </Dialog>
  );
}

ConfirmDialog.displayName = 'ConfirmDialog';
