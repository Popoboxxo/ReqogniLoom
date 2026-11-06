/**
 * ARCH-L1-001 ReactFrontend — Saved connection-view filters (P3 Task 3.2).
 *
 * "Saved views" are a per-user convenience: a name plus the URL parameters
 * that reproduce a filter set. They are stored through the existing
 * three-level preference API (`/users/me/preference-values/`, user scope) so
 * they follow the account across devices, exactly like the sidebar's
 * collapsed-group preference.
 *
 * The key is a `str_list` whose items are JSON-encoded view documents. If the
 * backend deployment does not yet know the key (the code registry rejects
 * unregistered keys with 400), the module degrades to `localStorage` so the
 * feature stays usable and never blocks the view. The fallback is deliberate,
 * not an error path the caller has to handle: `load` always answers a list and
 * `save` always succeeds locally.
 */

import { preferenceValuesApi } from "./preference-values";

/** Key under which the saved views live in the preference store. */
export const SAVED_VIEWS_PREFERENCE_KEY = "ui.connection_view.saved_views";

/** `localStorage` mirror used when the preference key is not registered. */
const LOCAL_STORAGE_KEY = "reqlo.connection_view.saved_views";

/** One named filter snapshot. `params` is the URL search string's data. */
export interface SavedConnectionView {
  id: string;
  name: string;
  /** The serialized `URLSearchParams` entries of the saved view. */
  params: Record<string, string>;
}

function parseViews(raw: unknown): SavedConnectionView[] {
  if (!Array.isArray(raw)) return [];
  const views: SavedConnectionView[] = [];
  for (const entry of raw) {
    if (typeof entry !== "string") continue;
    try {
      const parsed = JSON.parse(entry) as Partial<SavedConnectionView>;
      if (
        typeof parsed.id === "string" &&
        typeof parsed.name === "string" &&
        parsed.params &&
        typeof parsed.params === "object"
      ) {
        views.push({
          id: parsed.id,
          name: parsed.name,
          params: parsed.params as Record<string, string>,
        });
      }
    } catch {
      // A malformed item must never take the whole list down.
    }
  }
  return views;
}

function readLocal(): SavedConnectionView[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(LOCAL_STORAGE_KEY);
    return raw ? parseViews(JSON.parse(raw)) : [];
  } catch {
    return [];
  }
}

function writeLocal(views: SavedConnectionView[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(views));
  } catch {
    // Quota/private-mode failures are not worth breaking the view for.
  }
}

export const connectionViewsApi = {
  /**
   * Load the caller's saved views: preference store first, `localStorage` as
   * the transparent fallback. Never rejects.
   */
  async load(): Promise<SavedConnectionView[]> {
    try {
      const level = await preferenceValuesApi.getLevel("user");
      const stored = level.values[SAVED_VIEWS_PREFERENCE_KEY];
      if (stored !== undefined) return parseViews(stored);
    } catch {
      // Unregistered key or unavailable backend -> local mirror.
    }
    return readLocal();
  },

  /**
   * Persist the caller's saved views. Mirrors to `localStorage` in every case
   * so a subsequent `load()` on a backend without the key still sees them.
   */
  async save(views: SavedConnectionView[]): Promise<void> {
    writeLocal(views);
    try {
      await preferenceValuesApi.patchLevel("user", {
        [SAVED_VIEWS_PREFERENCE_KEY]: views.map((view) =>
          JSON.stringify(view)
        ),
      });
    } catch {
      // Degraded (unregistered key): the local mirror is already written.
    }
  },
};
