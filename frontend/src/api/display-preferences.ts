/**
 * ARCH-L1-001 ReactFrontend — User display-preference API (Issue #1096).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * Wraps the self-service endpoint under /api/v1/users/me/display-preferences/
 * (DisplayPreferenceView, Issue #1096): the caller's own UI display flags.
 * Today that is the single flag `show_readable_ids`, which decides whether the
 * readable, per-workspace artifact id (e.g. `REQ-001`) is rendered by
 * `<IdChip>`. Copying is unaffected — the chip always copies the system id
 * (UUID); only its visibility is controlled here.
 *
 * Same self-service shape as `api/notification-preferences.ts`: no admin gate,
 * any authenticated user, no `user_id`/`workspace_id` parameter — the server
 * derives the caller from the session, and `ctx.user_id` is the whole
 * authorization boundary. Consumed by direct import (IdentifiersSection) and
 * deliberately NOT re-exported from `api/index.ts`, exactly like
 * notification-preferences.ts and memory.ts (self-service user surfaces).
 *
 * The server is the source of truth. `useReadableIdsVisible` keeps its
 * localStorage value only as a first-render fallback so every `<IdChip>` can
 * paint before a network round trip completes; this wrapper is what makes the
 * choice actually follow the account across browsers and devices.
 */

import { apiClient } from "./client";

/** Wire shape for both GET and PATCH on this path. */
export interface DisplayPreferences {
  show_readable_ids: boolean;
}

const PATH = "/users/me/display-preferences/";

export const displayPreferencesApi = {
  /**
   * GET — the caller's effective display flags. A missing backend row is
   * reported by the server as the default (`show_readable_ids: true`), so the
   * caller never has to re-derive that default.
   */
  async get(): Promise<DisplayPreferences> {
    return apiClient.get<DisplayPreferences>(PATH);
  },

  /**
   * PATCH — partial update of the supplied flags. Returns the server's fresh
   * effective flags, which is what the caller must render (never a locally
   * guessed value).
   */
  async update(changes: Partial<DisplayPreferences>): Promise<DisplayPreferences> {
    return apiClient.patch<DisplayPreferences>(PATH, changes);
  },
};
