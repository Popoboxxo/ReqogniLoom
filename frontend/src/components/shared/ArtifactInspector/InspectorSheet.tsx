/**
 * ArtifactInspector — sheet / full-screen wrapper (issue #1762, M1).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-089, REQ-L1-093
 *
 * Presentation only. The sheet is the R3/R4 form of the inspector and the
 * full-screen surface is its R5 form (spec §4.2, SCR-INSP-03/04); both render
 * the same header + tablist + area body the inline panel renders, so the two
 * forms cannot drift apart.
 *
 * The sheet is **non-modal** (spec §4.2, D3/B1): no scrim, no focus trap.
 * What is non-modal is the *dismissal* — it is not a dialog, so it must not
 * claim `role="dialog"`; the covered detail area is marked `inert` by the
 * shell instead (`useInertBehindSheet`). `Esc` is handled here because focus
 * is moved into the sheet on open and therefore starts inside this subtree.
 */

import type { ReactNode } from "react";

import { INSPECTOR_HEADING_ID, INSPECTOR_TEST_IDS } from "./inspectorContract";
import styles from "./InspectorShell.module.css";

export interface InspectorSheetProps {
  mode: "sheet" | "fullscreen";
  onClose: () => void;
  children: ReactNode;
}

export function InspectorSheet({
  mode,
  onClose,
  children,
}: InspectorSheetProps): JSX.Element {
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>): void {
    // Spec §5.1: Esc closes the sheet. The composer keeps its draft — closing
    // is not a form reset (the textarea state lives in CommentPanel).
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
    }
  }

  return (
    <div
      className={mode === "fullscreen" ? styles.fullscreen : styles.sheet}
      // A named group, not a dialog: the sheet is non-modal (spec §4.2) and
      // the label is the inspector heading rendered inside it.
      role="region"
      aria-labelledby={INSPECTOR_HEADING_ID}
      data-testid={INSPECTOR_TEST_IDS.surface}
      data-inspector-form={mode}
      onKeyDown={onKeyDown}
    >
      {children}
    </div>
  );
}
