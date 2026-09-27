/**
 * NotificationFeed — the notifications tab body of the `InterviewWidget`
 * panel (ADR-009).
 *
 * This is the code that used to live in the sidebar's `NotificationBell`
 * dropdown, moved verbatim in structure: a `role="menu"` region of
 * `role="menuitem"` rows, each row marking one notification read and handing
 * the caller an artifact to navigate to, plus a footer that marks the whole
 * feed read. The `role="menu"` semantics are carried over unchanged on
 * purpose — the rows *are* actions, and anything already keyed off the menu
 * role (assistive-tech expectations, the E2E selectors' shape) keeps working.
 * What changed is the container it sits in: a `role="tabpanel"` rather than a
 * popover anchored to the sidebar, and the panel's own Escape / outside-click
 * dismissal, which now lives in `InterviewWidget`.
 *
 * Presentational by design. It owns no fetching and no read state: the hook
 * `useNotificationFeed` is the single source of truth (ADR-009), and the
 * badge on the widget toggle and this list read the same state object. A
 * second fetch here would reintroduce the split state the ADR rejects.
 *
 * State matrix — all four states are rendered, never faked:
 *   loading → a `role="status"` line, the tab stays open and usable
 *   error   → a `role="status"` line naming the failure (the widget itself
 *             keeps working; a notification centre must never block the
 *             navigation chrome it lives in)
 *   empty   → `notifications.empty` ("Nichts Neues.")
 *   success → the list plus the mark-all footer
 */
import { useTranslation } from "react-i18next";

import type { Notification } from "../../api/notifications";
import type { NotificationFeedStatus } from "../../hooks/useNotificationFeed";
import styles from "./NotificationFeed.module.css";

export interface NotificationFeedProps {
  status: NotificationFeedStatus;
  notifications: Notification[];
  /** A mark-all is in flight; the footer action is disabled meanwhile. */
  markPending: boolean;
  /**
   * The opt-out could not be read from the server. Disclosed rather than
   * silently resolved: the hook fails open, so unread items are shown even
   * though it cannot prove the user wanted them.
   */
  preferencesFailed: boolean;
  onOpen: (notification: Notification) => void;
  onMarkAllRead: () => void;
}

export function NotificationFeed({
  status,
  notifications,
  markPending,
  preferencesFailed,
  onOpen,
  onMarkAllRead,
}: NotificationFeedProps): JSX.Element {
  const { t } = useTranslation();

  return (
    <div className={styles.feed} data-testid="interview-widget-notifications">
      {status === "loading" && (
        <p role="status" className={styles.state} data-testid="interview-widget-notifications-loading">
          {t("notifications.loading", "Notifications are loading …")}
        </p>
      )}

      {status === "error" && (
        <p role="status" className={styles.state} data-testid="interview-widget-notifications-error">
          {t("notifications.loadFailed", "Notifications could not be loaded.")}
        </p>
      )}

      {status === "success" && notifications.length === 0 && (
        <p className={styles.state} data-testid="interview-widget-notifications-empty">
          {t("notifications.empty", "Nothing new.")}
        </p>
      )}

      {preferencesFailed && (
        <p className={styles.notice} data-testid="interview-widget-notifications-preferences-unavailable">
          {t(
            "notifications.preferencesUnavailable",
            "Your notification settings could not be read, so these notifications are shown unfiltered."
          )}
        </p>
      )}

      {status === "success" && notifications.length > 0 && (
        // The menu region exists only when it has menuitems in it — an empty
        // `role="menu"` is a widget with nothing in it, which is what the
        // empty state above is for.
        <div
          className={styles.menu}
          role="menu"
          aria-label={t("notifications.ariaLabel", "Notifications")}
          data-testid="interview-widget-notifications-menu"
        >
          <ul className={styles.list}>
            {notifications.map((notification) => (
              <li key={notification.id}>
                <button
                  type="button"
                  role="menuitem"
                  className={
                    notification.read
                      ? `${styles.item} btn-ghost`
                      : `${styles.item} ${styles.itemUnread} btn-ghost`
                  }
                  onClick={() => onOpen(notification)}
                  data-testid={`interview-widget-notification-item-${notification.id}`}
                >
                  {notification.message}
                </button>
              </li>
            ))}
          </ul>
          <div className={styles.footer}>
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={onMarkAllRead}
              disabled={markPending}
              data-testid="interview-widget-notifications-mark-all"
            >
              {t("notifications.markAllRead", "Mark all as read")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
