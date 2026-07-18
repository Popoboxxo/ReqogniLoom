/**
 * REQ-177 — WorkflowModal: base modal shell for the editor dialogs (Phase 2).
 *
 * A lightweight glassmorphism modal matching the editor's dark-slate aesthetic
 * (design brief §10): centered 400px surface-raised card, backdrop, Escape to
 * close, initial focus moved into the dialog, and focus restored to the trigger
 * on unmount. Reused by the Add/Edit State, Add/Edit Transition and Confirm
 * dialogs so they share one primitive instead of re-inventing modal chrome.
 */

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import styles from "./WorkflowEditor.module.css";

interface WorkflowModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
  testId?: string;
}

export function WorkflowModal({
  title,
  onClose,
  children,
  footer,
  testId,
}: WorkflowModalProps): JSX.Element {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    // Move focus to the first focusable control inside the dialog.
    const first = dialogRef.current?.querySelector<HTMLElement>(
      "input, select, textarea, button"
    );
    first?.focus();
    return () => {
      previouslyFocused.current?.focus?.();
    };
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  return (
    <div
      className={styles.modalBackdrop}
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        data-testid={testId}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>{title}</h2>
          <button
            type="button"
            className={styles.modalClose}
            aria-label="Close dialog"
            onClick={onClose}
            data-testid="workflow-modal-close"
          >
            <X size={16} />
          </button>
        </header>
        <div className={styles.modalBody}>{children}</div>
        <footer className={styles.modalFooter}>{footer}</footer>
      </div>
    </div>
  );
}
