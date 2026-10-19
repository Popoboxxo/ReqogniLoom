/**
 * ARCH-L1-001 ReactFrontend — useMediaQuery.
 *
 * Covers the three properties the mobile drawer's modality switch depends on:
 * the SSR/no-`matchMedia` guard, the initial match, and the live `change`
 * subscription (including its teardown). jsdom does not implement a real
 * `MediaQueryList`, so the stub below models the parts the hook uses
 * (`matches`, `addEventListener`, `removeEventListener`).
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useMediaQuery } from "./useMediaQuery";

type ChangeListener = (event: MediaQueryListEvent) => void;

interface MatchMediaStub {
  /** Fire a `change` event with the given match state. */
  emit: (matches: boolean) => void;
  /** Spy on the listener teardown, so unsubscribe can be asserted. */
  removeEventListener: ReturnType<typeof vi.fn>;
}

/** Install a controllable `window.matchMedia` for one test. */
function installMatchMedia(initialMatches: boolean): MatchMediaStub {
  const listeners = new Set<ChangeListener>();
  const removeEventListener = vi.fn(
    (_type: string, listener: ChangeListener) => {
      listeners.delete(listener);
    }
  );
  const mediaQueryList = {
    matches: initialMatches,
    media: "",
    onchange: null,
    addEventListener: (_type: string, listener: ChangeListener) => {
      listeners.add(listener);
    },
    removeEventListener,
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => true,
  };
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn(() => mediaQueryList),
  });
  return {
    emit: (matches: boolean) => {
      for (const listener of listeners) {
        listener({ matches } as MediaQueryListEvent);
      }
    },
    removeEventListener,
  };
}

afterEach(() => {
  // Drop the own descriptor so the environment's own `matchMedia` (if any)
  // is visible again for the next test.
  Reflect.deleteProperty(window, "matchMedia");
});

describe("useMediaQuery", () => {
  it("reports false and does not throw when matchMedia is unavailable", () => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: undefined,
    });
    const { result } = renderHook(() => useMediaQuery("(max-width: 1024px)"));
    expect(result.current).toBe(false);
  });

  it("reports the query's current match on the first render", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useMediaQuery("(max-width: 1024px)"));
    expect(result.current).toBe(true);
  });

  it("tracks change events in both directions", () => {
    const { emit } = installMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(max-width: 1024px)"));
    expect(result.current).toBe(false);

    act(() => emit(true));
    expect(result.current).toBe(true);

    act(() => emit(false));
    expect(result.current).toBe(false);
  });

  it("unsubscribes from the change event on unmount", () => {
    const { removeEventListener } = installMatchMedia(true);
    const { unmount } = renderHook(() => useMediaQuery("(max-width: 1024px)"));
    unmount();
    expect(removeEventListener).toHaveBeenCalledTimes(1);
  });

  it("re-reads the match when the query changes", () => {
    const { emit } = installMatchMedia(true);
    const { result, rerender } = renderHook(
      ({ query }) => useMediaQuery(query),
      { initialProps: { query: "(max-width: 1024px)" } }
    );
    expect(result.current).toBe(true);

    rerender({ query: "(max-width: 600px)" });
    expect(result.current).toBe(true);

    act(() => emit(false));
    expect(result.current).toBe(false);
  });
});
