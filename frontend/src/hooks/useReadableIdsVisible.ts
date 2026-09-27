/**
 * Issue #1094 — the "readable ids may be hidden" display preference.
 *
 * Scope of the persistence, stated up front because it is a real gap and not an
 * oversight: **this preference is browser-local.** The two self-service
 * preference endpoints in the repo cannot carry it:
 *
 *   - `GET/PATCH /api/v1/users/me/notification-preferences/` validates against
 *     the CLOSED four-kind trigger vocabulary
 *     (`application.notification_preference_service.ALL_KINDS`); an unknown
 *     kind is a 400 ("Unknown notification trigger(s)").
 *   - `GET/PATCH /api/v1/users/me/preferences/` is a *workspace-scoped* row
 *     whose one field is `optional_artifact_visibility` — read by
 *     `api/preferences.ts` as a fixed six-key `FeatureVisibility` map, and
 *     merged by the backend as `{**preset, **overrides}`. Smuggling a display
 *     flag in there would be a semantic abuse of "which optional artifact
 *     types are visible", it would need a `workspace_id` for what is a
 *     user-global preference, and no client would ever read it back.
 *
 * So the toggle is kept local (`localStorage`) and a backend display-preference
 * endpoint is reported as needed. Inventing a REST resource for it here would
 * have been out of scope and out of the reviewer's hands to revert.
 *
 * Why a module-level store with `useSyncExternalStore` rather than
 * `usePersistedListState` or a per-component `useState`:
 *
 *   - the preference is read by *every* `<IdChip>` on the page. A virtualized
 *     artifact list mounts hundreds of rows; one `useState` + one `storage`
 *     listener per row would be hundreds of listeners for one boolean.
 *   - `usePersistedListState` is `sessionStorage` + a caller-supplied key, and
 *     its docstring rules it out explicitly: it is for "leave it as you had it
 *     during this tab session", not for a preference that should follow the
 *     user across sessions.
 *   - `useSyncExternalStore` gives one `storage` listener for the whole app and
 *     a consistent snapshot across components mid-render.
 */

import { useCallback, useSyncExternalStore } from "react";

/** localStorage key. `reqflow-` prefix matches the other persisted view state. */
export const READABLE_IDS_STORAGE_KEY = "reqflow-display-readable-ids";

/** Readable ids are shown unless the user says otherwise. */
export const READABLE_IDS_VISIBLE_DEFAULT = true;

/**
 * Defensive localStorage access (same reasoning as `InterviewWidget`'s
 * `safeLocalStorage`, issue #679): the property is absent in some jsdom
 * environments and throws a `SecurityError` in private-browsing mode. A display
 * preference is never worth breaking a render over.
 */
function readStorage(): string | null {
  try {
    return window.localStorage.getItem(READABLE_IDS_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStorage(value: string): void {
  try {
    window.localStorage.setItem(READABLE_IDS_STORAGE_KEY, value);
  } catch {
    /* storage unavailable — the in-memory value below still applies */
  }
}

function normalize(raw: string | null): boolean {
  if (raw === null) return READABLE_IDS_VISIBLE_DEFAULT;
  return raw !== "false";
}

let snapshot: boolean = normalize(typeof window === "undefined" ? null : readStorage());
const listeners = new Set<() => void>();
let storageBound = false;

function emit(): void {
  snapshot = normalize(readStorage());
  for (const listener of [...listeners]) listener();
}

function onStorage(event: StorageEvent): void {
  // A `null` key is `localStorage.clear()`; a foreign key is another
  // preference's business.
  if (event.key !== null && event.key !== READABLE_IDS_STORAGE_KEY) return;
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
  return READABLE_IDS_VISIBLE_DEFAULT;
}

/** Current value, readable outside React (tests, non-React call sites). */
export function getReadableIdsVisible(): boolean {
  return snapshot;
}

/**
 * Imperative setter. Also notifies every mounted subscriber, so a write from
 * one component is reflected in every `<IdChip>` in the same tab immediately —
 * the `storage` event only fires in *other* tabs.
 */
export function setReadableIdsVisible(next: boolean): void {
  writeStorage(String(next));
  emit();
}

/**
 * `[readableIdsVisible, setReadableIdsVisible]`.
 *
 * `setReadableIdsVisible` is a module-level function, so it is stable across
 * renders and safe in a consumer's dependency array.
 */
export function useReadableIdsVisible(): [boolean, (next: boolean) => void] {
  const visible = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // `useCallback` is redundant for a module-level function, but it keeps the
  // returned tuple's identity stable for consumers that memoise on the setter.
  const setVisible = useCallback((next: boolean) => setReadableIdsVisible(next), []);
  return [visible, setVisible];
}
