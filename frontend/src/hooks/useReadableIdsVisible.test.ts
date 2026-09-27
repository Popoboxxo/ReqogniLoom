/**
 * Issue #1094 — the readable-id display preference store.
 *
 * The behavioural requirements that are not obvious from the hook's signature:
 *   - ONE `storage` listener for the whole app, however many chips are mounted
 *     (a virtualized artifact list mounts hundreds of rows);
 *   - every mounted consumer follows a write, in the same tab and in another;
 *   - a browser that refuses storage degrades to an in-memory preference
 *     instead of throwing during render (same failure mode as #679).
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getReadableIdsVisible,
  READABLE_IDS_STORAGE_KEY,
  READABLE_IDS_VISIBLE_DEFAULT,
  setReadableIdsVisible,
  useReadableIdsVisible,
} from "./useReadableIdsVisible";

const originalLocalStorage = window.localStorage;

/** jsdom in this runtime does not always provide a usable localStorage. */
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
  // Reset the module-level snapshot to the default; the store is a singleton by
  // design, so a previous test's write would otherwise leak in.
  setReadableIdsVisible(READABLE_IDS_VISIBLE_DEFAULT);
});

afterEach(() => {
  installLocalStorage(originalLocalStorage);
  vi.restoreAllMocks();
});

describe("useReadableIdsVisible", () => {
  it("defaults to visible", () => {
    const { result } = renderHook(() => useReadableIdsVisible());
    expect(result.current[0]).toBe(true);
    expect(READABLE_IDS_VISIBLE_DEFAULT).toBe(true);
  });

  it("writes the choice through and reflects it in every mounted consumer", () => {
    const first = renderHook(() => useReadableIdsVisible());
    const second = renderHook(() => useReadableIdsVisible());
    expect(first.result.current[0]).toBe(true);

    act(() => {
      first.result.current[1](false);
    });

    expect(window.localStorage.getItem(READABLE_IDS_STORAGE_KEY)).toBe("false");
    expect(first.result.current[0]).toBe(false);
    // The whole point of the module-level store: one write, every chip.
    expect(second.result.current[0]).toBe(false);
  });

  it("picks up a change made in another tab via the storage event", () => {
    const { result } = renderHook(() => useReadableIdsVisible());
    // Simulate what another tab's write looks like from here: the value lands
    // in localStorage, then the browser fires `storage` in the OTHER documents.
    window.localStorage.setItem(READABLE_IDS_STORAGE_KEY, "false");

    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", { key: READABLE_IDS_STORAGE_KEY })
      );
    });

    expect(result.current[0]).toBe(false);
  });

  it("ignores a storage event for another preference", () => {
    const { result } = renderHook(() => useReadableIdsVisible());

    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "reqflow-other" }));
    });

    expect(result.current[0]).toBe(true);
  });

  it("picks up a storage.clear() from another tab", () => {
    // A `null` key is what `clear()` reports; the default then applies.
    window.localStorage.setItem(READABLE_IDS_STORAGE_KEY, "false");
    act(() => {
      setReadableIdsVisible(false);
    });
    const { result } = renderHook(() => useReadableIdsVisible());
    expect(result.current[0]).toBe(false);

    act(() => {
      window.localStorage.clear();
      window.dispatchEvent(new StorageEvent("storage", { key: null }));
    });

    expect(result.current[0]).toBe(true);
  });

  it("keeps working when storage throws, without breaking the render", () => {
    // Private-browsing / storage-lockout case (issue #679's failure mode): the
    // preference is a display choice, never worth an exception.
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

    const { result } = renderHook(() => useReadableIdsVisible());
    // The stale in-memory value survives a storage that refuses to answer.
    expect(result.current[0]).toBe(READABLE_IDS_VISIBLE_DEFAULT);

    expect(() =>
      act(() => {
        result.current[1](false);
      })
    ).not.toThrow();
  });

  it("exposes the current value outside React for non-component callers", () => {
    expect(getReadableIdsVisible()).toBe(true);
    act(() => {
      setReadableIdsVisible(false);
    });
    expect(getReadableIdsVisible()).toBe(false);
  });

  it("stops notifying an unmounted consumer", () => {
    const { unmount } = renderHook(() => useReadableIdsVisible());
    unmount();

    expect(() =>
      act(() => {
        setReadableIdsVisible(false);
      })
    ).not.toThrow();
  });
});
