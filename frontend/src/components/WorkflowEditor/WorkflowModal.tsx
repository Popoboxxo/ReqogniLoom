/**
 * REQ-177 — WorkflowModal: base modal shell for the editor dialogs (Phase 2).
 *
 * A lightweight glassmorphism modal matching the editor's dark-slate aesthetic
 * (design brief §10): centered 400px surface-raised card, backdrop, Escape to
 * close, initial focus moved into the dialog, a full Tab focus trap while open
 * (WCAG 2.1.2 / 2.4.3), and focus restored to the trigger on unmount. Reused by
 * the Add/Edit State, Add/Edit Transition and Confirm dialogs so they share one
 * primitive instead of re-inventing modal chrome.
 */

import { useEffect, useRef, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import styles from "./WorkflowEditor.module.css";

const FOCUSABLE_SELECTOR =
  'input, select, textarea, button, a[href], [tabindex]:not([tabindex="-1"])';

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
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    // Move focus to the first focusable control inside the dialog.
    const first = dialogRef.current?.querySelector<HTMLElement>(
      FOCUSABLE_SELECTOR
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
        return;
      }
      // WCAG 2.4.3 / 2.1.2 — trap Tab focus inside the dialog while it is open
      // so keyboard/screen-reader users cannot tab into the hidden background.
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        ).filter((el) => !el.hasAttribute("disabled"));
        if (focusable.length === 0) return;
        const firstEl = focusable[0];
        const lastEl = focusable[focusable.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === firstEl) {
          e.preventDefault();
          lastEl.focus();
        } else if (!e.shiftKey && active === lastEl) {
          e.preventDefault();
          firstEl.focus();
        }
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
            aria-label={t("workflow.modal.closeDialog")}
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
