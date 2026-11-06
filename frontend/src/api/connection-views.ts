/**
 * ARCH-L1-001 ReactFrontend — Saved connection-view filters (P3 Task 3.2).
 *
 * "Saved views" are a per-user convenience: a name plus the URL parameters
 * that reproduce a filter set. They are stored through the three-level
 * preference API (`/users/me/preference-values/`, user scope only) so they
 * follow the account across devices, exactly like the sidebar's
 * collapsed-group preference.
 *
 * The key is a `str_list` whose items are JSON-encoded view documents and is
 * registered in the backend preference registry, so no client-side mirror
 * exists: the preference store is the single source of truth.
 *
 * `load` still never rejects — a transport error must not take the whole view
 * down, and an absent key simply means "no saved views". `save` deliberately
 * propagates its rejection so the caller can report a failed write.
 */

import { preferenceValuesApi } from "./preference-values";

/** Key under which the saved views live in the preference store. */
export const SAVED_VIEWS_PREFERENCE_KEY = "ui.connection_view.saved_views";

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

export const connectionViewsApi = {
  /**
   * Load the caller's saved views from the user level of the preference
   * store. An absent key yields `[]` (no saved views). Never rejects.
   */
  async load(): Promise<SavedConnectionView[]> {
    try {
      const level = await preferenceValuesApi.getLevel("user");
      return parseViews(level.values[SAVED_VIEWS_PREFERENCE_KEY]);
    } catch {
      // Unavailable backend: show an empty list rather than breaking the view.
      return [];
    }
  },

  /**
   * Persist the caller's saved views at the user level. A rejected write is
   * handed to the caller — the UI reports it instead of pretending success.
   */
  async save(views: SavedConnectionView[]): Promise<void> {
    await preferenceValuesApi.patchLevel("user", {
      [SAVED_VIEWS_PREFERENCE_KEY]: views.map((view) => JSON.stringify(view)),
    });
  },
};
