/**
 * Issue #1094 — the "readable ids may be hidden" display preference.
 *
 * Issue #1096 — persistence is now server-backed. The account-scoped endpoint
 * `GET/PATCH /api/v1/users/me/display-preferences/` (wrapped by
 * `api/display-preferences.ts`) is the source of truth. This hook remains the
 * synchronous, app-wide *read* surface and the first-render cache:
 *
 *   - `localStorage` is the **first-render fallback**, so every `<IdChip>` can
 *     paint immediately instead of waiting for a network round trip, and the
 *     value survives a reload before the GET answers;
 *   - the server response is written back through `setReadableIdsVisible`
 *     (which also refreshes the cache), and a failed PATCH rolls the store back
 *     to the previous value — the UI never keeps a change the server rejected.
 *
 * The network calls themselves live in `IdentifiersSection` (the only writer,
 * on the profile page), where loading and error states have a place to render.
 * Keeping this module synchronous is deliberate: it is read by *every* chip and
 * row, so it must never own request lifecycle. See the backend
 * `application/display_preference_service.py` for the server half.
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

/**
 * localStorage key for the first-render cache (issue #1096). `reqflow-` prefix
 * matches the other persisted view state. The server value wins once it arrives;
 * this key exists so the preference is available synchronously on the very first
 * paint and offline.
 */
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

/** Notify every mounted subscriber, without touching the snapshot. */
function notify(): void {
  for (const listener of [...listeners]) listener();
}

function emit(): void {
  snapshot = normalize(readStorage());
  notify();
}

function onStorage(event: StorageEvent): void {
  // A `null` key is `localStorage.clear()`; a foreign key is another
  // preference's business.
  if (event.key !== null && event.key !== READABLE_IDS_STORAGE_KEY) return;
  // Cross-tab path only: the `storage` event fires in documents OTHER than the
  // one that wrote, so the in-memory snapshot here is stale and storage is the
  // source for this notification.
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
  // FR-U3-01: the in-memory value is authoritative. Re-deriving the snapshot
  // from `readStorage()` here (as this setter used to via `emit()`) silently
  // reverted a freshly-set `false` back to the default `true` whenever storage
  // was unavailable (private browsing, quota): `readStorage()` returns `null`,
  // `normalize(null)` is the default. The value the user just chose vanished
  // with no error. Only the cross-tab `storage` path re-reads storage.
  snapshot = next;
  notify();
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
