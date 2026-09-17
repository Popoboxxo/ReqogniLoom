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
 */

import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";

function readStored<T>(key: string, initialValue: T): T {
  if (typeof window === "undefined" || !window.sessionStorage) {
    return initialValue;
  }
  try {
    const raw = window.sessionStorage.getItem(key);
    if (raw === null) return initialValue;
    return JSON.parse(raw) as T;
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
 */
export function usePersistedListState<T>(
  key: string,
  initialValue: T
): [T, Dispatch<SetStateAction<T>>] {
  const [state, setState] = useState<KeyedState<T>>(() => ({
    key,
    value: readStored(key, initialValue),
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
    currentValue = readStored(key, initialValue);
    setState({ key, value: currentValue });
  }

  useEffect(() => {
    if (typeof window === "undefined" || !window.sessionStorage) return;
    try {
      window.sessionStorage.setItem(key, JSON.stringify(currentValue));
    } catch {
      // Storage full/unavailable (e.g. private browsing) — persistence is
      // a nice-to-have, never block the UI on it.
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
