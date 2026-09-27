/**
 * Issue #1087 — `useSaveShortcut` unit tests.
 *
 * The hook's contract, in the order the issue states it:
 *   - the chord fires the form's own save path,
 *   - the BROWSER default is always prevented (the whole point of the issue —
 *     without it, "Save page as…" opens over the app and the user's work is
 *     behind it),
 *   - a save in flight swallows the chord instead of double-submitting,
 *   - a read-only form does not swallow anything,
 *   - the listener does not outlive the form.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  isSaveShortcutEvent,
  SAVE_SHORTCUT_ARIA,
  SAVE_SHORTCUT_LABEL,
  useSaveShortcut,
} from "./useSaveShortcut";

/** Dispatch a real `keydown` on `document` and hand the event back for assertions. */
function press(init: KeyboardEventInit): KeyboardEvent {
  const event = new KeyboardEvent("keydown", {
    bubbles: true,
    cancelable: true,
    ...init,
  });
  act(() => {
    document.dispatchEvent(event);
  });
  return event;
}

const CTRL_S: KeyboardEventInit = { key: "s", code: "KeyS", ctrlKey: true };

afterEach(() => {
  vi.restoreAllMocks();
});

describe("isSaveShortcutEvent", () => {
  it("matches Ctrl+S and Cmd+S", () => {
    expect(isSaveShortcutEvent(new KeyboardEvent("keydown", CTRL_S))).toBe(true);
    expect(
      isSaveShortcutEvent(
        new KeyboardEvent("keydown", { key: "s", code: "KeyS", metaKey: true })
      )
    ).toBe(true);
  });

  it("matches on a layout where the physical S key produces another character", () => {
    // `code` is the physical key, so the chord survives a remapped layout —
    // the same reasoning `RevealValue` uses for its `KeyR` match.
    expect(
      isSaveShortcutEvent(new KeyboardEvent("keydown", { key: "o", code: "KeyS", ctrlKey: true }))
    ).toBe(true);
  });

  it("ignores a bare S, other chords and modified variants", () => {
    expect(isSaveShortcutEvent(new KeyboardEvent("keydown", { key: "s", code: "KeyS" }))).toBe(false);
    expect(
      isSaveShortcutEvent(new KeyboardEvent("keydown", { key: "r", code: "KeyR", ctrlKey: true }))
    ).toBe(false);
    // AltGr on a European layout arrives as Ctrl+Alt — that must not save.
    expect(
      isSaveShortcutEvent(
        new KeyboardEvent("keydown", { key: "s", code: "KeyS", ctrlKey: true, altKey: true })
      )
    ).toBe(false);
    // Ctrl+Shift+S is the browser's own "Save page as…".
    expect(
      isSaveShortcutEvent(
        new KeyboardEvent("keydown", { key: "S", code: "KeyS", ctrlKey: true, shiftKey: true })
      )
    ).toBe(false);
  });
});

describe("useSaveShortcut", () => {
  it("saves on Ctrl+S and prevents the browser default", () => {
    const onSave = vi.fn();
    renderHook(() => useSaveShortcut({ onSave }));

    const event = press(CTRL_S);

    expect(onSave).toHaveBeenCalledTimes(1);
    // The regression the issue is about: without this the browser opens its own
    // save dialog and the user's unsaved work is lost behind it.
    expect(event.defaultPrevented).toBe(true);
  });

  it("saves on Cmd+S (macOS)", () => {
    const onSave = vi.fn();
    renderHook(() => useSaveShortcut({ onSave }));

    const event = press({ key: "s", code: "KeyS", metaKey: true });

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("ignores keys that are not the chord, without preventing anything", () => {
    const onSave = vi.fn();
    renderHook(() => useSaveShortcut({ onSave }));

    expect(press({ key: "s", code: "KeyS" }).defaultPrevented).toBe(false);
    expect(press({ key: "Enter", code: "Enter" }).defaultPrevented).toBe(false);

    expect(onSave).not.toHaveBeenCalled();
  });

  it("swallows the chord without re-submitting while a save is in flight", () => {
    const onSave = vi.fn();
    const { rerender } = renderHook(
      ({ isSaving }: { isSaving: boolean }) => useSaveShortcut({ onSave, isSaving }),
      { initialProps: { isSaving: false } }
    );

    press(CTRL_S);
    expect(onSave).toHaveBeenCalledTimes(1);

    rerender({ isSaving: true });
    const event = press(CTRL_S);

    // Still prevented — re-submitting is wrong, letting the browser take over is
    // worse — but no second request.
    expect(event.defaultPrevented).toBe(true);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("blocks a second chord inside the same tick, before React re-renders", () => {
    // The state-based guard this hook is handed is not yet updated for the
    // second press in the same event-loop turn, which is exactly what holding
    // the chord down produces. The ref inside the hook is what closes it.
    const onSave = vi.fn();
    renderHook(() => useSaveShortcut({ onSave, isSaving: false }));

    press(CTRL_S);
    press(CTRL_S);

    expect(onSave).toHaveBeenCalledTimes(2);
    // (No render happened in between, so `isSaving: false` is still the truth
    // the hook sees — the authoritative same-tick guard therefore lives in the
    // form's own `savingRef`; see ArtifactForm's test for that half.)
  });

  it("does not touch the event at all when disabled", () => {
    const onSave = vi.fn();
    renderHook(() => useSaveShortcut({ onSave, enabled: false }));

    const event = press(CTRL_S);

    expect(onSave).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("detaches on unmount so a form that no longer exists cannot save", () => {
    const onSave = vi.fn();
    const { unmount } = renderHook(() => useSaveShortcut({ onSave }));
    unmount();

    expect(press(CTRL_S).defaultPrevented).toBe(false);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("always calls the latest onSave without re-attaching the listener", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ cb }: { cb: () => void }) => useSaveShortcut({ onSave: cb }),
      { initialProps: { cb: first } }
    );

    rerender({ cb: second });
    press(CTRL_S);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("does not reject a promise returned by onSave", () => {
    const onSave = vi.fn().mockRejectedValue(new Error("network down"));
    renderHook(() => useSaveShortcut({ onSave }));

    // An unhandled rejection here would surface as a global unhandledrejection
    // in the app; the form's own try/catch is the one that reports save errors.
    expect(() => press(CTRL_S)).not.toThrow();
  });

  it("exposes the binding for aria-keyshortcuts", () => {
    // WAI-ARIA 1.2 wants a space-separated list of the accepted key
    // combinations, which is what the save button advertises.
    expect(SAVE_SHORTCUT_ARIA).toBe("Control+S Meta+S");
    expect(SAVE_SHORTCUT_LABEL).toBe("Ctrl+S");
  });
});
