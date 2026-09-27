/**
 * `useNotificationFeed` — the single source of truth for the unread signal
 * (ADR-009).
 *
 * The component tests prove the badge and the feed *render* the right things.
 * What only the hook can be asked, and what ADR-009 actually turns on, is:
 *
 *  - there is exactly ONE fetch, so the badge and the feed cannot disagree;
 *  - nothing is persisted, so no cached value can outlive an opt-out
 *    (the ADR's own verification note about the widget's `localStorage`
 *    open state versus the account-scoped preference);
 *  - a broken preferences endpoint fails OPEN — a working feed is never
 *    silently hidden.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useNotificationFeed, NOTIFICATION_PREFERENCES_CHANGED_EVENT } from "./useNotificationFeed";
import { notificationsApi } from "../api/notifications";
import { notificationPreferencesApi } from "../api/notification-preferences";

vi.mock("../api/notifications", () => ({
  NOTIFICATION_FEED_LIMIT: 20,
  notificationsApi: { list: vi.fn(), markRead: vi.fn(), markAllRead: vi.fn() },
}));

vi.mock("../api/notification-preferences", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/notification-preferences")>()),
  notificationPreferencesApi: { get: vi.fn(), update: vi.fn() },
}));

const ALL_ON = {
  assigned: true,
  comment_added: true,
  transition_pending: true,
  suspect_flagged: true,
};

const ALL_OFF = {
  assigned: false,
  comment_added: false,
  transition_pending: false,
  suspect_flagged: false,
};

const feedItem = {
  id: "n1",
  kind: "assigned" as const,
  artifactId: "a1",
  message: "REQ-1 assigned to you",
  read: false,
  createdAt: "2026-09-04T10:00:00Z",
};

describe("useNotificationFeed", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.mocked(notificationsApi.list)
      .mockReset()
      .mockResolvedValue({ notifications: [feedItem], unreadCount: 1 });
    vi.mocked(notificationsApi.markRead).mockReset().mockResolvedValue({ ...feedItem, read: true });
    vi.mocked(notificationsApi.markAllRead).mockReset().mockResolvedValue(1);
    vi.mocked(notificationPreferencesApi.get).mockReset().mockResolvedValue({ ...ALL_ON });
  });

  it("fetches the feed and the preferences exactly once per mount", async () => {
    renderHook(() => useNotificationFeed());

    await waitFor(() => expect(notificationsApi.list).toHaveBeenCalledTimes(1));
    expect(notificationPreferencesApi.get).toHaveBeenCalledTimes(1);
  });

  it("exposes loading, then success, then the unread count", async () => {
    const { result } = renderHook(() => useNotificationFeed());
    expect(result.current.status).toBe("loading");
    expect(result.current.unreadCount).toBe(0);

    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.unreadCount).toBe(1);
    expect(result.current.notifications).toHaveLength(1);
  });

  it("reports an error state when the feed cannot be loaded", async () => {
    vi.mocked(notificationsApi.list).mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useNotificationFeed());

    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.unreadCount).toBe(0);
  });

  it("does not suppress while at least one trigger is enabled", async () => {
    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_ON, assigned: false });
    const { result } = renderHook(() => useNotificationFeed());

    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.suppressed).toBe(false);
    expect(result.current.preferencesFailed).toBe(false);
  });

  it("suppresses only on a total opt-out", async () => {
    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_OFF });
    const { result } = renderHook(() => useNotificationFeed());

    await waitFor(() => expect(result.current.suppressed).toBe(true));
  });

  it("fails OPEN and discloses when the preferences cannot be read", async () => {
    vi.mocked(notificationPreferencesApi.get).mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useNotificationFeed());

    await waitFor(() => expect(result.current.preferencesFailed).toBe(true));
    expect(result.current.suppressed).toBe(false);
    expect(result.current.unreadCount).toBe(1);
  });

  // The ADR's verification note. The widget persists its panel-open state in
  // `localStorage`; the opt-out is account-scoped server state. If the hook
  // persisted anything, an opted-out user could be shown a restored badge on
  // the next mount. Nothing is.
  it("persists nothing, so no cached unread count can outlive an opt-out", async () => {
    const { result } = renderHook(() => useNotificationFeed());
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.unreadCount).toBe(1);

    expect(localStorage.length).toBe(0);
    expect(localStorage.getItem("reqflow-interview-widget-open")).toBeNull();
  });

  it("re-reads the preference on every mount, so an opt-out takes effect at once", async () => {
    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_ON });
    const first = renderHook(() => useNotificationFeed());
    await waitFor(() => expect(first.result.current.suppressed).toBe(false));
    first.unmount();

    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_OFF });
    const second = renderHook(() => useNotificationFeed());
    await waitFor(() => expect(second.result.current.suppressed).toBe(true));
    expect(notificationPreferencesApi.get).toHaveBeenCalledTimes(2);
  });

  // Live-verified in the browser on 2026-09-27: the user switches every
  // trigger off on /profile and the badge kept sitting on the widget until the
  // next remount. The profile route and the widget are disjoint subtrees, so
  // the write announces itself on the window and the hook refetches — without
  // the event carrying any state of its own.
  it("refetches when the preferences are written elsewhere in the app", async () => {
    const { result } = renderHook(() => useNotificationFeed());
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.suppressed).toBe(false);

    vi.mocked(notificationPreferencesApi.get).mockResolvedValue({ ...ALL_OFF });
    window.dispatchEvent(new Event(NOTIFICATION_PREFERENCES_CHANGED_EVENT));

    await waitFor(() => expect(result.current.suppressed).toBe(true));
    expect(result.current.unreadCount).toBe(0);
    expect(notificationPreferencesApi.get).toHaveBeenCalledTimes(2);
  });

  it("stops listening once unmounted", async () => {
    const { unmount } = renderHook(() => useNotificationFeed());
    await waitFor(() => expect(notificationPreferencesApi.get).toHaveBeenCalledTimes(1));
    unmount();

    window.dispatchEvent(new Event(NOTIFICATION_PREFERENCES_CHANGED_EVENT));

    expect(notificationPreferencesApi.get).toHaveBeenCalledTimes(1);
  });

  it("marks everything read and refetches", async () => {
    const { result } = renderHook(() => useNotificationFeed());
    await waitFor(() => expect(result.current.status).toBe("success"));

    await act(async () => {
      await result.current.markAllRead();
    });

    expect(notificationsApi.markAllRead).toHaveBeenCalledTimes(1);
    expect(notificationsApi.list).toHaveBeenCalledTimes(2);
    expect(result.current.markPending).toBe(false);
  });

  it("marks one notification read and refetches", async () => {
    const { result } = renderHook(() => useNotificationFeed());
    await waitFor(() => expect(result.current.status).toBe("success"));

    await act(async () => {
      await result.current.openNotification(feedItem);
    });

    expect(notificationsApi.markRead).toHaveBeenCalledWith("n1");
    expect(notificationsApi.list).toHaveBeenCalledTimes(2);
  });

  it("never rejects when marking read fails — navigation matters more", async () => {
    vi.mocked(notificationsApi.markRead).mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useNotificationFeed());
    await waitFor(() => expect(result.current.status).toBe("success"));

    await act(async () => {
      await expect(result.current.openNotification(feedItem)).resolves.toBeUndefined();
    });
    expect(notificationsApi.list).toHaveBeenCalledTimes(2);
  });
});
