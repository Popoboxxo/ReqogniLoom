/**
 * ARCH-L1-001 ReactFrontend — <Dialog> (UI concept ch. 12.8).
 *
 * The binding modal primitive. Before this component the codebase had no
 * real dialog at all: nine call sites set `aria-modal="true"` on a plain
 * `<div>` *without* `role="dialog"` (which ARIA ignores, so screen readers
 * kept treating them as ordinary containers), and
 * `RequirementsList/ModalDialogBase.tsx` — despite the name — renders an
 * inline form with neither overlay nor focus handling.
 *
 * The contract of ch. 12.8, in full:
 *   - `role="dialog"` **and** `aria-modal="true"` **and** `aria-labelledby`,
 *   - focus moves to the first operable element when it opens,
 *   - Tab / Shift+Tab cycle inside the dialog,
 *   - `Escape` closes,
 *   - focus returns to the triggering element when it closes,
 *   - `title` is mandatory and should repeat the label of its trigger.
 *
 * Rendered through a portal into `document.body` so no ancestor
 * `overflow`, `transform` or `z-index` (SplitView panels, sticky headers)
 * can clip it.
 */

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  type MouseEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useFocusTrap } from "./use-focus-trap";
import styles from "./Dialog.module.css";

export interface DialogProps {
  /**
   * Accessible name of the dialog, wired up via `aria-labelledby`.
   * Mandatory — ch. 12.8 wants it to match the label of the button that
   * opened the dialog.
   */
  title: string;
  /** Called on Escape, on the close button and on a backdrop click. */
  onClose: () => void;
  children: ReactNode;
  /** Optional one-liner below the title, exposed as `aria-describedby`. */
  description?: string;
  /** Action row pinned to the bottom of the panel. */
  footer?: ReactNode;
  /** Panel width. Default `md`. */
  size?: "sm" | "md" | "lg";
  /** Focus target on open. Defaults to the first focusable element. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  /** Default `true`. Set to false for dialogs that must not be dismissed accidentally. */
  closeOnBackdropClick?: boolean;
  /** Default `true`. */
  showCloseButton?: boolean;
  testId?: string;
}

export function Dialog({
  title,
  onClose,
  children,
  description,
  footer,
  size = "md",
  initialFocusRef,
  closeOnBackdropClick = true,
  showCloseButton = true,
  testId = "dialog",
}: DialogProps): JSX.Element | null {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const reactId = useId();
  const titleId = `${reactId}-title`;
  const descriptionId = `${reactId}-description`;

  useFocusTrap({
    containerRef: panelRef,
    onEscape: onClose,
    initialFocusRef,
  });

  // While a modal is open the page behind it must not scroll away under
  // the scrim. The previous value is restored so nested dialogs and views
  // that already locked scrolling are not disturbed.
  useEffect(() => {
    const { body } = document;
    const previousOverflow = body.style.overflow;
    body.style.overflow = "hidden";
    return () => {
      body.style.overflow = previousOverflow;
    };
  }, []);

  const handleBackdropMouseDown = useCallback(
    (event: MouseEvent<HTMLDivElement>): void => {
      if (!closeOnBackdropClick) return;
      // `mousedown` on the overlay itself only: a drag that starts on a
      // text selection inside the panel and ends on the backdrop must not
      // close the dialog.
      if (event.target === event.currentTarget) onClose();
    },
    [closeOnBackdropClick, onClose],
  );

  // Guard for non-browser rendering (SSR, tooling) — there is no body to
  // portal into.
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      className={styles.overlay}
      data-testid={`${testId}-overlay`}
      onMouseDown={handleBackdropMouseDown}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        className={`${styles.panel} ${styles[size]}`}
        data-testid={testId}
        tabIndex={-1}
      >
        <div className={styles.header}>
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
          {showCloseButton && (
            <button
              type="button"
              className={styles.close}
              data-testid={`${testId}-close`}
              onClick={onClose}
              aria-label={t("dialog.closeLabel", "Dialog schließen")}
              title={t("dialog.close", "Schließen")}
            >
              <span aria-hidden="true">×</span>
            </button>
          )}
        </div>

        {description && (
          <p id={descriptionId} className={styles.description}>
            {description}
          </p>
        )}

        <div className={styles.content}>{children}</div>

        {footer && <div className={styles.footer}>{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
