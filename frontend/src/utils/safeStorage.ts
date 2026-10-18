/**
 * Centralized defensive web-storage access (issue #679, audit finding FE-05).
 *
 * Direct `window.localStorage` / `window.sessionStorage` access throws in
 * third-party-cookie-restricted browsers, private-browsing storage lockouts,
 * and JSDOM test environments where the property is unavailable or mocked out
 * (`TypeError: Cannot read properties of undefined`, or a `SecurityError`) —
 * and even *reading* the `window.localStorage` property itself can throw in
 * locked-down browsers. Everything persisted through these wrappers is a
 * nice-to-have (view preferences, dismissals, panel widths, one-shot
 * handoffs): losing it degrades the experience, freezing the UI over it is
 * never acceptable.
 *
 * Reference pattern: the `InterviewWidget` toggle-open wrapper originally
 * introduced this guard for #679; every call site now goes through the shared
 * wrappers below instead of carrying its own copy.
 *
 * Contract:
 *   - `getItem` never throws — returns `null` when storage is unavailable,
 *     locked, or the key is absent;
 *   - `setItem`/`removeItem` never throw — silently no-op when storage
 *     refuses (private browsing, disabled cookies, quota, missing property);
 *   - the target `Storage` object is resolved lazily on every operation, so an
 *     environment that replaces `window.localStorage`/`window.sessionStorage`
 *     after module load (tests, polyfills) is honoured;
 *   - absent `window` (SSR) degrades to the same safe defaults.
 *
 * Deliberately no JSON helpers: serialization (and its failure modes) stays
 * with the callers, who know the payload shape they own.
 */

/** Minimal storage surface used by call sites. */
interface SafeStorage {
  /** Stored value, or `null` when absent / unavailable / foreign. */
  getItem(key: string): string | null;
  /** Persist `value`; silently ignored when storage is unavailable or full. */
  setItem(key: string, value: string): void;
  /** Remove `key`; silently ignored when storage is unavailable. */
  removeItem(key: string): void;
}

/** Resolves the backing `Storage` at call time (lazy, never cached). */
type StorageResolver = () => Storage | undefined;

function createSafeStorage(resolve: StorageResolver): SafeStorage {
  return {
    getItem: (key: string): string | null => {
      try {
        return resolve()?.getItem(key) ?? null;
      } catch {
        // Storage unavailable/blocked — a read that cannot answer is `null`.
        return null;
      }
    },
    setItem: (key: string, value: string): void => {
      try {
        resolve()?.setItem(key, value);
      } catch {
        // Storage unavailable (private browsing, disabled cookies, quota) —
        // silently no-op: persistence must never break the caller.
      }
    },
    removeItem: (key: string): void => {
      try {
        resolve()?.removeItem(key);
      } catch {
        // Same contract as `setItem` above.
      }
    },
  };
}

/** `window.localStorage`, resolved lazily and without touching `window` on SSR. */
function resolveLocalStorage(): Storage | undefined {
  return typeof window === "undefined" ? undefined : window.localStorage;
}

/** `window.sessionStorage`, resolved lazily and without touching `window` on SSR. */
function resolveSessionStorage(): Storage | undefined {
  return typeof window === "undefined" ? undefined : window.sessionStorage;
}

/** Defensive `localStorage` (see the module docstring). */
export const safeLocalStorage = createSafeStorage(resolveLocalStorage);

/** Defensive `sessionStorage` (see the module docstring). */
export const safeSessionStorage = createSafeStorage(resolveSessionStorage);
