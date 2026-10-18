/**
 * Unit tests for the centralized defensive web-storage wrappers (issue #679,
 * audit finding FE-05).
 *
 * The wrapper exists so that a browser refusing storage (private browsing,
 * third-party-cookie lockout, quota) or a JSDOM environment without a usable
 * `localStorage`/`sessionStorage` degrades to safe defaults instead of
 * freezing a render. The negative paths below are the actual contract; the
 * roundtrip only proves the wrappers still reach the real storage.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { safeLocalStorage, safeSessionStorage } from "./safeStorage";

const originalLocalStorage = window.localStorage;
const originalSessionStorage = window.sessionStorage;

function installStorage(kind: "localStorage" | "sessionStorage", impl: unknown): void {
  Object.defineProperty(window, kind, {
    configurable: true,
    writable: true,
    value: impl,
  });
}

function throwingStorage(): Storage {
  const throwSecurityError = (): never => {
    throw new Error("SecurityError: storage access is blocked");
  };
  return {
    get length() {
      return 0;
    },
    clear: vi.fn(throwSecurityError),
    getItem: vi.fn(throwSecurityError),
    key: vi.fn(throwSecurityError),
    removeItem: vi.fn(throwSecurityError),
    setItem: vi.fn(throwSecurityError),
  } as unknown as Storage;
}

afterEach(() => {
  // A test may have stubbed `window` itself away (SSR case) — restore it
  // before touching the storage properties again.
  vi.unstubAllGlobals();
  installStorage("localStorage", originalLocalStorage);
  installStorage("sessionStorage", originalSessionStorage);
  originalLocalStorage.clear();
  originalSessionStorage.clear();
  vi.restoreAllMocks();
});

const cases = [
  { name: "safeLocalStorage", kind: "localStorage" as const, api: safeLocalStorage },
  { name: "safeSessionStorage", kind: "sessionStorage" as const, api: safeSessionStorage },
];

describe.each(cases)("$name", ({ kind, api }) => {
  it("roundtrips set/get/remove against the real storage", () => {
    api.setItem("reqlo:safe-storage:roundtrip", "value");
    expect(api.getItem("reqlo:safe-storage:roundtrip")).toBe("value");
    // The value really landed in the matching native storage object.
    expect(window[kind].getItem("reqlo:safe-storage:roundtrip")).toBe("value");

    api.removeItem("reqlo:safe-storage:roundtrip");
    expect(api.getItem("reqlo:safe-storage:roundtrip")).toBeNull();
    expect(window[kind].getItem("reqlo:safe-storage:roundtrip")).toBeNull();
  });

  it("returns null for a key that was never written", () => {
    expect(api.getItem("reqlo:safe-storage:absent")).toBeNull();
  });

  it("absorbs a storage whose methods throw (issue #679)", () => {
    const throwing = throwingStorage();
    installStorage(kind, throwing);

    expect(api.getItem("reqlo:safe-storage:throw")).toBeNull();
    expect(() => api.setItem("reqlo:safe-storage:throw", "v")).not.toThrow();
    expect(() => api.removeItem("reqlo:safe-storage:throw")).not.toThrow();

    // The wrapper did reach the (throwing) storage — the guard is what
    // absorbed the failure.
    expect(throwing.setItem).toHaveBeenCalledWith("reqlo:safe-storage:throw", "v");
    expect(throwing.removeItem).toHaveBeenCalledWith("reqlo:safe-storage:throw");
  });

  it("absorbs a storage whose property access itself throws", () => {
    Object.defineProperty(window, kind, {
      configurable: true,
      get() {
        throw new Error("SecurityError: storage access is blocked");
      },
    });

    expect(api.getItem("reqlo:safe-storage:blocked")).toBeNull();
    expect(() => api.setItem("reqlo:safe-storage:blocked", "v")).not.toThrow();
    expect(() => api.removeItem("reqlo:safe-storage:blocked")).not.toThrow();
  });

  it("degrades to safe defaults when the storage object is absent", () => {
    installStorage(kind, undefined);

    expect(api.getItem("reqlo:safe-storage:missing")).toBeNull();
    expect(() => api.setItem("reqlo:safe-storage:missing", "v")).not.toThrow();
    expect(() => api.removeItem("reqlo:safe-storage:missing")).not.toThrow();
  });

  it("degrades to safe defaults without a window (SSR)", () => {
    vi.stubGlobal("window", undefined);

    expect(api.getItem("reqlo:safe-storage:ssr")).toBeNull();
    expect(() => api.setItem("reqlo:safe-storage:ssr", "v")).not.toThrow();
    expect(() => api.removeItem("reqlo:safe-storage:ssr")).not.toThrow();
  });
});

it("routes each wrapper to its own storage kind", () => {
  safeLocalStorage.setItem("reqlo:safe-storage:routing", "local");
  safeSessionStorage.setItem("reqlo:safe-storage:routing", "session");

  expect(safeLocalStorage.getItem("reqlo:safe-storage:routing")).toBe("local");
  expect(safeSessionStorage.getItem("reqlo:safe-storage:routing")).toBe("session");
});
