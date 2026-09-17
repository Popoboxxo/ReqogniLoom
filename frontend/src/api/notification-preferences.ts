/**
 * ARCH-L1-001 ReactFrontend — Notification delivery preferences API.
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * Wraps the backend endpoint under /api/v1/users/me/notification-preferences/
 * (NotificationPreferenceView, OD-1 2026-09-15): the caller's OWN opt-out
 * switches over the four notification triggers. Same self-service shape as
 * users/me/preferences/ — no admin gate, any authenticated user, no role
 * required. The wrapper is consumed by direct import (NotificationsSection);
 * it is deliberately NOT re-exported from api/index.ts, exactly like
 * memory-self-service.ts.
 *
 * The stored model is opt-out (`disabled_triggers`); the wire surface only
 * ever exposes the *effective* map (a missing row means all triggers on), so
 * the inverted list never reaches the client.
 *
 * No MCP counterpart: a notification preference is a human preference, and
 * notifications deliberately have no agent-facing surface (plan §6).
 */

import { apiClient } from "./client";

/** The four notification triggers a user can switch on or off. */
export type NotificationPreferenceKind =
  | "assigned"
  | "comment_added"
  | "transition_pending"
  | "suspect_flagged";

/** All kinds, in display order. Mirrors OPTIONAL_FEATURES in preferences.ts. */
export const NOTIFICATION_PREFERENCE_KINDS: readonly NotificationPreferenceKind[] = [
  "assigned",
  "comment_added",
  "transition_pending",
  "suspect_flagged",
] as const;

/** Effective per-kind preference map (true = the trigger is enabled). */
export type NotificationPreferences = Record<NotificationPreferenceKind, boolean>;

/** Backend response shape for both GET and PATCH on this path. */
interface NotificationPreferenceResponse {
  preferences: NotificationPreferences;
}

const PATH = "/users/me/notification-preferences/";

export const notificationPreferencesApi = {
  /**
   * GET /users/me/notification-preferences/ — the caller's effective map.
   * A missing backend row is reported by the server as all-`true`.
   */
  async get(): Promise<NotificationPreferences> {
    const resp = await apiClient.get<NotificationPreferenceResponse>(PATH);
    return resp.preferences;
  },

  /**
   * PATCH /users/me/notification-preferences/ — partial update of the supplied
   * kinds. Returns the server's resulting effective map, which is what the
   * caller should render (never a locally guessed value).
   */
  async update(
    changes: Partial<Record<NotificationPreferenceKind, boolean>>
  ): Promise<NotificationPreferences> {
    const resp = await apiClient.patch<NotificationPreferenceResponse>(PATH, {
      preferences: changes,
    });
    return resp.preferences;
  },
};
