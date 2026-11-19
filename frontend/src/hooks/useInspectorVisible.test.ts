/**
 * Inspector visibility store (Task 2 / Schnitt 1b).
 *
 * Mirrors `useTraceFooterVisible`: its own module store, its own localStorage
 * key and its own listeners. The pairing tests below prove that toggling the
 * inspector never moves the trace footer (and vice versa) — D2 of the plan.
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getInspectorVisible,
  setInspectorVisible,
  INSPECTOR_STORAGE_KEY,
  INSPECTOR_VISIBLE_DEFAULT,
  useInspectorVisible,
} from "./useInspectorVisible";
import {
  getTraceFooterVisible,
  setTraceFooterVisible,
  TRACE_FOOTER_VISIBLE_DEFAULT,
  useTraceFooterVisible,
} from "./useTraceFooterVisible";

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
  setInspectorVisible(INSPECTOR_VISIBLE_DEFAULT);
  setTraceFooterVisible(TRACE_FOOTER_VISIBLE_DEFAULT);
});

afterEach(() => {
  installLocalStorage(originalLocalStorage);
  vi.restoreAllMocks();
});

describe("useInspectorVisible", () => {
  it("defaults to visible", () => {
    const { result } = renderHook(() => useInspectorVisible());
    expect(result.current[0]).toBe(true);
    expect(INSPECTOR_VISIBLE_DEFAULT).toBe(true);
  });

  it("writes the choice through and reflects it in every mounted consumer", () => {
    const first = renderHook(() => useInspectorVisible());
    const second = renderHook(() => useInspectorVisible());

    act(() => {
      first.result.current[1](false);
    });

    expect(window.localStorage.getItem(INSPECTOR_STORAGE_KEY)).toBe("false");
    expect(first.result.current[0]).toBe(false);
    expect(second.result.current[0]).toBe(false);
  });

  it("is independent of the trace-footer toggle", () => {
    const inspector = renderHook(() => useInspectorVisible());
    const footer = renderHook(() => useTraceFooterVisible());

    act(() => {
      inspector.result.current[1](false);
    });
    expect(inspector.result.current[0]).toBe(false);
    // Toggling the inspector must never move the footer, in either direction.
    expect(footer.result.current[0]).toBe(true);

    act(() => {
      footer.result.current[1](false);
    });
    expect(footer.result.current[0]).toBe(false);
    expect(inspector.result.current[0]).toBe(false);
  });

  it("applies a server-provided value through the setter (server round-trip)", () => {
    act(() => {
      setInspectorVisible(false);
      setTraceFooterVisible(true);
    });

    expect(getInspectorVisible()).toBe(false);
    expect(getTraceFooterVisible()).toBe(true);
    expect(window.localStorage.getItem(INSPECTOR_STORAGE_KEY)).toBe("false");

    const { result } = renderHook(() => useInspectorVisible());
    expect(result.current[0]).toBe(false);
  });

  it("picks up a cross-tab storage event only for its own key", () => {
    const inspector = renderHook(() => useInspectorVisible());
    const footer = renderHook(() => useTraceFooterVisible());

    act(() => {
      window.localStorage.setItem(INSPECTOR_STORAGE_KEY, "false");
      window.dispatchEvent(
        new StorageEvent("storage", { key: INSPECTOR_STORAGE_KEY })
      );
    });

    expect(inspector.result.current[0]).toBe(false);
    expect(footer.result.current[0]).toBe(true);
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

    const { result } = renderHook(() => useInspectorVisible());
    expect(result.current[0]).toBe(INSPECTOR_VISIBLE_DEFAULT);
    expect(() =>
      act(() => {
        result.current[1](false);
      })
    ).not.toThrow();
    expect(result.current[0]).toBe(false);
    expect(getInspectorVisible()).toBe(false);
  });
});
