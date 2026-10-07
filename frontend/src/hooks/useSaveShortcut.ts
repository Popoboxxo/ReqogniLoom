/**
 * Issue #1087 — the `Ctrl`/`Cmd`+`S` save shortcut, as ONE reusable hook.
 *
 * Why a hook and not a `<form onKeyDown>`: the shortcut has to work from
 * anywhere on the page, including from a text field the user never tabs
 * through and from a dialog whose focus trap has not settled yet. A handler on
 * the form element only fires while focus happens to be inside it. A
 * document-level listener is the honest equivalent, and it has to be torn down
 * again on unmount — otherwise a form that unmounts on selection change keeps
 * answering `Ctrl+S` from the void.
 *
 * The three behaviour rules from the issue, and where they live
 * -----------------------------------------------------------------
 * 1. **unsaved changes → save.** The hook does not decide what "dirty" means;
 *    it calls `onSave` and lets the form's own submit path apply its own gates
 *    (the change-reason gate, server validation). That keeps the keystroke and
 *    the button on exactly one code path — a second, shortcut-only save
 *    implementation is precisely how the two drift apart. The one exception is
 *    `canSave`: a form whose required fields are empty must not be *called* at
 *    all, or the shortcut silently early-returns (see below).
 * 2. **save in flight → disabled, no double submit.** `isSaving` is read from
 *    a ref, so a second `Ctrl+S` inside the same tick (before React has
 *    re-rendered and re-read the state) is still swallowed. Note that this
 *    hook can only guard the *shortcut*; a form that also has a visible Save
 *    button needs its own same-tick guard (see `savingRef` in
 *    `shared/ArtifactForm/ArtifactForm.tsx`), otherwise button-then-shortcut
 *    within one tick still double-submits.
 * 3. **server error → focus the offending field.** Not this hook's job: it
 *    has no knowledge of which field failed. The form owns that, because only
 *    the form knows the field-name → control mapping.
 *
 * `preventDefault()` runs UNCONDITIONALLY, even when the save is deliberately
 * skipped, but only once this instance OWNS the chord. That is the whole point
 * of the issue: without it the browser's own "Save page as…" dialog opens on
 * top of the app and the user loses the work in the form behind it. Swallowing
 * the key is correct even while a save is already running — re-submitting is
 * wrong, and letting the browser take over is worse.
 *
 * `Ctrl+Shift+S` is deliberately NOT matched: it is the browser's
 * "Save page as…" binding on every mainstream browser, and stealing it would be
 * a regression rather than a feature.
 *
 * ONE chord, ONE active form (issue #1100)
 * ----------------------------------------
 * A document-level listener is per hook instance, so an open modal create
 * dialog and the detail form still mounted behind it would BOTH answer the
 * chord — the create form would submit and the detail form would PATCH at the
 * same time. `activeSaveHandlers` is the ordered registry of the enabled
 * instances; only the topmost (the most recently mounted, i.e. the modal the
 * user is looking at) handles the key. A disabled instance registers nothing,
 * so with no active form the browser keeps its native `Ctrl+S` entirely.
 *
 * INTERACTION CONTEXT, NOT JUST TOPMOST (issue #1100 follow-up)
 * -------------------------------------------------------------
 * Topmost arbitration answers "which form mounted last?", which is not the
 * same question as "which form is the user actually on?". A covering modal
 * that carries no form of its own — a confirm dialog, a legend, an export
 * panel — does not register a handler, so the form *behind* it can still be
 * topmost and `Ctrl+S` would save a surface the user can neither see nor
 * operate (WCAG 2.1.1 / 4.1.3). `containerRef` is the form (or panel) that
 * owns the shortcut: when it is supplied, the handler yields while a
 * `role="dialog"` + `aria-modal="true"` overlay that does not contain it is
 * open, and while focus sits inside a different such overlay. It is the
 * caller's form, not a DOM heuristic, so "am I the interaction context?" is
 * answered exactly. Hooks that do not pass `containerRef` keep the
 * topmost-only behaviour, so the gate is opt-in and cannot regress a caller
 * that has not been taught about it yet.
 *
 * `canSave` (issue #1100 / WCAG 3.3.1) closes the last silent path: a form
 * whose required fields are empty would otherwise be *called* and early-return
 * inside its own submit path, so the keystroke looked handled but nothing
 * happened and nothing was announced. When `canSave` is `false` the chord is
 * still swallowed (the browser's "Save page as…" must not open over the draft)
 * but `onSave` is not called — mirroring the disabled Save button, which is
 * the form's own statement that it is not saveable.
 */

import { useEffect, useRef, type RefObject } from "react";

/**
 * `aria-keyshortcuts` value for this binding (WAI-ARIA 1.2). The space-separated
 * list is required, not decorative: it is the only machine-readable way to
 * advertise a shortcut on a control, and assistive technology that renders
 * shortcuts surfaces it verbatim.
 */
export const SAVE_SHORTCUT_ARIA = "Control+S Meta+S";

/**
 * Non-localized label for the binding, used only where a component has no i18n
 * channel (logs, test failure messages). User-visible surfaces must use the
 * localized `artifactForm.saveShortcutHint` / `profile.saveShortcutHint` copy.
 */
export const SAVE_SHORTCUT_LABEL = "Ctrl+S";

/**
 * True for the save chord.
 *
 * `event.code === "KeyS"` is accepted alongside `event.key` so the binding also
 * fires on layouts where the physical S key produces a different character —
 * the same reasoning `RevealValue`'s `Alt+Shift+R` uses for its `KeyR` match.
 *
 * An in-flight IME composition is excluded: the keystroke then belongs to the
 * input method, and swallowing it could interrupt text entry (#1100). The key
 * is left entirely alone in that case — no `preventDefault` either.
 */
export function isSaveShortcutEvent(event: KeyboardEvent): boolean {
  if (event.altKey) return false;
  // Ctrl+Shift+S is the browser's own "Save page as…" — leave it alone.
  if (event.shiftKey) return false;
  if (!event.ctrlKey && !event.metaKey) return false;
  if (event.isComposing) return false;
  return event.code === "KeyS" || event.key?.toLowerCase() === "s";
}

/**
 * The topmost open modal in the document, or `null` when none is open.
 *
 * The shared `<Dialog>` portals to `document.body` and appends on mount, so the
 * last `[role="dialog"][aria-modal="true"]` in document order is the panel the
 * user is looking at. A DOM query rather than a React registry is deliberate:
 * the keydown listener is document-level, so the overlay that covers the form
 * is a DOM fact, and the consumers of this hook do not all share a React
 * ancestor with the dialog that covers them.
 */
function topmostOpenModal(): Element | null {
  if (typeof document === "undefined") return null;
  const modals = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
  return modals.length > 0 ? modals[modals.length - 1] : null;
}

/**
 * Ordered registry of the currently-enabled save handlers. The last entry is
 * the form that owns the chord (see the file header). Module-level because the
 * keydown listener is document-level and several forms can be mounted at once.
 */
const activeSaveHandlers: Array<() => void> = [];

export interface UseSaveShortcutOptions {
  /** The form's own save path. Returned promises are ignored on purpose. */
  onSave: () => void | Promise<void>;
  /**
   * `false` removes the listener entirely — no `preventDefault` either. Use it
   * for a form with nothing to save (read-only view, edit mode switched off):
   * swallowing the key there would only deny the user the browser's own action.
   */
  enabled?: boolean;
  /** A save is already in flight: swallow the key, do not submit again. */
  isSaving?: boolean;
  /**
   * The element that owns the shortcut — normally the form. When supplied, the
   * handler is suspended while a covering modal is open (see the file header);
   * omit it and the hook keeps the topmost-only behaviour.
   */
  containerRef?: RefObject<HTMLElement | null>;
  /**
   * Whether the form currently has something saveable. Default `true`. When
   * `false` the chord is still swallowed but `onSave` is not called, so an
   * empty required field cannot reach a submit path that would only
   * early-return silently (WCAG 3.3.1). Pair it with the same predicate that
   * disables the form's Save button.
   */
  canSave?: boolean;
}

export function useSaveShortcut({
  onSave,
  enabled = true,
  isSaving = false,
  containerRef,
  canSave = true,
}: UseSaveShortcutOptions): void {
  // Refs, not effect-updated closures: `onSave` is a fresh function identity
  // on every render of every consumer, so an effect that depended on it would
  // detach and re-attach the document listener on each render. Assigning during
  // render is the pattern `ArtifactForm` already uses for its
  // `initialValues` ref (see `initialRef.current = initialValues`), and it is
  // idempotent under StrictMode's double render.
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const isSavingRef = useRef(isSaving);
  isSavingRef.current = isSaving;
  const canSaveRef = useRef(canSave);
  canSaveRef.current = canSave;
  // The container is read at keydown time (a ref may not be attached on the
  // first render), so the ref *object* is what has to be kept current.
  const containerRefRef = useRef(containerRef);
  containerRefRef.current = containerRef;

  // This instance's own registry entry, so a keydown can tell whether it is the
  // form that currently owns the chord. `null` while disabled.
  const handlerRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!enabled) return undefined;
    const handler = (): void => {
      if (isSavingRef.current) return;
      void onSaveRef.current();
    };
    handlerRef.current = handler;
    activeSaveHandlers.push(handler);
    return () => {
      const index = activeSaveHandlers.lastIndexOf(handler);
      if (index >= 0) activeSaveHandlers.splice(index, 1);
      handlerRef.current = null;
    };
  }, [enabled]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (!isSaveShortcutEvent(event)) return;
      // Only the topmost enabled form acts. No active form (all disabled) or a
      // form that is not the topmost one leaves the key to the browser / to the
      // form that owns the surface — no `preventDefault`.
      if (!handlerRef.current) return;
      if (activeSaveHandlers[activeSaveHandlers.length - 1] !== handlerRef.current) {
        return;
      }

      // Interaction-context gate. Only consulted when the caller declared its
      // own container (see the file header): a covering modal that does not
      // contain the form suspends the shortcut, so it cannot save a surface
      // the user is not on. `document.activeElement` is consulted too — focus
      // inside a different modal is the same statement in a different voice.
      const container = containerRefRef.current?.current ?? null;
      if (container !== null) {
        const modal = topmostOpenModal();
        if (modal && !modal.contains(container)) {
          // Own the chord so the browser's own save dialog does not open over
          // the modal, but do not save the covered form.
          event.preventDefault();
          return;
        }
        const active = document.activeElement;
        const focusModal =
          active instanceof Element
            ? active.closest('[role="dialog"][aria-modal="true"]')
            : null;
        if (focusModal && !focusModal.contains(container)) {
          event.preventDefault();
          return;
        }
      }

      // Not savable (e.g. a required field is still empty). Swallow the chord
      // so the browser's "Save page as…" cannot open, but do not run a submit
      // path that would only early-return without telling the user anything.
      if (!canSaveRef.current) {
        event.preventDefault();
        return;
      }

      // Unconditional once we own the chord — see the file header.
      event.preventDefault();
      handlerRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}
