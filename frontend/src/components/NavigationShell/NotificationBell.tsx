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

import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { notificationsApi, type Notification } from "../../api/notifications";
import styles from "./NotificationBell.module.css";

export function NotificationBell(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const toggleRef = useRef<HTMLButtonElement | null>(null);
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

  // Issue #985: the popover used to be undismissable from the keyboard and
  // ignored a click outside — a real user review on the QS instance ended in
  // "why doesn't this go away any more?". Both halves of the standard popover
  // contract live here now.
  //
  // Escape follows the same precedence as `useFocusTrap` (the shared Dialog
  // primitive): the *innermost* overlay handles the key and stops it, so an
  // outer overlay listening on the document does not also close. This is what
  // makes a future nesting inside a dialog behave.
  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      // Focus returns to the trigger, which is where the user came from.
      toggleRef.current?.focus();
    };

    // `pointerdown`, not `click`: the click that *opens* the popover would
    // otherwise be caught by the same listener on the way up the document.
    const handlePointerDown = (event: PointerEvent): void => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (wrapperRef.current?.contains(target)) return;
      setOpen(false);
    };

    document.addEventListener("keydown", handleKeyDown, true);
    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [open]);

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
    <div className={styles.wrapper} ref={wrapperRef}>
      <button
        type="button"
        className={styles.toggle}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={t("notifications.ariaLabel", "Notifications")}
        onClick={() => setOpen((previous) => !previous)}
        data-testid="notification-bell-toggle"
        ref={toggleRef}
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
