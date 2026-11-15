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
 * The same module owns the connection view's two display switches
 * (navigation plan V.0): `ui.connection_view.show_edges` and
 * `ui.connection_view.filters_expanded`. Both are user-scoped booleans, so
 * they are read and written at the user level only — a workspace admin must
 * not change another person's reading aid, and the backend rejects any other
 * level. These helpers keep no state of their own: the component owns the
 * current value and stays authoritative while a write is in flight and after
 * it fails, which is what "the state stays local" means here.
 *
 * `load` still never rejects — a transport error must not take the whole view
 * down, and an absent key simply means "no saved views". `save` deliberately
 * propagates its rejection so the caller can report a failed write.
 */

import { preferenceValuesApi } from "./preference-values";

/** Key under which the saved views live in the preference store. */
export const SAVED_VIEWS_PREFERENCE_KEY = "ui.connection_view.saved_views";

/**
 * Key of the trees-mode edge overlay switch (navigation plan V.0, spec D7).
 * Registered as a user-scoped `bool` with default `true`.
 */
export const SHOW_EDGES_PREFERENCE_KEY = "ui.connection_view.show_edges";

/**
 * Key of the extra-filter popover's expanded state (navigation plan V.0, spec
 * D8). Registered as a user-scoped `bool` with default `false`.
 */
export const FILTERS_EXPANDED_PREFERENCE_KEY =
  "ui.connection_view.filters_expanded";

/** Registry default of {@link SHOW_EDGES_PREFERENCE_KEY}. */
export const SHOW_EDGES_DEFAULT = true;

/** Registry default of {@link FILTERS_EXPANDED_PREFERENCE_KEY}. */
export const FILTERS_EXPANDED_DEFAULT = false;

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

/**
 * Read one user-scoped `bool` preference, falling back to *fallback* for every
 * non-boolean outcome: absent key, `null`, a foreign type, or a failed read.
 * A preference must never keep a page from painting, so the read cannot reject.
 */
async function loadUserBoolean(
  key: string,
  fallback: boolean
): Promise<boolean> {
  try {
    const level = await preferenceValuesApi.getLevel("user");
    const raw = level.values[key];
    return typeof raw === "boolean" ? raw : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Write one user-scoped `bool` preference. The rejection is propagated on
 * purpose: the caller keeps its local state, keeps the switch where the user
 * put it, and reports the failed write instead of pretending it was stored.
 *
 * The transport is the keepalive PATCH in `preference-values.ts`, so the write
 * outlives an immediate reload; `ConnectionView` additionally serializes the
 * click stream (`preference-write-queue.ts`) so two fast clicks cannot produce
 * out-of-order requests.
 */
async function saveUserBoolean(key: string, value: boolean): Promise<void> {
  await preferenceValuesApi.patchLevel("user", { [key]: value });
}

/**
 * Load the caller's edge-overlay switch. Defaults to `true` when the store is
 * unreachable or the key was never set (spec D7).
 */
export async function loadShowEdges(): Promise<boolean> {
  return loadUserBoolean(SHOW_EDGES_PREFERENCE_KEY, SHOW_EDGES_DEFAULT);
}

/** Persist the edge-overlay switch; a rejected write reaches the caller. */
export async function saveShowEdges(showEdges: boolean): Promise<void> {
  await saveUserBoolean(SHOW_EDGES_PREFERENCE_KEY, showEdges);
}

/**
 * Load the caller's extra-filter popover state. Defaults to `false` — the
 * popover starts collapsed — when the store is unreachable or unset (D8).
 */
export async function loadFiltersExpanded(): Promise<boolean> {
  return loadUserBoolean(
    FILTERS_EXPANDED_PREFERENCE_KEY,
    FILTERS_EXPANDED_DEFAULT
  );
}

/** Persist the popover state; a rejected write reaches the caller. */
export async function saveFiltersExpanded(expanded: boolean): Promise<void> {
  await saveUserBoolean(FILTERS_EXPANDED_PREFERENCE_KEY, expanded);
}
