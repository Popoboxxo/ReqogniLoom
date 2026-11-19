/**
 * Task 2 (Schnitt 1b) — the "trace spine footer visible" display preference.
 *
 * One of TWO INDEPENDENT user toggles (the other is `useInspectorVisible`).
 * Each owns its own module-level store, its own localStorage key and its own
 * listener set: changing one can never move the other, and both may be on at
 * the same time (the status quo before this feature).
 *
 * Deliberately the same shape as `useReadableIdsVisible`:
 *
 *   - `localStorage` is the **first-render fallback**, so every consumer can
 *     paint synchronously before a network round trip completes;
 *   - the server (`GET/PATCH /users/me/display-preferences/`) is the source of
 *     truth — `components/PreferencesHydrator` writes the resolved
 *     `trace_footer_enabled` value through `setTraceFooterVisible`, and
 *     `UserProfileSettings/AppearanceSection` is the writer on the profile page;
 *   - `useSyncExternalStore` gives one `storage` listener for the whole app and
 *     a consistent snapshot across components mid-render.
 *
 * The network calls never live here — this module is the synchronous read
 * surface, not a request lifecycle.
 */

import { useCallback, useSyncExternalStore } from "react";

import { safeLocalStorage } from "../utils/safeStorage";

/** localStorage key for the first-render cache. */
export const TRACE_FOOTER_STORAGE_KEY = "reqflow-display-trace-footer";

/** The footer is shown unless the user says otherwise. */
export const TRACE_FOOTER_VISIBLE_DEFAULT = true;

function normalize(raw: string | null): boolean {
  if (raw === null) return TRACE_FOOTER_VISIBLE_DEFAULT;
  return raw !== "false";
}

let snapshot: boolean = normalize(
  safeLocalStorage.getItem(TRACE_FOOTER_STORAGE_KEY)
);
const listeners = new Set<() => void>();
let storageBound = false;

function notify(): void {
  for (const listener of [...listeners]) listener();
}

function emit(): void {
  snapshot = normalize(safeLocalStorage.getItem(TRACE_FOOTER_STORAGE_KEY));
  notify();
}

function onStorage(event: StorageEvent): void {
  // A `null` key is `localStorage.clear()`; a foreign key is another
  // preference's business (notably the inspector toggle's key).
  if (event.key !== null && event.key !== TRACE_FOOTER_STORAGE_KEY) return;
  emit();
}

function bindStorageListener(): void {
  if (storageBound || typeof window === "undefined") return;
  storageBound = true;
  window.addEventListener("storage", onStorage);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  bindStorageListener();
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): boolean {
  return snapshot;
}

function getServerSnapshot(): boolean {
  return TRACE_FOOTER_VISIBLE_DEFAULT;
}

/** Current value, readable outside React (tests, hydrator, non-React callers). */
export function getTraceFooterVisible(): boolean {
  return snapshot;
}

/**
 * Imperative setter, also used to apply a server response and to roll back a
 * rejected save. The in-memory value is authoritative: re-deriving it from a
 * locked/unavailable storage (as an earlier pattern did) would silently revert
 * a freshly-set `false` back to the default `true`.
 */
export function setTraceFooterVisible(next: boolean): void {
  safeLocalStorage.setItem(TRACE_FOOTER_STORAGE_KEY, String(next));
  snapshot = next;
  notify();
}

/** `[traceFooterVisible, setTraceFooterVisible]` (setter is stable). */
export function useTraceFooterVisible(): [boolean, (next: boolean) => void] {
  const visible = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const setVisible = useCallback((next: boolean) => setTraceFooterVisible(next), []);
  return [visible, setVisible];
}
