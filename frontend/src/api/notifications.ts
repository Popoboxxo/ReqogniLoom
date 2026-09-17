/**
 * The notification feed (Menschen-im-System spec §5).
 *
 * No real-time push by design: the bell fetches this once when the
 * NavigationShell mounts, and again after a mark-read action.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export type NotificationKind =
  | "transition_pending"
  | "suspect_flagged"
  | "assigned"
  | "comment_added";

interface NotificationWire {
  id: string;
  kind: NotificationKind;
  artifact_id: string | null;
  message: string;
  read: boolean;
  created_at: string;
}

interface FeedWire {
  notifications: NotificationWire[];
  unread_count: number;
}

export interface Notification {
  id: UUID;
  kind: NotificationKind;
  artifactId: UUID | null;
  message: string;
  read: boolean;
  createdAt: string;
}

export interface NotificationFeed {
  notifications: Notification[];
  unreadCount: number;
}

/** Bell dropdown size. The backend clamps anything above 200. */
export const NOTIFICATION_FEED_LIMIT = 20;

function toNotification(wire: NotificationWire): Notification {
  return {
    id: wire.id,
    kind: wire.kind,
    artifactId: wire.artifact_id,
    message: wire.message,
    read: wire.read,
    createdAt: wire.created_at,
  };
}

export const notificationsApi = {
  /** Fetch the caller's feed together with the unread count (one round trip). */
  async list(limit: number = NOTIFICATION_FEED_LIMIT): Promise<NotificationFeed> {
    const wire = await apiClient.get<FeedWire>(`/notifications/?limit=${limit}`);
    return {
      notifications: wire.notifications.map(toNotification),
      unreadCount: wire.unread_count,
    };
  },

  /** Mark one notification read. */
  async markRead(notificationId: UUID): Promise<Notification> {
    return toNotification(
      await apiClient.post<NotificationWire>(`/notifications/${notificationId}/read/`, {})
    );
  },

  /** Mark the whole feed read; returns how many rows changed. */
  async markAllRead(): Promise<number> {
    const result = await apiClient.post<{ marked: number }>(
      "/notifications/mark-all-read/",
      {}
    );
    return result.marked;
  },
};
