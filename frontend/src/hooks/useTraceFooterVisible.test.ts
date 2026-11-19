/**
 * Trace-spine footer visibility store (Task 2 / Schnitt 1b).
 *
 * The two display toggles (trace footer, inspector) are INDEPENDENT: each owns
 * its own module store, its own localStorage key and its own listeners. These
 * tests pin that contract in addition to the `useReadableIdsVisible` pattern
 * (default true, one store for all consumers, cross-tab sync, graceful
 * degradation when storage is locked).
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getTraceFooterVisible,
  setTraceFooterVisible,
  TRACE_FOOTER_STORAGE_KEY,
  TRACE_FOOTER_VISIBLE_DEFAULT,
  useTraceFooterVisible,
} from "./useTraceFooterVisible";
import {
  getInspectorVisible,
  setInspectorVisible,
  INSPECTOR_VISIBLE_DEFAULT,
  useInspectorVisible,
} from "./useInspectorVisible";

const originalLocalStorage = window.localStorage;

function installLocalStorage(impl: Storage | undefined): void {
  Object.defineProperty(window, "localStorage", {
    value: impl,
    configurable: true,
    writable: true,
  });
}

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(initial));
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (key: string) => map.get(key) ?? null,
    key: (index: number) => [...map.keys()][index] ?? null,
    removeItem: (key: string) => void map.delete(key),
    setItem: (key: string, value: string) => void map.set(key, value),
  } as Storage;
}

beforeEach(() => {
  installLocalStorage(memoryStorage());
  // Both stores are singletons by design; reset them between tests.
  setTraceFooterVisible(TRACE_FOOTER_VISIBLE_DEFAULT);
  setInspectorVisible(INSPECTOR_VISIBLE_DEFAULT);
});

afterEach(() => {
  installLocalStorage(originalLocalStorage);
  vi.restoreAllMocks();
});

describe("useTraceFooterVisible", () => {
  it("defaults to visible", () => {
    const { result } = renderHook(() => useTraceFooterVisible());
    expect(result.current[0]).toBe(true);
    expect(TRACE_FOOTER_VISIBLE_DEFAULT).toBe(true);
  });

  it("writes the choice through and reflects it in every mounted consumer", () => {
    const first = renderHook(() => useTraceFooterVisible());
    const second = renderHook(() => useTraceFooterVisible());

    act(() => {
      first.result.current[1](false);
    });

    expect(window.localStorage.getItem(TRACE_FOOTER_STORAGE_KEY)).toBe("false");
    expect(first.result.current[0]).toBe(false);
    expect(second.result.current[0]).toBe(false);
  });

  it("is independent of the inspector toggle", () => {
    const footer = renderHook(() => useTraceFooterVisible());
    const inspector = renderHook(() => useInspectorVisible());

    act(() => {
      footer.result.current[1](false);
    });
    expect(footer.result.current[0]).toBe(false);
    // Toggling the footer must never move the inspector, in either direction.
    expect(inspector.result.current[0]).toBe(true);

    act(() => {
      inspector.result.current[1](false);
    });
    expect(inspector.result.current[0]).toBe(false);
    expect(footer.result.current[0]).toBe(false);
  });

  it("applies a server-provided value through the setter (server round-trip)", () => {
    // The hydrator/settings writer call the exported setter after the server
    // answers; the store and its first-render cache must both follow, while the
    // other preference stays where the server left it.
    act(() => {
      setTraceFooterVisible(false);
      setInspectorVisible(true);
    });

    expect(getTraceFooterVisible()).toBe(false);
    expect(getInspectorVisible()).toBe(true);
    expect(window.localStorage.getItem(TRACE_FOOTER_STORAGE_KEY)).toBe("false");

    const { result } = renderHook(() => useTraceFooterVisible());
    expect(result.current[0]).toBe(false);
  });

  it("picks up a cross-tab storage event only for its own key", () => {
    const footer = renderHook(() => useTraceFooterVisible());
    const inspector = renderHook(() => useInspectorVisible());

    act(() => {
      window.localStorage.setItem(TRACE_FOOTER_STORAGE_KEY, "false");
      window.dispatchEvent(
        new StorageEvent("storage", { key: TRACE_FOOTER_STORAGE_KEY })
      );
    });

    expect(footer.result.current[0]).toBe(false);
    expect(inspector.result.current[0]).toBe(true);
  });

  it("degrades to an in-memory value when storage throws", () => {
    const throwing = {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("SecurityError");
      },
      removeItem: () => undefined,
      clear: () => undefined,
      key: () => null,
      length: 0,
    } as unknown as Storage;
    installLocalStorage(throwing);

    const { result } = renderHook(() => useTraceFooterVisible());
    expect(result.current[0]).toBe(TRACE_FOOTER_VISIBLE_DEFAULT);
    expect(() =>
      act(() => {
        result.current[1](false);
      })
    ).not.toThrow();
    // FR-U3-01: the just-set value is authoritative, even if storage refuses.
    expect(result.current[0]).toBe(false);
    expect(getTraceFooterVisible()).toBe(false);
  });
});
