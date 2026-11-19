/**
 * Task 2 (Schnitt 1b) — the "inspector visible" display preference.
 *
 * One of TWO INDEPENDENT user toggles (the other is `useTraceFooterVisible`).
 * Each owns its own module-level store, its own localStorage key and its own
 * listener set: changing one can never move the other, and both may be on at
 * the same time (the status quo before this feature — D2b of the plan).
 *
 * Same shape as `useReadableIdsVisible`: localStorage is the first-render
 * fallback, the server (`inspector_enabled` on the self-service endpoint) is
 * the source of truth, and `useSyncExternalStore` gives one storage listener
 * for the whole app. Network lifecycle stays in `PreferencesHydrator` and
 * `UserProfileSettings/AppearanceSection`.
 */

import { useCallback, useSyncExternalStore } from "react";

import { safeLocalStorage } from "../utils/safeStorage";

/** localStorage key for the first-render cache. */
export const INSPECTOR_STORAGE_KEY = "reqflow-display-inspector";

/** The inspector is shown unless the user says otherwise. */
export const INSPECTOR_VISIBLE_DEFAULT = true;

function normalize(raw: string | null): boolean {
  if (raw === null) return INSPECTOR_VISIBLE_DEFAULT;
  return raw !== "false";
}

let snapshot: boolean = normalize(safeLocalStorage.getItem(INSPECTOR_STORAGE_KEY));
const listeners = new Set<() => void>();
let storageBound = false;

function notify(): void {
  for (const listener of [...listeners]) listener();
}

function emit(): void {
  snapshot = normalize(safeLocalStorage.getItem(INSPECTOR_STORAGE_KEY));
  notify();
}

function onStorage(event: StorageEvent): void {
  // A foreign key is the other preference's business (notably the footer's).
  if (event.key !== null && event.key !== INSPECTOR_STORAGE_KEY) return;
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
  return INSPECTOR_VISIBLE_DEFAULT;
}

/** Current value, readable outside React (tests, hydrator, non-React callers). */
export function getInspectorVisible(): boolean {
  return snapshot;
}

/** Imperative setter — applies a server response or rolls back a rejected save. */
export function setInspectorVisible(next: boolean): void {
  safeLocalStorage.setItem(INSPECTOR_STORAGE_KEY, String(next));
  snapshot = next;
  notify();
}

/** `[inspectorVisible, setInspectorVisible]` (setter is stable). */
export function useInspectorVisible(): [boolean, (next: boolean) => void] {
  const visible = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const setVisible = useCallback((next: boolean) => setInspectorVisible(next), []);
  return [visible, setVisible];
}
