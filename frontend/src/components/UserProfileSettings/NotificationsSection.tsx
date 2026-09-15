/**
 * ARCH-L1-001 ReactFrontend — NotificationsSection (UserProfileSettings).
 *
 * leaf_id: COMP-RF-006 (UserProfileSettings — user-owned data controls)
 *
 * OD-1 (2026-09-15): the four notification triggers, visible and changeable on
 * the profile page. The checkbox is the *enabled* state (checked = the trigger
 * is on) even though the stored model is an opt-out `disabled_triggers` list —
 * the UI must not make the user invert it mentally (see
 * notification-preferences.ts; the wire surface only ever exposes the
 * effective map).
 *
 * Toggle handling follows the workspace-scoped visibility section in
 * UserProfileSettings.tsx (the closest precedent — same "toggle one per-user
 * preference" shape): only the toggled row's checkbox is disabled while its
 * PATCH is in flight, the server's returned map is applied on success, and a
 * failure surfaces in a `role="alert"` element while the previous state stays
 * intact. The box is never flipped optimistically and then lied about.
 */

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  NOTIFICATION_PREFERENCE_KINDS,
  notificationPreferencesApi,
  type NotificationPreferenceKind,
  type NotificationPreferences,
} from "../../api/notification-preferences";
import styles from "./NotificationsSection.module.css";

/**
 * Best-effort human-readable message from a thrown API error. Returns `""` when
 * the value carries none, so the caller can substitute localized copy.
 */
function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? "";
}

export function NotificationsSection(): JSX.Element {
  const { t } = useTranslation();
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingKind, setPendingKind] = useState<NotificationPreferenceKind | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      setPreferences(await notificationPreferencesApi.get());
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleToggle = useCallback(
    async (kind: NotificationPreferenceKind, enabled: boolean): Promise<void> => {
      setError(null);
      setPendingKind(kind);
      try {
        // The server's returned map wins — never assume the click took effect.
        setPreferences(await notificationPreferencesApi.update({ [kind]: enabled }));
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        setPendingKind(null);
      }
    },
    []
  );

  // Literal `t()` calls (not a lookup map) so static key scans — and Task 30 —
  // can read the exact key vocabulary off this component.
  const kindLabel = (kind: NotificationPreferenceKind): string => {
    switch (kind) {
      case "assigned":
        return t("notificationPreferences.assigned", "An artifact is assigned to me");
      case "comment_added":
        return t("notificationPreferences.comment_added", "Someone comments on my artifacts");
      case "transition_pending":
        return t("notificationPreferences.transition_pending", "A workflow transition awaits me");
      case "suspect_flagged":
        return t("notificationPreferences.suspect_flagged", "One of my artifacts was flagged suspect");
    }
  };

  return (
    <section className={styles.section} data-testid="notification-preferences-section">
      <h2 className={styles.heading}>{t("notificationPreferences.title", "Notifications")}</h2>
      <p className={styles.hint}>
        {t(
          "notificationPreferences.hint",
          "Choose which events send you a notification. The switches are yours alone and can be changed at any time."
        )}
      </p>

      {error !== null && (
        <p role="alert" data-testid="notification-preferences-error" className={styles.error}>
          {error || t("notificationPreferences.error", "Notification preferences could not be saved.")}
        </p>
      )}

      {isLoading ? (
        <p
          role="status"
          data-testid="notification-preferences-loading"
          className={styles.loadingText}
        >
          {t("notificationPreferences.loading", "Loading…")}
        </p>
      ) : (
        preferences && (
          <div className={styles.rows}>
            {NOTIFICATION_PREFERENCE_KINDS.map((kind) => {
              const isPending = pendingKind === kind;
              return (
                <div
                  key={kind}
                  className={styles.row}
                  data-testid={`notification-pref-row-${kind}`}
                >
                  <label className={styles.label}>
                    <input
                      type="checkbox"
                      className={styles.checkbox}
                      checked={preferences[kind]}
                      disabled={isPending}
                      onChange={(e) => void handleToggle(kind, e.target.checked)}
                      data-testid={`notification-pref-checkbox-${kind}`}
                    />
                    <span className={styles.labelText}>{kindLabel(kind)}</span>
                  </label>
                </div>
              );
            })}
          </div>
        )
      )}
    </section>
  );
}
