/**
 * ARCH-L1-001 ReactFrontend — useFocusTrap (UI concept ch. 12.8).
 *
 * The keyboard half of the dialog contract, kept separate from <Dialog> so
 * it can be tested on its own and reused by any other overlay that has to
 * behave modally (command palette, decompose panel, …).
 *
 * Responsibilities, all of them required by ch. 12.8:
 *   1. move focus into the container when the trap activates,
 *   2. keep Tab / Shift+Tab cycling *inside* the container,
 *   3. report `Escape` to the owner,
 *   4. return focus to the element that was focused before activation.
 *
 * Deliberately not handled here: rendering, ARIA attributes and the
 * backdrop — those belong to the component, not to the trap.
 */

import { useEffect, useRef, type RefObject } from "react";

/**
 * Elements that can receive focus by keyboard. `[tabindex="-1"]` is
 * excluded on purpose: it marks programmatic focus targets (such as the
 * dialog panel itself), which must not become Tab stops.
 */
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "area[href]",
  "button:not([disabled])",
  'input:not([disabled]):not([type="hidden"])',
  "select:not([disabled])",
  "textarea:not([disabled])",
  "iframe",
  "audio[controls]",
  "video[controls]",
  '[contenteditable]:not([contenteditable="false"])',
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/**
 * Returns the focusable descendants of `container` in DOM order.
 *
 * Visibility is decided by attributes only (`hidden`, `aria-hidden`,
 * `inert`) rather than by layout: jsdom reports no boxes at all, so a
 * geometry-based filter would report *every* element as hidden in tests
 * while behaving differently in the browser.
 *
 * `tabindex="-1"` is excluded explicitly (issue #800) rather than only via
 * the `[tabindex]:not([tabindex="-1"])` selector branch: that branch alone
 * only covers elements with no *other* matching selector (e.g. a plain
 * `<div tabindex="-1">`). A natively focusable element such as
 * `<button tabindex="-1">` still matches the unconditional
 * `button:not([disabled])` branch, so without this filter an explicit
 * `tabIndex={-1}` on a `<button>` (used to pull a control out of the Tab
 * cycle, e.g. the Dialog's close button) had no effect at all.
 */
export function getFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter(
    (element) =>
      element.getAttribute("tabindex") !== "-1" &&
      !element.hasAttribute("hidden") &&
      element.getAttribute("aria-hidden") !== "true" &&
      !element.closest("[inert]") &&
      !element.closest('[aria-hidden="true"]'),
  );
}

export interface FocusTrapOptions {
  /** The element the focus is confined to. */
  containerRef: RefObject<HTMLElement | null>;
  /** The trap only runs while this is true. Default: `true`. */
  enabled?: boolean;
  /** Called on `Escape`. Usually closes the owning overlay. */
  onEscape?: () => void;
  /**
   * Focus target on activation. Defaults to the first focusable
   * descendant, and to the container itself when there is none.
   */
  initialFocusRef?: RefObject<HTMLElement | null>;
  /**
   * Return focus to the previously focused element on deactivation.
   * Default: `true` — ch. 12.8 requires it; the escape hatch exists for
   * callers that navigate away as part of closing.
   */
  restoreFocus?: boolean;
}

/**
 * Confines keyboard focus to `containerRef` while `enabled`.
 *
 * The container must be focusable programmatically (`tabIndex={-1}`) so
 * that a dialog without any control still takes focus away from the page
 * behind it.
 */
export function useFocusTrap({
  containerRef,
  enabled = true,
  onEscape,
  initialFocusRef,
  restoreFocus = true,
}: FocusTrapOptions): void {
  // `onEscape` is very commonly an inline arrow function at the call site
  // (`onClose={() => setOpen(false)}`), which gets a fresh identity on
  // every render of the *parent* — including renders triggered by typing
  // into a controlled input inside this very dialog. If the setup effect
  // below depended on `onEscape` directly, it would tear down and re-run
  // `focusInitial()` on every such render, yanking focus away from the
  // input mid-keystroke. Storing the latest callback in a ref — updated on
  // every render via this separate, cheap effect — decouples "the effect
  // that wires up DOM listeners and moves focus" from "which closure gets
  // invoked," while still always calling the *latest* `onEscape`, never a
  // stale one.
  const onEscapeRef = useRef(onEscape);
  useEffect(() => {
    onEscapeRef.current = onEscape;
  });

  useEffect(() => {
    if (!enabled) return;
    const container = containerRef.current;
    if (!container) return;

    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    const focusInitial = (): void => {
      const explicit = initialFocusRef?.current;
      if (explicit) {
        explicit.focus();
        return;
      }
      const [first] = getFocusableElements(container);
      (first ?? container).focus();
    };

    focusInitial();

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        // Stop here: an outer overlay listening on the document must not
        // also close when the innermost one handles the key.
        event.preventDefault();
        event.stopPropagation();
        onEscapeRef.current?.();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = getFocusableElements(container);
      if (focusable.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const insideTrap = active instanceof Node && container.contains(active);

      if (event.shiftKey) {
        if (!insideTrap || active === first || active === container) {
          event.preventDefault();
          last.focus();
        }
        return;
      }
      if (!insideTrap || active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    /**
     * Safety net for focus moves the key handler cannot see — a click on
     * the page behind the dialog, or `element.focus()` called by other
     * code. Focus inside a *nested* dialog is left alone so stacked
     * overlays do not fight over it.
     */
    const handleFocusIn = (event: FocusEvent): void => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      if (container.contains(target)) return;
      if (target.closest('[role="dialog"]')) return;
      focusInitial();
    };

    container.addEventListener("keydown", handleKeyDown);
    document.addEventListener("focusin", handleFocusIn);

    return () => {
      container.removeEventListener("keydown", handleKeyDown);
      // Removed before the focus is restored — otherwise the safety net
      // would immediately pull focus back into the closing container.
      document.removeEventListener("focusin", handleFocusIn);
      if (restoreFocus && previouslyFocused?.isConnected) {
        previouslyFocused.focus();
      }
    };
  }, [containerRef, enabled, initialFocusRef, restoreFocus]);
}
