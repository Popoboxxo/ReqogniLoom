/**
 * ARCH-L1-001 ReactFrontend — bottom-sheet behaviour for <Dialog> (issue #874).
 *
 * The smartphone presentation of the shared dialog (anchoring, width, rounded
 * top corners, safe-area padding) is pure CSS in `Dialog.module.css` — one
 * media query, no component involvement at all. Only two things genuinely
 * need JavaScript, and they live here so the component itself stays the thin
 * primitive it was:
 *
 *   1. `useSheetViewport` — mirrors `window.visualViewport` onto the panel as
 *      two custom properties while the sheet is open, so the CSS can cap the
 *      sheet to the *visible* area and lift it above the on-screen keyboard
 *      (issue DoD 3). Without it the sheet would be sized against `dvh`, which
 *      accounts for the collapsing browser chrome but not for the keyboard.
 *   2. `useSwipeToDismiss` — the drag handle's gesture: a downward drag past a
 *      threshold requests the same dismissal the close button, Escape and the
 *      backdrop already request.
 *
 * Neither hook touches ARIA, focus or the DOM structure: the accessible
 * contract of ch. 12.8 (role/aria-modal/aria-labelledby, focus trap, Escape,
 * focus restore) is unaffected by both, which is why they are safe to add to
 * an already-hardened primitive.
 */

import {
  useCallback,
  useEffect,
  useRef,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";

/**
 * How far (in CSS pixels) the handle must be dragged *down* before the
 * release dismisses the sheet. 64px is comfortably past the ~10px jitter of a
 * finger tap, and roughly a tenth of the smallest smartphone viewport this
 * targets (360px), so it cannot be triggered by a tap or a small wobble.
 */
export const SWIPE_DISMISS_THRESHOLD = 64;

export interface SwipeToDismissOptions {
  /** Called when a downward drag ends past the threshold. */
  onDismiss: () => void;
  /**
   * `false` disables the gesture entirely. <Dialog> passes its
   * `closeOnBackdropClick` here so a dialog that must not be dismissed
   * accidentally (e.g. <ConfirmDialog> while a delete is in flight) cannot be
   * dismissed by a swipe either — swipe, backdrop and Escape are one
   * dismissibility decision, not three.
   */
  enabled?: boolean;
  /** Override the distance threshold. Defaults to `SWIPE_DISMISS_THRESHOLD`. */
  threshold?: number;
}

export interface SwipeToDismissHandlers {
  onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
  onPointerCancel: (event: ReactPointerEvent<HTMLElement>) => void;
}

/**
 * Spread the result onto the sheet's drag handle.
 *
 * The sheet deliberately does not follow the finger: translating the panel
 * would make it a containing block for `position: fixed` descendants (the
 * interview widget and the workflow editor both render fixed chrome that can
 * appear inside a dialog), and a visual offset would fight the focus-trap
 * geometry for no accessible gain. The gesture is measured, not animated.
 *
 * A drag is only evaluated on release: what counts is where the finger ended
 * up, so pulling the sheet down and back up before letting go keeps it open.
 */
export function useSwipeToDismiss({
  onDismiss,
  enabled = true,
  threshold = SWIPE_DISMISS_THRESHOLD,
}: SwipeToDismissOptions): SwipeToDismissHandlers {
  const startYRef = useRef<number | null>(null);
  const draggedRef = useRef(0);

  const endDrag = useCallback((event: ReactPointerEvent<HTMLElement>): void => {
    startYRef.current = null;
    draggedRef.current = 0;
    // jsdom has no pointer capture at all, hence the optional calls.
    const element = event.currentTarget;
    if (element.hasPointerCapture?.(event.pointerId)) {
      element.releasePointerCapture(event.pointerId);
    }
  }, []);

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLElement>): void => {
      if (!enabled) return;
      // Ignore non-primary mouse buttons; a long-press/contextmenu on the
      // handle must not become a drag.
      if (event.pointerType === "mouse" && event.button !== 0) return;
      startYRef.current = event.clientY;
      draggedRef.current = 0;
      event.currentTarget.setPointerCapture?.(event.pointerId);
    },
    [enabled],
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>): void => {
      if (startYRef.current === null) return;
      // Only downward movement counts; an upward drag is not a dismissal
      // gesture and must not accumulate negative credit.
      draggedRef.current = Math.max(0, event.clientY - startYRef.current);
    },
    [],
  );

  const onPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLElement>): void => {
      if (startYRef.current === null) return;
      const dragged = draggedRef.current;
      endDrag(event);
      if (enabled && dragged >= threshold) onDismiss();
    },
    [enabled, endDrag, onDismiss, threshold],
  );

  const onPointerCancel = useCallback(
    (event: ReactPointerEvent<HTMLElement>): void => {
      endDrag(event);
    },
    [endDrag],
  );

  return { onPointerDown, onPointerMove, onPointerUp, onPointerCancel };
}

/**
 * Publishes the live visual viewport of `panelRef` as two custom properties:
 *
 *   `--sheet-viewport-height` — `visualViewport.height`; the height the sheet
 *   may occupy without sliding under the keyboard.
 *   `--sheet-keyboard-inset`  — how much of the layout viewport the keyboard
 *   (or any other on-screen UI) currently covers; the sheet is pushed up by
 *   exactly that much.
 *
 * Both default to sane values in `tokens.css`, so this is a progressive
 * enhancement: where `window.visualViewport` does not exist (desktop Firefox,
 * jsdom) the effect is a no-op and the CSS falls back to `dvh`. Nothing is
 * written while a dialog is open on a desktop viewport either, because no
 * media query consumes the properties above 640px.
 */
export function useSheetViewport(panelRef: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const viewport = window.visualViewport;
    const panel = panelRef.current;
    if (!viewport || !panel) return;

    const sync = (): void => {
      const visibleHeight = Math.round(viewport.height);
      const covered = Math.max(
        0,
        Math.round(window.innerHeight) - visibleHeight,
      );
      panel.style.setProperty(
        "--sheet-viewport-height",
        `${visibleHeight}px`,
      );
      panel.style.setProperty("--sheet-keyboard-inset", `${covered}px`);
    };

    sync();
    viewport.addEventListener("resize", sync);
    return () => {
      viewport.removeEventListener("resize", sync);
      // Leaving the properties behind would keep the *previous* dialog's
      // viewport when this panel's slot is reused by the next one.
      panel.style.removeProperty("--sheet-viewport-height");
      panel.style.removeProperty("--sheet-keyboard-inset");
    };
  }, [panelRef]);
}
