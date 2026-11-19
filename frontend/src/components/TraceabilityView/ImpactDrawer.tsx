/**
 * ImpactDrawer — Task 10 (Schnitt 4a).
 *
 * The on-demand replacement for /traceability's permanent Impact column.
 * Triggered by the "Open Impact Analysis" button in the list view, it renders
 * the existing `ImpactDetailPanel` content plus the resolved impact preset in
 * a right-hand overlay drawer.
 *
 * This is a **real modal** (`role="dialog"` + `aria-modal="true"`), unlike the
 * non-modal trace-station popover of §3.4: it portals into `document.body`,
 * takes focus on open, cycles Tab inside via the shared `useFocusTrap`, closes
 * on Escape and returns focus to the trigger. The trap and the ARIA pattern
 * are the ones defined by the shared `Dialog` primitive (UI concept ch. 12.8);
 * only the presentation (right-hand drawer instead of centred panel) differs.
 *
 * Accessibility baseline only — the binding WCAG verdict stays with
 * `accessibility-specialist`.
 */

import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useFocusTrap } from "../shared/Dialog";
import type { ImpactPreset } from "../ImpactView/impact-preset";
import styles from "./TraceabilityView.module.css";

export interface ImpactDrawerProps {
  /** Preset resolved by TraceabilityView from the loaded workspace data. */
  preset: ImpactPreset | null;
  /** Called on Escape and on the close button. */
  onClose: () => void;
  /** Trigger button — focus is returned here when the drawer closes. */
  triggerRef: RefObject<HTMLElement | null>;
  /** The existing ImpactDetailPanel content (artifact picker + run action). */
  children?: ReactNode;
}

export function ImpactDrawer({
  preset,
  onClose,
  triggerRef,
  children,
}: ImpactDrawerProps): JSX.Element | null {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const reactId = useId();
  const titleId = `${reactId}-impact-drawer-title`;

  useFocusTrap({
    containerRef: panelRef,
    onEscape: onClose,
    triggerRef,
  });

  // A modal must not let the page behind it scroll away under the scrim.
  // Restore the previous value so nested overlays are not disturbed.
  useEffect(() => {
    const { body } = document;
    const previousOverflow = body.style.overflow;
    body.style.overflow = "hidden";
    return () => {
      body.style.overflow = previousOverflow;
    };
  }, []);

  // Non-browser tooling (SSR) has no portal target.
  if (typeof document === "undefined") return null;

  return createPortal(
    <div className={styles.impactDrawerOverlay}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={styles.impactDrawer}
        data-testid="impact-drawer"
        tabIndex={-1}
      >
        <div className={styles.impactDrawerHeader}>
          <h2 id={titleId} className={styles.impactDrawerTitle}>
            {t("traceability.impactTitle")}
          </h2>
          <button
            type="button"
            className={`btn-icon ${styles.impactDrawerClose}`}
            data-testid="impact-drawer-close"
            onClick={onClose}
            aria-label={t("dialog.closeLabel")}
            title={t("dialog.close")}
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>

        <div className={styles.impactDrawerContent}>
          {preset ? (
            <dl className={styles.impactDrawerData} data-testid="impact-drawer-data">
              <dt>{t("traceability.impactArtifact")}</dt>
              <dd>
                {preset.artifactType}
                {preset.artifactType && preset.title ? ": " : ""}
                {preset.title || preset.id}
              </dd>
              <dt>ID</dt>
              <dd>{preset.id}</dd>
            </dl>
          ) : (
            <p className={styles.impactDrawerEmpty} data-testid="impact-drawer-empty">
              {t("traceability.noArtifacts")}
            </p>
          )}
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}

export default ImpactDrawer;
