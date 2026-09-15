/**
 * NotificationBell — unread counter plus a dropdown of recent notifications.
 *
 * Menschen-im-System spec §5. Fetched once on mount and after each mark-read;
 * there is deliberately no polling and no push (that would be the very
 * infrastructure the spec rules out).
 *
 * A failing fetch stays silent: a notification centre must never block the
 * navigation chrome it lives in.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { notificationsApi, type Notification } from "../../api/notifications";
import styles from "./NotificationBell.module.css";

export function NotificationBell(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  const load = useCallback(async (): Promise<void> => {
    try {
      const feed = await notificationsApi.list();
      setNotifications(feed.notifications);
      setUnreadCount(feed.unreadCount);
    } catch {
      // Silent by design — see the module docstring.
      setNotifications([]);
      setUnreadCount(0);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleItemClick = useCallback(
    async (notification: Notification): Promise<void> => {
      try {
        await notificationsApi.markRead(notification.id);
      } catch {
        // Navigation matters more than the read flag; fall through.
      }
      setOpen(false);
      await load();
      if (notification.artifactId) {
        navigate(`/artifacts/${notification.artifactId}`);
      }
    },
    [load, navigate]
  );

  const handleMarkAll = useCallback(async (): Promise<void> => {
    try {
      await notificationsApi.markAllRead();
    } catch {
      // Ignore — the refetch below reflects whatever actually happened.
    }
    await load();
  }, [load]);

  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={styles.toggle}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={t("notifications.ariaLabel", "Notifications")}
        onClick={() => setOpen((previous) => !previous)}
        data-testid="notification-bell-toggle"
      >
        <span aria-hidden="true">{"\u{1F514}"}</span>
        <span>{t("notifications.label", "Notifications")}</span>
        {unreadCount > 0 && (
          <span className={styles.badge} data-testid="notification-bell-badge">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className={styles.dropdown} role="menu" data-testid="notification-bell-dropdown">
          {notifications.length === 0 ? (
            <p className={styles.empty} data-testid="notification-bell-empty">
              {t("notifications.empty", "Nothing new.")}
            </p>
          ) : (
            <ul className={styles.list}>
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <button
                    type="button"
                    role="menuitem"
                    className={
                      notification.read
                        ? styles.item
                        : `${styles.item} ${styles.itemUnread}`
                    }
                    onClick={() => void handleItemClick(notification)}
                    data-testid={`notification-bell-item-${notification.id}`}
                  >
                    {notification.message}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className={styles.footer}>
            <button
              type="button"
              className={styles.item}
              onClick={() => void handleMarkAll()}
              data-testid="notification-bell-mark-all"
            >
              {t("notifications.markAllRead", "Mark all as read")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
