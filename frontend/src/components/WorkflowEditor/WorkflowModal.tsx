/**
 * REQ-177 — WorkflowModal: base modal shell for the editor dialogs (Phase 2).
 *
 * UI concept ch. 12.8: reused by the Add/Edit State, Add/Edit Transition and
 * Confirm dialogs so they share the same modal primitive as the rest of the
 * app instead of re-inventing overlay/focus-trap/Escape chrome. Backdrop,
 * The dialog role, the modal flag and the labelledby wiring, the Tab focus trap and
 * focus-restore-on-close now come from <Dialog>; this component only maps
 * WorkflowModal's narrower props (title/onClose/children/footer/testId) onto
 * it, so ConfirmDialog/StateDialog/TransitionDialog did not have to change.
 */

import type { ReactNode } from "react";
import { Dialog } from "../shared/Dialog";

interface WorkflowModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
  testId?: string;
  /**
   * UI-24: while a state/transition/confirm mutation is in flight (``busy``
   * in the calling dialog), Escape and a backdrop click must not discard the
   * dialog — the request keeps running with no dialog left to report back
   * to. Callers pass their own `busy` flag through here.
   */
  preventClose?: boolean;
}

export function WorkflowModal({
  title,
  onClose,
  children,
  footer,
  testId,
  preventClose = false,
}: WorkflowModalProps): JSX.Element {
  return (
    <Dialog
      title={title}
      onClose={() => {
        if (!preventClose) onClose();
      }}
      closeOnBackdropClick={!preventClose}
      size="sm"
      testId={testId}
      footer={footer}
    >
      {children}
    </Dialog>
  );
}
