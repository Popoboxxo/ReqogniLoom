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
 *    (create-mode requiredness, the change-reason gate). That keeps the
 *    keystroke and the button on exactly one code path — a second, shortcut-
 *    only save implementation is precisely how the two drift apart.
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
 * skipped. That is the whole point of the issue: without it the browser's own
 * "Save page as…" dialog opens on top of the app and the user loses the work
 * in the form behind it. Swallowing the key is correct even while a save is
 * already running — re-submitting is wrong, and letting the browser take over
 * is worse.
 *
 * `Ctrl+Shift+S` is deliberately NOT matched: it is the browser's
 * "Save page as…" binding on every mainstream browser, and stealing it would be
 * a regression rather than a feature.
 */

import { useCallback, useEffect, useRef } from "react";

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
 */
export function isSaveShortcutEvent(event: KeyboardEvent): boolean {
  if (event.altKey) return false;
  // Ctrl+Shift+S is the browser's own "Save page as…" — leave it alone.
  if (event.shiftKey) return false;
  if (!event.ctrlKey && !event.metaKey) return false;
  return event.code === "KeyS" || event.key?.toLowerCase() === "s";
}

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
}

export function useSaveShortcut({
  onSave,
  enabled = true,
  isSaving = false,
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

  const triggerSave = useCallback((): void => {
    void onSaveRef.current();
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (!isSaveShortcutEvent(event)) return;
      // Unconditional — see the file header.
      event.preventDefault();
      if (isSavingRef.current) return;
      triggerSave();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [enabled, triggerSave]);
}
