/**
 * ARCH-L1-001 ReactFrontend — Persisted list filter/sort state.
 *
 * BUG-19 (docs/SYSTEMAUDIT_2026-08-18.md §4): list views (Requirements,
 * Needs, Risks, ...) previously kept their search/filter/sort selections in
 * plain `useState`, which is thrown away whenever the component unmounts —
 * i.e. on every route change away from and back to that view. Both the
 * claude-in-chrome exhaustive click-test and the Playwright suite flagged
 * this independently as confusing ("I filtered by status, navigated to a
 * detail view and back, and the filter was gone").
 *
 * `usePersistedListState` is a drop-in replacement for `useState` that
 * additionally mirrors the value into `sessionStorage`, keyed by a
 * caller-supplied string. `sessionStorage` (not `localStorage`) is used
 * deliberately: this is a "leave it as you had it during this tab session"
 * convenience, not a preference that should persist across devices/browser
 * restarts like the workspace visibility overrides (REQ-L1-027,
 * UserWorkspacePreference).
 *
 * Callers MUST pass a `key` that is unique per list view AND per workspace
 * (see `RequirementList.tsx`) — otherwise switching workspaces would leave
 * the previous workspace's filter/search/sort selection applied to the
 * newly-active workspace, which reads as "this workspace is filtered for no
 * reason" (review finding F-02, worse than the original BUG-19 symptom).
 *
 * The hook itself supports `key` changing across renders (e.g. the caller
 * derives the key from the active workspace ID, which changes when the user
 * switches workspaces): it re-reads sessionStorage for the new key instead
 * of carrying the old key's in-memory value over (review finding F-03 — a
 * plain `useState(() => readStored(key, initialValue))` only evaluates its
 * initializer on the FIRST mount, so a later `key` change would neither
 * re-read the new key's stored value nor stop overwriting it with the old
 * value via the persistence effect).
 *
 * Reads are not a blind `JSON.parse(raw) as T` (code-quality audit blocker 5):
 * a stored payload whose shape is incompatible with `initialValue` is
 * discarded and the initial value is returned instead (see `readStored`).
 * Callers with a contract narrower than the derived check — e.g. a
 * string-union sort key — can pass `options.validate` to replace it.
 */

import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";

import { safeSessionStorage } from "../utils/safeStorage";

/**
 * Derived shape guard for persisted values, used when the caller passes no
 * `validate`: primitives must match `typeof`; arrays stay arrays; objects must
 * be non-null non-array objects (JSON.parse cannot produce anything else, so
 * this also rejects `null` where an object was expected). Deliberately shallow
 * — it catches "a number where a string was stored" / "an array where an
 * object was stored" without pretending to validate a caller's full domain
 * contract.
 */
function hasCompatibleShape<T>(value: unknown, initialValue: T): value is T {
  if (Array.isArray(initialValue)) return Array.isArray(value);
  if (typeof initialValue === "object" && initialValue !== null) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }
  return typeof value === typeof initialValue;
}

function readStored<T>(
  key: string,
  initialValue: T,
  options?: { validate?: (value: unknown) => value is T }
): T {
  // Defensive storage access (issue #679) — a lockout/unavailable storage
  // reads as "nothing stored" instead of throwing during render.
  const raw = safeSessionStorage.getItem(key);
  if (raw === null) return initialValue;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (options?.validate) {
      return options.validate(parsed) ? parsed : initialValue;
    }
    return hasCompatibleShape(parsed, initialValue) ? parsed : initialValue;
  } catch {
    // Corrupt/foreign value under this key — fall back to the default
    // rather than throwing during render.
    return initialValue;
  }
}

interface KeyedState<T> {
  key: string;
  value: T;
}

/**
 * Like `useState`, but the value survives unmount/remount within the same
 * browser tab session (sessionStorage), scoped by `key`.
 *
 * Optional third argument (backwards-compatible): `validate` replaces the
 * derived shape check applied to a stored payload on read — a mismatching
 * value falls back to `initialValue`.
 */
export function usePersistedListState<T>(
  key: string,
  initialValue: T,
  options?: { validate?: (value: unknown) => value is T }
): [T, Dispatch<SetStateAction<T>>] {
  const [state, setState] = useState<KeyedState<T>>(() => ({
    key,
    value: readStored(key, initialValue, options),
  }));

  // `key` changed since the last render (e.g. the caller scopes it by
  // workspace ID and the user switched workspaces): re-read sessionStorage
  // for the NEW key right here, synchronously during render, instead of
  // waiting for an effect. This is React's documented pattern for
  // "resetting"/re-deriving state when something that behaves like a key
  // changes — it avoids both a stale-value flash (rendering the old
  // workspace's value under the new key for one frame) and the persistence
  // effect below writing the OLD key's value into the NEW key's storage
  // slot before the re-read would otherwise catch up.
  let currentValue = state.value;
  if (state.key !== key) {
    currentValue = readStored(key, initialValue, options);
    setState({ key, value: currentValue });
  }

  useEffect(() => {
    try {
      safeSessionStorage.setItem(key, JSON.stringify(currentValue));
    } catch {
      // `JSON.stringify` is the only remaining failure surface here (storage
      // lockout/quota is absorbed by safeSessionStorage) — persistence is a
      // nice-to-have, never block the UI on it.
    }
  }, [key, currentValue]);

  const setValue: Dispatch<SetStateAction<T>> = useCallback((update) => {
    setState((prev) => ({
      key: prev.key,
      value:
        typeof update === "function"
          ? (update as (prevValue: T) => T)(prev.value)
          : update,
    }));
  }, []);

  return [currentValue, setValue];
}
